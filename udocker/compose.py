# -*- coding: utf-8 -*-
"""Minimal docker compose support for udocker.

Only the subset that rootless udocker can actually serve is implemented:
services are started detached through the supervisor (any execution mode:
P/F/S use the monitor process group, R uses runc), depends_on orders the
startup, containers are named <project>_<service>_1 and ports are published
by the userspace TCP forwarder. There is no container network beyond the
shared host network stack, no health checks, restart policies or scaling.

The command line after the "compose" word is parsed here on purpose:
CmdParser stops looking for options at the first positional argument, so
compose reads the raw sys.argv and marks every parsed option as used.
"""

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from collections import OrderedDict

from udocker.config import Config
from udocker.msg import Msg
from udocker.utils.gotemplate import render as render_template
from udocker.utils.gotemplate import render_table

# udocker specific names come before the docker ones so that a project can
# ship both files: "udocker compose up" then runs the rootless variant
COMPOSE_FILES = ("compose.yaml", "compose.yml",
                 "udocker-compose.yaml", "udocker-compose.yml",
                 "docker-compose.yml", "docker-compose.yaml")

SUPPORTED_KEYS = ("image", "build", "container_name", "command",
                  "entrypoint", "environment", "env_file", "ports",
                  "volumes", "working_dir", "user", "labels", "depends_on",
                  "hostname", "extra_hosts", "ulimits", "networks",
                  "network_mode", "stop_signal", "stop_grace_period",
                  "restart", "healthcheck", "ipc", "pid", "runtime",
                  "cgroup", "deploy", "profiles")

ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}"
                         r"|\$([A-Za-z_][A-Za-z0-9_]*)")

_ACTIVE = []
_ACTIVE_LOCK = threading.Lock()


class ComposeError(Exception):
    """A compose usage or file error"""


class YamlError(ComposeError):
    """A YAML syntax error carrying the file and line number"""


def _warn(text):
    """Report a warning on stderr, so that JSON output stays parseable"""
    Msg().err("Warning: %s" % text, l=Msg.WAR)


def _strip_comment(line):
    """Cut an inline comment respecting single and double quotes"""
    quote = ""
    escaped = False
    previous = " "
    for (index, char) in enumerate(line):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\" and quote == '"':
                escaped = True
            elif char == quote:
                quote = ""
                previous = char
                continue
        elif char in ('"', "'"):
            quote = char
        elif char == "#" and previous in (" ", "\t"):
            return line[:index].rstrip()
        previous = char
    return line.rstrip()


def _unquote_key(text):
    """Remove the quotes of a mapping key"""
    if len(text) > 1 and text[0] == text[-1] and text[0] in ('"', "'"):
        return text[1:-1]
    return text


def _split_pair(text):
    """Split 'key: value' at the first top level colon, None if there is
    no such colon. A colon inside quotes or flow collections and a colon
    not followed by a space (8080:80) do not count."""
    depth = 0
    quote = ""
    escaped = False
    for (index, char) in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\" and quote == '"':
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in ('"', "'"):
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == ":" and depth == 0:
            if index + 1 < len(text) and text[index + 1] not in " \t":
                continue
            key = text[:index].strip()
            if not key:
                return None
            return (_unquote_key(key), text[index + 1:].strip())
    return None


def _split_flow(text):
    """Split the body of a flow collection on top level commas"""
    items = []
    depth = 0
    quote = ""
    escaped = False
    start = 0
    for (index, char) in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\" and quote == '"':
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in ('"', "'"):
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == "," and depth == 0:
            items.append(text[start:index])
            start = index + 1
    items.append(text[start:])
    return items


class YamlParser(object):
    """Parse the YAML subset used by compose files.

    Supported: block mappings and sequences nested by indentation, plain
    and quoted scalars, comments, empty values, flow sequences [a, b] and
    flow mappings {a: b}, block scalars | and >. Anchors, aliases, tags
    and multi document streams are not supported. Blank lines and comment
    lines inside block scalars are dropped.
    """

    def __init__(self):
        self.filename = "yaml"

    def parse(self, text, filename="yaml"):
        """Parse text and return an OrderedDict"""
        self.filename = filename or "yaml"
        lines = self._lines(text)
        if not lines:
            return OrderedDict()
        (value, pos) = self._block(lines, 0, lines[0][0])
        if pos < len(lines):
            raise self._error(lines[pos][2], "unexpected content")
        return value

    def _error(self, lineno, message):
        """Build a YamlError with file and line information"""
        return YamlError("%s:%d: %s" % (self.filename, lineno, message))

    def _lines(self, text):
        """Return (indent, content, lineno) of the lines carrying data"""
        lines = []
        for (index, line) in enumerate(str(text).splitlines()):
            lineno = index + 1
            if line.lstrip(" ").startswith("\t"):
                raise self._error(lineno, "tabs cannot be used for indent")
            content = _strip_comment(line)
            if not content.strip() or content.strip() in ("---", "..."):
                continue
            indent = len(content) - len(content.lstrip(" "))
            lines.append((indent, content.strip(), lineno))
        return lines

    def _block(self, lines, pos, indent):
        """Parse a mapping or a sequence starting at pos"""
        content = lines[pos][1]
        if content == "-" or content.startswith("- "):
            return self._sequence(lines, pos, indent)
        return self._mapping(lines, pos, indent)

    def _mapping(self, lines, pos, indent, first=None):
        """Parse a block mapping; first is an already split leading pair"""
        result = OrderedDict()
        if first is not None:
            pos = self._add_pair(lines, pos, indent, first[0], first[1],
                                 first[2], result)
        while pos < len(lines):
            (current, content, lineno) = lines[pos]
            if current < indent:
                break
            if current > indent:
                raise self._error(lineno, "unexpected indentation")
            if content == "-" or content.startswith("- "):
                break
            pair = _split_pair(content)
            if pair is None:
                raise self._error(lineno, "expected 'key: value'")
            pos = self._add_pair(lines, pos + 1, indent, pair[0], pair[1],
                                 lineno, result)
        return (result, pos)

    def _sequence(self, lines, pos, indent):
        """Parse a block sequence starting at pos"""
        result = []
        while pos < len(lines):
            (current, content, lineno) = lines[pos]
            if current < indent:
                break
            if current > indent:
                raise self._error(lineno, "unexpected indentation")
            if not (content == "-" or content.startswith("- ")):
                break
            item = content[1:].strip()
            if not item:
                pos += 1
                if pos < len(lines) and lines[pos][0] > indent:
                    (value, pos) = self._block(lines, pos, lines[pos][0])
                else:
                    value = None
                result.append(value)
                continue
            pair = _split_pair(item)
            if pair is None:
                result.append(self._scalar(item, lineno))
                pos += 1
                continue
            (mapping, pos) = self._mapping(
                lines, pos + 1, indent + 2, (pair[0], pair[1], lineno))
            result.append(mapping)
        return (result, pos)

    def _add_pair(self, lines, pos, indent, key, rest, lineno, result):
        """Parse the value of one mapping pair, pos is the next line"""
        if rest in ("|", "|-", "|+", ">", ">-", ">+"):
            (result[key], pos) = self._block_scalar(lines, pos, indent, rest)
            return pos
        if rest:
            result[key] = self._scalar(rest, lineno)
            return pos
        if pos < len(lines) and lines[pos][0] > indent:
            (result[key], pos) = self._block(lines, pos, lines[pos][0])
        elif (pos < len(lines) and lines[pos][0] == indent and
              (lines[pos][1] == "-" or lines[pos][1].startswith("- "))):
            (result[key], pos) = self._sequence(lines, pos, indent)
        else:
            result[key] = None
        return pos

    def _block_scalar(self, lines, pos, indent, style):
        """Parse a | or > block scalar below the parent indent"""
        content = []
        while pos < len(lines) and lines[pos][0] > indent:
            content.append(lines[pos][1])
            pos += 1
        if style.startswith("|"):
            value = "\n".join(content)
        else:
            value = " ".join(content)
        if style[-1] not in "-+":
            value += "\n"
        return (value, pos)

    def _scalar(self, text, lineno):
        """Parse a scalar or a flow collection"""
        text = text.strip()
        if not text:
            return None
        if text[0] in ('"', "'"):
            return self._unquote(text, lineno)
        if text[0] == "[":
            return self._flow_sequence(text, lineno)
        if text[0] == "{":
            return self._flow_mapping(text, lineno)
        if text.lower() in ("null", "~"):
            return None
        if re.match(r"^[+-]?[0-9]+$", text):
            return int(text)
        if re.match(r"^[+-]?[0-9]+\.[0-9]+$", text):
            return float(text)
        return text

    def _unquote(self, text, lineno):
        """Remove the quotes of a quoted scalar"""
        quote = text[0]
        if len(text) < 2 or text[-1] != quote:
            raise self._error(lineno, "unterminated quoted string")
        if quote == "'":
            return text[1:-1].replace("''", "'")
        try:
            return json.loads(text)
        except ValueError:
            raise self._error(lineno, "invalid quoted string")

    def _flow_sequence(self, text, lineno):
        """Parse a [a, b] flow sequence"""
        if not text.endswith("]"):
            raise self._error(lineno, "unterminated flow sequence")
        result = []
        for item in _split_flow(text[1:-1]):
            if item.strip():
                result.append(self._scalar(item, lineno))
        return result

    def _flow_mapping(self, text, lineno):
        """Parse a {a: b} flow mapping"""
        if not text.endswith("}"):
            raise self._error(lineno, "unterminated flow mapping")
        result = OrderedDict()
        for item in _split_flow(text[1:-1]):
            item = item.strip()
            if not item:
                continue
            pair = _split_pair(item)
            if pair is None:
                raise self._error(lineno, "expected 'key: value'")
            if pair[1]:
                result[pair[0]] = self._scalar(pair[1], lineno)
            else:
                result[pair[0]] = None
        return result


def expand_env(text):
    """Substitute ${VAR} and $VAR from the environment like compose does.

    A missing variable expands to an empty string and is reported as a
    warning; $$ is the escape for a literal $.
    """
    def replace(match):
        """Replace one variable reference"""
        name = match.group(1) or match.group(2)
        if name in os.environ:
            return os.environ[name]
        _warn("environment variable not set: %s" % name)
        return ""

    marker = "\0"
    protected = str(text).replace("$$", marker)
    return ENV_PATTERN.sub(replace, protected).replace(marker, "$")


def _substitute(value):
    """Recursively expand environment variables in parsed values"""
    if isinstance(value, dict):
        return OrderedDict((key, _substitute(item))
                           for (key, item) in value.items())
    if isinstance(value, list):
        return [_substitute(item) for item in value]
    if isinstance(value, str):
        return expand_env(value)
    return value


def _validate_model(raw, filename):
    """Check the top level of a parsed compose model"""
    services = raw.get("services")
    if not isinstance(services, dict) or not services:
        raise ComposeError("%s: no services defined" % filename)
    volumes = raw.get("volumes")
    if volumes is not None and not isinstance(volumes, dict):
        raise ComposeError("%s: volumes must be a mapping" % filename)
    return raw


APPEND_KEYS = ("ports", "expose", "volumes", "environment", "labels",
               "extra_hosts", "dns", "dns_search", "tmpfs", "cap_add",
               "cap_drop", "devices", "security_opt", "sysctls", "links",
               "ulimits")


def _merge_environment(base, override):
    """Merge environment lists by variable name, the override winning"""
    merged = OrderedDict()
    for item in list(base) + list(override):
        text = str(item)
        (key, separator, dummy) = text.partition("=")
        merged[key if separator else text] = text
    return list(merged.values())


def merge_models(base, override, key=""):
    """Merge two compose models, the override file winning.

    Mappings are merged key by key, scalars are replaced, and the
    sequences that docker appends (ports, volumes, environment, ...) are
    appended with duplicates removed; command and entrypoint keep the
    value of the last file.
    """
    if isinstance(base, dict) and isinstance(override, dict):
        result = OrderedDict(base)
        for (name, value) in override.items():
            if name in result:
                result[name] = merge_models(result[name], value, name)
            else:
                result[name] = value
        return result
    if isinstance(base, list) and isinstance(override, list) and \
            key in APPEND_KEYS:
        if key == "environment":
            return _merge_environment(base, override)
        result = list(base)
        for item in override:
            if item not in result:
                result.append(item)
        return result
    return override


