# -*- coding: utf-8 -*-
"""Docker-like extras: top, stats, diff, port, system df and prune.

The functions are independent from the CLI: they receive resolved
container data, print through Msg().out and return 0 or 1.  Pure
helpers (parsers, formatters, selectors) are kept apart so that the
unit tests can feed fixtures instead of real /proc or real containers.
"""

import os
import sys
import time
import tarfile
import posixpath

from udocker.msg import Msg
from udocker import supervisor


STATUS_OK = 0
STATUS_ERROR = 1

STATS_INTERVAL = 0.3

# ROOT entries that udocker adds itself or binds at runtime
ROOT_IGNORE = ("dev", "proc", "sys", ".udocker", ".bind_host_files",
               ".bind_orig_files")
# PRoot leaves its tmp dirs in the container /tmp
TMP_IGNORE_PREFIX = "prooted-"

SIZE_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")

TOP_FMT = "%-8.8s %6.6s %6.6s %3.3s %-8.8s %-8.8s %8.8s %-45.45s"
STATS_FMT = "%-12.12s %-20.20s %7.7s %21.21s %7.7s %5.5s"
DF_FMT = "%-15.15s %8.8s %8.8s %12.12s %18.18s"


# ---------------------------------------------------------------- helpers


def _decode(data):
    """Bytes to text keeping py2 str working"""
    if isinstance(data, bytes):
        return data.decode("utf-8", "replace")
    return data


def _read_file(path):
    """Read a file in binary mode, empty bytes on any error"""
    try:
        with open(path, "rb") as filep:
            return filep.read()
    except (IOError, OSError):
        return b""


def _read_text(path):
    """Read a small UTF-8 text file, empty string on any error"""
    return _decode(_read_file(path))


def _int_field(fields, position):
    """Safe integer extraction from a list of strings"""
    try:
        return int(fields[position])
    except (IndexError, TypeError, ValueError):
        return 0


def clock_ticks():
    """System clock ticks per second used by /proc/<pid>/stat"""
    try:
        return int(os.sysconf("SC_CLK_TCK")) or 100
    except (AttributeError, OSError, TypeError, ValueError):
        return 100


def read_uptime():
    """Seconds since boot, 0 when /proc/uptime is unreadable"""
    fields = _read_text("/proc/uptime").split()
    try:
        return float(fields[0])
    except (IndexError, TypeError, ValueError):
        return 0.0


def mem_total_bytes():
    """Host MemTotal in bytes, 0 when unknown"""
    for line in _read_text("/proc/meminfo").splitlines():
        if line.startswith("MemTotal:"):
            fields = line.split()
            return _int_field(fields, 1) * 1024
    return 0


def format_size(num):
    """Format a byte count with 1024 based units (B, KB, MB, GB)"""
    try:
        num = float(num)
    except (TypeError, ValueError):
        return "0B"
    if num < 0:
        num = 0
    idx = 0
    while num >= 1024.0 and idx < len(SIZE_UNITS) - 1:
        num /= 1024.0
        idx += 1
    if idx == 0:
        return "%dB" % int(round(num))
    return "%.2f%s" % (num, SIZE_UNITS[idx])


def format_seconds(seconds):
    """Format CPU time like ps TIME: [D-]HH:MM:SS or MM:SS"""
    try:
        total = int(float(seconds))
    except (TypeError, ValueError):
        total = 0
    if total < 0:
        total = 0
    (days, rest) = divmod(total, 86400)
    (hours, rest) = divmod(rest, 3600)
    (minutes, secs) = divmod(rest, 60)
    if days:
        return "%d-%02d:%02d:%02d" % (days, hours, minutes, secs)
    if hours:
        return "%d:%02d:%02d" % (hours, minutes, secs)
    return "%d:%02d" % (minutes, secs)


# ------------------------------------------------------------- /proc parse


def parse_proc_stat(data):
    """Parse /proc/<pid>/stat; comm may contain spaces and parentheses"""
    data = _decode(data)
    if not data:
        return {}
    left = data.find("(")
    right = data.rfind(")")
    if left < 0 or right <= left:
        return {}
    try:
        pid = int(data[:left].strip())
    except ValueError:
        return {}
    fields = data[right + 1:].split()
    info = {"pid": pid,
            "comm": data[left + 1:right],
            "state": fields[0] if fields else "-",
            "ppid": _int_field(fields, 1),
            "tty": _int_field(fields, 4),
            "utime": _int_field(fields, 11),
            "stime": _int_field(fields, 12),
            "starttime": _int_field(fields, 19)}
    return info


