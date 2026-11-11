#!/usr/bin/env python3
"""Dump the ground-truth CLI surface of the real docker / docker compose.

The table in replica/cli-parity.md is generated from this dump, so the
"docker" column is never written from memory: it is parsed out of the
downloaded binaries' own --help output.

Usage:  python3 utils/docker_cli_census.py

The docker binaries are not vendored: download the static CLI and the compose
v2 binary into .manual-test/dockercli (or point DOCKER_BIN_DIR at a directory
that has docker/docker and docker-compose).
"""

import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.environ.get("DOCKER_BIN_DIR") or os.path.join(
    ROOT, ".manual-test", "dockercli")
DOCKER = os.path.join(BIN, "docker", "docker")
COMPOSE = os.path.join(BIN, "docker-compose")
OUT_DIR = os.path.join(ROOT, ".manual-test")

SECTION_RE = re.compile(r"^((?:[A-Z][A-Za-z]*\s+)*(?:Commands|Options)):\s*$")
CMD_RE = re.compile(r"^ {2}([a-z0-9][a-z0-9-]*)(\*?)\s{2,}(\S.*)$")
OPT_RE = re.compile(r"^ {2,6}(?:-(\w), )?--([\w-]+)(?:[ =]([\w\[\]<>|.]+))?"
                    r"(?:\s{2,}(.*))?$")
USAGE_RE = re.compile(r"^Usage:\s*(.+)$")
ALIAS_RE = re.compile(r"^Aliases:\s*$")


def parse_help(text):
    """Parse one --help page into usage, aliases, commands and options."""
    node = {"usage": "", "aliases": [], "commands": [], "options": []}
    section = None
    current = None
    for line in text.splitlines():
        match = USAGE_RE.match(line)
        if match:
            node["usage"] = match.group(1).strip()
            continue
        if ALIAS_RE.match(line):
            section = "aliases"
            continue
        match = SECTION_RE.match(line)
        if match:
            section = match.group(1).strip().lower()
            current = None
            continue
        if section == "aliases":
            node["aliases"].extend(part.strip()
                                   for part in line.split(",") if part.strip())
            continue
        if line.strip() == "":
            current = None
            continue
        if section and "commands" in section:
            match = CMD_RE.match(line)
            if match:
                node["commands"].append({"name": match.group(1),
                                         "plugin": bool(match.group(2)),
                                         "group": section,
                                         "desc": match.group(3).strip()})
                continue
        if section == "options":
            match = OPT_RE.match(line)
            if match and (match.group(1) or match.group(2)):
                current = {"short": "-" + match.group(1) if match.group(1) else "",
                           "long": "--" + match.group(2),
                           "arg": match.group(3) or "",
                           "desc": (match.group(4) or "").strip()}
                node["options"].append(current)
            elif current is not None and line.startswith(" " * 20):
                current["desc"] = (current["desc"] + " " + line.strip()).strip()
    return node


def run_help(binary, path):
    """Return (help_text, ok) for `<binary> <path...> --help`."""
    argv = [binary] + list(path) + ["--help"]
    env = dict(os.environ)
    env["DOCKER_CLI_HINTS"] = "false"
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, env=env,
                              timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return "error: %s" % error, False
    text = proc.stdout + proc.stderr
    if "is not a docker command" in text or "unknown command" in text:
        return text, False
    return text, proc.returncode == 0


def walk(binary, root_path, depth, out):
    """Depth-first dump of the help tree starting at root_path."""
    key = " ".join(root_path)
    text, ok = run_help(binary, root_path)
    if not ok:
        out[key] = {"path": list(root_path), "unavailable": True,
                    "raw": text.strip()[:400]}
        return
    node = parse_help(text)
    node["path"] = list(root_path)
    out[key] = node
    if depth > 0:
        for command in node["commands"]:
            if command["plugin"] and command["name"] in ("buildx", "compose",
                                                         "debug", "sbom"):
                continue
            walk(binary, list(root_path) + [command["name"]], depth - 1, out)


def main():
    out_path = os.path.join(OUT_DIR, "docker-cli-census.json")
    data = {"docker_version": subprocess.run(
                [DOCKER, "--version"], capture_output=True, text=True,
                check=False).stdout.strip(),
            "compose_version": subprocess.run(
                [COMPOSE, "version", "--short"], capture_output=True,
                text=True, check=False).stdout.strip(),
            "docker": {}, "compose": {}}
    walk(DOCKER, [], 2, data["docker"])
    walk(COMPOSE, [], 1, data["compose"])
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=1, sort_keys=True)
    total_opts = sum(len(node.get("options", []))
                     for group in ("docker", "compose")
                     for node in data[group].values())
    print("docker:   %d command pages, %d options" % (
        len(data["docker"]), total_opts))
    print("compose:  %d command pages" % len(data["compose"]))
    print("written:  %s" % out_path)


if __name__ == "__main__":
    sys.exit(main())
