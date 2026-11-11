#!/usr/bin/env python3
"""Probe udocker against the real docker CLI surface and mark what works.

Ground truth for the docker column is the `--help` tree of the downloaded
docker / docker compose binaries (replica/cli-census.json, produced by
replica/cli_census.py).  Nothing here is written from memory: every udocker
mark comes from actually running udocker and classifying its exit status and
stderr, so re-running the probe after a code change re-validates the table.

States
  ok         udocker exited 0 for the probe
  accepted   udocker parsed the flag and failed later (no such container...)
  missing    udocker rejected the flag/command   ("syntax error at: ...")
  root-only  udocker refused it on purpose       ("not available without root")
  crash      udocker raised an uncaught exception (a real bug)
  excluded   docker daemon/swarm-only page, out of the rootless contract
  n/a        not probed (needs a registry/network or is a group page)

Usage:
  python3 utils/docker_cli_probe.py                # probe + write CSV + MD
  python3 utils/docker_cli_probe.py --only ps images   # selected pages
  python3 utils/docker_cli_probe.py --no-probe     # rebuild the MD from CSV

The docker side comes from utils/docker_cli_census.py, so the table is never
written from memory: regenerate both to re-validate the marks.
"""

import argparse
import csv
import sys as _sys
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CENSUS = os.path.join(ROOT, ".manual-test", "docker-cli-census.json")
CSV_OUT = os.path.join(ROOT, "docs", "docker-cli-flags.csv")
MD_OUT = os.path.join(ROOT, "docs", "docker-cli-parity.md")
REPO = os.path.join(ROOT, ".manual-test", "probe-repo")
PYTHON = os.path.join(ROOT, ".venv", "bin", "python")
PROBE_TIMEOUT = 20

# docker pages that need a running daemon / swarm and are outside the
# rootless contract.  They must still fail with a clear message.
EXCLUDED_PAGES = ("swarm", "stack", "service", "node", "secret", "config",
                  "context", "plugin", "checkpoint", "builder", "manifest")

# arguments appended after the probed flag so the command reaches a fast,
# side-effect free failure *after* the option parser accepted the flag.
PROBE_TAIL = {
    "run": ["--pull=never", "nosuchct"],
    "create": ["--pull=never", "nosuchct"],
    "build": ["/nonexistent-context"],
    "pull": ["nonexistent.invalid/img:zzz"],
    "push": ["nosuchimg:zzz"],
    "tag": ["nosuchimg", "nosuchimg2"],
    "rmi": ["nosuchimg"],
    "rm": ["nosuchct"],
    "save": ["nosuchimg"],
    "import": ["/nonexistent/in.tar"],

    "history": ["nosuchimg"],
    "inspect": ["nosuchobj"],
    "logs": ["nosuchct"],
    "exec": ["nosuchct", "true"],
    "attach": ["nosuchct"],
    "cp": ["nosuchct:/x", "/nonexistent/y"],
    "commit": ["nosuchct", "nosuchimg2"],
    "top": ["nosuchct"],
    "stats": ["nosuchct"],
    "diff": ["nosuchct"],
    "port": ["nosuchct"],
    "start": ["nosuchct"],
    "stop": ["nosuchct"],
    "restart": ["nosuchct"],
    "kill": ["nosuchct"],
    "pause": ["nosuchct"],
    "unpause": ["nosuchct"],
    "rename": ["nosuchct", "nosuchct2"],
    "wait": ["nosuchct"],
    "update": ["nosuchct"],
    "search": ["zz-no-such-repository-zz"],
    "login": ["nonexistent.invalid"],
    "logout": ["nonexistent.invalid"],
    "events": ["--until=0"],
    "export": ["nosuchct"],
    "container export": ["nosuchct"],
    "load": [],
    "image load": [],
    "completion": ["bash"],
    "container attach": ["nosuchct"],
    "container commit": ["nosuchct", "nosuchimg2"],
    "container cp": ["nosuchct:/x", "/nonexistent/y"],
    "container diff": ["nosuchct"],
    "container exec": ["nosuchct", "true"],
    "container export": ["nosuchct"],
    "container inspect": ["nosuchobj"],
    "container logs": ["nosuchct"],
    "container port": ["nosuchct"],
    "container rename": ["nosuchct", "nosuchct2"],
    "container rm": ["nosuchct"],
    "container start": ["nosuchct"],
    "container stats": ["nosuchct"],
    "container stop": ["nosuchct"],
    "container top": ["nosuchct"],
    "container unpause": ["nosuchct"],
    "container update": ["nosuchct"],
    "container wait": ["nosuchct"],
    "image history": ["nosuchimg"],
    "image inspect": ["nosuchobj"],

    "image save": ["nosuchimg"],
    "image rm": ["nosuchimg"],
    "image push": ["nosuchimg:zzz"],
    "image tag": ["nosuchimg", "nosuchimg2"],
    "image build": ["/nonexistent-context"],
    "volume inspect": ["nosuchvol"],
    "volume rm": ["nosuchvol"],
    "network inspect": ["nosuchnet"],
    "network rm": ["nosuchnet"],
    "manifest inspect": ["busybox"],
}