def parse_proc_status(data):
    """Parse the Uid and VmRSS fields of /proc/<pid>/status"""
    info = {}
    for line in _decode(data).splitlines():
        if ":" not in line:
            continue
        (key, value) = line.split(":", 1)
        if key == "Uid":
            fields = value.split()
            info["uid"] = fields[0] if fields else "-"
        elif key == "VmRSS":
            info["rss_kb"] = _int_field(value.split(), 0)
    return info


def parse_proc_cmdline(data):
    """Split /proc/<pid>/cmdline into an argument list"""
    data = _decode(data)
    if not data:
        return []
    return [part for part in data.rstrip("\0").split("\0") if part]


def scan_procs():
    """One snapshot of the visible processes keyed by pid"""
    procs = {}
    try:
        entries = os.listdir("/proc")
    except (IOError, OSError):
        return procs
    for name in entries:
        if not name.isdigit():
            continue
        pid = int(name)
        stat = parse_proc_stat(_read_file("/proc/%s/stat" % name))
        if not stat:
            continue
        status = parse_proc_status(_read_file("/proc/%s/status" % name))
        stat["uid"] = status.get("uid", "-")
        stat["rss_kb"] = status.get("rss_kb", 0)
        stat["cmd"] = parse_proc_cmdline(_read_file("/proc/%s/cmdline" % name))
        procs[pid] = stat
    return procs


def proc_tree(procs, root_pid):
    """Pids of root_pid and all its descendants, sorted"""
    children = {}
    for (pid, info) in procs.items():
        children.setdefault(info.get("ppid", 0), []).append(pid)
    result = []
    visited = set()
    queue = [root_pid]
    while queue:
        pid = queue.pop(0)
        if pid in visited:
            continue
        visited.add(pid)
        if pid in procs:
            result.append(pid)
        queue.extend(sorted(children.get(pid, [])))
    return sorted(result)


def format_tty(tty_nr):
    """Render a /proc/<pid>/stat tty_nr as ps would"""
    try:
        number = int(tty_nr)
    except (TypeError, ValueError):
        return "-"
    if number == 0:
        return "-"
    try:
        major = os.major(number)
        minor = os.minor(number)
    except (AttributeError, TypeError, ValueError):
        return str(number)
    if 136 <= major <= 143:
        return "pts/%d" % ((major - 136) * 256 + minor)
    if major == 4:
        return "tty%d" % minor
    return "%d:%d" % (major, minor)


def top_rows(procs, root_pid, ps_args=None, tck=100, uptime=0.0):
    """Data rows of docker top for a fixture/dict of processes"""
    rows = []
    boot_time = time.time() - uptime if uptime else 0.0
    for pid in proc_tree(procs, root_pid):
        info = procs[pid]
        utime = info.get("utime", 0)
        stime = info.get("stime", 0)
        starttime = info.get("starttime", 0)
        cpu_seconds = (utime + stime) / float(tck) if tck else 0.0
        lifetime = uptime - (starttime / float(tck)) if tck else 0.0
        percent = 0
        if lifetime > 0:
            percent = int(round(cpu_seconds * 100.0 / lifetime))
        start_clock = "-"
        if boot_time and starttime:
            start_clock = time.strftime(
                "%H:%M", time.localtime(boot_time + starttime / float(tck)))
        if ps_args:
            cmd = " ".join(info.get("cmd") or []) or info.get("comm", "-")
        else:
            cmd = info.get("comm", "-") or "-"
        rows.append((str(info.get("uid", "-")), str(pid),
                     str(info.get("ppid", 0)), str(percent), start_clock,
                     format_tty(info.get("tty", 0)),
                     format_seconds(cpu_seconds), cmd))
    return rows


# ------------------------------------------------------------------- top


def _state_pid(state):
    """Monitor pid from a state.json dict"""
    try:
        return int(state.get("pid", 0))
    except (AttributeError, TypeError, ValueError):
        return 0


