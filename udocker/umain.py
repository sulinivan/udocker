# -*- coding: utf-8 -*-
"""Implements most of the command line interface."""

import os
import sys
from udocker.msg import Msg
from udocker.cmdparser import CmdParser
from udocker.config import Config
from udocker.container.localrepo import LocalRepository
from udocker.cli import UdockerCLI


# docker command groups and their udocker equivalents. The group syntax is
# rewritten before parsing, so every flag of the target command keeps working.
COMPAT_GROUPS = {
    "container": {
        "ls": ["ps"], "list": ["ps"], "ps": ["ps"],
        "run": ["run"], "create": ["create"], "start": ["start"],
        "stop": ["stop"], "restart": ["restart"], "kill": ["kill"],
        "rm": ["rm"], "remove": ["rm"], "exec": ["exec"],
        "logs": ["logs"], "inspect": ["inspect"], "top": ["top"],
        "stats": ["stats"], "port": ["port"], "diff": ["diff"],
        "wait": ["wait"], "commit": ["commit"], "cp": ["cp"],
        "rename": ["rename"], "pause": ["pause"],
        "unpause": ["unpause"],
    },
    "image": {
        "ls": ["images"], "list": ["images"], "pull": ["pull"],
        "push": ["push"], "rm": ["rmi"], "remove": ["rmi"],
        "tag": ["tag"], "inspect": ["inspect"],
        "history": ["history"], "save": ["save"], "load": ["load"],
        "import": ["import"], "export": ["export"],
        "build": ["build"], "prune": ["image", "prune"],
        "manifest": ["manifest"],
    },
    "system": {
        "df": ["system", "df"], "prune": ["system", "prune"],
        "info": ["info"],
    },
}


# short options that are always boolean, safe to split out of a combined
# group such as -aq or -it
SHORT_FLAGS = "aqitdmslDPTV"


def expand_short_flags(argv):
    """Expand combined boolean short options: -aq -> -a -q"""
    result = [argv[0]]
    command_seen = False
    options_region = False
    for token in argv[1:]:
        if not command_seen:
            result.append(token)
            if not token.startswith("-"):
                command_seen = True
                options_region = True
            continue
        combined = (options_region and token.startswith("-") and
                    not token.startswith("--") and len(token) > 2 and
                    "=" not in token and
                    all(char in SHORT_FLAGS for char in token[1:]))
        if combined:
            result.extend("-" + char for char in token[1:])
            continue
        result.append(token)
        if options_region and not token.startswith("-"):
            options_region = False
    return result


def expand_compat_argv(argv):
    """Rewrite docker group syntax, e.g. 'container ls', to udocker commands"""
    for index in range(1, len(argv)):
        token = argv[index]
        if token.startswith("-"):
            continue
        group = COMPAT_GROUPS.get(token)
        if group is None:
            return argv
        if index + 1 >= len(argv):
            return argv
        subcmd = argv[index + 1]
        if subcmd in ("-h", "--help", "help"):
            return argv[:index] + ["help"]
        target = group.get(subcmd)
        if target is None:
            return argv
        return argv[:index] + target + argv[index + 2:]
    return argv


