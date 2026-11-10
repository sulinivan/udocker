#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
udocker unit tests: docker --ulimit parsing and application
"""

import resource
from unittest import TestCase, main

from udocker.utils import ulimits


class UlimitsTestCase(TestCase):
    """--ulimit statements, OCI rlimits and process limits"""

    def test_01_parse(self):
        """Test01 valid statements, defaults and hard limits"""
        self.assertEqual(ulimits.parse("nofile=64"),
                         {"name": "nofile", "type": "RLIMIT_NOFILE",
                          "soft": 64, "hard": 64})
        self.assertEqual(ulimits.parse("nofile=64:128")["hard"], 128)
        self.assertEqual(ulimits.parse("nofile=-1")["soft"], -1)
        self.assertEqual(len(ulimits.parse_all(["nofile=1", "nproc=2"])), 2)

    def test_02_invalid(self):
        """Test02 malformed statements raise ValueError"""
        for statement in ("nofile", "bogus=1", "nofile=x", "nofile=1:2:3",
                          "nofile=", ""):
            with self.assertRaises(ValueError):
                ulimits.parse(statement)

    def test_03_oci(self):
        """Test03 OCI rlimits entries, unlimited becomes uint64 max"""
        entries = ulimits.oci_rlimits(["nofile=64:128", "nproc=-1"])
        self.assertEqual(entries[0], {"type": "RLIMIT_NOFILE",
                                      "soft": 64, "hard": 128})
        self.assertEqual(entries[1]["soft"], ulimits.UNLIMITED)
        self.assertEqual(entries[1]["hard"], ulimits.UNLIMITED)

    def test_04_apply(self):
        """Test04 process limits are applied and refuse hard raises"""
        limit = resource.RLIMIT_NOFILE
        saved = ulimits.apply(["nofile=64:128"])
        self.assertEqual(resource.getrlimit(limit), (64, 128))
        ulimits.restore(saved)
        with self.assertRaises(ValueError):
            ulimits.apply(["nofile=64:%d" % (ulimits.UNLIMITED,)])
        with self.assertRaises(ValueError):
            ulimits.apply(["nofile=128:64"])


if __name__ == '__main__':
    main()
