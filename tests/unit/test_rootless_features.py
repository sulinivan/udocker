#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
udocker unit tests: commit, cp, history, ps state and JSON output
"""

import json
import os
import shutil
import socket
import tempfile
import threading
from unittest import TestCase, main
from unittest.mock import Mock, patch

from udocker.config import Config
from udocker.cmdparser import CmdParser
from udocker.cli import UdockerCLI
from udocker.utils.portforward import PortForwarder


class RootlessFeaturesTestCase(TestCase):
    """Tests for features that work without any privileges."""

    def setUp(self):
        Config().getconf()
        Config().conf['location'] = ""
        Config().conf['keystore'] = "KEYSTORE"

    @staticmethod
    def _cli(localrepo):
        """Create a CLI object with the network/file helpers mocked"""
        localrepo.homedir = "/home/user"
        with patch('udocker.cli.DockerIoAPI'), \
                patch('udocker.cli.LocalFileAPI'), \
                patch('udocker.cli.KeyStore'):
            return UdockerCLI(localrepo)

    @staticmethod
    def _container_dir(base, container_id="CID", state=None):
        container_dir = os.path.join(base, "containers", container_id)
        os.makedirs(os.path.join(container_dir, "ROOT"))
        if state is not None:
            with open(os.path.join(container_dir, "state.json"), "w") as filep:
                json.dump(state, filep)
        return container_dir

    def test_01_commit(self):
        """Test01 commit resolves the container and creates the image"""
        localrepo = Mock()
        localrepo.get_container_id.return_value = "CID"
        localrepo.cd_imagerepo.return_value = ""
        cli = self._cli(localrepo)
        builder = Mock()
        builder.commit.return_value = True
        cmdp = CmdParser()
        cmdp.parse(["udocker", "commit", "-m", "my message",
                    "CID", "myrepo/myimage:latest"])
        with patch('udocker.cli.ContainerBuilder',
                   return_value=builder) as mock_builder:
            status = cli.do_commit(cmdp)
        self.assertEqual(status, 0)
        mock_builder.assert_called_with(localrepo, "CID")
        builder.commit.assert_called_with("myrepo/myimage", "latest",
                                          message="my message", author=None)

    def test_02_commit_errors(self):
        """Test02 commit rejects missing container and missing args"""
        localrepo = Mock()
        localrepo.get_container_id.return_value = ""
        cli = self._cli(localrepo)
        builder = Mock()
        with patch('udocker.cli.ContainerBuilder', return_value=builder):
            cmdp = CmdParser()
            cmdp.parse(["udocker", "commit", "NOPE", "repo/img:tag"])
            self.assertEqual(cli.do_commit(cmdp), 1)
            cmdp = CmdParser()
            cmdp.parse(["udocker", "commit", "CID"])
            self.assertEqual(cli.do_commit(cmdp), 1)
        self.assertFalse(builder.commit.called)

    def test_03_cp_into_container(self):
        """Test03 cp copies a host file into the container"""
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base)
        container_dir = self._container_dir(base)
        src = os.path.join(base, "hostfile.txt")
        with open(src, "w") as filep:
            filep.write("payload")
        localrepo = Mock()
        localrepo.get_container_id.side_effect = \
            lambda ref: "CID" if ref == "CID" else None
        localrepo.cd_container.return_value = container_dir
        cli = self._cli(localrepo)
        cmdp = CmdParser()
        cmdp.parse(["udocker", "cp", src, "CID:/data/hostfile.txt"])
        self.assertEqual(cli.do_cp(cmdp), 0)
        with open(os.path.join(container_dir, "ROOT", "data",
                               "hostfile.txt")) as filep:
            self.assertEqual(filep.read(), "payload")

    def test_04_cp_out_of_container(self):
        """Test04 cp copies a container file to a host directory"""
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base)
        container_dir = self._container_dir(base)
        inside = os.path.join(container_dir, "ROOT", "etc", "release")
        os.makedirs(os.path.dirname(inside))
        with open(inside, "w") as filep:
            filep.write("release")
        outdir = os.path.join(base, "out")
        os.makedirs(outdir)
        localrepo = Mock()
        localrepo.get_container_id.side_effect = \
            lambda ref: "CID" if ref == "CID" else None
        localrepo.cd_container.return_value = container_dir
        cli = self._cli(localrepo)
        cmdp = CmdParser()
        cmdp.parse(["udocker", "cp", "CID:/etc/release", outdir])
        self.assertEqual(cli.do_cp(cmdp), 0)
        with open(os.path.join(outdir, "release")) as filep:
            self.assertEqual(filep.read(), "release")

    def test_05_cp_rejects_escape(self):
        """Test05 cp refuses destinations and sources escaping the root"""
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base)
        container_dir = self._container_dir(base)
        src = os.path.join(base, "hostfile.txt")
        with open(src, "w") as filep:
            filep.write("payload")
        os.symlink("/etc", os.path.join(container_dir, "ROOT", "etclink"))
        localrepo = Mock()
        localrepo.get_container_id.side_effect = \
            lambda ref: "CID" if ref == "CID" else None
        localrepo.cd_container.return_value = container_dir
        cli = self._cli(localrepo)
        cmdp = CmdParser()
        cmdp.parse(["udocker", "cp", src, "CID:/../escape.txt"])
        self.assertEqual(cli.do_cp(cmdp), 1)
        self.assertFalse(os.path.exists(os.path.join(base, "escape.txt")))
        cmdp = CmdParser()
        cmdp.parse(["udocker", "cp", "CID:/etclink/passwd", base])
        self.assertEqual(cli.do_cp(cmdp), 1)

    def test_06_container_status(self):
        """Test06 ps state: created, running, exited, interrupted"""
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base)
        container_dir = self._container_dir(base)
        self.assertEqual(UdockerCLI._container_status(container_dir),
                         "Created")
        UdockerCLI._write_state(container_dir, "running")
        self.assertEqual(UdockerCLI._container_status(container_dir),
                         "Running")
        UdockerCLI._write_state(container_dir, "exited", exitcode=3)
        self.assertEqual(UdockerCLI._container_status(container_dir),
                         "Exited (3)")
        with open(os.path.join(container_dir, "state.json"), "w") as filep:
            json.dump({"status": "running", "pid": 2147483647}, filep)
        self.assertEqual(UdockerCLI._container_status(container_dir),
                         "Interrupted")
        UdockerCLI._write_state(container_dir, "interrupted")
        self.assertEqual(UdockerCLI._container_status(container_dir),
                         "Interrupted")

    def test_07_run_writes_state(self):
        """Test07 run records running and exited states"""
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base)
        container_dir = self._container_dir(base)
        localrepo = Mock()
        localrepo.get_container_id.return_value = "CID"
        localrepo.cd_container.return_value = container_dir
        cli = self._cli(localrepo)
        engine = Mock()
        engine.run.return_value = 7
        cmdp = CmdParser()
        cmdp.parse(["udocker", "run", "CID"])
        with patch.object(UdockerCLI, '_get_run_options'), \
                patch('udocker.cli.ExecutionMode') as mock_exec, \
                patch('udocker.cli.Msg'):
            mock_exec.return_value.get_engine.return_value = engine
            status = cli.do_run(cmdp)
        self.assertEqual(status, 7)
        self.assertEqual(UdockerCLI._container_status(container_dir),
                         "Exited (7)")

    def test_08_run_interrupted_state(self):
        """Test08 run marks the container interrupted on an exception"""
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base)
        container_dir = self._container_dir(base)
        localrepo = Mock()
        localrepo.get_container_id.return_value = "CID"
        localrepo.cd_container.return_value = container_dir
        cli = self._cli(localrepo)
        engine = Mock()
        engine.run.side_effect = KeyboardInterrupt()
        cmdp = CmdParser()
        cmdp.parse(["udocker", "run", "CID"])
        with patch.object(UdockerCLI, '_get_run_options'), \
                patch('udocker.cli.ExecutionMode') as mock_exec, \
                patch('udocker.cli.Msg'):
            mock_exec.return_value.get_engine.return_value = engine
            with self.assertRaises(KeyboardInterrupt):
                cli.do_run(cmdp)
        self.assertEqual(UdockerCLI._container_status(container_dir),
                         "Interrupted")

    def test_09_ps_json(self):
        """Test09 ps -a --format=json emits every container as JSON"""
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base)
        container_dir = self._container_dir(
            base, state={"status": "exited", "exitcode": 0})
        localrepo = Mock()
        localrepo.get_containers_list.return_value = [
            ("CID", "myimage:latest", ["mycontainer"])]
        localrepo.cd_container.return_value = container_dir
        localrepo.isprotected_container.return_value = False
        localrepo.iswriteable_container.return_value = 1
        localrepo.get_size.return_value = 1024
        cli = self._cli(localrepo)
        cmdp = CmdParser()
        cmdp.parse(["udocker", "ps", "-a", "--format=json"])
        with patch('udocker.cli.Msg') as mock_msg, \
                patch('udocker.cli.ExecutionMode') as mock_exec, \
                patch('udocker.cli.ContainerStructure') as mock_structure:
            mock_exec.return_value.get_mode.return_value = "P1"
            mock_structure.return_value.get_container_platform_fmt.\
                return_value = "linux/amd64"
            self.assertEqual(cli.do_ps(cmdp), 0)
        output = mock_msg.return_value.out.call_args[0][0]
        data = json.loads(output)
        self.assertEqual(data["ID"], "CID")
        self.assertEqual(data["State"], "exited")
        self.assertTrue(data["Status"].startswith("Exited (0)"))
        self.assertEqual(data["Image"], "myimage:latest")
        self.assertEqual(data["Names"], "mycontainer")

    def test_10_images_json(self):
        """Test10 images --format=json emits the image list as JSON"""
        localrepo = Mock()
        localrepo.get_imagerepos.return_value = [("img1", "tag1")]
        localrepo.cd_imagerepo.return_value = "/repos/img1/tag1"
        localrepo.isprotected_imagerepo.return_value = True
        localrepo.get_layers.return_value = [("/x/l1", 1048576)]
        localrepo.get_image_platform_fmt.return_value = "linux/amd64"
        cli = self._cli(localrepo)
        cmdp = CmdParser()
        cmdp.parse(["udocker", "images", "--format=json"])
        with patch('udocker.cli.Msg') as mock_msg:
            self.assertEqual(cli.do_images(cmdp), 0)
        data = json.loads(mock_msg.return_value.out.call_args[0][0])
        self.assertEqual(data["Repository"], "img1")
        self.assertEqual(data["Tag"], "tag1")
        self.assertEqual(data["ID"], "l1")
        self.assertEqual(data["Size"], "1.00MB")

    def test_11_history(self):
        """Test11 history prints layers newest first with the top comment"""
        localrepo = Mock()
        localrepo.cd_imagerepo.return_value = "/repos/img1/tag1"
        localrepo.load_json.return_value = ["aaa", "bbb"]
        localrepo.get_image_attributes.return_value = (
            {"created": "2024-01-01T00:00:00Z", "comment": "top"}, [])
        localrepo.get_layers.return_value = [
            ("/repos/img1/tag1/aaa.layer", 1048576),
            ("/repos/img1/tag1/bbb.layer", 2097152)]
        cli = self._cli(localrepo)
        cmdp = CmdParser()
        cmdp.parse(["udocker", "history", "img1:tag1"])
        with patch('udocker.cli.Msg') as mock_msg:
            self.assertEqual(cli.do_history(cmdp), 0)
        lines = [str(call[0][0]) for call in mock_msg.return_value.out.call_args_list]
        text = "\n".join(lines)
        self.assertIn("LAYER ID", text)
        self.assertLess(text.find("bbb"), text.find("aaa"))
        self.assertIn("top", text)


    def test_12_port_forwarder(self):
        """Test12 publish forwards TCP traffic to the container port"""
        echo = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        echo.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        echo.bind(("127.0.0.1", 0))
        echo.listen(5)
        echo_port = echo.getsockname()[1]
        self.addCleanup(echo.close)

        def serve():
            while True:
                try:
                    (conn, dummy) = echo.accept()
                except OSError:
                    return
                while True:
                    try:
                        data = conn.recv(4096)
                    except OSError:
                        break
                    if not data:
                        break
                    conn.sendall(data)
                conn.close()

        thread = threading.Thread(target=serve)
        thread.daemon = True
        thread.start()

        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        host_port = probe.getsockname()[1]
        probe.close()

        forwarder = PortForwarder()
        self.assertTrue(forwarder.add(host_port, echo_port))
        forwarder.start()
        self.addCleanup(forwarder.stop)
        client = socket.create_connection(("127.0.0.1", host_port), timeout=5)
        client.sendall(b"hello")
        self.assertEqual(client.recv(5), b"hello")
        client.close()

    def test_13_run_publishes_in_non_p_mode(self):
        """Test13 run starts a forwarder for -p outside Pn modes"""
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base)
        container_dir = self._container_dir(base)
        localrepo = Mock()
        localrepo.get_container_id.return_value = "CID"
        localrepo.cd_container.return_value = container_dir
        cli = self._cli(localrepo)
        engine = Mock()
        engine.opt = {"portsmap": ["8123:80"]}
        engine.run.return_value = 0
        exec_mode = Mock()
        exec_mode.get_engine.return_value = engine
        exec_mode.get_mode.return_value = "F3"
        cmdp = CmdParser()
        cmdp.parse(["udocker", "run", "CID"])
        with patch.object(UdockerCLI, '_get_run_options'), \
                patch('udocker.cli.ExecutionMode', return_value=exec_mode), \
                patch('udocker.cli.PortForwarder') as mock_forwarder, \
                patch('udocker.cli.Msg'):
            status = cli.do_run(cmdp)
        self.assertEqual(status, 0)
        forwarder = mock_forwarder.return_value
        forwarder.add.assert_called_with("8123", "80")
        self.assertTrue(forwarder.start.called)
        self.assertTrue(forwarder.stop.called)

    def test_14_run_does_not_publish_in_p_mode(self):
        """Test14 PRoot handles publishing in Pn modes, no forwarder"""
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base)
        container_dir = self._container_dir(base)
        localrepo = Mock()
        localrepo.get_container_id.return_value = "CID"
        localrepo.cd_container.return_value = container_dir
        cli = self._cli(localrepo)
        engine = Mock()
        engine.opt = {"portsmap": ["8123:80"]}
        engine.run.return_value = 0
        exec_mode = Mock()
        exec_mode.get_engine.return_value = engine
        exec_mode.get_mode.return_value = "P1"
        cmdp = CmdParser()
        cmdp.parse(["udocker", "run", "CID"])
        with patch.object(UdockerCLI, '_get_run_options'), \
                patch('udocker.cli.ExecutionMode', return_value=exec_mode), \
                patch('udocker.cli.PortForwarder') as mock_forwarder, \
                patch('udocker.cli.Msg'):
            status = cli.do_run(cmdp)
        self.assertEqual(status, 0)
        self.assertFalse(mock_forwarder.called)

    def test_15_digest_imagespec(self):
        """Test15 image digests are accepted as pull references"""
        from udocker.docker import DockerIoAPI
        with patch('udocker.docker.GetURL'):
            api = DockerIoAPI(Mock())
        digest = "sha256:" + "a" * 64
        self.assertTrue(api.is_layer_name("alpine@" + digest))
        self.assertTrue(api.is_layer_name("library/alpine@" + digest))
        self.assertFalse(api.is_layer_name("alpine@sha256:xyz"))


if __name__ == '__main__':
    main()
