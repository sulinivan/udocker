#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
udocker unit tests: docker CLI parity fixes

Covers the drop-in shim (udocker/compat.py) and the command flags that were
added after comparing the real docker CLI with udocker:
create recording run options, start replaying them, ps --last/--latest/--size,
logs --since/--until/--timestamps, images --filter, rmi with several images,
stats/docker JSON output and the docker search record/filter helpers.
"""

import csv
import json
import os
import shutil
import sys
import tempfile
from unittest import TestCase, main
from unittest.mock import Mock, patch

from udocker import compat
from udocker.cli import UdockerCLI
from udocker.cmdparser import CmdParser
from udocker.config import Config
from udocker import extras


class CompatShimTestCase(TestCase):
    """The docker flags rootless udocker cannot honour"""

    def test_01_ignored(self):
        """Test01 harmless docker flags are dropped from the command line"""
        argv, refusal, page = compat.rewrite(
            ["udocker", "run", "--quiet", "--init", "busybox"])
        self.assertIsNone(refusal)
        self.assertEqual(page, "run")
        self.assertEqual(argv, ["udocker", "run", "busybox"])

    def test_02_ignored_space_value(self):
        """Test02 a space separated value goes with the dropped flag"""
        argv, refusal, dummy = compat.rewrite(
            ["udocker", "run", "--log-driver", "json", "busybox"])
        self.assertIsNone(refusal)
        self.assertEqual(argv, ["udocker", "run", "busybox"])

    def test_03_refused(self):
        """Test03 cgroup and privilege flags are refused explicitly"""
        for flag in ("--memory=1g", "--cpus=2", "--privileged", "--cap-add=X",
                     "--read-only", "--tmpfs=/tmp"):
            (dummy, refusal, page) = compat.rewrite(
                ["udocker", "run", flag, "busybox"])
            self.assertTrue(refusal, flag)
            self.assertIn(flag.split("=")[0], refusal)
            self.assertEqual(page, "run")

    def test_04_allowed_values(self):
        """Test04 host ipc/pid/uts/network and no-new-privileges pass"""
        for flag in ("--network=host", "--network", "--ipc=host",
                     "--pid=host", "--uts=host",
                     "--security-opt=no-new-privileges"):
            argv, refusal, dummy = compat.rewrite(
                ["udocker", "run", flag, "busybox"]
                if "=" in flag else ["udocker", "run", flag, "host",
                                     "busybox"])
            self.assertIsNone(refusal, flag)
            self.assertNotIn(flag.split("=")[0], argv)

    def test_05_refused_value(self):
        """Test05 a network docker cannot provide rootless is refused"""
        (dummy, refusal, dummy2) = compat.rewrite(
            ["udocker", "run", "--network=overlay", "busybox"])
        self.assertIn("--network", refusal)

    def test_06_group_pages(self):
        """Test06 group syntax pages are handled too"""
        argv, refusal, page = compat.rewrite(
            ["udocker", "container", "run", "--quiet", "img"])
        self.assertIsNone(refusal)
        self.assertEqual(page, "container run")
        self.assertEqual(argv, ["udocker", "container", "run", "img"])
        (dummy, refusal, dummy2) = compat.rewrite(
            ["udocker", "container", "run", "--memory", "1g", "img"])
        self.assertIn("--memory", refusal)

    def test_07_end_of_options(self):
        """Test07 everything after -- belongs to the container command"""
        argv, refusal, dummy = compat.rewrite(
            ["udocker", "run", "busybox", "--", "--memory=1g"])
        self.assertIsNone(refusal)
        self.assertEqual(argv[-2:], ["--", "--memory=1g"])
        (dummy, refusal, dummy2) = compat.rewrite(
            ["udocker", "run", "--", "--memory=1g"])
        self.assertIsNone(refusal)

    def test_08_short_options(self):
        """Test08 docker short options map to their long counterpart"""
        (dummy, refusal, dummy2) = compat.rewrite(
            ["udocker", "run", "-m", "1g", "busybox"])
        self.assertIn("--memory", refusal)
        argv, refusal, dummy = compat.rewrite(
            ["udocker", "run", "-q", "-a", "stdout", "busybox"])
        self.assertIsNone(refusal)
        self.assertEqual(argv, ["udocker", "run", "busybox"])


class CreateReplayTestCase(TestCase):
    """docker create accepts the run flags and start replays them"""

    def setUp(self):
        Config().getconf()
        Config().conf['location'] = ""
        Config().conf['keystore'] = "KEYSTORE"
        self.base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base)

    def _cli(self):
        localrepo = Mock()
        localrepo.homedir = "/home/user"
        with patch('udocker.cli.DockerIoAPI'), \
                patch('udocker.cli.LocalFileAPI'), \
                patch('udocker.cli.KeyStore'):
            return UdockerCLI(localrepo)

    def test_01_create_records_run_flags(self):
        """Test01 create --name/-v records a replayable run command line"""
        container_dir = os.path.join(self.base, "containers", "CID")
        os.makedirs(container_dir)
        cli = self._cli()
        cli.localrepo.get_container_id.return_value = None
        cli.localrepo.cd_container.return_value = container_dir
        cli.localrepo.set_container_name.return_value = True
        cmdp = CmdParser()
        cmdp.parse(["udocker", "create", "--name=web",
                    "-v", "/tmp:/data", "--label", "a=b", "busybox"])
        argv = ["udocker", "create", "--name=web",
                "-v", "/tmp:/data", "--label", "a=b", "busybox"]
        with patch('udocker.cli.Msg'), \
                patch.object(cli, "_create", return_value="CID"), \
                patch.object(sys, "argv", argv):
            self.assertEqual(cli.do_create(cmdp), 0)
        with open(os.path.join(container_dir, "create.json")) as handle:
            recorded = json.load(handle)
        self.assertEqual(recorded["image"], "busybox")
        replay = recorded["argv"]
        self.assertIn("run", replay)
        self.assertIn("CID", replay)
        self.assertIn("/tmp:/data", replay)
        self.assertNotIn("--name=web", replay)
        self.assertEqual(replay[-1], "CID")

    def test_02_start_replays(self):
        """Test02 start spawns the recorded create command line"""
        container_dir = os.path.join(self.base, "containers", "CID")
        os.makedirs(container_dir)
        cli = self._cli()
        cli.localrepo.cd_container.return_value = container_dir
        cmdp = CmdParser()
        cmdp.parse(["udocker", "start", "CID"])
        replay = ["run", "CID"]
        with patch('udocker.cli.Msg'), \
                patch.object(cli, "_resolve_container", return_value="CID"), \
                patch.object(cli, "_created_argv", return_value=replay), \
                patch.object(cli, "_is_runc_mode", return_value=False), \
                patch('udocker.cli.supervisor.is_running',
                      return_value=False), \
                patch('udocker.cli.supervisor.read_conf',
                      return_value={"argv": []}), \
                patch('udocker.cli.supervisor.read_state',
                      return_value={"status": "exited"}), \
                patch('udocker.cli.supervisor.clear_stopped'), \
                patch('udocker.cli.supervisor.spawn',
                      return_value=True) as spawn:
            self.assertEqual(cli.do_start(cmdp), 0)
        self.assertEqual(spawn.call_args[0][2], replay)


class DockerCommandFlagsTestCase(TestCase):
    """docker long option spellings and docker-shaped outputs"""

    def setUp(self):
        Config().getconf()
        Config().conf['location'] = ""
        Config().conf['keystore'] = "KEYSTORE"
        self.base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base)

    def _cli(self):
        localrepo = Mock()
        localrepo.homedir = "/home/user"
        with patch('udocker.cli.DockerIoAPI'), \
                patch('udocker.cli.LocalFileAPI'), \
                patch('udocker.cli.KeyStore'):
            return UdockerCLI(localrepo)

    def test_01_ps_last_latest_size(self):
        """Test01 ps --last/--latest/--size behave like docker"""
        containers = []
        for (index, container_id) in enumerate(("a1", "b2", "c3")):
            container_dir = os.path.join(self.base, container_id)
            os.makedirs(os.path.join(container_dir, "ROOT"))
            with open(os.path.join(container_dir, "state.json"), "w") as fd:
                json.dump({"status": "exited", "exitcode": 0}, fd)
            with open(os.path.join(container_dir, "container.json"), "w") as fd:
                json.dump({"config": {"Cmd": ["true"]}}, fd)
            os.utime(os.path.join(container_dir, "container.json"),
                     (1000 + index, 1000 + index))
            containers.append((container_id, "busybox:latest", []))
        cli = self._cli()
        cli.localrepo.get_containers_list.return_value = containers
        cli.localrepo.cd_container.side_effect = \
            lambda cid: os.path.join(self.base, cid)
        cli.localrepo.isprotected_container.return_value = False
        cli.localrepo.iswriteable_container.return_value = 1
        cli.localrepo.get_size.return_value = 1

        def run(*args):
            cmdp = CmdParser()
            cmdp.parse(["udocker", "ps"] + list(args))
            with patch('udocker.cli.Msg') as mock_msg, \
                    patch('udocker.cli.ExecutionMode'), \
                    patch('udocker.cli.ContainerStructure'), \
                    patch('udocker.supervisor.reconcile'):
                self.assertEqual(cli.do_ps(cmdp), 0)
            return [str(call.args[0]) for call in
                    mock_msg.return_value.out.call_args_list]

        out = " ".join(run("-a", "--last", "1"))
        self.assertIn("c3", out)
        self.assertNotIn("a1", out)
        out = " ".join(run("-a", "--latest"))
        self.assertIn("c3", out)
        self.assertNotIn("b2", out)
        out = " ".join(run("-a", "--size"))
        self.assertIn("SIZE", out)

    def test_02_logs_flags(self):
        """Test02 logs passes --since/--until/--timestamps to the supervisor"""
        cli = self._cli()
        cmdp = CmdParser()
        cmdp.parse(["udocker", "logs", "--since", "1h", "--until=2h",
                    "--timestamps", "CID"])
        with patch('udocker.cli.Msg'), \
                patch.object(cli, "_resolve_container", return_value="CID"), \
                patch('udocker.cli.supervisor.logs',
                      return_value=0) as logs:
            self.assertEqual(cli.do_logs(cmdp), 0)
        args = logs.call_args[0]
        self.assertTrue(args[4])
        self.assertTrue(args[5])
        self.assertIsNotNone(args[3])

    def test_03_images_filter(self):
        """Test03 images --filter reference= works like docker"""
        cli = self._cli()
        rows = [{"repository": "busybox", "tag": "latest"},
                {"repository": "ubuntu", "tag": "24.04"}]
        selected = cli._filter_image_rows(rows, ["reference=ubuntu*"])
        self.assertEqual([row["repository"] for row in selected], ["ubuntu"])
        selected = cli._filter_image_rows(rows, ["dangling=false"])
        self.assertEqual(len(selected), 2)

    def test_04_stats_json(self):
        """Test04 stats --format json prints one docker record per line"""
        records = [("cid123456789", "web", "1.00%", "1MiB / 2MiB", "50.00%",
                    "3")]
        with patch('udocker.extras.Msg') as mock_msg:
            self.assertEqual(extras.print_stats_records(records, "json"), 0)
        line = mock_msg.return_value.out.call_args_list[0].args[0]
        record = json.loads(line)
        self.assertEqual(record["Container"], "cid123456789")
        self.assertEqual(record["Name"], "web")
        self.assertEqual(record["PIDs"], "3")

    def test_05_rmi_multiple(self):
        """Test05 rmi removes every image given on the command line"""
        cli = self._cli()
        cmdp = CmdParser()
        cmdp.parse(["udocker", "rmi", "-f", "one:1", "two:2"])
        with patch.object(cli, "_rmi_one", return_value=0) as rmi_one:
            self.assertEqual(cli.do_rmi(cmdp), 0)
        self.assertEqual([call.args[0] for call in rmi_one.call_args_list],
                         ["one:1", "two:2"])
        self.assertTrue(rmi_one.call_args_list[0].args[1])

    def test_06_search_records(self):
        """Test06 search records and --filter is-official/stars"""
        page = {"results": [
            {"name": "busybox", "star_count": 100, "is_official": True,
             "description": "tiny"},
            {"name": "someone/busybox", "star_count": 5,
             "is_official": False, "description": "fork"},
        ]}
        records = UdockerCLI._search_records(page)
        self.assertEqual(records[0]["Name"], "busybox")
        self.assertEqual(records[0]["IsOfficial"], "true")
        selected = [record for record in records
                    if UdockerCLI._search_match(record, ["is-official=true"])]
        self.assertEqual(len(selected), 1)
        selected = [record for record in records
                    if UdockerCLI._search_match(record, ["stars=10"])]
        self.assertEqual(selected[0]["Name"], "busybox")

    def test_07_export_output(self):
        """Test07 export --output=<file> takes the file as option value"""
        cli = self._cli()
        cmdp = CmdParser()
        target = os.path.join(self.base, "out.tar")
        cmdp.parse(["udocker", "export", "--output=" + target, "CID"])
        cli.localrepo.get_container_id.return_value = "CID"
        with patch('udocker.cli.Msg') as mock_msg, \
                patch('udocker.cli.ContainerStructure') as structure:
            structure.return_value.export_tofile.return_value = True
            self.assertEqual(cli.do_export(cmdp), 0)
        self.assertEqual(
            structure.return_value.export_tofile.call_args[0][0], target)
        self.assertFalse(mock_msg.return_value.err.called)


class ProbeTableTestCase(TestCase):
    """The generated table must keep its docker-side marks"""

    def test_01_table_present(self):
        """Test01 replica/cli-flags.csv is generated and marked"""
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))), "replica",
            "cli-flags.csv")
        if not os.path.exists(path):
            self.skipTest("table not generated in this checkout")
        with open(path) as handle:
            rows = list(csv.DictReader(handle))
        self.assertGreater(len(rows), 100)
        states = {row["state"] for row in rows}
        self.assertTrue(states & {"ok", "accepted", "missing"})


if __name__ == '__main__':
    main()
