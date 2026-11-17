# html-script-async-checker-cli

Check every `<script src>` tag inside `<head>` carries async or defer — fail CI when one blocks rendering.

[![CI](https://github.com/haiderstudio/html-script-async-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/html-script-async-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`html_script_async_checker` reads each HTML file,
finds every `<script src>` tag inside `<head>`
without `async` or `defer`, and reports each one
with the file and the line number. It exits 1 when
any head script blocks rendering, so it can fail a
CI run. A file whose head scripts all carry
`async` or `defer` exits 0.

- A render-blocking script in the head stalls the
  first paint — the page looks slow for a reason
  that reads like a server problem, not a script
  tag. This names the exact line, and the fix is
  one attribute per tag once found.
- Only head scripts are checked. A script at the
  end of the body does not block rendering, so it
  is never flagged — and neither is an inline
  `<script>` with no `src`, since there is nothing
  to load. The narrowing matters: demanding
  `async` or `defer` on every script would be
  noise, because it is not always wanted.
- A head script counts as non-blocking when it
  carries `async` or `defer`, in any form: a bare
  attribute, `async="async"`, or `defer="defer"`
  all count. Tag and attribute names are matched
  without regard to case, as HTML requires —
  `<SCRIPT SRC=...>` is checked exactly like
  `<script src=...>`.
- A file given directly on the command line is always
  checked, whatever its name. A folder is walked for
  files ending in `.html` or `.htm` only, recursively
  by default (`--no-recursive` stops at the top
  level). `.git` folders are never walked, and
  directory links are never followed.
- `--json` prints the result as JSON, and `--stdin`
  checks one HTML document read from standard input.
- Scripts inside HTML comments are not scripts — the
  parser skips them. Markup inside `<script>` and
  `<style>` blocks is not parsed as HTML either, so
  a `"<script src>"` written in a JavaScript string
  or a stylesheet is left alone. A script split
  across lines reports the line the tag starts on.
  A head that is never closed still counts as the
  head until the body starts, the way a browser
  reads it.

## Who it is for

Every site owner whose page looks slow for no
clear reason — one render-blocking script in the
head stalls the first paint, and the fix is one
attribute once the tag is found. This is the gate
that stops it at the pull request.

## What it does NOT do

- It does not check whether a `<script>` tag has a
  `src` attribute at all. That is repo #91,
  html-script-src-checker-cli — the `src` attribute
  is a different check on the same tags.
- It does not check scripts in the body, and it
  does not judge whether a script *should* be
  async or defer when it already carries one of
  them — ordering and loading strategy are
  different jobs.
- It does not check whether the file a `src`
  points at exists — existence is a different check
  on the same tags.
- It never rewrites a file, and it never touches the
  network.

## How this differs

- A fresh search of GitHub on Nov 16, 2026 found 0
  results for `"html-script-async-checker-cli"` and 0
  results for `html script async checker` — a
  completely empty field.
- Repo #91 (html-script-src-checker-cli) checks the
  `src` attribute exists; async/defer on head
  scripts is a different check on the same tags.

## Install

```sh
git clone https://github.com/haiderstudio/html-script-async-checker-cli.git
cd html-script-async-checker-cli
```

There is nothing else to install: Python 3.10 or newer,
standard library only, no dependencies.

## Usage

Check one HTML file:

```sh
python3 src/html_script_async_checker.py page.html
```

A file whose head scripts all carry async or defer
passes:

```sh
$ python3 src/html_script_async_checker.py examples/clean.html
OK — 1 file(s) checked, no blocking <script> in <head>.
```

A file with blocking head scripts fails, with the
file and line for each one:

```sh
$ python3 src/html_script_async_checker.py examples/flagged.html
FAIL examples/flagged.html: <script src="app.js"> line 5 in <head> without async or defer
FAIL examples/flagged.html: <script src="vendor.js"> line 6 in <head> without async or defer
FAIL examples/flagged.html: <script src="upper.js"> line 7 in <head> without async or defer
Checked 1 file(s), 3 blocking <script> tag(s) in 1 file(s).
```

Check a whole folder (`.html` / `.htm` files only):

```sh
$ python3 src/html_script_async_checker.py examples/
FAIL examples/flagged.html: <script src="app.js"> line 5 in <head> without async or defer
FAIL examples/flagged.html: <script src="vendor.js"> line 6 in <head> without async or defer
FAIL examples/flagged.html: <script src="upper.js"> line 7 in <head> without async or defer
Checked 3 file(s), 3 blocking <script> tag(s) in 1 file(s).
```

Check one document from standard input:

```sh
$ printf '<head><script src="x.js"></script></head>\n' | python3 src/html_script_async_checker.py --stdin
FAIL <stdin>: <script src="x.js"> line 1 in <head> without async or defer
Checked 1 file(s), 1 blocking <script> tag(s) in 1 file(s).
```

Machine-readable output:

```sh
$ python3 src/html_script_async_checker.py --json examples/flagged.html
{
  "files": [
    {
      "path": "examples/flagged.html",
      "findings": [
        {
          "line": 5,
          "src": "app.js",
          "reason": "in <head> without async or defer"
        },
        {
          "line": 6,
          "src": "vendor.js",
          "reason": "in <head> without async or defer"
        },
        {
          "line": 7,
          "src": "upper.js",
          "reason": "in <head> without async or defer"
        }
      ],
      "error": null
    }
  ],
  "checked": 1,
  "findings": 3
}
```

Exit codes: 0 when no head script blocks rendering,
1 when any head script lacks async or defer or a file
cannot be read, 2 for a usage error (a missing path,
a bad flag, or no HTML files found).

## Examples

Head scripts with async, defer, or both, an inline
head script, and a body-end script all pass —
`examples/clean.html` holds them:

```sh
$ python3 src/html_script_async_checker.py examples/clean.html
OK — 1 file(s) checked, no blocking <script> in <head>.
```

Uppercase tags, a script split across lines, valued
attributes (`async="async"`), a script in a comment
and a script tag inside a script string are all
handled — `examples/edge.html` has all of them,
and it passes:

```sh
$ python3 src/html_script_async_checker.py examples/edge.html
OK — 1 file(s) checked, no blocking <script> in <head>.
```

A body-end script without async or defer is not
flagged — it does not block rendering:

```sh
$ printf '<html><head></head><body><script src="body.js"></script></body></html>\n' | python3 src/html_script_async_checker.py --stdin
OK — 1 file(s) checked, no blocking <script> in <head>.
```

Run every bundled example at once with `sh
examples/run-example.sh` — the output is saved in
[examples/sample-output.md](examples/sample-output.md).

## How it is tested

```sh
python3 tests/test_html_script_async_checker.py
```

The tests cover head-script detection (a head
script without async or defer fails, async passes,
defer passes, both pass, valued async and defer
pass, a body script is not flagged, an inline head
script is not flagged, an empty src is not flagged,
several head scripts in document order, uppercase
tags and attributes, a script split across lines
reports the line the tag starts on, a script before
the head is not flagged, a script after an unclosed
head counts as a body script, a script in an
unclosed head is flagged, two heads are both
checked, a file with no scripts passes, an empty
document passes, a self-closing head script is
flagged and with defer passes, a src with a query
string is flagged), skipping (a script in a
comment, a script in a script string, a script in
a style block, a real script after a script block
checked), the CLI (exit 0/1/2, folder walking for
several HTML files including `.htm`, nested folders,
`--no-recursive`, `--exclude`, `.git` skipped, a
direct file checked whatever its name, duplicate
paths checked once, `--json` output, `--stdin`, bad
flags, missing paths, empty folders, `--version`, a
non-UTF-8 file reported, input files left
unchanged, the tool run from another folder and
under a changed HOME), the bundled examples (sample
output compared byte-for-byte against a fresh run,
and the README-quoted outputs checked against it),
and hygiene checks (no placeholder text, no
absolute paths, no real secrets outside the tests
and examples, stdlib imports only, no network use
in the source, `.env` first in `.gitignore`, CI
file runs the test file, README names the
neighbouring repo).

## Contributing

Small, focused improvements are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool was written from scratch for this repo. The
idea of deferring head scripts is not new, and the
parsing follows Python's own standard-library HTML
parser — but no existing tool does this one job,
checking only `<script src>` tags inside `<head>`
for async or defer, as a tested command-line gate
with a CI exit code, as the search above shows —
and every line of code here is original, built on
nothing but Python's standard library.
