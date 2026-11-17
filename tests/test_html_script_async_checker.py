#!/usr/bin/env python3
"""Tests for html_script_async_checker — stdlib unittest only.

Every HTML document in this file is made up for testing.
No real secret appears anywhere in this file.
"""

import ast
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import html_script_async_checker as checker

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src/html_script_async_checker.py"

HEAD = "<html><head>%s</head><body></body></html>"


def run_cli(argv):
    """Run main(argv), capture stdout/stderr, return (code, out, err)."""
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = checker.main(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def write(tmp, name, text, encoding="utf-8"):
    path = Path(tmp) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding=encoding)
    return str(path)


def findings_of(text):
    return checker.check_text(text)


class TestHeadScriptDetection(unittest.TestCase):
    def test_head_script_without_async_or_defer_fails(self):
        bad = findings_of(HEAD % '<script src="app.js"></script>')
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 1)
        self.assertEqual(bad[0]["src"], "app.js")
        self.assertEqual(bad[0]["reason"],
                         "in <head> without async or defer")

    def test_head_script_with_async_passes(self):
        self.assertEqual(
            findings_of(HEAD % '<script src="app.js" async></script>'),
            [])

    def test_head_script_with_defer_passes(self):
        self.assertEqual(
            findings_of(HEAD % '<script src="app.js" defer></script>'),
            [])

    def test_head_script_with_both_passes(self):
        self.assertEqual(
            findings_of(HEAD % '<script src="app.js" async defer>'
                        '</script>'),
            [])

    def test_async_with_value_passes(self):
        self.assertEqual(
            findings_of(HEAD % '<script src="app.js" async="async">'
                        '</script>'),
            [])

    def test_defer_with_value_passes(self):
        self.assertEqual(
            findings_of(HEAD % '<script src="app.js" defer="defer">'
                        '</script>'),
            [])

    def test_body_script_not_flagged(self):
        text = ("<html><head></head><body>"
                '<script src="body.js"></script></body></html>')
        self.assertEqual(findings_of(text), [])

    def test_inline_head_script_not_flagged(self):
        self.assertEqual(
            findings_of(HEAD % "<script>console.log(1);</script>"), [])

    def test_empty_src_not_flagged(self):
        self.assertEqual(
            findings_of(HEAD % '<script src=""></script>'), [])

    def test_several_head_scripts_in_document_order(self):
        bad = findings_of(
            "<html>\n<head>\n"
            '<script src="a.js"></script>\n'
            '<script src="b.js"></script>\n'
            '<script src="c.js"></script>\n'
            "</head>\n<body></body>\n</html>")
        self.assertEqual([item["line"] for item in bad], [3, 4, 5])
        self.assertEqual([item["src"] for item in bad],
                         ["a.js", "b.js", "c.js"])

    def test_uppercase_tag_and_attrs_checked(self):
        bad = findings_of(HEAD % '<SCRIPT SRC="upper.js"></SCRIPT>')
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["src"], "upper.js")

    def test_uppercase_async_passes(self):
        self.assertEqual(
            findings_of(HEAD % '<SCRIPT SRC="a.js" ASYNC></SCRIPT>'), [])

    def test_script_split_across_lines_reports_start_line(self):
        bad = findings_of(
            "<html>\n<head>\n"
            '<script\n  src="split.js">\n</script>\n'
            "</head>\n<body></body>\n</html>")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 3)

    def test_script_before_head_not_flagged(self):
        text = ("<html><script src=\"early.js\"></script>"
                "<head></head><body></body></html>")
        self.assertEqual(findings_of(text), [])

    def test_script_after_unclosed_head_is_body_script(self):
        # A browser closes the head when the body starts.
        text = ("<html><head><title>t</title>"
                "<body><script src=\"body.js\"></script>"
                "</body></html>")
        self.assertEqual(findings_of(text), [])

    def test_script_in_unclosed_head_flagged(self):
        text = ("<html><head><title>t</title>"
                '<script src="head.js"></script>')
        bad = findings_of(text)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["src"], "head.js")

    def test_second_head_checked(self):
        # A malformed page with two heads still checks both.
        text = ("<html><head><script src=\"a.js\"></script></head>"
                "<head><script src=\"b.js\"></script></head>"
                "<body></body></html>")
        bad = findings_of(text)
        self.assertEqual([item["src"] for item in bad], ["a.js", "b.js"])

    def test_file_with_no_scripts_passes(self):
        self.assertEqual(findings_of("<html><head><title>t</title>"
                                     "</head><body><p>hi</p></body>"
                                     "</html>"),
                         [])

    def test_empty_document_passes(self):
        self.assertEqual(findings_of(""), [])

    def test_self_closing_head_script_flagged(self):
        bad = findings_of(HEAD % '<script src="a.js" />')
        self.assertEqual(len(bad), 1)

    def test_self_closing_head_script_with_defer_passes(self):
        self.assertEqual(
            findings_of(HEAD % '<script src="a.js" defer />'), [])

    def test_src_with_query_string_flagged(self):
        bad = findings_of(HEAD % '<script src="app.js?v=2"></script>')
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["src"], "app.js?v=2")