def read_model(path, interpolate=True):
    """Read one compose file into a raw model mapping"""
    try:
        with open(path, "r") as filep:
            text = filep.read()
    except (IOError, OSError) as error:
        raise ComposeError("cannot read %s: %s" % (path, error))
    raw = YamlParser().parse(text, path)
    return _substitute(raw) if interpolate else raw


class ComposeFile(object):
    """A parsed compose file with a validated services section"""

    def __init__(self):
        self.path = ""
        self.raw = OrderedDict()

    def parse(self, text, filename="compose"):
        """Parse compose text and return the raw mapping"""
        raw = _substitute(YamlParser().parse(text, filename))
        _validate_model(raw, filename)
        self.path = filename
        self.raw = raw
        return raw

    def load(self, path):
        """Read and parse a compose file"""
        raw = read_model(path)
        _validate_model(raw, path)
        self.path = path
        self.raw = raw
        return raw

    def services(self):
        """Return the services mapping"""
        return self.raw.get("services") or OrderedDict()

    def volume_defs(self):
        """Top-level named volume declarations"""
        volumes = self.raw.get("volumes")
        if isinstance(volumes, dict):
            return volumes
        return OrderedDict()


def normalize_name(value):
    """Lowercase a name and replace the characters that container and
    image names do not accept with an underscore"""
    return re.sub(r"[^a-z0-9_-]", "_", str(value).lower())


def container_name(project, service):
    """Default container name of a service, as docker compose names it"""
    return "%s_%s_1" % (normalize_name(project), normalize_name(service))


def default_image(project, service):
    """Image tag given to a service that only has a build section"""
    return "%s_%s:latest" % (normalize_name(project), normalize_name(service))


def parse_command(value):
    """Normalize a command or entrypoint to a list of arguments"""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        return shlex.split(str(value))
    except ValueError as error:
        raise ComposeError("cannot parse command %s: %s" % (value, error))


def _dotenv_lines(lines, values):
    """Add the KEY=VALUE lines of one dotenv file to a mapping"""
    for line in lines:
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if text.startswith("export "):
            text = text[len("export "):]
        (key, separator, value) = text.partition("=")
        if not separator:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key.strip():
            values[key.strip()] = value


def load_dotenv(directory):
    """Read the compose .env file of a directory, empty when missing"""
    values = OrderedDict()
    path = os.path.join(directory, ".env")
    try:
        with open(path, "r") as filep:
            lines = filep.read().splitlines()
    except (IOError, OSError):
        return values
    _dotenv_lines(lines, values)
    return values


def read_env_file(path):
    """Read an --env-file given on the command line"""
    try:
        with open(path, "r") as filep:
            lines = filep.read().splitlines()
    except (IOError, OSError) as error:
        raise ComposeError("cannot read env file %s: %s" % (path, error))
    values = OrderedDict()
    _dotenv_lines(lines, values)
    return values


def parse_env_files(value, compose_dir):
    """Read compose env_file entries into VAR=VALUE items"""
    result = []
    if value is None:
        return result
    files = value if isinstance(value, list) else [value]
    for item in files:
        path = str(item)
        if not os.path.isabs(path):
            path = os.path.normpath(os.path.join(compose_dir, path))
        try:
            with open(path, "r") as filep:
                lines = filep.read().splitlines()
        except (IOError, OSError) as error:
            raise ComposeError("cannot read env_file %s: %s" % (path, error))
        for line in lines:
            entry = line.strip()
            if not entry or entry.startswith("#"):
                continue
            if entry.startswith("export "):
                entry = entry[len("export "):]
            if "=" not in entry:
                _warn("env_file line without value ignored: %s" % entry)
                continue
            (key, dummy, val) = entry.partition("=")
            val = val.strip()
            if (len(val) >= 2 and val[0] == val[-1] and
                    val[0] in ('"', "'")):
                val = val[1:-1]
            result.append("%s=%s" % (key.strip(), val))
    return result


def parse_ulimits(value):
    """Normalize compose ulimits to docker --ulimit statements"""
    result = []
    if value is None:
        return result
    if not isinstance(value, dict):
        raise ComposeError("ulimits must be a mapping")
    for (name, spec) in value.items():
        if isinstance(spec, dict):
            soft = spec.get("soft")
            hard = spec.get("hard", soft)
            if soft is None:
                raise ComposeError("ulimits %s: soft required" % name)
            result.append("%s=%s:%s" % (name, soft, hard))
        else:
            result.append("%s=%s" % (name, spec))
    return result


def parse_environment(value):
    """Normalize environment to a list of VAR=VALUE items"""
    result = []
    if value is None:
        return result
    if isinstance(value, dict):
        for (key, item) in value.items():
            if item is None:
                item = ""
            result.append("%s=%s" % (key, item))
        return result
    if isinstance(value, list):
        for item in value:
            item = str(item)
            if "=" in item:
                result.append(item)
            else:
                _warn("environment without value ignored: %s" % item)
        return result
    raise ComposeError("environment must be a mapping or a list")


def parse_ports(value):
    """Normalize ports to a list of host:container tcp pairs.

    udocker publishes ports with a userspace TCP forwarder, therefore a
    container only port, udp, port ranges and a bind address do not fit
    and are reported and skipped.
    """
    result = []
    if value is None:
        return result
    if not isinstance(value, list):
        raise ComposeError("ports must be a list")
    for item in value:
        spec = str(item)
        protocol = "tcp"
        if "/" in spec:
            (spec, protocol) = spec.split("/", 1)
        if protocol.lower() != "tcp":
            _warn("only tcp ports are supported, ignored: %s" % str(item))
            continue
        fields = spec.split(":")
        if len(fields) == 1:
            _warn("container port without host port ignored: %s" % str(item))
            continue
        if len(fields) > 2:
            _warn("bind address ignored in port: %s" % str(item))
        (host, container) = (fields[-2], fields[-1])
        if not (host.isdigit() and container.isdigit()):
            _warn("port ranges are not supported, ignored: %s" % str(item))
            continue
        result.append("%s:%s" % (host, container))
    return result


def parse_volumes(value, compose_dir, project="", volume_defs=None,
                  resolve_paths=True):
    """Normalize volumes to a list of host:container bind mounts.

    Relative bind paths are resolved against the compose file directory
    unless --no-path-resolution asks for the raw values. A source without a
    path separator is a named volume: it is mapped to an udocker named
    volume, prefixed with the project name like docker compose does, unless
    the top-level declaration sets name: or external: true. The volume
    itself is created by the udocker run child.
    """
    result = []
    if value is None:
        return result
    if not isinstance(value, list):
        raise ComposeError("volumes must be a list")
    for item in value:
        spec = os.path.expanduser(str(item))
        if ":" not in spec:
            _warn("anonymous volume ignored: %s" % spec)
            continue
        (host, container) = spec.split(":", 1)
        if not host or not container:
            raise ComposeError("invalid volume: %s" % spec)
        if not os.path.isabs(host):
            if host.startswith("."):
                if resolve_paths:
                    host = os.path.normpath(os.path.join(compose_dir, host))
            else:
                host = volume_name(project, host, volume_defs)
        result.append("%s:%s" % (host, container))
    return result


def volume_name(project, source, volume_defs=None):
    """Name of the udocker volume serving a compose named volume"""
    if not isinstance(volume_defs, dict):
        volume_defs = {}
    if source not in volume_defs:
        _warn("volume %s is not declared in the top-level volumes,"
              " using %s_%s" % (source, project, source))
    declared = volume_defs.get(source)
    definition = declared if isinstance(declared, dict) else {}
    explicit = definition.get("name")
    if definition.get("external"):
        return str(explicit or source)
    if explicit:
        return str(explicit)
    return "%s_%s" % (project, source)


