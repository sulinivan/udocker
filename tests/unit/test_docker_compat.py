#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
udocker unit tests: docker CLI compatibility (groups, ps/images output)
"""

import json
import os
import shutil
import tempfile
from unittest import TestCase, main
from unittest.mock import Mock, patch

from udocker.cli import UdockerCLI
from udocker.cmdparser import CmdParser
from udocker.config import Config
from udocker.umain import expand_compat_argv


class DockerCompatArgvTestCase(TestCase):
    """docker group syntax is rewritten to the udocker command"""

    def test_01_groups(self):
        """Test01 container/image/system groups and untouched commands"""
        self.assertEqual(expand_compat_argv(["udocker", "container", "ls"]),
                         ["udocker", "ps"])
        self.assertEqual(expand_compat_argv(["udocker", "container", "ls",
                                             "-a", "-q"]),
                         ["udocker", "ps", "-a", "-q"])
        self.assertEqual(expand_compat_argv(["udocker", "container", "rm",
                                             "web"]),
                         ["udocker", "rm", "web"])
        self.assertEqual(expand_compat_argv(["udocker", "image", "ls"]),
                         ["udocker", "images"])
        self.assertEqual(expand_compat_argv(["udocker", "image", "rm",
                                             "busybox"]),
                         ["udocker", "rmi", "busybox"])
        self.assertEqual(expand_compat_argv(["udocker", "image", "inspect",
                                             "busybox"]),
                         ["udocker", "inspect", "busybox"])
        self.assertEqual(expand_compat_argv(["udocker", "image", "prune"]),
                         ["udocker", "image", "prune"])
        self.assertEqual(expand_compat_argv(["udocker", "system", "df"]),
                         ["udocker", "system", "df"])
        self.assertEqual(expand_compat_argv(["udocker", "--repo=/r",
                                             "container", "ls"]),
                         ["udocker", "--repo=/r", "ps"])
        self.assertEqual(expand_compat_argv(["udocker", "ps", "-a"]),
                         ["udocker", "ps", "-a"])
        self.assertEqual(expand_compat_argv(["udocker", "container", "bogus"]),
                         ["udocker", "container", "bogus"])
        self.assertEqual(expand_compat_argv(["udocker", "container"]),
                         ["udocker", "container"])


class DockerCompatOutputTestCase(TestCase):
    """docker-like ps and images tables"""

    def setUp(self):
        Config().getconf()
        Config().conf['location'] = ""
        Config().conf['keystore'] = "KEYSTORE"
        self.base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base)

    @staticmethod
    def _cli(localrepo):
        localrepo.homedir = "/home/user"
        with patch('udocker.cli.DockerIoAPI'), \
                patch('udocker.cli.LocalFileAPI'), \
                patch('udocker.cli.KeyStore'):
            return UdockerCLI(localrepo)

    def _container_dir(self, container_id, state, command=None):
        container_dir = os.path.join(self.base, "containers", container_id)
        os.makedirs(os.path.join(container_dir, "ROOT"))
        with open(os.path.join(container_dir, "state.json"), "w") as filep:
            json.dump(state, filep)
        container_json = {"config": {"Cmd": command or ["true"]}}
        with open(os.path.join(container_dir, "container.json"),
                  "w") as filep:
            json.dump(container_json, filep)
        return container_dir

    def _localrepo(self, dirs):
        localrepo = Mock()
        localrepo.get_containers_list.return_value = [
            (cid, "busybox:latest", names)
            for (cid, (dummy, names)) in dirs.items()]
        localrepo.cd_container.side_effect = \
            lambda cid: dirs[cid][0] if cid in dirs else ""
        localrepo.isprotected_container.return_value = False
        localrepo.iswriteable_container.return_value = 1
        localrepo.get_size.return_value = 2
        return localrepo

    def _run_ps(self, localrepo, *args):
        cli = self._cli(localrepo)
        cmdp = CmdParser()
        cmdp.parse(["udocker", "ps"] + list(args))
        with patch('udocker.cli.Msg') as mock_msg, \
                patch('udocker.cli.ExecutionMode') as mock_exec, \
                patch('udocker.cli.ContainerStructure') as mock_structure, \
                patch('udocker.supervisor.reconcile'):
            mock_exec.return_value.get_mode.return_value = "P1"
            mock_structure.return_value.get_container_platform_fmt.\
                return_value = "linux/amd64"
            self.assertEqual(cli.do_ps(cmdp), 0)
        calls = mock_msg.return_value.out.call_args_list
        return "\n".join(str(call.args[0]) for call in calls)

    def test_02_ps_table(self):
        """Test02 ps hides stopped containers unless -a, docker columns"""
        running = self._container_dir(
            "run1", {"status": "running", "pid": os.getpid(),
                     "timestamp": "2026-11-10T10:00:00Z",
                     "ports": ["18080:80"]}, ["sleep", "60"])
        exited = self._container_dir(
            "ex1", {"status": "exited", "exitcode": 0,
                    "timestamp": "2026-11-10T10:00:00Z", "ports": []})
        localrepo = self._localrepo({"run1": (running, ["web"]),
                                     "ex1": (exited, [])})
        out = self._run_ps(localrepo)
        self.assertIn("CONTAINER ID", out)
        self.assertIn("COMMAND", out)
        self.assertIn("PORTS", out)
        self.assertIn("web", out)
        self.assertIn("0.0.0.0:18080->80/tcp", out)
        self.assertNotIn("ex1", out)
        out_all = self._run_ps(localrepo, "-a")
        self.assertIn("ex1", out_all)
        self.assertIn("Exited (0)", out_all)
        out_quiet = self._run_ps(localrepo, "-q")
        self.assertEqual(out_quiet.strip(), "run1")
        out_filter = self._run_ps(localrepo, "-f", "status=exited")
        self.assertIn("ex1", out_filter)
        self.assertNotIn("run1", out_filter)

    def _run_images(self, localrepo, *args):
        cli = self._cli(localrepo)
        cmdp = CmdParser()
        cmdp.parse(["udocker", "images"] + list(args))
        with patch('udocker.cli.Msg') as mock_msg:
            self.assertEqual(cli.do_images(cmdp), 0)
        calls = mock_msg.return_value.out.call_args_list
        return "\n".join(str(call.args[0]) for call in calls)

    def test_03_images_table(self):
        """Test03 images prints REPOSITORY/TAG/ID/CREATED/SIZE and -q"""
        localrepo = Mock()
        localrepo.get_imagerepos.return_value = [("busybox", "latest")]
        localrepo.cd_imagerepo.return_value = "/repos/busybox/latest"
        localrepo.isprotected_imagerepo.return_value = False
        localrepo.get_layers.return_value = [("/x/aaa.layer", 1048576)]
        localrepo.load_json.return_value = None
        localrepo.get_image_attributes.return_value = (None, None)
        out = self._run_images(localrepo)
        self.assertIn("REPOSITORY", out)
        self.assertIn("busybox", out)
        self.assertIn("latest", out)
        self.assertIn("aaa", out)
        self.assertIn("1.00MB", out)
        out_quiet = self._run_images(localrepo, "-q")
        self.assertEqual(out_quiet.strip(), "aaa")


    def test_04_generated_name(self):
        """Test04 unnamed containers get a docker style random name"""
        localrepo = Mock()
        localrepo.get_container_id.return_value = ""
        cli = self._cli(localrepo)
        name = cli._generated_container_name()
        self.assertIn("_", name)
        self.assertGreater(len(name), 4)

if __name__ == '__main__':
    main()
