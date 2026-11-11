# -*- coding: utf-8 -*-
"""Tiny subset of Go text/template used by the docker --format options.

Supports the placeholders docker users type most often:
  {{.Field}}, {{.Nested.Field}}, {{json .}} and {{json .Field}}
Unknown paths render docker's "<no value>". Tab and newline escapes in the
template text are converted, as docker does for CLI templates.
"""

import json
import re

NO_VALUE = "<no value>"


def _resolve(data, path):
    """Walk a dotted path through nested mappings"""
    current = data
    for key in path.split("."):
        if not key:
            continue
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return NO_VALUE
    return current


def _text(value):
    """Render one resolved value the way docker templates do"""
    if value == NO_VALUE:
        return NO_VALUE
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return NO_VALUE
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    return str(value)


def _expression(expression, data):
    """Render the inside of one {{...}} placeholder"""
    if expression.startswith("json "):
        value = _resolve(data, expression[len("json "):].strip().lstrip("."))
        if value == NO_VALUE:
            return NO_VALUE
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    if expression.startswith("."):
        return _text(_resolve(data, expression[1:]))
    if expression.startswith('"') and expression.endswith('"'):
        return expression[1:-1]
    return NO_VALUE


def render(template, data):
    """Render every placeholder of a template with one data record"""
    if not isinstance(template, str):
        return ""
    text = template.replace("\\t", "\t").replace("\\n", "\n")
    result = []
    index = 0
    while True:
        start = text.find("{{", index)
        if start < 0:
            result.append(text[index:])
            break
        result.append(text[index:start])
        end = text.find("}}", start)
        if end < 0:
            result.append(text[start:])
            break
        expression = text[start + 2:end].strip()
        result.append(_expression(expression, data))
        index = end + 2
    return "".join(result)


def _label(name):
    """Header label for a template field: Names -> NAMES, CreatedAt ->
    CREATED AT"""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(name))
    return spaced.upper()


def render_table(template, records):
    """Render a docker 'table {{.A}}\t{{.B}}' template with a header"""
    text = template
    if text.startswith("table "):
        text = text[len("table "):]
    columns = text.replace("\\t", "\t").split("\t")
    header = []
    for column in columns:
        found = re.findall(r"\{\{\s*\.?([A-Za-z0-9_.]+)\s*\}\}", column)
        header.append(_label(found[-1].split(".")[-1]) if found
                      else column.strip())
    rows = []
    for record in records:
        rendered = render("\t".join(columns), record)
        rows.append(rendered.split("\t"))
    widths = [len(cell) for cell in header]
    for row in rows:
        for (index, cell) in enumerate(row):
            if index < len(widths):
                widths[index] = max(widths[index], len(cell))
    lines = []
    lines.append("   ".join(cell.ljust(widths[index])
                            for (index, cell) in enumerate(header)))
    for row in rows:
        cells = [cell.ljust(widths[index]) for (index, cell) in
                 enumerate(row) if index < len(widths)]
        lines.append("   ".join(cells).rstrip())
    return "\n".join(lines)