def parse_duration(value):
    """Compose duration ('10s', '1m30s', bare number) to seconds"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().lower()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    units = {"h": 3600, "m": 60, "s": 1}
    total = 0
    index = 0
    while index < len(text):
        start = index
        while index < len(text) and text[index].isdigit():
            index += 1
        if start == index or index >= len(text) or text[index] not in units:
            return None
        total += int(text[start:index]) * units[text[index]]
        index += 1
    return total


def parse_healthcheck(value):
    """Normalize a compose healthcheck mapping to docker-ish fields"""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ComposeError("healthcheck must be a mapping")
    if value.get("disable"):
        return {"test": ["NONE"]}
    test = value.get("test")
    if isinstance(test, list):
        test = [str(item) for item in test]
    elif test is not None:
        test = ["CMD-SHELL", str(test)]
    result = {"test": test}
    for key in ("interval", "timeout", "start_period"):
        result[key] = parse_duration(value.get(key))
    retries = value.get("retries")
    try:
        result["retries"] = int(retries) if retries is not None else None
    except (TypeError, ValueError):
        raise ComposeError("healthcheck retries must be a number")
    return result


def parse_extra_hosts(value):
    """Normalize extra_hosts to a list of host:ip entries"""
    result = []
    if value is None:
        return result
    if isinstance(value, dict):
        return ["%s:%s" % (host, address) for (host, address) in value.items()]
    if isinstance(value, list):
        for item in value:
            text = str(item)
            if "=" in text:
                (host, address) = text.split("=", 1)
                result.append("%s:%s" % (host, address))
            else:
                result.append(text)
        return result
    return [str(value)]


def parse_labels(value):
    """Normalize labels to a list of key=value items"""
    result = []
    if value is None:
        return result
    if isinstance(value, dict):
        for (key, item) in value.items():
            if item is None:
                item = ""
            result.append("%s=%s" % (key, item))
        return result
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def parse_depends_conditions(value):
    """Conditions of a long-syntax depends_on mapping, empty for the list"""
    result = {}
    if isinstance(value, dict):
        for (name, spec) in value.items():
            condition = "service_started"
            if isinstance(spec, dict) and spec.get("condition"):
                condition = str(spec["condition"])
            result[str(name)] = condition
    return result


def parse_depends_on(value):
    """Normalize depends_on, short or long syntax, to service names"""
    if value is None:
        return []
    if isinstance(value, dict):
        return [str(name) for name in value]
    if isinstance(value, list):
        return [str(name) for name in value]
    return [str(value)]


def _build_config(value, service):
    """Return the raw build context of a service, or None"""
    if isinstance(value, dict):
        for key in value:
            if key != "context":
                _warn("service %s: unsupported build key ignored: %s"
                      % (service, key))
        return value.get("context") or "."
    if isinstance(value, str) and value:
        return value
    return None


def normalize_service(project, service, config, compose_dir,
                      volume_defs=None, resolve_env=True, resolve_paths=True):
    """Return a normalized description of one service.

    Unknown keys are reported and ignored instead of failing the project,
    so a compose file that uses unsupported features still starts the
    parts that udocker can run. resolve_env and resolve_paths implement the
    --no-env-resolution and --no-path-resolution config options.
    """
    if not isinstance(config, dict):
        raise ComposeError("service %s: expected a mapping" % service)
    for key in config:
        if key not in SUPPORTED_KEYS:
            _warn("service %s: unsupported key ignored: %s" % (service, key))
    context = _build_config(config.get("build"), service)
    if context and resolve_paths and not os.path.isabs(context):
        context = os.path.normpath(os.path.join(compose_dir, context))
    image = config.get("image")
    if image is not None:
        image = str(image)
    if not image:
        if not context:
            raise ComposeError("service %s: image or build required"
                               % service)
        image = default_image(project, service)
    name = config.get("container_name")
    if not name:
        name = container_name(project, service)
    environment = parse_environment(config.get("environment"))
    env_file_values = []
    if resolve_env:
        env_file_values = parse_env_files(config.get("env_file"), compose_dir)
    merged = OrderedDict()
    for item in env_file_values + environment:
        (key, separator, value) = item.partition("=")
        if separator:
            merged[key] = value
    environment = ["%s=%s" % (key, value) for (key, value) in merged.items()]
    return {
        "image": image,
        "container_name": str(name),
        "build": context,
        "command": parse_command(config.get("command")),
        "entrypoint": parse_command(config.get("entrypoint")),
        "environment": environment,
        "ports": parse_ports(config.get("ports")),
        "volumes": parse_volumes(config.get("volumes"), compose_dir,
                                 project, volume_defs, resolve_paths),
        "working_dir": str(config.get("working_dir") or ""),
        "user": str(config.get("user") or ""),
        "labels": parse_labels(config.get("labels")),
        "hostname": str(config.get("hostname") or ""),
        "extra_hosts": parse_extra_hosts(config.get("extra_hosts")),
        "ulimits": parse_ulimits(config.get("ulimits")),
        "stop_signal": str(config.get("stop_signal") or ""),
        "stop_timeout": parse_duration(config.get("stop_grace_period")),
        "restart": str(config.get("restart") or ""),
        "healthcheck": parse_healthcheck(config.get("healthcheck")),
        "depends_on": parse_depends_on(config.get("depends_on")),
        "depends_conditions": parse_depends_conditions(
            config.get("depends_on")),
    }


def build_arguments(plan, extra=()):
    """udocker build command line for a service, None if it is not built"""
    if not plan["build"]:
        return None
    return (["build", "-t=" + plan["image"], "--force"] + list(extra) +
            [plan["build"]])


def create_arguments(plan):
    """udocker create command line for a service"""
    return ["create", "--name=" + plan["container_name"], plan["image"]]


def run_arguments(plan):
    """udocker run command line of a service, detached.

    Every option goes before the container name because CmdParser stops
    reading options at the first positional argument.
    """
    args = ["run", "-d"]
    for item in plan["environment"]:
        args.append("--env=" + item)
    for item in plan["volumes"]:
        args.append("--volume=" + item)
    for item in plan["ports"]:
        args.append("--publish=" + item)
    if plan["working_dir"]:
        args.append("--workdir=" + plan["working_dir"])
    if plan["user"]:
        args.append("--user=" + plan["user"])
    if plan["entrypoint"]:
        args.append("--entrypoint=" + " ".join(plan["entrypoint"]))
    if plan.get("hostname"):
        args.append("--hostname=" + plan["hostname"])
    for item in plan.get("extra_hosts") or []:
        args.append("--add-host=" + item)
    for item in plan["labels"]:
        args.append("--label=" + item)
    for item in plan.get("ulimits") or []:
        args.append("--ulimit=" + item)
    if plan.get("stop_signal"):
        args.append("--stop-signal=" + plan["stop_signal"])
    if plan.get("stop_timeout") is not None:
        args.append("--stop-timeout=" + str(plan["stop_timeout"]))
    if plan.get("restart"):
        args.append("--restart=" + plan["restart"])
    health = plan.get("healthcheck") or {}
    test = health.get("test")
    if test:
        if test[0] == "NONE":
            args.append("--health-cmd=NONE")
        else:
            args.append("--health-cmd=" + " ".join(test[1:]))
    for key, flag in (("interval", "--health-interval="),
                      ("timeout", "--health-timeout="),
                      ("start_period", "--health-start-period=")):
        if health.get(key) is not None:
            args.append(flag + "%gs" % health[key])
    if health.get("retries") is not None:
        args.append("--health-retries=%d" % health["retries"])
    args.append(plan["container_name"])
    args.extend(plan["command"])
    return args


def topo_sort(services, selected=None):
    """Order services so that dependencies come before their dependants.

    An unknown service or a dependency cycle raises ComposeError. A
    service named in selected pulls in its dependencies as well.
    """
    order = []
    state = {}

    def visit(name):
        """Depth first visit of one service"""
        if name not in services:
            raise ComposeError("unknown service: %s" % name)
        if not isinstance(services[name], dict):
            raise ComposeError("service %s: expected a mapping" % name)
        if state.get(name) == "done":
            return
        if state.get(name) == "visiting":
            raise ComposeError("dependency cycle at service: %s" % name)
        state[name] = "visiting"
        for dependency in parse_depends_on(services[name].get("depends_on")):
            visit(dependency)
        state[name] = "done"
        order.append(name)

    for name in (selected or list(services)):
        visit(name)
    return order


class ComposeProject(object):
    """A compose file, its project name and the service plans"""

    def __init__(self, path, name=None, directory=None, env_files=(),
                 profiles=(), interpolate=True, resolve_env=True,
                 resolve_paths=True):
        files = list(path) if isinstance(path, (list, tuple)) else [path]
        if not files:
            raise ComposeError("no compose file selected")
        self.path = files[0]
        self.files = files
        self.dir = directory or os.path.dirname(os.path.abspath(files[0]))
        self.resolve_env = resolve_env
        self.resolve_paths = resolve_paths
        self.enabled_profiles = list(profiles)
        dotenv = load_dotenv(self.dir)
        for env_path in env_files:
            dotenv.update(read_env_file(env_path))
        restore = []
        for (key, value) in dotenv.items():
            if key not in os.environ:
                restore.append(key)
                os.environ[key] = value
        try:
            models = [read_model(item, interpolate) for item in files]
        finally:
            for key in restore:
                os.environ.pop(key, None)
        raw = models[0]
        for override in models[1:]:
            raw = merge_models(raw, override)
        _validate_model(raw, files[0])
        self.file = ComposeFile()
        self.file.path = self.path
        self.file.raw = raw
        self.services = self._enabled_services(raw.get("services") or
                                               OrderedDict())
        source = name or raw.get("name") or os.path.basename(self.dir)
        self.name = normalize_name(source) or "app"
        self._plans = {}

    def _enabled_services(self, services):
        """Drop the services whose profiles were not enabled"""
        if not self.enabled_profiles:
            enabled = [service for (service, config) in services.items()
                       if not self._service_profiles(config)]
            return OrderedDict((service, services[service])
                               for service in enabled)
        star = "*" in self.enabled_profiles
        result = OrderedDict()
        for (service, config) in services.items():
            declared = self._service_profiles(config)
            if not declared or star or \
                    any(item in self.enabled_profiles for item in declared):
                result[service] = config
        return result

    @staticmethod
    def _service_profiles(config):
        """The profiles a service declares, empty when always enabled"""
        if not isinstance(config, dict):
            return []
        declared = config.get("profiles")
        if isinstance(declared, (list, tuple)):
            return [str(item) for item in declared]
        if declared:
            return [str(declared)]
        return []

    def all_services(self):
        """Every service of the file, including the disabled profiles"""
        return self.file.services()

    def profiles(self):
        """The profile names declared by the file"""
        result = []
        for config in self.file.services().values():
            for item in self._service_profiles(config):
                if item not in result:
                    result.append(item)
        return result

    def plan(self, service):
        """Normalized plan of a service, computed once"""
        if service not in self._plans:
            if service not in self.services:
                raise ComposeError("no such service: %s" % service)
            self._plans[service] = normalize_service(
                self.name, service, self.services[service], self.dir,
                self.volume_defs(), self.resolve_env, self.resolve_paths)
        return self._plans[service]

    def volume_defs(self):
        """Top-level named volume declarations"""
        return self.file.volume_defs()

    def volume_names(self):
        """Mapping of compose volume keys to udocker volume names"""
        declared = self.volume_defs()
        result = OrderedDict()
        for source in declared:
            result[str(source)] = volume_name(self.name, source, declared)
        return result

    def external_volumes(self):
        """Names of the volumes declared external"""
        declared = self.volume_defs()
        result = []
        for source in declared:
            definition = declared.get(source)
            if isinstance(definition, dict) and definition.get("external"):
                result.append(volume_name(self.name, source, declared))
        return result

    def container_name(self, service):
        """Container name of a service"""
        return self.plan(service)["container_name"]

    def select(self, selected=None):
        """Validate and return the requested services, or all of them"""
        if not selected:
            return list(self.services)
        for name in selected:
            if name not in self.services:
                raise ComposeError("no such service: %s" % name)
        return list(selected)

    def names(self, selected=None):
        """Ordered mapping of service name to container name"""
        result = OrderedDict()
        for service in self.select(selected):
            result[service] = self.container_name(service)
        return result

    def order(self, selected=None):
        """Services in depends_on order, dependencies first"""
        self.select(selected)
        return topo_sort(self.services, selected)


def find_compose_file(directory="."):
    """Return the first compose file found in a directory, or an empty str"""
    for name in COMPOSE_FILES:
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            return path
    return ""


def child_arguments(args):
    """The udocker command line used for every child process"""
    return [sys.executable, "-m", "udocker.maincmd",
            "--repo=" + str(Config.conf["topdir"])] + list(args)


def _terminate(proc):
    """Terminate a child process and close its output pipe"""
    try:
        proc.terminate()
    except OSError:
        pass
    deadline = time.time() + 1.0
    while proc.poll() is None and time.time() < deadline:
        time.sleep(0.05)
    if proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.stdout.close()
    except (IOError, OSError, AttributeError):
        pass


def kill_active():
    """Terminate the child processes left running, used on Ctrl-C"""
    with _ACTIVE_LOCK:
        procs = list(_ACTIVE)
        del _ACTIVE[:]
    for proc in procs:
        _terminate(proc)


def _udocker(args, stream=False):
    """Run a udocker child command and capture its output.

    This is the only place where subprocesses are started: the environment
    is inherited, no shell is involved and stdout and stderr are merged.
    With stream=True the output lines are printed as they arrive and the
    call blocks until the child exits.
    """
    argv = child_arguments(args)
    Msg().out("Debug: exec: %s" % " ".join(argv), l=Msg.DBG)
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            universal_newlines=True)
    with _ACTIVE_LOCK:
        _ACTIVE.append(proc)
    output = []
    try:
        if stream:
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                output.append(line)
                Msg().out(line.rstrip("\n"))
            proc.wait()
        else:
            (text, dummy) = proc.communicate()
            output.append(text or "")
        return (proc.returncode, "".join(output))
    finally:
        with _ACTIVE_LOCK:
            if proc in _ACTIVE:
                _ACTIVE.remove(proc)
        if proc.poll() is None:
            _terminate(proc)


def _parse_json_records(text):
    """Parse a JSON array or docker-style newline delimited JSON records"""
    text = text.strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    records = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            raise ComposeError("cannot parse the container list")
        if isinstance(record, dict):
            records.append(record)
    return records


def list_containers():
    """Return the containers of the repository as parsed JSON records"""
    (status, output) = _udocker(["ps", "-a", "--format=json"])
    if status != 0:
        raise ComposeError("cannot list containers: %s" % output.strip())
    return _parse_json_records(output)


def record_field(record, name, default=""):
    """Read a field from an udocker or a docker ps record"""
    if name in record:
        return record[name]
    aliases = {"name": "Names", "status": "State", "container_id": "ID",
               "image": "Image"}
    alias = aliases.get(name)
    if alias and alias in record:
        return record[alias]
    return default


def container_index(containers):
    """Map every container name to its ps record"""
    index = {}
    for container in containers:
        for name in str(record_field(container, "name")).split(","):
            if name:
                index[name] = container
    return index


def orphan_names(project, index):
    """Names of project containers that the compose file does not describe"""
    known = set(project.names().values())
    prefix = project.name + "_"
    return sorted(name for name in index
                  if name.startswith(prefix) and name not in known)


def _tail_options(tail):
    """The --tail options for the udocker logs command"""
    if tail is None:
        return []
    return ["--tail=" + str(tail)]


def stream_logs(names, tail=None, extra=()):
    """Follow the logs of one or several containers concurrently.

    Multiple services are followed in threads and their lines are printed
    without a service prefix, so the output stays byte exact but lines of
    different services may interleave. extra holds the time filtering
    options (--since/--until/--timestamps) passed to udocker logs.
    """
    base = ["logs"] + _tail_options(tail) + list(extra)
    if len(names) == 1:
        _udocker(base + ["-f", names[0]], stream=True)
        return
    threads = []
    try:
        for name in names:
            thread = threading.Thread(target=_follow_one,
                                      args=(base + ["-f", name],))
            thread.daemon = True
            thread.start()
            threads.append(thread)
        while True:
            running = [thread for thread in threads if thread.is_alive()]
            if not running:
                break
            running[0].join(0.2)
    finally:
        kill_active()


def _follow_one(args):
    """Follow one container log; errors of one thread do not stop others"""
    try:
        _udocker(args, stream=True)
    except (OSError, ValueError) as error:
        Msg().err("Error: cannot follow logs:", str(error))


DOCKER_OPTIONS = {
    "": {
        "--all-resources": "flag", "--ansi": "value",
        "--compatibility": "flag", "--dry-run": "flag", "--env-file": "list",
        "--file": "list", "--parallel": "value", "--profile": "list",
        "--progress": "value", "--project-directory": "value",
        "--project-name": "value"
    },
    "attach": {
        "--detach-keys": "value", "--dry-run": "flag", "--index": "value",
        "--no-stdin": "flag", "--sig-proxy": "flag"
    },
    "bridge": {
        "--dry-run": "flag"
    },
    "build": {
        "--build-arg": "list", "--builder": "value", "--check": "flag",
        "--dry-run": "flag", "--memory": "value", "--no-cache": "flag",
        "--print": "flag", "--provenance": "value", "--pull": "flag",
        "--push": "flag", "--quiet": "flag", "--sbom": "value",
        "--ssh": "value", "--with-dependencies": "flag"
    },
    "commit": {
        "--author": "value", "--change": "list", "--dry-run": "flag",
        "--index": "value", "--message": "value", "--pause": "flag"
    },
    "config": {
        "--dry-run": "flag", "--environment": "flag", "--format": "value",
        "--hash": "value", "--images": "flag",
        "--lock-image-digests": "flag", "--models": "flag",
        "--networks": "flag", "--no-consistency": "flag",
        "--no-env-resolution": "flag", "--no-interpolate": "flag",
        "--no-normalize": "flag", "--no-path-resolution": "flag",
        "--output": "value", "--profiles": "flag", "--quiet": "flag",
        "--resolve-image-digests": "flag", "--services": "flag",
        "--variables": "flag", "--volumes": "flag"
    },
    "cp": {
        "--all": "flag", "--archive": "flag", "--dry-run": "flag",
        "--follow-link": "flag", "--index": "value"
    },
    "create": {
        "--build": "flag", "--dry-run": "flag", "--force-recreate": "flag",
        "--no-build": "flag", "--no-recreate": "flag", "--pull": "value",
        "--quiet-pull": "flag", "--remove-orphans": "flag",
        "--scale": "list", "--yes": "flag"
    },
    "down": {
        "--dry-run": "flag", "--remove-orphans": "flag", "--rmi": "value",
        "--timeout": "value", "--volumes": "flag"
    },
    "events": {
        "--dry-run": "flag", "--json": "flag", "--since": "value",
        "--until": "value"
    },
    "exec": {
        "--detach": "flag", "--dry-run": "flag", "--env": "list",
        "--index": "value", "--no-tty": "flag", "--privileged": "flag",
        "--user": "value", "--workdir": "value"
    },
    "export": {
        "--dry-run": "flag", "--index": "value", "--output": "value"
    },
    "images": {
        "--dry-run": "flag", "--format": "value", "--quiet": "flag"
    },
    "kill": {
        "--dry-run": "flag", "--remove-orphans": "flag", "--signal": "value"
    },
    "logs": {
        "--dry-run": "flag", "--follow": "flag", "--index": "value",
        "--no-color": "flag", "--no-log-prefix": "flag", "--since": "value",
        "--tail": "value", "--timestamps": "flag", "--until": "value"
    },
    "ls": {
        "--all": "flag", "--dry-run": "flag", "--filter": "list",
        "--format": "value", "--quiet": "flag"
    },
    "pause": {
        "--dry-run": "flag"
    },
    "port": {
        "--dry-run": "flag", "--index": "value", "--protocol": "value"
    },
    "ps": {
        "--all": "flag", "--dry-run": "flag", "--filter": "value",
        "--format": "value", "--no-trunc": "flag", "--orphans": "flag",
        "--quiet": "flag", "--services": "flag", "--status": "list"
    },
    "publish": {
        "--app": "flag", "--dry-run": "flag", "--oci-version": "value",
        "--resolve-image-digests": "flag", "--with-env": "flag",
        "--yes": "flag"
    },
    "pull": {
        "--dry-run": "flag", "--ignore-buildable": "flag",
        "--ignore-pull-failures": "flag", "--include-deps": "flag",
        "--policy": "value", "--quiet": "flag"
    },
    "push": {
        "--dry-run": "flag", "--ignore-missing": "flag",
        "--include-deps": "flag", "--quiet": "flag"
    },
    "restart": {
        "--dry-run": "flag", "--no-deps": "flag", "--timeout": "value"
    },
    "rm": {
        "--dry-run": "flag", "--force": "flag", "--stop": "flag",
        "--volumes": "flag"
    },
    "run": {
        "--build": "flag", "--cap-add": "list", "--cap-drop": "list",
        "--detach": "flag", "--dry-run": "flag", "--entrypoint": "value",
        "--env": "list", "--env-from-file": "list", "--interactive": "flag",
        "--label": "list", "--name": "value", "--no-deps": "flag",
        "--no-recreate": "flag", "--no-tty": "flag", "--publish": "list",
        "--pull": "value", "--quiet": "flag", "--quiet-build": "flag",
        "--quiet-pull": "flag", "--remove-orphans": "flag", "--rm": "flag",
        "--service-ports": "flag", "--use-aliases": "flag",
        "--user": "value", "--volume": "list", "--workdir": "value"
    },
    "scale": {
        "--dry-run": "flag", "--no-deps": "flag"
    },
    "start": {
        "--dry-run": "flag", "--wait": "flag", "--wait-timeout": "value"
    },
    "stats": {
        "--aggregate": "flag", "--all": "flag", "--all-projects": "flag",
        "--dry-run": "flag", "--format": "value", "--no-stream": "flag",
        "--no-trunc": "flag"
    },
    "stop": {
        "--dry-run": "flag", "--timeout": "value"
    },
    "top": {
        "--dry-run": "flag"
    },
    "unpause": {
        "--dry-run": "flag"
    },
    "up": {
        "--abort-on-container-exit": "flag",
        "--abort-on-container-failure": "flag",
        "--always-recreate-deps": "flag", "--attach": "list",
        "--attach-dependencies": "flag", "--build": "flag",
        "--detach": "flag", "--dry-run": "flag", "--exit-code-from": "value",
        "--force-recreate": "flag", "--menu": "flag", "--no-attach": "list",
        "--no-build": "flag", "--no-color": "flag", "--no-deps": "flag",
        "--no-log-prefix": "flag", "--no-recreate": "flag",
        "--no-start": "flag", "--pull": "value", "--quiet-build": "flag",
        "--quiet-pull": "flag", "--remove-orphans": "flag",
        "--renew-anon-volumes": "flag", "--scale": "list",
        "--timeout": "value", "--timestamps": "flag", "--wait": "flag",
        "--wait-timeout": "value", "--watch": "flag", "--yes": "flag"
    },
    "version": {
        "--dry-run": "flag", "--format": "value", "--short": "flag"
    },
    "volumes": {
        "--dry-run": "flag", "--format": "value", "--quiet": "flag"
    },
    "wait": {
        "--down-project": "flag", "--dry-run": "flag"
    },
    "watch": {
        "--dry-run": "flag", "--no-up": "flag", "--prune": "flag",
        "--quiet": "flag"
    },
}

SHORT_ALIASES = {
    "": {
        "-f": "--file", "-p": "--project-name"
    },
    "build": {
        "-m": "--memory", "-q": "--quiet"
    },
    "commit": {
        "-a": "--author", "-c": "--change", "-m": "--message",
        "-p": "--pause"
    },
    "config": {
        "-o": "--output", "-q": "--quiet"
    },
    "cp": {
        "-a": "--archive", "-L": "--follow-link"
    },
    "create": {
        "-y": "--yes"
    },
    "down": {
        "-t": "--timeout", "-v": "--volumes"
    },
    "exec": {
        "-d": "--detach", "-e": "--env", "-T": "--no-tty",
        "-u": "--user", "-w": "--workdir"
    },
    "export": {
        "-o": "--output"
    },
    "images": {
        "-q": "--quiet"
    },
    "kill": {
        "-s": "--signal"
    },
    "logs": {
        "-f": "--follow", "-n": "--tail", "-t": "--timestamps"
    },
    "ls": {
        "-a": "--all", "-q": "--quiet"
    },
    "ps": {
        "-a": "--all", "-q": "--quiet"
    },
    "publish": {
        "-y": "--yes"
    },
    "pull": {
        "-q": "--quiet"
    },
    "push": {
        "-q": "--quiet"
    },
    "restart": {
        "-t": "--timeout"
    },
    "rm": {
        "-f": "--force", "-s": "--stop", "-v": "--volumes"
    },
    "run": {
        "-d": "--detach", "-e": "--env", "-i": "--interactive",
        "-l": "--label", "-T": "--no-tty", "-p": "--publish",
        "-q": "--quiet", "-P": "--service-ports", "-u": "--user",
        "-v": "--volume", "-w": "--workdir"
    },
    "stats": {
        "-a": "--all"
    },
    "stop": {
        "-t": "--timeout"
    },
    "up": {
        "-d": "--detach", "-V": "--renew-anon-volumes",
        "-t": "--timeout", "-w": "--watch", "-y": "--yes"
    },
    "version": {
        "-f": "--format"
    },
    "volumes": {
        "-q": "--quiet"
    },
}

COMPOSE_VERSION = "v5.7.0"
OPTIONAL_VALUE_OPTIONS = {"--rmi": "all"}

ROOT_ONLY_OPTIONS = {
    ("build", "--memory"): "cgroup memory limits for the build container",
    ("exec", "--privileged"): "extended privileges",
    ("run", "--cap-add"): "Linux capabilities",
    ("run", "--cap-drop"): "Linux capabilities",
}

NOT_APPLICABLE_OPTIONS = {
    ("build", "--check"): "checking the build configuration",
    ("build", "--builder"): "BuildKit builders",
    ("build", "--print"): "printing an equivalent bake file",
    ("build", "--provenance"): "build provenance attestations",
    ("build", "--sbom"): "SBOM attestations",
    ("build", "--ssh"): "forwarding SSH agents into builds",
    ("commit", "--change"): "applying Dockerfile instructions",
    ("config", "--lock-image-digests"): "pinning image digests",
    ("config", "--models"): "compose models",
    ("config", "--resolve-image-digests"): "resolving image digests",
    ("config", "--variables"): "compose model variables",
    ("create", "--scale"): "multi-replica services",
    ("stats", "--aggregate"): "aggregating resource usage per project",
    ("stats", "--all-projects"): "showing other projects",
    ("up", "--abort-on-container-exit"): "aborting on container exit",
    ("up", "--abort-on-container-failure"): "aborting on container failure",
    ("up", "--exit-code-from"): "returning one service exit code",
    ("up", "--renew-anon-volumes"): "anonymous volumes",
    ("up", "--scale"): "multi-replica services",
    ("up", "--watch"): "watching the source tree",
}

NOT_APPLICABLE_COMMANDS = {
    "attach": "udocker has no attach support, use: udocker exec",
    "bridge": "converting compose files to Kubernetes manifests is not"
              " part of a rootless container runtime",
    "publish": "publishing a compose application as an OCI artifact is not"
               " supported",
    "scale": "udocker runs one container per service; multi-replica scaling"
             " is not supported",
    "watch": "watching the source tree and rebuilding containers is not"
             " supported",
}


HEALTH_WAIT_TIMEOUT = 60


def _remove_orphans(project, index):
    """Remove the project containers that are not in the compose file"""
    for name in orphan_names(project, index):
        Msg().out("Info: removing orphan container: %s" % name, l=Msg.INF)
        _udocker(["rm", "-f", name])


def _inspect_field(name, template):
    """Run udocker inspect -f and return the stripped output"""
    (status, output) = _udocker(["inspect", "-f", template, name])
    if status != 0:
        return ""
    return output.strip()


def _wait_healthy(name, timeout=HEALTH_WAIT_TIMEOUT):
    """Wait until a container reports healthy, False on unhealthy/timeout"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = _inspect_field(name, "{{.State.Health.Status}}")
        if status == "healthy":
            return True
        if status == "unhealthy":
            return False
        time.sleep(0.5)
    return False