class TestSkipping(unittest.TestCase):
    def test_script_in_comment_not_flagged(self):
        text = ("<html><head><!-- <script src=\"c.js\"></script> -->"
                "</head><body></body></html>")
        self.assertEqual(findings_of(text), [])

    def test_script_in_script_string_not_flagged(self):
        text = ("<html><head><script>"
                "var m = '<script src=\"s.js\"></script>';"
                "</script></head><body></body></html>")
        self.assertEqual(findings_of(text), [])

    def test_script_in_style_block_not_flagged(self):
        text = ("<html><head><style>"
                '.x { content: "<script src=\\"s.js\\">"; }'
                "</style></head><body></body></html>")
        self.assertEqual(findings_of(text), [])

    def test_real_script_after_script_block_checked(self):
        text = ("<html><head><script>var a = 1;</script>"
                '<script src="real.js"></script>'
                "</head><body></body></html>")
        bad = findings_of(text)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["src"], "real.js")


class TestCLI(unittest.TestCase):
    def test_exit_0_on_clean_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "page.html",
                         HEAD % '<script src="a.js" async></script>')
            code, out, _err = run_cli([path])
            self.assertEqual(code, 0)
            self.assertIn("OK", out)

    def test_exit_1_on_flagged_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "page.html",
                         HEAD % '<script src="a.js"></script>')
            code, out, _err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("without async or defer", out)

    def test_exit_2_on_missing_path(self):
        code, _out, err = run_cli(["no-such-file"])
        self.assertEqual(code, 2)
        self.assertIn("error", err)

    def test_exit_2_on_no_paths(self):
        code, _out, err = run_cli([])
        self.assertEqual(code, 2)

    def test_exit_2_on_empty_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _out, err = run_cli([tmp])
            self.assertEqual(code, 2)
            self.assertIn("no HTML files found", err)

    def test_exit_2_on_bad_flag(self):
        code, _out, _err = run_cli(["--nope"])
        self.assertEqual(code, 2)

    def test_folder_walking(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.html",
                  HEAD % '<script src="a.js"></script>')
            write(tmp, "sub/b.htm",
                  HEAD % '<script src="b.js" defer></script>')
            write(tmp, "sub/c.txt",
                  HEAD % '<script src="c.js"></script>')
            code, out, _err = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("a.js", out)
            self.assertNotIn("c.txt", out)
            self.assertIn("Checked 2 file(s)", out)

    def test_nested_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a/b/page.html",
                  HEAD % '<script src="a.js"></script>')
            code, out, _err = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("Checked 1 file(s)", out)

    def test_no_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.html",
                  HEAD % '<script src="a.js" async></script>')
            write(tmp, "sub/b.html",
                  HEAD % '<script src="b.js"></script>')
            code, out, _err = run_cli(["--no-recursive", tmp])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_exclude(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.html",
                  HEAD % '<script src="a.js"></script>')
            write(tmp, "skip/b.html",
                  HEAD % '<script src="b.js"></script>')
            code, out, _err = run_cli(["--exclude", "skip", tmp])
            self.assertEqual(code, 1)
            self.assertIn("Checked 1 file(s)", out)

    def test_git_folder_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.html",
                  HEAD % '<script src="a.js" async></script>')
            write(tmp, ".git/b.html",
                  HEAD % '<script src="b.js"></script>')
            code, out, _err = run_cli([tmp])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_direct_file_checked_whatever_its_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "weird-name.txt",
                         HEAD % '<script src="a.js"></script>')
            code, out, _err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("without async or defer", out)

    def test_duplicate_paths_checked_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.html",
                         HEAD % '<script src="a.js" async></script>')
            code, out, _err = run_cli([path, path])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.html",
                         HEAD % '<script src="a.js"></script>')
            code, out, _err = run_cli(["--json", path])
            self.assertEqual(code, 1)
            data = json.loads(out)
            self.assertEqual(data["checked"], 1)
            self.assertEqual(data["findings"], 1)
            self.assertEqual(data["files"][0]["findings"][0]["src"],
                             "a.js")

    def test_stdin(self):
        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(
                HEAD % '<script src="a.js"></script>')
            code, out, _err = run_cli(["--stdin"])
        finally:
            sys.stdin = old_stdin
        self.assertEqual(code, 1)
        self.assertIn("without async or defer", out)

    def test_stdin_clean(self):
        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(
                HEAD % '<script src="a.js" async></script>')
            code, out, _err = run_cli(["--stdin"])
        finally:
            sys.stdin = old_stdin
        self.assertEqual(code, 0)
        self.assertIn("OK", out)

    def test_stdin_via_subprocess(self):
        result = subprocess.run(
            [sys.executable, str(SRC), "--stdin"],
            input=HEAD % '<script src="a.js"></script>',
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("without async or defer", result.stdout)

    def test_version(self):
        code, out, _err = run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("html_script_async_checker 1.0.0", out)

    def test_non_utf8_file_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.html", b"<html>\xff</html>")
            code, out, _err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("not valid UTF-8", out)

    def test_input_files_left_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.html",
                         HEAD % '<script src="a.js"></script>')
            before = Path(path).read_text()
            run_cli([path])
            self.assertEqual(Path(path).read_text(), before)

    def test_run_from_another_folder_and_changed_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "fakehome"
            home.mkdir()
            work = Path(tmp) / "work"
            work.mkdir()
            target = write(str(work), "a.html",
                           HEAD % '<script src="a.js"></script>')
            env = dict(os.environ)
            env["HOME"] = str(home)
            result = subprocess.run(
                [sys.executable, str(SRC), target],
                cwd=str(work), env=env,
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("without async or defer", result.stdout)


class TestExamples(unittest.TestCase):
    def test_run_example_output_matches_sample(self):
        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        expected = (REPO / "examples/sample-output.md").read_text()
        self.assertEqual(result.stdout, expected)

    def test_readme_quotes_match_real_runs(self):
        readme = (REPO / "README.md").read_text()
        clean = subprocess.run(
            [sys.executable, "src/html_script_async_checker.py",
             "examples/clean.html"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(clean.returncode, 0)
        self.assertIn(clean.stdout.strip(), readme)
        flagged = subprocess.run(
            [sys.executable, "src/html_script_async_checker.py",
             "examples/flagged.html"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(flagged.returncode, 1)
        self.assertIn(flagged.stdout.strip(), readme)
        folder = subprocess.run(
            [sys.executable, "src/html_script_async_checker.py",
             "examples/"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(folder.returncode, 1)
        self.assertIn("Checked 3 file(s), 3 blocking <script> tag(s) "
                      "in 1 file(s).", folder.stdout)
        self.assertIn("Checked 3 file(s), 3 blocking <script> tag(s) "
                      "in 1 file(s).", readme)
        edge = subprocess.run(
            [sys.executable, "src/html_script_async_checker.py",
             "examples/edge.html"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(edge.returncode, 0)
        self.assertIn(edge.stdout.strip(), readme)
        js = subprocess.run(
            [sys.executable, "src/html_script_async_checker.py",
             "--json", "examples/flagged.html"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(js.returncode, 1)
        self.assertIn(js.stdout.strip(), readme)


class TestHygiene(unittest.TestCase):
    def _repo_files(self, skip_tests=True, skip_examples=True):
        for root, dirs, files in os.walk(REPO):
            dirs[:] = [d for d in dirs
                       if d not in (".git", "__pycache__")
                       and not (skip_tests and d == "tests")
                       and not (skip_examples and d == "examples")]
            for name in files:
                if name.endswith(".pyc"):
                    continue
                yield Path(root) / name

    def test_no_placeholder_text(self):
        banned = ["TODO", "coming soon", "lorem", "FIXME", "XXX"]
        hits = []
        for path in self._repo_files(skip_tests=True,
                                     skip_examples=False):
            text = path.read_text(errors="ignore")
            for word in banned:
                if word in text:
                    hits.append("%s: %s" % (path.name, word))
        self.assertEqual(hits, [])

    def test_no_absolute_paths(self):
        hits = []
        for path in self._repo_files(skip_tests=True,
                                     skip_examples=False):
            text = path.read_text(errors="ignore")
            for marker in ("/home/", "/Users/", "C:\\"):
                if marker in text:
                    hits.append("%s: %s" % (path.name, marker))
        self.assertEqual(hits, [])

    def test_no_real_secrets_outside_tests_and_examples(self):
        # The source holds no key values at all; the tests
        # and examples hold fake values only, so they are
        # excluded from this scan.
        patterns = [
            re.compile(r"AKIA[0-9A-Z]{16}"),
            re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
            re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
            re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
            re.compile(r"AIza[0-9A-Za-z_-]{35}"),
            re.compile(r"[rs]k_(?:live|test)_[A-Za-z0-9]{16,}"),
            re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
            re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ"),
        ]
        hits = []
        for path in self._repo_files():
            text = path.read_text(errors="ignore")
            for pattern in patterns:
                if pattern.search(text):
                    hits.append("%s: %s" % (path.name, pattern.pattern))
        self.assertEqual(hits, [])

    def test_stdlib_imports_only(self):
        stdlib = set(sys.stdlib_module_names)
        for target in (REPO / "src/html_script_async_checker.py",
                       REPO / "tests/test_html_script_async_checker.py"):
            tree = ast.parse(target.read_text())
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0]
                                    for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertFalse(
                imported - stdlib - {"html_script_async_checker"},
                (target.name, imported))
            self.assertNotIn("yaml", imported)

    def test_no_network_use_in_src(self):
        src = (REPO / "src/html_script_async_checker.py").read_text()
        for marker in ("urllib.request", "requests", "socket",
                       "http.client", "urlopen", "urlretrieve"):
            self.assertNotIn(marker, src, marker)

    def test_gitignore_lists_env_first(self):
        lines = (REPO / ".gitignore").read_text().splitlines()
        self.assertEqual(lines[0], ".env")

    def test_ci_runs_this_test_file(self):
        ci = (REPO / ".github/workflows/ci.yml").read_text()
        self.assertIn("tests/test_html_script_async_checker.py", ci)
        self.assertIn("ubuntu-latest", ci)
        self.assertIn("3.12", ci)
        self.assertIn("actions/checkout", ci)
        self.assertIn("setup-python", ci)
        self.assertIn("push", ci)
        self.assertIn("pull_request", ci)

    def test_readme_names_the_neighbouring_repo(self):
        readme = (REPO / "README.md").read_text()
        self.assertIn("html-script-src-checker-cli", readme)


if __name__ == "__main__":
    unittest.main()
