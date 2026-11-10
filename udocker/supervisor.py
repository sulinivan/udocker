# -*- coding: utf-8 -*-
"""Per-user container supervisor built on runc/crun.
Detached containers are started by a monitor process (the normal
udocker run command) whose stdio goes to a log file. runc keeps the
container state, so start/stop/kill/exec/logs/wait work without root
and without a system daemon.
"""

import os
import signal
import subprocess
import sys
import time
import json
import re

from udocker.msg import Msg
from udocker.config import Config
from udocker.utils.runcenv import runc_container_id, runtime_env
from udocker.utils.containerpath import container_realpath


STATE_NAME = "state.json"
CONF_NAME = "supervisor.json"
LOG_NAME = os.path.join("logs", "container.log")


def log_path(container_dir):
    """Return the path of the container stdout/stderr log"""
    return os.path.join(container_dir, LOG_NAME)


def _read_json(path):
    """Read a JSON file, return {} on any problem"""
    try:
        with open(path, "r") as filep:
            return json.load(filep)
    except (IOError, OSError, ValueError, TypeError):
        return {}


def read_state(container_dir):
    """Return the state.json contents of a container"""
    return _read_json(os.path.join(container_dir, STATE_NAME))


def read_conf(container_dir):
    """Return the supervisor.json contents of a container"""
    return _read_json(os.path.join(container_dir, CONF_NAME))


def write_conf(container_dir, argv, log, rm=False):
    """Persist what is needed to start the container again"""
    conf = {
        "argv": list(argv),
        "log": log,
        "runc_id": runc_container_id(os.path.basename(container_dir)),
        "rm": bool(rm),
    }
    try:
        with open(os.path.join(container_dir, CONF_NAME), "w") as filep:
            json.dump(conf, filep)
    except (IOError, OSError, ValueError, TypeError):
        return False
    return True


def is_running(container_dir):
    """Is the container monitor process alive"""
    state = read_state(container_dir)
    if state.get("status") not in ("running", "paused"):
        return False
    return _pid_alive(state.get("pid", 0))


