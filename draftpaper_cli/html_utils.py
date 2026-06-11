from __future__ import annotations

import re
from html import escape
from pathlib import Path


def markdown_to_html(markdown: str, *, title: str = "DraftPaper Report") -> str:
    """Render a conservative Markdown subset as standalone HTML for local review."""
    body: list[str] = []
    in_list = False
    in_code = False
    code_lines: list[str] = []

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            body.append("</ul>")
            in_list = False

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.startswith("```"):
            if in_code:
                body.append("<pre><code>" + escape("\n".join(code_lines)) + "</code></pre>")
                code_lines = []
                in_code = False
            else:
                close_list()
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not line.strip():
            close_list()
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            close_list()
            level = len(heading.group(1))
            body.append(f"<h{level}>{_inline_markdown(heading.group(2))}</h{level}>")
            continue
        if line.startswith("- "):
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append(f"<li>{_inline_markdown(line[2:])}</li>")
            continue
        close_list()
        body.append(f"<p>{_inline_markdown(line)}</p>")
    close_list()
    if in_code:
        body.append("<pre><code>" + escape("\n".join(code_lines)) + "</code></pre>")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escape(title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; max-width: 980px; margin: 32px auto; line-height: 1.58; color: #202124; }}
    h1, h2, h3 {{ color: #111827; }}
    code {{ background: #f3f4f6; padding: 0.1rem 0.25rem; border-radius: 4px; }}
    pre {{ background: #f8fafc; padding: 16px; overflow-x: auto; border: 1px solid #e5e7eb; }}
    li {{ margin: 0.35rem 0; }}
  </style>
</head>
<body>
{chr(10).join(body)}
</body>
</html>
"""


def write_html_report(path: Path, markdown: str, *, title: str) -> None:
    path.write_text(markdown_to_html(markdown, title=title), encoding="utf-8")


def _inline_markdown(text: str) -> str:
    escaped = escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped
