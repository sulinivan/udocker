#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
udocker unit tests: compose module, YAML subset parser and command lines
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
from collections import OrderedDict
from unittest import TestCase, main
from unittest.mock import Mock, patch

from udocker import compose
from udocker.config import Config


COMPOSE_TEXT = """\
# a project with two services
name: myproj
services:
  web:
    image: busybox:latest
    depends_on: [db]
    environment:
      - A=1
      - B=two
    ports: ["8080:80"]
    volumes:
      - ./data:/data
    working_dir: /app
    user: app
    entrypoint: /bin/sh -c
    command: ["sleep", "60"]
  db:
    image: busybox:latest
    command: sleep 30
"""


class FakeProcess(object):
    """A subprocess.Popen stand-in for the compose tests"""

    def __init__(self, output="", status=0):
        self.output = output
        self.returncode = status
        self.stdout = io.StringIO(output)

    def communicate(self):
        """Return the canned output"""
        return (self.stdout.read(), "")

    def wait(self):
        """Pretend the process has already exited"""
        return self.returncode

    def poll(self):
        """Pretend the process has already exited"""
        return self.returncode

    def terminate(self):
        """A canned process ignores signals"""
        pass

    def kill(self):
        """A canned process ignores signals"""
        pass


class FakeUdocker(object):
    """Emulate the udocker child processes and record their arguments"""

    def __init__(self, containers=None, logs=None, failing=()):
        self.calls = []
        self.containers = containers or []
        self.logs = logs or {}
        self.failing = tuple(failing)

    def __call__(self, argv, **kwargs):
        """Answer one child call"""
        self.calls.append(list(argv))
        args = list(argv[4:])
        text = ""
        if args[:3] == ["ps", "-a", "--format=json"]:
            text = json.dumps(self.containers)
        elif args and args[0] == "logs":
            text = self.logs.get(args[-1], "")
        status = 0
        for marker in self.failing:
            if marker in " ".join(args):
                status = 1
        return FakeProcess(text, status)

    def commands(self):
        """The udocker arguments of every recorded call"""
        return [list(call[4:]) for call in self.calls]


class FakeCLI(object):
    """The minimal UdockerCLI surface used by do_compose"""

    STATUS_OK = 0
    STATUS_ERROR = 1

    def __init__(self):
        self.localrepo = Mock()


def write_compose(directory, text=COMPOSE_TEXT, name="compose.yaml"):
    """Write a compose file and return its path"""
    path = os.path.join(directory, name)
    with open(path, "w") as filep:
        filep.write(text)
    return path


