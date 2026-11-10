# -*- coding: utf-8 -*-
"""udocker Command Line Interface implementation"""

import os
import sys
import string
import json
import random
import hashlib
import shutil
import socket
import time
import calendar
from getpass import getpass

from udocker import __version__
from udocker.config import Config
from udocker.msg import Msg
from udocker.docker import DockerIoAPI
from udocker.localfile import LocalFileAPI
from udocker.helper.keystore import KeyStore
from udocker.helper.hostinfo import HostInfo
from udocker.helper.unshare import Unshare
from udocker.helper.unique import Unique
from udocker.container.structure import ContainerStructure
from udocker.container.dockerfile import DockerfileParser, ContainerBuilder
from udocker.engine.execmode import ExecutionMode
from udocker.engine.nvidia import NvidiaMode
from udocker.tools import UdockerTools
from udocker.utils.fileutil import FileUtil
from udocker.utils.filebind import FileBind
from udocker.utils.mountpoint import MountPoint
from udocker.utils.portforward import PortForwarder
from udocker.utils.containerpath import container_realpath
from udocker.utils.gotemplate import render as render_template
from udocker.utils import ulimits as ulimits_util
from udocker import supervisor
from udocker import extras
from udocker import compose

# if Python 3
if sys.version_info[0] >= 3:
    BUILTIN = "builtins"
    GET_INPUT = input
else:
    BUILTIN = "__builtin__"
    # Xpylint: disable=undefined-variable
    GET_INPUT = raw_input