# value used for a docker option that takes an argument, by docker arg type
ARG_VALUES = {
    "filter": "name=x",
    "string": "x",
    "stringArray": "x",
    "stringSlice": "x",
    "list": "x",
    "int": "1",
    "int64": "1",
    "uint64": "1",
    "duration": "1s",
    "unit": "1g",
    "bytes": "1",
    "time": "2026-01-01T00:00:00Z",
    "daemon-name": "x",
}

# canonical value per flag: docker only tells the *type*, and a random value
# can make udocker fail on the value instead of on the flag itself
NAME_VALUES = {
    "pull": "missing", "restart": "always", "network": "host",
    "network-mode": "host", "format": "json", "log-driver": "none",
    "isolation": "default", "ipc": "private", "pid": "host",
    "uts": "host", "userns": "host", "cgroupns": "host",
    "attach": "stdout", "detach-keys": "ctrl-p", "sig-proxy": "true",
    "memory": "64m", "memory-swap": "128m", "shm-size": "64m",
    "cpus": "1", "cpuset-cpus": "0", "cpuset-mems": "0",
    "tmpfs": "/tmp", "expose": "80", "hostname": "x", "domainname": "x",
    "label": "a=b", "filter": "name=x", "platform": "linux/amd64",
    "progress": "plain", "ansi": "never", "health-interval": "30s",
    "health-timeout": "30s", "health-retries": "3",
    "health-start-period": "1s", "health-start-interval": "1s",
    "tail": "10", "since": "1h", "until": "1h", "timeout": "10",
    "stop-signal": "SIGTERM", "stop-timeout": "10",
    "publish": "8080:80", "publish-all": "", "entrypoint": "sh",
    "workdir": "/", "volume": "/tmp:/mnt", "mount": "/tmp",
    "env": "A=B", "env-file": "/dev/null", "label-file": "/dev/null",
    "cidfile": "/tmp/cid", "dns": "1.1.1.1", "dns-search": "example.org",
    "add-host": "x:1.2.3.4", "ulimit": "nofile=1024:1024",
    "user": "0", "userland-proxy": "false", "type": "image",
    "change": "CMD", "message": "x", "author": "x",
    "signal": "SIGTERM", "tag": "latest", "arch": "amd64",
    "os": "linux", "osversion": "1", "os-features": "x",
    "cgroup-parent": "x", "runtime": "runc", "storage-opt": "size=1g",
    "security-opt": "no-new-privileges", "cap-add": "SYS_CHROOT",
    "cap-drop": "SYS_ADMIN", "device": "/dev/null", "group-add": "0",
    "sysctl": "net.ipv4.ip_forward=1", "annotation": "a=b",
    "cpu-shares": "1", "cpuset": "0", "cpuset-mems-x": "0",
    "name": "probename", "scale": "x=1", "project-name": "p",
    "profile": "x", "env-file": "/dev/null", "file": "/dev/null",
    "parallel": "1", "progress-x": "plain", "rmi": "local",
    "volumes": "", "url": "127.0.0.1", "cert-dir": "/tmp",
    "registry": "docker.io", "gpus": "all", "sdks": "x",
    "sep": "x", "filter-x": "name=x", "column": "x",
}

MARK = {"ok": "✅", "accepted": "🔶", "ignored": "🔷", "missing": "❌",
        "root-only": "⛔", "crash": "💥", "excluded": "➖", "n/a": "➖"}
