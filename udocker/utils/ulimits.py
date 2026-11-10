# -*- coding: utf-8 -*-
"""Docker --ulimit handling: parsing, OCI rlimits and process limits."""

try:
    import resource
except ImportError:                     # pragma: no cover - non POSIX
    resource = None

NAMES = {
    "as": "AS", "core": "CORE", "cpu": "CPU", "data": "DATA",
    "fsize": "FSIZE", "locks": "LOCKS", "memlock": "MEMLOCK",
    "msgqueue": "MSGQUEUE", "nice": "NICE", "nofile": "NOFILE",
    "nproc": "NPROC", "rss": "RSS", "rtprio": "RTPRIO",
    "rttime": "RTTIME", "sigpending": "SIGPENDING", "stack": "STACK",
}

UNLIMITED = (1 << 64) - 1


def parse(statement):
    """Parse a name=soft[:hard] statement, raise ValueError when invalid"""
    text = str(statement).strip()
    (name, separator, value) = text.partition("=")
    name = name.strip().lower()
    if not separator:
        raise ValueError("expected name=soft[:hard]: %s" % text)
    if name not in NAMES:
        raise ValueError("unknown ulimit: %s" % name)
    value = value.strip()
    if not value:
        raise ValueError("missing value: %s" % text)
    parts = value.split(":")
    if len(parts) > 2:
        raise ValueError("invalid ulimit: %s" % text)
    try:
        soft = int(parts[0])
        hard = int(parts[1]) if len(parts) == 2 else soft
    except ValueError:
        raise ValueError("invalid number in ulimit: %s" % text)
    return {"name": name, "type": "RLIMIT_" + NAMES[name],
            "soft": soft, "hard": hard}


def parse_all(statements):
    """Parse every --ulimit statement, raise ValueError on the first bad one"""
    return [parse(item) for item in statements or []]


def oci_rlimits(statements):
    """OCI process.rlimits entries used by the runc engine"""
    entries = []
    for item in parse_all(statements):
        entries.append({
            "type": item["type"],
            "soft": item["soft"] if item["soft"] >= 0 else UNLIMITED,
            "hard": item["hard"] if item["hard"] >= 0 else UNLIMITED,
        })
    return entries


def apply(statements):
    """Set process rlimits inherited by the P/F/S children.

    Returns the previous values so restore() can put them back.
    """
    saved = []
    for item in parse_all(statements):
        limit = _rlimit(item["name"])
        previous = resource.getrlimit(limit)
        soft = _value(item["soft"])
        hard = _value(item["hard"])
        if hard > previous[1]:
            restore(saved)
            raise ValueError("cannot raise the hard limit of %s without"
                             " CAP_SYS_RESOURCE" % item["name"])
        if soft > hard:
            restore(saved)
            raise ValueError("soft limit above hard limit for %s"
                             % item["name"])
        try:
            resource.setrlimit(limit, (soft, hard))
        except (ValueError, OSError) as error:
            restore(saved)
            raise ValueError("cannot set ulimit %s: %s"
                             % (item["name"], error))
        saved.append((limit, previous))
    return saved


def restore(saved):
    """Restore the process rlimits saved by apply()"""
    if not saved:
        return
    for (limit, previous) in reversed(saved):
        try:
            resource.setrlimit(limit, previous)
        except (ValueError, OSError):
            pass


def _rlimit(name):
    """The resource module constant of an ulimit name"""
    if resource is None:
        raise ValueError("ulimits require a POSIX system")
    limit = getattr(resource, "RLIMIT_" + NAMES[name], None)
    if limit is None:
        raise ValueError("ulimit not supported here: %s" % name)
    return limit


def _value(number):
    """Soft/hard value with -1 meaning unlimited"""
    return resource.RLIM_INFINITY if number < 0 else number