def _parse_timestamp(timestamp):
    """Epoch seconds of an ISO-8601 UTC timestamp, None if unparsable"""
    if not isinstance(timestamp, str) or len(timestamp) < 19:
        return None
    try:
        parsed = time.strptime(timestamp[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
    return calendar.timegm(parsed)


def _human_duration(seconds):
    """Docker style duration: 3 minutes, 2 hours, 5 days"""
    seconds = max(int(seconds), 0)
    for size, name in ((31536000, "year"), (2592000, "month"),
                       (604800, "week"), (86400, "day"),
                       (3600, "hour"), (60, "minute"), (1, "second")):
        value = seconds // size
        if value:
            return "%d %s%s" % (value, name, "" if value == 1 else "s")
    return "0 seconds"


def _relative_time(timestamp):
    """Human readable age of a timestamp, as docker prints it in CREATED"""
    epoch = _parse_timestamp(timestamp)
    if epoch is None:
        return ""
    return _human_duration(time.time() - epoch) + " ago"


def _container_labels(container_dir):
    """Labels recorded for a container, empty dict when missing"""
    if not isinstance(container_dir, (str, bytes)):
        return {}
    try:
        with open(container_dir + "/labels.json", "r") as filep:
            labels = json.load(filep)
    except (IOError, OSError, ValueError, TypeError):
        return {}
    return labels if isinstance(labels, dict) else {}


def _read_state(container_dir):
    """Container state.json as a dict, empty when missing or invalid"""
    if not isinstance(container_dir, (str, bytes)):
        return {}
    try:
        with open(container_dir + "/state.json", "r") as filep:
            state = json.load(filep)
    except (IOError, OSError, ValueError, TypeError):
        return {}
    return state if isinstance(state, dict) else {}


def _docker_status(container_dir, status):
    """Docker style STATUS column of a container"""
    if status == "Created":
        return "Created"
    state = _read_state(container_dir)
    epoch = _parse_timestamp(state.get("timestamp", ""))
    age = _human_duration(time.time() - epoch) if epoch else ""
    if status in ("Running", "Paused"):
        if not age:
            status_text = "Up"
        elif age == "0 seconds":
            status_text = "Up Less than a second"
        else:
            status_text = "Up " + age
        return status_text + (" (Paused)" if status == "Paused" else "")
    suffix = " " + age + " ago" if age else ""
    if status == "Interrupted":
        return "Exited (137)" + suffix
    return status + suffix


def _as_command_list(value):
    """Normalize a Cmd/Entrypoint metadata value to a list of tokens"""
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return value.split()
    return []


def _format_command(parts, no_trunc=False):
    """COMMAND column text: quoted and truncated like docker"""
    text = " ".join(parts)
    if not text:
        return ""
    text = '"' + text + '"'
    if not no_trunc and len(text) > 20:
        text = text[:20]
    return text


def _container_command(container_dir, no_trunc=False):
    """Docker style COMMAND column built from the container metadata"""
    if not isinstance(container_dir, (str, bytes)):
        return ""
    try:
        with open(container_dir + "/cmd.json", "r") as filep:
            recorded = json.load(filep)
    except (IOError, OSError, ValueError, TypeError):
        recorded = None
    if isinstance(recorded, dict):
        parts = _as_command_list(recorded.get("entrypoint"))
        parts.extend(_as_command_list(recorded.get("cmd")))
        text = _format_command(parts, no_trunc)
        if text:
            return text
    try:
        with open(container_dir + "/container.json", "r") as filep:
            data = json.load(filep)
    except (IOError, OSError, ValueError, TypeError):
        return ""
    if not isinstance(data, dict):
        return ""
    meta = data.get("config") or data.get("container_config") or data
    if not isinstance(meta, dict):
        return ""
    parts = (_as_command_list(meta.get("Entrypoint")) or
             _as_command_list(meta.get("entrypoint")))
    parts = list(parts)
    parts.extend(_as_command_list(meta.get("Cmd")) or
                 _as_command_list(meta.get("cmd")))
    return _format_command(parts, no_trunc)


def _docker_ports(ports):
    """Docker style PORTS column from the recorded port mappings"""
    result = []
    for mapping in ports or []:
        text = str(mapping)
        parts = text.split(":")
        if len(parts) == 2 and parts[0] and parts[1]:
            port = parts[1]
            proto = "tcp"
            if "/" in port:
                (port, proto) = port.split("/", 1)
            result.append("0.0.0.0:%s->%s/%s" % (parts[0], port, proto))
        else:
            result.append(text)
    return ", ".join(result)


def _status_matches(status, wanted):
    """Does a container status match a docker ps -f status= filter value"""
    if wanted in ("running", "up"):
        return status == "Running"
    if wanted in ("exited", "dead"):
        return status.startswith("Exited") or status == "Interrupted"
    if wanted == "created":
        return status == "Created"
    if wanted == "paused":
        return status == "Paused"
    return False


def _filter_match(container, filters):
    """Apply docker ps --filter key=value items to one container record"""
    for item in filters:
        (key, separator, value) = str(item).partition("=")
        if not separator:
            return False
        values = [entry for entry in value.split(",") if entry]
        if key == "status":
            if not any(_status_matches(container["status"], entry)
                       for entry in values):
                return False
        elif key == "name":
            names = container.get("name") or ""
            if not any(entry in names for entry in values):
                return False
        elif key == "id":
            if not any(container["container_id"].startswith(entry)
                       for entry in values):
                return False
        elif key in ("ancestor", "image"):
            image = container.get("image") or ""
            if not any(entry in image for entry in values):
                return False
        elif key == "label":
            labels = container.get("labels") or {}
            for entry in values:
                (label_key, separator, label_value) = entry.partition("=")
                if separator:
                    if labels.get(label_key) != label_value:
                        return False
                elif label_key not in labels:
                    return False
        else:
            return False
    return True


class UdockerCLI(object):
    """Implements most of the command line interface.
    These methods correspond directly to the commands that can
    be invoked via the command line interface.
    """

    STATUS_OK = 0
    STATUS_ERROR = 1

    def __init__(self, localrepo):
        self.localrepo = localrepo
        self.dockerioapi = DockerIoAPI(self.localrepo)
        self.localfileapi = LocalFileAPI(self.localrepo)
        if Config.conf['keystore'].startswith("/"):
            self.keystore = KeyStore(Config.conf['keystore'])
        else:
            self.keystore = KeyStore(self.localrepo.homedir + "/" + Config.conf['keystore'])

        Msg().out("Debug: Localrepo homedir is", self.localrepo.homedir, l=Msg.DBG)

    def _cdrepo(self, cmdp):
        """Select the top directory of a local repository"""
        topdir = cmdp.get("P1")
        if cmdp.missing_options():               # syntax error
            return False

        if not FileUtil(topdir).isdir():
            Msg().out("Warning: localrepo directory is invalid: ",
                      topdir, l=Msg.WAR)
            return False

        self.localrepo.setup(topdir)
        return True

    # ARCHNEW
    def _check_imagespec(self, imagespec, def_imagespec=None):
        """Check image:tag syntax"""
        if (not imagespec) and def_imagespec:
            imagespec = def_imagespec

        try:
            (imagerepo, tag) = imagespec.split("@", 1)
        except (ValueError, AttributeError):
            try:
                (imagerepo, tag) = imagespec.split(":", 1)
            except (ValueError, AttributeError):
                imagerepo = imagespec
                tag = "latest"

        if not (imagerepo and tag and
                (self.dockerioapi.is_repo_name(imagespec) or
                 self.dockerioapi.is_layer_name(imagespec))):
            Msg().err("Error: must specify image:tag or repository/image:tag")
            return (None, None)

        return imagerepo, tag

    def _check_imagerepo(self, imagerepo, def_imagerepo=None):
        """Check image repository syntax"""
        if (not imagerepo) and def_imagerepo:
            imagerepo = def_imagerepo

        if not (imagerepo and
                self.dockerioapi.is_repo_name(imagerepo)):
            Msg().err("Error: enter image or repository/image without tag")
            return None

        return imagerepo

    def _set_repository(self, registry_url, index_url=None,
                        imagerepo=None, http_proxy=None):
        """Select docker repository"""
        transport = "https:"
        if http_proxy:
            self.dockerioapi.set_proxy(http_proxy)

        if registry_url:
            if "://" not in registry_url:
                registry_url = "https://" + registry_url
            self.dockerioapi.set_registry(registry_url)
            if not index_url:
                self.dockerioapi.set_index("")

        if index_url:
            if "://" not in index_url:
                index_url = "https://" + index_url
            self.dockerioapi.set_index(index_url)
            if not registry_url:
                self.dockerioapi.set_registry("")

        if not (registry_url or index_url):
            try:
                if "://" in imagerepo:
                    (transport, dummy, hostname) = imagerepo.split('/')[:3]
                else:
                    (hostname, dummy) = imagerepo.split('/')[:2]
            except (ValueError, IndexError, TypeError):
                return False
            if "." in hostname:
                try:
                    self.dockerioapi.set_registry(Config.conf['docker_registries'][hostname][0])
                    self.dockerioapi.set_index(Config.conf['docker_registries'][hostname][1])
                except (KeyError, NameError, TypeError):
                    self.dockerioapi.set_registry(transport + "//" + hostname)
                    self.dockerioapi.set_index(transport + "//" + hostname)

        Msg().out("Debug: Set registry URL", registry_url, l=Msg.DBG)
        return True

    def _split_imagespec(self, imagerepo):
        """Split image repo into hostname, repo, tag"""
        if not imagerepo:
            return ("", "", "", "")
        transport = ""
        hostname = ""
        image = imagerepo
        tag = ""
        try:
            if "://" in imagerepo:
                (transport, dummy, hostname, image) = imagerepo.split('/', 4)
            elif '/' in imagerepo:
                (hostname, image) = imagerepo.split('/', 1)
        except (ValueError, IndexError, TypeError):
            pass
        if hostname and '.' not in hostname:
            image = hostname + '/' + image
            hostname = ""
        if ':' in image:
            (image, tag) = image.split(':', 1)
        return (transport, hostname, image, tag)

    @staticmethod
    def _container_realpath(container_root, path, follow_final=True):
        """Resolve a path inside the container ROOT without escaping it"""
        return container_realpath(container_root, path, follow_final)

    def _parse_cp_arg(self, arg):
        """Split a cp argument into (container_id, path).
        Returns (None, arg) when the argument is a host path."""
        if not arg:
            return (None, "")
        if ":" in arg:
            (ref, path) = arg.split(":", 1)
            container_id = self.localrepo.get_container_id(ref)
            if container_id:
                return (container_id, path)
        return (None, arg)

    @staticmethod
    def _copy_tree(src, dst):
        """Recursively copy src into dst preserving modes and symlinks"""
        if os.path.exists(dst) and not os.path.isdir(dst):
            return False
        try:
            if not os.path.isdir(dst):
                os.makedirs(dst)
            for name in os.listdir(src):
                srcname = os.path.join(src, name)
                dstname = os.path.join(dst, name)
                if os.path.islink(srcname):
                    if os.path.lexists(dstname):
                        os.unlink(dstname)
                    os.symlink(os.readlink(srcname), dstname)
                elif os.path.isdir(srcname):
                    if not UdockerCLI._copy_tree(srcname, dstname):
                        return False
                else:
                    shutil.copy2(srcname, dstname)
        except (IOError, OSError):
            return False
        try:
            shutil.copystat(src, dst)
        except (IOError, OSError):
            pass
        return True

    @staticmethod
    def _copy_path(src, dst):
        """Copy one file, symlink or directory tree to dst"""
        if not os.path.lexists(src):
            return False
        if os.path.islink(src):
            try:
                if os.path.lexists(dst):
                    os.unlink(dst)
                os.symlink(os.readlink(src), dst)
            except (IOError, OSError):
                return False
            return True
        if os.path.isdir(src):
            return UdockerCLI._copy_tree(src, dst)
        try:
            parent = os.path.dirname(dst)
            if parent and not os.path.isdir(parent):
                os.makedirs(parent)
            shutil.copy2(src, dst)
        except (IOError, OSError):
            return False
        return True

    @staticmethod
    def _write_state(container_dir, status, exitcode=None, ports=None):
        """Record the execution state of a container for ps"""
        supervisor.write_state(container_dir, status, exitcode, ports=ports)

    @staticmethod
    def _ps_record(container):
        """Docker ps --format json record of one container"""
        status = container.get("status", "")
        if status == "Running":
            state = "running"
        elif status.startswith("Exited") or status == "Interrupted":
            state = "exited"
        elif status == "Paused":
            state = "paused"
        else:
            state = "created"
        created_epoch = container.get("created_epoch") or 0
        created_at = ""
        if created_epoch:
            created_at = time.strftime(
                "%Y-%m-%d %H:%M:%S %z", time.localtime(created_epoch))
        return {
            "Command": container.get("command", ""),
            "CreatedAt": created_at,
            "ID": container.get("container_id", ""),
            "Image": container.get("image", ""),
            "Labels": ",".join("%s=%s" % item for item in
                               sorted((container.get("labels") or {}).items())),
            "LocalVolumes": "0",
            "Mounts": "",
            "Names": container.get("name", ""),
            "Networks": "host",
            "Ports": container.get("ports", ""),
            "RunningFor": container.get("created", ""),
            "Size": "0B",
            "State": state,
            "Status": container.get("docker_status", ""),
        }

    @staticmethod
    def _container_status(container_dir):
        """Compute the docker-like status of a container"""
        if not isinstance(container_dir, (str, bytes)):
            return "Created"
        try:
            with open(container_dir + "/state.json", "r") as filep:
                state = json.load(filep)
        except (IOError, OSError, ValueError, TypeError):
            return "Created"
        status = state.get("status", "")
        if status in ("running", "paused"):
            try:
                os.kill(int(state.get("pid", 0)), 0)
            except (OSError, ValueError, TypeError):
                return "Interrupted"
            return "Running" if status == "running" else "Paused"
        if status == "exited":
            return "Exited (%s)" % state.get("exitcode", "?")
        if status == "interrupted":
            return "Interrupted"
        return "Created"

    @staticmethod
    def _free_tcp_port():
        """Pick a free localhost TCP port for -P"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]
        except (OSError, ValueError):
            return 0
        finally:
            sock.close()

    def _expand_publish_all(self, exec_engine, container_id):
        """Map the image ExposedPorts to free host ports for -P
        The mappings are explicit afterwards: PRoot publishes them with
        -p in P modes and the userspace forwarder does it in F/R/S modes.
        """
        if not isinstance(getattr(exec_engine, "opt", None), dict):
            return True
        if not exec_engine.opt.get("netcoop"):
            return True
        container_structure = ContainerStructure(self.localrepo,
                                                 container_id)
        (dummy, container_json) = container_structure.get_container_attr()
        exposed = []
        if container_json:
            exposed = container_structure.get_container_meta(
                "ExposedPorts", [], container_json)
        for port in exposed or []:
            # metadata dicts are flattened to "key:value" strings by
            # ContainerStructure, so "8080/tcp:{}" -> port "8080/tcp"
            port_str = str(port).split(":", 1)[0]
            port_spec = port_str.split("/")[0]
            proto = "tcp"
            if "/" in port_str:
                proto = port_str.split("/", 1)[1]
            if proto != "tcp":
                Msg().out("Warning: -P publishes TCP ports only, skipping:",
                          port_str, l=Msg.WAR)
                continue
            host_port = self._free_tcp_port()
            if not host_port:
                Msg().err("Error: cannot find a free host port for:", port)
                return False
            mapping = "%d:%s" % (host_port, port_spec)
            if mapping not in exec_engine.opt["portsmap"]:
                exec_engine.opt["portsmap"].append(mapping)
        # the mappings are explicit now, avoid the engine -P warnings
        exec_engine.opt["netcoop"] = False
        return True

    def _expand_volumes_from(self, exec_engine):
        """Append the volumes of containers named with --volumes-from"""
        if not isinstance(getattr(exec_engine, "opt", None), dict):
            return True
        refs = exec_engine.opt.get("volfrom")
        if not isinstance(refs, (list, tuple)):
            return True
        for ref in refs:
            ref_id = self.localrepo.get_container_id(ref)
            if not ref_id:
                Msg().err("Error: --volumes-from container not found:", ref)
                return False
            ref_dir = self.localrepo.cd_container(ref_id) or ""
            volumes = []
            try:
                with open(ref_dir + "/volumes.json", "r") as filep:
                    volumes = json.load(filep)
            except (IOError, OSError, ValueError, TypeError):
                volumes = []
            if not volumes:
                Msg().out("Warning: container has no recorded volumes:",
                          ref, l=Msg.WAR)
                continue
            for vol in volumes:
                if vol not in exec_engine.opt["vol"]:
                    exec_engine.opt["vol"].append(vol)
        return True

    @staticmethod
    def _save_run_volumes(container_dir, volumes):
        """Remember the volume bindings for later --volumes-from"""
        if not isinstance(container_dir, str):
            return
        try:
            with open(container_dir + "/volumes.json", "w") as filep:
                json.dump(list(volumes), filep)
        except (IOError, OSError, ValueError, TypeError):
            pass

    @staticmethod
    def _stop_config(container_dir):
        """Signal and timeout recorded for docker stop"""
        if not isinstance(container_dir, str):
            return {}
        try:
            with open(container_dir + "/stop.json", "r") as filep:
                config = json.load(filep)
        except (IOError, OSError, ValueError, TypeError):
            return {}
        return config if isinstance(config, dict) else {}

    @staticmethod
    def _save_stop_config(container_dir, signal, timeout):
        """Record the stop signal and timeout of the last run"""
        if not isinstance(container_dir, str):
            return
        config = {"signal": str(signal or ""), "timeout": timeout}
        try:
            with open(container_dir + "/stop.json", "w") as filep:
                json.dump(config, filep)
        except (IOError, OSError, ValueError, TypeError):
            pass

    @staticmethod
    def _image_stop_signal(container_dir):
        """StopSignal declared by the image metadata, empty when absent"""
        if not isinstance(container_dir, (str, bytes)):
            return ""
        try:
            with open(container_dir + "/container.json", "r") as filep:
                data = json.load(filep)
        except (IOError, OSError, ValueError, TypeError):
            return ""
        if not isinstance(data, dict):
            return ""
        meta = data.get("config") or data.get("container_config") or data
        if not isinstance(meta, dict):
            return ""
        return str(meta.get("StopSignal") or meta.get("stopsignal") or "")

    @staticmethod
    def _save_labels(container_dir, labels):
        """Remember the container labels for ps/inspect filters"""
        if not isinstance(container_dir, str):
            return
        data = {}
        for item in labels or []:
            (key, separator, value) = str(item).partition("=")
            if key:
                data[key] = value if separator else ""
        try:
            with open(container_dir + "/labels.json", "w") as filep:
                json.dump(data, filep)
        except (IOError, OSError, ValueError, TypeError):
            pass

    @staticmethod
    def _save_run_command(container_dir, opt):
        """Remember the command of the last run for docker ps COMMAND"""
        if not isinstance(container_dir, str):
            return
        data = {
            "entrypoint": opt.get("entryp") or "",
            "cmd": opt.get("cmd") or [],
        }
        try:
            with open(container_dir + "/cmd.json", "w") as filep:
                json.dump(data, filep)
        except (IOError, OSError, ValueError, TypeError):
            pass

    @staticmethod
    def _start_port_forwarder(exec_engine, exec_mode):
        """Publish container ports where PRoot does not do it.
        F, R and S modes share the host network namespace, so a userspace
        TCP forwarder is enough and requires no privileges.
        Returns a started PortForwarder, None when nothing to do, or
        False on a malformed mapping.
        """
        if not isinstance(getattr(exec_engine, "opt", None), dict):
            return None
        portsmap = exec_engine.opt.get("portsmap") or []
        if not portsmap:
            return None
        mode = exec_mode.get_mode() if exec_mode else ""
        if isinstance(mode, str) and mode.startswith("P"):
            return None
        forwarder = PortForwarder()
        for mapping in portsmap:
            try:
                (host_port, container_port) = str(mapping).split(":", 1)
            except ValueError:
                Msg().err("Error: invalid port mapping:", mapping)
                return False
            if not forwarder.add(host_port, container_port):
                forwarder.stop()
                return False
        forwarder.start()
        return forwarder

    def do_mkrepo(self, cmdp):
        """
        mkrepo: create a local repository in a specified directory
        mkrepo <directory>
        """
        topdir = cmdp.get("P1")
        if cmdp.missing_options():
            return self.STATUS_ERROR
        if not os.path.exists(topdir):
            self.localrepo.setup(topdir)
            if not self.localrepo.create_repo():
                Msg().err("Error: localrepo creation failure: ", topdir)
                return self.STATUS_ERROR
        else:
            Msg().err("Error: localrepo directory already exists: ", topdir)
            return self.STATUS_ERROR

        return self.STATUS_OK

    def _search_print_lines(self, repo_list, lines, fmt):
        """Print search results from v1 or v2 API"""
        for repo in repo_list["results"]:
            if "is_official" in repo and repo["is_official"]:
                is_official = "[OK]"
            else:
                is_official = "----"
            description = ""
            for dfield in ("description", "short_description"):
                if dfield in repo and repo[dfield] is not None:
                    for char in repo[dfield]:
                        if char == '\n':
                            break
                        if char in string.printable:
                            description += char
                    break
            name = ""
            for nfield in ("name", "repo_name"):
                if nfield in repo and repo[nfield] is not None:
                    name = repo[nfield]
                    break
            stars = ""
            if "star_count" in repo and repo["star_count"] is not None:
                stars = str(repo["star_count"])
            Msg().out(fmt % (name, is_official, description, stars))
            lines -= 1
            if not lines:
                break

    def _search_repositories(self, expression, pause="", no_trunc=""):
        """Print search header and loop over search results"""
        term_lines, dummy = HostInfo().termsize()
        term_lines -= 2
        fmt = "%-55.80s %8.8s %-70.70s %5.5s"
        if no_trunc:
            fmt = "%-55s %8s %-70s %5s"
        while True:
            lines = term_lines
            while lines > 0:
                repo_list = self.dockerioapi.search_get_page(expression, term_lines)
                if not repo_list:
                    return self.STATUS_OK
                if lines == term_lines:
                    Msg().out(fmt % ("NAME", "OFFICIAL", "DESCRIPTION", "STARS"), l=Msg.INF)
                if len(repo_list["results"]) > lines:
                    print_lines = lines
                else:
                    print_lines = len(repo_list["results"])

                lines -= print_lines
                self._search_print_lines(repo_list, print_lines, fmt)

            if pause and not self.dockerioapi.search_ended:
                if GET_INPUT("[return or q to quit]") in ('q', 'Q', 'e', 'E'):
                    return self.STATUS_OK

    def _list_tags(self, expression):
        """List tags for repository"""
        try:
            for tag in self.dockerioapi.get_tags(expression):
                Msg().out(tag)
            return self.STATUS_OK
        except (KeyError, TypeError, ValueError):
            return self.STATUS_ERROR

    def do_search(self, cmdp):
        """
                search: search dockerhub for container images
        search [options]  <expression>
        -a                                              :do not pause
        --no-trunc                                      :do not trunc lines
        --list-tags                                     :list repository tags
        --index=<url>                ex. https://index.docker.io/v1
        --registry=<url>             ex. https://registry-1.docker.io
        --httpproxy=socks4://user:pass@host:port        :use http proxy
        --httpproxy=socks5://user:pass@host:port        :use http proxy
        --httpproxy=socks4://host:port                  :use http proxy
        --httpproxy=socks5://host:port                  :use http proxy
        --httpproxy=socks4a://user:pass@host:port       :use http proxy
        --httpproxy=socks5h://user:pass@host:port       :use http proxy
        --httpproxy=socks4a://host:port                 :use http proxy
        --httpproxy=socks5h://host:port                 :use http proxy
        """
        pause = not cmdp.get("-a")
        index_url = cmdp.get("--index=")
        registry_url = cmdp.get("--registry=")
        http_proxy = cmdp.get("--httpproxy=")
        no_trunc = cmdp.get("--no-trunc")
        list_tags = cmdp.get("--list-tags")
        expression = cmdp.get("P1")
        if cmdp.missing_options():               # syntax error
            return self.STATUS_ERROR
        self._set_repository(registry_url, index_url, expression, http_proxy)
        Msg().out("Debug: registry URL", registry_url, l=Msg.DBG)
        (dum1, dum2, expression, dum3) = self._split_imagespec(expression)
        self.dockerioapi.search_init(pause)
        v2_auth_token = self.keystore.get(self.dockerioapi.registry_url)
        self.dockerioapi.set_v2_login_token(v2_auth_token)
        if list_tags:
            return self._list_tags(expression)

        return self._search_repositories(expression, pause, no_trunc)

    def do_load(self, cmdp):
        """
        load: load an  image saved by docker with 'docker save'
        load [options] <repo/image>
        --input=<image-file>        :load image file saved by docker
        -i <image-file>             :load image file saved by docker
        """
        imagefile = cmdp.get("--input=")
        if not imagefile:
            imagefile = cmdp.get("-i=")
            if not imagefile:
                imagefile = '-'
        from_stdin = cmdp.get('-')
        if from_stdin:
            imagefile = '-'
            cmdp.get("-i")
        imagerepo = cmdp.get("P1")
        if imagerepo == '-':
            imagefile = '-'
            imagerepo = cmdp.get("P2")
        if cmdp.missing_options():  # syntax error
            return self.STATUS_ERROR
        if not imagefile:
            Msg().err("Error: must specify filename of docker exported image")
            return self.STATUS_ERROR
        if imagerepo and not self._check_imagerepo(imagerepo):
            return self.STATUS_ERROR
        tag = None
        if imagerepo and ':' in imagerepo:
            (imagerepo, tag) = imagerepo.rsplit(':', 1)
        repos = self.localfileapi.load(imagefile, imagerepo, tag)
        if not repos:
            Msg().err("Error: load failed")
            return self.STATUS_ERROR
        for repo_item in repos:
            Msg().out(repo_item)
        return self.STATUS_OK

    def do_save(self, cmdp):
        """
        save: save an image to file
        save [options] IMAGE
        --output=<image-file>       :save image to file
        -o <image-file>             :save image to file
        """
        imagefile = cmdp.get("--output=")
        if not imagefile:
            imagefile = cmdp.get("-o=")
            if not imagefile:
                imagefile = '-'
        from_stdin = cmdp.get('-')
        imagespec_list = cmdp.get("P*")
        if from_stdin:
            del imagespec_list[0]
            imagefile = '-'
            cmdp.get("-o")
        if cmdp.missing_options():  # syntax error
            return self.STATUS_ERROR
        if imagefile != '-':
            if os.path.exists(imagefile):
                Msg().err("Error: output file already exists:", imagefile)
                return self.STATUS_ERROR
        imagetag_list = []
        for imagespec in imagespec_list:
            (imagerepo, tag) = self._check_imagespec(imagespec)
            if not imagerepo:
                return self.STATUS_ERROR
            imagetag_list.append((imagerepo, tag))
        if not imagefile:
            Msg().err("Error: must specify filename of image file for output")
            return self.STATUS_ERROR
        if not self.localfileapi.save(imagetag_list, imagefile):
            return self.STATUS_ERROR
        return self.STATUS_OK

    def do_import(self, cmdp):
        """
        import : import image (directory tree) from tar file or stdin
        import <tar-file> <repo/image:tag>
        import - <repo/image:tag>
        --mv                      :if possible move tar-file instead of copy
        --tocontainer             :import to container, no image is created
        --clone                   :import udocker container format with metadata
        --name=<container-name>   :with --tocontainer or --clone to add an alias
        --platform=os/arch        :docker platform
        """
        move_tarball = cmdp.get("--mv")
        to_container = cmdp.get("--tocontainer")
        name = cmdp.get("--name=")
        platform = cmdp.get("--platform=")
        clone = cmdp.get("--clone")
        from_stdin = cmdp.get('-')
        if from_stdin:
            tarfile = '-'
            imagespec = cmdp.get("P1")
            if imagespec == '-':
                imagespec = cmdp.get("P2")
            move_tarball = False
        else:
            tarfile = cmdp.get("P1")
            imagespec = cmdp.get("P2")
        if cmdp.missing_options():  # syntax error
            return self.STATUS_ERROR
        if not tarfile:
            Msg().err("Error: must specify tar filename")
            return self.STATUS_ERROR
        if to_container or clone:
            if clone:
                container_id = self.localfileapi.import_clone(
                    tarfile, name)
            else:
                (imagerepo, tag) = self._check_imagespec(imagespec,
                                                         "IMPORTED:unknown")
                container_id = self.localfileapi.import_tocontainer(
                    tarfile, imagerepo, tag, name, platform)
            if container_id:
                Msg().out(container_id)
                return self.STATUS_OK
        else:
            (imagerepo, tag) = self._check_imagespec(imagespec)
            if not imagerepo:
                return self.STATUS_ERROR
            if self.localfileapi.import_toimage(tarfile, imagerepo, tag,
                                                move_tarball, platform):
                return self.STATUS_OK
        Msg().err("Error: importing")
        return self.STATUS_ERROR

    def do_export(self, cmdp):
        """
        export : export container (directory tree) to a tar file or stdin
        export -o <tar-file> <container-id>
        export - <container-id>
        -o                         :export to file, instead of stdout
        --clone                    :export in clone (udocker) format
        """
        to_file = cmdp.get("-o")
        clone = cmdp.get("--clone")
        if to_file:
            tarfile = cmdp.get("P1")
            container_id = cmdp.get("P2")
        else:
            tarfile = "-"
            container_id = cmdp.get("P1")
        if cmdp.missing_options():  # syntax error
            return self.STATUS_ERROR
        container_id = self.localrepo.get_container_id(container_id)
        if not container_id:
            Msg().err("Error: invalid container id", container_id)
            return self.STATUS_ERROR
        if not tarfile:
            Msg().err("Error: invalid output file name", tarfile)
            return self.STATUS_ERROR
        if to_file:
            Msg().out("Info: exporting to file", tarfile)

        cstruct = ContainerStructure(self.localrepo, container_id)
        if clone:
            if cstruct.clone_tofile(tarfile):
                return self.STATUS_OK
        elif cstruct.export_tofile(tarfile):
            return self.STATUS_OK

        Msg().err("Error: exporting")
        return self.STATUS_ERROR

    def do_clone(self, cmdp):
        """
        clone : create a duplicate copy of an existing container
        clone <source-container-id>
        --name=<container-name>    :add an alias to the cloned container
        """
        name = cmdp.get("--name=")
        container_id = cmdp.get("P1")
        if cmdp.missing_options():  # syntax error
            return self.STATUS_ERROR
        container_id = self.localrepo.get_container_id(container_id)
        if not container_id:
            Msg().err("Error: invalid container id", container_id)
            return self.STATUS_ERROR
        if name and self.localrepo.get_container_id(name):
            Msg().err("Error: container name already exists")
            return self.STATUS_ERROR
        Msg().out("Debug: cloning container id:", container_id, l=Msg.DBG)
        clone_id = self.localfileapi.clone_container(container_id, name)
        if clone_id:
            Msg().out(clone_id)
            return self.STATUS_OK

        Msg().err("Error: cloning")
        return self.STATUS_ERROR

    def do_login(self, cmdp):
        """
        login: authenticate into docker repository e.g. dockerhub
        --username=username
        --password=password
        --password-stdin         :read password from stdin
        --registry=<url>         :optional ex. quay.io, public.ecr.aws
        """
        username = cmdp.get("--username=")
        password = cmdp.get("--password=")
        password_stdin = cmdp.get("--password-stdin")
        registry_url = cmdp.get("--registry=")
        if cmdp.missing_options():  # syntax error
            return self.STATUS_ERROR
        self._set_repository(registry_url, None, None, None)
        if not username:
            username = GET_INPUT("username: ")
        if password_stdin:
            password = input()
        elif not password:
            password = getpass("password: ")
        if password and password == password.upper():
            Msg().out("Warning: password in uppercase", "Caps Lock ?", l=Msg.WAR)

        v2_auth_token = self.dockerioapi.get_v2_login_token(username, password)
        Msg().out("Debug: V2 Auth token", v2_auth_token, l=Msg.DBG)
        if self.keystore.put(self.dockerioapi.registry_url, v2_auth_token, "") == 0:
            Msg().out("Debug: registry URL", self.dockerioapi.registry_url, l=Msg.DBG)
            return self.STATUS_OK

        Msg().err("Error: invalid credentials")
        return self.STATUS_ERROR

    def do_logout(self, cmdp):
        """
        logout: authenticate into docker repository e.g. dockerhub
        -a remove all authentication credentials
        --registry=<url>          ex. https://registry-1.docker.io
        """
        all_credentials = cmdp.get("-a")
        registry_url = cmdp.get("--registry=")
        if cmdp.missing_options():  # syntax error
            return self.STATUS_ERROR
        self._set_repository(registry_url, None, None, None)
        if all_credentials:
            exit_status = self.keystore.erase()
        else:
            exit_status = self.keystore.delete(self.dockerioapi.registry_url)

        if exit_status == self.STATUS_ERROR:
            Msg().err("Error: deleting credentials")

        return exit_status

    def do_pull(self, cmdp):
        """
        pull: download images from docker hub
        pull [options] <repo/image:tag>
        --httpproxy=socks4://user:pass@host:port        :use http proxy
        --httpproxy=socks5://user:pass@host:port        :use http proxy
        --httpproxy=socks4://host:port                  :use http proxy
        --httpproxy=socks5://host:port                  :use http proxy
        --httpproxy=socks4a://user:pass@host:port       :use http proxy
        --httpproxy=socks5h://user:pass@host:port       :use http proxy
        --httpproxy=socks4a://host:port                 :use http proxy
        --httpproxy=socks5h://host:port                 :use http proxy
        --index=https://index.docker.io/v1              :docker index
        --registry=https://registry-1.docker.io         :docker registry
        --platform=os/arch                              :docker platform

        Examples:
          pull fedora:latest
          pull quay.io/something/somewhere:latest
        """
        index_url = cmdp.get("--index=")
        registry_url = cmdp.get("--registry=")
        http_proxy = cmdp.get("--httpproxy=")
        platform = cmdp.get("--platform=")
        (imagerepo, tag) = self._check_imagespec(cmdp.get("P1"))
        if (not imagerepo) or cmdp.missing_options():    # syntax error
            return self.STATUS_ERROR

        self._set_repository(registry_url, index_url, imagerepo, http_proxy)
        v2_auth_token = self.keystore.get(self.dockerioapi.registry_url)
        self.dockerioapi.set_v2_login_token(v2_auth_token)
        if self.dockerioapi.get(imagerepo, tag, platform):
            return self.STATUS_OK

        Msg().err("Error: no files downloaded")
        return self.STATUS_ERROR

    def do_push(self, cmdp):
        """
        push: upload an image to a docker registry
        push [options] <repo/image:tag>
        --registry=<url>          :registry url e.g. quay.io
        --index=<url>             :docker index url
        --httpproxy=<proxy>       :use http proxy for registry access
        """
        index_url = cmdp.get("--index=")
        registry_url = cmdp.get("--registry=")
        http_proxy = cmdp.get("--httpproxy=")
        (imagerepo, tag) = self._check_imagespec(cmdp.get("P1"))
        if (not imagerepo) or cmdp.missing_options():    # syntax error
            return self.STATUS_ERROR

        self._set_repository(registry_url, index_url, imagerepo, http_proxy)
        v2_auth_token = self.keystore.get(self.dockerioapi.registry_url)
        self.dockerioapi.set_v2_login_token(v2_auth_token)
        if self.dockerioapi.push(imagerepo, tag):
            Msg().out("Info: image pushed:", imagerepo + ":" + tag, l=Msg.INF)
            return self.STATUS_OK

        Msg().err("Error: pushing image")
        return self.STATUS_ERROR

    def _create(self, imagespec):
        """Auxiliary to create(), performs the creation"""
        if not self.dockerioapi.is_repo_name(imagespec):
            Msg().err("Error: must specify image:tag or repository/image:tag")
            return False
        (imagerepo, tag) = self._check_imagespec(imagespec)
        if imagerepo:
            return ContainerStructure(self.localrepo).create_fromimage(
                imagerepo, tag)
        return False

    NAMES_ADJECTIVES = ("brave", "calm", "eager", "fancy", "gentle",
                        "happy", "jolly", "keen", "lucid", "merry",
                        "noble", "proud", "quick", "quiet", "vivid", "wise")
    NAMES_NOUNS = ("bohr", "curie", "darwin", "euler", "fermi", "gauss",
                   "hopper", "kepler", "lovelace", "noether", "pascal",
                   "ritchie", "shannon", "turing", "volta", "wozniak")

    def _generated_container_name(self):
        """Docker style random container name (adjective_scientist)"""
        for dummy in range(20):
            name = "%s_%s" % (random.choice(self.NAMES_ADJECTIVES),
                              random.choice(self.NAMES_NOUNS))
            if not self.localrepo.get_container_id(name):
                return name
        return "container_" + Unique().imagename()

    def do_create(self, cmdp):
        """
        create: extract image layers and create a container
        create [options]  <repo/image:tag>
        --name=<container-name>    :set or change the name of the container
        --force                    :allow create even if name already exists
        """
        imagespec = cmdp.get("P1")
        name = cmdp.get("--name=")
        labels = cmdp.get("--label=", "CMD_OPT", True)
        force = cmdp.get("--force")
        if cmdp.missing_options():               # syntax error
            return self.STATUS_ERROR
        if not force:
            if name and self.localrepo.get_container_id(name):
                Msg().err("Error: container name already exists")
                return self.STATUS_ERROR
        container_id = self._create(imagespec)
        if container_id:
            self._save_labels(self.localrepo.cd_container(container_id),
                              labels)
            if not name:
                name = self._generated_container_name()
            Msg().out(container_id)
            if name and not self.localrepo.set_container_name(container_id,
                                                              name):
                if not force:
                    Msg().err("Error: invalid container name or wrong format")
                    return self.STATUS_ERROR
            return self.STATUS_OK
        return self.STATUS_ERROR

    def _get_run_options(self, cmdp, exec_engine=None):
        """Read command line options into variables"""
        cmdp.declare_options("-v= -e= -w= -u= -p= -i -t -a -P "
                             "--dns= --dns-search= --volumes-from=")
        cmd_options = {
            "netcoop": {
                "fl": ("-P", "--publish-all", "--netcoop",), "act": "R",
                "p2": "CMD_OPT", "p3": False
            },
            "portsmap": {
                "fl": ("-p=", "--publish=",), "act": "E",
                "p2": "CMD_OPT", "p3": True
            },
            "novol": {
                "fl": ("--novol=",), "act": "R",
                "p2": "CMD_OPT", "p3": True
            },
            "vol": {
                "fl": ("-v=", "--volume=",), "act": "E",
                "p2": "CMD_OPT", "p3": True
            },
            "env": {
                "fl": ("-e=", "--env=",), "act": "E",
                "p2": "CMD_OPT", "p3": True
            },
            "envfile": {
                "fl": ("--env-file=",), "act": 'E',
                "p2": "CMD_OPT", "p3": True
            },
            "user": {
                "fl": ("-u=", "--user=",), "act": "R",
                "p2": "CMD_OPT", "p3": False
            },
            "cwd": {
                "fl": ("-w=", "--workdir=",), "act": "R",
                "p2": "CMD_OPT", "p3": False
            },
            "entryp": {
                "fl": ("--entrypoint=",), "act": "R",
                "p2": "CMD_OPT", "p3": False
            },
            "cpuset": {
                "fl": ("--cpuset-cpus=",), "act": "R",
                "p2": "CMD_OPT", "p3": False
            },
            "hostauth": {
                "fl": ("--hostauth",), "act": "R",
                "p2": "CMD_OPT", "p3": False
            },
            "containerauth": {
                "fl": ("--containerauth",), "act": 'R',
                "p2": "CMD_OPT", "p3": False
            },
            "nosysdirs": {
                "fl": ("--nosysdirs",), "act": "R",
                "p2": "CMD_OPT", "p3": False
            },
            "hostenv": {
                "fl": ("--hostenv",), "act": "R",
                "p2": "CMD_OPT", "p3": False
            },
            "bindhome": {
                "fl": ("--bindhome",), "act": "R",
                "p2": "CMD_OPT", "p3": False
            },
            "nometa": {
                "fl": ("--nometa",), "act": "R",
                "p2": "CMD_OPT", "p3": False
            },
            "dri": {
                "fl": ("--dri",), "act": "R",
                "p2": "CMD_OPT", "p3": False
            },
            "cmd": {
                "fl": ("P+",), "act": "R",
                "p2": "CMD_OPT", "p3": False
            },
            "volfrom": {
                "fl": ("--volumes-from=",), "act": "E",
                "p2": "CMD_OPT", "p3": True
            },
            "dns": {
                "fl": ("--dns=",), "act": "E",
                "p2": "CMD_OPT", "p3": True
            },
            "dnssearch": {
                "fl": ("--dns-search=",), "act": "E",
                "p2": "CMD_OPT", "p3": True
            },
            "tty": {
                "fl": ("-t", "--tty"), "act": "R",
                "p2": "CMD_OPT", "p3": False
            },
            "interactive": {
                "fl": ("-i", "--interactive"), "act": "R",
                "p2": "CMD_OPT", "p3": False
            },
            "kernel": {
                "fl": ("--kernel=",), "act": "R",
                "p2": "CMD_OPT", "p3": False
            },
            "devices": {
                "fl": ("--device=",), "act": "E",
                "p2": "CMD_OPT", "p3": True
            },
            "hostname": {
                "fl": ("--hostname=",), "act": 'R',
                "p2": "CMD_OPT", "p3": False
            },
            "addhost": {
                "fl": ("--add-host=",), "act": 'E',
                "p2": "CMD_OPT", "p3": True
            },
            "labels": {
                "fl": ("--label=",), "act": 'E',
                "p2": "CMD_OPT", "p3": True
            },
            "ulimit": {
                "fl": ("--ulimit=",), "act": 'E',
                "p2": "CMD_OPT", "p3": True
            },
            "stopsignal": {
                "fl": ("--stop-signal=",), "act": 'R',
                "p2": "CMD_OPT", "p3": False
            },
            "stoptimeout": {
                "fl": ("--stop-timeout=",), "act": 'R',
                "p2": "CMD_OPT", "p3": False
            },
            "nobanner": {
                "fl": ("--nobanner",), "act": 'R',
                "p2": "CMD_OPT", "p3": False
            },
            "banner": {
                "fl": ("--banner",), "act": 'R',
                "p2": "CMD_OPT", "p3": False
            },
            "platform": {
                "fl": ("--platform=",), "act": 'R',
                "p2": "CMD_OPT", "p3": False
            },
            "pull": {
                "fl": ("--pull="), "act": 'R',
                "p2": "CMD_OPT", "p3": False
            }
        }
        for option, cmdp_args in list(cmd_options.items()):
            last_value = None
            for cmdp_fl in cmdp_args["fl"]:
                option_value = cmdp.get(cmdp_fl, cmdp_args["p2"],
                                        cmdp_args["p3"])
                if not exec_engine:
                    continue
                if cmdp_args["act"] == "R":   # action is replace
                    if option_value or last_value is None:
                        exec_engine.opt[option] = option_value
                elif cmdp_args["act"] == "E":   # action is extend
                    exec_engine.opt.setdefault(option, []).extend(
                        option_value)
                last_value = option_value
        if exec_engine:
            exec_engine.opt["nobanner"] = not bool(
                exec_engine.opt.get("banner"))

    def do_run(self, cmdp):
        """
        run: execute a container
        run [options] <container-id-or-name>
        run [options] <repo/image:tag>
        --rm                       :delete container upon exit
        --workdir=/home/userXX     :working directory set to /home/userXX
        --user=userXX              :run as userXX
        --user=root                :run as root
        --volume=/data:/mnt        :mount host directory /data in /mnt
        --volume=<name>:/mnt       :mount named volume <name> in /mnt
        --novol=/proc              :remove /proc from list of volumes to mount
        --env="MYTAG=xxx"          :set environment variable
        --env-file=<file>          :read environment variables from file
        --hostauth                 :get user account and group from host
        --containerauth            :use container passwd and group directly
        --nosysdirs                :do not bind the host /proc /sys /run /dev
        --nometa                   :ignore container metadata
        --dri                      :bind directories relevant for dri graphics
        --hostenv                  :pass the host environment to the container
        --cpuset-cpus=<1,2,3-4>    :CPUs in which to allow execution
        --name=<container-name>    :set or change the name of the container
        --bindhome                 :bind the home directory into the container
        --kernel=<kernel-id>       :simulate this Linux kernel version
        --device=/dev/xxx          :pass device to container (R1 mode only)
        --location=<container-dir> :use container outside the repository
        --banner                   :print the container startup banner
        --entrypoint               :override the container metadata entrypoint
        --platform=os/arch         :pull image for OS and architecture
        --pull=<when>              :when to pull (missing|never|always|reuse)
        --httpproxy=<proxy>        :use http proxy, see udocker pull --help
        -d, --detach               :run in background (all execution modes)
        -i, --interactive          :keep stdin attached when it is not a tty
        -t, --tty                  :allocate a pseudo terminal
        --dns=<addr>               :set the container DNS server (repeatable)
        --dns-search=<domain>      :set the container DNS search domain
        --volumes-from=<container> :copy volume bindings of a container
        --hostname=<name>          :set the container hostname
        --add-host=<host:ip>       :add a line to the container /etc/hosts
        --label=<key=value>        :set a container label (repeatable)
        --ulimit=<name=soft[:hard]>:set a resource limit (repeatable)
        --stop-signal=<signal>     :signal sent by stop (default image value)
        --stop-timeout=<seconds>   :seconds stop waits before killing

        Only available in Rn execution modes:
        --device=/dev/xxx          :pass device to container (R1 mode only)

        Port publishing:
        --publish=<hport:cport>    :map container TCP/IP <cport> into <hport>
        --publish-all              :map the exposed ports to random host ports
        In Pn modes publishing is done by PRoot, in Fn/Rn/Sn modes -p is
        implemented with a userspace TCP forwarder (no privileges needed).

        run <container-id-or-name> executes an existing container, previously
        created from an image by using: create <repo/image:tag>

        run <repo/image:tag> always creates a new container from the image.
        If needed the image is pulled. This is slow and may waste storage.
        Using run --name=<container-name> --pull=reuse allows to use existing
        container and only pull/create if the <container-name> does not exist.
        """
        self._get_run_options(cmdp)
        detach = cmdp.get("-d") or cmdp.get("--detach")
        container_or_image = cmdp.get("P1")
        Config.conf['location'] = cmdp.get("--location=")
        delete = cmdp.get("--rm")
        name = cmdp.get("--name=")
        pull = cmdp.get("--pull=")
        cmdp.get("--pull")          # if invoked without option
        cmdp.get("--index=")        # used in do_pull()
        cmdp.get("--registry=")     # used in do_pull()
        cmdp.get("--httpproxy=")    # used in do_pull()

        if cmdp.missing_options():  # syntax error
            return self.STATUS_ERROR

        container_id = ""
        if Config.conf['location']:
            pass
        elif not container_or_image:
            Msg().err("Error: must specify container_id or image:tag")
            return self.STATUS_ERROR
        else:
            if pull == "reuse" and name:
                container_id = self.localrepo.get_container_id(name)
            created = False
            if not container_id:
                container_id = self.localrepo.get_container_id(container_or_image)
            if not container_id:
                (imagerepo, tag) = self._check_imagespec(container_or_image)
                if (imagerepo and
                        self.localrepo.cd_imagerepo(imagerepo, tag)):
                    container_id = self._create(imagerepo + ":" + tag)
                    created = bool(container_id)
                if pull != "never" and (not container_id or pull == "always"):
                    self.do_pull(cmdp)
                    if self.localrepo.cd_imagerepo(imagerepo, tag):
                        container_id = self._create(imagerepo + ":" + tag)
                        created = bool(container_id)
                    if not container_id:
                        Msg().err("Error: image or container not available")
                        return self.STATUS_ERROR
            if created and not name:
                name = self._generated_container_name()
            if name and container_id:
                if not self.localrepo.set_container_name(container_id, name):
                    if pull != "reuse":
                        Msg().err("Error: invalid container name")
                        return self.STATUS_ERROR

        exec_mode = ExecutionMode(self.localrepo, container_id)
        exec_engine = exec_mode.get_engine()
        if not exec_engine:
            Msg().err("Error: no execution engine for this execmode")
            return self.STATUS_ERROR

        self._get_run_options(cmdp, exec_engine)
        opt = exec_engine.opt
        if not isinstance(opt, dict):
            opt = {}
        container_dir = ""
        if not Config.conf['location']:
            container_dir = self.localrepo.cd_container(container_id)
        if not self._expand_volumes_from(exec_engine):
            return self.STATUS_ERROR
        self._save_run_volumes(container_dir, opt.get("vol") or [])
        self._save_run_command(container_dir, opt)
        self._save_labels(container_dir, opt.get("labels") or [])
        self._save_stop_config(
            container_dir,
            opt.get("stopsignal") or self._image_stop_signal(container_dir)
            or "SIGTERM",
            opt.get("stoptimeout"))
        if not self._expand_publish_all(exec_engine, container_id):
            return self.STATUS_ERROR
        portsmap = opt.get("portsmap") or []
        if detach:
            if opt.get("interactive"):
                Msg().out("Warning: -i is ignored with -d: there is no "
                          "terminal to attach to", l=Msg.WAR)
            return self._run_detached(container_id, container_dir,
                                      container_or_image, exec_mode, delete,
                                      ports=portsmap,
                                      netcoop=bool(opt.get("netcoop")))
        forwarder = self._start_port_forwarder(exec_engine, exec_mode)
        if forwarder is False:
            Msg().err("Error: cannot publish container ports")
            return self.STATUS_ERROR
        self._write_state(container_dir, "running", ports=portsmap)
        saved_limits = []
        if opt.get("ulimit"):
            try:
                ulimits_util.parse_all(opt["ulimit"])
                if not str(exec_mode.get_mode()).startswith("R"):
                    saved_limits = ulimits_util.apply(opt["ulimit"])
            except ValueError as error:
                Msg().err("Error: invalid --ulimit:", str(error))
                return self.STATUS_ERROR
        try:
            exit_status = exec_engine.run(container_id)
        except BaseException:
            if forwarder:
                forwarder.stop()
            self._write_state(container_dir, "interrupted")
            raise
        finally:
            ulimits_util.restore(saved_limits)
        if not isinstance(exit_status, int) or getattr(
                exec_engine, "exit_code", 0) == 127:
            exit_status = 127 if getattr(
                exec_engine, "exit_code", 0) == 127 else 1
        if forwarder:
            forwarder.stop()
        self._write_state(container_dir, "exited", exitcode=exit_status)
        if delete and not self.localrepo.isprotected_container(container_id):
            self.localrepo.del_container(container_id)

        return exit_status

    def _detach_argv(self, container_id, container_or_image,
                     ports=None, netcoop=False):
        """Build the monitor command line from this invocation"""
        cleaned = []
        skip_next = False
        for arg in list(sys.argv):
            if skip_next:
                skip_next = False
                continue
            if arg in ("-d", "--detach"):
                continue
            if arg == "--name":
                skip_next = True
                continue
            if arg.startswith("--name="):
                continue
            cleaned.append(arg)
        if not cleaned:
            return []
        rest = cleaned[1:]
        try:
            run_index = rest.index("run")
        except ValueError:
            return []
        if "--nobanner" not in rest:
            rest.insert(run_index + 1, "--nobanner")
        # -P was expanded by the parent: hand the explicit mappings to the
        # monitor so it does not pick a different set of random ports
        if not netcoop:
            rest = [arg for arg in rest
                    if arg not in ("-P", "--publish-all", "--netcoop")]
            for offset, mapping in enumerate(ports or []):
                rest.insert(run_index + 1 + offset,
                            "--publish=%s" % mapping)
        if container_or_image:
            for position in range(run_index + 1, len(rest)):
                if rest[position] == container_or_image:
                    rest[position] = container_id
                    break
        return rest

    def _run_detached(self, container_id, container_dir,
                      container_or_image, exec_mode, delete,
                      ports=None, netcoop=False):
        """Start a container in the background under the supervisor"""
        if self.localrepo.iswriteable_container(container_id) != 1:
            Msg().err("Error: container is not writable")
            return self.STATUS_ERROR
        if supervisor.is_running(container_dir):
            Msg().err("Error: container is already running")
            return self.STATUS_ERROR
        argv = self._detach_argv(container_id, container_or_image,
                                 ports, netcoop)
        if not argv:
            Msg().err("Error: cannot build the supervisor command line")
            return self.STATUS_ERROR
        if not supervisor.spawn(container_id, container_dir, argv):
            return self.STATUS_ERROR
        Msg().out(container_id)
        return self.STATUS_OK

    def _runc_engine(self, container_id):
        """Return the runc engine and its executable for a container"""
        exec_mode = ExecutionMode(self.localrepo, container_id)
        mode = exec_mode.get_mode()
        if not (isinstance(mode, str) and mode.startswith("R")):
            Msg().err("Error: this command requires an Rn execution mode")
            return (None, "")
        engine = exec_mode.get_engine()
        if not engine or not hasattr(engine, "select_runc"):
            Msg().err("Error: runc/crun engine not available")
            return (None, "")
        engine.select_runc()
        return (engine, engine.executable)

    def _is_runc_mode(self, container_id):
        """Is the container configured for an Rn execution mode"""
        mode = ExecutionMode(self.localrepo, container_id).get_mode()
        return isinstance(mode, str) and mode.startswith("R")

    def _resolve_container(self, arg):
        """Resolve a container id or name, print an error if missing"""
        if not arg:
            Msg().err("Error: must specify a container")
            return ""
        container_id = self.localrepo.get_container_id(arg)
        if not container_id:
            Msg().err("Error: container not found:", arg)
        return container_id

    def _stop_container(self, container_id, timeout, stop_signal="SIGTERM"):
        """Stop a container with runc/crun or with the monitor signals"""
        container_dir = self.localrepo.cd_container(container_id)
        if self._is_runc_mode(container_id):
            (dummy, executable) = self._runc_engine(container_id)
            if not executable:
                return self.STATUS_ERROR
            status = supervisor.stop(container_dir, executable, timeout,
                                     Config.conf['topdir'], sig=stop_signal)
        else:
            status = supervisor.stop_monitor(container_dir, timeout,
                                             sig=stop_signal)
        if status != 0:
            Msg().err("Error: cannot stop container")
            return self.STATUS_ERROR
        return self.STATUS_OK

    def do_start(self, cmdp):
        """
        start: start a container that was created with run -d
        start <container-id-or-name>
        """
        container_id = self._resolve_container(cmdp.get("P1"))
        if cmdp.missing_options() or not container_id:
            return self.STATUS_ERROR
        container_dir = self.localrepo.cd_container(container_id)
        conf = supervisor.read_conf(container_dir)
        if not conf.get("argv"):
            Msg().err("Error: container was not started with -d")
            return self.STATUS_ERROR
        if supervisor.read_state(container_dir).get("status") == "paused":
            Msg().err("Error: container is paused;"
                      " unpause it before restarting:", container_id)
            return self.STATUS_ERROR
        if supervisor.is_running(container_dir):
            Msg().err("Error: container is already running")
            return self.STATUS_ERROR
        if self._is_runc_mode(container_id):
            (dummy, executable) = self._runc_engine(container_id)
            if not executable:
                return self.STATUS_ERROR
        if not supervisor.spawn(container_id, container_dir,
                                conf["argv"], truncate=False):
            return self.STATUS_ERROR
        Msg().out(container_id)
        return self.STATUS_OK

    def do_pause(self, cmdp):
        """
        pause: pause all processes of a running container
        pause <container-id-or-name>
        """
        container_id = self._resolve_container(cmdp.get("P1"))
        if cmdp.missing_options() or not container_id:
            return self.STATUS_ERROR
        container_dir = self.localrepo.cd_container(container_id)
        state = supervisor.read_state(container_dir)
        if state.get("status") == "paused":
            Msg().err("Error: container is already paused:", container_id)
            return self.STATUS_ERROR
        if not supervisor.is_running(container_dir):
            Msg().err("Error: container is not running:", container_id)
            return self.STATUS_ERROR
        if not supervisor.pause(container_dir):
            Msg().err("Error: cannot pause container:", container_id)
            return self.STATUS_ERROR
        Msg().out(container_id)
        return self.STATUS_OK

    def do_unpause(self, cmdp):
        """
        unpause: resume a paused container
        unpause <container-id-or-name>
        """
        container_id = self._resolve_container(cmdp.get("P1"))
        if cmdp.missing_options() or not container_id:
            return self.STATUS_ERROR
        container_dir = self.localrepo.cd_container(container_id)
        state = supervisor.read_state(container_dir)
        if state.get("status") != "paused":
            Msg().err("Error: container is not paused:", container_id)
            return self.STATUS_ERROR
        if not supervisor.unpause(container_dir):
            Msg().err("Error: cannot unpause container:", container_id)
            return self.STATUS_ERROR
        Msg().out(container_id)
        return self.STATUS_OK

    def do_stop(self, cmdp):
        """
        stop: stop a running container
        stop [options] <container-id-or-name>
        -t, --time=<seconds>       :seconds to wait before killing (default 10)
        """
        timeout = cmdp.get("-t=") or cmdp.get("--time=")
        container_id = self._resolve_container(cmdp.get("P1"))
        if cmdp.missing_options() or not container_id:
            return self.STATUS_ERROR
        container_dir = self.localrepo.cd_container(container_id)
        stop_config = self._stop_config(container_dir)
        timeout = timeout or stop_config.get("timeout") or 10
        stop_signal = stop_config.get("signal") or "SIGTERM"
        if not supervisor.is_running(container_dir):
            Msg().out("Info: container is not running", container_id,
                      l=Msg.INF)
            return self.STATUS_OK
        if supervisor.read_state(container_dir).get("status") == "paused":
            Msg().err("Error: container is paused;"
                      " unpause it before stopping:", container_id)
            return self.STATUS_ERROR
        if self._stop_container(container_id, timeout, stop_signal) != 0:
            return self.STATUS_ERROR
        Msg().out(container_id)
        return self.STATUS_OK

    def do_restart(self, cmdp):
        """
        restart: stop and start a container created with run -d
        restart [options] <container-id-or-name>
        -t, --time=<seconds>       :seconds to wait before killing (default 10)
        """
        timeout = cmdp.get("-t=") or cmdp.get("--time=")
        container_id = self._resolve_container(cmdp.get("P1"))
        if cmdp.missing_options() or not container_id:
            return self.STATUS_ERROR
        container_dir = self.localrepo.cd_container(container_id)
        stop_config = self._stop_config(container_dir)
        timeout = timeout or stop_config.get("timeout") or 10
        stop_signal = stop_config.get("signal") or "SIGTERM"
        conf = supervisor.read_conf(container_dir)
        if not conf.get("argv"):
            Msg().err("Error: container was not started with -d")
            return self.STATUS_ERROR
        if supervisor.read_state(container_dir).get("status") == "paused":
            Msg().err("Error: container is paused;"
                      " unpause it before restarting:", container_id)
            return self.STATUS_ERROR
        if self._is_runc_mode(container_id):
            (dummy, executable) = self._runc_engine(container_id)
            if not executable:
                return self.STATUS_ERROR
        if supervisor.is_running(container_dir):
            if self._stop_container(container_id, timeout,
                                    stop_signal) != 0:
                return self.STATUS_ERROR
        if not supervisor.spawn(container_id, container_dir,
                                conf["argv"], truncate=False):
            return self.STATUS_ERROR
        Msg().out(container_id)
        return self.STATUS_OK

    def do_kill(self, cmdp):
        """
        kill: send a signal to a running container
        kill [options] <container-id-or-name>
        -s, --signal=<signal>      :signal to send (default KILL)
        """
        sig = cmdp.get("-s=") or cmdp.get("--signal=") or "KILL"
        container_id = self._resolve_container(cmdp.get("P1"))
        if cmdp.missing_options() or not container_id:
            return self.STATUS_ERROR
        container_dir = self.localrepo.cd_container(container_id)
        if not supervisor.is_running(container_dir):
            Msg().err("Error: container is not running")
            return self.STATUS_ERROR
        if self._is_runc_mode(container_id):
            (dummy, executable) = self._runc_engine(container_id)
            if not executable:
                return self.STATUS_ERROR
            status = supervisor.kill(container_dir, executable, sig,
                                     Config.conf['topdir'])
        else:
            status = supervisor.signal_monitor(container_dir, sig)
            if (status == 0 and
                    str(sig).upper().replace("SIG", "") in ("KILL", "9")):
                supervisor.wait_stopped(container_dir, 3)
                supervisor.reconcile(container_dir)
        if status != 0:
            Msg().err("Error: cannot signal container")
            return self.STATUS_ERROR
        Msg().out(container_id)
        return self.STATUS_OK

    def do_exec(self, cmdp):
        """
        exec: execute a command inside a running container
        exec [options] <container-id-or-name> <command> [args]
        -u, --user=<user>          :run as user or uid[:gid]
        -w, --workdir=<dir>        :working directory in the container
        -e, --env=<VAR=VALUE>      :set environment variable (repeatable)
        -t                         :allocate a tty
        """
        cmdp.declare_options("-u= -w= -e= -t -i")
        user = cmdp.get("-u=") or cmdp.get("--user=")
        workdir = cmdp.get("-w=") or cmdp.get("--workdir=")
        env_vars = cmdp.get("-e=", "CMD_OPT", True)
        env_vars.extend(cmdp.get("--env=", "CMD_OPT", True))
        tty = bool(cmdp.get("-t")) and sys.stdout.isatty()
        cmdp.get("-i")
        container_id = self._resolve_container(cmdp.get("P1"))
        command = cmdp.get("P+")
        if cmdp.missing_options() or not container_id:
            return self.STATUS_ERROR
        if not command:
            Msg().err("Error: must specify a command to execute")
            return self.STATUS_ERROR
        container_dir = self.localrepo.cd_container(container_id)
        if not supervisor.is_running(container_dir):
            Msg().err("Error: container is not running")
            return self.STATUS_ERROR
        (engine, executable) = self._runc_engine(container_id)
        if not executable:
            return self.STATUS_ERROR
        run_user = ""
        if user:
            run_user = supervisor.resolve_user(container_dir, user)
            if not run_user:
                Msg().err("Error: user not found in container:", user)
                return self.STATUS_ERROR
        return supervisor.exec_command(
            container_dir, executable, command, user=run_user,
            workdir=workdir, env_vars=env_vars, tty=tty,
            topdir=Config.conf['topdir'])

    def do_logs(self, cmdp):
        """
        logs: print the stdout/stderr log of a container started with -d
        logs [options] <container-id-or-name>
        -f, --follow               :follow log output
        --tail=<lines>             :number of lines from the end
        """
        follow = cmdp.get("-f") or cmdp.get("--follow")
        tail = cmdp.get("--tail=")
        container_id = self._resolve_container(cmdp.get("P1"))
        if cmdp.missing_options() or not container_id:
            return self.STATUS_ERROR
        container_dir = self.localrepo.cd_container(container_id)
        return supervisor.logs(container_dir, follow, tail)

    def do_wait(self, cmdp):
        """
        wait: wait for a container to stop and print its exit code
        wait [options] <container-id-or-name>
        --timeout=<seconds>        :give up after this timeout
        """
        timeout = cmdp.get("--timeout=")
        container_id = self._resolve_container(cmdp.get("P1"))
        if cmdp.missing_options() or not container_id:
            return self.STATUS_ERROR
        container_dir = self.localrepo.cd_container(container_id)
        supervisor.reconcile(container_dir)
        exitcode = supervisor.wait(container_dir, timeout)
        if exitcode is None:
            Msg().err("Error: timeout waiting for container")
            return self.STATUS_ERROR
        Msg().out(exitcode)
        return self.STATUS_OK

    def _prune_force(self, cmdp):
        """Accept -f/--force before or after a prune subcommand"""
        force = bool(cmdp.get("-f") or cmdp.get("--force"))
        for position in ("P2", "P3"):
            if cmdp.get(position) in ("-f", "--force"):
                force = True
        return force

    def do_top(self, cmdp):
        """
        top: display the running processes of a container
        top <container-id-or-name> [ps options]
        """
        container_id = self._resolve_container(cmdp.get("P1"))
        ps_args = cmdp.get("P+")
        if cmdp.missing_options() or not container_id:
            return self.STATUS_ERROR
        container_dir = self.localrepo.cd_container(container_id)
        return extras.print_top(container_dir, container_id, ps_args)

    def do_stats(self, cmdp):
        """
        stats: display a resource usage snapshot of containers
        stats [container-id-or-name ...]
        """
        names = cmdp.get("P*")
        if cmdp.missing_options():
            return self.STATUS_ERROR
        if not names:
            containers = [(item[0], self.localrepo.cd_container(item[0]))
                          for item in self.localrepo.get_containers_list(False)]
        else:
            containers = []
            for name in names:
                container_id = self._resolve_container(name)
                if not container_id:
                    return self.STATUS_ERROR
                containers.append((container_id,
                                   self.localrepo.cd_container(container_id)))
        return extras.print_stats(containers)

    def do_diff(self, cmdp):
        """
        diff: inspect changes to a container filesystem
        diff <container-id-or-name>
        """
        container_id = self._resolve_container(cmdp.get("P1"))
        if cmdp.missing_options() or not container_id:
            return self.STATUS_ERROR
        return extras.print_diff(self.localrepo, container_id)

    def do_port(self, cmdp):
        """
        port: list the published ports of a container
        port <container-id-or-name> [private-port[/proto]]
        """
        container_id = self._resolve_container(cmdp.get("P1"))
        mapping = cmdp.get("P2")
        if cmdp.missing_options() or not container_id:
            return self.STATUS_ERROR
        container_dir = self.localrepo.cd_container(container_id)
        return extras.print_ports(container_dir, mapping)

    def do_system(self, cmdp):
        """
        system: udocker data management
        system df                  :show disk usage
        system prune [-f]          :remove stopped containers and unused images
        """
        subcmd = cmdp.get("P1")
        if subcmd == "df":
            if cmdp.missing_options():
                return self.STATUS_ERROR
            return extras.print_system_df(self.localrepo)
        if subcmd == "prune":
            force = self._prune_force(cmdp)
            if cmdp.missing_options():
                return self.STATUS_ERROR
            return extras.system_prune(self.localrepo, "all", force)
        if not subcmd:
            Msg().err("Error: system requires a subcommand: df, prune")
            return self.STATUS_ERROR
        if cmdp.missing_options():
            return self.STATUS_ERROR
        Msg().err("Error: unknown system subcommand:", subcmd)
        return self.STATUS_ERROR

    def do_image(self, cmdp):
        """
        image: image management
        image prune [-f]           :remove images not used by containers
        """
        subcmd = cmdp.get("P1")
        if subcmd == "prune":
            force = self._prune_force(cmdp)
            if cmdp.missing_options():
                return self.STATUS_ERROR
            return extras.system_prune(self.localrepo, "images", force)
        if subcmd in (None, "ls", "list"):
            Msg().err("Error: use 'udocker images' to list images")
            return self.STATUS_ERROR
        if cmdp.missing_options():
            return self.STATUS_ERROR
        Msg().err("Error: unknown image subcommand:", subcmd)
        return self.STATUS_ERROR

    def do_prune(self, cmdp):
        """
        prune: remove stopped containers and unused images
        prune [-f]
        """
        force = self._prune_force(cmdp)
        if cmdp.missing_options():
            return self.STATUS_ERROR
        return extras.system_prune(self.localrepo, "all", force)

    NETWORKS = ("host", "none")

    def _network_data(self, name):
        """Docker shaped metadata of a rootless network"""
        if name not in self.NETWORKS:
            return None
        driver = "host" if name == "host" else "null"
        network_id = hashlib.sha256(name.encode()).hexdigest()[:12]
        return {
            "Name": name,
            "Id": network_id,
            "Created": "",
            "Scope": "local",
            "Driver": driver,
            "EnableIPv6": False,
            "IPAM": {"Driver": "default", "Options": {}, "Config": []},
            "Internal": False,
            "Attachable": False,
            "Ingress": False,
            "ConfigFrom": {"Network": ""},
            "ConfigOnly": False,
            "Containers": {},
            "Options": {},
            "Labels": {},
        }

    def do_network(self, cmdp):
        """
        network: manage docker networks (rootless: host and none only)
        network ls [--format=json]     :list the available networks
        network inspect <name> [<name>]:print network metadata
        network create|rm|connect|disconnect :not available without root
        """
        raw = cmdp.get("P*") or []
        subcmd = raw[0] if raw else None
        args = []
        output_format = ""
        index = 1
        while index < len(raw):
            arg = raw[index]
            if arg.startswith("--format="):
                output_format = arg.split("=", 1)[1]
            elif arg.startswith("-f="):
                output_format = arg.split("=", 1)[1]
            elif arg in ("--format", "-f") and index + 1 < len(raw):
                index += 1
                output_format = raw[index]
            elif not arg.startswith("-"):
                args.append(arg)
            index += 1
        if subcmd in ("ls", "list"):
            networks = [self._network_data(name)
                        for name in self.NETWORKS]
            if output_format == "json":
                for network in networks:
                    Msg().out(json.dumps(network, sort_keys=True))
            elif output_format and output_format != "table":
                for network in networks:
                    Msg().out(render_template(output_format, network))
            else:
                Msg().out("%-14s %-10s %-10s %s" %
                          ("NETWORK ID", "NAME", "DRIVER", "SCOPE"))
                for network in networks:
                    Msg().out("%-14.14s %-10s %-10s %s" %
                              (network["Id"], network["Name"],
                               network["Driver"], network["Scope"]))
            return self.STATUS_OK
        if subcmd == "inspect":
            if not args:
                Msg().err("Error: network inspect requires a name")
                return self.STATUS_ERROR
            data = []
            for name in args:
                network = self._network_data(name)
                if network is None:
                    Msg().err("Error: no such network:", name)
                    return self.STATUS_ERROR
                data.append(network)
            if output_format and output_format not in ("json", "table"):
                for network in data:
                    Msg().out(render_template(output_format, network))
            else:
                Msg().out(json.dumps(data, sort_keys=True, indent=4))
            return self.STATUS_OK
        if subcmd in ("create", "rm", "remove", "connect", "disconnect",
                      "prune"):
            Msg().err("Error: network", subcmd, "is not available without"
                      " root/daemon; udocker uses the host network stack")
            return self.STATUS_ERROR
        if not subcmd:
            Msg().err("Error: network requires a subcommand: ls, inspect")
            return self.STATUS_ERROR
        Msg().err("Error: unknown network subcommand:", subcmd)
        return self.STATUS_ERROR

    def do_volume(self, cmdp):
        """
        volume: manage named volumes
        volume create [<name>]          :create a named volume
        volume ls [--format=json]       :list named volumes
        volume inspect <name> [<name>]  :print volume metadata as JSON
        volume rm [-f] <name> [<name>]  :remove named volumes
        volume prune [-f]               :remove volumes not used by containers
        """
        subcmd = cmdp.get("P1")
        args = cmdp.get("P*") or []
        args = args[1:]
        force = ("-f" in args) or ("--force" in args)
        names = [arg for arg in args if not arg.startswith("-")]
        if subcmd == "create":
            return self._volume_create(args)
        if subcmd in ("ls", "list"):
            return self._volume_ls("--format=json" in args)
        if subcmd == "inspect":
            return self._volume_inspect(names)
        if subcmd == "rm":
            return self._volume_rm(names, force)
        if subcmd == "prune":
            return self._volume_prune(force)
        if not subcmd:
            Msg().err("Error: volume requires a subcommand:"
                      " create, ls, inspect, rm, prune")
            return self.STATUS_ERROR
        Msg().err("Error: unknown volume subcommand:", subcmd)
        return self.STATUS_ERROR

    def _volume_create(self, args):
        """Create a named volume, like docker volume create"""
        driver = ""
        labels = {}
        names = []
        index = 0
        while index < len(args):
            arg = args[index]
            if arg in ("-d", "--driver"):
                index += 1
                if index >= len(args):
                    Msg().err("Error: option requires a value:", arg)
                    return self.STATUS_ERROR
                driver = args[index]
            elif arg.startswith("--driver=") or arg.startswith("-d="):
                driver = arg.split("=", 1)[1]
            elif arg.startswith("--label="):
                item = arg.split("=", 1)[1]
                (key, sep, value) = item.partition("=")
                if not sep or not key:
                    Msg().err("Error: invalid label, expected key=value:",
                              item)
                    return self.STATUS_ERROR
                labels[key] = value
            elif arg.startswith("-"):
                Msg().err("Error: unknown volume create option:", arg)
                return self.STATUS_ERROR
            else:
                names.append(arg)
            index += 1
        if driver and driver != "local":
            Msg().err("Error: only the local volume driver is available:",
                      driver)
            return self.STATUS_ERROR
        if len(names) > 1:
            Msg().err("Error: volume create accepts at most one name")
            return self.STATUS_ERROR
        name = names[0] if names else Unique().imagename()
        if not self.localrepo.volume_name_valid(name):
            Msg().err("Error: invalid volume name:", name)
            return self.STATUS_ERROR
        if not self.localrepo.create_volume(name, labels):
            Msg().err("Error: cannot create volume:", name)
            return self.STATUS_ERROR
        Msg().out(name)
        return self.STATUS_OK

    def _volume_ls(self, as_json=False):
        """List named volumes"""
        volumes = [self.localrepo.get_volume(name)
                   for name in self.localrepo.get_volumes_list()]
        if as_json:
            Msg().out(json.dumps(volumes, sort_keys=True))
            return self.STATUS_OK
        Msg().out("%-10s %s" % ("DRIVER", "VOLUME NAME"))
        for volume in volumes:
            Msg().out("%-10s %s" % (volume["Driver"], volume["Name"]))
        return self.STATUS_OK

    def _volume_inspect(self, names):
        """Print the metadata of named volumes as JSON"""
        if not names:
            Msg().err("Error: volume inspect requires at least one name")
            return self.STATUS_ERROR
        volumes = []
        for name in names:
            volume = self.localrepo.get_volume(name)
            if volume is None:
                Msg().err("Error: no such volume:", name)
                return self.STATUS_ERROR
            volumes.append(volume)
        Msg().out(json.dumps(volumes, indent=4, sort_keys=True))
        return self.STATUS_OK

    def _volume_rm(self, names, force=False):
        """Remove named volumes, refusing volumes still in use"""
        if not names:
            Msg().err("Error: volume rm requires at least one name")
            return self.STATUS_ERROR
        status = self.STATUS_OK
        for name in names:
            if not self.localrepo.is_volume(name):
                Msg().err("Error: no such volume:", name)
                status = self.STATUS_ERROR
                continue
            in_use = self.localrepo.get_volume_containers(name)
            if in_use and not force:
                Msg().err("Error: volume is in use:", name,
                          ",".join(in_use))
                status = self.STATUS_ERROR
                continue
            if not self.localrepo.del_volume(name):
                Msg().err("Error: cannot remove volume:", name)
                status = self.STATUS_ERROR
                continue
            Msg().out(name)
        return status

    def _volume_prune(self, force=False):
        """Remove the named volumes that no container references"""
        unused = [name for name in self.localrepo.get_volumes_list()
                  if not self.localrepo.get_volume_containers(name)]
        if not unused:
            Msg().out("Total reclaimed space: 0B")
            return self.STATUS_OK
        if not force:
            answer = extras._confirm(                        # pylint: disable=protected-access
                "WARNING! This will remove all volumes not used by any "
                "container. Are you sure you want to continue? [y/N] ")
            if answer is None:
                Msg().err("Error: prune requires -f when stdin is not a "
                          "terminal (use -f)")
                return self.STATUS_ERROR
            if not answer:
                Msg().out("Aborted")
                return self.STATUS_OK
        Msg().out("Deleted Volumes:")
        reclaimed = 0
        for name in unused:
            size = self.localrepo.get_volume_size(name)
            if size and size > 0:
                reclaimed += size * 1024 * 1024
            Msg().out(name)
            self.localrepo.del_volume(name)
        Msg().out("Total reclaimed space: %s" % extras.format_size(reclaimed))
        return self.STATUS_OK

    def do_compose(self, cmdp):
        """compose: run a multi-container project (see: udocker compose help)"""
        return compose.do_compose(self, cmdp)

    def _image_id(self):
        """Docker image id of the image selected with cd_imagerepo()"""
        manifest = self.localrepo.load_json("manifest")
        if isinstance(manifest, dict):
            config = manifest.get("config")
            if isinstance(config, dict) and config.get("digest"):
                return str(config["digest"])
            layers = manifest.get("layers")
            if isinstance(layers, list) and layers:
                last = layers[-1]
                if isinstance(last, dict) and last.get("digest"):
                    return str(last["digest"])
        ancestry = self.localrepo.load_json("ancestry")
        if isinstance(ancestry, list) and ancestry:
            return str(ancestry[-1])
        return ""

    def _image_row(self, imagerepo, tag, no_trunc=False):
        """Docker style row of one image tag"""
        self.localrepo.cd_imagerepo(imagerepo, tag)
        layers_list = self.localrepo.get_layers(imagerepo, tag)
        size = 0
        for (dummy, layer_size) in layers_list:
            size += layer_size
        container_json = None
        attrs = self.localrepo.get_image_attributes()
        if isinstance(attrs, (list, tuple)) and attrs:
            container_json = attrs[0]
        created = ""
        if isinstance(container_json, dict):
            created = container_json.get("created", "") or ""
        short_id = self._image_id()
        if not short_id:
            for (layer_path, dummy) in layers_list:
                short_id = os.path.basename(str(layer_path))
                if short_id.endswith(".layer"):
                    short_id = short_id[:-len(".layer")]
                if short_id:
                    break
        if short_id.startswith("sha256:"):
            short_id = short_id[len("sha256:"):]
        created_at = ""
        created_epoch = _parse_timestamp(created)
        if created_epoch is not None:
            created_at = time.strftime(
                "%Y-%m-%d %H:%M:%S +0000 UTC", time.gmtime(created_epoch))
        return {
            "repository": imagerepo,
            "tag": tag,
            "image_id": short_id if no_trunc else short_id[:12],
            "full_id": short_id,
            "created": _relative_time(created) if created else "N/A",
            "created_at": created_at,
            "size": size,
        }

    @staticmethod
    def _image_record(row):
        """Docker images --format json record of one image"""
        return {
            "Containers": "N/A",
            "CreatedAt": row.get("created_at", ""),
            "CreatedSince": row.get("created", ""),
            "Digest": "<none>",
            "ID": row.get("full_id", ""),
            "Repository": row.get("repository", ""),
            "SharedSize": "N/A",
            "Size": extras.format_size(row.get("size", 0)),
            "Tag": row.get("tag", ""),
            "UniqueSize": "N/A",
            "VirtualSize": extras.format_size(row.get("size", 0)),
        }

    def do_images(self, cmdp):
        """
        images: list container images
        images [options]
        -q, --quiet                :only display image ids
        -l                         :long format (udocker)
        -p                         :print platform (udocker)
        -a, --all                  :accepted for compatibility
        --no-trunc                 :don't truncate the image id
        --format=json              :print the image list as JSON
        """
        output_format = cmdp.get("--format=")
        quiet = bool(cmdp.get("-q") or cmdp.get("--quiet"))
        verbose = cmdp.get("-l")
        print_platform = cmdp.get("-p")
        no_trunc = bool(cmdp.get("--no-trunc"))
        dummy = cmdp.get("-a")
        dummy = cmdp.get("--all")
        if cmdp.missing_options():               # syntax error
            return self.STATUS_ERROR
        images_list = self.localrepo.get_imagerepos()

        if output_format == "json":
            for (imagerepo, tag) in images_list:
                row = self._image_row(imagerepo, tag, no_trunc)
                Msg().out(json.dumps(self._image_record(row),
                                     sort_keys=True))
            return self.STATUS_OK

        if output_format and output_format != "table":
            for (imagerepo, tag) in images_list:
                row = self._image_row(imagerepo, tag, no_trunc)
                Msg().out(render_template(output_format,
                                          self._image_record(row)))
            return self.STATUS_OK

        if verbose or print_platform:
            Msg().out("REPOSITORY", l=Msg.INF)
            for (imagerepo, tag) in images_list:
                prot = (".", "P")[
                    self.localrepo.isprotected_imagerepo(imagerepo, tag)]
                imagerepo_dir = self.localrepo.cd_imagerepo(imagerepo, tag)

                if print_platform:
                    platform = self.localrepo.get_image_platform_fmt()
                    Msg().out("%-18.18s %c %s" %
                              (platform, prot, imagerepo + ":" + tag))
                else:
                    Msg().out("%s    %c" % (imagerepo + ":" + tag, prot))

                if verbose:
                    Msg().out(" %s" % (imagerepo_dir))
                    layers_list = self.localrepo.get_layers(imagerepo, tag)
                    if layers_list:
                        for (layer_name, size) in layers_list:
                            file_size = size / (1024 * 1024)
                            if not file_size and size:
                                file_size = 1
                            Msg().out("    %s (%d MB)" %
                                      (layer_name.replace(imagerepo_dir, ""),
                                       file_size))
            return self.STATUS_OK

        rows = [self._image_row(imagerepo, tag, no_trunc)
                for (imagerepo, tag) in images_list]
        if quiet:
            for row in rows:
                Msg().out(row["full_id"])
            return self.STATUS_OK
        Msg().out("%-30s %-20s %-12s %-20s %s" %
                  ("REPOSITORY", "TAG", "IMAGE ID", "CREATED", "SIZE"))
        for row in rows:
            Msg().out("%-30s %-20s %-12s %-20s %s" % (
                row["repository"] or "<none>", row["tag"] or "<none>",
                row["image_id"] or "<none>", row["created"],
                extras.format_size(row["size"])))
        return self.STATUS_OK

    def do_ps(self, cmdp):
        """
        ps: list containers
        -a, --all                  :show all containers (default: running)
        -q, --quiet                :only display container ids
        -f, --filter=<key=value>   :filter by status, name, id or ancestor
        -s                         :show the container size
        --no-trunc                 :don't truncate output
        -m                         :print execution mode (udocker)
        -p                         :print platform (udocker)
        --format=json              :print the container list as JSON
        """
        filters = list(cmdp.get("-f=", "CMD_OPT", True))
        filters.extend(cmdp.get("--filter=", "CMD_OPT", True))
        output_format = cmdp.get("--format=")
        show_all = bool(cmdp.get("-a") or cmdp.get("--all"))
        quiet = bool(cmdp.get("-q") or cmdp.get("--quiet"))
        no_trunc = bool(cmdp.get("--no-trunc"))
        print_mode = cmdp.get("-m")
        print_size = cmdp.get("-s")
        print_platform = cmdp.get("-p")
        if cmdp.missing_options():               # syntax error
            return self.STATUS_ERROR

        containers = []
        for (container_id, image, names) in \
                self.localrepo.get_containers_list(False):
            container_dir = self.localrepo.cd_container(container_id) or ""
            supervisor.reconcile(container_dir)
            if isinstance(names, (list, tuple)):
                names = ",".join(names)
            status = self._container_status(container_dir)
            if isinstance(container_dir, (str, bytes)):
                try:
                    created_epoch = os.path.getmtime(
                        container_dir + "/container.json")
                except (IOError, OSError, TypeError):
                    created_epoch = 0.0
            else:
                created_epoch = 0.0
            containers.append({
                "container_id": container_id,
                "name": names,
                "image": image,
                "mode": ExecutionMode(self.localrepo,
                                      container_id).get_mode(),
                "protected": bool(self.localrepo.isprotected_container(
                    container_id)),
                "writable": self.localrepo.iswriteable_container(container_id),
                "size": self.localrepo.get_size(container_id),
                "platform": ContainerStructure(
                    self.localrepo,
                    container_id).get_container_platform_fmt(),
                "status": status,
                "docker_status": _docker_status(container_dir, status),
                "command": _container_command(container_dir, no_trunc),
                "created": (_human_duration(time.time() - created_epoch) +
                            " ago" if created_epoch else ""),
                "created_epoch": created_epoch,
                "ports": _docker_ports(_read_state(container_dir).get("ports")),
                "labels": _container_labels(container_dir),
            })

        status_filter = [item.split("=", 1)[1] for item in filters
                         if item.startswith("status=")]
        selected = []
        for container in containers:
            if (not show_all and not status_filter and
                    container["status"] not in ("Running", "Paused")):
                continue
            if filters and not _filter_match(container, filters):
                continue
            selected.append(container)
        selected.sort(key=lambda item: item.get("created_epoch", 0),
                      reverse=True)

        if output_format == "json":
            for container in selected:
                Msg().out(json.dumps(self._ps_record(container),
                                     sort_keys=True))
            return self.STATUS_OK

        if output_format and output_format != "table":
            for container in selected:
                Msg().out(render_template(output_format,
                                          self._ps_record(container)))
            return self.STATUS_OK

        if quiet:
            for container in selected:
                Msg().out(container["container_id"])
            return self.STATUS_OK

        if print_mode or print_platform:
            # legacy udocker table, kept for the native flags
            mod_h = size_h = plat_h = ""
            mod_l = size_l = plat_l = "%0s"
            if print_mode:
                mod_h = "MOD "
                mod_l = "%2.2s "
            if print_size:
                size_h = "SIZE "
                size_l = "%5.5s "
            if print_platform:
                plat_h = "PLATFORM           "
                plat_l = "%-18.18s "
            fmt = ("%-36.36s %c %c " + mod_h + size_h + plat_h +
                   "%-12.12s %-18s %-20.20s")
            Msg().out(fmt % ("CONTAINER ID", 'P', 'M', "STATUS", "NAMES",
                             "IMAGE"))
            fmt = ("%-36.36s %c %c " + mod_l + size_l + plat_l +
                   "%-12.100s %-18.100s %-20.100s")
            for container in selected:
                line = [''] * 9
                line[0] = container["container_id"]
                line[1] = ('.', 'P')[container["protected"]]
                line[2] = ('R', 'W', 'N', 'D')[container["writable"]]
                line[3] = container["mode"] if print_mode else ""
                line[4] = container["size"] if print_size else ""
                line[5] = container["platform"] if print_platform else ""
                line[6] = container["status"]
                line[7] = container["name"]
                line[8] = container["image"]
                Msg().out(fmt % tuple(line))
            return self.STATUS_OK

        # docker ps table
        header = ("CONTAINER ID", "IMAGE", "COMMAND", "CREATED", "STATUS",
                  "PORTS", "NAMES")
        fmt = "%-14s %-24s %-22s %-20s %-22s %-24s %s"
        if print_size:
            fmt += "   %10s"
            header = header + ("SIZE",)
        Msg().out(fmt % header)
        for container in selected:
            container_id = container["container_id"]
            if not no_trunc:
                container_id = container_id[:12]
            size = container["size"]
            if not size or size < 0:
                size = 0
            line = (container_id, container["image"] or "<none>",
                    container["command"], container["created"],
                    container["docker_status"], container["ports"],
                    container["name"])
            if print_size:
                line = line + (extras.format_size(size * 1024 * 1024),)
            Msg().out(fmt % line)
        return self.STATUS_OK

    def do_rm(self, cmdp):
        """
        rm: delete a container
        rm <container_id>
        -f                          :force removal
        """
        force = cmdp.get("-f")
        container_id_list = cmdp.get("P*")
        if cmdp.missing_options():               # syntax error
            return self.STATUS_ERROR
        if not container_id_list:
            Msg().err("Error: must specify image:tag or repository/image:tag")
            return self.STATUS_ERROR

        exit_status = self.STATUS_OK
        for container_id in cmdp.get("P*"):
            container_id = self.localrepo.get_container_id(container_id)
            if not container_id:
                Msg().err("Error: invalid container id", container_id)
                exit_status = self.STATUS_ERROR
                continue

            if self.localrepo.isprotected_container(container_id):
                Msg().err("Error: container is protected")
                exit_status = self.STATUS_ERROR
                continue

            container_dir = self.localrepo.cd_container(container_id)
            if supervisor.is_running(container_dir):
                if not force:
                    Msg().err("Error: container is running, use -f to stop it")
                    exit_status = self.STATUS_ERROR
                    continue
                self._stop_container(container_id, 10)

            Msg().out("Info: deleting container:",
                      str(container_id), l=Msg.INF)
            if not self.localrepo.del_container(container_id, force):
                Msg().err("Error: deleting container")
                exit_status = self.STATUS_ERROR

        return exit_status

    def do_tag(self, cmdp):
        """
        tag: create a new tag for a given image
        tag <source repo/image:tag> <target repo/image:tag>
        """
        source_imagespec = str(cmdp.get("P1"))
        target_imagespec = str(cmdp.get("P2"))
        if cmdp.missing_options():               # syntax error
            return self.STATUS_ERROR

        (tgt_imagerepo, tgt_tag) = self._check_imagespec(target_imagespec)
        if not (tgt_imagerepo and tgt_tag):
            Msg().err("Error: target name is invalid")
            return self.STATUS_ERROR

        if self.localrepo.cd_imagerepo(tgt_imagerepo, tgt_tag):
            Msg().err("Error: target already exists")
            return self.STATUS_ERROR

        (src_imagerepo, src_tag) = self._check_imagespec(source_imagespec)
        if not self.localrepo.cd_imagerepo(src_imagerepo, src_tag):
            Msg().err("Error: source does not exist")
            return self.STATUS_ERROR

        if self.localrepo.isprotected_imagerepo(src_imagerepo, src_tag):
            Msg().err("Error: source repository is protected")
            return self.STATUS_ERROR

        if not self.localrepo.tag(src_imagerepo, src_tag, tgt_imagerepo, tgt_tag):
            Msg().err("Error: creation of new image tag failed")
            return self.STATUS_ERROR

        return self.STATUS_OK

    def do_rmi(self, cmdp):
        """
        rmi: delete an image in the local repository
        rmi [options] <repo/image:tag>
        -f                          :force removal
        """
        force = cmdp.get("-f")
        imagespec = str(cmdp.get("P1"))
        if cmdp.missing_options():               # syntax error
            return self.STATUS_ERROR

        (imagerepo, tag) = self._check_imagespec(imagespec)
        if not imagerepo:
            return self.STATUS_ERROR

        if self.localrepo.isprotected_imagerepo(imagerepo, tag):
            Msg().err("Error: image repository is protected")
            return self.STATUS_ERROR

        Msg().out("Info: deleting image:", imagespec, l=Msg.INF)
        if not self.localrepo.del_imagerepo(imagerepo, tag, force):
            Msg().err("Error: deleting image")
            return self.STATUS_ERROR

        return self.STATUS_OK

    def do_commit(self, cmdp):
        """
        commit: create a new image from a container
        commit [options] <container-id-or-name> <repo/image:tag>
        -m, --message=<text>       :commit message
        -a, --author=<text>        :author name
        """
        message = cmdp.get("-m=") or cmdp.get("--message=") or None
        author = cmdp.get("-a=") or cmdp.get("--author=") or None
        container_or_name = cmdp.get("P1")
        imagespec = cmdp.get("P2")
        if cmdp.missing_options():               # syntax error
            return self.STATUS_ERROR
        if not (container_or_name and imagespec):
            Msg().err("Error: must specify container and repo/image:tag")
            return self.STATUS_ERROR

        container_id = self.localrepo.get_container_id(container_or_name)
        if not container_id:
            Msg().err("Error: container not found:", container_or_name)
            return self.STATUS_ERROR

        (imagerepo, tag) = self._check_imagespec(imagespec)
        if not imagerepo:
            return self.STATUS_ERROR
        if self.localrepo.cd_imagerepo(imagerepo, tag):
            if self.localrepo.isprotected_imagerepo(imagerepo, tag):
                Msg().err("Error: image repository is protected")
                return self.STATUS_ERROR
            self.localrepo.del_imagerepo(imagerepo, tag, force=True)

        builder = ContainerBuilder(self.localrepo, container_id)
        if not builder.commit(imagerepo, tag, message=message, author=author):
            Msg().err("Error: committing container")
            return self.STATUS_ERROR

        Msg().out("Info: image committed:", imagerepo + ":" + tag, l=Msg.INF)
        return self.STATUS_OK

    def do_history(self, cmdp):
        """
        history: show the layers of an image
        history <repo/image:tag>
        --no-trunc                 :do not truncate layer ids
        """
        imagespec = cmdp.get("P1")
        no_trunc = cmdp.get("--no-trunc")
        if cmdp.missing_options():               # syntax error
            return self.STATUS_ERROR
        (imagerepo, tag) = self._check_imagespec(imagespec)
        if not imagerepo:
            return self.STATUS_ERROR
        if not self.localrepo.cd_imagerepo(imagerepo, tag):
            Msg().err("Error: image not found:", imagespec)
            return self.STATUS_ERROR

        ancestry = self.localrepo.load_json("ancestry") or []
        (container_json, dummy) = self.localrepo.get_image_attributes()
        created = ""
        comment = ""
        if container_json:
            created = container_json.get("created", "") or ""
            comment = container_json.get("comment", "") or ""

        layers = self.localrepo.get_layers(imagerepo, tag)
        layers_map = {}
        for (layer_path, layer_size) in layers:
            layer_name = os.path.basename(layer_path)
            if layer_name.endswith(".layer"):
                layer_name = layer_name[:-len(".layer")]
            layers_map[layer_name] = layer_size

        layer_ids = [layer_id for layer_id in reversed(ancestry)
                     if layer_id in layers_map]
        if not layer_ids:
            layer_ids = list(layers_map)

        Msg().out("%-24s %-10s %-12s %s" %
                  ("LAYER ID", "SIZE", "CREATED", "COMMENT"))
        for position, layer_id in enumerate(layer_ids):
            size_mb = layers_map.get(layer_id, 0) / (1024 * 1024)
            layer_disp = layer_id if no_trunc else layer_id[:24]
            created_row = created if position == 0 else ""
            comment_row = comment if position == 0 else ""
            Msg().out("%-24.24s %-10s %-12s %s" %
                      (layer_disp, "%d MB" % size_mb,
                       created_row[:12], comment_row))
        return self.STATUS_OK

    def do_cp(self, cmdp):
        """
        cp: copy files between the host and a container
        cp <container-id-or-name>:<path> <host-path>
        cp <host-path> <container-id-or-name>:<path>
        """
        src = cmdp.get("P1")
        dst = cmdp.get("P2")
        if cmdp.missing_options():               # syntax error
            return self.STATUS_ERROR
        if not (src and dst):
            Msg().err("Error: must specify source and destination")
            return self.STATUS_ERROR

        (src_cid, src_path) = self._parse_cp_arg(src)
        (dst_cid, dst_path) = self._parse_cp_arg(dst)
        if bool(src_cid) == bool(dst_cid):
            Msg().err("Error: one of source or destination must be a container")
            return self.STATUS_ERROR

        if src_cid:
            container_dir = self.localrepo.cd_container(src_cid)
            if not container_dir:
                Msg().err("Error: container not found:", src_cid)
                return self.STATUS_ERROR
            source = self._container_realpath(container_dir + "/ROOT",
                                              src_path, False)
            if not source or not os.path.lexists(source):
                Msg().err("Error: source path not found in container:", src_path)
                return self.STATUS_ERROR
            dest_is_dir = dst.endswith("/") or os.path.isdir(dst)
            target = dst
            if dest_is_dir:
                target = os.path.join(dst,
                                      os.path.basename(source.rstrip("/")))
            if not self._copy_path(source, target):
                Msg().err("Error: copying from container:", src)
                return self.STATUS_ERROR
            return self.STATUS_OK

        container_dir = self.localrepo.cd_container(dst_cid)
        if not container_dir:
            Msg().err("Error: container not found:", dst_cid)
            return self.STATUS_ERROR
        if not os.path.lexists(src):
            Msg().err("Error: source path not found:", src)
            return self.STATUS_ERROR
        target = self._container_realpath(container_dir + "/ROOT",
                                          dst_path, True)
        if not target:
            Msg().err("Error: destination path escapes container:", dst_path)
            return self.STATUS_ERROR
        if dst_path.endswith("/") or os.path.isdir(target):
            target = os.path.join(target, os.path.basename(src.rstrip("/")))
        if not self._copy_path(src, target):
            Msg().err("Error: copying into container:", dst)
            return self.STATUS_ERROR
        return self.STATUS_OK

    def do_protect(self, cmdp):
        """
        protect: protect a container or image against deletion
        protect <container-id or repo/image:tag>
        """
        arg = cmdp.get("P1")
        if cmdp.missing_options():               # syntax error
            return self.STATUS_ERROR

        if self.localrepo.get_container_id(arg):
            if not self.localrepo.protect_container(arg):
                Msg().err("Error: protect container failed")
                return self.STATUS_ERROR
            return self.STATUS_OK

        (imagerepo, tag) = self._check_imagespec(arg)
        if imagerepo:
            if self.localrepo.protect_imagerepo(imagerepo, tag):
                return self.STATUS_OK

        Msg().err("Error: protect image failed")
        return self.STATUS_ERROR

    def do_unprotect(self, cmdp):
        """
        unprotect: remove delete protection
        unprotect <container-id or repo/image:tag>
        """
        arg = cmdp.get("P1")
        if cmdp.missing_options():               # syntax error
            return self.STATUS_ERROR

        if self.localrepo.get_container_id(arg):
            if not self.localrepo.unprotect_container(arg):
                Msg().err("Error: unprotect container failed")
                return self.STATUS_ERROR
            return self.STATUS_OK

        (imagerepo, tag) = self._check_imagespec(arg)
        if imagerepo:
            if self.localrepo.unprotect_imagerepo(imagerepo, tag):
                return self.STATUS_OK

        Msg().err("Error: unprotect image failed")
        return self.STATUS_ERROR

    def do_name(self, cmdp):
        """
        name: give a name alias to a container
        name <container-id> <container-name>
        """
        container_id = cmdp.get("P1")
        name = cmdp.get("P2")
        if cmdp.missing_options():               # syntax error
            return self.STATUS_ERROR
        if not (self.localrepo.get_container_id(container_id) and name):
            Msg().err("Error: invalid container id or name")
            return self.STATUS_ERROR
        if not self.localrepo.set_container_name(container_id, name):
            Msg().err("Error: invalid container name")
            return self.STATUS_ERROR

        return self.STATUS_OK

    def do_rename(self, cmdp):
        """
        rename: change a name alias
        name <container-name> <new-container-name>
        """
        name = cmdp.get("P1")
        new_name = cmdp.get("P2")
        if cmdp.missing_options():               # syntax error
            return self.STATUS_ERROR
        container_id = self.localrepo.get_container_id(name)
        if not container_id:
            Msg().err("Error: container does not exist")
            return self.STATUS_ERROR
        if self.localrepo.get_container_id(new_name):
            Msg().err("Error: new name already exists")
            return self.STATUS_ERROR
        if not self.localrepo.del_container_name(name):
            Msg().err("Error: name does not exist")
            return self.STATUS_ERROR
        if not self.localrepo.set_container_name(container_id, new_name):
            Msg().err("Error: setting new name")
            self.localrepo.set_container_name(container_id, name)
            return self.STATUS_ERROR

        return self.STATUS_OK

    def do_rmname(self, cmdp):
        """
        rmname: remove a name alias from container
        rmname <container-name>
        """
        name = cmdp.get("P1")
        if cmdp.missing_options():               # syntax error
            return self.STATUS_ERROR
        if not name:
            Msg().err("Error: invalid container id or name")
            return self.STATUS_ERROR
        if not self.localrepo.del_container_name(name):
            Msg().err("Error: removing container name")
            return self.STATUS_ERROR

        Msg().out("Info: container name: %s removed." % name)
        return self.STATUS_OK

    def do_manifest(self, cmdp):
        """
        manifest: commands for image manifests
        manifest [options] inspect <repo/image:tag>
        --httpproxy=socks4://user:pass@host:port        :use http proxy
        --httpproxy=socks5://user:pass@host:port        :use http proxy
        --httpproxy=socks4://host:port                  :use http proxy
        --httpproxy=socks5://host:port                  :use http proxy
        --httpproxy=socks4a://user:pass@host:port       :use http proxy
        --httpproxy=socks5h://user:pass@host:port       :use http proxy
        --httpproxy=socks4a://host:port                 :use http proxy
        --httpproxy=socks5h://host:port                 :use http proxy
        --index=https://index.docker.io/v1              :docker index
        --registry=https://registry-1.docker.io         :docker registry
        --platform=os/arch                              :docker platform

        Examples:
          manifest inspect quay.io/something/somewhere:latest
        """
        index_url = cmdp.get("--index=")
        registry_url = cmdp.get("--registry=")
        http_proxy = cmdp.get("--httpproxy=")
        platform = cmdp.get("--platform=")
        platform = "" if platform is False else platform
        subcommand = cmdp.get("P1")

        (imagerepo, tag) = self._check_imagespec(cmdp.get("P2"))
        if (not imagerepo) or cmdp.missing_options() or subcommand != "inspect":
            return self.STATUS_ERROR

        self._set_repository(registry_url, index_url, imagerepo, http_proxy)
        v2_auth_token = self.keystore.get(self.dockerioapi.registry_url)
        self.dockerioapi.set_v2_login_token(v2_auth_token)
        (dummy, manifest_json) = \
            self.dockerioapi.get_manifest(imagerepo, tag, platform)

        try:
            Msg().out(json.dumps(manifest_json, sort_keys=True,
                                 indent=4, separators=(',', ': ')))
        except (IOError, OSError, AttributeError, ValueError, TypeError):
            Msg().out(manifest_json)
            return self.STATUS_ERROR

        return self.STATUS_OK

    def _build_cleanup(self, container_ids):
        """Delete build containers created for intermediate/failed stages"""
        for container_id in container_ids:
            self.localrepo.del_container(container_id)

    def _build_stage_base(self, base_imagespec, platform, stage_containers):
        """Resolve the FROM of a build stage to a fresh container id: pull
        the image if needed and create a container from it, or clone the
        container of a previously built stage referred to by name"""
        if base_imagespec in stage_containers:
            container_id = ContainerStructure(
                self.localrepo, stage_containers[base_imagespec]).clone()
            if not container_id:
                Msg().err("Error: duplicating build stage:", base_imagespec)
            return container_id

        (base_imagerepo, base_tag) = self._check_imagespec(base_imagespec)
        if not base_imagerepo:
            return None

        if not self.localrepo.cd_imagerepo(base_imagerepo, base_tag):
            Msg().out("Info: pulling base image:", base_imagespec, l=Msg.INF)
            self._set_repository(None, None, base_imagerepo, None)
            v2_auth_token = self.keystore.get(self.dockerioapi.registry_url)
            self.dockerioapi.set_v2_login_token(v2_auth_token)
            if not self.dockerioapi.get(base_imagerepo, base_tag, platform):
                Msg().err("Error: pulling base image failed:", base_imagespec)
                return None

        if self.localrepo.cd_imagerepo(base_imagerepo, base_tag):
            image_platform = self.localrepo.get_image_platform_fmt()
            wanted = platform or (HostInfo().osversion() + "/" +
                                  HostInfo().arch("docker"))
            if isinstance(image_platform, str) and \
                    image_platform != wanted and "unknown" not in image_platform:
                Msg().out("Warning: base image platform", image_platform,
                          "differs from", wanted, l=Msg.WAR)

        container_id = self._create(base_imagerepo + ":" + base_tag)
        if not container_id:
            Msg().err("Error: creating build container from base image")

        return container_id

    def do_build(self, cmdp):
        """
        build: build a container image from a Dockerfile
        build [options]  PATH
        -f=<Dockerfile>              :Alternate Dockerfile (default: PATH/Dockerfile)
        --file=<Dockerfile>          :Alternate Dockerfile (default: PATH/Dockerfile)
        -t=<repo/image:tag>          :Repository and tag to apply to the built image
        --tag=<repo/image:tag>       :Repository and tag to apply to the built image
        --build-arg=<VAR=VALUE>      :Set a build-time ARG variable (repeatable)
        --platform=os/arch           :Pull the base image for this platform
        --force                      :Replace the image tag if it already exists
        --name=<container-name>      :Name given to the resulting build container

        Multi-stage Dockerfiles are supported: FROM <image> AS <name>
        followed later by COPY --from=<name-or-index> <src> <dest>, and by
        FROM <name> to continue building on top of an earlier stage.
        RUN instructions execute using the container execution mode
        currently configured, see: udocker setup --execmode. ADD does not
        fetch remote URLs.

        Examples:
          udocker build -t myrepo/myimage:latest .
          udocker build -f Dockerfile.alt -t myrepo/myimage:latest .
        """
        dockerfile = cmdp.get("-f=") or cmdp.get("--file=")
        imagespec = cmdp.get("-t=") or cmdp.get("--tag=")
        build_args = cmdp.get("--build-arg=", "CMD_OPT", True)
        platform = cmdp.get("--platform=")
        force = cmdp.get("--force")
        name = cmdp.get("--name=")
        context_dir = cmdp.get("P1") or "."
        if cmdp.missing_options():               # syntax error
            return self.STATUS_ERROR

        if not FileUtil(context_dir).isdir():
            Msg().err("Error: build context directory not found:", context_dir)
            return self.STATUS_ERROR

        if not dockerfile:
            dockerfile = context_dir.rstrip("/") + "/Dockerfile"
        if not os.path.isfile(dockerfile):
            Msg().err("Error: Dockerfile not found:", dockerfile)
            return self.STATUS_ERROR

        imagerepo = tag = None
        if imagespec:
            (imagerepo, tag) = self._check_imagespec(imagespec)
            if not imagerepo:
                return self.STATUS_ERROR
            if not force and self.localrepo.cd_imagerepo(imagerepo, tag):
                Msg().err("Error: image tag already exists:", imagespec,
                          "(use --force to replace)")
                return self.STATUS_ERROR

        try:
            instructions = DockerfileParser().parse(dockerfile)
        except (IOError, OSError) as error:
            Msg().err("Error: reading Dockerfile:", error)
            return self.STATUS_ERROR

        try:
            stages = DockerfileParser.split_stages(instructions)
        except ValueError as error:
            Msg().err("Error:", error)
            return self.STATUS_ERROR

        if not stages:
            Msg().err("Error: Dockerfile must start with a FROM instruction")
            return self.STATUS_ERROR

        stage_containers = {}     # stage name/index (str) -> container id
        stage_roots = {}          # stage name/index (str) -> container ROOT
        all_container_ids = []
        builder = None
        container_id = None

        for (index, stage) in enumerate(stages):
            base_imagespec = stage["image"]
            if base_imagespec.lower() == "scratch":
                Msg().err("Error: FROM scratch is not supported")
                self._build_cleanup(all_container_ids)
                return self.STATUS_ERROR

            container_id = self._build_stage_base(
                base_imagespec, platform, stage_containers)
            if not container_id:
                self._build_cleanup(all_container_ids)
                return self.STATUS_ERROR

            all_container_ids.append(container_id)
            Msg().out("Info: build stage %d/%d, container: %s" %
                      (index + 1, len(stages), container_id), l=Msg.INF)
            builder = ContainerBuilder(self.localrepo, container_id,
                                       context_dir)
            builder.set_build_args(build_args)
            builder.set_stage_roots(stage_roots)
            if not builder.run_instructions(stage["instructions"]):
                self._build_cleanup(all_container_ids)
                return self.STATUS_ERROR

            stage_roots[str(index)] = builder.container_root
            stage_containers[str(index)] = container_id
            if stage["name"]:
                stage_roots[stage["name"]] = builder.container_root
                stage_containers[stage["name"]] = container_id

        self._build_cleanup(all_container_ids[:-1])

        if name and not self.localrepo.set_container_name(container_id, name):
            Msg().out("Warning: invalid container name, container kept as:",
                      container_id, l=Msg.WAR)

        if imagerepo:
            if force and self.localrepo.cd_imagerepo(imagerepo, tag):
                self.localrepo.del_imagerepo(imagerepo, tag, force=True)
            if not builder.commit(imagerepo, tag):
                Msg().err("Error: committing built image")
                self.localrepo.del_container(container_id)
                return self.STATUS_ERROR
            Msg().out("Info: image built:", imagerepo + ":" + tag, l=Msg.INF)
            if not name:
                self.localrepo.del_container(container_id)
        else:
            Msg().out(container_id)

        return self.STATUS_OK

    @staticmethod
    def _recorded_command(container_dir):
        """The command recorded by the last run, empty dict when missing"""
        if not isinstance(container_dir, (str, bytes)):
            return {}
        try:
            with open(container_dir + "/cmd.json", "r") as filep:
                recorded = json.load(filep)
        except (IOError, OSError, ValueError, TypeError):
            return {}
        return recorded if isinstance(recorded, dict) else {}

    @classmethod
    def _container_argv(cls, container_dir, config):
        """Command tokens of the container: last run first, image next"""
        recorded = cls._recorded_command(container_dir)
        if recorded:
            parts = _as_command_list(recorded.get("entrypoint"))
            parts.extend(_as_command_list(recorded.get("cmd")))
            if parts:
                return parts
        if isinstance(config, dict):
            parts = _as_command_list(config.get("Entrypoint"))
            parts.extend(_as_command_list(config.get("Cmd")))
            return parts
        return []

    @staticmethod
    def _container_mounts(localrepo, container_dir):
        """Docker Mounts entries from the recorded volume bindings"""
        mounts = []
        if not isinstance(container_dir, (str, bytes)):
            return mounts
        try:
            with open(container_dir + "/volumes.json", "r") as filep:
                specs = json.load(filep)
        except (IOError, OSError, ValueError, TypeError):
            return mounts
        if not isinstance(specs, list):
            return mounts
        for spec in specs:
            (source, destination) = str(spec).split(":", 1)
            if source.startswith("/"):
                mounts.append({
                    "Type": "bind", "Name": "", "Source": source,
                    "Destination": destination, "Driver": "",
                    "Mode": "", "RW": True, "Propagation": "",
                })
            else:
                mounts.append({
                    "Type": "volume", "Name": source,
                    "Source": localrepo.get_volume_path(source),
                    "Destination": destination, "Driver": "local",
                    "Mode": "", "RW": True, "Propagation": "",
                })
        return mounts

    @staticmethod
    def _docker_state_name(status):
        """Docker State.Status value from the udocker status text"""
        if status == "Running":
            return "running"
        if status.startswith("Exited") or status == "Interrupted":
            return "exited"
        if status == "Paused":
            return "paused"
        return "created"

    def _inspect_container(self, container_id):
        """Docker shaped metadata of a container"""
        container_dir = self.localrepo.cd_container(container_id) or ""
        try:
            (dummy, container_json) = ContainerStructure(
                self.localrepo, container_id).get_container_attr()
        except (AttributeError, KeyError, ValueError, TypeError):
            container_json = {}
        if not isinstance(container_json, dict):
            container_json = {}
        config = container_json.get("config")
        config = dict(config) if isinstance(config, dict) else {}
        state = _read_state(container_dir)
        status = self._container_status(container_dir)
        timestamps = state.get("timestamp", "") or ""
        running = status in ("Running", "Paused")
        try:
            exit_code = int(state.get("exitcode") or 0)
        except (TypeError, ValueError):
            exit_code = 0
        try:
            pid = int(state.get("pid") or 0)
        except (TypeError, ValueError):
            pid = 0
        recorded = self._recorded_command(container_dir)
        if recorded:
            entrypoint = _as_command_list(recorded.get("entrypoint"))
            if entrypoint:
                config["Entrypoint"] = entrypoint
            config["Cmd"] = _as_command_list(recorded.get("cmd"))
        argv = self._container_argv(container_dir, config)
        image = ""
        if isinstance(container_dir, (str, bytes)):
            try:
                with open(container_dir + "/imagerepo.name", "r") as filep:
                    image = filep.read().strip()
            except (IOError, OSError):
                image = ""
        names = self.localrepo.get_container_name(container_id) or []
        name = "/" + str(names[0]) if names else "/" + container_id
        config.setdefault("Hostname", "")
        config.setdefault("Domainname", "")
        config.setdefault("User", "")
        config.setdefault("AttachStdin", False)
        config.setdefault("AttachStdout", False)
        config.setdefault("AttachStderr", False)
        config.setdefault("Tty", False)
        config.setdefault("Env", [])
        config.setdefault("Cmd", argv[1:] if argv else [])
        config.setdefault("Entrypoint", None)
        config.setdefault("Image", image)
        config.setdefault("Volumes", None)
        config.setdefault("WorkingDir", "")
        config.setdefault("Labels", {})
        image_labels = config.get("Labels")
        if not isinstance(image_labels, dict):
            image_labels = {}
        merged_labels = dict(image_labels)
        merged_labels.update(_container_labels(container_dir))
        config["Labels"] = merged_labels
        port_bindings = {}
        for mapping in state.get("ports") or []:
            parts = str(mapping).split(":")
            if len(parts) == 2:
                port_bindings["%s/tcp" % parts[1]] = [
                    {"HostIp": "0.0.0.0", "HostPort": parts[0]}]
        mounts = self._container_mounts(self.localrepo, container_dir)
        binds = []
        if isinstance(container_dir, (str, bytes)):
            try:
                with open(container_dir + "/volumes.json", "r") as filep:
                    binds = [str(item) for item in json.load(filep)]
            except (IOError, OSError, ValueError, TypeError):
                binds = []
        created = ""
        if isinstance(container_dir, (str, bytes)):
            try:
                created = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ",
                    time.gmtime(os.path.getmtime(
                        container_dir + "/container.json")))
            except (IOError, OSError, TypeError):
                created = ""
        return {
            "Id": container_id,
            "Created": created,
            "Path": argv[0] if argv else "",
            "Args": argv[1:] if argv else [],
            "State": {
                "Status": self._docker_state_name(status),
                "Running": running,
                "Paused": status == "Paused",
                "Restarting": False,
                "OOMKilled": False,
                "Dead": False,
                "Pid": pid,
                "ExitCode": exit_code,
                "Error": "",
                "StartedAt": timestamps if running else "",
                "FinishedAt": "" if running else timestamps,
            },
            "Image": image,
            "Name": name,
            "RestartCount": 0,
            "Driver": "udocker",
            "Platform": "linux",
            "Mounts": mounts,
            "Config": config,
            "HostConfig": {
                "Binds": binds,
                "NetworkMode": "host",
                "PortBindings": port_bindings,
                "RestartPolicy": {"Name": "no", "MaximumRetryCount": 0},
                "AutoRemove": False,
                "Privileged": False,
            },
            "NetworkSettings": {
                "Ports": port_bindings,
                "Networks": {"host": {
                    "NetworkID": "", "Driver": "host", "Gateway": "",
                    "IPAddress": "", "IPPrefixLen": 0,
                }},
            },
        }

    def _inspect_image(self, imagerepo, tag):
        """Docker shaped metadata of an image tag"""
        (container_json, dummy) = self.localrepo.get_image_attributes()
        if not isinstance(container_json, dict):
            container_json = {}
        config = container_json.get("config")
        config = dict(config) if isinstance(config, dict) else {}
        layers = self.localrepo.get_layers(imagerepo, tag) or []
        layer_ids = []
        size = 0
        for (layer_path, layer_size) in layers:
            size += layer_size
            layer_name = os.path.basename(str(layer_path))
            if layer_name.endswith(".layer"):
                layer_name = layer_name[:-len(".layer")]
            layer_ids.append(layer_name)
        created = container_json.get("created") or ""
        return {
            "Id": self._image_id(),
            "RepoTags": ["%s:%s" % (imagerepo, tag)],
            "RepoDigests": [],
            "Parent": "",
            "Comment": container_json.get("comment") or "",
            "Created": created,
            "DockerVersion": container_json.get("docker_version") or "",
            "Author": container_json.get("author") or "",
            "Config": config,
            "Architecture": container_json.get("architecture") or "unknown",
            "Os": container_json.get("os") or "linux",
            "Size": size,
            "VirtualSize": size,
            "GraphDriver": {"Name": "udocker", "Data": {}},
            "RootFS": {"Type": "layers", "Layers": layer_ids},
            "Metadata": {"LastTagTime": created},
        }

    def _inspect_one(self, name, obj_type=""):
        """Docker shaped object for one name, None when not found"""
        if not name:
            return None
        container_id = ""
        if obj_type != "image":
            container_id = self.localrepo.get_container_id(name)
        if container_id:
            return self._inspect_container(container_id)
        if obj_type == "container":
            return None
        (imagerepo, tag) = self._check_imagespec(name)
        if imagerepo and self.localrepo.cd_imagerepo(imagerepo, tag):
            return self._inspect_image(imagerepo, tag)
        return None

    def do_inspect(self, cmdp):
        """
        inspect: print docker-like metadata JSON of containers or images
        inspect [options] <name|id> [<name|id> ...]
        -f, --format=<template>   :render each object with a Go-template
        --type=<container|image>  :restrict the object type
        -s, --size                :accepted, size is always included
        -p                        :print container ROOT paths (udocker)
        """
        template = cmdp.get("--format=") or cmdp.get("-f=")
        obj_type = cmdp.get("--type=")
        print_dir = cmdp.get("-p")
        dummy = cmdp.get("-s")
        objects = cmdp.get("P*") or []
        if cmdp.missing_options():               # syntax error
            return self.STATUS_ERROR
        if not objects:
            Msg().err("Error: inspect requires at least one name or id")
            return self.STATUS_ERROR
        data = []
        for name in objects:
            item = self._inspect_one(name, obj_type or "")
            if item is None:
                Msg().err("Error: no such object:", name)
                return self.STATUS_ERROR
            data.append(item)
        if print_dir:
            for name in objects:
                container_id = self.localrepo.get_container_id(name)
                container_dir = ""
                if container_id:
                    container_dir = self.localrepo.cd_container(container_id)
                if not container_dir:
                    Msg().err("Error: -p requires a container:", name)
                    return self.STATUS_ERROR
                Msg().out(str(container_dir) + "/ROOT")
            return self.STATUS_OK
        if template:
            for item in data:
                Msg().out(render_template(template, item))
            return self.STATUS_OK
        Msg().out(json.dumps(data, sort_keys=True, indent=4,
                             separators=(',', ': ')))
        return self.STATUS_OK

    def do_verify(self, cmdp):
        """
        verify: verify an image
        verify <repo/image:tag>
        """
        (imagerepo, tag) = self._check_imagespec(cmdp.get("P1"))
        if (not imagerepo) or cmdp.missing_options():  # syntax error
            return self.STATUS_ERROR

        Msg().out("Info: verifying: %s:%s" % (imagerepo, tag), l=Msg.INF)
        if not self.localrepo.cd_imagerepo(imagerepo, tag):
            Msg().err("Error: selecting image and tag")
            return self.STATUS_ERROR

        if self.localrepo.verify_image():
            Msg().out("Info: image Ok", l=Msg.INF)
            return self.STATUS_OK

        Msg().err("Error: image verification failure")
        return self.STATUS_ERROR

    def do_setup(self, cmdp):
        """
        setup: change container execution settings
        setup [options] <container-id>
        --execmode=<mode>       :select execution mode from below
        --force                 :force setup change
        --purge                 :clean mountpoints and files created by udocker
        --fixperm               :attempt to fix file permissions
        --nvidia                :add NVIDIA libraries and binaries

        <mode> is one of the following execution modes:
        P1: proot accelerated mode using seccomp filtering (default)
        P2: proot accelerated mode disabled
        F1: fakechroot starting executables via direct loader invocation
        F2: like F1 plus protected environment and modified ld.so
        F3: fakechroot plus patching of elf headers in binaries and libs
        F4: like F3 plus support for newly created executables via
            dynamic patching of elf headers in binaries and libs
        R1: runc using rootless namespaces, requires recent kernel
            with user namespace support enabled
        R2: proot with root emulation running on top of runc to avoid
            most of the errors related to change of uid or gid
        R3: same as R2 but with proot accelerated mode disabled
        S1: singularity, requires a local installation of singularity,
            if singularity is available in the PATH udocker will use
            it to execute the container
        """
        container_id = cmdp.get("P1")
        xmode = cmdp.get("--execmode=")
        force = cmdp.get("--force")
        nvidia = cmdp.get("--nvidia")
        purge = cmdp.get("--purge")
        fixperm = cmdp.get("--fixperm")
        if cmdp.missing_options():               # syntax error
            return self.STATUS_ERROR

        container_dir = self.localrepo.cd_container(container_id)
        if not container_dir:
            Msg().err("Error: invalid container id")
            return self.STATUS_ERROR

        if xmode and self.localrepo.isprotected_container(container_id):
            Msg().err("Error: container is protected")
            return self.STATUS_ERROR

        if purge:
            FileBind(self.localrepo, container_id).restore(force)
            MountPoint(self.localrepo, container_id).restore()

        if fixperm:
            Unshare().namespace_exec(lambda: FileUtil(container_dir +
                                                      "/ROOT").rchown())
            FileUtil(container_dir + "/ROOT").rchmod()

        nvidia_mode = NvidiaMode(self.localrepo, container_id)
        if nvidia:
            nvidia_mode.set_mode(force)

        exec_mode = ExecutionMode(self.localrepo, container_id)
        if xmode:
            if exec_mode.set_mode(xmode.upper(), force):
                return self.STATUS_OK
            return self.STATUS_ERROR

        if xmode or not (xmode or force or nvidia or purge or fixperm):
            Msg().out("execmode: %s" % (exec_mode.get_mode()))
            Msg().out("nvidiamode: %s" % (nvidia_mode.get_mode()))

        return self.STATUS_OK

    def do_install(self, cmdp):
        """
        install: install udocker and its tools
        install [options]
        --force                    :force reinstall
        --purge                    :remove files (be careful)
        """
        if cmdp is not None:
            force = cmdp.get("--force")
            purge = cmdp.get("--purge")
            if cmdp.missing_options():  # syntax error
                return self.STATUS_ERROR
        else:
            force = False
            purge = False

        utools = UdockerTools(self.localrepo)
        if purge:
            utools.purge()

        if utools.install(force):
            return self.STATUS_OK

        return self.STATUS_ERROR

    def do_showconf(self, cmdp):
        """
        showconf: Print all configuration options
        """
        cmdp.get("showconf", "CMD")
        if cmdp.missing_options():  # syntax error
            return self.STATUS_ERROR

        Msg().out(80*"-")
        Msg().out("\t\tConfiguration options")
        for (key, value) in Config.conf.items():
            Msg().out(key, '=', value)

        Msg().out(80*"-")
        return self.STATUS_OK

    def do_version(self, cmdp):
        """
        version: print docker-like client and engine versions
        -f, --format=<template>   :render the information with a Go-template
        """
        template = cmdp.get("--format=") or cmdp.get("-f=")
        if cmdp.missing_options():               # syntax error
            return self.STATUS_ERROR
        arch = HostInfo().arch() or "unknown"
        client = {
            "Version": __version__,
            "ApiVersion": "1.44",
            "GoVersion": "python %s" % sys.version.split()[0],
            "Os": "linux",
            "Arch": arch,
            "Context": "default",
            "Experimental": False,
        }
        server = {
            "Version": __version__,
            "ApiVersion": "1.44",
            "MinAPIVersion": "1.24",
            "Os": "linux",
            "Arch": arch,
            "Engine": {"Name": "udocker"},
        }
        data = {"Client": client, "Server": server}
        if template:
            Msg().out(render_template(template, data))
            return self.STATUS_OK
        Msg().out("Client:")
        Msg().out(" Version:           %s" % client["Version"])
        Msg().out(" API version:       %s" % client["ApiVersion"])
        Msg().out(" Go version:        %s" % client["GoVersion"])
        Msg().out(" OS/Arch:           %s/%s" % (client["Os"], arch))
        Msg().out(" Context:           default")
        Msg().out("")
        Msg().out("Server: udocker")
        Msg().out(" Engine:")
        Msg().out("  Version:          %s" % server["Version"])
        Msg().out("  API version:      %s (minimum version %s)"
                  % (server["ApiVersion"], server["MinAPIVersion"]))
        Msg().out("  OS/Arch:          linux/%s" % arch)
        return self.STATUS_OK

    def do_info(self, cmdp):
        """
        info: print docker-like engine and host information
        -f, --format=<template>   :render the information with a Go-template
        """
        template = cmdp.get("--format=") or cmdp.get("-f=")
        if cmdp.missing_options():               # syntax error
            return self.STATUS_ERROR
        hostinfo = HostInfo()
        containers = self.localrepo.get_containers_list(False)
        running = 0
        for item in containers:
            container_dir = self.localrepo.cd_container(item[0]) or ""
            if self._container_status(container_dir) == "Running":
                running += 1
        data = {
            "ID": "",
            "Name": "udocker",
            "ServerVersion": __version__,
            "StorageDriver": "udocker",
            "LoggingDriver": "udocker",
            "CgroupDriver": "none",
            "DockerRootDir": str(Config.conf['topdir']),
            "OperatingSystem": hostinfo.osversion() or "Linux",
            "OSType": "linux",
            "Architecture": hostinfo.arch() or "unknown",
            "KernelVersion": hostinfo.oskernel() or "",
            "NCPU": os.cpu_count() or 0,
            "MemTotal": extras.mem_total_bytes(),
            "Containers": len(containers),
            "ContainersRunning": running,
            "ContainersPaused": 0,
            "ContainersStopped": len(containers) - running,
            "Images": len(self.localrepo.get_imagerepos()),
            "Volumes": len(self.localrepo.get_volumes_list()),
            "Registry": str(Config.conf['dockerio_registry_url']),
            "UdockerTarball": str(Config.conf['tarball_release']),
        }
        if template:
            Msg().out(render_template(template, data))
            return self.STATUS_OK
        Msg().out("Client:")
        Msg().out(" Version:           %s" % __version__)
        Msg().out(" Context:           default")
        Msg().out("")
        Msg().out("Server: udocker")
        Msg().out(" Engine:")
        Msg().out("  Version:          %s" % data["ServerVersion"])
        Msg().out("  Storage Driver:   %s" % data["StorageDriver"])
        Msg().out("  Logging Driver:   %s" % data["LoggingDriver"])
        Msg().out("  Cgroup Driver:    %s" % data["CgroupDriver"])
        Msg().out("  Operating System: %s" % data["OperatingSystem"])
        Msg().out("  OSType:           %s" % data["OSType"])
        Msg().out("  Architecture:     %s" % data["Architecture"])
        Msg().out("  Kernel Version:   %s" % data["KernelVersion"])
        Msg().out("  CPUs:             %s" % data["NCPU"])
        Msg().out("  Total Memory:     %s"
                  % extras.format_size(data["MemTotal"]))
        Msg().out("  Docker Root Dir:  %s" % data["DockerRootDir"])
        Msg().out("  Udocker tarball:  %s" % data["UdockerTarball"])
        Msg().out(" Containers:       %s" % data["Containers"])
        Msg().out("  Running:          %s" % data["ContainersRunning"])
        Msg().out("  Paused:           0")
        Msg().out("  Stopped:          %s" % data["ContainersStopped"])
        Msg().out(" Images:           %s" % data["Images"])
        Msg().out(" Volumes:          %s" % data["Volumes"])
        Msg().out(" Registry:         %s" % data["Registry"])
        return self.STATUS_OK

    def do_help(self, cmdp):
        """
        Print help information
        """
        cmdp.get("help", "CMD")
        Msg().out(
            """
Syntax:
  udocker  [general_options] <command>  [command_options]  <command_args>

  udocker [-h|--help|help]        :Display this help and exits
  udocker [-V|--version|version]  :Display udocker and tarball version and exits

General options common to all commands must appear before the command:
  -D, --debug                   :Debug
  -q, --quiet                   :Less verbosity
  --insecure                    :Allow insecure non authenticated https
  --repo=<directory>            :Use repository at directory
  --allow-root                  :Allow execution by root NOT recommended
  --config=<conf_file>          :Use configuration <conf_file>

Commands:
  --help [command]              :Command specific help
  showconf                      :Print all configuration options
  version                       :Print docker-like client and engine versions
  info                          :Print docker-like engine and host information

Docker-style command groups are accepted and translated:
  container ls|run|rm|...       :same as ps, run, rm, ...
  image ls|inspect|rm|...       :same as images, inspect, rmi, ...
  system df|prune               :same as system df|prune

  search <repo/expression>      :Search dockerhub for container images
  pull <repo/image:tag>         :Pull container image from dockerhub
  push <repo/image:tag>         :Upload image to a docker registry
  create <repo/image:tag>       :Create container from a pulled image
  run <container_id|name>       :Execute created container
  run <repo/image:tag>          :Pull, create and execute container
  run -d <container>            :Execute container in background (all modes)
  start <container>             :Start a container created with run -d
  stop <container>              :Stop a running container
  restart <container>           :Stop and start a container
  pause <container>             :Pause all processes of a container
  unpause <container>           :Resume a paused container
  kill -s <signal> <container>  :Send a signal to a running container
  exec <container> <command>    :Execute a command in a running container
  logs [-f] <container>         :Show the log of a container
  wait <container>              :Wait for a container and print its exit code
  top <container> [ps args]     :Show the running processes of a container
  stats [container ...]         :Show CPU memory and pids of containers
  diff <container>              :Show filesystem changes of a container
  port <container> [port]       :Show published ports of a container
  build -t <repo/image:tag> <path> :Build image from a Dockerfile
  commit <container> <repo/image:tag> :Create an image from a container
  compose [-f=<file>] up|down|ps|logs|config :Run a compose project

  images -l                     :List container images
  history <repo/image:tag>      :List the layers of an image
  ps -m -s                      :List created containers
  system df                     :Show disk usage of images and containers
  system prune [-f]             :Remove stopped containers and unused images
  image prune [-f]              :Remove images not used by containers
  network ls                    :List available networks (host, none)
  network inspect <name>        :Print network metadata as JSON
  volume create [<name>]        :Create a named volume
  volume ls                     :List named volumes
  volume inspect <name>         :Print volume metadata as JSON
  volume rm [-f] <name>         :Remove named volumes
  volume prune [-f]             :Remove volumes not used by containers
  cp <container>:<path> <host-path> :Copy files from container to host
  cp <host-path> <container>:<path> :Copy files from host to container
  name <container_id> <name>    :Give name to container
  rmname <name>                 :Delete name from container
  rename <name> <new_name>      :Change container name
  clone <container_id>          :Duplicate container
  rm  <container-id|name>       :Delete container
  rmi <repo/image:tag>          :Delete image
  tag <repo/image:tag> <repo2/image2:tag2> :Tag image

  import <tar> <repo/image:tag> :Import tar file (exported by docker)
  import - <repo/image:tag>     :Import from stdin (exported by docker)
  export -o <tar> <container>   :Export container directory tree to file
  export - <container>          :Export container directory tree to stdin
  load -i <exported-image>      :Load image from file (saved by docker)
  load                          :Load image from stdin (saved by docker)
  save -o <imagefile> <repo/image:tag>  :Save image with layers to file

  inspect -p <repo/image:tag>   :Print image or container metadata
  verify <repo/image:tag>       :Verify a pulled image
  manifest inspect <repo/image:tag> :Print manifest metadata

  udocker manifest inspect centos/centos8
  udocker pull --platform=linux/arm64 centos/centos8
  udocker tag centos/centos8  mycentos/centos8:arm64

  protect <repo/image:tag>      :Protect repository
  unprotect <repo/image:tag>    :Unprotect repository
  protect <container>           :Protect container
  unprotect <container>         :Unprotect container

  mkrepo <top-repo-dir>         :Create another repository in location
  setup --execmode=<mode>       :Change container execution mode
  setup --nvidia                :Setup container to use nvidia GPU
  setup --purge                 :clean mountpoints and files created by udocker
  setup --fixperm               :attempt to fix file permissions

  login                         :Login into docker repository
  logout                        :Logout from docker repository

Examples:
  udocker search expression
  udocker search quay.io/expression
  udocker search --list-tags myimage
  udocker pull myimage:mytag
  udocker images
  udocker create --name=mycontainer  myimage:mytag
  udocker ps -m -s
  udocker top mycontainer ps aux
  udocker stats mycontainer
  udocker diff mycontainer
  udocker port mycontainer 80/tcp
  udocker system df
  udocker compose up -d
  udocker inspect mycontainer
  udocker inspect -p mycontainer

  udocker manifest inspect centos/centos8
  udocker pull --platform=linux/arm64 centos/centos8
  udocker tag centos/centos8  mycentos/centos8:arm64

  udocker build -t myrepo/myimage:latest .
  udocker build -f Dockerfile.alt -t myrepo/myimage:latest .
  udocker commit -m "installed packages" mycontainer myrepo/myimage:latest
  udocker history myrepo/myimage:latest
  udocker cp mycontainer:/etc/os-release /tmp/
  udocker cp /tmp/script.sh mycontainer:/tmp/
  udocker push myrepo/myimage:latest

  udocker run  mycontainer  cat /etc/redhat-release
  udocker run --hostauth --hostenv --bindhome  mycontainer
  udocker run --user=root  mycontainer  yum install firefox
  udocker run --hostauth --hostenv --bindhome mycontainer  firefox
  udocker run --entrypoint="" mycontainer  /bin/bash -i
  udocker run --entrypoint="/bin/bash" mycontainer -i

  udocker clone --name=anotherc mycontainer
  udocker rm anotherc

  udocker mkrepo /data/myrepo
  udocker --repo=/data/myrepo load -i docker-saved-repo.tar
  udocker --repo=/data/myrepo images
  udocker --repo=/data/myrepo run --user=$USER  myimage:mytag

  udocker export -o myimage.tar mycontainer
  udocker import myimage.tar mynewimage
  udocker create --name=mynewc mynewimage
  udocker export --clone -o mycontainer.tar mycontainer
  udocker import --clone mycontainer.tar

Notes:
 * by default the binaries, images and containers are placed in
      $HOME/.udocker
 * by default the following host directories are mounted in the
   container:
      /dev /proc /sys /etc/resolv.conf /etc/host.conf /etc/hostname
 * to prevent the mount of the above directories use:
      run  --nosysdirs  <container>
 * additional host directories to be mounted are specified with:
      run --volume=/data:/mnt --volume=/etc/hosts  <container>
      run --nosysdirs --volume=/dev --volume=/proc  <container>
 * udocker provides several execution modes that offer different
   approaches and technologies to execute containers, they
   can be selected using the setup command. See the setup help.
      udocker setup --execmode=F3 fedx
      udocker setup --execmode=R1 fedx
      udocker setup --execmode=S1 fedx
      udocker setup --help
 * udocker facilitates the usage of nvidia drivers within containers
      udocker setup --nvidia fedx

See: https://github.com/indigo-dc/udocker/blob/master/SUMMARY.md
            """)
        return self.STATUS_OK
