from __future__ import annotations

from collections.abc import Mapping, Sequence


def render_table(rows: Sequence[Mapping[str, object]]) -> str:
    if not rows:
        return ""

    headers = list(rows[0].keys())
    widths = {header: len(header) for header in headers}
    for row in rows:
        for header in headers:
            widths[header] = max(widths[header], len(str(row.get(header, ""))))

    def format_row(row: Mapping[str, object]) -> str:
        return " | ".join(str(row.get(header, "")).ljust(widths[header]) for header in headers)

    separator = "-+-".join("-" * widths[header] for header in headers)
    parts = [format_row({header: header for header in headers}), separator]
    parts.extend(format_row(row) for row in rows)
    return "\n".join(parts)