def write_state(container_dir, status, exitcode=None, ports=None, pid=None):
    """Record the execution state of a container for ps
    Published ports are preserved across updates when not given.
    """
    if not isinstance(container_dir, str) or not container_dir:
        return
    state = read_state(container_dir)
    state["status"] = status
    state["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                       time.gmtime())
    if status in ("running", "paused"):
        state["pid"] = pid if pid is not None else os.getpid()
    else:
        state.pop("pid", None)
    if exitcode is not None:
        state["exitcode"] = exitcode
    elif status != "exited":
        state.pop("exitcode", None)
    if ports is not None:
        state["ports"] = list(ports)
    try:
        with open(os.path.join(container_dir, STATE_NAME), "w") as filep:
            json.dump(state, filep)
    except (IOError, OSError, ValueError, TypeError):
        pass


def reconcile(container_dir):
    """Fix the state of a container whose monitor died without writing

    Rootless engines without a control channel (P/F/S) can be killed
    from outside; ps and wait must still report them as exited.
    """
    state = read_state(container_dir)
    if state.get("status") not in ("running", "paused"):
        return state
    if _pid_alive(state.get("pid", 0)):
        return state
    write_state(container_dir, "exited", 137)
    return read_state(container_dir)


def pause(container_dir):
    """Freeze the container process group with SIGSTOP (no cgroup needed)"""
    state = read_state(container_dir)
    if state.get("status") == "paused":
        return True
    if not is_running(container_dir):
        return False
    if signal_monitor(container_dir, "STOP") != 0:
        return False
    write_state(container_dir, "paused", ports=state.get("ports"),
                pid=state.get("pid"))
    return True


def unpause(container_dir):
    """Resume a paused container with SIGCONT"""
    state = read_state(container_dir)
    if state.get("status") != "paused":
        return False
    if signal_monitor(container_dir, "CONT") != 0:
        return False
    write_state(container_dir, "running", ports=state.get("ports"),
                pid=state.get("pid"))
    return True


def _popen_kwargs():
    """Make the monitor independent from the invoking shell"""
    if sys.version_info[0] >= 3:
        return {"start_new_session": True}
    return {"preexec_fn": os.setsid}


def _devnull():
    """A readable/writable /dev/null handle"""
    return open(os.devnull, "r+")


def _pid_alive(pid):
    """Is a process alive and not a zombie"""
    try:
        pid = int(pid)
        os.kill(pid, 0)
    except (OSError, ValueError, TypeError):
        return False
    try:
        with open("/proc/%d/stat" % pid, "r") as filep:
            data = filep.read()
        state = data.rsplit(")", 1)[1].split()[0]
    except (IOError, OSError, IndexError):
        return True
    return state != "Z"


def wait_running(container_dir, proc=None, timeout=15):
    """Wait until the monitor reports the container as running"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = read_state(container_dir)
        if state.get("status") == "running":
            if proc is not None:
                if (int(state.get("pid", 0)) == proc.pid and
                        _pid_alive(proc.pid)):
                    return True
            elif _pid_alive(state.get("pid", 0)):
                return True
        if proc is not None and proc.poll() is not None:
            return False
        time.sleep(0.1)
    return False


def spawn(container_id, container_dir, argv, truncate=True, timeout=15):
    """Start the monitor process for a container.
    argv is the udocker command line without the program name and
    without the detach option.
    """
    state_path = os.path.join(container_dir, STATE_NAME)
    try:
        os.remove(state_path)
    except OSError:
        pass
    log = log_path(container_dir)
    try:
        if not os.path.isdir(os.path.dirname(log)):
            os.makedirs(os.path.dirname(log))
        logf = open(log, "wb" if truncate else "ab")
    except (IOError, OSError) as error:
        Msg().err("Error: cannot open container log:", str(error))
        return False
    devnull = _devnull()
    cmd = [sys.executable, "-m", "udocker.maincmd"] + list(argv)
    kwargs = _popen_kwargs()
    try:
        proc = subprocess.Popen(cmd, stdin=devnull, stdout=logf, stderr=logf,
                                close_fds=True, **kwargs)
    except (OSError, ValueError) as error:
        Msg().err("Error: starting container monitor:", str(error))
        return False
    finally:
        devnull.close()
        logf.close()
    write_conf(container_dir, argv, log)
    if wait_running(container_dir, proc, timeout):
        return True
    try:
        proc.terminate()
    except OSError:
        pass
    Msg().err("Error: container did not start")
    _print_tail(log)
    return False


def _print_tail(path, lines=20):
    """Print the last lines of the container log"""
    try:
        with open(path, "r") as filep:
            content = filep.readlines()
    except (IOError, OSError):
        return
    for line in content[-lines:]:
        Msg().err(line.rstrip("\n"))


def _runc_call(container_dir, executable, args, topdir):
    """Invoke runc/crun with the container state root"""
    cmd = [executable, "--root", container_dir] + list(args)
    try:
        return subprocess.call(cmd, env=runtime_env(topdir),
                               stdout=Msg.chlderr, stderr=Msg.chlderr,
                               close_fds=True)
    except (OSError, ValueError) as error:
        Msg().err("Error: invoking runc:", str(error))
        return 1


def kill(container_dir, executable, sig="KILL", topdir=""):
    """Send a signal to the container init process"""
    rid = runc_container_id(os.path.basename(container_dir))
    status = _runc_call(container_dir, executable,
                        ["kill", rid, str(sig)], topdir)
    if status == 0:
        return 0
    return _signal_monitor(container_dir, sig)


def _signal_monitor(container_dir, sig):
    """Fallback: signal the monitor process itself"""
    state = read_state(container_dir)
    pid = state.get("pid", 0)
    try:
        number = getattr(signal, "SIG" + str(sig).replace("SIG", ""),
                         signal.SIGKILL)
        os.kill(int(pid), number)
    except (OSError, ValueError, TypeError, AttributeError):
        return 1
    return 0


def _signal_number(sig):
    """Translate a signal name or number into a signal number"""
    if re.match(r"^\d+$", str(sig)):
        return int(sig)
    name = str(sig).upper()
    if name.startswith("SIG"):
        name = name[3:]
    return getattr(signal, "SIG" + name, None)


def signal_monitor(container_dir, sig="KILL"):
    """Signal the monitor process group of a non runc container

    The monitor is spawned in its own session, so the container
    processes share its process group and all of them are signalled.
    """
    state = read_state(container_dir)
    try:
        pid = int(state.get("pid", 0))
    except (TypeError, ValueError):
        return 1
    number = _signal_number(sig)
    if number is None:
        Msg().err("Error: invalid signal:", sig)
        return 1
    try:
        os.killpg(os.getpgid(pid), number)
    except OSError:
        try:
            os.kill(pid, number)
        except OSError:
            return 1
    return 0


def _group_alive(pgid):
    """Is any process of the container process group still alive

    Zombies are ignored: a killed monitor stays a zombie until its
    parent reaps it and must not keep stop waiting.
    """
    if not pgid:
        return False
    try:
        entries = os.listdir("/proc")
    except OSError:
        return False
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open("/proc/%s/stat" % entry, "r") as filep:
                data = filep.read()
            fields = data.rsplit(")", 1)[1].split()
            state = fields[0]
            pgrp = int(fields[2])
        except (IOError, OSError, IndexError, ValueError):
            continue
        if pgrp == int(pgid) and state != "Z":
            return True
    return False


def _monitor_group(container_dir):
    """Process group of the container monitor, None when unknown"""
    state = read_state(container_dir)
    try:
        return os.getpgid(int(state.get("pid", 0)))
    except (OSError, TypeError, ValueError):
        return None


def wait_stopped(container_dir, timeout=10):
    """Wait until the monitor and its process group are gone"""
    pgid = _monitor_group(container_dir)
    deadline = time.time() + float(timeout)
    while time.time() < deadline:
        if not is_running(container_dir) and not _group_alive(pgid):
            return True
        time.sleep(0.1)
    return False


def stop_monitor(container_dir, timeout=10, sig="TERM"):
    """Stop a container whose engine has no runc control channel"""
    if not is_running(container_dir):
        reconcile(container_dir)
        return 0
    if signal_monitor(container_dir, sig) != 0:
        return 1
    if wait_stopped(container_dir, timeout):
        write_state(container_dir, "exited", 128 + 15)
        return 0
    signal_monitor(container_dir, "KILL")
    if wait_stopped(container_dir, 3):
        write_state(container_dir, "exited", 137)
        return 0
    Msg().err("Error: container did not stop")
    return 1


def stop(container_dir, executable, timeout=10, topdir="", sig="TERM"):
    """Stop a container: signal, wait, then kill"""
    if not is_running(container_dir):
        return 0
    kill(container_dir, executable, sig, topdir)
    deadline = time.time() + float(timeout)
    while time.time() < deadline:
        if not is_running(container_dir):
            return 0
        time.sleep(0.1)
    kill(container_dir, executable, "KILL", topdir)
    deadline = time.time() + 3
    while time.time() < deadline:
        if not is_running(container_dir):
            return 0
        time.sleep(0.1)
    return 1


def resolve_user(container_dir, user):
    """Resolve a docker style user/group into uid:gid for runc exec"""
    if not user:
        return None
    parts = str(user).split(":", 1)
    name = parts[0]
    group = parts[1] if len(parts) > 1 else ""
    uid = gid = None
    if re.match(r"^\d+$", name):
        uid = int(name)
    else:
        uid, gid = _find_user(container_dir, name)
        if uid is None:
            return None
    if group:
        if re.match(r"^\d+$", group):
            gid = int(group)
        else:
            gid = _find_group(container_dir, group)
            if gid is None:
                return None
    if gid is None:
        return str(uid)
    return "%d:%d" % (uid, gid)


def _auth_file(container_dir, name):
    """Locate /etc/passwd or /etc/group as the container sees it.
    R modes may bind host files instead of the container ones; if the
    path cannot be resolved inside the root fall back to the host file.
    """
    path = container_realpath(container_dir + "/ROOT", name)
    if path and os.path.isfile(path):
        return path
    if os.path.isfile(name):
        return name
    return ""


def _find_user(container_dir, name):
    """Find uid and gid by name in the container or host passwd"""
    path = _auth_file(container_dir, "/etc/passwd")
    try:
        with open(path, "r") as filep:
            for line in filep:
                fields = line.split(":")
                if fields[0] == name and len(fields) > 3:
                    return (int(fields[2]), int(fields[3]))
    except (IOError, OSError, ValueError):
        pass
    return (None, None)


def _find_group(container_dir, name):
    """Find gid by name in the container or host group"""
    path = _auth_file(container_dir, "/etc/group")
    try:
        with open(path, "r") as filep:
            for line in filep:
                fields = line.split(":")
                if fields[0] == name and len(fields) > 2:
                    return int(fields[2])
    except (IOError, OSError, ValueError):
        pass
    return None


def exec_command(container_dir, executable, command,
                 user=None, workdir=None, env_vars=None, tty=False,
                 topdir=""):
    """Execute a command inside a running container with runc exec"""
    rid = runc_container_id(os.path.basename(container_dir))
    args = [executable, "--root", container_dir, "exec"]
    if user:
        args.extend(["--user", user])
    if workdir:
        args.extend(["--cwd", workdir])
    for item in env_vars or []:
        args.extend(["--env", item])
    if tty:
        args.append("--tty")
    args.append(rid)
    args.extend(command)
    Msg().out("Debug: runc exec:", " ".join(args), l=Msg.DBG)
    try:
        return subprocess.call(args, env=runtime_env(topdir),
                               close_fds=True)
    except (OSError, ValueError) as error:
        Msg().err("Error: invoking runc exec:", str(error))
        return 1


def wait(container_dir, timeout=None):
    """Wait for the container to stop, return its exit code"""
    deadline = None
    if timeout:
        deadline = time.time() + float(timeout)
    while is_running(container_dir):
        if deadline is not None and time.time() > deadline:
            return None
        time.sleep(0.1)
    reconcile(container_dir)
    state = read_state(container_dir)
    return state.get("exitcode")


def logs(container_dir, follow=False, tail=None):
    """Print the container stdout/stderr log"""
    path = log_path(container_dir)
    try:
        filep = open(path, "rb")
    except (IOError, OSError):
        Msg().err("Error: no logs for this container")
        return 1
    try:
        content = filep.read()
        offset = len(content)
        if tail:
            lines = content.splitlines(True)
            content = b"".join(lines[-int(tail):])
        _write_bytes(content)
        if not follow:
            return 0
        while True:
            size = FileSize(path)
            if size > offset:
                filep.seek(offset)
                data = filep.read()
                offset += len(data)
                _write_bytes(data)
            if not is_running(container_dir) and FileSize(path) <= offset:
                return 0
            time.sleep(0.2)
    finally:
        filep.close()


def FileSize(path):
    """Size of a file, -1 when missing"""
    try:
        return os.path.getsize(path)
    except OSError:
        return -1


def _write_bytes(data):
    """Write bytes to stdout in a py2/py3 compatible way"""
    if not data:
        return
    try:
        sys.stdout.buffer.write(data)
    except AttributeError:
        sys.stdout.write(data)
    try:
        sys.stdout.flush()
    except (IOError, OSError):
        pass