class ComposeYamlTestCase(TestCase):
    """Test the YAML subset parser used for compose files"""

    def test_01_mappings(self):
        """Test01 block mappings, comments, quotes, flow collections"""
        text = (
            "# leading comment\n"
            "version: '3'\n"
            "services:\n"
            "  web:\n"
            "    image: \"busybox:latest\"  # trailing comment\n"
            "    environment:\n"
            "      A: 1\n"
            "      B: two words\n"
            "      C:\n"
            "    labels: {com.example.x: 'a b'}\n"
            "    ports: [\"80:80\", 8080:80]\n"
        )
        data = compose.YamlParser().parse(text)
        web = data["services"]["web"]
        self.assertEqual(data["version"], "3")
        self.assertEqual(web["image"], "busybox:latest")
        self.assertEqual(web["environment"]["A"], 1)
        self.assertEqual(web["environment"]["B"], "two words")
        self.assertIsNone(web["environment"]["C"])
        self.assertEqual(web["labels"]["com.example.x"], "a b")
        self.assertEqual(web["ports"], ["80:80", "8080:80"])
        self.assertIsInstance(web, OrderedDict)

    def test_02_sequences(self):
        """Test02 sequences, mappings in sequences and same indent lists"""
        text = (
            "services:\n"
            "  web:\n"
            "    ports:\n"
            "    - \"8000:8000\"\n"
            "    - target: 80\n"
            "      published: 8080\n"
            "    volumes:\n"
            "      - ./data:/data\n"
            "    empty: []\n"
        )
        web = compose.YamlParser().parse(text)["services"]["web"]
        self.assertEqual(web["ports"], [
            "8000:8000", {"target": 80, "published": 8080}])
        self.assertEqual(web["volumes"], ["./data:/data"])
        self.assertEqual(web["empty"], [])

    def test_03_block_scalars(self):
        """Test03 literal and folded block scalars"""
        text = "script: |\n  line one\n  line two\nplain: >\n  a\n  b\n"
        data = compose.YamlParser().parse(text)
        self.assertEqual(data["script"], "line one\nline two\n")
        self.assertEqual(data["plain"], "a b\n")

    def test_04_errors(self):
        """Test04 format errors carry the file and line number"""
        cases = [
            ("a:\n  b: 1\n   c: 2\n", "yaml:3:"),
            ("a: 1\nbad\n", "yaml:2:"),
            ("a: \"x\n", "yaml:1:"),
            ("a:\n\tb: 1\n", "yaml:2:"),
            ("a: [1, 2\n", "yaml:1:"),
            ("a: {x: 1\n", "yaml:1:"),
        ]
        for (text, prefix) in cases:
            with self.assertRaises(compose.YamlError) as context:
                compose.YamlParser().parse(text)
            message = str(context.exception)
            self.assertTrue(message.startswith(prefix), message)
        with self.assertRaises(compose.YamlError) as context:
            compose.YamlParser().parse("a:\n  - x\n b: 1\n", "my.yml")
        self.assertTrue(str(context.exception).startswith("my.yml:3:"))

    def test_05_expand_env(self):
        """Test05 environment variables are expanded like compose does"""
        with patch.dict(os.environ, {"COMPOSE_TEST_TAG": "v1"}):
            self.assertEqual(compose.expand_env("img:${COMPOSE_TEST_TAG}"),
                             "img:v1")
            self.assertEqual(compose.expand_env("a$COMPOSE_TEST_TAG"), "av1")
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            self.assertEqual(compose.expand_env("${COMPOSE_TEST_ABSENT}"),
                             "")
        self.assertIn("COMPOSE_TEST_ABSENT", errors.getvalue())
        self.assertEqual(compose.expand_env("cost:$$5"), "cost:$5")

    def test_06_compose_file(self):
        """Test06 ComposeFile requires a services section"""
        project = compose.ComposeFile()
        raw = project.parse("services:\n  web:\n    image: busybox\n")
        self.assertEqual(raw["services"]["web"]["image"], "busybox")
        with self.assertRaises(compose.ComposeError):
            compose.ComposeFile().parse("version: '3'\n")
        with self.assertRaises(compose.ComposeError):
            compose.ComposeFile().parse("services: []\n")
        with self.assertRaises(compose.ComposeError):
            compose.ComposeFile().load("/nonexistent/compose.yaml")


