# -*- coding: utf-8 -*-
"""Drop-in shim for docker options that rootless udocker cannot honour.

Docker users pass options that only make sense with a daemon, cgroups or
privileges.  Rejecting them with a generic "syntax error" breaks scripts for
no reason, so this module rewrites the command line before it is parsed:

* options whose absence does not change what the container does (quiet,
  log-driver, dns options, host ipc/pid/uts, ...) are dropped silently;
* options that would promise limits or privileges the container will not get
  (memory, cpus, privileged, cap-add, ...) abort the command with an explicit
  message, because silently ignoring them means running with a different
  contract than the caller asked for.

The tables are the docker side of `replica/cli-flags.csv`; the probe in
replica/cli_probe.py re-checks every one of them against the real docker CLI.
"""

import re

# page -> {option: takes_value} dropped from the command line.  takes_value
# is 1 when docker expects an argument (the space separated form is common:
# `--log-driver json`), 0 for plain switches.
IGNORED = {
    "run": {"--quiet": 0, "--init": 0, "--detach-keys": 1,
            "--sig-proxy": 1, "--attach": 1, "--annotation": 1,
            "--domainname": 1, "--storage-opt": 1, "--cgroup-parent": 1,
            "--cgroupns": 1, "--log-driver": 1, "--log-opt": 1,
            "--shm-size": 1, "--use-api-socket": 0, "--dns-option": 1,
            "--isolation": 1, "--device-cgroup-rule": 1,
            "--volume-driver": 1, "--umask": 1},
    "create": {"--quiet": 0, "--init": 0, "--detach-keys": 1,
               "--sig-proxy": 1, "--attach": 1, "--annotation": 1,
               "--domainname": 1, "--storage-opt": 1, "--cgroup-parent": 1,
               "--cgroupns": 1, "--log-driver": 1, "--log-opt": 1,
               "--shm-size": 1, "--use-api-socket": 0, "--dns-option": 1,
               "--isolation": 1, "--device-cgroup-rule": 1,
               "--volume-driver": 1, "--umask": 1},
    "build": {"--quiet": 0, "--rm": 0, "--force-rm": 0, "--compress": 0,
              "--squash": 0, "--isolation": 1, "--cgroup-parent": 1,
              "--cache-from": 1, "--iidfile": 1, "--add-host": 1,
              "--ulimit": 1, "--cpuset-cpus": 1, "--shm-size": 1},
    "exec": {"--detach-keys": 1, "--privileged": 0},
    "start": {"--attach": 1, "--interactive": 0, "--detach-keys": 1},
    "attach": {"--detach-keys": 1, "--sig-proxy": 1},
    "stats": {"--no-trunc": 0},
    "images": {"--tree": 0, "--digests": 0},
    "ps": {"--tree": 0},
    "system df": {"--verbose": 0},
    "prune": {"--filter": 1},
    "rm": {"--link": 0},
    "container prune": {"--filter": 1},
    "pull": {"--quiet": 0},
    "push": {"--quiet": 0},
    "load": {"--quiet": 0},
    "save": {},
    "image load": {"--quiet": 0},
    "image save": {},
    "image push": {"--quiet": 0},
    "image pull": {"--quiet": 0},
}

# options that change container semantics: refused with an explanation
REFUSED = (
    (r"^--(memory|memory-swap|memory-reservation|memory-swappiness"
     r"|pids-limit|oom-kill-disable|oom-score-adj|blkio-weight"
     r"|blkio-weight-device|io-maxbandwidth|io-maxiops"
     r"|device-read-bps|device-write-bps|device-read-iops"
     r"|device-write-iops|device-cgroup-rule)$",
     "resource limits need cgroup delegation"),
    (r"^--(cpus|cpu-shares|cpu-period|cpu-quota|cpu-count|cpu-percent"
     r"|cpu-rt-period|cpu-rt-runtime|cpuset-mems)$",
     "CPU limits need cgroup delegation"),
    (r"^--(privileged|cap-add|cap-drop|group-add|sysctl)$",
     "privileges and capabilities need root"),
    (r"^--(ip|ip6|mac-address|link|link-local-ip|network-alias)$",
     "container networking is host-only"),
    (r"^--runtime$", "the execution mode is selected with --execmode"),
    (r"^--(checkpoint|checkpoint-dir)$", "checkpointing needs CRIU and root"),
    (r"^--read-only$", "a read-only root filesystem needs a mount namespace"),
    (r"^--tmpfs$", "tmpfs mounts need a mount namespace "
                   "(use -v /some/dir:/path instead)"),
)

