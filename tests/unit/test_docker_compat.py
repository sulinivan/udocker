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
from udocker import supervisor
from udocker.umain import expand_compat_argv
from udocker.cli import _parse_time_arg


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
        out_tmpl = self._run_ps(localrepo, "--format",
                                "{{.ID}} {{.Names}} {{.State}}")
        self.assertIn("run1 web running", out_tmpl)
        out_json = self._run_ps(localrepo, "--format", "json")
        record = json.loads(out_json)
        self.assertEqual(record["ID"], "run1")
        self.assertEqual(record["Names"], "web")
        self.assertEqual(record["State"], "running")

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
        out_tmpl = self._run_images(localrepo, "--format",
                                    "{{.Repository}}:{{.Tag}} {{.ID}}")
        self.assertEqual(out_tmpl.strip(), "busybox:latest aaa")
        out_json = self._run_images(localrepo, "--format", "json")
        record = json.loads(out_json)
        self.assertEqual(record["Repository"], "busybox")
        self.assertEqual(record["Tag"], "latest")
        self.assertEqual(record["ID"], "aaa")

    def test_05_inspect(self):
        """Test05 inspect prints docker-shaped JSON and templates"""
        from udocker.container.localrepo import LocalRepository
        repo = LocalRepository(self.base)
        self.assertTrue(repo.create_repo())
        cid = "cafe1234-0000-0000-0000-000000000000"
        container_dir = os.path.join(self.base, "containers", cid)
        os.makedirs(os.path.join(container_dir, "ROOT"))
        with open(os.path.join(container_dir, "container.json"), "w") as fp:
            json.dump({"config": {"Cmd": ["sh"], "Env": ["A=1"]},
                       "created": "2026-01-01T00:00:00Z"}, fp)
        with open(os.path.join(container_dir, "state.json"), "w") as fp:
            json.dump({"status": "exited", "exitcode": 7,
                       "timestamp": "2026-11-10T10:00:00Z",
                       "ports": []}, fp)
        with open(os.path.join(container_dir, "cmd.json"), "w") as fp:
            json.dump({"entrypoint": [], "cmd": ["echo", "hi"]}, fp)
        with open(os.path.join(container_dir, "volumes.json"), "w") as fp:
            json.dump(["vol1:/data"], fp)
        with open(os.path.join(container_dir, "labels.json"), "w") as fp:
            json.dump({"team": "infra"}, fp)
        self.assertTrue(repo.create_volume("vol1"))
        self.assertTrue(repo.set_container_name(cid, "web"))
        cli = self._cli(repo)
        cmdp = CmdParser()
        cmdp.parse(["udocker", "inspect", cid])
        with patch('udocker.cli.Msg') as mock_msg:
            self.assertEqual(cli.do_inspect(cmdp), 0)
        data = json.loads(mock_msg.return_value.out.call_args[0][0])
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["Id"], cid)
        self.assertEqual(data[0]["Name"], "/web")
        self.assertEqual(data[0]["State"]["Status"], "exited")
        self.assertEqual(data[0]["State"]["ExitCode"], 7)
        self.assertEqual(data[0]["Config"]["Cmd"], ["echo", "hi"])
        self.assertEqual(data[0]["Mounts"][0]["Type"], "volume")
        self.assertEqual(data[0]["Mounts"][0]["Name"], "vol1")
        self.assertEqual(data[0]["HostConfig"]["NetworkMode"], "host")
        self.assertEqual(data[0]["Config"]["Labels"], {"team": "infra"})
        cmdp = CmdParser()
        cmdp.parse(["udocker", "inspect", "-f", "{{.State.ExitCode}}",
                    "--type=container", cid])
        with patch('udocker.cli.Msg') as mock_msg:
            self.assertEqual(cli.do_inspect(cmdp), 0)
        self.assertEqual(mock_msg.return_value.out.call_args[0][0], "7")

    def test_06_paused_ps(self):
        """Test06 paused containers are listed by default with docker text"""
        container_dir = self._container_dir(
            "pau1", {"status": "paused", "pid": os.getpid(),
                     "timestamp": "2026-11-10T10:00:00Z", "ports": []})
        localrepo = self._localrepo({"pau1": (container_dir, ["idle"])})
        out = self._run_ps(localrepo)
        self.assertIn("pau1", out)
        self.assertIn("(Paused)", out)
        out_state = self._run_ps(localrepo, "--format", "{{.State}}")
        self.assertEqual(out_state.strip(), "paused")

    def test_07_info_and_version(self):
        """Test06 info and version print docker fields and templates"""
        from udocker import __version__
        localrepo = Mock()
        localrepo.get_containers_list.return_value = []
        localrepo.get_imagerepos.return_value = []
        localrepo.get_volumes_list.return_value = []
        cli = self._cli(localrepo)
        for argv in (["udocker", "info"], ["udocker", "version"]):
            cmdp = CmdParser()
            cmdp.parse(argv)
            with patch('udocker.cli.Msg') as mock_msg:
                self.assertEqual(getattr(cli, "do_" + argv[1])(cmdp), 0)
            self.assertTrue(mock_msg.return_value.out.called)
        cmdp = CmdParser()
        cmdp.parse(["udocker", "info", "-f", "{{.ServerVersion}}"])
        with patch('udocker.cli.Msg') as mock_msg:
            self.assertEqual(cli.do_info(cmdp), 0)
        self.assertEqual(mock_msg.return_value.out.call_args[0][0],
                         __version__)
        cmdp = CmdParser()
        cmdp.parse(["udocker", "version", "-f", "{{.Server.Version}}"])
        with patch('udocker.cli.Msg') as mock_msg:
            self.assertEqual(cli.do_version(cmdp), 0)
        self.assertEqual(mock_msg.return_value.out.call_args[0][0],
                         __version__)


    def test_04_generated_name(self):
        """Test04 unnamed containers get a docker style random name"""
        localrepo = Mock()
        localrepo.get_container_id.return_value = ""
        cli = self._cli(localrepo)
        name = cli._generated_container_name()
        self.assertIn("_", name)
        self.assertGreater(len(name), 4)

    def test_08_network(self):
        """Test08 network ls/inspect and the root-only refusal"""
        localrepo = Mock()
        cli = self._cli(localrepo)
        cmdp = CmdParser()
        cmdp.parse(["udocker", "network", "ls"])
        with patch('udocker.cli.Msg') as mock_msg:
            self.assertEqual(cli.do_network(cmdp), 0)
        out = "\n".join(str(call.args[0]) for call in
                         mock_msg.return_value.out.call_args_list)
        self.assertIn("NETWORK ID", out)
        self.assertIn("host", out)
        self.assertIn("none", out)
        cmdp = CmdParser()
        cmdp.parse(["udocker", "network", "ls", "--format", "json"])
        with patch('udocker.cli.Msg') as mock_msg:
            self.assertEqual(cli.do_network(cmdp), 0)
        record = json.loads(
            mock_msg.return_value.out.call_args_list[0][0][0])
        self.assertEqual(record["Name"], "host")
        self.assertEqual(record["Driver"], "host")
        cmdp = CmdParser()
        cmdp.parse(["udocker", "network", "inspect", "host"])
        with patch('udocker.cli.Msg') as mock_msg:
            self.assertEqual(cli.do_network(cmdp), 0)
        data = json.loads(mock_msg.return_value.out.call_args[0][0])
        self.assertEqual(data[0]["Name"], "host")
        for subcmd in ("inspect", "create"):
            cmdp = CmdParser()
            if subcmd == "inspect":
                cmdp.parse(["udocker", "network", "inspect", "nope"])
            else:
                cmdp.parse(["udocker", "network", "create", "foo"])
            with patch('udocker.cli.Msg'):
                self.assertEqual(cli.do_network(cmdp), 1)

    def test_09_stop_signal(self):
        """Test09 stop uses the signal and timeout recorded by run"""
        container_dir = self._container_dir(
            "stop1", {"status": "running", "pid": os.getpid(),
                      "timestamp": "2026-11-10T10:00:00Z", "ports": []})
        with open(os.path.join(container_dir, "stop.json"), "w") as filep:
            json.dump({"signal": "SIGQUIT", "timeout": 5}, filep)
        localrepo = Mock()
        localrepo.get_container_id.return_value = "stop1"
        localrepo.cd_container.return_value = container_dir
        cli = self._cli(localrepo)
        cmdp = CmdParser()
        cmdp.parse(["udocker", "stop", "stop1"])
        with patch('udocker.cli.Msg'), \
                patch('udocker.cli.ExecutionMode') as mock_exec, \
                patch('udocker.cli.supervisor.stop_monitor',
                      return_value=0) as mock_stop:
            mock_exec.return_value.get_mode.return_value = "P1"
            self.assertEqual(cli.do_stop(cmdp), 0)
        mock_stop.assert_called_once_with(container_dir, 5, sig="SIGQUIT")

    def test_10_restart_policy(self):
        """Test10 restart policy validation, counters and stop marker"""
        cli = self._cli(Mock())
        for policy in ("always", "unless-stopped", "on-failure",
                       "on-failure:3", "no"):
            self.assertTrue(cli._valid_restart_policy(policy), policy)
        for policy in ("sometimes", "on-failure:x", "", None):
            self.assertFalse(cli._valid_restart_policy(policy), policy)
        container_dir = self._container_dir(
            "rs1", {"status": "exited", "exitcode": 3})
        self.assertTrue(cli._restart_requested("always", 0, container_dir))
        self.assertFalse(cli._restart_requested("on-failure", 0,
                                                container_dir))
        self.assertTrue(cli._restart_requested("on-failure", 3,
                                               container_dir))
        self.assertTrue(cli._restart_requested("on-failure:2", 3,
                                               container_dir))
        self.assertTrue(cli._restart_requested("on-failure:2", 3,
                                               container_dir))
        self.assertFalse(cli._restart_requested("on-failure:2", 3,
                                                container_dir))
        supervisor.mark_stopped(container_dir)
        self.assertFalse(cli._restart_requested("always", 3, container_dir))
        supervisor.clear_stopped(container_dir)


    def test_11_events(self):
        """Test11 event records, snapshot diff and filters"""
        cli = self._cli(Mock())
        record = cli._event_record(
            "start", {"id": "c1", "image": "busybox:latest", "name": "web"},
            1000)
        self.assertEqual(record["Type"], "container")
        self.assertEqual(record["Action"], "start")
        self.assertEqual(record["Actor"]["ID"], "c1")
        self.assertEqual(record["Actor"]["Attributes"]["name"], "web")
        self.assertEqual(record["time"], 1000)
        old = {}
        new = {"c1": {"id": "c1", "status": "running",
                      "image": "i", "name": "n"}}
        diff = cli._event_diff(old, new)
        self.assertEqual([item[0] for item in diff], ["create", "start"])
        paused = {"c1": {"id": "c1", "status": "paused",
                         "image": "i", "name": "n"}}
        self.assertEqual([item[0] for item in cli._event_diff(new, paused)],
                         ["pause"])
        self.assertEqual([item[0] for item in cli._event_diff(paused, new)],
                         ["unpause"])
        exited = {"c1": {"id": "c1", "status": "exited",
                         "image": "i", "name": "n"}}
        self.assertEqual([item[0] for item in cli._event_diff(new, exited)],
                         ["die"])
        self.assertEqual([item[0] for item in cli._event_diff(new, {})],
                         ["destroy"])
        self.assertTrue(cli._event_matches(
            "start", {"id": "c1", "name": "web", "image": "i"},
            ["type=container", "action=start"]))
        self.assertFalse(cli._event_matches(
            "die", {"id": "c1", "name": "web", "image": "i"},
            ["event=start"]))
        self.assertTrue(cli._event_matches(
            "die", {"id": "c1", "name": "web", "image": "i"},
            ["container=c1"]))
        import time as time_module
        self.assertAlmostEqual(_parse_time_arg("10m"),
                               time_module.time() - 600, delta=5)
        self.assertAlmostEqual(_parse_time_arg("1h30m"),
                               time_module.time() - 5400, delta=5)
        self.assertIsNotNone(_parse_time_arg("2026-11-10T10:00:00Z"))
        self.assertIsNone(_parse_time_arg("bad"))

    def test_12_prune_and_table(self):
        """Test12 container/image/network prune and table output"""
        localrepo = Mock()
        cli = self._cli(localrepo)
        with patch('udocker.cli.extras.system_prune',
                   return_value=0) as mock_prune:
            cmdp = CmdParser()
            cmdp.parse(["udocker", "container-prune", "-f"])
            self.assertEqual(cli.do_container_prune(cmdp), 0)
            mock_prune.assert_called_once_with(localrepo, "containers", True)
        with patch('udocker.cli.extras.system_prune',
                   return_value=0) as mock_prune:
            cmdp = CmdParser()
            cmdp.parse(["udocker", "image", "prune", "-a", "-f"])
            self.assertEqual(cli.do_image(cmdp), 0)
            mock_prune.assert_called_once_with(localrepo, "images", True)
        cmdp = CmdParser()
        cmdp.parse(["udocker", "network", "prune", "-f"])
        with patch('udocker.cli.Msg'):
            self.assertEqual(cli.do_network(cmdp), 0)

    def test_13_ps_table_format(self):
        """Test13 ps --format 'table ...' prints docker-like columns"""
        container_dir = self._container_dir(
            "tab1", {"status": "running", "pid": os.getpid(),
                     "timestamp": "2026-11-10T10:00:00Z", "ports": []})
        localrepo = self._localrepo({"tab1": (container_dir, ["web"])})
        out = self._run_ps(localrepo, "--format",
                           "table {{.ID}}\t{{.Names}}")
        lines = out.splitlines()
        self.assertEqual(lines[0].split(), ["ID", "NAMES"])
        self.assertIn("web", lines[1])

if __name__ == '__main__':
    main()