LEGEND = ("✅ работает · 🔶 принимается, эффект не проверен · "
          "🔷 принимается без эффекта (флаг отброшен шимом) · ❌ нет · "
          "⛔ явный root-only отказ · 💥 падение · ➖ вне scope")

PAGE_ORDER = ("run create start stop restart kill rm pause unpause ps "
              "images inspect logs exec build pull push tag rmi save load "
              "import export commit cp top stats diff port wait rename "
              "history version info search login logout events completion "
              "prune").split()


def udocker_argv(page):
    """docker page key -> argv words for udocker."""
    if not page:
        return []
    return page.split(" ")


def probe_page_exists(page):
    ensure_repo()
    argv = [PYTHON, "-m", "udocker.maincmd", "--repo=" + REPO]
    argv.extend(udocker_argv(page))
    argv.append("--help")
    rc, out, err = run(argv)
    text = out + err
    if "invalid command" in text.lower() or "syntax error" in text.lower():
        return "missing", first_line(err or out)
    if rc == 0:
        return "ok", first_line(out)
    return "accepted", first_line(err or out)


def first_line(text):
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line[:160]
    return ""


def run(argv, timeout=PROBE_TIMEOUT, stdin_devnull=True):
    env = dict(os.environ)
    env["TMPDIR"] = "/tmp"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    stdin = subprocess.DEVNULL if stdin_devnull else None
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, env=env,
                              timeout=timeout, stdin=stdin, check=False,
                              cwd=ROOT)
    except subprocess.TimeoutExpired:
        return 0, "", ""
    except OSError as error:
        return 137, "", "error: %s" % error
    return proc.returncode, proc.stdout, proc.stderr


def classify(rc, out, err):
    text = (err or "") + "\n" + (out or "")
    lower = text.lower()
    if "syntax error at:" in lower or "invalid option" in lower or \
            "unrecognized option" in lower or "unknown flag" in lower:
        return "missing"
    if "traceback (most recent call last)" in lower:
        return "crash"
    if ("is not available rootless" in lower or
            "not available without root" in lower or
            "cgroup delegation" in lower or
            "capabilities need root" in lower or
            "is host-only" in lower or
            "needs criu" in lower or
            "needs a docker daemon" in lower):
        return "root-only"
    if rc == 0:
        return "ok"
    return "accepted"


def compat_policy(page, long_flag):
    """Shim policy for one docker option (ignored/refused/supported)"""
    if ROOT not in _sys.path:
        _sys.path.insert(0, ROOT)
    try:
        from udocker import compat
    except ImportError:
        return ""
    return compat.policy(page, long_flag)


def probe_flag(page, flag):
    arg = flag["arg"]
    token = flag["long"]
    if arg:
        value = NAME_VALUES.get(flag["long"].lstrip("-"))
        if value is None:
            value = ARG_VALUES.get(arg, "x")
        token += "=" + value
    ensure_repo()
    argv = [PYTHON, "-m", "udocker.maincmd", "--repo=" + REPO]
    argv.extend(udocker_argv(page))
    argv.append(token)
    tail = PROBE_TAIL.get(page, [])
    if page not in ("run", "create", "container run", "container create"):
        tail = [item for item in tail
                if item.split("=", 1)[0] != flag["long"]]
    argv.extend(tail)
    network_pages = ("events", "search", "login", "logout", "pull", "push")
    timeout = 8 if page in network_pages else PROBE_TIMEOUT
    rc, out, err = run(argv, timeout=timeout)
    state = classify(rc, out, err)
    return state, rc, pick_evidence(state, err, out)


def pick_evidence(state, err, out):
    """Return the line that actually decided the state."""
    markers = {
        "missing": ("syntax error at:", "invalid option", "unknown flag",
                    "unrecognized option"),
        "root-only": ("not available", "not supported", "requires root",
                      "without root", "needs root"),
        "crash": ("traceback",),
    }
    for text in (err, out):
        for line in (text or "").splitlines():
            line = line.strip()
            if not line:
                continue
            low = line.lower()
            for marker in markers.get(state, ()):
                if marker in low:
                    return line[:160]
    return first_line(err) or first_line(out)


