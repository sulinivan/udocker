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

COMPOSE_FILES = ("compose.yaml", "compose.yml",
                 "docker-compose.yml", "docker-compose.yaml")

SUPPORTED_KEYS = ("image", "build", "container_name", "command",
                  "entrypoint", "environment", "ports", "volumes",
                  "working_dir", "user", "labels", "depends_on")

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


class ComposeFile(object):
    """A parsed compose file with a validated services section"""

    def __init__(self):
        self.path = ""
        self.raw = OrderedDict()

    def parse(self, text, filename="compose"):
        """Parse compose text and return the raw mapping"""
        raw = _substitute(YamlParser().parse(text, filename))
        services = raw.get("services")
        if not isinstance(services, dict) or not services:
            raise ComposeError("%s: no services defined" % filename)
        volumes = raw.get("volumes")
        if volumes is not None and not isinstance(volumes, dict):
            raise ComposeError("%s: volumes must be a mapping" % filename)
        self.path = filename
        self.raw = raw
        return raw

    def load(self, path):
        """Read and parse a compose file"""
        try:
            with open(path, "r") as filep:
                text = filep.read()
        except (IOError, OSError) as error:
            raise ComposeError("cannot read %s: %s" % (path, error))
        return self.parse(text, path)

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


def parse_volumes(value, compose_dir, project="", volume_defs=None):
    """Normalize volumes to a list of host:container bind mounts.

    Relative bind paths are resolved against the compose file directory.
    A source without a path separator is a named volume: it is mapped to an
    udocker named volume, prefixed with the project name like docker
    compose does, unless the top-level declaration sets name: or
    external: true. The volume itself is created by the udocker run child.
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
                      volume_defs=None):
    """Return a normalized description of one service.

    Unknown keys are reported and ignored instead of failing the project,
    so a compose file that uses unsupported features still starts the
    parts that udocker can run.
    """
    if not isinstance(config, dict):
        raise ComposeError("service %s: expected a mapping" % service)
    for key in config:
        if key not in SUPPORTED_KEYS:
            _warn("service %s: unsupported key ignored: %s" % (service, key))
    context = _build_config(config.get("build"), service)
    if context and not os.path.isabs(context):
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
    return {
        "image": image,
        "container_name": str(name),
        "build": context,
        "command": parse_command(config.get("command")),
        "entrypoint": parse_command(config.get("entrypoint")),
        "environment": parse_environment(config.get("environment")),
        "ports": parse_ports(config.get("ports")),
        "volumes": parse_volumes(config.get("volumes"), compose_dir,
                                 project, volume_defs),
        "working_dir": str(config.get("working_dir") or ""),
        "user": str(config.get("user") or ""),
        "labels": parse_labels(config.get("labels")),
        "depends_on": parse_depends_on(config.get("depends_on")),
    }


def build_arguments(plan):
    """udocker build command line for a service, None if it is not built"""
    if not plan["build"]:
        return None
    return ["build", "-t=" + plan["image"], "--force", plan["build"]]


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
    if plan["labels"]:
        _warn("labels are not supported by udocker run, ignored: %s"
              % plan["container_name"])
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

    def __init__(self, path, name=None):
        self.file = ComposeFile()
        self.file.load(path)
        self.path = path
        self.dir = os.path.dirname(os.path.abspath(path))
        self.services = self.file.services()
        source = name or self.file.raw.get("name") or \
            os.path.basename(self.dir)
        self.name = normalize_name(source) or "app"
        self._plans = {}

    def plan(self, service):
        """Normalized plan of a service, computed once"""
        if service not in self._plans:
            if service not in self.services:
                raise ComposeError("no such service: %s" % service)
            self._plans[service] = normalize_service(
                self.name, service, self.services[service], self.dir,
                self.volume_defs())
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


def list_containers():
    """Return the containers of the repository as parsed JSON records"""
    (status, output) = _udocker(["ps", "-a", "--format=json"])
    if status != 0:
        raise ComposeError("cannot list containers: %s" % output.strip())
    try:
        containers = json.loads(output.strip() or "[]")
    except ValueError:
        raise ComposeError("cannot parse the container list")
    if not isinstance(containers, list):
        raise ComposeError("cannot parse the container list")
    return containers


def container_index(containers):
    """Map every container name to its ps record"""
    index = {}
    for container in containers:
        for name in str(container.get("name") or "").split(","):
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


def stream_logs(names, tail=None):
    """Follow the logs of one or several containers concurrently.

    Multiple services are followed in threads and their lines are printed
    without a service prefix, so the output stays byte exact but lines of
    different services may interleave.
    """
    base = ["logs"] + _tail_options(tail)
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


def parse_options(args, flags=(), values=()):
    """Parse compose command options mixed with positional arguments.

    Options may appear before or after the service names. Both
    --option=value and --option value are accepted.
    """
    options = {}
    positional = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            positional.extend(args[index + 1:])
            break
        if arg.startswith("-") and arg != "-":
            (name, separator, value) = arg.partition("=")
            if name in values:
                if not separator:
                    index += 1
                    if index >= len(args):
                        raise ComposeError("option %s requires a value"
                                           % name)
                    value = args[index]
                if not value:
                    raise ComposeError("option %s requires a value" % name)
                options[name] = value
            elif name in flags and not separator:
                options[name] = True
            else:
                raise ComposeError("unknown option: %s (see: udocker"
                                   " compose --help)" % arg)
        else:
            positional.append(arg)
        index += 1
    return (options, positional)


FILE_OPTIONS = ("-f", "--file", "-p", "--project-name")
PROJECT_OPTIONS = ("-p", "--project-name")
UP_FLAGS = ("-d", "--detach", "--build", "--force-recreate",
            "--remove-orphans")


def _load_project(options):
    """Load the compose file selected by the command options"""
    path = options.get("--file") or options.get("-f")
    if path and not isinstance(path, str):
        path = ""
    if path:
        if not os.path.isfile(path):
            raise ComposeError("compose file not found: %s" % path)
    else:
        path = find_compose_file()
        if not path:
            raise ComposeError("no compose file found in %s (tried: %s)"
                               % (os.getcwd(), ", ".join(COMPOSE_FILES)))
    return ComposeProject(path, options.get("-p")
                          or options.get("--project-name"))


def _remove_orphans(project, index):
    """Remove the project containers that are not in the compose file"""
    for name in orphan_names(project, index):
        Msg().out("Info: removing orphan container: %s" % name, l=Msg.INF)
        _udocker(["rm", "-f", name])


def _cmd_up(cli, args):
    """compose up: build, create and start the project"""
    (options, rest) = parse_options(args, UP_FLAGS, FILE_OPTIONS)
    project = _load_project(options)
    for name in project.external_volumes():
        if not os.path.isdir(os.path.join(str(Config.conf["topdir"]),
                                          "volumes", name, "_data")):
            Msg().err("Error: external volume does not exist:", name)
            return cli.STATUS_ERROR
    order = project.order(project.select(rest))
    if options.get("--build"):
        for service in order:
            plan = project.plan(service)
            build = build_arguments(plan)
            if not build:
                continue
            Msg().out("Info: building image: %s" % plan["image"], l=Msg.INF)
            (status, dummy) = _udocker(build)
            if status != 0:
                Msg().err("Error: build failed for service:", service)
                return cli.STATUS_ERROR
    start = container_index(list_containers())
    if options.get("--remove-orphans"):
        _remove_orphans(project, start)
        start = container_index(list_containers())
    started = []
    for service in order:
        plan = project.plan(service)
        name = plan["container_name"]
        record = start.get(name)
        if record is not None and options.get("--force-recreate"):
            Msg().out("Info: removing container: %s" % name, l=Msg.INF)
            _udocker(["rm", "-f", name])
            record = None
        if record is None:
            Msg().out("Info: creating container: %s" % name, l=Msg.INF)
            (status, dummy) = _udocker(create_arguments(plan))
            if status != 0:
                Msg().err("Error: cannot create container:", name)
                return cli.STATUS_ERROR
        elif str(record.get("status") or "").lower() == "running":
            Msg().out("Info: container is already running: %s" % name,
                      l=Msg.INF)
            started.append(name)
            continue
        Msg().out("Info: starting container: %s" % name, l=Msg.INF)
        (status, dummy) = _udocker(run_arguments(plan))
        if status != 0:
            Msg().err("Error: cannot start container:", name)
            return cli.STATUS_ERROR
        started.append(name)
    if options.get("-d") or options.get("--detach"):
        Msg().out("Info: project %s is up" % project.name, l=Msg.INF)
        return cli.STATUS_OK
    Msg().out("Info: attached to the project logs, Ctrl-C stops the project",
              l=Msg.INF)
    try:
        stream_logs([project.plan(service)["container_name"]
                     for service in order])
    except KeyboardInterrupt:
        Msg().out("Info: keyboard interrupt", l=Msg.INF)
        kill_active()
    Msg().out("Info: stopping containers", l=Msg.INF)
    for name in started:
        _udocker(["stop", name])
    return cli.STATUS_OK


def _cmd_down(cli, args):
    """compose down: stop and remove the project containers"""
    (options, dummy) = parse_options(
        args, ("--remove-orphans", "--rmi", "-v", "--volumes"), FILE_OPTIONS)
    project = _load_project(options)
    index = container_index(list_containers())
    names = list(project.names().values())
    if options.get("--remove-orphans"):
        names.extend(orphan_names(project, index))
    status = cli.STATUS_OK
    for name in names:
        if name not in index:
            continue
        Msg().out("Info: stopping container: %s" % name, l=Msg.INF)
        _udocker(["stop", name])
        Msg().out("Info: removing container: %s" % name, l=Msg.INF)
        (result, dummy) = _udocker(["rm", "-f", name])
        if result != 0:
            Msg().err("Error: cannot remove container:", name)
            status = cli.STATUS_ERROR
    if options.get("--rmi"):
        for service in project.services:
            image = project.plan(service)["image"]
            Msg().out("Info: removing image: %s" % image, l=Msg.INF)
            (result, dummy) = _udocker(["rmi", image])
            if result != 0:
                _warn("cannot remove image: %s" % image)
    if options.get("-v") or options.get("--volumes"):
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


def _cmd_ps(cli, args):
    """compose ps: list the containers of the project"""
    (options, rest) = parse_options(args, (), FILE_OPTIONS)
    project = _load_project(options)
    known = OrderedDict((project.container_name(service), service)
                        for service in project.select(rest))
    prefix = "" if rest else project.name + "_"
    rows = []
    index = container_index(list_containers())
    for name in sorted(index):
        if name in known:
            service = known[name]
        elif prefix and name.startswith(prefix):
            service = name[len(prefix):].rsplit("_", 1)[0]
        else:
            continue
        record = index[name]
        rows.append((name, service, str(record.get("status") or ""),
                     str(record.get("image") or "")))
    if not rows:
        Msg().out("Info: no containers for project %s" % project.name,
                  l=Msg.INF)
        return cli.STATUS_OK
    fmt = "%-32.32s %-16.16s %-12.12s %s"
    Msg().out(fmt % ("NAME", "SERVICE", "STATUS", "IMAGE"))
    for row in rows:
        Msg().out(fmt % row)
    return cli.STATUS_OK


def _cmd_logs(cli, args):
    """compose logs: print or follow the logs of the project containers"""
    (options, rest) = parse_options(
        args, ("-f", "--follow"), ("--file", "--tail") + PROJECT_OPTIONS)
    project = _load_project(options)
    tail = options.get("--tail")
    if tail is not None and not str(tail).isdigit():
        raise ComposeError("invalid --tail value: %s" % tail)
    names = [project.container_name(service)
             for service in project.select(rest)]
    if options.get("-f") or options.get("--follow"):
        stream_logs(names, tail)
        return cli.STATUS_OK
    for name in names:
        (status, output) = _udocker(["logs"] + _tail_options(tail) + [name])
        if status != 0:
            return cli.STATUS_ERROR
        if output:
            Msg().out(output.rstrip("\n"))
    return cli.STATUS_OK


def _cmd_config(cli, args):
    """compose config: print the normalized project as JSON"""
    (options, dummy) = parse_options(args, (), FILE_OPTIONS)
    project = _load_project(options)
    services = OrderedDict()
    for service in project.services:
        services[service] = project.plan(service)
    data = OrderedDict()
    data["name"] = project.name
    data["services"] = services
    Msg().out(json.dumps(data, indent=2))
    return cli.STATUS_OK


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
    Msg().err("See: udocker compose --help")


def do_compose(cli, cmdp):
    """
    compose: run a multi-container project described by a compose file
    compose [-f=<file>] [-p=<project>] <command> [options] [services...]
    -f, --file=<file>          :compose file (default: compose.yaml,
                                compose.yml, docker-compose.yml or .yaml)
    -p, --project-name=<name>  :project name (default: directory name)

    Commands:
      up [-d] [--build] [--force-recreate] [--remove-orphans] [services...]
                                :create and start the services; without -d
                                 follow the logs and stop on Ctrl-C
      down [--remove-orphans] [--rmi] [-v]
                                :stop and delete the project containers;
                                 -v also removes the project named volumes
      ps [services...]          :list the project containers
      logs [-f] [--tail=<lines>] [services...]
                                :print or follow the service logs (-f is
                                 follow here, use --file for the file)
      config                    :print the normalized project as JSON

    Containers are named <project>_<service>_1 and are started detached
    through the supervisor in any execution mode (P/F/S use the monitor
    process group, R uses runc).

    Differences from docker compose: no container networks beyond the host
    network stack, no health checks, restart policies or scaling; only tcp
    ports with a host port are published; images are not pulled; build
    sections are built with udocker build; labels are accepted but not
    applied. Named volumes are supported: "name:/path" becomes the udocker
    volume <project>_<name> unless the top-level volumes section sets name:
    or external: true.
    """
    consume = getattr(cmdp, "consume_all", None)
    if consume is not None:
        consume()
    args = _raw_arguments()
    if not args or args[0] in ("-h", "--help", "help"):
        Msg().out(do_compose.__doc__)
        return cli.STATUS_OK
    if args[0].startswith("-"):
        Msg().err("Error: compose command expected, got:", args[0])
        _print_usage()
        return cli.STATUS_ERROR
    if "-h" in args[1:] or "--help" in args[1:]:
        Msg().out(do_compose.__doc__)
        return cli.STATUS_OK
    handlers = {
        "up": _cmd_up,
        "down": _cmd_down,
        "ps": _cmd_ps,
        "logs": _cmd_logs,
        "config": _cmd_config,
    }
    if args[0] not in handlers:
        Msg().err("Error: unknown compose command:", args[0])
        _print_usage()
        return cli.STATUS_ERROR
    try:
        return handlers[args[0]](cli, args[1:])
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