def _is_running(container_dir):
    """supervisor.is_running without exceptions"""
    try:
        return bool(supervisor.is_running(container_dir))
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def print_top(container_dir, container_id, ps_args=None):
    """Print the processes of a container like docker top"""
    state = supervisor.read_state(container_dir)
    pid = _state_pid(state)
    if not pid or not _is_running(container_dir):
        Msg().err("Error: container is not running:", container_id)
        return STATUS_ERROR
    procs = scan_procs()
    if pid not in procs:
        Msg().err("Error: cannot read the process table of:", container_id)
        return STATUS_ERROR
    tck = clock_ticks()
    rows = top_rows(procs, pid, ps_args, tck, read_uptime())
    Msg().out(TOP_FMT % ("UID", "PID", "PPID", "C", "STIME", "TTY",
                         "TIME", "CMD"))
    for row in rows:
        Msg().out(TOP_FMT % row)
    return STATUS_OK


# ----------------------------------------------------------------- stats


def cpu_percent(old_jiffies, new_jiffies, elapsed, tck):
    """CPU usage percentage between two samples"""
    if elapsed <= 0 or tck <= 0:
        return 0.0
    delta = new_jiffies - old_jiffies
    if delta < 0:
        delta = 0
    return delta * 100.0 / (tck * elapsed)


def total_jiffies(procs, pids):
    """Sum of user and system jiffies of the given pids"""
    total = 0
    for pid in pids:
        info = procs.get(pid, {})
        total += info.get("utime", 0) + info.get("stime", 0)
    return total


def total_rss_kb(procs, pids):
    """Sum of resident memory in kB of the given pids"""
    total = 0
    for pid in pids:
        total += procs.get(pid, {}).get("rss_kb", 0)
    return total


def container_names(container_dir):
    """Comma separated names linked to a container directory"""
    parent = os.path.dirname(container_dir)
    target = os.path.basename(container_dir)
    names = []
    try:
        entries = os.listdir(parent)
    except (IOError, OSError):
        return ""
    for name in entries:
        path = os.path.join(parent, name)
        if not os.path.islink(path):
            continue
        try:
            link = os.readlink(path)
        except (IOError, OSError):
            continue
        if os.path.basename(link) == target:
            names.append(name)
    return ",".join(sorted(names))


def print_stats(containers):
    """Print one resource snapshot for all containers"""
    entries = []
    for item in containers or []:
        try:
            (container_id, container_dir) = item
        except (TypeError, ValueError):
            continue
        entries.append((container_id, container_dir))
    if not entries:
        Msg().err("Error: no containers")
        return STATUS_ERROR

    tck = clock_ticks()
    limit = mem_total_bytes()
    roots = []
    for (container_id, container_dir) in entries:
        pid = 0
        if _is_running(container_dir):
            pid = _state_pid(supervisor.read_state(container_dir))
        roots.append((container_id, container_dir, pid))

    first = scan_procs()
    trees = {}
    for (dummy, dummy2, pid) in roots:
        trees[pid] = proc_tree(first, pid) if pid else []

    started = time.time()
    if any(pid for (dummy, dummy2, pid) in roots):
        time.sleep(STATS_INTERVAL)
    second = scan_procs()
    elapsed = time.time() - started

    Msg().out(STATS_FMT % ("CONTAINER ID", "NAME", "CPU%",
                           "MEM USAGE / LIMIT", "MEM%", "PIDS"))
    for (container_id, container_dir, pid) in roots:
        pids = proc_tree(second, pid) if pid else []
        if pids:
            cpu = cpu_percent(total_jiffies(first, trees.get(pid, [])),
                              total_jiffies(second, pids), elapsed, tck)
            rss_kb = total_rss_kb(second, pids)
            count = len(pids)
        else:
            cpu = 0.0
            rss_kb = 0
            count = 0
        usage = rss_kb * 1024
        mem_percent = (usage * 100.0 / limit) if limit else 0.0
        mem_column = "%s / %s" % (format_size(usage), format_size(limit))
        name = container_names(container_dir) or "-"
        Msg().out(STATS_FMT % (str(container_id)[:12], name,
                               "%.2f%%" % cpu, mem_column,
                               "%.2f%%" % mem_percent, str(count)))
    return STATUS_OK


# ------------------------------------------------------------------ diff


def split_imagespec(spec):
    """Split repo/image:tag (also digest tags) into (repo, tag)"""
    spec = (spec or "").strip()
    if not spec:
        return ("", "")
    if "@" in spec:
        return tuple(spec.split("@", 1))
    for marker in (":sha256:", ":sha512:"):
        position = spec.find(marker)
        if position > 0:
            return (spec[:position], spec[position + 1:])
    slash = spec.rfind("/")
    colon = spec.rfind(":")
    if colon > slash:
        return (spec[:colon], spec[colon + 1:])
    return (spec, "latest")


