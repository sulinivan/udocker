# -*- coding: utf-8 -*-
"""Tiny subset of Go text/template used by the docker --format options.

Supports the placeholders docker users type most often:
  {{.Field}}, {{.Nested.Field}}, {{json .}} and {{json .Field}}
Unknown paths render docker's "<no value>". Tab and newline escapes in the
template text are converted, as docker does for CLI templates.
"""

import json

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
