"""
ssgen.py, a single-file static site generator library.

Copy this file to your project,
define `Rule`s to define routes and transformations on your content,
and use `main`, `build`, or `develop` for your own static site generator.
Requires Python 3.13+.

MIT License
Lucas Yunkyu Lee <lucas@yklcs.com>
"""

import argparse
import logging
import mimetypes
import os
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import chain
from pathlib import Path
from threading import Condition, Event, Thread
from typing import overload
from urllib.parse import unquote, urlsplit

__all__ = [
    # Functions
    "build",
    "develop",
    "main",
    "read",
    # Types
    "Rule",
    "Transform",
    "PathLike",
    "Contents",
    "Source",
]

__version__ = "0.1.0"


## Types ##


@dataclass(frozen=True)
class Source:
    """Source file contents that have not yet been read or changed."""

    path: Path


type Contents = str | bytes | Source
"""File contents, used as the input/output for `Transform`."""

type Transform = Callable[[Contents], Contents]
"""A content transformation, to be produced by `Rule`."""

type Rule = Callable[[Path], tuple[Path, Transform] | None]
"""
A rule defining a path routing and its content transformation.

A `rule: Rule` is called on a relative website `path`.

If a tuple `(newpath, tf) = rule(path)` is returned:
    - `newpath` is used as the output route, and
    - `tf` is used to transform the contents of `path` as in
      `newcontents = tf(contents)`.

Otherwise, returning `None` excludes the path from output.
"""

type PathLike = str | Path


## Internal Constants ##


_logger = logging.getLogger(__name__)
_OUTPUT_MARKER = ".ssgen"
_RELOAD_PATH = "/__hot"
_RELOAD_SCRIPT = f"""
    <script>
        new EventSource('{_RELOAD_PATH}').addEventListener(
            'reload', () => location.reload()
        );
    </script>
"""


## Functions ##


def build(
    srcdir: PathLike,
    outdir: PathLike,
    rules: Sequence[Rule] = (),
) -> None:
    """Build a static website by applying `rules` to `srcdir`."""

    srcdir = Path(srcdir).resolve()
    outdir = Path(outdir).resolve()
    if not srcdir.is_dir():
        raise NotADirectoryError(srcdir)

    if srcdir.is_relative_to(outdir) or outdir.is_relative_to(srcdir):
        raise ValueError("srcdir and outdir must not overlap")

    marker = outdir / _OUTPUT_MARKER
    if outdir.exists():
        if not marker.is_file():
            raise ValueError(f"refusing to remove unmarked output directory: {outdir}")
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True)
    marker.touch(exist_ok=False)

    for output, (source, transforms) in _collect(srcdir, rules).items():
        dest = outdir / output
        dest.parent.mkdir(parents=True, exist_ok=True)
        contents = _apply(source, transforms)

        match contents:
            case str():
                dest.write_text(contents, encoding="utf-8", newline="")
            case bytes():
                dest.write_bytes(contents)
            case Source(path):
                assert path == source, "mismatched Source path"
                shutil.copy2(path, dest)
            case _:
                raise TypeError(f"unexpected content type {type(contents)}")