def _normalize_tar_path(name):
    """Relative, normalized path of a tar member or an empty string"""
    name = _decode(name).replace("\\", "/")
    while name.startswith("./"):
        name = name[2:]
    name = name.lstrip("/")
    name = posixpath.normpath(name)
    if name in ("", "."):
        return ""
    if name == ".." or name.startswith("../"):
        return ""
    return name


def _is_ignored_path(rel):
    """ROOT paths that never belong to the image"""
    parts = rel.split("/")
    if parts[0] in ROOT_IGNORE:
        return True
    if rel.startswith("etc/udev/devices/"):
        return True
    if len(parts) > 1 and parts[0] == "tmp":
        if parts[1].startswith(TMP_IGNORE_PREFIX):
            return True
    return False


def _drop_path(entries, path):
    """Remove a path and everything below it"""
    for key in [key for key in entries
                if key == path or key.startswith(path + "/")]:
        del entries[key]


def _member_attrs(member):
    """Normalized attrs tuple of a tar member: size, mtime, mode, type"""
    if member.isdir():
        return (0, int(member.mtime), member.mode & 0o7777, "d")
    if member.issym():
        return (0, int(member.mtime), 0o777, "l")
    if member.islnk():
        return (0, int(member.mtime), member.mode & 0o7777, "link")
    if member.isreg():
        return (member.size, int(member.mtime), member.mode & 0o7777, "f")
    return None


def _apply_layer(layer_file, image, links):
    """Overlay one layer tar on the image entries dict"""
    whiteouts = []
    additions = []
    try:
        tarf = tarfile.open(layer_file, "r:*")
    except (IOError, OSError, tarfile.TarError) as error:
        Msg().err("Error: cannot read image layer:", str(error))
        return False
    try:
        for member in tarf:
            rel = _normalize_tar_path(member.name)
            if not rel or _is_ignored_path(rel):
                continue
            if posixpath.basename(rel).startswith(".wh."):
                whiteouts.append(rel)
                continue
            attrs = _member_attrs(member)
            if not attrs:
                continue
            if attrs[3] == "link":
                linkname = _normalize_tar_path(member.linkname)
                if linkname:
                    additions.append((rel, linkname))
            else:
                additions.append((rel, attrs))
    except (IOError, OSError, tarfile.TarError) as error:
        Msg().err("Error: reading image layer:", str(error))
        return False
    finally:
        tarf.close()

    for rel in whiteouts:
        base = posixpath.basename(rel)
        directory = posixpath.dirname(rel)
        if base == ".wh..wh..opq":
            prefix = directory + "/" if directory else ""
            for key in [key for key in image if not prefix or
                        key.startswith(prefix)]:
                del image[key]
            for key in [key for key in links if not prefix or
                        key.startswith(prefix)]:
                del links[key]
        else:
            target = posixpath.join(directory, base[4:]) if directory \
                else base[4:]
            _drop_path(image, target)
            _drop_path(links, target)

    for (rel, attrs) in additions:
        if isinstance(attrs, tuple):
            image[rel] = attrs
            links.pop(rel, None)
        else:
            links[rel] = attrs
            image.pop(rel, None)
    return True


def _resolve_links(image, links):
    """Resolve tar hardlinks to the attrs of their target"""
    remaining = dict(links)
    progress = True
    while remaining and progress:
        progress = False
        for rel in list(remaining):
            target = remaining[rel]
            if target in image and image[target][3] in ("f", "d", "l"):
                image[rel] = image[target]
                del remaining[rel]
                progress = True
    return image


def image_entries(layer_files):
    """Dict path -> attrs of all image layers, or None on read error"""
    image = {}
    links = {}
    for layer_file in layer_files or []:
        if not _apply_layer(layer_file, image, links):
            return None
    return _resolve_links(image, links)


def _lstat_attrs(path):
    """Normalized attrs tuple of a ROOT path"""
    try:
        status = os.lstat(path)
    except (IOError, OSError):
        return None
    if os.path.islink(path):
        return (0, int(status.st_mtime), 0o777, "l")
    if os.path.isdir(path):
        return (0, int(status.st_mtime), status.st_mode & 0o7777, "d")
    if os.path.isfile(path):
        return (status.st_size, int(status.st_mtime),
                status.st_mode & 0o7777, "f")
    return None


