#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
udocker unit tests: extra commands (top, stats, diff, port, df, prune)
"""

import io
import json
import os
import shutil
import tarfile
import tempfile
from contextlib import redirect_stdout, redirect_stderr
from unittest import TestCase, main
from unittest.mock import Mock, patch

from udocker import extras


def add_tar_member(tarf, name, kind="f", data=b"", mtime=1000,
                   mode=0o644, linkname=""):
    """Add a regular file, directory, symlink or hardlink to a tar"""
    info = tarfile.TarInfo(name)
    info.mtime = mtime
    info.mode = mode
    info.linkname = linkname
    if kind == "d":
        info.type = tarfile.DIRTYPE
        info.size = 0
        tarf.addfile(info)
    elif kind == "s":
        info.type = tarfile.SYMTYPE
        info.size = 0
        tarf.addfile(info)
    elif kind == "h":
        info.type = tarfile.LNKTYPE
        info.size = 0
        tarf.addfile(info)
    else:
        info.type = tarfile.REGTYPE
        info.size = len(data)
        tarf.addfile(info, io.BytesIO(data))


class ExtrasTestCase(TestCase):
    """Test the docker-like extras helpers and printers"""

    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base)

    # ------------------------------------------------------- test helpers

    def _capture(self, func, *args, **kwargs):
        """Run func capturing stdout and stderr, return status and output"""
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = func(*args, **kwargs)
        return status, out.getvalue(), err.getvalue()

    def _container(self, container_id, state=None, conf=None, image=None):
        """Create a fake container directory"""
        container_dir = os.path.join(self.base, "containers", container_id)
        os.makedirs(os.path.join(container_dir, "ROOT"))
        if state is not None:
            with open(os.path.join(container_dir, "state.json"), "w") as filep:
                json.dump(state, filep)
        if conf is not None:
            with open(os.path.join(container_dir, "supervisor.json"),
                      "w") as filep:
                json.dump(conf, filep)
        if image is not None:
            with open(os.path.join(container_dir, "imagerepo.name"),
                      "w") as filep:
                filep.write(image)
        return container_dir

    def _write(self, path, data, mtime=1000, mode=0o644):
        """Write a file with a fixed mtime and mode"""
        parent = os.path.dirname(path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        with open(path, "wb") as filep:
            filep.write(data)
        os.chmod(path, mode)
        os.utime(path, (mtime, mtime))

    # ---------------------------------------------------------- formatting

    def test_01_format_size(self):
        """Test01 human readable sizes"""
        self.assertEqual(extras.format_size(0), "0B")
        self.assertEqual(extras.format_size(1023), "1023B")
        self.assertEqual(extras.format_size(1024), "1.00KB")
        self.assertEqual(extras.format_size(1536), "1.50KB")
        self.assertEqual(extras.format_size(1024 * 1024), "1.00MB")
        self.assertEqual(extras.format_size(1024 ** 3), "1.00GB")
        self.assertEqual(extras.format_size(None), "0B")

    def test_02_format_seconds(self):
        """Test02 ps style cpu time"""
        self.assertEqual(extras.format_seconds(0), "0:00")
        self.assertEqual(extras.format_seconds(65), "1:05")
        self.assertEqual(extras.format_seconds(3665), "1:01:05")
        self.assertEqual(extras.format_seconds(90065), "1-01:01:05")

    # ----------------------------------------------------------- /proc

    def test_03_parse_proc_stat(self):
        """Test03 /proc/pid/stat parsing with tricky comm"""
        data = ("7 (b) weird) R 1 7 7 0 -1 0 0 0 0 0 10 5 0 0 20 0 1 0 "
                "100 1234 999 18446744073709551615")
        info = extras.parse_proc_stat(data)
        self.assertEqual(info["pid"], 7)
        self.assertEqual(info["comm"], "b) weird")
        self.assertEqual(info["ppid"], 1)
        self.assertEqual(info["tty"], 0)
        self.assertEqual(info["utime"], 10)
        self.assertEqual(info["stime"], 5)
        self.assertEqual(info["starttime"], 100)
        self.assertEqual(extras.parse_proc_stat("garbage"), {})

        with open("/proc/self/stat", "rb") as filep:
            real = extras.parse_proc_stat(filep.read())
        self.assertEqual(real["pid"], os.getpid())
        self.assertEqual(real["ppid"], os.getppid())

    def test_04_parse_proc_status_cmdline(self):
        """Test04 /proc/pid/status and cmdline parsing"""
        status = ("Name:\tpython\nUid:\t1000\t1000\t1000\t1000\n"
                  "VmRSS:\t  2048 kB\n")
        info = extras.parse_proc_status(status)
        self.assertEqual(info["uid"], "1000")
        self.assertEqual(info["rss_kb"], 2048)
        self.assertEqual(extras.parse_proc_cmdline(b"sh\0-c\0sleep 1\0"),
                         ["sh", "-c", "sleep 1"])
        self.assertEqual(extras.parse_proc_cmdline(b""), [])

    def test_05_proc_tree_and_top_rows(self):
        """Test05 process tree, tty and top row formatting"""
        procs = {
            100: {"pid": 100, "ppid": 1, "uid": "1000", "comm": "python",
                  "utime": 10, "stime": 5, "starttime": 100, "tty": 0,
                  "cmd": ["python", "-m", "udocker.maincmd"], "rss_kb": 1000},
            101: {"pid": 101, "ppid": 100, "uid": "1000", "comm": "runc",
                  "utime": 1, "stime": 1, "starttime": 110, "tty": 0,
                  "cmd": ["runc", "run"], "rss_kb": 200},
            102: {"pid": 102, "ppid": 101, "uid": "0", "comm": "sh",
                  "utime": 2, "stime": 0, "starttime": 120, "tty": 34816,
                  "cmd": ["sh", "-c", "sleep 1"], "rss_kb": 300},
            103: {"pid": 103, "ppid": 1, "uid": "0", "comm": "other",
                  "utime": 2, "stime": 0, "starttime": 120, "tty": 0,
                  "cmd": ["other"], "rss_kb": 1},
        }
        self.assertEqual(extras.proc_tree(procs, 100), [100, 101, 102])
        rows = extras.top_rows(procs, 100, None, 100, 200.0)
        self.assertEqual([row[1] for row in rows], ["100", "101", "102"])
        self.assertEqual(rows[2][0], "0")
        self.assertEqual(rows[2][5], "pts/0")
        self.assertEqual(rows[2][7], "sh")
        full = extras.top_rows(procs, 100, ["aux"], 100, 200.0)
        self.assertEqual(full[2][7], "sh -c sleep 1")
        self.assertEqual(full[0][7], "python -m udocker.maincmd")
        self.assertEqual(extras.format_tty(0), "-")
        self.assertEqual(extras.format_tty(34816), "pts/0")

    def test_06_scan_procs(self):
        """Test06 scan_procs sees the current process"""
        procs = extras.scan_procs()
        self.assertIn(os.getpid(), procs)
        self.assertEqual(procs[os.getpid()]["ppid"], os.getppid())
        self.assertIsInstance(procs[os.getpid()]["cmd"], list)

    def test_07_print_top(self):
        """Test07 top prints the header and the monitor process"""
        container_dir = self._container(
            "cid", {"status": "running", "pid": os.getpid()})
        with patch("udocker.extras.supervisor.is_running",
                   return_value=True), \
                patch("udocker.extras.supervisor.read_state",
                      return_value={"status": "running", "pid": os.getpid()}):
            status, out, dummy = self._capture(
                extras.print_top, container_dir, "cid")
        self.assertEqual(status, 0)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("UID"))
        self.assertIn(str(os.getpid()), out)
        self.assertEqual(len(lines[0]), 99)

        with patch("udocker.extras.supervisor.is_running",
                   return_value=False):
            status, dummy, err = self._capture(
                extras.print_top, container_dir, "cid")
        self.assertEqual(status, 1)
        self.assertIn("not running", err)

    # ------------------------------------------------------------ stats

    def test_08_stats_helpers(self):
        """Test08 cpu percentage, jiffies and rss aggregation"""
        self.assertEqual(extras.cpu_percent(10, 20, 0.5, 100), 20.0)
        self.assertEqual(extras.cpu_percent(20, 10, 0.5, 100), 0.0)
        self.assertEqual(extras.cpu_percent(10, 20, 0.0, 100), 0.0)
        procs = {1: {"utime": 2, "stime": 3, "rss_kb": 100},
                 2: {"utime": 1, "stime": 1, "rss_kb": 200}}
        self.assertEqual(extras.total_jiffies(procs, [1, 2]), 7)
        self.assertEqual(extras.total_rss_kb(procs, [1, 2]), 300)
        self.assertEqual(extras.total_jiffies(procs, [3]), 0)

    def test_09_print_stats(self):
        """Test09 stats prints one snapshot for all containers"""
        container_dir = self._container(
            "cid123456789", {"status": "running", "pid": os.getpid()})
        name = os.path.join(os.path.dirname(container_dir), "web")
        os.symlink(os.path.basename(container_dir), name)
        with patch("udocker.extras.supervisor.is_running",
                   return_value=True), \
                patch("udocker.extras.supervisor.read_state",
                      return_value={"status": "running", "pid": os.getpid()}), \
                patch("udocker.extras.time.sleep"):
            status, out, dummy = self._capture(
                extras.print_stats, [("cid123456789", container_dir)])
        self.assertEqual(status, 0)
        lines = out.splitlines()
        self.assertEqual(lines[0].split(), ["CONTAINER", "ID", "NAME", "CPU%",
                                            "MEM", "USAGE", "/", "LIMIT",
                                            "MEM%", "PIDS"])
        self.assertEqual(len(lines), 2)
        self.assertIn("web", lines[1])
        self.assertIn("cid123456789"[:12], lines[1])

        with patch("udocker.extras.supervisor.is_running",
                   return_value=False):
            exited = self._container("cid2", {"status": "exited",
                                              "exitcode": 0})
            status, out, dummy = self._capture(
                extras.print_stats, [("cid2", exited)])
        self.assertEqual(status, 0)
        self.assertIn("0.00%", out.splitlines()[1])

        status, dummy, err = self._capture(extras.print_stats, [])
        self.assertEqual(status, 1)
        self.assertIn("no containers", err)

    # ------------------------------------------------------------- diff

    def test_10_split_imagespec(self):
        """Test10 image spec split including digest tags"""
        self.assertEqual(extras.split_imagespec("busybox:latest"),
                         ("busybox", "latest"))
        self.assertEqual(extras.split_imagespec("busybox:sha256:abc"),
                         ("busybox", "sha256:abc"))
        self.assertEqual(extras.split_imagespec("localhost:5000/a/b:t1"),
                         ("localhost:5000/a/b", "t1"))
        self.assertEqual(extras.split_imagespec("repo/name@sha256:abc"),
                         ("repo/name", "sha256:abc"))
        self.assertEqual(extras.split_imagespec("plain"), ("plain", "latest"))

    def test_11_diff_added_changed_deleted(self):
        """Test11 diff reports A, C and D against the image layers"""
        layer = os.path.join(self.base, "layer.tar")
        with tarfile.open(layer, "w") as tarf:
            add_tar_member(tarf, "bin", "d", mode=0o755)
            add_tar_member(tarf, "bin/keep", data=b"same")
            add_tar_member(tarf, "bin/change", data=b"old")
            add_tar_member(tarf, "bin/deleted", data=b"gone")
            add_tar_member(tarf, "bin/link", "s", linkname="keep")
            add_tar_member(tarf, "tmp", "d", mode=0o1777)
        container_dir = self._container("cid", image="busybox:latest")
        root = os.path.join(container_dir, "ROOT")
        self._write(os.path.join(root, "bin", "keep"), b"same")
        self._write(os.path.join(root, "bin", "change"), b"different")
        self._write(os.path.join(root, "bin", "added"), b"new")
        os.symlink("keep", os.path.join(root, "bin", "link"))
        os.utime(os.path.join(root, "bin", "link"), (1000, 1000),
                 follow_symlinks=False)
        os.chmod(os.path.join(root, "bin"), 0o755)
        os.utime(os.path.join(root, "bin"), (1000, 1000))
        # udocker runtime entries must not show up as changes
        os.makedirs(os.path.join(root, "proc"))
        os.makedirs(os.path.join(root, "sys"))
        os.makedirs(os.path.join(root, ".udocker"))
        self._write(os.path.join(root, "tmp", "prooted-1", "f"), b"x")
        os.chmod(os.path.join(root, "tmp"), 0o1777)
        os.utime(os.path.join(root, "tmp"), (1000, 1000))

        localrepo = Mock()
        localrepo.cd_container.return_value = container_dir
        localrepo.cd_imagerepo.return_value = os.path.join(self.base, "tag")
        localrepo.get_image_attributes.return_value = ({}, [layer])
        status, out, dummy = self._capture(
            extras.print_diff, localrepo, "cid")
        self.assertEqual(status, 0)
        self.assertEqual(out.splitlines(), ["A /bin/added", "C /bin/change",
                                            "D /bin/deleted"])

    def test_12_diff_layers_whiteouts_and_hardlinks(self):
        """Test12 layer overlay applies whiteouts and resolves hardlinks"""
        lower = os.path.join(self.base, "lower.tar")
        with tarfile.open(lower, "w") as tarf:
            add_tar_member(tarf, "a.txt", data=b"a")
            add_tar_member(tarf, "d", "d", mode=0o755)
            add_tar_member(tarf, "d/f", data=b"f")
            add_tar_member(tarf, "bin/busybox", data=b"bb", mode=0o755)
            add_tar_member(tarf, "bin/sh", "h", linkname="./bin/busybox",
                           mode=0o755)
        upper = os.path.join(self.base, "upper.tar")
        with tarfile.open(upper, "w") as tarf:
            add_tar_member(tarf, ".wh.a.txt", data=b"")
            add_tar_member(tarf, "d/.wh..wh..opq", data=b"")
            add_tar_member(tarf, "d/new", data=b"n")
        image = extras.image_entries([lower, upper])
        self.assertIsNotNone(image)
        self.assertNotIn("a.txt", image)
        self.assertNotIn("d/f", image)
        self.assertIn("d/new", image)
        self.assertEqual(image["bin/sh"], image["bin/busybox"])
        self.assertEqual(image["bin/sh"][3], "f")
        self.assertEqual(image["bin/sh"][0], 2)

    def test_13_diff_missing_image(self):
        """Test13 diff errors when the image is missing"""
        container_dir = self._container("cid", image="busybox:latest")
        localrepo = Mock()
        localrepo.cd_container.return_value = container_dir
        localrepo.cd_imagerepo.return_value = ""
        status, dummy, err = self._capture(
            extras.print_diff, localrepo, "cid")
        self.assertEqual(status, 1)
        self.assertIn("image not found", err)

    # ------------------------------------------------------------- ports

    def test_14_parse_ports(self):
        """Test14 port spec parsing"""
        self.assertEqual(extras.parse_port("8080:80"), ("8080", "80", "tcp"))
        self.assertEqual(extras.parse_port("8080:80/tcp"),
                         ("8080", "80", "tcp"))
        self.assertEqual(extras.parse_port("127.0.0.1:8080:80/tcp"),
                         ("8080", "80", "tcp"))
        self.assertEqual(extras.parse_port("127.0.0.1:8080:80/udp"),
                         ("8080", "80", "udp"))
        self.assertIsNone(extras.parse_port("abc"))
        self.assertIsNone(extras.parse_port("8080:70000"))
        ports, publish_all = extras.ports_from_argv(
            ["run", "-p", "8081:80", "--publish=9091:91", "-p=7070:70/tcp",
             "cid"])
        self.assertEqual(ports, [("8081", "80", "tcp"),
                                 ("9091", "91", "tcp"),
                                 ("7070", "70", "tcp")])
        self.assertFalse(publish_all)
        (dummy, publish_all) = extras.ports_from_argv(["run", "-P", "cid"])
        self.assertTrue(publish_all)

    def test_15_print_ports(self):
        """Test15 port from state.json and argv fallback"""
        container_dir = self._container(
            "p1", {"status": "exited",
                   "ports": ["8080:80", "127.0.0.1:9090:90/tcp"]})
        status, out, dummy = self._capture(extras.print_ports, container_dir)
        self.assertEqual(status, 0)
        self.assertEqual(out.splitlines(),
                         ["80/tcp -> 8080", "90/tcp -> 9090"])
        status, out, dummy = self._capture(extras.print_ports,
                                          container_dir, "80/tcp")
        self.assertEqual(status, 0)
        self.assertEqual(out.strip(), "8080")
        status, dummy, err = self._capture(extras.print_ports,
                                          container_dir, "81")
        self.assertEqual(status, 1)
        self.assertIn("no published port", err)

        fallback = self._container(
            "p2", {"status": "exited"},
            {"argv": ["run", "-p", "8081:80", "--publish=9091:91", "cid"]})
        status, out, dummy = self._capture(extras.print_ports, fallback)
        self.assertEqual(status, 0)
        self.assertEqual(out.splitlines(),
                         ["80/tcp -> 8081", "91/tcp -> 9091"])

        priority = self._container(
            "p3", {"status": "exited", "ports": ["7070:70"]},
            {"argv": ["run", "-p", "9999:99", "cid"]})
        status, out, dummy = self._capture(extras.print_ports, priority)
        self.assertEqual(out.splitlines(), ["70/tcp -> 7070"])

        publish_all = self._container(
            "p4", {"status": "exited"}, {"argv": ["run", "-P", "cid"]})
        status, out, dummy = self._capture(extras.print_ports, publish_all)
        self.assertEqual(status, 1)
        self.assertIn("Notice", out)
        self.assertIn("no published ports", dummy)

    # --------------------------------------------------------------- df

    def test_16_system_df(self):
        """Test16 df totals, sharing and reclaimable sizes"""
        layer_map = {
            ("busybox", "latest"): [("/x/sha256:aaa", 1024),
                                    ("/x/sha256:bbb", 2048)],
            ("unused", "v1"): [("/x/sha256:ccc", 512)],
        }
        localrepo = Mock()
        localrepo.get_imagerepos.return_value = [("busybox", "latest"),
                                                  ("unused", "v1")]
        localrepo.get_layers.side_effect = lambda name, tag: layer_map[
            (name, tag)]
        localrepo.cd_imagerepo.return_value = "tagdir"
        localrepo.get_containers_list.return_value = [
            ("c1", "busybox:latest", []), ("c2", "", [])]
        localrepo.cd_container.side_effect = lambda cid: os.path.join(
            self.base, cid)
        localrepo.get_size.return_value = 2
        status, out, dummy = self._capture(extras.print_system_df, localrepo)
        self.assertEqual(status, 0)
        lines = out.splitlines()
        self.assertEqual(lines[0].split(),
                         ["TYPE", "TOTAL", "ACTIVE", "SIZE", "RECLAIMABLE"])
        images = lines[1].split()
        self.assertEqual(images[0], "Images")
        self.assertEqual(images[1], "2")
        self.assertEqual(images[2], "1")
        self.assertEqual(images[3], "3.50KB")
        self.assertEqual(images[4], "512B")
        containers = lines[2].split()
        self.assertEqual(containers[0], "Containers")
        self.assertEqual(containers[1], "2")
        self.assertEqual(containers[3], "4.00MB")
        self.assertIn("Local Volumes", out)
        self.assertIn("Build Cache", out)

    # ------------------------------------------------------------ prune

    def test_17_prune_containers(self):
        """Test17 container prune skips running and protected ones"""
        localrepo = Mock()
        localrepo.get_containers_list.return_value = [
            ("run", "busybox:latest", []), ("prot", "busybox:latest", []),
            ("ok", "busybox:latest", [])]
        localrepo.cd_container.side_effect = lambda cid: os.path.join(
            self.base, cid)
        localrepo.isprotected_container.side_effect = lambda cid: cid == "prot"
        localrepo.get_size.return_value = 1
        localrepo.del_container.return_value = True
        with patch("udocker.extras.supervisor.is_running",
                   side_effect=lambda path: os.path.basename(path) == "run"):
            status, out, dummy = self._capture(
                extras.system_prune, localrepo, "containers", True)
        self.assertEqual(status, 0)
        localrepo.del_container.assert_called_once_with("ok")
        self.assertIn("Deleted Containers:", out)
        self.assertIn("Total reclaimed space: 1.00MB", out)

        localrepo.reset_mock()
        localrepo.get_size.return_value = 1
        localrepo.isprotected_container.side_effect = \
            lambda cid: cid == "prot"
        localrepo.del_container.return_value = False
        with patch("udocker.extras.supervisor.is_running",
                   side_effect=lambda path: os.path.basename(path) == "run"):
            status, out, err = self._capture(
                extras.system_prune, localrepo, "containers", True)
        self.assertEqual(status, 1)
        self.assertIn("Error: deleting container", err)

    def test_18_prune_needs_force(self):
        """Test18 prune without -f needs a tty and a confirmation"""
        localrepo = Mock()
        with patch("udocker.extras._confirm", return_value=None):
            status, dummy, err = self._capture(
                extras.system_prune, localrepo, "containers")
        self.assertEqual(status, 1)
        self.assertIn("use -f", err)
        self.assertFalse(localrepo.del_container.called)

        with patch("udocker.extras._confirm", return_value=False):
            status, out, dummy = self._capture(
                extras.system_prune, localrepo, "images")
        self.assertEqual(status, 0)
        self.assertIn("Aborted", out)
        self.assertFalse(localrepo.del_imagerepo.called)

        with patch("udocker.extras._confirm", return_value=True), \
                patch("udocker.extras._prune_containers", return_value=(7, 0)):
            status, out, dummy = self._capture(
                extras.system_prune, localrepo, "containers")
        self.assertEqual(status, 0)
        self.assertIn("Total reclaimed space: 7B", out)

        status, dummy, err = self._capture(
            extras.system_prune, localrepo, "bogus", True)
        self.assertEqual(status, 1)
        self.assertIn("invalid prune target", err)

    def test_19_prune_images(self):
        """Test19 image prune keeps used and protected images"""
        layer_map = {
            ("used", "v1"): [("/x/sha256:a", 100)],
            ("unused", "v1"): [("/x/sha256:b", 200)],
            ("prot", "v1"): [("/x/sha256:c", 300)],
        }
        localrepo = Mock()
        localrepo.get_imagerepos.return_value = [
            ("used", "v1"), ("unused", "v1"), ("prot", "v1")]
        localrepo.get_containers_list.return_value = [("c1", "used:v1", [])]
        localrepo.cd_imagerepo.return_value = "tagdir"
        localrepo.get_layers.side_effect = lambda name, tag: layer_map[
            (name, tag)]
        localrepo.isprotected_imagerepo.side_effect = \
            lambda name, tag: (name, tag) == ("prot", "v1")
        localrepo.del_imagerepo.return_value = True
        status, out, dummy = self._capture(
            extras.system_prune, localrepo, "images", True)
        self.assertEqual(status, 0)
        localrepo.del_imagerepo.assert_called_once_with(
            "unused", "v1", force=True)
        self.assertIn("untagged: unused:v1", out)
        self.assertIn("Total reclaimed space: 200B", out)

    def test_20_prune_all(self):
        """Test20 prune all removes containers and unused images"""
        localrepo = Mock()
        localrepo.get_containers_list.return_value = [
            ("ok", "used:v1", [])]
        localrepo.cd_container.side_effect = lambda cid: os.path.join(
            self.base, cid)
        localrepo.isprotected_container.return_value = False
        localrepo.get_size.return_value = 1
        localrepo.del_container.return_value = True
        localrepo.get_imagerepos.return_value = [("used", "v1"),
                                                  ("unused", "v1")]
        localrepo.cd_imagerepo.return_value = "tagdir"
        localrepo.get_layers.side_effect = lambda name, tag: {
            ("used", "v1"): [("/x/sha256:a", 100)],
            ("unused", "v1"): [("/x/sha256:b", 200)],
        }[(name, tag)]
        localrepo.isprotected_imagerepo.return_value = False
        localrepo.del_imagerepo.return_value = True
        with patch("udocker.extras.supervisor.is_running",
                   return_value=False):
            status, out, dummy = self._capture(
                extras.system_prune, localrepo, "all", True)
        self.assertEqual(status, 0)
        self.assertTrue(localrepo.del_container.called)
        localrepo.del_imagerepo.assert_called_once_with(
            "unused", "v1", force=True)
        self.assertIn("Deleted Containers:", out)
        self.assertIn("Deleted Images:", out)
        self.assertIn("Total reclaimed space: 1.00MB", out)


if __name__ == '__main__':
    main()