class ComposeProjectTestCase(TestCase):
    """Test project names, service plans and dependency order"""

    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base)

    def test_07_project_name(self):
        """Test07 project name from -p, the name key or the directory"""
        directory = os.path.join(self.base, "My.Project X")
        os.makedirs(directory)
        path = write_compose(directory, "services:\n  web:\n"
                                       "    image: busybox\n")
        self.assertEqual(compose.ComposeProject(path).name, "my_project_x")
        path = write_compose(directory, "name: Custom_Name\nservices:\n"
                                       "  web:\n    image: busybox\n",
                             "other.yaml")
        self.assertEqual(compose.ComposeProject(path).name, "custom_name")
        self.assertEqual(compose.ComposeProject(path, "Explicit").name,
                         "explicit")
        self.assertEqual(compose.normalize_name("A.b C"), "a_b_c")
        self.assertEqual(compose.normalize_name(""), "")
        self.assertEqual(compose.container_name("Proj", "my.web"),
                         "proj_my_web_1")
        self.assertEqual(compose.default_image("Proj", "my.web"),
                         "proj_my_web:latest")

    def test_08_service_parsing(self):
        """Test08 service keys are normalized for the udocker commands"""
        path = write_compose(self.base)
        project = compose.ComposeProject(path)
        web = project.plan("web")
        db = project.plan("db")
        self.assertEqual(web["image"], "busybox:latest")
        self.assertEqual(web["container_name"], "myproj_web_1")
        self.assertEqual(web["environment"], ["A=1", "B=two"])
        self.assertEqual(web["ports"], ["8080:80"])
        self.assertEqual(web["volumes"],
                         [os.path.join(self.base, "data") + ":/data"])
        self.assertEqual(web["working_dir"], "/app")
        self.assertEqual(web["user"], "app")
        self.assertEqual(web["entrypoint"], ["/bin/sh", "-c"])
        self.assertEqual(web["command"], ["sleep", "60"])
        self.assertEqual(web["depends_on"], ["db"])
        self.assertEqual(db["command"], ["sleep", "30"])
        self.assertIsNone(db["build"])
        self.assertEqual(project.names(),
                         OrderedDict([("web", "myproj_web_1"),
                                      ("db", "myproj_db_1")]))

    def test_09_arguments(self):
        """Test09 create, run and build command lines put options first"""
        text = (
            "name: myproj\n"
            "services:\n"
            "  app:\n"
            "    build: ./app\n"
            "    environment: {A: '1', B: 2}\n"
            "    ports: [\"127.0.0.1:8080:80\", 9000:90/udp, 80]\n"
            "    volumes: [named:/var/lib, ./cache:/cache]\n"
            "    labels: {x: y}\n"
            "    command: echo hi\n"
        )
        path = write_compose(self.base, text)
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            project = compose.ComposeProject(path)
            plan = project.plan("app")
            args = compose.run_arguments(plan)
        context = os.path.join(self.base, "app")
        self.assertEqual(compose.build_arguments(plan),
                         ["build", "-t=myproj_app:latest", "--force",
                          context])
        self.assertEqual(compose.create_arguments(plan),
                         ["create", "--name=myproj_app_1",
                          "myproj_app:latest"])
        self.assertEqual(args[:2], ["run", "-d"])
        self.assertIn("--env=A=1", args)
        self.assertIn("--env=B=2", args)
        self.assertIn("--publish=8080:80", args)
        self.assertNotIn("--publish=9000:90", args)
        self.assertIn("--volume=myproj_named:/var/lib", args)
        self.assertIn("--volume=%s:/cache" % os.path.join(self.base,
                                                          "cache"), args)
        self.assertEqual(args[-3:], ["myproj_app_1", "echo", "hi"])
        self.assertLess(args.index("--env=A=1"), args.index("myproj_app_1"))
        self.assertIn("udp", errors.getvalue())
        self.assertIn("labels", errors.getvalue())

    def test_09_named_volumes(self):
        """Test09 named volumes: project prefix, name: and external:"""
        text = (
            "name: myproj\n"
            "services:\n"
            "  app:\n"
            "    image: busybox:latest\n"
            "    volumes:\n"
            "      - data:/data\n"
            "      - named:/named\n"
            "      - ext:/ext\n"
            "      - ./host:/host\n"
            "volumes:\n"
            "  data:\n"
            "  named:\n"
            "    name: elsewhere\n"
            "  ext:\n"
            "    external: true\n"
        )
        path = write_compose(self.base, text)
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            project = compose.ComposeProject(path)
            plan = project.plan("app")
        self.assertEqual(plan["volumes"], [
            "myproj_data:/data", "elsewhere:/named", "ext:/ext",
            "%s:/host" % os.path.join(self.base, "host")])
        self.assertEqual(list(project.volume_names().items()),
                         [("data", "myproj_data"), ("named", "elsewhere"),
                          ("ext", "ext")])
        self.assertEqual(project.external_volumes(), ["ext"])
        with contextlib.redirect_stderr(errors):
            self.assertEqual(compose.parse_volumes(
                ["nolabel:/x"], self.base, "p", {}), ["p_nolabel:/x"])
        self.assertIn("not declared", errors.getvalue())

    def test_10_depends_on_order(self):
        """Test10 depends_on orders the services and catches cycles"""
        services = OrderedDict([
            ("web", {"image": "x", "depends_on": ["db"]}),
            ("db", {"image": "x"}),
            ("cache", {"image": "x"}),
        ])
        self.assertEqual(compose.topo_sort(services), ["db", "web", "cache"])
        self.assertEqual(compose.topo_sort(services, ["web"]), ["db", "web"])
        self.assertEqual(compose.topo_sort(services, ["cache"]), ["cache"])
        services["db"] = {"image": "x", "depends_on": ["web"]}
        with self.assertRaises(compose.ComposeError):
            compose.topo_sort(services)
        with self.assertRaises(compose.ComposeError):
            compose.topo_sort(services, ["missing"])
        with self.assertRaises(compose.ComposeError):
            compose.topo_sort(OrderedDict([("a", {"depends_on": ["b"]})]))
        long_syntax = {"db": {"condition": "started"}}
        self.assertEqual(compose.parse_depends_on(long_syntax), ["db"])


