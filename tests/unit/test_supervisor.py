#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
udocker unit tests: per-user supervisor built on runc/crun
"""

import json
import os
import shutil
import tempfile
from unittest import TestCase, main
from unittest.mock import Mock, patch

from udocker import supervisor


class SupervisorTestCase(TestCase):
    """Test the rootless container supervisor helpers"""

    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base)
        self.container_id = "CID"
        self.container_dir = os.path.join(self.base, "containers",
                                          self.container_id)
        os.makedirs(os.path.join(self.container_dir, "ROOT"))

    def _state(self, data):
        with open(os.path.join(self.container_dir,
                               supervisor.STATE_NAME), "w") as filep:
            json.dump(data, filep)

    def test_01_state_and_conf(self):
        """Test01 state and supervisor config round trip"""
        self._state({"status": "exited", "exitcode": 3})
        self.assertEqual(supervisor.read_state(self.container_dir)
                         ["status"], "exited")
        self.assertTrue(supervisor.write_conf(
            self.container_dir, ["run", "CID"], "/tmp/log"))
        conf = supervisor.read_conf(self.container_dir)
        self.assertEqual(conf["argv"], ["run", "CID"])
        self.assertEqual(conf["runc_id"], "udocker-CID")

    def test_02_is_running(self):
        """Test02 only a live monitor counts as running"""
        self._state({"status": "running", "pid": os.getpid()})
        self.assertTrue(supervisor.is_running(self.container_dir))
        self._state({"status": "running", "pid": 2147483647})
        self.assertFalse(supervisor.is_running(self.container_dir))
        self._state({"status": "exited", "exitcode": 0})
        self.assertFalse(supervisor.is_running(self.container_dir))

    def test_03_resolve_user(self):
        """Test03 resolve container user and group to uid:gid"""
        etcdir = os.path.join(self.container_dir, "ROOT", "etc")
        os.makedirs(etcdir)
        with open(os.path.join(etcdir, "passwd"), "w") as filep:
            filep.write("root:x:0:0:root:/root:/bin/sh\n")
            filep.write("app:x:1000:1001:App:/home/app:/bin/sh\n")
        with open(os.path.join(etcdir, "group"), "w") as filep:
            filep.write("app:x:1001:\n")
        self.assertEqual(supervisor.resolve_user(self.container_dir, "app"),
                         "1000:1001")
        self.assertEqual(supervisor.resolve_user(self.container_dir,
                                                 "app:app"), "1000:1001")
        self.assertEqual(supervisor.resolve_user(self.container_dir, "1000"),
                         "1000")
        self.assertIsNone(supervisor.resolve_user(self.container_dir,
                                                  "missing"))

    def test_04_exec_command(self):
        """Test04 runc exec gets user, workdir, env and the command"""
        with patch('udocker.supervisor.subprocess.call',
                   return_value=7) as mock_call:
            status = supervisor.exec_command(
                self.container_dir, "/usr/bin/runc", ["echo", "hi"],
                user="1000:1001", workdir="/app", env_vars=["A=1"],
                topdir=self.base)
        self.assertEqual(status, 7)
        args = mock_call.call_args[0][0]
        self.assertEqual(args[0], "/usr/bin/runc")
        self.assertIn("--root", args)
        self.assertIn(self.container_dir, args)
        self.assertIn("exec", args)
        self.assertIn("--user", args)
        self.assertIn("1000:1001", args)
        self.assertIn("--cwd", args)
        self.assertIn("--env", args)
        self.assertEqual(args[-2:], ["echo", "hi"])

    def test_05_kill(self):
        """Test05 kill uses the runc container id"""
        with patch('udocker.supervisor._runc_call',
                   return_value=0) as mock_runc:
            status = supervisor.kill(self.container_dir, "/usr/bin/runc",
                                     "TERM", self.base)
        self.assertEqual(status, 0)
        args = mock_runc.call_args[0][2]
        self.assertEqual(args, ["kill", "udocker-CID", "TERM"])

    def test_06_stop(self):
        """Test06 stop signals and waits for the monitor to exit"""
        self._state({"status": "running", "pid": os.getpid()})
        with patch('udocker.supervisor.is_running',
                   side_effect=[True, False]), \
                patch('udocker.supervisor.kill', return_value=0) as mock_kill:
            status = supervisor.stop(self.container_dir, "/usr/bin/runc",
                                     1, self.base)
        self.assertEqual(status, 0)
        self.assertTrue(mock_kill.called)

    def test_07_wait(self):
        """Test07 wait returns the recorded exit code"""
        self._state({"status": "exited", "exitcode": 5})
        self.assertEqual(supervisor.wait(self.container_dir), 5)

    def test_08_logs_tail(self):
        """Test08 logs --tail prints the last lines"""
        logdir = os.path.join(self.container_dir, "logs")
        os.makedirs(logdir)
        with open(os.path.join(logdir, "container.log"), "w") as filep:
            filep.write("one\ntwo\nthree\n")
        with patch('udocker.supervisor._write_bytes') as mock_write:
            status = supervisor.logs(self.container_dir, False, 2)
        self.assertEqual(status, 0)
        self.assertEqual(mock_write.call_args[0][0], b"two\nthree\n")

    def test_09_spawn(self):
        """Test09 spawn starts the monitor and stores the config"""
        proc = Mock()
        proc.pid = os.getpid()
        proc.poll.return_value = None
        with patch('udocker.supervisor.subprocess.Popen',
                   return_value=proc) as mock_popen, \
                patch('udocker.supervisor.wait_running',
                      return_value=True), \
                patch('udocker.supervisor._devnull'):
            status = supervisor.spawn(self.container_id, self.container_dir,
                                      ["run", "CID"])
        self.assertTrue(status)
        cmd = mock_popen.call_args[0][0]
        self.assertEqual(cmd[:3], [supervisor.sys.executable, "-m",
                                   "udocker.maincmd"])
        self.assertEqual(cmd[3:], ["run", "CID"])
        conf = supervisor.read_conf(self.container_dir)
        self.assertEqual(conf["argv"], ["run", "CID"])


if __name__ == '__main__':
    main()
