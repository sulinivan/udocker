#!/usr/bin/env python3
"""Probe every `docker compose` option against `udocker compose`.

The ground truth is the docker-compose vX --help tree already dumped in
.manual-test/docker-cli-census.json (key "compose").  Every option of every page is
fed to `udocker compose` for real; the observed return code and the error
text decide the state, nothing is guessed:

  works     - the command accepted the option and exited 0
  accepted  - the option parsed, the command then failed for an unrelated
              reason (no such service, no container, ...)
  missing   - udocker rejected the option/command as unknown
  root-only - udocker reports that the option needs root privileges
  n-a       - udocker reports the option as not applicable to rootless

Probes are side effect free: they run in a throwaway directory in /tmp
with a compose file whose only image is a name that does not exist in the
repository, and they ask for a service that is not in the file, so every
command fails right after the argument parsing.  Each probe has a timeout.

Usage:
  TMPDIR=/tmp python3 utils/docker_compose_probe.py [--repo PATH] [--csv PATH]
              [--jobs N] [--timeout S] [--only PAGE ...] [--check] [--keep]
"""

import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CENSUS = os.path.join(HERE, os.pardir, ".manual-test",
                      "docker-cli-census.json")
DEFAULT_REPO = os.path.join(ROOT, ".manual-test", "repo")
DEFAULT_CSV = os.path.join(HERE, os.pardir, "docs",
                           "docker-compose-flags.csv")
VENV_PYTHON = os.path.join(ROOT, ".venv", "bin", "python")
DEFAULT_PYTHON = VENV_PYTHON if os.path.isfile(VENV_PYTHON) else \
    sys.executable

PROBE_IMAGE = "probe/absent-image:0"
MISSING_MARKERS = ("unknown option", "unknown compose command",
                   "unrecognized option", "syntax error",
                   "compose command expected", "not a docker compose command")
ROOT_MARKERS = ("requires root privileges",)
NA_MARKERS = ("not applicable to rootless udocker",)

# Positional arguments that make a page fail safely right after the option
# parsing, so no container is created, stopped or removed.
SAFE_ARGS = {
    "": ["config", "nosuchservice"],
    "attach": ["nosuchservice"],
    "bridge": ["convert"],
    "build": ["nosuchservice"],
    "commit": ["nosuchservice", "probe/image:0"],
    "config": ["nosuchservice"],
    "cp": ["nosuchservice:/tmp/x", "/tmp/y"],
    "create": ["nosuchservice"],
    "down": ["nosuchservice"],
    "events": ["nosuchservice"],
    "exec": ["nosuchservice", "true"],
    "export": ["nosuchservice"],
    "images": ["nosuchservice"],
    "kill": ["nosuchservice"],
    "logs": ["nosuchservice"],
    "ls": [],
    "pause": ["nosuchservice"],
    "port": ["nosuchservice", "80"],
    "ps": ["nosuchservice"],
    "publish": ["probe.invalid/app:0"],
    "pull": ["nosuchservice"],
    "push": ["nosuchservice"],
    "restart": ["nosuchservice"],
    "rm": ["nosuchservice"],
    "run": ["nosuchservice", "true"],
    "scale": ["nosuchservice=2"],
    "start": ["nosuchservice"],
    "stats": ["nosuchservice"],
    "stop": ["nosuchservice"],
    "top": ["nosuchservice"],
    "unpause": ["nosuchservice"],
    "up": ["nosuchservice"],
    "version": [],
    "volumes": ["nosuchservice"],
    "wait": ["nosuchservice"],
    "watch": ["nosuchservice"],
}

COMPOSE_YAML = """\
name: probe
services:
  app:
    image: %s
""" % PROBE_IMAGE

