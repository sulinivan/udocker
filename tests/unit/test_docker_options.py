#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
udocker unit tests: run options (dns, tty, stdin, volumes-from, -P)
and the engine agnostic supervisor helpers
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from unittest import TestCase, main
from unittest.mock import Mock, patch

from udocker import supervisor
from udocker.cmdparser import CmdParser
from udocker.cli import UdockerCLI
from udocker.config import Config
from udocker.engine.base import ExecutionEngineCommon
from udocker.utils.uenv import Uenv


def _run_options(engine, args):
    """Parse run options into a minimal fake engine"""
    cmdp = CmdParser()
    cmdp.parse(["udocker", "run"] + args)
    localrepo = Mock()
    with patch('udocker.cli.DockerIoAPI'), \
            patch('udocker.cli.LocalFileAPI'), \
            patch('udocker.cli.KeyStore'):
        localrepo.homedir = "/home/user"
        cli = UdockerCLI(localrepo)
    cli._get_run_options(cmdp, engine)
    return cmdp


def _engine_opt():
    """Minimal run option dict for the extendable options"""
    return {"env": Uenv(), "envfile": [], "vol": [], "portsmap": [],
            "novol": [], "devices": [], "volfrom": [], "dns": [],
            "dnssearch": [], "tty": False, "interactive": False}


class DockerOptionsTestCase(TestCase):
    """Run options that used to be accepted but ignored"""

    def setUp(self):
        Config().getconf()
        Config().conf['location'] = ""
        # the test environment may point TMPDIR at a read only directory
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir)
        old_tmpdir = Config.conf['tmpdir']
        self.addCleanup(Config.conf.__setitem__, 'tmpdir', old_tmpdir)
        Config.conf['tmpdir'] = self.tmpdir

    def test_01_tty_interactive_parsing(self):
        """Test01 -t/-i are read into the engine options"""
        engine = Mock()
        engine.opt = _engine_opt()
        _run_options(engine, ["-i", "-t", "CID"])
        self.assertTrue(engine.opt["tty"])
        self.assertTrue(engine.opt["interactive"])
        engine.opt = _engine_opt()
        _run_options(engine, ["CID"])
        self.assertFalse(engine.opt["tty"])
        self.assertFalse(engine.opt["interactive"])

    def test_02_dns_options(self):
        """Test02 --dns and --dns-search are repeatable lists"""
        engine = Mock()
        engine.opt = _engine_opt()
        _run_options(engine, ["--dns=1.1.1.1", "--dns=8.8.8.8",
                              "--dns-search=example.com", "CID"])
        self.assertEqual(engine.opt["dns"], ["1.1.1.1", "8.8.8.8"])
        self.assertEqual(engine.opt["dnssearch"], ["example.com"])

    def test_03_resolv_conf(self):
        """Test03 a private resolv.conf replaces the host binding"""
        engine = ExecutionEngineCommon(Mock(), Mock())
        engine.opt = {"dns": ["1.2.3.4"], "dnssearch": ["lan"],
                      "vol": ["/etc/resolv.conf:/etc/resolv.conf",
                              "/data:/mnt"]}
        self.assertTrue(engine._setup_resolv_conf())
        vol = engine.opt["vol"]
        self.assertEqual(len(vol), 2)
        self.assertNotIn("/etc/resolv.conf:/etc/resolv.conf", vol)
        self.assertIn("/data:/mnt", vol)
        host_file = vol[1].split(":")[0]
        self.assertTrue(host_file.endswith("-resolv.conf"))
        with open(host_file) as filep:
            content = filep.read()
        self.assertIn("nameserver 1.2.3.4", content)
        self.assertIn("search lan", content)
        os.remove(host_file)

    def test_04_no_dns_no_change(self):
        """Test04 without --dns the volume list is untouched"""
        engine = ExecutionEngineCommon(Mock(), Mock())
        vols = ["/etc/resolv.conf:/etc/resolv.conf"]
        engine.opt = {"dns": [], "dnssearch": [], "vol": list(vols)}
        self.assertTrue(engine._setup_resolv_conf())
        self.assertEqual(engine.opt["vol"], vols)

    def test_05_stdin_policy(self):
        """Test05 stdin is closed for pipes unless -i is given"""
        engine = ExecutionEngineCommon(Mock(), Mock())
        engine.opt = {"interactive": False}
        with patch('udocker.engine.base.sys.stdin') as mock_stdin:
            mock_stdin.isatty.return_value = False
            self.assertFalse(engine._stdin_attached())
            engine.opt["interactive"] = True
            self.assertTrue(engine._stdin_attached())
            engine.opt["interactive"] = False
            mock_stdin.isatty.return_value = True
            self.assertTrue(engine._stdin_attached())

    def test_06_detach_argv(self):
        """Test06 -P is replaced by explicit -p for the monitor"""
        localrepo = Mock()
        localrepo.homedir = "/home/user"
        with patch('udocker.cli.DockerIoAPI'), \
                patch('udocker.cli.LocalFileAPI'), \
                patch('udocker.cli.KeyStore'):
            cli = UdockerCLI(localrepo)
        argv_in = ["udocker", "run", "-d", "-P", "--name=web", "CID", "sh"]
        with patch.object(sys, "argv", argv_in):
            argv = cli._detach_argv("CID", "CID",
                                    ports=["43210:8080"], netcoop=False)
        self.assertNotIn("-d", argv)
        self.assertNotIn("-P", argv)
        self.assertNotIn("--name=web", argv)
        self.assertIn("--publish=43210:8080", argv)
        self.assertIn("--nobanner", argv)
        self.assertEqual(argv[0], "run")

    def test_07_publish_all(self):
        """Test07 -P maps the image exposed ports to free host ports"""
        localrepo = Mock()
        localrepo.homedir = "/home/user"
        with patch('udocker.cli.DockerIoAPI'), \
                patch('udocker.cli.LocalFileAPI'), \
                patch('udocker.cli.KeyStore'):
            cli = UdockerCLI(localrepo)
        engine = Mock()
        engine.opt = {"portsmap": [], "netcoop": True}
        structure = Mock()
        structure.get_container_attr.return_value = ("/dir", {"config": {}})
        structure.get_container_meta.return_value = ["8080/tcp:{}"]
        with patch('udocker.cli.ContainerStructure', return_value=structure), \
                patch.object(UdockerCLI, '_free_tcp_port',
                             return_value=43210):
            self.assertTrue(cli._expand_publish_all(engine, "CID"))
        self.assertEqual(engine.opt["portsmap"], ["43210:8080"])
        self.assertFalse(engine.opt["netcoop"])
        # already expanded, nothing to do
        self.assertTrue(cli._expand_publish_all(engine, "CID"))
        self.assertEqual(engine.opt["portsmap"], ["43210:8080"])

    def test_08_volumes_from(self):
        """Test08 --volumes-from copies the recorded volume bindings"""
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base)
        ref_dir = os.path.join(base, "containers", "REF")
        os.makedirs(ref_dir)
        with open(os.path.join(ref_dir, "volumes.json"), "w") as filep:
            json.dump(["/src:/data"], filep)
        localrepo = Mock()
        localrepo.homedir = "/home/user"
        localrepo.get_container_id.return_value = "REF"
        localrepo.cd_container.return_value = ref_dir
        with patch('udocker.cli.DockerIoAPI'), \
                patch('udocker.cli.LocalFileAPI'), \
                patch('udocker.cli.KeyStore'):
            cli = UdockerCLI(localrepo)
        engine = Mock()
        engine.opt = {"vol": ["/already:/already"], "volfrom": ["REF"]}
        self.assertTrue(cli._expand_volumes_from(engine))
        self.assertEqual(engine.opt["vol"], ["/already:/already",
                                             "/src:/data"])

    def test_09_save_volumes(self):
        """Test09 the volume bindings are recorded for later reuse"""
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base)
        UdockerCLI._save_run_volumes(base, ["/a:/b"])
        with open(os.path.join(base, "volumes.json")) as filep:
            self.assertEqual(json.load(filep), ["/a:/b"])