def _wait_running(name, timeout=HEALTH_WAIT_TIMEOUT):
    """Wait until a container is running (used by compose up --wait)"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _inspect_field(name, "{{.State.Status}}") == "running":
            return True
        time.sleep(0.5)
    return False


def option_kind(page, name):
    """The kind of an option for one compose command page or None"""
    table = DOCKER_OPTIONS.get(page) or {}
    if name in table:
        return table[name]
    return DOCKER_OPTIONS[""].get(name)


def canonical_option(page, flag):
    """Resolve a short option to its long name for a page, None if unknown"""
    name = flag
    if not name.startswith("--"):
        aliases = SHORT_ALIASES.get(page) or {}
        name = aliases.get(flag) or SHORT_ALIASES[""].get(flag)
        if name is None:
            return None
    if option_kind(page, name) is None:
        return None
    return name


def unsupported_state(page, name):
    """root-only / n-a state of an option, empty when it is supported"""
    if (page, name) in ROOT_ONLY_OPTIONS:
        return "root-only"
    if (page, name) in NOT_APPLICABLE_OPTIONS:
        return "n-a"
    return ""


def unsupported_error(page, name):
    """The explicit error message of a root-only or not applicable option"""
    where = "compose %s" % page if page else "compose"
    state = unsupported_state(page, name)
    if state == "root-only":
        return ("option %s of '%s' requires root privileges: %s are not"
                " available to a rootless runtime (see: udocker %s --help)"
                % (name, where, ROOT_ONLY_OPTIONS[(page, name)], where))
    return ("option %s of '%s' is not applicable to rootless udocker: %s"
            " (see: udocker %s --help)"
            % (name, where, NOT_APPLICABLE_OPTIONS[(page, name)], where))


def parse_options(args, page="", stop_at_positional=False):
    """Parse the options of one compose command page.

    Every option that the real docker compose accepts for this page is
    recognized, so an unimplemented but applicable option never fails as
    "unknown option". Options may appear before or after the positional
    arguments, "--option=value" and "--option value" both work, and the
    short options of the page are mapped to their long name.
    """
    options = {}
    positional = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            positional.extend(args[index + 1:])
            break
        if not arg.startswith("-") or arg == "-":
            if stop_at_positional:
                positional.extend(args[index:])
                break
            positional.append(arg)
            index += 1
            continue
        (raw, separator, inline) = arg.partition("=")
        name = canonical_option(page, raw)
        if name is None:
            raise ComposeError("unknown option: %s (see: udocker compose %s"
                               "--help)" % (arg, (page + " ") if page else ""))
        if unsupported_state(page, name):
            raise ComposeError(unsupported_error(page, name))
        kind = option_kind(page, name)
        if kind == "flag":
            if separator:
                if inline not in ("true", "false"):
                    raise ComposeError("option %s does not take a value: %s"
                                       % (name, arg))
                options[name] = inline == "true"
            else:
                options[name] = True
            index += 1
            continue
        if separator:
            value = inline
        elif index + 1 < len(args) and not (
                name in OPTIONAL_VALUE_OPTIONS and
                str(args[index + 1]).startswith("-")):
            index += 1
            value = args[index]
        elif name in OPTIONAL_VALUE_OPTIONS:
            value = OPTIONAL_VALUE_OPTIONS[name]
        else:
            raise ComposeError("option %s requires a value" % name)
        if value == "":
            raise ComposeError("option %s requires a value" % name)
        if kind == "list":
            options.setdefault(name, []).append(value)
        else:
            options[name] = value
        index += 1
    return (options, positional)


def _option_text(options, flag, default=None):
    """The last value of an option, None when it is not present"""
    value = options.get(flag)
    if isinstance(value, (list, tuple)):
        value = value[-1] if value else None
    return default if value is None else value


def _option_list(options, flag):
    """The values of a repeatable option, always a list"""
    value = options.get(flag)
    if value is None or value is False:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _option_int(options, flag, default=None):
    """An integer option value, a compose error on a bad number"""
    value = _option_text(options, flag)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ComposeError("invalid %s value: %s" % (flag, value))


def _load_project(options):
    """Load the compose file selected by the global and command options"""
    files = _option_list(options, "--file")
    if files:
        for path in files:
            if not os.path.isfile(path):
                raise ComposeError("compose file not found: %s" % path)
    else:
        path = find_compose_file()
        if not path:
            raise ComposeError("no compose file found in %s (tried: %s)"
                               % (os.getcwd(), ", ".join(COMPOSE_FILES)))
        files = [path]
    directory = _option_text(options, "--project-directory")
    if directory:
        directory = os.path.abspath(directory)
        if not os.path.isdir(directory):
            raise ComposeError("project directory not found: %s" % directory)
    return ComposeProject(
        files,
        name=_option_text(options, "--project-name"),
        directory=directory,
        env_files=_option_list(options, "--env-file"),
        profiles=_option_list(options, "--profile"),
        interpolate=not options.get("--no-interpolate"),
        resolve_env=not options.get("--no-env-resolution"),
        resolve_paths=not options.get("--no-path-resolution"))


def _record_status(record):
    """Lowercase status of a container record from udocker ps"""
    return str(record_field(record, "status")).lower()


def _record_running(record):
    """True when the container record describes a running container"""
    return _record_status(record) in ("running", "paused", "restarting")


def _selected_order(project, selected, no_deps=False):
    """Service start order, dependencies first unless --no-deps is used"""
    if no_deps:
        project.select(selected)
        return list(selected)
    return project.order(selected)


def _check_external_volumes(project):
    """Fail early when a declared external volume does not exist"""
    for name in project.external_volumes():
        if not os.path.isdir(os.path.join(str(Config.conf["topdir"]),
                                          "volumes", name, "_data")):
            raise ComposeError("external volume does not exist: %s" % name)


def _build_services(project, services, options):
    """Build the services that declare a build section, True on success"""
    extra = ["--build-arg=" + item
             for item in _option_list(options, "--build-arg")]
    for service in services:
        plan = project.plan(service)
        build = build_arguments(plan, extra)
        if not build:
            continue
        Msg().out("Info: building image: %s" % plan["image"], l=Msg.INF)
        (status, dummy) = _udocker(build)
        if status != 0:
            Msg().err("Error: build failed for service:", service)
            return False
        if options.get("--push"):
            (status, dummy) = _udocker(["push", plan["image"]])
            if status != 0:
                Msg().err("Error: push failed for service:", service)
                return False
    return True


def _image_present(image):
    """True when the image already exists in the udocker repository"""
    spec = str(image)
    (repository, separator, tag) = spec.rpartition(":")
    if not separator or "/" in tag or not tag:
        (repository, tag) = (spec, "latest")
    path = os.path.join(str(Config.conf["topdir"]), "repos", repository, tag)
    return os.path.isdir(path)


def _pull_services(project, services, options):
    """Pull the images of the services, True when every pull worked"""
    policy = _option_text(options, "--policy", "missing")
    ignore = bool(options.get("--ignore-pull-failures"))
    for service in services:
        plan = project.plan(service)
        if options.get("--ignore-buildable") and plan["build"]:
            continue
        image = plan["image"]
        if policy != "always" and _image_present(image):
            continue
        Msg().out("Info: pulling image: %s" % image, l=Msg.INF)
        (status, dummy) = _udocker(["pull", image])
        if status == 0:
            continue
        if ignore:
            _warn("cannot pull image: %s" % image)
            continue
        Msg().err("Error: cannot pull image:", image)
        return False
    return True


def _wait_services(project, services, timeout):
    """Wait until every service container is running or healthy"""
    for service in services:
        plan = project.plan(service)
        name = plan["container_name"]
        test = (plan.get("healthcheck") or {}).get("test") or []
        healthy = bool(test) and test[0] != "NONE"
        ok = _wait_healthy(name, timeout) if healthy else \
            _wait_running(name, timeout)
        if not ok:
            Msg().err("Error: container is not ready:", name)
            return False
    return True


def _ensure_container(project, service, options, index):
    """Create and start one service container; returns (ok, name)"""
    plan = project.plan(service)
    name = plan["container_name"]
    record = index.get(name)
    if record is not None and options.get("--force-recreate"):
        Msg().out("Info: removing container: %s" % name, l=Msg.INF)
        _udocker(["rm", "-f", name])
        record = None
    if record is None:
        Msg().out("Info: creating container: %s" % name, l=Msg.INF)
        (status, dummy) = _udocker(create_arguments(plan))
        if status != 0:
            Msg().err("Error: cannot create container:", name)
            return (False, name)
    elif _record_running(record):
        Msg().out("Info: container is already running: %s" % name, l=Msg.INF)
        return (True, name)
    Msg().out("Info: starting container: %s" % name, l=Msg.INF)
    (status, dummy) = _udocker(run_arguments(plan))
    if status != 0:
        Msg().err("Error: cannot start container:", name)
        return (False, name)
    return (True, name)


def _create_container(project, service, options, index):
    """Create one service container without starting it; (ok, name)"""
    plan = project.plan(service)
    name = plan["container_name"]
    record = index.get(name)
    if record is not None:
        if options.get("--force-recreate"):
            _udocker(["rm", "-f", name])
            record = None
        elif options.get("--no-recreate"):
            Msg().out("Info: container exists: %s" % name, l=Msg.INF)
            return (True, name)
        else:
            Msg().out("Info: container exists: %s" % name, l=Msg.INF)
            return (True, name)
    Msg().out("Info: creating container: %s" % name, l=Msg.INF)
    (status, dummy) = _udocker(create_arguments(plan))
    if status != 0:
        Msg().err("Error: cannot create container:", name)
        return (False, name)
    return (True, name)


def _cmd_up(cli, options, rest):
    """compose up: build, create and start the project"""
    project = _load_project(options)
    _check_external_volumes(project)
    selected = project.select(rest)
    no_deps = bool(options.get("--no-deps"))
    order = _selected_order(project, selected, no_deps)
    if options.get("--build") and not _build_services(project, order, options):
        return cli.STATUS_ERROR
    pull = _option_text(options, "--pull")
    if pull and pull != "never":
        if not _pull_services(project, order, options):
            return cli.STATUS_ERROR
    start = container_index(list_containers())
    if options.get("--remove-orphans"):
        _remove_orphans(project, start)
        start = container_index(list_containers())
    started = []
    for service in order:
        plan = project.plan(service)
        if not no_deps:
            for dependency in plan.get("depends_on") or []:
                condition = (plan.get("depends_conditions") or {}).get(
                    dependency)
                if condition != "service_healthy":
                    continue
                dependency_name = project.plan(dependency)["container_name"]
                Msg().out("Info: waiting for %s to be healthy"
                          % dependency_name, l=Msg.INF)
                if not _wait_healthy(dependency_name):
                    Msg().err("Error: dependency is not healthy:",
                              dependency_name)
                    return cli.STATUS_ERROR
        if options.get("--no-start"):
            (ok, dummy) = _create_container(project, service, options, start)
        else:
            (ok, dummy) = _ensure_container(project, service, options, start)
        if not ok:
            return cli.STATUS_ERROR
        if not options.get("--no-start"):
            started.append(plan["container_name"])
    if options.get("--no-start"):
        return cli.STATUS_OK
    if options.get("--wait"):
        timeout = _option_int(options, "--wait-timeout", HEALTH_WAIT_TIMEOUT)
        if not _wait_services(project, order, timeout):
            return cli.STATUS_ERROR
    detach = bool(options.get("--detach") or options.get("--wait"))
    if detach:
        Msg().out("Info: project %s is up" % project.name, l=Msg.INF)
        return cli.STATUS_OK
    attach = _option_list(options, "--attach")
    no_attach = _option_list(options, "--no-attach")
    follow = []
    for service in order:
        if attach and service not in attach:
            continue
        if service in no_attach:
            continue
        follow.append(project.plan(service)["container_name"])
    Msg().out("Info: attached to the project logs, Ctrl-C stops the project",
              l=Msg.INF)
    try:
        stream_logs(follow, extra=_log_options(options))
    except KeyboardInterrupt:
        Msg().out("Info: keyboard interrupt", l=Msg.INF)
        kill_active()
    Msg().out("Info: stopping containers", l=Msg.INF)
    timeout = _option_int(options, "--timeout")
    for name in started:
        _udocker(["stop"] + _timeout_option(timeout) + [name])
    return cli.STATUS_OK


def _timeout_option(timeout, flag="--time"):
    """The udocker stop/restart timeout option, an empty list by default"""
    if timeout is None:
        return []
    return [flag + "=" + str(timeout)]


def _cmd_down(cli, options, rest):
    """compose down: stop and remove the project containers"""
    project = _load_project(options)
    services = project.select(rest) if rest else list(project.services)
    index = container_index(list_containers())
    return _down_project(cli, project, options, services, index)


def _down_project(cli, project, options, services, index):
    """Stop and remove the project containers of the selected services"""
    names = [project.plan(service)["container_name"]
             for service in services]
    if options.get("--remove-orphans"):
        names.extend(orphan_names(project, index))
    timeout = _option_int(options, "--timeout")
    status = cli.STATUS_OK
    for name in names:
        if name not in index:
            continue
        Msg().out("Info: stopping container: %s" % name, l=Msg.INF)
        _udocker(["stop"] + _timeout_option(timeout) + [name])
        Msg().out("Info: removing container: %s" % name, l=Msg.INF)
        (result, dummy) = _udocker(["rm", "-f", name])
        if result != 0:
            Msg().err("Error: cannot remove container:", name)
            status = cli.STATUS_ERROR
    if options.get("--rmi"):
        for service in services:
            image = project.plan(service)["image"]
            Msg().out("Info: removing image: %s" % image, l=Msg.INF)
            (result, dummy) = _udocker(["rmi", image])
            if result != 0:
                _warn("cannot remove image: %s" % image)
    if options.get("--volumes"):
        declared = project.volume_defs()
        for (source, name) in project.volume_names().items():
            definition = declared.get(source)
            if isinstance(definition, dict) and definition.get("external"):
                continue
            Msg().out("Info: removing volume: %s" % name, l=Msg.INF)
            (result, dummy) = _udocker(["volume", "rm", "-f", name])
            if result != 0:
                _warn("cannot remove volume: %s" % name)
    return status


def _cmd_create(cli, options, rest):
    """compose create: create the service containers without starting them"""
    project = _load_project(options)
    _check_external_volumes(project)
    order = _selected_order(project, project.select(rest),
                            options.get("--no-deps"))
    if options.get("--build") and not _build_services(project, order, options):
        return cli.STATUS_ERROR
    pull = _option_text(options, "--pull")
    if pull and pull != "never":
        if not _pull_services(project, order, options):
            return cli.STATUS_ERROR
    index = container_index(list_containers())
    if options.get("--remove-orphans"):
        _remove_orphans(project, index)
        index = container_index(list_containers())
    for service in order:
        (ok, dummy) = _create_container(project, service, options, index)
        if not ok:
            return cli.STATUS_ERROR
    return cli.STATUS_OK


def _ps_filters(options, record):
    """Apply the --filter and --status conditions to a container record"""
    status = _record_status(record)
    wanted = []
    for item in _option_list(options, "--status"):
        wanted.extend(part.strip() for part in str(item).split(",")
                      if part.strip())
    for item in _option_list(options, "--filter"):
        text = str(item)
        if text.startswith("status="):
            wanted.append(text[len("status="):])
    if wanted and status not in [item.lower() for item in wanted]:
        return False
    return True


def _service_from_container(name, prefix, known):
    """The service a project container belongs to"""
    if name in known:
        return known[name]
    if prefix and name.startswith(prefix):
        return name[len(prefix):].rsplit("_", 1)[0]
    return ""


def _cmd_ps(cli, options, rest):
    """compose ps: list the containers of the project"""
    project = _load_project(options)
    selected = project.select(rest)
    known = OrderedDict((project.container_name(service), service)
                        for service in selected)
    prefix = "" if rest else project.name + "_"
    rows = []
    index = container_index(list_containers())
    for name in sorted(index):
        if name not in known and not (prefix and name.startswith(prefix)):
            continue
        record = index[name]
        if not options.get("--all") and not _record_running(record):
            continue
        if not _ps_filters(options, record):
            continue
        rows.append({
            "ID": name,
            "Name": name,
            "Service": _service_from_container(name, prefix, known),
            "State": _record_status(record),
            "Status": str(record_field(record, "status")),
            "Image": str(record_field(record, "image")),
        })
    if options.get("--services"):
        for row in rows:
            Msg().out(row["Service"])
        return cli.STATUS_OK
    if not rows:
        Msg().out("Info: no containers for project %s" % project.name,
                  l=Msg.INF)
        return cli.STATUS_OK
    if options.get("--quiet"):
        for row in rows:
            Msg().out(row["ID"])
        return cli.STATUS_OK
    text = _format_rows(options, rows, ["NAME", "SERVICE", "STATUS", "IMAGE"],
                        ["Name", "Service", "Status", "Image"],
                        [32, 16, 12, 0], options.get("--no-trunc"))
    if text:
        Msg().out(text)
    return cli.STATUS_OK


def _format_rows(options, rows, headers, fields, widths, no_trunc=False):
    """Render rows as a table, JSON or with a docker --format template"""
    fmt = _option_text(options, "--format")
    if fmt and fmt != "table":
        if fmt.startswith("json"):
            Msg().out(json.dumps(rows, indent=2))
            return ""
        if fmt.startswith("table "):
            Msg().out(render_table(fmt, rows))
            return ""
        Msg().out("\n".join(render_template(fmt, row) for row in rows))
        return ""
    cells = []
    for (header, width) in zip(headers, widths):
        cells.append(header if not width else "%-*.*s" % (width, width,
                                                          header))
    lines = [" ".join(cells).rstrip()]
    for row in rows:
        cells = []
        for (field, width) in zip(fields, widths):
            value = str(row.get(field, ""))
            if width and not no_trunc:
                value = value[:width]
            cells.append(value if not width else "%-*s" % (width, value))
        lines.append(" ".join(cells).rstrip())
    return "\n".join(lines)


def _log_options(options):
    """The udocker logs options for the time filtering flags"""
    extra = []
    since = _option_text(options, "--since")
    until = _option_text(options, "--until")
    if since:
        extra.append("--since=" + since)
    if until:
        extra.append("--until=" + until)
    if options.get("--timestamps"):
        extra.append("--timestamps")
    return extra


def _cmd_logs(cli, options, rest):
    """compose logs: print or follow the logs of the project containers"""
    project = _load_project(options)
    tail = _option_text(options, "--tail")
    if tail is not None and not str(tail).isdigit():
        raise ComposeError("invalid --tail value: %s" % tail)
    names = [project.container_name(service)
             for service in project.select(rest)]
    extra = _log_options(options)
    if options.get("--follow"):
        stream_logs(names, tail, extra)
        return cli.STATUS_OK
    for name in names:
        (status, output) = _udocker(["logs"] + _tail_options(tail) + extra +
                                    [name])
        if status != 0:
            return cli.STATUS_ERROR
        if output:
            Msg().out(output.rstrip("\n"))
    return cli.STATUS_OK


def _yaml_scalar(value):
    """One YAML scalar; JSON quoting is valid YAML and keeps types intact"""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == "":
        return '""'
    if re.search(r"[:#\[\]{},&*!|>'\"%@`\s]", text) or \
            text.lower() in ("true", "false", "null", "yes", "no", "on",
                             "off", "~") or \
            re.match(r"^[-+]?[0-9.]+$", text):
        return json.dumps(text)
    return text


def _yaml_flow(value):
    """A nested value rendered in flow style (JSON is valid YAML)"""
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return _yaml_scalar(value)


def _yaml_lines(value, indent=0):
    """Recursive list of YAML lines of a value"""
    pad = "  " * indent
    if isinstance(value, dict):
        if not value:
            return [pad + "{}"]
        lines = []
        for (key, item) in value.items():
            if isinstance(item, (dict, list)) and item:
                lines.append(pad + str(key) + ":")
                lines.extend(_yaml_lines(item, indent + 1))
            else:
                lines.append(pad + str(key) + ": " + _yaml_flow(item))
        return lines
    if isinstance(value, list):
        if not value:
            return [pad + "[]"]
        lines = []
        for item in value:
            if isinstance(item, (dict, list)) and item:
                nested = _yaml_lines(item, indent + 1)
                lines.append(pad + "- " + nested[0].strip())
                lines.extend(nested[1:])
            else:
                lines.append(pad + "- " + _yaml_flow(item))
        return lines
    return [pad + _yaml_flow(value)]


def dump_yaml(value):
    """Render a mapping as YAML, the default docker compose config format"""
    return "\n".join(_yaml_lines(value))


def _plan_hash(plan):
    """A stable hash of a normalized service like docker compose --hash"""
    payload = json.dumps(plan, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _network_names(project):
    """Network names declared by the services and the top level"""
    names = []

    def add(value):
        """Add the keys of a networks declaration"""
        if isinstance(value, dict):
            items = value.keys()
        elif isinstance(value, list):
            items = value
        else:
            return
        for item in items:
            if str(item) not in names:
                names.append(str(item))

    for config in project.all_services().values():
        if isinstance(config, dict):
            add(config.get("networks"))
    add(project.file.raw.get("networks"))
    return names


def _emit(options, text):
    """Write command output to stdout or to config --output"""
    path = _option_text(options, "--output")
    if not path:
        if text:
            Msg().out(text)
        return
    try:
        with open(path, "w") as filep:
            filep.write(text + "\n")
    except (IOError, OSError) as error:
        raise ComposeError("cannot write %s: %s" % (path, error))


def _cmd_config(cli, options, rest):
    """compose config: validate and print the normalized project"""
    project = _load_project(options)
    services = project.select(rest)
    fmt = _option_text(options, "--format", "yaml")
    if options.get("--quiet"):
        return cli.STATUS_OK
    if options.get("--services"):
        _emit(options, "\n".join(services))
        return cli.STATUS_OK
    if options.get("--volumes"):
        _emit(options, "\n".join(project.volume_names().values()))
        return cli.STATUS_OK
    if options.get("--images"):
        _emit(options, "\n".join(project.plan(service)["image"]
                                 for service in services))
        return cli.STATUS_OK
    if options.get("--profiles"):
        _emit(options, "\n".join(project.profiles()))
        return cli.STATUS_OK
    if options.get("--networks"):
        _emit(options, "\n".join(_network_names(project)))
        return cli.STATUS_OK
    if options.get("--environment"):
        values = dict(os.environ)
        values["COMPOSE_PROJECT_NAME"] = project.name
        _emit(options, "\n".join("%s=%s" % (key, values[key])
                                 for key in sorted(values)))
        return cli.STATUS_OK
    if options.get("--hash"):
        selector = _option_text(options, "--hash")
        wanted = services
        if selector and selector != "*":
            wanted = [item for item in selector.split(",") if item]
            unknown = [item for item in wanted if item not in project.services]
            if unknown:
                raise ComposeError("no such service: %s" % unknown[0])
        _emit(options, "\n".join("%s %s" % (service,
                                            _plan_hash(project.plan(service)))
                                 for service in wanted))
        return cli.STATUS_OK
    if fmt not in ("yaml", "json"):
        raise ComposeError("unsupported --format value: %s (use yaml or json)"
                           % fmt)
    model = OrderedDict()
    model["name"] = project.name
    model["services"] = OrderedDict((service, project.plan(service))
                                    for service in services)
    if fmt == "json":
        text = json.dumps(model, indent=2)
    else:
        text = dump_yaml(model)
    _emit(options, text)
    return cli.STATUS_OK


def _cmd_build(cli, options, rest):
    """compose build: build the images of the services"""
    project = _load_project(options)
    selected = project.select(rest)
    if options.get("--with-dependencies"):
        services = project.order(selected)
    else:
        services = selected
    if not _build_services(project, services, options):
        return cli.STATUS_ERROR
    return cli.STATUS_OK


def _cmd_pull(cli, options, rest):
    """compose pull: pull the images of the services"""
    project = _load_project(options)
    selected = project.select(rest)
    if options.get("--include-deps"):
        services = project.order(selected)
    else:
        services = selected
    if not _pull_services(project, services, options):
        return cli.STATUS_ERROR
    return cli.STATUS_OK


def _cmd_push(cli, options, rest):
    """compose push: push the images of the services"""
    project = _load_project(options)
    selected = project.select(rest)
    if options.get("--include-deps"):
        services = project.order(selected)
    else:
        services = selected
    ignore = bool(options.get("--ignore-missing"))
    for service in services:
        image = project.plan(service)["image"]
        if ignore and not _image_present(image):
            _warn("image is not available locally: %s" % image)
            continue
        Msg().out("Info: pushing image: %s" % image, l=Msg.INF)
        (status, dummy) = _udocker(["push", image])
        if status != 0:
            Msg().err("Error: cannot push image:", image)
            return cli.STATUS_ERROR
    return cli.STATUS_OK


def _service_names(project, rest):
    """Ordered mapping of container name to service for the selection"""
    result = OrderedDict()
    for service in project.select(rest):
        result[project.container_name(service)] = service
    return result


def _cmd_start(cli, options, rest):
    """compose start: start the existing service containers"""
    project = _load_project(options)
    names = _service_names(project, rest)
    index = container_index(list_containers())
    status = cli.STATUS_OK
    for name in names:
        record = index.get(name)
        if record is None or _record_running(record):
            continue
        Msg().out("Info: starting container: %s" % name, l=Msg.INF)
        (result, dummy) = _udocker(["start", name])
        if result != 0:
            status = cli.STATUS_ERROR
    if options.get("--wait"):
        timeout = _option_int(options, "--wait-timeout", HEALTH_WAIT_TIMEOUT)
        if not _wait_services(project, list(names.values()), timeout):
            return cli.STATUS_ERROR
    return status


def _cmd_stop(cli, options, rest):
    """compose stop: stop the running service containers"""
    project = _load_project(options)
    names = _service_names(project, rest)
    index = container_index(list_containers())
    timeout = _option_int(options, "--timeout")
    status = cli.STATUS_OK
    for name in names:
        record = index.get(name)
        if record is None or not _record_running(record):
            continue
        Msg().out("Info: stopping container: %s" % name, l=Msg.INF)
        (result, dummy) = _udocker(["stop"] + _timeout_option(timeout) +
                                   [name])
        if result != 0:
            status = cli.STATUS_ERROR
    return status


def _cmd_restart(cli, options, rest):
    """compose restart: restart the service containers"""
    project = _load_project(options)
    names = _service_names(project, rest)
    index = container_index(list_containers())
    timeout = _option_int(options, "--timeout")
    status = cli.STATUS_OK
    for name in names:
        if name not in index:
            continue
        Msg().out("Info: restarting container: %s" % name, l=Msg.INF)
        (result, dummy) = _udocker(["restart"] + _timeout_option(timeout) +
                                   [name])
        if result != 0:
            status = cli.STATUS_ERROR
    return status


def _cmd_kill(cli, options, rest):
    """compose kill: send a signal to the service containers"""
    project = _load_project(options)
    index = container_index(list_containers())
    names = list(_service_names(project, rest))
    if options.get("--remove-orphans"):
        names.extend(orphan_names(project, index))
    signal = _option_text(options, "--signal", "SIGKILL")
    status = cli.STATUS_OK
    for name in names:
        if name not in index:
            continue
        Msg().out("Info: killing container: %s" % name, l=Msg.INF)
        (result, dummy) = _udocker(["kill", "--signal=" + signal, name])
        if result != 0:
            status = cli.STATUS_ERROR
    return status


def _cmd_pause(cli, options, rest):
    """compose pause: pause the service containers"""
    project = _load_project(options)
    index = container_index(list_containers())
    status = cli.STATUS_OK
    for name in _service_names(project, rest):
        record = index.get(name)
        if record is None or not _record_running(record):
            continue
        (result, dummy) = _udocker(["pause", name])
        if result != 0:
            status = cli.STATUS_ERROR
    return status


def _cmd_unpause(cli, options, rest):
    """compose unpause: resume the paused service containers"""
    project = _load_project(options)
    index = container_index(list_containers())
    status = cli.STATUS_OK
    for name in _service_names(project, rest):
        if name not in index:
            continue
        (result, dummy) = _udocker(["unpause", name])
        if result != 0:
            status = cli.STATUS_ERROR
    return status


def _cmd_rm(cli, options, rest):
    """compose rm: remove the service containers"""
    project = _load_project(options)
    index = container_index(list_containers())
    status = cli.STATUS_OK
    for name in _service_names(project, rest):
        if name not in index:
            continue
        if options.get("--stop"):
            _udocker(["stop", name])
        Msg().out("Info: removing container: %s" % name, l=Msg.INF)
        (result, dummy) = _udocker(["rm", "-f", name])
        if result != 0:
            Msg().err("Error: cannot remove container:", name)
            status = cli.STATUS_ERROR
    return status


def _service_from_argument(project, text):
    """Replace a service:path argument with container:path"""
    if ":" not in text:
        return text
    (head, tail) = text.split(":", 1)
    if not head or os.path.isabs(text) or "/" in head:
        return text
    if head not in project.services:
        raise ComposeError("no such service: %s" % head)
    return project.container_name(head) + ":" + tail


def _cmd_cp(cli, options, rest):
    """compose cp: copy files between a service container and the host"""
    if len(rest) != 2:
        raise ComposeError("cp requires a service:path and a destination")
    project = _load_project(options)
    (source, target) = rest
    argv = ["cp", _service_from_argument(project, source),
            _service_from_argument(project, target)]
    (status, output) = _udocker(argv)
    if output:
        Msg().out(output.rstrip("\n"))
    return status


def _cmd_commit(cli, options, rest):
    """compose commit: create an image from a service container"""
    if not rest:
        raise ComposeError("commit requires a service name")
    project = _load_project(options)
    service = rest[0]
    plan = project.plan(service)
    image = rest[1] if len(rest) > 1 else plan["image"]
    argv = ["commit"]
    message = _option_text(options, "--message")
    author = _option_text(options, "--author")
    if message:
        argv.append("--message=" + message)
    if author:
        argv.append("--author=" + author)
    argv.extend([plan["container_name"], image])
    (status, output) = _udocker(argv)
    if output:
        Msg().out(output.rstrip("\n"))
    return status


def _cmd_export(cli, options, rest):
    """compose export: export a service container to a tar file"""
    if not rest:
        raise ComposeError("export requires a service name")
    project = _load_project(options)
    plan = project.plan(rest[0])
    output = _option_text(options, "--output")
    if not output:
        raise ComposeError("export writes a tar stream to stdout in docker"
                           " compose; this implementation needs --output/-o")
    (status, message) = _udocker(["export", "-o", output,
                                  plan["container_name"]])
    if message:
        Msg().out(message.rstrip("\n"))
    return status


def _cmd_events(cli, options, rest):
    """compose events: stream the events of the project containers"""
    project = _load_project(options)
    argv = ["events"]
    since = _option_text(options, "--since")
    until = _option_text(options, "--until")
    if since:
        argv.append("--since=" + since)
    if until:
        argv.append("--until=" + until)
    if options.get("--json"):
        argv.append("--format=json")
    for service in project.select(rest):
        argv.append("--filter=container=" + project.container_name(service))
    return _udocker(argv, stream=True)[0]


def _cmd_images(cli, options, rest):
    """compose images: list the images of the service containers"""
    project = _load_project(options)
    names = _service_names(project, rest or None)
    index = container_index(list_containers())
    rows = []
    for name in names:
        record = index.get(name)
        if record is None:
            continue
        rows.append({"Container": name, "Name": name,
                     "Image": str(record_field(record, "image"))})
    if not rows:
        return cli.STATUS_OK
    if options.get("--quiet"):
        for row in rows:
            Msg().out(row["Container"])
        return cli.STATUS_OK
    text = _format_rows(options, rows, ["CONTAINER", "IMAGE"],
                        ["Container", "Image"], [32, 0])
    if text:
        Msg().out(text)
    return cli.STATUS_OK


def _project_of_container(name):
    """The compose project a container name belongs to"""
    parts = name.rsplit("_", 2)
    if len(parts) == 3 and parts[2].isdigit():
        return parts[0]
    return ""


def _ls_filters(options, project):
    """Apply ls --filter name=/status= conditions"""
    for item in _option_list(options, "--filter"):
        text = str(item)
        if "=" not in text:
            continue
        (key, value) = text.split("=", 1)
        if key == "name" and value not in project["Name"]:
            return False
        if key == "status" and value != project["State"]:
            return False
    return True


def _cmd_ls(cli, options, rest):
    """compose ls: list the compose projects found in the repository"""
    index = container_index(list_containers())
    projects = OrderedDict()
    for name in sorted(index):
        project = _project_of_container(name)
        if not project:
            continue
        entry = projects.setdefault(project, {"Name": project,
                                              "State": "exited"})
        if _record_running(index[name]):
            entry["State"] = "running"
    rows = []
    for entry in projects.values():
        if not options.get("--all") and entry["State"] != "running":
            continue
        if not _ls_filters(options, entry):
            continue
        rows.append(entry)
    if options.get("--quiet"):
        for row in rows:
            Msg().out(row["Name"])
        return cli.STATUS_OK
    if not rows:
        return cli.STATUS_OK
    text = _format_rows(options, rows, ["NAME", "STATUS"],
                        ["Name", "State"], [32, 0])
    if text:
        Msg().out(text)
    return cli.STATUS_OK


def _volume_exists(name):
    """True when the named volume exists in the udocker repository"""
    path = os.path.join(str(Config.conf["topdir"]), "volumes", name, "_data")
    return os.path.isdir(path)


def _cmd_volumes(cli, options, rest):
    """compose volumes: list the named volumes of the project"""
    project = _load_project(options)
    project.select(rest)
    rows = [{"Name": name} for name in project.volume_names().values()
            if _volume_exists(name)]
    if not rows:
        return cli.STATUS_OK
    if options.get("--quiet"):
        for row in rows:
            Msg().out(row["Name"])
        return cli.STATUS_OK
    text = _format_rows(options, rows, ["NAME"], ["Name"], [40])
    if text:
        Msg().out(text)
    return cli.STATUS_OK


def _cmd_top(cli, options, rest):
    """compose top: display the processes of the service containers"""
    project = _load_project(options)
    index = container_index(list_containers())
    status = cli.STATUS_OK
    for name in _service_names(project, rest or None):
        if name not in index:
            continue
        (result, output) = _udocker(["top", name])
        if result != 0:
            status = cli.STATUS_ERROR
            continue
        if output:
            Msg().out(output.rstrip("\n"))
    return status


def _cmd_port(cli, options, rest):
    """compose port: print the public port of a service container"""
    if not rest:
        raise ComposeError("port requires a service name")
    project = _load_project(options)
    plan = project.plan(rest[0])
    mapping = rest[1] if len(rest) > 1 else ""
    protocol = _option_text(options, "--protocol")
    if mapping and protocol and "/" not in mapping:
        mapping = mapping + "/" + protocol
    (status, output) = _udocker(["port", plan["container_name"], mapping])
    if output:
        Msg().out(output.rstrip("\n"))
    return status


def _cmd_wait(cli, options, rest):
    """compose wait: wait until the service containers stop"""
    if not rest:
        raise ComposeError("wait requires at least one service name")
    project = _load_project(options)
    selected = project.select(rest)
    status = cli.STATUS_OK
    for service in selected:
        name = project.container_name(service)
        (result, output) = _udocker(["wait", name])
        if result != 0:
            status = cli.STATUS_ERROR
            continue
        if output.strip():
            Msg().out(output.strip())
    if options.get("--down-project"):
        index = container_index(list_containers())
        _down_project(cli, project, options, selected, index)
    return status


def _cmd_stats(cli, options, rest):
    """compose stats: print one resource usage snapshot of the containers"""
    project = _load_project(options)
    index = container_index(list_containers())
    names = []
    for name in _service_names(project, rest or None):
        record = index.get(name)
        if record is None:
            continue
        if not options.get("--all") and not _record_running(record):
            continue
        names.append(name)
    if not names:
        return cli.STATUS_OK
    fmt = _option_text(options, "--format")
    if fmt == "json":
        rows = [{"Name": name, "State": _record_status(index[name])}
                for name in names]
        Msg().out(json.dumps(rows, indent=2))
        return cli.STATUS_OK
    if fmt and fmt not in ("table",):
        raise ComposeError("stats --format supports table and json, not: %s"
                           % fmt)
    (status, output) = _udocker(["stats"] + names)
    if output:
        Msg().out(output.rstrip("\n"))
    return status


def _oneoff_arguments(plan, options, command):
    """The udocker run command line of a one-off service container"""
    args = ["run"]
    if options.get("--rm"):
        args.append("--rm")
    if options.get("--detach"):
        args.append("-d")
    if options.get("--interactive"):
        args.append("-i")
    if not options.get("--no-tty") and sys.stdout.isatty() and \
            not options.get("--detach"):
        args.append("-t")
    environment = list(plan["environment"])
    for item in _option_list(options, "--env"):
        if "=" in item:
            environment.append(item)
    for item in environment:
        args.append("--env=" + item)
    for item in _option_list(options, "--env-from-file"):
        args.append("--env-file=" + item)
    for item in plan["volumes"] + _option_list(options, "--volume"):
        args.append("--volume=" + item)
    if options.get("--service-ports"):
        for item in plan["ports"]:
            args.append("--publish=" + item)
    for item in _option_list(options, "--publish"):
        args.append("--publish=" + item)
    workdir = _option_text(options, "--workdir") or plan["working_dir"]
    if workdir:
        args.append("--workdir=" + workdir)
    user = _option_text(options, "--user") or plan["user"]
    if user:
        args.append("--user=" + user)
    entrypoint = _option_text(options, "--entrypoint")
    if entrypoint:
        args.append("--entrypoint=" + entrypoint)
    elif plan["entrypoint"]:
        args.append("--entrypoint=" + " ".join(plan["entrypoint"]))
    for item in plan["labels"] + _option_list(options, "--label"):
        args.append("--label=" + item)
    if plan["hostname"]:
        args.append("--hostname=" + plan["hostname"])
    for item in plan["ulimits"]:
        args.append("--ulimit=" + item)
    if plan["stop_signal"]:
        args.append("--stop-signal=" + plan["stop_signal"])
    pull = _option_text(options, "--pull")
    if pull:
        args.append("--pull=" + pull)
    name = _option_text(options, "--name")
    if name:
        args.append("--name=" + name)
    args.append(plan["image"])
    args.extend(command or plan["command"])
    return args


def _udocker_detached(args):
    """Start a udocker child in the background without waiting for it"""
    argv = child_arguments(args)
    Msg().out("Debug: exec detached: %s" % " ".join(argv), l=Msg.DBG)
    try:
        proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
    except (OSError, ValueError) as error:
        Msg().err("Error: cannot start background command:", str(error))
        return 1
    Msg().out(str(proc.pid))
    return 0


def _cmd_run(cli, options, rest):
    """compose run: run a one-off command on a service"""
    if not rest:
        raise ComposeError("run requires a service name")
    project = _load_project(options)
    service = rest[0]
    command = rest[1:]
    plan = project.plan(service)
    if options.get("--build"):
        if not _build_services(project, [service], options):
            return cli.STATUS_ERROR
    index = container_index(list_containers())
    if options.get("--remove-orphans"):
        _remove_orphans(project, index)
        index = container_index(list_containers())
    if not options.get("--no-deps"):
        for dependency in project.order([service])[:-1]:
            (ok, dummy) = _ensure_container(project, dependency, options,
                                            index)
            if not ok:
                return cli.STATUS_ERROR
    args = _oneoff_arguments(plan, options, command)
    if options.get("--detach"):
        return _udocker_detached(args)
    return _udocker(args, stream=True)[0]


def _cmd_exec(cli, options, rest):
    """compose exec: execute a command in a running service container"""
    if len(rest) < 2:
        raise ComposeError("exec requires a service name and a command")
    project = _load_project(options)
    plan = project.plan(rest[0])
    args = ["exec"]
    for item in _option_list(options, "--env"):
        args.append("--env=" + item)
    user = _option_text(options, "--user")
    if user:
        args.append("--user=" + user)
    workdir = _option_text(options, "--workdir")
    if workdir:
        args.append("--workdir=" + workdir)
    if not options.get("--no-tty") and not options.get("--detach") and \
            sys.stdout.isatty():
        args.append("-t")
    args.append(plan["container_name"])
    args.extend(rest[1:])
    if options.get("--detach"):
        return _udocker_detached(args)
    return _udocker(args, stream=True)[0]


def _cmd_version(cli, options, rest):
    """compose version: print the compose version like the real one"""
    fmt = _option_text(options, "--format")
    if options.get("--short"):
        Msg().out(COMPOSE_VERSION[1:])
        return cli.STATUS_OK
    if fmt in (None, "", "pretty"):
        Msg().out("Docker Compose version %s" % COMPOSE_VERSION)
        return cli.STATUS_OK
    if fmt == "json":
        Msg().out(json.dumps({"version": COMPOSE_VERSION}))
        return cli.STATUS_OK
    raise ComposeError("unsupported --format value: %s (use pretty or json)"
                       % fmt)


POSITIONAL_COMMAND_PAGES = ("exec", "run")


def _raw_arguments():
    """The compose arguments as typed after the compose word"""
    argv = list(sys.argv)
    try:
        index = argv.index("compose")
    except ValueError:
        return []
    return argv[index + 1:]


def _print_usage():
    """Print the compose subcommand list on stderr"""
    Msg().err("Commands: up, down, ps, logs, config")
    Msg().err("Also: attach, bridge, build, commit, cp, create, events, exec,"
              " export, images, kill, ls, pause, port, publish, pull, push,"
              " restart, rm, run, scale, start, stats, stop, top, unpause,"
              " version, volumes, wait, watch")
    Msg().err("See: udocker compose --help")


HANDLERS = {
    "build": _cmd_build,
    "commit": _cmd_commit,
    "config": _cmd_config,
    "cp": _cmd_cp,
    "create": _cmd_create,
    "down": _cmd_down,
    "events": _cmd_events,
    "exec": _cmd_exec,
    "export": _cmd_export,
    "images": _cmd_images,
    "kill": _cmd_kill,
    "logs": _cmd_logs,
    "ls": _cmd_ls,
    "pause": _cmd_pause,
    "port": _cmd_port,
    "ps": _cmd_ps,
    "pull": _cmd_pull,
    "push": _cmd_push,
    "restart": _cmd_restart,
    "rm": _cmd_rm,
    "run": _cmd_run,
    "stats": _cmd_stats,
    "start": _cmd_start,
    "stop": _cmd_stop,
    "top": _cmd_top,
    "unpause": _cmd_unpause,
    "up": _cmd_up,
    "version": _cmd_version,
    "volumes": _cmd_volumes,
    "wait": _cmd_wait,
}


def do_compose(cli, cmdp):
    """
    compose: run a multi-container project described by a compose file
    compose [globals] <command> [options] [services...]
    -f, --file=<file>          :compose file, repeatable (default: compose.yaml,
                                compose.yml, udocker-compose.yml/..yaml,
                                docker-compose.yml or .yaml)
    -p, --project-name=<name>  :project name (default: name field or directory)
    --project-directory=<dir>  :base directory for relative paths
    --env-file=<file>          :environment file used for interpolation
    --profile=<name>           :enable the services of a profile, "*" for all
    --ansi=<mode>              :never, always or auto (accepted, no colour)
    --progress=<mode>          :auto, tty, plain, json or quiet (accepted)
    --parallel=<n>             :accepted, services start one at a time
    --compatibility            :accepted, no compose v1 compatibility mode
    --dry-run                  :print the command instead of running it

    Commands:
      up [options] [services...]   :create and start the services
      create [options] [services...]:create the containers, do not start them
      down [options] [services...]:stop and delete the project containers
      start|stop|restart|kill|pause|unpause|rm [services...]
      ps [options] [services...]   :list the project containers
      logs [options] [services...] :print or follow the service logs (-f is
                                    follow here, --file selects the file)
      config [options] [services...]:print the normalized project as YAML
                                    (--format json for JSON, --services,
                                    --volumes, --images, --hash, --profiles,
                                    --environment, -q, -o file)
      build|pull|push [services...]:build, pull or push the service images
      run [options] SERVICE [CMD]  :run a one-off command on a service
      exec [options] SERVICE CMD   :execute a command in a running container
      images|top|port|cp|commit|export|events|wait|stats|ls|volumes|version
      attach, bridge, publish, scale, watch are not applicable to rootless
      udocker and fail with an explicit message.

    Containers are named <project>_<service>_1 and are started detached
    through the supervisor in any execution mode (P/F/S use the monitor
    process group, R uses runc). Every docker compose option is either
    implemented, accepted as a no-op, or rejected with an explicit
    root-only / not-applicable error; unknown options are usage errors.
    Differences: no container networks beyond the host network stack, no
    scaling, no anonymous volumes, no log timestamps; only tcp ports with a
    host port are published; images are only pulled on request.
    """
    consume = getattr(cmdp, "consume_all", None)
    if consume is not None:
        consume()
    args = _raw_arguments()
    if not args:
        Msg().out(do_compose.__doc__)
        return cli.STATUS_OK
    if args[0] in ("-h", "--help", "help") or "-h" in args or \
            "--help" in args:
        Msg().out(do_compose.__doc__)
        return cli.STATUS_OK
    try:
        (global_options, rest) = parse_options(args, "", True)
        if not rest:
            Msg().err("Error: compose command expected")
            _print_usage()
            return cli.STATUS_ERROR
        page = rest[0]
        if page.startswith("-"):
            raise ComposeError("compose command expected, got: %s" % page)
        if page not in HANDLERS and page not in NOT_APPLICABLE_COMMANDS:
            Msg().err("Error: unknown compose command:", page)
            _print_usage()
            return cli.STATUS_ERROR
        (command_options, positional) = parse_options(
            rest[1:], page, page in POSITIONAL_COMMAND_PAGES)
        options = dict(global_options)
        options.update(command_options)
        if options.get("--dry-run"):
            Msg().out("Dry run: %s" % " ".join(["compose"] + rest))
            return cli.STATUS_OK
        if page in NOT_APPLICABLE_COMMANDS:
            raise ComposeError("%s is not applicable to rootless udocker: %s"
                               % (page, NOT_APPLICABLE_COMMANDS[page]))
        return HANDLERS[page](cli, options, positional)
    except ComposeError as error:
        Msg().err("Error:", str(error))
        return cli.STATUS_ERROR
    except (IOError, OSError) as error:
        Msg().err("Error:", str(error))
        return cli.STATUS_ERROR
    except KeyboardInterrupt:
        Msg().out("Info: keyboard interrupt", l=Msg.INF)
        kill_active()
        return cli.STATUS_OK
