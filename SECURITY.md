# Security Policy

This tool runs locally, collects no data, sends nothing anywhere, and needs no API key or secret. It only reads the HTML files you point it at, and it never rewrites a file and never changes anything. It writes nothing except the report on standard output (and usage errors on standard error). It never fetches a URL: a script tag is checked for async or defer, not loaded.

It only checks that a `<script src>` tag inside `<head>` carries async or defer. It never loads a page, never runs JavaScript, and never executes a script.

If you find a case where the tool rewrites a file, opens a URL, or reports a pass for an HTML file with a blocking script in the head, please open an issue describing the exact commands and input. Do not include any real secret in the report.