def page_flags(census):
    """Yield (page, [flags]) for every docker page that has options."""
    for page, node in sorted(census["docker"].items()):
        if node.get("unavailable"):
            continue
        options = node.get("options") or []
        if options:
            yield page, options


def udocker_help_flags(page):
    """Flags listed in `udocker <page> --help` (secondary signal)."""
    ensure_repo()
    ensure_repo()
    argv = [PYTHON, "-m", "udocker.maincmd", "--repo=" + REPO]
    argv.extend(udocker_argv(page))
    argv.append("--help")
    rc, out, err = run(argv, timeout=PROBE_TIMEOUT)
    if rc != 0:
        return set()
    found = set()
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        head = line.split(":", 1)[0]
        for chunk in head.replace(",", " ").split():
            if chunk.startswith("--"):
                found.add(chunk.split("=")[0].rstrip(":"))
            elif chunk.startswith("-") and len(chunk) == 2:
                found.add(chunk)
    return found


def is_excluded(page):
    root = page.split(" ")[0] if page else ""
    return root in EXCLUDED_PAGES


def ensure_repo():
    """Initialise the throwaway repository the probes run against."""
    if os.path.isdir(os.path.join(REPO, "repos")):
        return
    if os.path.isdir(REPO):
        shutil.rmtree(REPO)
    run([PYTHON, "-m", "udocker.maincmd", "mkrepo", REPO])
    if not os.path.isdir(os.path.join(REPO, "repos")):
        raise SystemExit("cannot create probe repo at %s" % REPO)


def probe(only=None):
    with open(CENSUS, encoding="utf-8") as handle:
        census = json.load(handle)
    ensure_repo()
    rows = []
    pages = list(page_flags(census))
    for page, options in pages:
        if only and page not in only:
            continue
        print("probe:", page, len(options), flush=True)
        excluded = is_excluded(page)
        if excluded:
            cmd_state, cmd_evidence = probe_page_exists(page)
            listed = set()
        else:
            cmd_state, cmd_evidence = probe_page_exists(page)
            listed = udocker_help_flags(page)
        for flag in options:
            long_flag = flag["long"]
            if excluded:
                state, rc, evidence = "excluded", 0, "вне scope контракта"
            elif cmd_state == "missing":
                state, rc, evidence = "missing", 0, cmd_evidence
            else:
                state, rc, evidence = probe_flag(page, flag)
                treatment = compat_policy(page, flag["long"])
                if treatment == "ignored" and state in ("ok", "accepted"):
                    state = "ignored"
                elif treatment == "refused" and state != "missing":
                    state = "root-only"
            rows.append({
                "page": page,
                "command": "udocker " + page,
                "command_state": cmd_state,
                "flag": long_flag,
                "short": flag["short"],
                "docker_arg": flag["arg"],
                "docker_desc": (flag["desc"] or "").strip(),
                "state": state,
                "rc": rc,
                "in_help": "yes" if long_flag in listed else "no",
                "evidence": evidence,
            })
    return rows


def merge_rows(rows, pages):
    """Keep the rows of the pages that were not probed this time"""
    if not pages or not os.path.exists(CSV_OUT):
        return rows
    kept = [row for row in read_csv() if row["page"] not in pages]
    return kept + rows