class UMain(object):
    """These methods correspond directly to the commands that can
    be invoked via the command line interface.
    """

    STATUS_OK = 0
    STATUS_ERROR = 1

    def __init__(self, argv):
        """Initialize variables of the class"""
        self.argv = argv
        self.cmdp = None
        self.local = None
        self.cli = None

    def _prepare_exec(self):
        """Prepare configuration, parse and execute the command line"""
        self.cmdp = CmdParser()
        self.cmdp.parse(self.argv)
        allow_root = self.cmdp.get("--allow-root", "GEN_OPT")
        if not (os.geteuid() or allow_root):
            Msg().err("Error: do not run as root !")
            sys.exit(self.STATUS_ERROR)

        if self.cmdp.get("--config=", "GEN_OPT"):
            conf_file = self.cmdp.get("--config=", "GEN_OPT")
            Config().getconf(conf_file)
        else:
            Config().getconf()

        if (self.cmdp.get("--debug", "GEN_OPT") or
                self.cmdp.get("-D", "GEN_OPT")):
            Config.conf['verbose_level'] = Msg.DBG
        elif (self.cmdp.get("--quiet", "GEN_OPT") or
              self.cmdp.get("-q", "GEN_OPT")):
            Config.conf['verbose_level'] = Msg.MSG
        Msg().setlevel(Config.conf['verbose_level'])

        if self.cmdp.get("--insecure", "GEN_OPT"):
            Config.conf['http_insecure'] = True

        topdir = self.cmdp.get("--repo=", "GEN_OPT")
        if topdir:  # override repo root tree
            Config.conf['topdir'] = topdir
        self.local = LocalRepository()
        if not self.local.is_repo():
            if topdir:
                Msg().err("Error: invalid udocker repository:", topdir)
                sys.exit(self.STATUS_ERROR)
            else:
                Msg().out("Info: creating repo: " + Config.conf['topdir'],
                          l=Msg.INF)
                self.local.create_repo()

        self.cli = UdockerCLI(self.local)

    def execute(self):
        """Command parsing and selection"""
        self.argv = expand_short_flags(expand_compat_argv(self.argv))
        self._prepare_exec()
        cmds = {
            "search": self.cli.do_search, "help": self.cli.do_help,
            "images": self.cli.do_images, "pull": self.cli.do_pull,
            "create": self.cli.do_create, "ps": self.cli.do_ps,
            "run": self.cli.do_run, "version": self.cli.do_version,
            "rmi": self.cli.do_rmi, "mkrepo": self.cli.do_mkrepo,
            "import": self.cli.do_import, "load": self.cli.do_load,
            "export": self.cli.do_export, "clone": self.cli.do_clone,
            "protect": self.cli.do_protect, "rm": self.cli.do_rm,
            "name": self.cli.do_name, "rmname": self.cli.do_rmname,
            "verify": self.cli.do_verify, "logout": self.cli.do_logout,
            "unprotect": self.cli.do_unprotect, "rename": self.cli.do_rename,
            "showconf": self.cli.do_showconf, "save": self.cli.do_save,
            "inspect": self.cli.do_inspect, "login": self.cli.do_login,
            "setup": self.cli.do_setup, "install": self.cli.do_install,
            "tag": self.cli.do_tag, "manifest": self.cli.do_manifest,
            "build": self.cli.do_build, "commit": self.cli.do_commit,
            "history": self.cli.do_history, "cp": self.cli.do_cp,
            "push": self.cli.do_push, "start": self.cli.do_start,
            "stop": self.cli.do_stop, "restart": self.cli.do_restart,
            "kill": self.cli.do_kill, "exec": self.cli.do_exec,
            "logs": self.cli.do_logs, "wait": self.cli.do_wait,
            "top": self.cli.do_top, "stats": self.cli.do_stats,
            "diff": self.cli.do_diff, "port": self.cli.do_port,
            "system": self.cli.do_system, "image": self.cli.do_image,
            "prune": self.cli.do_prune, "compose": self.cli.do_compose,
            "volume": self.cli.do_volume, "info": self.cli.do_info,
            "pause": self.cli.do_pause, "unpause": self.cli.do_unpause,
        }

        if ((len(self.argv) == 1) or
                self.cmdp.get("-h", "GEN_OPT") or
                self.cmdp.get("--help", "GEN_OPT")):
            return self.cli.do_help(self.cmdp)

        if (self.cmdp.get("-V", "GEN_OPT") or
                self.cmdp.get("--version", "GEN_OPT")):
            return self.cli.do_version(self.cmdp)

        command = self.cmdp.get("", "CMD")
        if command in cmds:
            if self.cmdp.get("--help", "CMD_OPT"):
                Msg().out(cmds[command].__doc__)
                return self.STATUS_OK
            if command in ["version", "showconf"]:
                return cmds[command](self.cmdp)
            if command != "install":
                self.cli.do_install(None)
            exit_status = cmds[command](self.cmdp)  # executes command
            if self.cmdp.missing_options():
                Msg().err("Error: syntax error at: %s" %
                          " ".join(self.cmdp.missing_options()))
                return self.STATUS_ERROR

            return exit_status

        Msg().err("Error: invalid command:", command, "\n")
        return self.STATUS_ERROR