class ComposeCommandTestCase(TestCase):
    """Test the compose subcommands with a canned child process"""

    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base)
        self.path = write_compose(self.base)

    def run_compose(self, tail, fake=None):
        """Run do_compose with a canned child and captured output"""
        fake = fake or FakeUdocker()
        cmdp = Mock()
        out = io.StringIO()
        errors = io.StringIO()
        argv = ["udocker", "compose"] + list(tail)
        with patch.object(compose.subprocess, "Popen", fake), \
                patch.object(compose.sys, "argv", argv), \
                contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(errors):
            status = compose.do_compose(FakeCLI(), cmdp)
        return (status, out.getvalue(), errors.getvalue(), fake, cmdp)

    def test_11_up_detached(self):
        """Test11 up -d creates the dependencies first and starts detached"""
        (status, out, errors, fake, cmdp) = self.run_compose(
            ["up", "-d", "-p", "Other", "--file=" + self.path])
        self.assertEqual(status, 0)
        self.assertEqual(errors, "")
        self.assertTrue(cmdp.consume_all.called)
        self.assertEqual(fake.calls[0][:4],
                         [sys.executable, "-m", "udocker.maincmd",
                          "--repo=" + Config.conf["topdir"]])
        commands = fake.commands()
        self.assertEqual(commands[0], ["ps", "-a", "--format=json"])
        self.assertEqual(commands[1], ["create", "--name=other_db_1",
                                       "busybox:latest"])
        self.assertEqual(commands[2], ["run", "-d", "other_db_1",
                                       "sleep", "30"])
        self.assertEqual(commands[3], ["create", "--name=other_web_1",
                                       "busybox:latest"])
        run_web = commands[4]
        self.assertEqual(run_web[:2], ["run", "-d"])
        self.assertIn("--env=A=1", run_web)
        self.assertIn("--env=B=two", run_web)
        self.assertIn("--publish=8080:80", run_web)
        self.assertIn("--volume=%s:/data" % os.path.join(self.base, "data"),
                      run_web)
        self.assertIn("--workdir=/app", run_web)
        self.assertIn("--user=app", run_web)
        self.assertIn("--entrypoint=/bin/sh -c", run_web)
        self.assertEqual(run_web[-3:], ["other_web_1", "sleep", "60"])
        self.assertIn("project other is up", out)

    def test_12_up_existing_container(self):
        """Test12 up starts an existing container without recreating it"""
        containers = [{"name": "myproj_db_1", "status": "exited",
                       "image": "busybox:latest"}]
        fake = FakeUdocker(containers=containers)
        (status, dummy, dummy2, fake, dummy3) = self.run_compose(
            ["up", "-d", "--file", self.path], fake)
        self.assertEqual(status, 0)
        commands = fake.commands()
        self.assertNotIn(["create", "--name=myproj_db_1",
                          "busybox:latest"], commands)
        self.assertIn(["run", "-d", "myproj_db_1", "sleep", "30"], commands)
        containers[0]["status"] = "running"
        fake = FakeUdocker(containers=containers)
        (status, dummy, dummy2, fake, dummy3) = self.run_compose(
            ["up", "-d", "--file", self.path], fake)
        self.assertEqual(status, 0)
        self.assertNotIn(["run", "-d", "myproj_db_1", "sleep", "30"],
                         fake.commands())

    def test_13_up_build_and_force_recreate(self):
        """Test13 up --build builds first and --force-recreate removes"""
        text = ("name: myproj\n"
                "services:\n"
                "  app:\n"
                "    build:\n"
                "      context: ./app\n")
        path = write_compose(self.base, text, "build.yaml")
        fake = FakeUdocker(containers=[{"name": "myproj_app_1",
                                        "status": "exited",
                                        "image": "myproj_app:latest"}])
        (status, dummy, errors, fake, dummy2) = self.run_compose(
            ["up", "-d", "--build", "--force-recreate",
             "--file=" + path], fake)
        self.assertEqual(status, 0)
        self.assertEqual(errors, "")
        commands = fake.commands()
        self.assertEqual(commands[0],
                         ["build", "-t=myproj_app:latest", "--force",
                          os.path.join(self.base, "app")])
        self.assertEqual(commands[1], ["ps", "-a", "--format=json"])
        self.assertEqual(commands[2], ["rm", "-f", "myproj_app_1"])
        self.assertEqual(commands[3], ["create", "--name=myproj_app_1",
                                       "myproj_app:latest"])
        self.assertEqual(commands[4], ["run", "-d", "myproj_app_1"])

    def test_14_up_attached_interrupt(self):
        """Test14 up without -d follows logs and stops on KeyboardInterrupt"""
        with patch.object(compose, "stream_logs",
                          side_effect=KeyboardInterrupt) as mock_logs:
            (status, dummy, dummy2, fake, dummy3) = self.run_compose(
                ["up", "--file=" + self.path])
        self.assertEqual(status, 0)
        self.assertTrue(mock_logs.called)
        commands = fake.commands()
        self.assertIn(["stop", "myproj_db_1"], commands)
        self.assertIn(["stop", "myproj_web_1"], commands)

    def test_15_down(self):
        """Test15 down stops and removes the project containers"""
        containers = [
            {"name": "myproj_web_1", "status": "running",
             "image": "busybox:latest"},
            {"name": "myproj_db_1", "status": "exited",
             "image": "busybox:latest"},
            {"name": "other_web_1", "status": "running", "image": "x:1"},
        ]
        fake = FakeUdocker(containers=containers)
        (status, dummy, dummy2, fake, dummy3) = self.run_compose(
            ["down", "--file=" + self.path], fake)
        self.assertEqual(status, 0)
        commands = fake.commands()
        self.assertEqual(commands[0], ["ps", "-a", "--format=json"])
        self.assertIn(["stop", "myproj_web_1"], commands)
        self.assertIn(["rm", "-f", "myproj_web_1"], commands)
        self.assertIn(["stop", "myproj_db_1"], commands)
        self.assertIn(["rm", "-f", "myproj_db_1"], commands)
        self.assertNotIn(["rm", "-f", "other_web_1"], commands)

    def test_16_down_orphans_rmi(self):
        """Test16 down removes orphans and images when asked to"""
        containers = [
            {"name": "myproj_web_1", "status": "exited", "image": "a:1"},
            {"name": "myproj_db_1", "status": "exited", "image": "b:1"},
            {"name": "myproj_old_1", "status": "exited", "image": "c:1"},
        ]
        fake = FakeUdocker(containers=containers, failing=("rmi",))
        (status, dummy, errors, fake, dummy2) = self.run_compose(
            ["down", "--remove-orphans", "--rmi",
             "--file=" + self.path], fake)
        self.assertEqual(status, 0)
        commands = fake.commands()
        self.assertIn(["rm", "-f", "myproj_old_1"], commands)
        images = [command[1] for command in commands if command[0] == "rmi"]
        self.assertEqual(images, ["busybox:latest", "busybox:latest"])
        self.assertIn("cannot remove image", errors)

    def test_17_ps(self):
        """Test17 ps prints the project containers as a table"""
        containers = [
            {"name": "myproj_web_1", "status": "running",
             "image": "busybox:latest"},
            {"name": "myproj_db_1", "status": "exited",
             "image": "busybox:latest"},
            {"name": "other_web_1", "status": "running", "image": "x:1"},
        ]
        fake = FakeUdocker(containers=containers)
        (status, out, dummy, fake, dummy2) = self.run_compose(
            ["ps", "--file=" + self.path], fake)
        self.assertEqual(status, 0)
        lines = out.splitlines()
        self.assertEqual(lines[0].split(), ["NAME", "SERVICE", "STATUS",
                                            "IMAGE"])
        self.assertIn("myproj_web_1", out)
        self.assertIn("running", out)
        self.assertIn("busybox:latest", out)
        self.assertNotIn("other_web_1", out)
        (status, out, dummy, dummy2, dummy3) = self.run_compose(
            ["ps", "db", "--file=" + self.path], fake)
        self.assertEqual(status, 0)
        self.assertNotIn("myproj_web_1", out)
        self.assertIn("myproj_db_1", out)

    def test_18_logs(self):
        """Test18 logs prints the log of every service in project order"""
        fake = FakeUdocker(logs={"myproj_web_1": "web line\n",
                                 "myproj_db_1": "db line\n"})
        (status, out, dummy, fake, dummy2) = self.run_compose(
            ["logs", "--file=" + self.path], fake)
        self.assertEqual(status, 0)
        commands = fake.commands()
        self.assertEqual(len(commands), 2)
        self.assertEqual(commands[0], ["logs", "myproj_web_1"])
        self.assertEqual(commands[1], ["logs", "myproj_db_1"])
        self.assertIn("web line", out)
        self.assertIn("db line", out)
        fake = FakeUdocker(logs={"myproj_db_1": "db line\n"})
        (status, out, dummy, fake, dummy2) = self.run_compose(
            ["logs", "--tail=3", "db", "--file=" + self.path], fake)
        self.assertEqual(status, 0)
        self.assertEqual(fake.commands()[0],
                         ["logs", "--tail=3", "myproj_db_1"])
        self.assertIn("db line", out)

    def test_19_logs_follow(self):
        """Test19 logs -f follows every selected service concurrently"""
        fake = FakeUdocker(logs={"myproj_web_1": "follow web\n",
                                 "myproj_db_1": "follow db\n"})
        (status, out, dummy, fake, dummy2) = self.run_compose(
            ["logs", "-f", "--file=" + self.path], fake)
        self.assertEqual(status, 0)
        commands = fake.commands()
        self.assertEqual(len(commands), 2)
        for command in commands:
            self.assertEqual(command[:2], ["logs", "-f"])
        self.assertIn("follow web", out)
        self.assertIn("follow db", out)

    def test_20_config(self):
        """Test20 config prints the normalized project as JSON"""
        (status, out, dummy, dummy2, dummy3) = self.run_compose(
            ["config", "--file=" + self.path])
        self.assertEqual(status, 0)
        data = json.loads(out)
        self.assertEqual(data["name"], "myproj")
        self.assertEqual(sorted(data["services"]), ["db", "web"])
        web = data["services"]["web"]
        self.assertEqual(web["container_name"], "myproj_web_1")
        self.assertEqual(web["command"], ["sleep", "60"])
        self.assertEqual(web["environment"], ["A=1", "B=two"])
        self.assertEqual(web["volumes"],
                         [os.path.join(self.base, "data") + ":/data"])

    def test_21_usage_errors(self):
        """Test21 unknown commands and options fail with a message"""
        (status, dummy, errors, dummy2, dummy3) = self.run_compose(
            ["bogus"])
        self.assertEqual(status, 1)
        self.assertIn("unknown compose command", errors)
        self.assertIn("up, down, ps, logs, config", errors)
        (status, dummy, errors, dummy2, dummy3) = self.run_compose(
            ["up", "-d", "--bogus", "--file=" + self.path])
        self.assertEqual(status, 1)
        self.assertIn("unknown option", errors)
        (status, dummy, errors, dummy2, dummy3) = self.run_compose(
            ["config", "--file=/nonexistent/compose.yaml"])
        self.assertEqual(status, 1)
        self.assertIn("compose file not found", errors)
        (status, dummy, errors, dummy2, dummy3) = self.run_compose(
            ["up", "-d", "missing", "--file=" + self.path])
        self.assertEqual(status, 1)
        self.assertIn("no such service", errors)
        (status, dummy, errors, dummy2, dummy3) = self.run_compose(
            ["-f", self.path])
        self.assertEqual(status, 1)
        self.assertIn("compose command expected", errors)
        (status, out, dummy, dummy2, dummy3) = self.run_compose(["--help"])
        self.assertEqual(status, 0)
        self.assertIn("Commands:", out)
        (status, out, dummy, dummy2, dummy3) = self.run_compose(
            ["up", "--help"])
        self.assertEqual(status, 0)
        self.assertIn("multi-container project", out)

    def test_22_failed_child(self):
        """Test22 a failing child aborts up with the error status"""
        fake = FakeUdocker(failing=("--name=myproj_db_1",))
        (status, dummy, errors, dummy2, dummy3) = self.run_compose(
            ["up", "-d", "--file=" + self.path], fake)
        self.assertEqual(status, 1)
        self.assertIn("cannot create container", errors)

    def test_23_missing_compose_file(self):
        """Test23 the default compose file names are searched in the cwd"""
        self.assertEqual(compose.find_compose_file(self.base), self.path)
        empty = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, empty)
        self.assertEqual(compose.find_compose_file(empty), "")
        errors = io.StringIO()
        cwd = os.getcwd()
        os.chdir(empty)
        try:
            with patch.object(compose.subprocess, "Popen", FakeUdocker()), \
                    patch.object(compose.sys, "argv",
                                 ["udocker", "compose", "config"]), \
                    contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(errors):
                status = compose.do_compose(FakeCLI(), Mock())
        finally:
            os.chdir(cwd)
        self.assertEqual(status, 1)
        self.assertIn("no compose file found", errors.getvalue())


if __name__ == '__main__':
    main()
