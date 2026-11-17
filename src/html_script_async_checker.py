#!/usr/bin/env python3
"""Check <script src> tags inside <head> carry async or defer.

Run: python3 src/html_script_async_checker.py page.html
     python3 src/html_script_async_checker.py site/
     python3 src/html_script_async_checker.py --stdin < page.html

A render-blocking script in the head stalls the
first paint — the page looks slow for a reason
that reads like a server problem, not a script
tag. This tool reads each HTML file, finds every
<script src> tag inside <head> without async or
defer, and reports each one with the file and the
line number. It exits 1 when any head script
blocks rendering, so it can fail a CI run. A file
whose head scripts all carry async or defer
exits 0.

Only head scripts are checked. A script at the
end of the body does not block rendering, so it
is never flagged, and neither is an inline
<script> with no src — there is nothing to load.
A head script counts as non-blocking when it
carries async or defer, in any form: a bare
attribute, async="async", or defer="defer" all
count. Tag and attribute names are matched
without regard to case, as HTML requires.

A file given directly on the command line is
always checked, whatever its name. A folder is
walked for files ending in .html or .htm only,
recursively by default (--no-recursive stops at
the top level). .git folders are never walked,
and directory links are never followed.

Scripts inside HTML comments are not scripts —
the parser skips them. Markup inside <script>
and <style> blocks is not parsed as HTML either,
so a "<script src>" written in a JavaScript
string or a stylesheet is left alone.

It never rewrites a file, never touches the
network, and reads only the files and folders
you point it at.
"""

import argparse
import fnmatch
import json
import os
import sys
from html.parser import HTMLParser
from pathlib import Path

__version__ = "1.0.0"

HTML_SUFFIXES = (".html", ".htm")


class HeadScriptParser(HTMLParser):
    """Collect every blocking <script src> inside <head>.

    HTMLParser already treats <script> and <style>
    content as character data, so markup written
    inside those blocks never reaches handle_starttag.
    Comments never reach it either.

    The head is entered on <head> and left on
    </head>, or on <body> — a browser closes the
    head implicitly when the body starts, so a
    script after an unclosed head still counts as
    a body script.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.findings = []
        self.in_head = False

    def handle_starttag(self, tag, attrs):
        if tag == "head":
            self.in_head = True
            return
        if tag == "body":
            self.in_head = False
            return
        if tag != "script" or not self.in_head:
            return
        values = dict(attrs)
        src = values.get("src")
        if not src:
            # No src to load (inline script, or an empty
            # src) — nothing blocks rendering.
            return
        if "async" in values or "defer" in values:
            return
        line, _offset = self.getpos()
        self.findings.append({
            "line": line,
            "src": src,
            "reason": "in <head> without async or defer",
        })

    def handle_endtag(self, tag):
        if tag == "head":
            self.in_head = False


def check_text(text):
    """Check one document's text.

    Returns a list of findings, each {"line": int,
    "src": str, "reason": str}, in document order.
    """
    parser = HeadScriptParser()
    parser.feed(text)
    parser.close()
    return parser.findings


def check_file(path):
    """Check one file. Returns (findings, error)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [], "not valid UTF-8"
    except OSError as exc:
        return [], str(exc)
    try:
        return check_text(text), None
    except Exception as exc:  # malformed markup the parser rejects
        return [], "could not be parsed: %s" % exc


def _is_html_file(path):
    return Path(path).name.lower().endswith(HTML_SUFFIXES)


def collect_files(paths, recursive=True, exclude=None):
    """Expand CLI paths into a sorted list of HTML files.

    A file given directly is always checked, whatever its
    name. A folder is walked for files ending in .html
    or .htm only. .git folders are never walked, and
    directory links are never followed.
    """
    exclude = exclude or []
    found = []
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            found.append(str(path))
        elif path.is_dir():
            for dirpath, dirs, files in os.walk(path, followlinks=False):
                dirs[:] = [
                    d for d in dirs
                    if d != ".git"
                    and not any(fnmatch.fnmatch(d, pat) for pat in exclude)
                ]
                for name in files:
                    candidate = Path(dirpath) / name
                    if not _is_html_file(candidate):
                        continue
                    if any(
                        fnmatch.fnmatch(str(candidate), pat)
                        or fnmatch.fnmatch(name, pat)
                        for pat in exclude
                    ):
                        continue
                    found.append(str(candidate))
                if not recursive:
                    break
        else:
            raise FileNotFoundError("no such file or folder: %s" % raw)
    seen = set()
    unique = []
    for item in found:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return sorted(unique)


def format_finding(path, finding):
    """One human-readable line for one blocking head script."""
    return ("FAIL %s: <script src=\"%s\"> line %d %s"
            % (path, finding["src"], finding["line"],
               finding["reason"]))


def run(paths, recursive=True, exclude=None, as_json=False):
    """Check paths, print the report, return the exit code."""
    try:
        files = collect_files(paths, recursive=recursive, exclude=exclude)
    except FileNotFoundError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if not files:
        print("error: no HTML files found", file=sys.stderr)
        return 2
    results = []
    findings = 0
    files_with_findings = 0
    for path in files:
        bad, error = check_file(path)
        count = len(bad) + (1 if error else 0)
        if count:
            findings += count
            files_with_findings += 1
        results.append({"path": path, "findings": bad, "error": error})
    if as_json:
        print(json.dumps(
            {"files": results, "checked": len(files),
             "findings": findings},
            indent=2))
    else:
        for result in results:
            if result["error"]:
                print("FAIL %s: %s" % (result["path"], result["error"]))
            for finding in result["findings"]:
                print(format_finding(result["path"], finding))
        if findings:
            print("Checked %d file(s), %d blocking <script> tag(s) "
                  "in %d file(s)." % (len(files), findings,
                                      files_with_findings))
        else:
            print("OK — %d file(s) checked, no blocking <script> "
                  "in <head>." % len(files))
    return 1 if findings else 0


def run_stdin(as_json=False):
    """Check one HTML document read from standard input."""
    text = sys.stdin.read()
    bad = check_text(text)
    findings = len(bad)
    if as_json:
        print(json.dumps(
            {"files": [{"path": "<stdin>", "findings": bad,
                        "error": None}],
             "checked": 1, "findings": findings},
            indent=2))
    else:
        for finding in bad:
            print(format_finding("<stdin>", finding))
        if findings:
            print("Checked 1 file(s), %d blocking <script> tag(s) "
                  "in 1 file(s)." % findings)
        else:
            print("OK — 1 file(s) checked, no blocking <script> "
                  "in <head>.")
    return 1 if findings else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="html_script_async_checker",
        description="Check <script src> tags inside <head> "
                    "carry async or defer, fail CI when one "
                    "does not.")
    parser.add_argument("paths", nargs="*",
                        help="HTML files or folders to walk")
    parser.add_argument("--no-recursive", action="store_true",
                        help="do not walk into subfolders")
    parser.add_argument("--exclude", action="append", default=[],
                        help="skip files or folders matching this pattern "
                             "(repeatable)")
    parser.add_argument("--json", action="store_true",
                        help="print the result as JSON")
    parser.add_argument("--stdin", action="store_true",
                        help="check one HTML document from standard input")
    parser.add_argument("--version", action="version",
                        version="%(prog)s " + __version__)
    args = parser.parse_args(argv)
    if args.stdin:
        if args.paths:
            parser.error("--stdin takes no file or folder arguments")
        return run_stdin(as_json=args.json)
    if not args.paths:
        parser.error("give at least one HTML file or folder")
    return run(args.paths, recursive=not args.no_recursive,
               exclude=args.exclude, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
