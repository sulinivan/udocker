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

    def __init__(self, containers=None, logs=None, failing=(),
                 inspect_output="healthy"):
        self.calls = []
        self.containers = containers or []
        self.logs = logs or {}
        self.failing = tuple(failing)
        self.inspect_output = inspect_output

    def __call__(self, argv, **kwargs):
        """Answer one child call"""
        self.calls.append(list(argv))
        args = list(argv[4:])
        text = ""
        if args[:3] == ["ps", "-a", "--format=json"]:
            text = json.dumps(self.containers)
        elif args and args[0] == "logs":
            text = self.logs.get(args[-1], "")
        elif args and args[0] == "inspect":
            text = self.inspect_output
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
            "    hostname: apphost\n"
            "    extra_hosts: [\"db:10.0.0.2\", \"cache=10.0.0.3\"]\n"
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
        self.assertIn("--label=x=y", args)
        self.assertIn("--hostname=apphost", args)
        self.assertIn("--add-host=db:10.0.0.2", args)
        self.assertIn("--add-host=cache:10.0.0.3", args)

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

    def test_09_env_and_ulimits(self):
        """Test09 .env substitution, env_file merge and ulimits arguments"""
        text = (
            "name: envproj\n"
            "services:\n"
            "  app:\n"
            "    image: busybox:${COMPOSE_E2E_TAG}\n"
            "    env_file: ./app.env\n"
            "    environment:\n"
            "      B: from-compose\n"
            "    restart: unless-stopped\n"
            "    ipc: host\n"
            "    runtime: runc\n"
            "    deploy:\n"
            "      replicas: 2\n"
            "    healthcheck:\n"
            "      test: [\"CMD-SHELL\", \"test -f /ok\"]\n"
            "      interval: 5s\n"
            "      retries: 2\n"
            "      start_period: 3s\n"
            "    stop_signal: SIGQUIT\n"
            "    stop_grace_period: 1m30s\n"
            "    networks: [backend]\n"
            "    network_mode: host\n"
            "    ulimits:\n"
            "      nofile: 128\n"
            "      nproc:\n"
            "        soft: 16\n"
            "        hard: 32\n"
            "    command: true\n"
        )
        with open(os.path.join(self.base, ".env"), "w") as filep:
            filep.write("COMPOSE_E2E_TAG=latest-from-env\n")
        with open(os.path.join(self.base, "app.env"), "w") as filep:
            filep.write("A=file\nB=file-value\n# comment\n")
        os.environ.pop("COMPOSE_E2E_TAG", None)
        path = write_compose(self.base, text)
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            project = compose.ComposeProject(path)
            plan = project.plan("app")
        self.assertNotIn("COMPOSE_E2E_TAG", os.environ)
        self.assertEqual(plan["image"], "busybox:latest-from-env")
        self.assertIn("A=file", plan["environment"])
        self.assertIn("B=from-compose", plan["environment"])
        self.assertEqual(plan["ulimits"], ["nofile=128", "nproc=16:32"])
        self.assertEqual(plan["restart"], "unless-stopped")
        self.assertEqual(plan["healthcheck"]["test"],
                         ["CMD-SHELL", "test -f /ok"])
        self.assertEqual(plan["healthcheck"]["interval"], 5)
        self.assertEqual(plan["healthcheck"]["retries"], 2)
        self.assertEqual(plan["healthcheck"]["start_period"], 3)
        self.assertEqual(plan["stop_signal"], "SIGQUIT")
        self.assertEqual(plan["stop_timeout"], 90)
        self.assertNotIn("networks", errors.getvalue())
        self.assertNotIn("unsupported key ignored: ipc", errors.getvalue())
        self.assertNotIn("unsupported key ignored: runtime",
                         errors.getvalue())
        self.assertNotIn("unsupported key ignored: deploy",
                         errors.getvalue())
        args = compose.run_arguments(plan)
        self.assertIn("--env=A=file", args)
        self.assertIn("--env=B=from-compose", args)
        self.assertIn("--ulimit=nofile=128", args)
        self.assertIn("--ulimit=nproc=16:32", args)
        self.assertIn("--restart=unless-stopped", args)
        self.assertIn("--health-cmd=test -f /ok", args)
        self.assertIn("--health-interval=5s", args)
        self.assertIn("--health-retries=2", args)
        self.assertIn("--health-start-period=3s", args)
        self.assertIn("--stop-signal=SIGQUIT", args)
        self.assertIn("--stop-timeout=90", args)

    def test_09_missing_env_file(self):
        """Test09 a missing env_file is a compose error"""
        text = (
            "services:\n"
            "  app:\n"
            "    image: busybox:latest\n"
            "    env_file: ./missing.env\n"
        )
        path = write_compose(self.base, text)
        project = compose.ComposeProject(path)
        with self.assertRaises(compose.ComposeError):
            project.plan("app")

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
            ["ps", "-a", "db", "--file=" + self.path], fake)
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
            ["config", "--format=json", "--file=" + self.path])
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

    def test_24_compose_file_preference(self):
        """Test24 udocker-compose files win over docker-compose ones"""
        directory = os.path.join(self.base, "pref")
        os.makedirs(directory)
        write_compose(directory, "services:\n  web:\n    image: busybox\n",
                      name="docker-compose.yml")
        udocker_path = write_compose(
            directory, "services:\n  web:\n    image: busybox\n",
            name="udocker-compose.yml")
        self.assertEqual(compose.find_compose_file(directory), udocker_path)
        canonical = write_compose(directory)
        self.assertEqual(compose.find_compose_file(directory), canonical)

    def test_25_compose_file_env(self):
        """Test25 $COMPOSE_FILE and $COMPOSE_PROJECT_NAME work from elsewhere"""
        directory = os.path.join(self.base, "envproj")
        os.makedirs(directory)
        path = write_compose(directory,
                             "services:\n  web:\n    image: busybox\n",
                             name="udocker-compose.yml")
        elsewhere = os.path.join(self.base, "elsewhere")
        os.makedirs(elsewhere)
        cwd = os.getcwd()
        os.chdir(elsewhere)
        try:
            with patch.dict(os.environ, {"COMPOSE_FILE": path}):
                (status, out, errors, dummy, dummy2) = self.run_compose(
                    ["config"])
            self.assertEqual(status, 0)
            self.assertEqual(errors, "")
            self.assertIn("busybox", out)
            with patch.dict(os.environ, {"COMPOSE_FILE": path,
                                         "COMPOSE_PROJECT_NAME": "Env"}):
                (status, out, errors, dummy, dummy2) = self.run_compose(
                    ["ps"])
            self.assertEqual(status, 0)
            self.assertIn("project env", out)
        finally:
            os.chdir(cwd)

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


    def test_20_depends_on_healthy(self):
        """Test20 depends_on service_healthy waits before starting"""
        text = (
            "name: dep\n"
            "services:\n"
            "  db:\n"
            "    image: busybox:latest\n"
            "    healthcheck:\n"
            "      test: [\"CMD-SHELL\", \"true\"]\n"
            "    command: sleep 60\n"
            "  web:\n"
            "    image: busybox:latest\n"
            "    depends_on:\n"
            "      db:\n"
            "        condition: service_healthy\n"
            "    command: sleep 60\n"
        )
        path = write_compose(self.base, text, name="depends.yaml")
        fake = FakeUdocker(inspect_output="healthy")
        (status, out, errors, fake, cmdp) = self.run_compose(
            ["up", "-d", "--file=" + path], fake)
        self.assertEqual(status, 0)
        self.assertIn("waiting for dep_db_1", out)
        inspects = [call for call in fake.commands()
                    if call and call[0] == "inspect"]
        self.assertTrue(inspects)
        self.assertEqual(inspects[0][1], "-f")
        self.assertIn("State.Health.Status", inspects[0][2])

    def test_21_depends_on_unhealthy(self):
        """Test21 an unhealthy dependency aborts compose up"""
        text = (
            "name: dep\n"
            "services:\n"
            "  db:\n"
            "    image: busybox:latest\n"
            "    healthcheck:\n"
            "      test: [\"CMD-SHELL\", \"true\"]\n"
            "  web:\n"
            "    image: busybox:latest\n"
            "    depends_on:\n"
            "      db:\n"
            "        condition: service_healthy\n"
        )
        path = write_compose(self.base, text, name="depends.yaml")
        fake = FakeUdocker(inspect_output="unhealthy")
        (status, out, errors, fake, cmdp) = self.run_compose(
            ["up", "-d", "--file=" + path], fake)
        self.assertEqual(status, 1)
        self.assertIn("not healthy", errors)

    def test_22_up_wait(self):
        """Test22 compose up --wait waits for healthy containers"""
        text = (
            "name: waitproj\n"
            "services:\n"
            "  app:\n"
            "    image: busybox:latest\n"
            "    healthcheck:\n"
            "      test: [\"CMD-SHELL\", \"true\"]\n"
            "    command: sleep 60\n"
        )
        path = write_compose(self.base, text, name="wait.yaml")
        fake = FakeUdocker(inspect_output="healthy")
        (status, out, errors, fake, cmdp) = self.run_compose(
            ["up", "-d", "--wait", "--file=" + path], fake)
        self.assertEqual(status, 0)
        self.assertIn("project waitproj is up", out)
    def test_24_option_surface(self):
        """Test24 every docker compose option of the census is recognized"""
        total = sum(len(table) for table in compose.DOCKER_OPTIONS.values())
        self.assertEqual(len(compose.DOCKER_OPTIONS), 36)
        self.assertEqual(total, 232)
        for (page, table) in compose.DOCKER_OPTIONS.items():
            for flag in table:
                self.assertEqual(compose.canonical_option(page, flag), flag)
        self.assertEqual(compose.canonical_option("up", "-d"), "--detach")
        self.assertEqual(compose.canonical_option("logs", "-f"), "--follow")
        self.assertEqual(compose.canonical_option("version", "-f"),
                         "--format")
        self.assertIsNone(compose.canonical_option("up", "--bogus"))

    def test_25_global_options_override_files(self):
        """Test25 globals come before the command and -f files merge"""
        base = write_compose(self.base, COMPOSE_TEXT, "base.yaml")
        extra = os.path.join(self.base, "override.yaml")
        with open(extra, "w") as filep:
            filep.write("services:\n"
                        "  web:\n"
                        "    environment:\n"
                        "      - C=3\n"
                        "      - A=override\n")
        (status, out, errors, dummy, dummy2) = self.run_compose(
            ["-p", "Renamed", "-f", base, "-f", extra, "config",
             "--format=json"])
        self.assertEqual(status, 0, errors)
        data = json.loads(out)
        self.assertEqual(data["name"], "renamed")
        environment = data["services"]["web"]["environment"]
        self.assertIn("C=3", environment)
        self.assertIn("A=override", environment)
        self.assertIn("B=two", environment)

    def test_26_profiles_and_project_directory(self):
        """Test26 --profile filters services, --project-directory sets paths"""
        text = ("name: prof\n"
                "services:\n"
                "  app:\n"
                "    image: busybox:latest\n"
                "    volumes: [\"./data:/data\"]\n"
                "  debug:\n"
                "    image: busybox:latest\n"
                "    profiles: [debug]\n")
        path = write_compose(self.base, text, "profiles.yaml")
        (status, out, dummy, dummy2, dummy3) = self.run_compose(
            ["config", "--services", "--file=" + path])
        self.assertEqual(status, 0)
        self.assertEqual(out.split(), ["app"])
        (status, out, dummy, dummy2, dummy3) = self.run_compose(
            ["--profile", "debug", "config", "--services",
             "--file=" + path])
        self.assertEqual(status, 0)
        self.assertEqual(out.split(), ["app", "debug"])
        alt = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, alt)
        (status, out, dummy, dummy2, dummy3) = self.run_compose(
            ["--project-directory", alt, "config", "--format=json",
             "--file=" + path])
        self.assertEqual(status, 0)
        data = json.loads(out)
        self.assertEqual(data["services"]["app"]["volumes"],
                         [os.path.join(alt, "data") + ":/data"])

    def test_27_dry_run(self):
        """Test27 --dry-run prints the command and runs no child process"""
        fake = FakeUdocker()
        (status, out, errors, fake, dummy) = self.run_compose(
            ["up", "-d", "--dry-run", "--file=" + self.path], fake)
        self.assertEqual(status, 0)
        self.assertIn("Dry run:", out)
        self.assertEqual(fake.calls, [])

    def test_28_explicit_unsupported(self):
        """Test28 root-only and not applicable options fail explicitly"""
        (status, dummy, errors, dummy2, dummy3) = self.run_compose(
            ["exec", "--privileged", "--file=" + self.path, "web", "true"])
        self.assertEqual(status, 1)
        self.assertIn("requires root privileges", errors)
        self.assertIn("--privileged", errors)
        (status, dummy, errors, dummy2, dummy3) = self.run_compose(
            ["up", "--scale", "web=2", "--file=" + self.path])
        self.assertEqual(status, 1)
        self.assertIn("not applicable to rootless udocker", errors)
        self.assertIn("multi-replica", errors)
        (status, dummy, errors, dummy2, dummy3) = self.run_compose(["scale"])
        self.assertEqual(status, 1)
        self.assertIn("not applicable to rootless udocker", errors)
        (status, dummy, errors, dummy2, dummy3) = self.run_compose(
            ["up", "--abort-on-container-exit", "--file=" + self.path])
        self.assertEqual(status, 1)
        self.assertIn("not applicable to rootless udocker", errors)

    def test_29_ps_options(self):
        """Test29 ps -a, -q, --services, --status and --format json"""
        containers = [
            {"name": "myproj_web_1", "status": "running",
             "image": "busybox:latest"},
            {"name": "myproj_db_1", "status": "exited",
             "image": "busybox:latest"},
            {"name": "myproj_old_1", "status": "running", "image": "x:1"},
            {"name": "other_web_1", "status": "running", "image": "y:1"},
        ]
        fake = FakeUdocker(containers=containers)
        (status, out, dummy, dummy2, dummy3) = self.run_compose(
            ["ps", "--file=" + self.path], fake)
        self.assertEqual(status, 0)
        self.assertIn("myproj_web_1", out)
        self.assertIn("myproj_old_1", out)
        self.assertNotIn("myproj_db_1", out)
        (status, out, dummy, dummy2, dummy3) = self.run_compose(
            ["ps", "-a", "--status", "exited", "--file=" + self.path], fake)
        self.assertIn("myproj_db_1", out)
        self.assertNotIn("myproj_web_1", out)
        (status, out, dummy, dummy2, dummy3) = self.run_compose(
            ["ps", "-q", "--file=" + self.path], fake)
        self.assertEqual(sorted(out.split()),
                         ["myproj_old_1", "myproj_web_1"])
        (status, out, dummy, dummy2, dummy3) = self.run_compose(
            ["ps", "--services", "--file=" + self.path], fake)
        self.assertEqual(out.split(), ["old", "web"])
        (status, out, dummy, dummy2, dummy3) = self.run_compose(
            ["ps", "--format", "json", "--file=" + self.path], fake)
        data = json.loads(out)
        self.assertEqual(sorted(row["Name"] for row in data),
                         ["myproj_old_1", "myproj_web_1"])

    def test_30_down_timeout_and_services(self):
        """Test30 down -t sets the stop timeout and honours services"""
        containers = [
            {"name": "myproj_web_1", "status": "running",
             "image": "busybox:latest"},
            {"name": "myproj_db_1", "status": "running",
             "image": "busybox:latest"},
        ]
        fake = FakeUdocker(containers=containers)
        (status, dummy, dummy2, fake, dummy3) = self.run_compose(
            ["down", "-t", "3", "web", "--file=" + self.path], fake)
        self.assertEqual(status, 0)
        commands = fake.commands()
        self.assertIn(["stop", "--time=3", "myproj_web_1"], commands)
        self.assertNotIn(["stop", "--time=3", "myproj_db_1"], commands)

    def test_31_create_and_no_start(self):
        """Test31 create and up --no-start create without starting"""
        fake = FakeUdocker()
        (status, out, errors, fake, dummy) = self.run_compose(
            ["create", "--file=" + self.path], fake)
        self.assertEqual(status, 0, errors)
        commands = fake.commands()
        self.assertEqual(commands[0], ["ps", "-a", "--format=json"])
        names = [command[1] for command in commands if command[0] == "create"]
        self.assertEqual(names, ["--name=myproj_db_1",
                                 "--name=myproj_web_1"])
        self.assertFalse([command for command in commands
                          if command[0] == "run"])
        fake = FakeUdocker()
        (status, out, errors, fake, dummy) = self.run_compose(
            ["up", "--no-start", "--file=" + self.path], fake)
        self.assertEqual(status, 0, errors)
        self.assertNotIn("attached to the project logs", out)
        self.assertFalse([command for command in fake.commands()
                          if command[0] == "run"])

    def test_32_build_args_and_pull_policy(self):
        """Test32 build --build-arg is forwarded and pull --policy=always"""
        text = ("name: bproj\n"
                "services:\n"
                "  app:\n"
                "    build: ./app\n")
        path = write_compose(self.base, text, "build.yaml")
        fake = FakeUdocker()
        (status, dummy, errors, fake, dummy2) = self.run_compose(
            ["build", "--build-arg", "A=1", "--build-arg", "B=2",
             "--file=" + path], fake)
        self.assertEqual(status, 0, errors)
        self.assertEqual(fake.commands()[0],
                         ["build", "-t=bproj_app:latest", "--force",
                          "--build-arg=A=1", "--build-arg=B=2",
                          os.path.join(self.base, "app")])
        fake = FakeUdocker()
        (status, dummy, errors, fake, dummy2) = self.run_compose(
            ["pull", "--policy", "always", "--file=" + path], fake)
        self.assertEqual(status, 0, errors)
        self.assertIn(["pull", "bproj_app:latest"], fake.commands())

    def test_33_run_oneoff(self):
        """Test33 run forwards its options and stops parsing at the service"""
        fake = FakeUdocker()
        (status, dummy, errors, fake, dummy2) = self.run_compose(
            ["run", "--rm", "-e", "A=1", "-v", "/tmp/x:/y",
             "--service-ports", "--file=" + self.path, "web", "sh", "-c",
             "echo hi"], fake)
        self.assertEqual(status, 0, errors)
        runs = [command for command in fake.commands()
                if command[0] == "run" and command[-1] == "echo hi"]
        self.assertEqual(len(runs), 1)
        command = runs[0]
        self.assertIn("--rm", command)
        self.assertIn("--env=A=1", command)
        self.assertIn("--volume=/tmp/x:/y", command)
        self.assertIn("--publish=8080:80", command)
        self.assertEqual(command[-4:], ["busybox:latest", "sh", "-c",
                                        "echo hi"])

    def test_34_exec_options(self):
        """Test34 exec forwards options and the command after the service"""
        containers = [{"name": "myproj_web_1", "status": "running",
                       "image": "busybox:latest"}]
        fake = FakeUdocker(containers=containers)
        (status, dummy, errors, fake, dummy2) = self.run_compose(
            ["exec", "-T", "-e", "A=1", "-u", "app", "-w", "/app",
             "--file=" + self.path, "web", "sh", "-c", "echo hi"], fake)
        self.assertEqual(status, 0, errors)
        self.assertEqual(fake.commands()[0],
                         ["exec", "--env=A=1", "--user=app",
                          "--workdir=/app", "myproj_web_1", "sh", "-c",
                          "echo hi"])

    def test_35_lifecycle_delegation(self):
        """Test35 start/stop/restart/kill/pause/unpause/rm wait top port cp"""
        containers = [
            {"name": "myproj_web_1", "status": "running", "image": "b:1"},
            {"name": "myproj_db_1", "status": "exited", "image": "b:1"},
        ]
        fake = FakeUdocker(containers=containers)
        cases = [
            (["start", "--file=" + self.path], ["start", "myproj_db_1"]),
            (["stop", "--timeout", "2", "--file=" + self.path],
             ["stop", "--time=2", "myproj_web_1"]),
            (["restart", "--file=" + self.path],
             ["restart", "myproj_web_1"]),
            (["kill", "-s", "SIGTERM", "--file=" + self.path],
             ["kill", "--signal=SIGTERM", "myproj_web_1"]),
            (["pause", "web", "--file=" + self.path],
             ["pause", "myproj_web_1"]),
            (["unpause", "web", "--file=" + self.path],
             ["unpause", "myproj_web_1"]),
            (["rm", "-f", "web", "--file=" + self.path],
             ["rm", "-f", "myproj_web_1"]),
            (["wait", "db", "--file=" + self.path],
             ["wait", "myproj_db_1"]),
            (["top", "web", "--file=" + self.path],
             ["top", "myproj_web_1"]),
            (["port", "web", "80", "--file=" + self.path],
             ["port", "myproj_web_1", "80"]),
            (["cp", "web:/x", "/tmp/y", "--file=" + self.path],
             ["cp", "myproj_web_1:/x", "/tmp/y"]),
            (["commit", "web", "repo/img:1", "--file=" + self.path],
             ["commit", "myproj_web_1", "repo/img:1"]),
            (["export", "-o", "/tmp/x.tar", "web", "--file=" + self.path],
             ["export", "-o", "/tmp/x.tar", "myproj_web_1"]),
        ]
        for (args, expected) in cases:
            (status, dummy, errors, fake, dummy2) = self.run_compose(
                args, fake)
            self.assertEqual(status, 0, "%s: %s" % (args, errors))
            self.assertIn(expected, fake.commands())

    def test_36_events_images_ls(self):
        """Test36 events delegation, images and ls output"""
        containers = [
            {"name": "myproj_web_1", "status": "running", "image": "b:1"},
            {"name": "other_web_1", "status": "running", "image": "c:1"},
        ]
        fake = FakeUdocker(containers=containers)
        (status, dummy, errors, fake, dummy2) = self.run_compose(
            ["events", "--json", "--since", "1h", "--until", "1s",
             "--file=" + self.path], fake)
        self.assertEqual(status, 0, errors)
        self.assertEqual(fake.commands()[0],
                         ["events", "--since=1h", "--until=1s",
                          "--format=json",
                          "--filter=container=myproj_web_1",
                          "--filter=container=myproj_db_1"])
        (status, out, errors, fake, dummy2) = self.run_compose(
            ["images", "--file=" + self.path], fake)
        self.assertEqual(status, 0)
        self.assertIn("myproj_web_1", out)
        self.assertIn("b:1", out)
        (status, out, errors, fake, dummy2) = self.run_compose(
            ["ls", "-a", "-q", "--file=" + self.path], fake)
        self.assertEqual(sorted(out.split()), ["myproj", "other"])
        (status, out, errors, fake, dummy2) = self.run_compose(
            ["ls", "--format", "json", "--file=" + self.path], fake)
        self.assertEqual(sorted(row["Name"] for row in json.loads(out)),
                         ["myproj", "other"])

    def test_37_volumes_existing(self):
        """Test37 volumes lists the named volumes that exist"""
        text = ("name: myproj\n"
                "services:\n"
                "  web:\n"
                "    image: busybox:latest\n"
                "    volumes: [\"data:/data\"]\n"
                "volumes:\n"
                "  data: {}\n")
        path = write_compose(self.base, text, "vol.yaml")
        os.makedirs(os.path.join(self.base, "volumes", "myproj_data",
                                 "_data"))
        with patch.dict(Config.conf, {"topdir": self.base}):
            (status, out, dummy, dummy2, dummy3) = self.run_compose(
                ["volumes", "-q", "--file=" + path])
        self.assertEqual(status, 0)
        self.assertEqual(out.split(), ["myproj_data"])

    def test_38_version(self):
        """Test38 version pretty, --short and --format json"""
        (status, out, dummy, dummy2, dummy3) = self.run_compose(["version"])
        self.assertEqual(status, 0)
        self.assertEqual(out.strip(), "Docker Compose version v5.7.0")
        (status, out, dummy, dummy2, dummy3) = self.run_compose(
            ["version", "--short"])
        self.assertEqual(out.strip(), "5.7.0")
        (status, out, dummy, dummy2, dummy3) = self.run_compose(
            ["version", "--format=json"])
        self.assertEqual(json.loads(out), {"version": "v5.7.0"})

    def test_39_config_outputs(self):
        """Test39 config selectors, hash, file output and default YAML"""
        (status, out, dummy, dummy2, dummy3) = self.run_compose(
            ["config", "--services", "--file=" + self.path])
        self.assertEqual(out.split(), ["web", "db"])
        (status, out, dummy, dummy2, dummy3) = self.run_compose(
            ["config", "--images", "--file=" + self.path])
        self.assertEqual(out.split(), ["busybox:latest", "busybox:latest"])
        (status, out, dummy, dummy2, dummy3) = self.run_compose(
            ["config", "--hash", "*", "--file=" + self.path])
        fields = out.split()
        self.assertEqual(fields[0], "web")
        self.assertEqual(len(fields[1]), 64)
        (status, out, errors, dummy, dummy2) = self.run_compose(
            ["config", "--format=json", "--quiet", "--file=" + self.path])
        self.assertEqual((status, out), (0, ""))
        target = os.path.join(self.base, "config.json")
        (status, out, dummy, dummy2, dummy3) = self.run_compose(
            ["config", "--format=json", "-o", target, "--file=" + self.path])
        self.assertEqual(status, 0)
        self.assertTrue(os.path.exists(target))
        with open(target) as filep:
            self.assertEqual(json.load(filep)["name"], "myproj")
        (status, out, dummy, dummy2, dummy3) = self.run_compose(
            ["config", "--file=" + self.path])
        self.assertIn("name: myproj", out)
        self.assertIn("  web:", out)

    def test_40_config_not_applicable(self):
        """Test40 not applicable config options and invalid values"""
        (status, dummy, errors, dummy2, dummy3) = self.run_compose(
            ["config", "--models", "--file=" + self.path])
        self.assertEqual(status, 1)
        self.assertIn("not applicable to rootless udocker", errors)
        (status, dummy, errors, dummy2, dummy3) = self.run_compose(
            ["config", "--format=toml", "--file=" + self.path])
        self.assertEqual(status, 1)
        self.assertIn("unsupported --format value", errors)
        (status, dummy, errors, dummy2, dummy3) = self.run_compose(
            ["up", "--timeout", "abc", "--file=" + self.path])
        self.assertEqual(status, 1)
        self.assertIn("invalid --timeout value", errors)

    def test_41_env_file_and_interpolation(self):
        """Test41 --env-file feeds the interpolation, --no-interpolate off"""
        envfile = os.path.join(self.base, "probe.env")
        with open(envfile, "w") as filep:
            filep.write("PROBE_TAG=fromfile\n")
        text = ("name: envproj\n"
                "services:\n"
                "  app:\n"
                "    image: \"busybox:${PROBE_TAG}\"\n")
        path = write_compose(self.base, text, "env.yaml")
        os.environ.pop("PROBE_TAG", None)
        self.addCleanup(os.environ.pop, "PROBE_TAG", None)
        (status, out, dummy, dummy2, dummy3) = self.run_compose(
            ["--env-file", envfile, "config", "--format=json",
             "--file=" + path])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out)["services"]["app"]["image"],
                         "busybox:fromfile")
        (status, out, dummy, dummy2, dummy3) = self.run_compose(
            ["config", "--no-interpolate", "--format=json",
             "--file=" + path])
        self.assertEqual(json.loads(out)["services"]["app"]["image"],
                         "busybox:${PROBE_TAG}")

    def test_42_no_env_resolution_and_paths(self):
        """Test42 --no-env-resolution and --no-path-resolution keep values"""
        with open(os.path.join(self.base, "service.env"), "w") as filep:
            filep.write("FROM_FILE=1\n")
        text = ("name: rproj\n"
                "services:\n"
                "  app:\n"
                "    image: busybox:latest\n"
                "    env_file: ./service.env\n"
                "    environment: [\"A=1\"]\n"
                "    volumes: [\"./data:/data\"]\n")
        path = write_compose(self.base, text, "res.yaml")
        (status, out, dummy, dummy2, dummy3) = self.run_compose(
            ["config", "--no-env-resolution", "--no-path-resolution",
             "--format=json", "--file=" + path])
        self.assertEqual(status, 0)
        plan = json.loads(out)["services"]["app"]
        self.assertEqual(plan["environment"], ["A=1"])
        self.assertEqual(plan["volumes"], ["./data:/data"])

    def test_43_up_attach_filter(self):
        """Test43 up --attach limits the followed logs"""
        with patch.object(compose, "stream_logs") as mock_logs:
            (status, dummy, errors, fake, dummy2) = self.run_compose(
                ["up", "--attach", "db", "--file=" + self.path])
        self.assertEqual(status, 0, errors)
        self.assertEqual(mock_logs.call_args[0][0], ["myproj_db_1"])
        stops = [command for command in fake.commands()
                 if command[0] == "stop"]
        self.assertEqual(sorted(command[1] for command in stops),
                         ["myproj_db_1", "myproj_web_1"])

    def test_44_bool_option_values(self):
        """Test44 --option=false turns a boolean flag off"""
        containers = [{"name": "myproj_db_1", "status": "exited",
                       "image": "busybox:latest"}]
        fake = FakeUdocker(containers=containers)
        (status, out, dummy, dummy2, dummy3) = self.run_compose(
            ["ps", "--file=" + self.path], fake)
        self.assertNotIn("myproj_db_1", out)
        (status, out, dummy, dummy2, dummy3) = self.run_compose(
            ["ps", "--all=true", "--file=" + self.path], fake)
        self.assertIn("myproj_db_1", out)

    def test_45_up_profiles(self):
        """Test45 up starts the services of the enabled profiles only"""
        text = ("name: pj\n"
                "services:\n"
                "  app:\n"
                "    image: busybox:latest\n"
                "    command: sleep 5\n"
                "  debug:\n"
                "    image: busybox:latest\n"
                "    profiles: [debug]\n"
                "    command: sleep 5\n")
        path = write_compose(self.base, text, "pup.yaml")
        fake = FakeUdocker()
        (status, dummy, errors, fake, dummy2) = self.run_compose(
            ["up", "-d", "--file=" + path], fake)
        self.assertEqual(status, 0, errors)
        names = [command[1] for command in fake.commands()
                 if command[0] == "create"]
        self.assertEqual(names, ["--name=pj_app_1"])
        fake = FakeUdocker()
        (status, dummy, errors, fake, dummy2) = self.run_compose(
            ["--profile", "debug", "up", "-d", "--file=" + path], fake)
        self.assertEqual(status, 0, errors)
        names = [command[1] for command in fake.commands()
                 if command[0] == "create"]
        self.assertEqual(names, ["--name=pj_app_1", "--name=pj_debug_1"])

    def test_46_logs_time_options(self):
        """Test46 logs --since/--until/--timestamps are forwarded"""
        fake = FakeUdocker(logs={"myproj_web_1": "line\n"})
        (status, out, errors, fake, dummy) = self.run_compose(
            ["logs", "--since", "1h", "--until", "1s", "--timestamps",
             "web", "--file=" + self.path], fake)
        self.assertEqual(status, 0, errors)
        self.assertEqual(fake.commands()[0],
                         ["logs", "--since=1h", "--until=1s",
                          "--timestamps", "myproj_web_1"])

    def test_47_up_timestamps_follow(self):
        """Test47 up --timestamps is forwarded to the followed logs"""
        with patch.object(compose, "stream_logs") as mock_logs:
            (status, dummy, errors, dummy2, dummy3) = self.run_compose(
                ["up", "--timestamps", "--file=" + self.path])
        self.assertEqual(status, 0, errors)
        self.assertEqual(mock_logs.call_args[1]["extra"], ["--timestamps"])


if __name__ == '__main__':
    main()
