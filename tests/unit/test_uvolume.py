#!/usr/bin/env python
"""
udocker unit tests: Uvolume
"""

from unittest import TestCase, main
from udocker.utils.uvolume import Uvolume
import collections

collections.Callable = collections.abc.Callable


class UvolumeTestCase(TestCase):
    """Test Uvolume()."""

    def test_01_init(self):
        """Test01 Uvolume() constructor"""
        volm = '/data'
        uvol = Uvolume(volm)
        self.assertEqual(uvol.volume, volm)

    def test_02_cleanpath(self):
        """Test02 Uvolume().cleanpath()."""
        path = '/bin/ls'
        volm = '/data'
        uvol = Uvolume(volm)
        result = uvol.cleanpath(path)
        self.assertEqual(result, path)

        path2 = '//bin//ls'
        volm = '/data'
        uvol = Uvolume(volm)
        result = uvol.cleanpath(path2)
        self.assertEqual(result, path)

    def test_03_split(self):
        """Test03 Uvolume().split()."""
        volm = '/data:/contdata'
        uvol = Uvolume(volm)
        result = uvol.split()
        self.assertEqual(result, ('/data', '/contdata'))

        volm = '/data'
        uvol = Uvolume(volm)
        result = uvol.split()
        self.assertEqual(result, ('/data', '/data'))

    def test_04_split_modes(self):
        """Test04 Uvolume().split() with docker volume modes."""
        uvol = Uvolume('/data:/contdata:ro')
        self.assertEqual(uvol.split(), ('/data', '/contdata'))
        self.assertEqual(uvol.mode, 'ro')
        self.assertTrue(uvol.readonly)

        uvol = Uvolume('/data:/contdata:ro,Z')
        self.assertEqual(uvol.split(), ('/data', '/contdata'))
        self.assertTrue(uvol.readonly)

        uvol = Uvolume('/data:/contdata:rw')
        self.assertEqual(uvol.split(), ('/data', '/contdata'))
        self.assertFalse(uvol.readonly)

        uvol = Uvolume('/data:/cont:weird')
        self.assertEqual(uvol.split(), ('/data', '/cont:weird'))
        self.assertEqual(uvol.mode, '')
        self.assertFalse(uvol.readonly)

        uvol = Uvolume('/data')
        self.assertEqual(uvol.split(), ('/data', '/data'))


if __name__ == '__main__':
    main()
