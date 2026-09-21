#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["jinja2>=3.1,<4"]
# ///

"""Render HTML templates from src/ to dist/."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

import ssgen

SOURCE = Path("src")
OUTPUT = Path("dist")
TEMPLATES = Path("templates")

environment = Environment(
    loader=FileSystemLoader(TEMPLATES),
    autoescape=select_autoescape(default_for_string=True),
)


def render_template(path: Path) -> tuple[Path, ssgen.Transform]:
    if path.suffix != ".html":
        return path, lambda contents: contents

    def render(contents: ssgen.Contents) -> str:
        template = environment.from_string(ssgen.read(contents, str))
        return template.render(path=path)

    return path, render


if __name__ == "__main__":
    ssgen.main(
        SOURCE,
        OUTPUT,
        rules=(render_template,),
        watch=(TEMPLATES,),
    )