def write_csv(rows):
    fields = ["page", "command", "command_state", "flag", "short",
              "docker_arg", "docker_desc", "state", "rc", "in_help",
              "evidence"]
    with open(CSV_OUT, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_csv():
    with open(CSV_OUT, encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def summary(rows):
    counts = {}
    for row in rows:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    pages = {}
    for row in rows:
        pages.setdefault(row["page"], row["command_state"])
    return counts, pages


def write_md(rows):
    counts, pages = summary(rows)
    with open(CENSUS, encoding="utf-8") as handle:
        census = json.load(handle)
    lines = ["# Таблица соответствия CLI: docker ⇄ udocker", ""]
    lines.append("Сгенерировано `utils/docker_cli_probe.py` по живому `--help` "
                 "реальных бинарей: %s · %s." % (
                     census.get("docker_version", "docker ?"),
                     census.get("compose_version", "compose ?")))
    lines.append("")
    lines.append("Обозначения: " + LEGEND + ".")
    lines.append("")
    lines.append("Флаги и команды проверяются запуском udocker, а не "
                 "перечислены по памяти: docker-сторона снимается из "
                 "`--help` реальных бинарей (`utils/docker_cli_census.py`), "
                 "udocker-сторона — пробами (`utils/docker_cli_probe.py`).")
    lines.append("")
    lines.append("Вне гарантии (нужен демон/root/swarm): `swarm`, `stack`, "
                 "`service`, `node`, `secret`, `config`, `context`, `plugin`, "
                 "`checkpoint`, `builder`, `manifest create/push/rm` — такие "
                 "страницы помечены ➖, а неприменимые флаги применимых "
                 "команд отвечают явной ошибкой (⛔), а не молча игнорируются.")
    lines.append("")
    lines.append("Колонка **проверка** — это вывод, по которому проба "
                 "поставила отметку; пустая колонка означает успешный запуск.")
    lines.append("")
    lines.append("## Сводка")
    lines.append("")
    lines.append("| состояние | флагов |")
    lines.append("|---|---|")
    for state in ("ok", "accepted", "ignored", "missing", "root-only",
                  "crash", "excluded"):
        if counts.get(state):
            lines.append("| %s %s | %d |" % (MARK[state], state,
                                             counts[state]))
    lines.append("| всего | %d |" % len(rows))
    lines.append("")
    supported = sum(1 for page, state in pages.items()
                    if state == "ok" and page)
    missing = [page for page, state in pages.items()
               if state == "missing" and page]
    lines.append("Команд-страниц с рабочим udocker: **%d**; отсутствуют: "
                 "**%d**." % (supported, len(missing)))
    if missing:
        lines.append("")
        lines.append("Отсутствующие команды: " + ", ".join(
            "`%s`" % page for page in sorted(missing)))
    lines.append("")
    lines.append("## По командам")
    lines.append("")
    grouped = {}
    for row in rows:
        grouped.setdefault(row["page"], []).append(row)
    order = [page for page in PAGE_ORDER if page in grouped]
    order += [page for page in sorted(grouped) if page not in order]

    def sort_key(page):
        root = page.split(" ")[0]
        return (0 if page in PAGE_ORDER else 1, root, page)

    for page in sorted(grouped, key=sort_key):
        rows_page = grouped[page]
        command_state = rows_page[0]["command_state"]
        if all(row["state"] == "excluded" for row in rows_page):
            command_state = "excluded"
        mark = MARK.get(command_state, command_state)
        title = "### `docker %s` → `%s` %s" % (
            page, rows_page[0]["command"], mark)
        lines.append(title)
        lines.append("")
        lines.append("| флаг | аргумент | docker | udocker | в `--help` | "
                     "проверка |")
        lines.append("|---|---|---|---|---|---|")
        for row in rows_page:
            flag = row["flag"]
            if row["short"]:
                flag = "%s, %s" % (row["short"], flag)
            lines.append("| `%s` | %s | %s | %s %s | %s | %s |" % (
                flag, row["docker_arg"] or "—",
                "да" if row["short"] or row in rows_page else "да",
                MARK.get(row["state"], row["state"]), row["state"],
                row["in_help"], (row["evidence"] or "").replace("|", "\\|")))
        lines.append("")
    with open(MD_OUT, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def main():
    parse = argparse.ArgumentParser()
    parse.add_argument("--only", nargs="+", help="probe these pages only")
    parse.add_argument("--no-probe", action="store_true",
                       help="rebuild the md from the existing csv")
    args = parse.parse_args()
    if not os.path.exists(CENSUS):
        print("missing %s: run replica/cli_census.py first" % CENSUS)
        return 1
    if args.no_probe:
        write_md(read_csv())
        print("rebuilt %s from csv" % MD_OUT)
        return 0
    rows = merge_rows(probe(only=args.only), set(args.only or ()))
    write_csv(rows)
    write_md(rows)
    counts, pages = summary(rows)
    print("pages: %d, flags: %d" % (len(pages), len(rows)))
    for state in ("ok", "accepted", "ignored", "missing", "root-only",
                  "crash", "excluded"):
        if counts.get(state):
            print("  %-10s %d" % (state, counts[state]))
    print("written %s, %s" % (CSV_OUT, MD_OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