class SupervisorLifecycleTestCase(TestCase):
    """Process group lifecycle for engines without runc"""

    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base)
        self.container_dir = os.path.join(self.base, "CID")
        os.makedirs(self.container_dir)
        self.proc = None

    def _state(self, data):
        with open(os.path.join(self.container_dir,
                               supervisor.STATE_NAME), "w") as filep:
            json.dump(data, filep)

    def _spawn_sleeper(self):
        self.proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            start_new_session=True)
        self.addCleanup(self._reap)
        self._state({"status": "running", "pid": self.proc.pid})

    def _reap(self):
        if self.proc is not None:
            try:
                self.proc.kill()
            except OSError:
                pass
            try:
                self.proc.wait()
            except OSError:
                pass

    def test_11_stop_monitor(self):
        """Test11 stop_monitor kills the process group and records state"""
        self._spawn_sleeper()
        self.assertTrue(supervisor.is_running(self.container_dir))
        self.assertEqual(supervisor.stop_monitor(self.container_dir, 5), 0)
        state = supervisor.read_state(self.container_dir)
        self.assertEqual(state["status"], "exited")
        self.assertEqual(state["exitcode"], 143)
        self.assertIsNotNone(self.proc.poll())

    def test_12_signal_monitor(self):
        """Test12 a numeric signal is accepted for non runc containers"""
        self._spawn_sleeper()
        self.assertEqual(supervisor.signal_monitor(self.container_dir, "9"),
                         0)
        self.proc.wait()
        supervisor.reconcile(self.container_dir)
        state = supervisor.read_state(self.container_dir)
        self.assertEqual(state["status"], "exited")
        self.assertEqual(state["exitcode"], 137)

    def test_13_reconcile(self):
        """Test13 a dead monitor is reported as exited"""
        self._state({"status": "running", "pid": 2147483647})
        supervisor.reconcile(self.container_dir)
        self.assertEqual(supervisor.read_state(self.container_dir)
                         ["exitcode"], 137)
        self._state({"status": "running", "pid": os.getpid()})
        supervisor.reconcile(self.container_dir)
        self.assertEqual(supervisor.read_state(self.container_dir)
                         ["status"], "running")

    def test_14_ports_survive_state_updates(self):
        """Test14 published ports are kept when the container exits"""
        supervisor.write_state(self.container_dir, "running",
                               ports=["43210:8080"])
        supervisor.write_state(self.container_dir, "exited", exitcode=0)
        state = supervisor.read_state(self.container_dir)
        self.assertEqual(state["ports"], ["43210:8080"])
        self.assertEqual(state["exitcode"], 0)
        self.assertNotIn("pid", state)


if __name__ == '__main__':
    main()
