#!/usr/bin/env python
"""
udocker unit tests: UMain
"""

from unittest import TestCase, main
from unittest.mock import patch
from udocker.umain import UMain
from udocker.config import Config
import collections

collections.Callable = collections.abc.Callable


class UMainTestCase(TestCase):
    """Test UMain() class main udocker program."""

    def setUp(self):
        Config().getconf()

    def tearDown(self):
        pass

    def test_01_init(self):
        """Test01 UMain(argv) constructor."""
        argv = ["udocker", "-h"]
        udoc = UMain(argv)
        self.assertEqual(udoc.argv, argv)

    @patch('udocker.umain.Msg')
    @patch('udocker.umain.UdockerCLI')
    @patch('udocker.umain.LocalRepository')
    @patch('udocker.umain.os.geteuid')
    def test_02__prepare_exec(self, mock_getuid,
                              mock_local, mock_ucli, mock_msg):
        """Test02 UMain()._prepare_exec()."""
        argv = ["udocker", "-h"]
        mock_msg.level = 0
        mock_msg.VER = 4
        mock_getuid.return_value = 0
        with patch('sys.exit') as mock_exit:
            umain = UMain(argv)
            umain._prepare_exec()
            self.assertTrue(mock_exit.called)

        argv = ["udocker", "-h", "--debug", "--insecure"]
        mock_msg.level = 0
        mock_msg.VER = 4
        mock_getuid.return_value = 100
        mock_local.return_value.is_repo.return_value = True
        mock_local.return_value.create_repo.return_value = None
        mock_ucli.return_value = None
        umain = UMain(argv)
        umain._prepare_exec()
        self.assertTrue(mock_getuid.called)
        self.assertTrue(mock_local.return_value.is_repo.called)
        self.assertTrue(mock_ucli.called)

    @patch('udocker.umain.Msg')
    @patch('udocker.umain.UdockerCLI')
    def test_03_execute(self, mock_ucli, mock_msg):
        """Test03 UMain().execute()."""
        mock_msg.level = 0
        argv = ['udocker', '--allow-root', '-h']
        mock_ucli.return_value.do_help.return_value = 0
        umain = UMain(argv)
        status = umain.execute()
        self.assertTrue(mock_ucli.return_value.do_help.called)
        self.assertEqual(status, 0)

        argv = ['udocker', '--allow-root', '--version']
        mock_ucli.return_value.do_version.return_value = 0
        umain = UMain(argv)
        status = umain.execute()
        self.assertTrue(mock_ucli.return_value.do_version.called)
        self.assertEqual(status, 0)

        argv = ['udocker', '--allow-root', 'install']
        mock_ucli.return_value.do_install.return_value = 0
        umain = UMain(argv)
        status = umain.execute()
        self.assertTrue(mock_ucli.return_value.do_install.called)
        self.assertEqual(status, 0)

        argv = ['udocker', '--allow-root', 'showconf']
        mock_ucli.return_value.do_showconf.return_value = 0
        umain = UMain(argv)
        status = umain.execute()
        self.assertTrue(mock_ucli.return_value.do_showconf.called)
        self.assertEqual(status, 0)

        argv = ['udocker', '--allow-root', 'rm']
        mock_ucli.return_value.do_rm.return_value = 0
        umain = UMain(argv)
        status = umain.execute()
        self.assertTrue(mock_ucli.return_value.do_rm.called)
        self.assertEqual(status, 0)

        argv = ['udocker', '--allow-root', 'faking']
        umain = UMain(argv)
        status = umain.execute()
        self.assertEqual(status, 1)
    @patch('udocker.umain.Msg')
    @patch('udocker.umain.UdockerCLI')
    @patch('udocker.umain.LocalRepository')
    @patch('udocker.umain.os.geteuid')
    def test_04_repo_path_expanded_and_created(self, mock_getuid,
                                               mock_local, mock_ucli,
                                               mock_msg):
        """Test04 --repo with ~ is expanded and a missing repo is created."""
        mock_msg.level = 0
        mock_getuid.return_value = 1000
        mock_local.return_value.is_repo.return_value = False
        mock_local.return_value.create_repo.return_value = True
        with patch('udocker.umain.os.path.isdir', return_value=False), \
                patch('udocker.umain.os.path.expanduser',
                      side_effect=lambda p: p.replace("~", "/home/u")):
            umain = UMain(["udocker", "--repo=~/repos/x", "images"])
            umain._prepare_exec()
        self.assertEqual(Config.conf['topdir'], "/home/u/repos/x")
        self.assertTrue(mock_local.return_value.create_repo.called)
        self.assertTrue(mock_ucli.called)

    @patch('udocker.umain.Msg')
    @patch('udocker.umain.UdockerCLI')
    @patch('udocker.umain.LocalRepository')
    @patch('udocker.umain.os.geteuid')
    def test_05_repo_populated_is_rejected(self, mock_getuid, mock_local,
                                           mock_ucli, mock_msg):
        """Test05 an existing non-repository directory is not taken over."""
        mock_msg.level = 0
        mock_getuid.return_value = 1000
        mock_local.return_value.is_repo.return_value = False
        with patch('udocker.umain.os.path.isdir', return_value=True), \
                patch('udocker.umain.os.listdir', return_value=["data"]):
            umain = UMain(["udocker", "--repo=/data/myrepo", "images"])
            with self.assertRaises(SystemExit):
                umain._prepare_exec()
        self.assertFalse(mock_local.return_value.create_repo.called)

    @patch('udocker.umain.Msg')
    @patch('udocker.umain.UdockerCLI')
    @patch('udocker.umain.LocalRepository')
    @patch('udocker.umain.os.geteuid')
    def test_06_repo_create_failure(self, mock_getuid, mock_local,
                                    mock_ucli, mock_msg):
        """Test06 a repository that cannot be created is a hard error."""
        mock_msg.level = 0
        mock_getuid.return_value = 1000
        mock_local.return_value.is_repo.return_value = False
        mock_local.return_value.create_repo.return_value = False
        with patch('udocker.umain.os.path.isdir', return_value=False):
            umain = UMain(["udocker", "--repo=/ro/repo", "images"])
            with self.assertRaises(SystemExit):
                umain._prepare_exec()
        self.assertFalse(mock_ucli.called)


if __name__ == '__main__':
    main()
