# -*- coding: utf-8 -*-
"""Environment helpers for invoking runc/crun without root"""

import os


RUN_ID_PREFIX = "udocker-"


def runc_container_id(container_id):
    """The runc container id used by udocker for a container"""
    return RUN_ID_PREFIX + str(container_id)


def runtime_env(topdir):
    """Return an environment with a writable XDG_RUNTIME_DIR.
    runc needs it even for rootless containers, and batch/HPC hosts
    often have it unset or read-only.
    """
    env = dict(os.environ)
    xdg = env.get("XDG_RUNTIME_DIR", "")
    if xdg and os.path.isdir(xdg) and os.access(xdg, os.W_OK):
        return env
    fallback = os.path.join(str(topdir), "runc-runtime")
    try:
        if not os.path.isdir(fallback):
            os.makedirs(fallback)
        os.chmod(fallback, 0o700)
    except OSError:
        pass
    env["XDG_RUNTIME_DIR"] = fallback
    return env
