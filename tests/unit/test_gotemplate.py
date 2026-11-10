#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
udocker unit tests: docker Go-template subset
"""

from unittest import TestCase, main

from udocker.utils.gotemplate import render


class GoTemplateTestCase(TestCase):
    """Rendering of the {{...}} placeholders docker --format accepts"""

    def setUp(self):
        self.data = {
            "ID": "abc123",
            "Names": "web",
            "N": 3,
            "State": {"Status": "running", "ExitCode": 0},
            "List": ["a", "b"],
        }

    def test_01_fields(self):
        """Test01 scalars, nested paths and literal text"""
        self.assertEqual(render("{{.Names}}", self.data), "web")
        self.assertEqual(render("{{.State.Status}}", self.data), "running")
        self.assertEqual(render("id={{.ID}} n={{.N}}", self.data),
                         "id=abc123 n=3")
        self.assertEqual(render("plain", self.data), "plain")

    def test_02_json_and_missing(self):
        """Test02 json function, missing paths and escapes"""
        self.assertEqual(render("{{json .State}}", self.data),
                         '{"ExitCode":0,"Status":"running"}')
        self.assertEqual(render("{{.Missing}}", self.data), "<no value>")
        self.assertEqual(render("{{.State.Missing}}", self.data),
                         "<no value>")
        self.assertEqual(render("a\\tb\\nc", self.data), "a\tb\nc")

    def test_03_edge_cases(self):
        """Test03 lists, quotes, unclosed placeholders and empty input"""
        self.assertEqual(render("{{.List}}", self.data), '["a","b"]')
        self.assertEqual(render('{{"text"}}', self.data), "text")
        self.assertEqual(render("{{.ID", self.data), "{{.ID")
        self.assertEqual(render("", self.data), "")
        self.assertEqual(render(None, self.data), "")
