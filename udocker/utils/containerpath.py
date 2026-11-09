# -*- coding: utf-8 -*-
"""Resolve paths inside a container ROOT without escaping it"""

import os


def container_realpath(container_root, path, follow_final=True):
    """Resolve a path inside the container ROOT without escaping it.
    Absolute symlinks are interpreted relative to the container root,
    as they are when the container executes. The final path component
    is followed only if follow_final is True. Returns None when the
    resolved path would escape the container root.
    """
    root = os.path.realpath(container_root)
    parts = [part for part in str(path).split("/") if part not in ("", ".")]
    current = root
    hops = 0
    while parts:
        part = parts.pop(0)
        if not parts and not follow_final:
            current = os.path.join(current, part)
            break
        if part == "..":
            parent = os.path.dirname(current)
            if parent != root and not parent.startswith(root + os.sep):
                return None
            current = parent
            continue
        candidate = os.path.join(current, part)
        if os.path.islink(candidate):
            hops += 1
            if hops > 40:
                return None
            link = os.readlink(candidate)
            if link.startswith("/"):
                current = root
            parts = [item for item in link.split("/")
                     if item not in ("", ".")] + parts
            continue
        current = candidate
    current = os.path.normpath(current)
    if current != root and not current.startswith(root + os.sep):
        return None
    if not follow_final:
        return current
    real = os.path.realpath(current)
    if real != root and not real.startswith(root + os.sep):
        return None
    return real