def root_entries(root_dir):
    """Dict path -> attrs of a container ROOT directory"""
    entries = {}
    if not os.path.isdir(root_dir):
        return entries
    for (dirpath, dirnames, filenames) in os.walk(root_dir, followlinks=False):
        keep = []
        for name in dirnames:
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root_dir).replace(os.sep, "/")
            if _is_ignored_path(rel):
                continue
            attrs = _lstat_attrs(path)
            if attrs:
                entries[rel] = attrs
            if not os.path.islink(path):
                keep.append(name)
        dirnames[:] = keep
        for name in filenames:
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root_dir).replace(os.sep, "/")
            if _is_ignored_path(rel):
                continue
            attrs = _lstat_attrs(path)
            if attrs:
                entries[rel] = attrs
    return entries


def diff_entries(image, root):
    """Sorted list of (kind, path) with kind A, C or D"""
    changes = []
    for path in sorted(set(image) | set(root)):
        if path not in image:
            changes.append(("A", path))
        elif path not in root:
            changes.append(("D", path))
        elif image[path] != root[path]:
            changes.append(("C", path))
    return changes


def print_diff(localrepo, container_id):
    """Print the container filesystem changes relative to its image"""
    container_dir = localrepo.cd_container(container_id)
    if not container_dir:
        Msg().err("Error: container not found:", container_id)
        return STATUS_ERROR
    image_name = _read_text(container_dir + "/imagerepo.name").strip()
    (imagerepo, tag) = split_imagespec(image_name)
    if not (imagerepo and tag):
        Msg().err("Error: invalid image name for container:", container_id)
        return STATUS_ERROR
    if not localrepo.cd_imagerepo(imagerepo, tag):
        Msg().err("Error: image not found:", imagerepo + ":" + tag)
        return STATUS_ERROR
    (dummy, layers) = localrepo.get_image_attributes()
    if not layers:
        Msg().err("Error: cannot read the image layers of:",
                  imagerepo + ":" + tag)
        return STATUS_ERROR
    image = image_entries(layers)
    if image is None:
        return STATUS_ERROR
    root = root_entries(container_dir + "/ROOT")
    for (kind, path) in diff_entries(image, root):
        Msg().out("%s /%s" % (kind, path))
    return STATUS_OK


# ---------------------------------------------------------------- system


def used_images(localrepo):
    """Set of repo:tag strings referenced by existing containers"""
    used = set()
    try:
        containers = localrepo.get_containers_list(False)
    except (AttributeError, IOError, OSError, TypeError, ValueError):
        return used
    for item in containers:
        try:
            imagerepo = item[1]
        except (IndexError, TypeError):
            continue
        if imagerepo:
            used.add(imagerepo.strip())
    return used


def tag_layers(localrepo, imagerepo, tag):
    """Dict layer filename -> size for one image tag"""
    layers = {}
    try:
        if not localrepo.cd_imagerepo(imagerepo, tag):
            return layers
        for (filename, size) in localrepo.get_layers(imagerepo, tag):
            layers[posixpath.basename(filename)] = size
    except (AttributeError, IOError, OSError, TypeError, ValueError):
        return layers
    return layers


def _reclaimable(size, total):
    """Docker style 'SIZE (NN%)' reclaimable column"""
    if not size or size <= 0:
        return "0B"
    percent = int(round(size * 100.0 / total)) if total else 0
    return "%s (%d%%)" % (format_size(size), percent)


