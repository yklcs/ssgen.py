# ssgen.py

A single-file library to build your own static site generator.
Requires Python 3.13+, has no external dependencies.
The main idea is to build sites based on functional rules:

```python
type Transform = Callable[[Contents], Contents]
type Rule = Callable[[Path], tuple[Path, Transform] | None]
```

Features:

- functional routing and content transformation
- unopinionated and minimal (bring your own markup, templating, etc.)
- static builder + hot reloading development server
- small "agent-friendly" core

## Usage

### Quick Start

1. Copy ssgen.py into your project, and import it in a build script
2. Write your own `ssgen.Rule`s to map paths and transform content
3. Use `ssgen.main` to build a CLI with your directories

A minimal build script is shown below.
See [examples/](examples/) for more examples.

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

import ssgen
from pathlib import Path


def markdown(path: Path):
    if path.suffix != ".md":
        return path, lambda x: x

    output = path.with_suffix("") / "index.html"

    def transform(contents: ssgen.Contents) -> ssgen.Contents:
        return "<h1>" + ssgen.read(contents, str).strip("# \n") + "</h1>"

    return output, transform


if __name__ == "__main__":
    ssgen.main(
        srcdir="src/",
        outdir="dist/",
        rules=(markdown,),
    )
```

> [!TIP]
> Use [PEP 723](https://peps.python.org/pep-0723/) or [uv scripts](https://docs.astral.sh/uv/guides/scripts/#declaring-script-dependencies) like above for a self-contained build script.

> [!TIP]
> LLMs are great at writing rules, feed your agent ssgen.py and ask it to write rules following the `ssgen` API.

### Rules

A `Rule` is a function, and receives a relative path.
If a tuple `(newpath, tf) = rule(path)` is returned:

- `newpath` is used as the output route, and
- `tf` is used to transform the contents of `path` as in
  `newcontents = tf(contents)`.

Otherwise, returning `None` excludes the path from output.
Rules run in order, and all routing and transformations are chained.
Conceptually, for a single path and its contents, ssgen.py performs the following:

```python
def process(path: Path, contents: Contents):
    transforms = []

    for rule in rules:
        result = rule(path)
        if result is None:
            return None
        path, transform = result
        transforms.append(transform)

    for transform in transforms:
        contents = transform(contents)

    return path, contents
```

## Philosophy

A static site generator has two parts:

- **site-independent** code
  - build command, development server, etc.
  - this is what **ssgen.py** provides
- **site-specific** code
  - opinionated choices such as templating and markup (see all the Markdown dialects out there)
  - this is what **you** write via rules
  - LLMs are great at writing this part using ssgen.py's abstractions

ssgen.py aims to be a minimal solution to the first part,
and an elegant abstraction to write the second part upon.

## License

<details>
  <summary>MIT License</summary>

Copyright 2026 Lucas Yunkyu Lee

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

</details>