# Values used for options that take an argument.  Only values that the real
# implementation accepts are used, an invalid value would classify as a
# missing flag for the wrong reason.
VALUE_OVERRIDES = {
    "--ansi": "never",
    "--progress": "plain",
    "--parallel": "2",
    "--profile": "probe",
    "--project-name": "probe",
    "--project-directory": "@tmpdir",
    "--file": "@compose",
    "--env-file": "@envfile",
    "--output": "@outfile",
    "-o": "@outfile",
    "--format": "table",
    "--timeout": "3",
    "-t": "3",
    "--wait-timeout": "3",
    "--tail": "5",
    "-n": "5",
    "--index": "1",
    "--since": "1h",
    "--until": "1s",
    "--signal": "SIGTERM",
    "-s": "SIGTERM",
    "--rmi": "local",
    "--pull": "never",
    "--policy": "missing",
    "--scale": "app=2",
    "--memory": "64m",
    "-m": "64m",
    "--hash": "*",
    "--change": "CMD true",
    "-c": "CMD true",
    "--author": "probe",
    "-a": "probe",
    "--message": "probe",
    "--detach-keys": "ctrl-a",
    "--name": "probe",
    "--entrypoint": "/bin/true",
    "--user": "0",
    "-u": "0",
    "--workdir": "/",
    "-w": "/",
    "--volume": "/tmp:/probe",
    "-v": "/tmp:/probe",
    "--publish": "8080:80",
    "-p": "8080:80",
    "--build-arg": "A=1",
    "--env": "A=1",
    "-e": "A=1",
    "--label": "a=b",
    "-l": "a=b",
    "--cap-add": "NET_ADMIN",
    "--cap-drop": "MKNOD",
    "--filter": "status=running",
    "--status": "running",
    "--protocol": "tcp",
    "--attach": "app",
    "--no-attach": "app",
    "--ssh": "default",
    "--sbom": "true",
    "--provenance": "mode=max",
    "--oci-version": "v1",
    "--builder": "default",
}
FORMAT_BY_PAGE = {
    "": "json",
    "config": "json",
    "ps": "table",
    "images": "table",
    "ls": "table",
    "volumes": "table",
    "stats": "table",
    "version": "pretty",
}

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
SPACE_RE = re.compile(r"\s+")


def compose_page_options(census):
    """The (page, flag, arg) tuples of every docker compose option"""
    result = []
    for (page, node) in census.items():
        for option in node.get("options", []):
            result.append((page, option["long"], option.get("arg", "")))
            short = option.get("short") or ""
            if short:
                result.append((page, short, option.get("arg", "")))
    return result


def option_value(page, flag, arg, scratch):
    """A valid dummy value for an option, None for a boolean flag"""
    if not arg:
        return None
    if flag == "--format":
        return FORMAT_BY_PAGE.get(page, "table")
    value = VALUE_OVERRIDES.get(flag)
    if value is None:
        value = {"int": "1", "bytes": "64m", "scale": "app=2",
                 "filter": "status=running", "list": "probe",
                 "stringArray": "probe"}.get(arg, "probe")
    return make_path(value, scratch)


def make_path(value, scratch):
    """Resolve the @... placeholders of the dummy values"""
    if not value.startswith("@"):
        return value
    mapping = {
        "@tmpdir": scratch["dir"],
        "@compose": scratch["compose"],
        "@envfile": scratch["envfile"],
        "@outfile": os.path.join(scratch["dir"], "out.json"),
    }
    return mapping.get(value, value)


def build_command(repo, python, page, flag, arg, scratch):
    """The udocker command line of one probe"""
    value = option_value(page, flag, arg, scratch)
    flag_args = [flag] if value is None else [flag, value]
    argv = [python, "-m", "udocker.maincmd", "--repo=" + repo,
            "compose"]
    if page == "":
        argv.extend(flag_args)
        argv.extend(SAFE_ARGS[""])
    else:
        argv.append(page)
        argv.extend(flag_args)
        argv.extend(SAFE_ARGS.get(page, []))
    return argv


def classify(returncode, text):
    """Map the observed result to one of the states"""
    lowered = text.lower()
    if returncode == 0:
        return "works"
    if "traceback (most recent call last)" in lowered:
        return "error"
    if any(marker in lowered for marker in ROOT_MARKERS):
        return "root-only"
    if any(marker in lowered for marker in NA_MARKERS):
        return "n-a"
    if any(marker in lowered for marker in MISSING_MARKERS):
        return "missing"
    return "accepted"


def evidence(returncode, stdout, stderr, scratch):
    """One short, reproducible line of evidence"""
    text = (stderr or "").strip()
    if not text:
        text = ""
        for line in (stdout or "").splitlines():
            if line.strip():
                text = line.strip()
                break
    for (path, replacement) in ((scratch["dir"], "<tmp>"),
                                (scratch["compose"], "<compose>")):
        text = text.replace(path, replacement)
    text = ANSI_RE.sub("", text)
    text = SPACE_RE.sub(" ", text).strip()
    if len(text) > 160:
        text = text[:157] + "..."
    return "rc=%d: %s" % (returncode, text or "(no output)")