# options accepted only for specific values: anything else is refused
ALLOWED_VALUES = {
    "--network": ("host", "none", "default", "bridge"),
    "--ipc": ("host", "private", "none", "shareable"),
    "--pid": ("host", "private"),
    "--uts": ("host", "private"),
    "--userns": ("host",),
    "--security-opt": ("no-new-privileges", "no-new-privileges:true",
                       "seccomp=unconfined", "apparmor=unconfined",
                       "label=disable"),
}

# short docker options of the tables above (udocker uses some shorts for its
# own options, so the mapping is per command page)
SHORT_TO_LONG = {
    "run": {"-m": "--memory", "-c": "--cpu-shares", "-a": "--attach",
            "-q": "--quiet"},
    "create": {"-m": "--memory", "-c": "--cpu-shares", "-a": "--attach",
               "-q": "--quiet"},
    "build": {"-q": "--quiet", "-m": "--memory", "-c": "--cpu-shares"},
}

GROUPS = ("container", "image", "system", "network", "volume", "manifest",
          "builder", "config", "secret", "node", "service", "stack", "swarm",
          "checkpoint", "plugin", "context")


def _command_span(argv):
    """Return (page, index of the first option) for a docker command line."""
    index = 1
    while index < len(argv):
        token = argv[index]
        if token.startswith("-"):
            index += 1
            continue
        page = token
        index += 1
        if token in GROUPS and index < len(argv) and \
                not argv[index].startswith("-"):
            page = token + " " + argv[index]
            index += 1
        return page, index
    return "", len(argv)


GROUP_ALIASES = {
    ("container", "ls"): "ps", ("container", "list"): "ps",
    ("container", "ps"): "ps", ("image", "ls"): "images",
    ("image", "list"): "images", ("system", "df"): "system df",
}


def _tables(page):
    """Return the ignored table for a page, group aliases included."""
    if page in IGNORED:
        return IGNORED[page]
    parts = page.split(" ", 1)
    if len(parts) == 2:
        alias = GROUP_ALIASES.get((parts[0], parts[1]))
        if alias and alias in IGNORED:
            return IGNORED[alias]
        return IGNORED.get(parts[1], {})
    return IGNORED.get(parts[0], {})


def _split(token):
    """Split '--flag=value' into ('--flag', 'value'); value None if absent."""
    if "=" in token:
        name, value = token.split("=", 1)
        return name, value
    return token, None


def rewrite(argv):
    """Rewrite a docker-style command line.

    Returns (argv, refusal, page) where refusal is a message to print before
    exiting with a non-zero status, or None when the line can be parsed as is.
    """
    page, index = _command_span(argv)
    if not page:
        return argv, None, page
    ignored = _tables(page)
    shorts = SHORT_TO_LONG.get(page, {})
    result = list(argv[:index])
    tail = list(argv[index:])
    pos = 0
    while pos < len(tail):
        token = tail[pos]
        if token == "--":                       # end of docker options
            pos += 1
            break
        if not token.startswith("-") or token == "-":
            break
        name, value = _split(token)
        name = shorts.get(name, name)
        if name in ALLOWED_VALUES:
            if value is None and pos + 1 < len(tail) and \
                    not tail[pos + 1].startswith("-"):
                value = tail[pos + 1]
                pos += 1                        # space separated value
            if value is not None and \
                    value.split(",")[0] in ALLOWED_VALUES[name]:
                pos += 1
                continue
            return result, "%s: only %s are available rootless" % (
                name, "/".join(ALLOWED_VALUES[name])), page
        if name in ignored:
            pos += 1
            if value is None and ignored[name] and pos < len(tail):
                pos += 1                        # space separated value
            continue
        reason = _refusal(name)
        if reason:
            return result, "%s: %s" % (name, reason), page
        result.append(token)
        pos += 1
    result.extend(tail[pos:])
    return result, None, page


def _refusal(name):
    """Return a refusal reason for a docker option, or None to keep it."""
    for pattern, reason in REFUSED:
        if re.match(pattern, name):
            return reason
    return None


def refusal_reason(name):
    """Public wrapper: the reason an option is refused, or an empty string"""
    return _refusal(name) or ""


def policy(page, long_flag):
    """How one docker option is treated: ignored, refused or supported."""
    if long_flag in ALLOWED_VALUES or long_flag in _tables(page):
        return "ignored"
    if _refusal(long_flag):
        return "refused"
    return "supported"
