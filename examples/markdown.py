#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["markdown-it-py>=4,<5"]
# ///

"""Render Markdown from src/ to dist/, and generate an index page."""

import html
from pathlib import Path
from urllib.parse import quote

from markdown_it import MarkdownIt

import ssgen

SOURCE = Path("src")
OUTPUT = Path("dist")
markdown = MarkdownIt("commonmark")


def title(path: Path) -> str:
    return path.stem.replace("-", " ").replace("_", " ").title()


def page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
</head>
<body>
{body}
</body>
</html>
"""


def articles() -> list[Path]:
    return [path.relative_to(SOURCE) for path in sorted(SOURCE.rglob("*.md"))]


def render_markdown(path: Path) -> tuple[Path, ssgen.Transform]:
    if path.suffix != ".md":
        return path, lambda contents: contents

    output = path.with_suffix("") / "index.html"

    def render(contents: ssgen.Contents) -> str:
        body = markdown.render(ssgen.read(contents, str))
        return page(title(path), body)

    return output, render


def generate_index(path: Path) -> tuple[Path, ssgen.Transform]:
    if path != Path("index.html"):
        return path, lambda contents: contents

    def render(_: ssgen.Contents) -> str:
        links = [
            f'<li><a href="{quote(article.with_suffix("").as_posix())}/">'
            f"{html.escape(title(article))}</a></li>"
            for article in articles()
        ]
        body = "<h1>Articles</h1>\n<ul>\n" + "\n".join(links) + "\n</ul>"
        return page("Articles", body)

    return path, render


if __name__ == "__main__":
    ssgen.main(SOURCE, OUTPUT, rules=(render_markdown, generate_index))
