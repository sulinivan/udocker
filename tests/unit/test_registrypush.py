#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
udocker unit tests: push to a registry (Docker Registry HTTP API v2)
Runs against a local fake registry, no privileges and no network needed.
"""

import hashlib
import json
import os
import shutil
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import TestCase, main
from unittest.mock import Mock, patch
from urllib.parse import urlparse, parse_qs

from udocker.config import Config
from udocker.docker import DockerIoAPI, RegistryUploader


class FakeRegistry(object):
    """Minimal Docker Registry v2 HTTP endpoints for the push flow"""

    def __init__(self):
        self.blobs = {}
        self.pending = b""
        self.manifest = None
        self.headers_seen = []
        self.server = HTTPServer(("127.0.0.1", 0), self._handler())
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def url(self):
        return "http://127.0.0.1:%d" % self.port

    def _handler(self):
        registry = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "fake-registry"

            def log_message(self, *args):
                pass

            def _send(self, code, body=b"", headers=None):
                self.send_response(code)
                for (key, value) in (headers or {}).items():
                    self.send_header(key, str(value))
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def do_GET(self):
                if self.path.startswith("/token"):
                    body = json.dumps({"token": "testtoken"}).encode()
                    self._send(200, body, {"Content-Type": "application/json"})
                    return
                if self.path.startswith("/v2/"):
                    auth = self.headers.get("Authorization", "")
                    if auth.startswith("Bearer "):
                        self._send(200, b"{}")
                    else:
                        self._send(401, b"", {
                            "WWW-Authenticate":
                                'Bearer realm="%s/token",service="test"'
                                % registry.url()})
                    return
                self._send(404)

            def do_HEAD(self):
                digest = self.path.split("/blobs/")[-1]
                if digest in registry.blobs:
                    self._send(200)
                else:
                    self._send(404)

            def do_POST(self):
                registry.headers_seen.append(
                    self.headers.get("Authorization", ""))
                self._send(202, b"", {
                    "Location": self.path + "upload/1"})

            def do_PATCH(self):
                size = int(self.headers.get("Content-Length", 0))
                registry.pending = self.rfile.read(size)
                registry.headers_seen.append(
                    self.headers.get("Authorization", ""))
                self._send(202, b"", {"Location": self.path})

            def do_PUT(self):
                size = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(size)
                parsed = urlparse(self.path)
                if "/manifests/" in parsed.path:
                    registry.manifest = json.loads(body.decode())
                    self._send(201)
                    return
                digest = parse_qs(parsed.query).get("digest", [""])[0]
                if digest:
                    registry.blobs[digest] = registry.pending
                    self._send(201)
                    return
                self._send(400)

        return Handler


class RegistryPushTestCase(TestCase):
    """Test the rootless registry push implementation"""

    def setUp(self):
        Config().getconf()
        self.registry = FakeRegistry().start()
        self.addCleanup(self.registry.stop)
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir)

    def test_01_push_image(self):
        """Test01 push uploads config, layers and a schema2 manifest"""
        layer_file = os.path.join(self.tmpdir, "layer0.layer")
        with open(layer_file, "wb") as filep:
            filep.write(b"fake layer tar content")
        localrepo = Mock()
        localrepo.cd_imagerepo.return_value = os.path.join(self.tmpdir, "tag")
        localrepo.get_image_attributes.return_value = (
            {"architecture": "amd64", "os": "linux",
             "config": {"Env": ["PATH=/usr/bin"]}}, [layer_file])

        with patch('udocker.docker.GetURL'):
            api = DockerIoAPI(localrepo)
        api.set_registry(self.registry.url())
        api.set_v2_login_token("dXNlcjpwYXNz")
        status = api.push("testrepo", "v1")
        self.assertTrue(status)

        manifest = self.registry.manifest
        self.assertEqual(manifest["schemaVersion"], 2)
        self.assertEqual(manifest["config"]["mediaType"],
                         RegistryUploader.CONFIG_TYPE)
        self.assertEqual(len(manifest["layers"]), 1)
        layer_digest = manifest["layers"][0]["digest"]
        self.assertIn(layer_digest, self.registry.blobs)
        self.assertEqual(self.registry.blobs[layer_digest],
                         b"fake layer tar content")
        layer_hash = "sha256:" + hashlib.sha256(
            b"fake layer tar content").hexdigest()
        self.assertEqual(layer_digest, layer_hash)
        config_digest = manifest["config"]["digest"]
        self.assertIn(config_digest, self.registry.blobs)
        self.assertIn("Bearer testtoken", self.registry.headers_seen)

    def test_02_push_skips_existing_blobs(self):
        """Test02 blobs already in the registry are not uploaded again"""
        layer_file = os.path.join(self.tmpdir, "layer0.layer")
        with open(layer_file, "wb") as filep:
            filep.write(b"layer")
        layer_digest = "sha256:" + hashlib.sha256(b"layer").hexdigest()
        self.registry.blobs[layer_digest] = b"layer"
        localrepo = Mock()
        localrepo.cd_imagerepo.return_value = "/tag"
        localrepo.get_image_attributes.return_value = (
            {"architecture": "amd64", "os": "linux"}, [layer_file])
        with patch('udocker.docker.GetURL'):
            api = DockerIoAPI(localrepo)
        api.set_registry(self.registry.url())
        status = api.push("testrepo", "v1")
        self.assertTrue(status)
        self.assertEqual(self.registry.blobs[layer_digest], b"layer")
        self.assertIsNotNone(self.registry.manifest)

    def test_03_push_missing_image(self):
        """Test03 push fails when the local image is absent"""
        localrepo = Mock()
        localrepo.cd_imagerepo.return_value = ""
        with patch('udocker.docker.GetURL'):
            api = DockerIoAPI(localrepo)
        api.set_registry(self.registry.url())
        self.assertFalse(api.push("testrepo", "v1"))

    def test_04_request_method(self):
        """Test04 _MethodRequest returns the requested HTTP method"""
        from udocker.docker import _MethodRequest
        request = _MethodRequest("http://localhost/", method="PATCH")
        self.assertEqual(request.get_method(), "PATCH")


if __name__ == '__main__':
    main()
