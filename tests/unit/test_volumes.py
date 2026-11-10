#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
udocker unit tests: named volumes
"""

import contextlib
import io
import json
import os
import shutil
import tempfile
from unittest import TestCase, main

from udocker.cli import UdockerCLI
from udocker.cmdparser import CmdParser
from udocker.config import Config
from udocker.container.localrepo import LocalRepository
from udocker.engine.base import ExecutionEngineCommon


class VolumesTestCase(TestCase):
    """Named volumes: storage, CLI commands and engine resolution"""

    def setUp(self):
        Config().getconf()
        self.base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base)
        self.repo = LocalRepository(self.base)
        self.assertTrue(self.repo.create_repo())
        self.cli = UdockerCLI(self.repo)

    def _run(self, *args):
        """Run one command through the CLI, return status and output"""
        cmdp = CmdParser()
        cmdp.parse(["udocker"] + list(args))
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = getattr(self.cli, "do_" + args[0])(cmdp)
        return status, out.getvalue(), err.getvalue()

    def _container(self, container_id, volumes):
        """Fake container directory with recorded volumes"""
        container_dir = os.path.join(self.base, "containers", container_id)
        os.makedirs(os.path.join(container_dir, "ROOT"))
        with open(os.path.join(container_dir, "volumes.json"), "w") as filep:
            json.dump(volumes, filep)
        return container_dir

    def test_01_names(self):
        """Test01 docker-like volume name validation"""
        for name in ("a", "pgdata", "a.b_c-d", "A1", "my_project_data"):
            self.assertTrue(self.repo.volume_name_valid(name), name)
        for name in ("", "-x", ".vol", "a/b", "a b", "../x", None, 3):
            self.assertFalse(self.repo.volume_name_valid(name), name)

    def test_02_create_list_inspect(self):
        """Test02 volume storage, idempotent create and metadata"""
        self.assertTrue(self.repo.create_volume("pgdata"))
        self.assertTrue(self.repo.create_volume("pgdata"))
        self.assertTrue(self.repo.is_volume("pgdata"))
        self.assertIn("pgdata", self.repo.get_volumes_list())
        data = self.repo.get_volume("pgdata")
        self.assertEqual(data["Name"], "pgdata")
        self.assertEqual(data["Driver"], "local")
        self.assertEqual(data["Scope"], "local")
        self.assertEqual(data["Mountpoint"],
                         self.repo.get_volume_path("pgdata"))
        self.assertEqual(data["Labels"], {})
        self.assertTrue(os.path.isdir(self.repo.get_volume_path("pgdata")))
        self.assertIsNone(self.repo.get_volume("missing"))
        self.assertIsNone(self.repo.get_volume("../escape"))
        self.assertFalse(self.repo.create_volume("../escape"))

    def test_03_usage_and_remove(self):
        """Test03 in-use detection and rm -f"""
        self.assertTrue(self.repo.create_volume("data"))
        self._container("cid", ["data:/data"])
        self.assertEqual(self.repo.get_volume_containers("data"), ["cid"])
        self.assertEqual(self._run("volume", "rm", "data")[0], 1)
        self.assertTrue(self.repo.is_volume("data"))
        self.assertEqual(self._run("volume", "rm", "-f", "data")[0], 0)
        self.assertFalse(self.repo.is_volume("data"))
        self.assertEqual(self._run("volume", "rm", "data")[0], 1)

    def test_04_cli_create_ls_inspect(self):
        """Test04 volume create, ls (table and JSON), inspect"""
        status, out, dummy = self._run("volume", "create", "v1")
        self.assertEqual(status, 0)
        self.assertEqual(out.strip(), "v1")
        self.assertEqual(self._run("volume", "create", "--label=a=b",
                                   "v2")[0], 0)
        self.assertEqual(self.repo.get_volume("v2")["Labels"], {"a": "b"})
        status, out, dummy = self._run("volume", "create")
        self.assertEqual(status, 0)
        self.assertTrue(self.repo.is_volume(out.strip()))
        status, out, dummy = self._run("volume", "ls")
        self.assertEqual(status, 0)
        self.assertIn("VOLUME NAME", out)
        self.assertIn("v1", out)
        status, out, dummy = self._run("volume", "ls", "--format=json")
        self.assertIn("v1", [item["Name"] for item in json.loads(out)])
        status, out, dummy = self._run("volume", "inspect", "v1")
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out)[0]["Name"], "v1")
        self.assertEqual(self._run("volume", "inspect", "nope")[0], 1)
        names = list(self.repo.get_volumes_list())
        self.assertEqual(self._run("volume", "rm", *names)[0], 0)
        self.assertEqual(self.repo.get_volumes_list(), [])

    def test_05_cli_prune(self):
        """Test05 prune removes only unreferenced volumes"""
        self.assertTrue(self.repo.create_volume("used"))
        self.assertTrue(self.repo.create_volume("unused"))
        self._container("cid", ["used:/data"])
        status, out, dummy = self._run("volume", "prune", "-f")
        self.assertEqual(status, 0)
        self.assertIn("unused", out)
        self.assertTrue(self.repo.is_volume("used"))
        self.assertFalse(self.repo.is_volume("unused"))

    def test_06_engine_resolves_named_volume(self):
        """Test06 engine turns name:/path into the repository bind mount"""
        engine = ExecutionEngineCommon.__new__(ExecutionEngineCommon)
        engine.localrepo = self.repo
        engine.opt = {"vol": ["data:/data"]}
        self.assertTrue(engine._resolve_named_volumes())
        self.assertEqual(engine.opt["vol"],
                         [self.repo.get_volume_path("data") + ":/data"])
        self.assertTrue(self.repo.is_volume("data"))
        engine.opt = {"vol": ["/tmp:/tmp", "bad name:/x"]}
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertFalse(engine._resolve_named_volumes())


if __name__ == '__main__':
    main()