def run_probe(repo, python, page, flag, arg, scratch, timeout):
    """Run one probe and return its CSV row"""
    argv = build_command(repo, python, page, flag, arg, scratch)
    env = dict(os.environ)
    env["TMPDIR"] = "/tmp"
    env["DOCKER_CLI_HINTS"] = "false"
    try:
        proc = subprocess.run(argv, cwd=scratch["dir"], env=env,
                              capture_output=True, text=True,
                              timeout=timeout, check=False)
        (returncode, out, err) = (proc.returncode, proc.stdout, proc.stderr)
    except subprocess.TimeoutExpired as error:
        out = (error.stdout or "") if isinstance(error.stdout, str) else ""
        err = "probe timeout after %ss" % timeout
        returncode = 124
    except (OSError, ValueError) as error:
        out = ""
        err = "cannot run probe: %s" % error
        returncode = 125
    state = classify(returncode, out + "\n" + err)
    return {
        "page": page or "(global)",
        "flag": flag,
        "docker_arg": arg,
        "udocker_state": state,
        "evidence": evidence(returncode, out, err, scratch),
    }


def make_scratch():
    """A throwaway project directory under /tmp with a compose file"""
    directory = tempfile.mkdtemp(prefix="compose-probe-", dir="/tmp")
    compose = os.path.join(directory, "compose.yaml")
    with open(compose, "w") as handle:
        handle.write(COMPOSE_YAML)
    envfile = os.path.join(directory, "probe.env")
    with open(envfile, "w") as handle:
        handle.write("PROBE=1\n")
    return {"dir": directory, "compose": compose, "envfile": envfile}


def write_csv(path, rows):
    """Write the CSV table in census order"""
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("page,flag,docker_arg,udocker_state,evidence\n")
        for row in rows:
            fields = [row["page"], row["flag"], row["docker_arg"],
                      row["udocker_state"], row["evidence"]]
            handle.write(",".join(csv_field(field) for field in fields))
            handle.write("\n")


def csv_field(text):
    """Minimal CSV quoting"""
    text = str(text)
    if any(char in text for char in ',"\n'):
        return '"' + text.replace('"', '""') + '"'
    return text


def main(argv=None):
    """Run every probe and write the CSV table"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--csv", default=DEFAULT_CSV)
    parser.add_argument("--python", default=DEFAULT_PYTHON,
                        help="interpreter used to run udocker")
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 2))
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--only", action="append", default=[],
                        help="probe only this page (repeatable)")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 when an applicable flag is missing")
    parser.add_argument("--keep", action="store_true",
                        help="keep the throwaway project directory")
    options = parser.parse_args(argv)
    os.environ["TMPDIR"] = "/tmp"
    with open(CENSUS, "r", encoding="utf-8") as handle:
        census = json.load(handle)["compose"]
    if options.only:
        unknown = [page for page in options.only if page not in census]
        if unknown:
            parser.error("unknown page(s): %s" % ", ".join(unknown))
        census = {page: census[page] for page in options.only
                  if page in census}
    scratch = make_scratch()
    if options.keep:
        print("probe directory: %s" % scratch["dir"], file=sys.stderr)
    probes = compose_page_options(census)
    rows = []
    try:
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=max(1, options.jobs)) as pool:
            futures = [pool.submit(run_probe, options.repo, options.python,
                                   page, flag, arg, scratch,
                                   options.timeout)
                       for (page, flag, arg) in probes]
            for future in futures:
                rows.append(future.result())
    finally:
        if not options.keep:
            shutil.rmtree(scratch["dir"], ignore_errors=True)
    write_csv(options.csv, rows)
    counts = {}
    for row in rows:
        counts[row["udocker_state"]] = counts.get(row["udocker_state"], 0) + 1
    applicable = len(rows) - counts.get("root-only", 0) - counts.get("n-a", 0)
    missing = counts.get("missing", 0)
    errors = counts.get("error", 0)
    print("probed: %d options over %d pages" % (len(rows), len(census)))
    for state in ("works", "accepted", "missing", "root-only", "n-a",
                  "error"):
        print("  %-9s %4d" % (state, counts.get(state, 0)))
    share = (100.0 * missing / applicable) if applicable else 0.0
    print("missing among applicable: %d/%d (%.1f%%)"
          % (missing, applicable, share))
    print("written: %s" % options.csv)
    if options.check and (missing or errors):
        print("FAIL: missing=%d error=%d" % (missing, errors),
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
