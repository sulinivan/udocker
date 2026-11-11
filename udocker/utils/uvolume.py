# -*- coding: utf-8 -*-
"""Manipulate volume bindings host_path:container_path[:mode]"""

# docker volume modes that may follow the container path (":ro", ":rw,Z")
VOLUME_MODES = ("ro", "rw", "z", "Z", "nocopy", "cached", "delegated",
                "consistent", "shared", "slave", "private", "rshared",
                "rslave", "rprivate")


class Uvolume(object):
    """Manipulate volumes"""

    def __init__(self, volume=""):
        self.volume = volume
        self.mode = ""

    @property
    def readonly(self):
        """True when the binding asks for a read-only mount"""
        return "ro" in self.mode.lower().split(",")

    def cleanpath(self, path):
        """Remove duplicate and trailing slashes"""
        clean_path = ""
        p_char = ''
        for char in str(path):
            if not clean_path:
                clean_path = char
            elif not (char == p_char and char == '/'):
                clean_path += char

            p_char = char

        if clean_path == "/":
            return clean_path

        return clean_path.rstrip('/')

    def _strip_mode(self, cont_dir, field):
        """Trailing field is a mode only when every part is a known mode"""
        parts = [part.strip() for part in field.split(",")]
        if parts and all(part in VOLUME_MODES for part in parts):
            self.mode = field
            return cont_dir
        return cont_dir + ":" + field

    def split(self):
        """Split host_path:container_path[:mode] into a (host, container) pair"""
        try:
            (host_dir, cont_dir, mode) = self.volume.split(":", 2)
            cont_dir = self._strip_mode(cont_dir, mode)
            if not cont_dir:
                cont_dir = host_dir
        except ValueError:
            try:
                (host_dir, cont_dir) = self.volume.split(":", 1)
                if not cont_dir:
                    cont_dir = host_dir
            except ValueError:
                host_dir = self.volume
                cont_dir = self.volume

        return (self.cleanpath(host_dir), self.cleanpath(cont_dir))