def develop(
    srcdir: PathLike,
    *,
    rules: Sequence[Rule] = (),
    watch: Sequence[PathLike] = (),
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Start a hot-reloading development server by applying `rules` to `srcdir`."""

    srcdir = Path(srcdir).resolve()
    if not srcdir.is_dir():
        raise NotADirectoryError(srcdir)
    roots = tuple(dict.fromkeys((srcdir, *(Path(path).resolve() for path in watch))))
    stopping = Event()
    changed = Condition()
    generation = 0
    routes = _collect(srcdir, rules)

    def watch_changes() -> None:
        nonlocal generation, routes
        previous = _snapshot(roots)
        while not stopping.wait(0.5):
            current = _snapshot(roots)
            if current == previous:
                continue
            previous = current
            try:
                new_routes = _collect(srcdir, rules)
            except Exception:
                _logger.exception("Cannot update routes")
                new_routes = None
            with changed:
                if new_routes is not None:
                    routes = new_routes
                generation += 1
                changed.notify_all()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            try:
                self.respond()
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                _logger.exception("Cannot serve %s", self.path)
                self.send_error(500)

        def do_HEAD(self) -> None:
            self.do_GET()

        def respond(self) -> None:
            try:
                url = urlsplit(self.path)
                decoded = unquote(url.path, errors="strict")
                path = Path(decoded.lstrip("/"))
            except (ValueError, UnicodeError):
                self.send_error(400)
                return

            if url.path == _RELOAD_PATH:
                self.events()
                return

            if ".." in path.parts:
                self.send_error(404)
                return

            with changed:
                current_routes = routes

            if url.path.endswith("/"):
                output = path / "index.html"
            elif path not in current_routes and path / "index.html" in current_routes:
                location = "/" + url.path.lstrip("/") + "/"
                if url.query:
                    location += "?" + url.query
                self.send_response(301)
                self.send_header("Location", location)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            else:
                output = path

            plan = current_routes.get(output)
            if plan is None:
                self.send_error(404)
                return
            source, transforms = plan
            if not source.is_file():
                self.send_error(404)
                return

            contents = _apply(source, transforms)
            if output.suffix.lower() == ".html":
                match contents:
                    case str():
                        html = contents
                    case bytes():
                        html = contents.decode()
                    case Source():
                        html = read(contents, str)
                    case _:
                        raise TypeError(f"unexpected return type {type(contents)}")

                index = html.lower().rfind("</body>")

                if index == -1:
                    contents = html + _RELOAD_SCRIPT
                else:
                    contents = html[:index] + _RELOAD_SCRIPT + "\n" + html[index:]

            match contents:
                case str():
                    contents = contents.encode()
                case bytes():
                    contents = contents
                case Source():
                    contents = read(contents, bytes)
                case _:
                    raise TypeError(f"unexpected content type {type(contents)}")

            content_type = (
                mimetypes.guess_file_type(output)[0] or "application/octet-stream"
            )
            if content_type.startswith("text/"):
                content_type += "; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(contents)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(contents)

        def events(self) -> None:
            observed = generation
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            if self.command == "HEAD":
                return
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while not stopping.is_set():
                with changed:
                    changed.wait(timeout=0.5)
                    current = generation
                message = (
                    b"event: reload\ndata: now\n\n"
                    if current != observed
                    else b": keepalive\n\n"
                )
                self.wfile.write(message)
                self.wfile.flush()
                observed = current

    with ThreadingHTTPServer((host, port), Handler) as server:
        watcher = Thread(target=watch_changes, daemon=True)
        watcher.start()
        print(f"Serving http://{host}:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            stopping.set()
            with changed:
                changed.notify_all()
            watcher.join()


def main(
    srcdir: PathLike,
    outdir: PathLike,
    rules: Sequence[Rule] = (),
    watch: Sequence[PathLike] = (),
) -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command")

    _ = commands.add_parser("build")

    serve = commands.add_parser("serve")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)

    parser.set_defaults(command="build")

    args = parser.parse_args()
    match args.command:
        case "serve":
            develop(srcdir, rules=rules, watch=watch, host=args.host, port=args.port)
        case "build":
            build(srcdir, outdir, rules=rules)


@overload
def read(contents: Contents, as_type: type[str]) -> str: ...


@overload
def read(contents: Contents, as_type: type[bytes]) -> bytes: ...


def read(contents: Contents, as_type: type[str] | type[bytes]) -> str | bytes:
    """
    Read contents to `str` or `bytes`.
    Does not handle conversions between `str` and `bytes`.
    """

    match contents:
        case Source():
            if as_type is str:
                return contents.path.read_text(encoding="utf-8", newline="")
            if as_type is bytes:
                return contents.path.read_bytes()
        case str():
            if as_type is str:
                return contents
        case bytes():
            if as_type is bytes:
                return contents

    raise TypeError(f"cannot read {type(contents)} as {as_type}")


## Internal Functions ##

type _Route = tuple[Path, list[Transform]]


def _collect(srcdir: Path, rules: Sequence[Rule]) -> dict[Path, _Route]:
    def _aux(path: Path, rules: Sequence[Rule]) -> _Route | None:
        assert _is_relative(srcdir, path)

        transforms = []
        for rule in rules:
            result = rule(path)
            match result:
                case (Path() as path, transform) if callable(transform):
                    if not _is_relative(srcdir, path):
                        raise ValueError(f"invalid output path: {path}")
                case None:
                    return None
                case _:
                    raise TypeError(f"{rule} returned an invalid rule result")
            transforms.append(transform)

        return path, transforms

    collected = {}

    for source in sorted(srcdir.rglob("*")):
        if not source.is_file():
            continue

        route = _aux(source.relative_to(srcdir), rules)
        if route is None:
            continue
        output, transforms = route

        if previous := collected.get(output):
            raise ValueError(
                f"multiple sources produce {output}: {previous[0]} and {source}"
            )
        collected[output] = source, transforms

    for output in collected:
        assert _is_relative(srcdir, output)

        parent = output.parent
        while parent != Path():
            if parent in collected:
                raise ValueError(f"output path is both a file and directory: {parent}")
            parent = parent.parent

    return collected


def _apply(source: Path, transforms: Sequence[Transform]) -> Contents:
    contents: Contents = Source(source)
    for transform in transforms:
        contents = transform(contents)
        if not isinstance(contents, (str, bytes, Source)):
            raise TypeError(f"{transform} returned {type(contents)} for {source}")

    return contents


def _snapshot(roots: tuple[Path, ...]) -> dict[Path, tuple[int, int]]:
    snapshot = {}
    for root in roots:
        for path in chain((root,), root.rglob("*")):
            try:
                stat = path.stat()
            except (FileNotFoundError, NotADirectoryError):
                continue
            snapshot[path] = stat.st_mtime_ns, stat.st_size
    return snapshot


def _is_relative(root: Path, path: Path) -> bool:
    absolute = Path(os.path.abspath(root / path))
    return (not path.is_absolute()) and absolute.is_relative_to(root)