def print_system_df(localrepo):
    """Print disk usage of images and containers like docker system df"""
    tags = localrepo.get_imagerepos()
    used = used_images(localrepo)
    layer_sizes = {}
    image_layers = {}
    images_active = 0
    for (imagerepo, tag) in tags:
        layers = tag_layers(localrepo, imagerepo, tag)
        image_layers[imagerepo + ":" + tag] = layers
        for (name, size) in layers.items():
            if size and size > 0:
                layer_sizes.setdefault(name, size)
    used_layers = set()
    for (name, layers) in image_layers.items():
        if name in used:
            images_active += 1
            used_layers.update(layers.keys())
    images_size = sum(layer_sizes.values())
    images_reclaim = sum(size for (name, size) in layer_sizes.items()
                         if name not in used_layers)

    containers = localrepo.get_containers_list(False)
    containers_active = 0
    containers_size = 0
    containers_reclaim = 0
    for item in containers:
        container_id = item[0]
        container_dir = localrepo.cd_container(container_id) or ""
        size_mb = localrepo.get_size(container_id)
        if not size_mb or size_mb < 0:
            size_mb = 0
        size = size_mb * 1024 * 1024
        containers_size += size
        if container_dir and _is_running(container_dir):
            containers_active += 1
        else:
            containers_reclaim += size

    volumes = localrepo.get_volumes_list()
    volumes_active = 0
    volumes_size = 0
    volumes_reclaim = 0
    for name in volumes:
        size_mb = localrepo.get_volume_size(name)
        if not size_mb or size_mb < 0:
            size_mb = 0
        size = size_mb * 1024 * 1024
        volumes_size += size
        if localrepo.get_volume_containers(name):
            volumes_active += 1
        else:
            volumes_reclaim += size

    Msg().out(DF_FMT % ("TYPE", "TOTAL", "ACTIVE", "SIZE", "RECLAIMABLE"))
    Msg().out(DF_FMT % ("Images", str(len(tags)), str(images_active),
                        format_size(images_size),
                        _reclaimable(images_reclaim, images_size)))
    Msg().out(DF_FMT % ("Containers", str(len(containers)),
                        str(containers_active), format_size(containers_size),
                        _reclaimable(containers_reclaim, containers_size)))
    Msg().out(DF_FMT % ("Local Volumes", str(len(volumes)),
                        str(volumes_active), format_size(volumes_size),
                        _reclaimable(volumes_reclaim, volumes_size)))
    Msg().out(DF_FMT % ("Build Cache", "0", "0", "0B", "0B"))
    return STATUS_OK


def prunable_containers(localrepo):
    """Containers that are neither running nor protected"""
    result = []
    for item in localrepo.get_containers_list(False):
        container_id = item[0]
        container_dir = localrepo.cd_container(container_id)
        if not container_dir:
            continue
        if localrepo.isprotected_container(container_id):
            continue
        if _is_running(container_dir):
            continue
        result.append((container_id, container_dir))
    return result


def prunable_images(localrepo):
    """Image tags not used by any container and not protected"""
    used = used_images(localrepo)
    result = []
    for (imagerepo, tag) in localrepo.get_imagerepos():
        if imagerepo + ":" + tag in used:
            continue
        if localrepo.isprotected_imagerepo(imagerepo, tag):
            continue
        result.append((imagerepo, tag))
    return result


def _confirm(question):
    """Ask y/N on a tty; None means stdin is not interactive"""
    try:
        interactive = sys.stdin.isatty()
    except (AttributeError, IOError, OSError):
        interactive = False
    if not interactive:
        return None
    Msg().out(question)
    try:
        answer = sys.stdin.readline()
    except (IOError, OSError):
        return False
    return answer.strip().lower() in ("y", "yes")


def _prune_containers(localrepo):
    """Delete prunable containers, return (reclaimed bytes, failures)"""
    containers = prunable_containers(localrepo)
    if not containers:
        return (0, 0)
    reclaimed = 0
    failures = 0
    Msg().out("Deleted Containers:")
    for (container_id, dummy) in containers:
        size_mb = localrepo.get_size(container_id)
        if size_mb and size_mb > 0:
            reclaimed += size_mb * 1024 * 1024
        Msg().out(container_id)
        if not localrepo.del_container(container_id):
            Msg().err("Error: deleting container:", container_id)
            failures += 1
    return (reclaimed, failures)


def _prune_images(localrepo):
    """Delete unused image tags, return (reclaimed bytes, failures)"""
    images = prunable_images(localrepo)
    if not images:
        return (0, 0)
    remove = set(imagerepo + ":" + tag for (imagerepo, tag) in images)
    kept_layers = set()
    for (imagerepo, tag) in localrepo.get_imagerepos():
        if imagerepo + ":" + tag in remove:
            continue
        kept_layers.update(tag_layers(localrepo, imagerepo, tag).keys())
    reclaimed = 0
    failures = 0
    removed_layers = set()
    Msg().out("Deleted Images:")
    for (imagerepo, tag) in images:
        for (name, size) in tag_layers(localrepo, imagerepo, tag).items():
            if name in kept_layers or name in removed_layers:
                continue
            removed_layers.add(name)
            if size and size > 0:
                reclaimed += size
        Msg().out("untagged:", imagerepo + ":" + tag)
        if not localrepo.del_imagerepo(imagerepo, tag, force=True):
            Msg().err("Error: deleting image:", imagerepo + ":" + tag)
            failures += 1
    return (reclaimed, failures)


