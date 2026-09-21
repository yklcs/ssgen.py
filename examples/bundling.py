#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

"""Bundle JavaScript and TypeScript using esbuild via CLI."""

import subprocess
from pathlib import Path

import ssgen

SOURCE = Path("src")
OUTPUT = Path("dist")
ENTRY_POINTS = {Path("main.ts")}
SCRIPT_SUFFIXES = {".js", ".jsx", ".ts", ".tsx"}


def bundle(path: Path) -> tuple[Path, ssgen.Transform] | None:
    if path not in ENTRY_POINTS:
        if path.suffix in SCRIPT_SUFFIXES:
            return None
        return path, lambda contents: contents

    output = path.with_suffix(".js")

    def run_esbuild(_: ssgen.Contents) -> bytes:
        return subprocess.check_output(
            (
                "esbuild",
                str(SOURCE / path),
                "--bundle",
                "--format=esm",
                "--platform=browser",
            )
        )

    return output, run_esbuild


if __name__ == "__main__":
    ssgen.main(SOURCE, OUTPUT, rules=(bundle,))