def system_prune(localrepo, what, force=False):
    """Prune containers, images or both"""
    questions = {
        "containers": "WARNING! This will remove all stopped containers. "
                      "Are you sure you want to continue? [y/N] ",
        "images": "WARNING! This will remove all images not used by any "
                  "container. Are you sure you want to continue? [y/N] ",
        "all": "WARNING! This will remove all stopped containers and unused "
               "images. Are you sure you want to continue? [y/N] ",
    }
    if what not in questions:
        Msg().err("Error: invalid prune target:", what)
        return STATUS_ERROR
    if not force:
        answer = _confirm(questions[what])
        if answer is None:
            Msg().err("Error: prune requires -f when stdin is not a "
                      "terminal (use -f)")
            return STATUS_ERROR
        if not answer:
            Msg().out("Aborted")
            return STATUS_OK
    reclaimed = 0
    failures = 0
    if what in ("containers", "all"):
        (size, errors) = _prune_containers(localrepo)
        reclaimed += size
        failures += errors
    if what in ("images", "all"):
        (size, errors) = _prune_images(localrepo)
        reclaimed += size
        failures += errors
    Msg().out("Total reclaimed space:", format_size(reclaimed))
    if failures:
        return STATUS_ERROR
    return STATUS_OK


# ------------------------------------------------------------------ port


def parse_port(spec):
    """Parse 'host:cont', 'ip:host:cont[/proto]' into a tuple"""
    spec = str(spec).strip()
    if not spec:
        return None
    proto = "tcp"
    if "/" in spec:
        (spec, proto) = spec.rsplit("/", 1)
    parts = spec.split(":")
    if len(parts) < 2:
        return None
    host = parts[-2]
    cont = parts[-1]
    if not (host.isdigit() and cont.isdigit()):
        return None
    if not (0 < int(host) <= 65535 and 0 < int(cont) <= 65535):
        return None
    return (host, cont, proto.lower() or "tcp")


def ports_from_argv(argv):
    """Published ports and -P flag found in a run command line"""
    ports = []
    publish_all = False
    index = 0
    argv = list(argv or [])
    while index < len(argv):
        arg = str(argv[index])
        if arg in ("-P", "--publish-all"):
            publish_all = True
        elif arg in ("-p", "--publish"):
            if index + 1 < len(argv):
                index += 1
                ports.append(argv[index])
        elif arg.startswith("-p="):
            ports.append(arg[3:])
        elif arg.startswith("--publish="):
            ports.append(arg.split("=", 1)[1])
        index += 1
    parsed = []
    for spec in ports:
        port = parse_port(spec)
        if port:
            parsed.append(port)
    return (parsed, publish_all)


def container_ports(container_dir):
    """Ports from state.json if available, else from supervisor.json argv"""
    state = supervisor.read_state(container_dir)
    ports = []
    for entry in state.get("ports") or []:
        if isinstance(entry, (list, tuple)):
            entry = ":".join([str(part) for part in entry])
        port = parse_port(entry)
        if port:
            ports.append(port)
    if ports:
        return (ports, False)
    conf = supervisor.read_conf(container_dir)
    return ports_from_argv(conf.get("argv") or [])


def print_ports(container_dir, mapping=None):
    """Print published ports of a container like docker port"""
    (ports, publish_all) = container_ports(container_dir)
    if publish_all:
        Msg().out("Notice: -P ports are allocated by PRoot and cannot be "
                  "inspected", l=Msg.WAR)
    if mapping:
        wanted = str(mapping).strip()
        proto = "tcp"
        if "/" in wanted:
            (wanted, proto) = wanted.split("/", 1)
        matched = [port for port in ports
                   if port[1] == wanted and port[2] == proto.lower()]
        if not matched:
            Msg().err("Error: no published port:", mapping)
            return STATUS_ERROR
        for port in matched:
            Msg().out(port[0])
        return STATUS_OK
    if not ports:
        Msg().err("Error: no published ports for this container")
        return STATUS_ERROR
    for (host, cont, proto) in ports:
        Msg().out("%s/%s -> %s" % (cont, proto, host))
    return STATUS_OK
