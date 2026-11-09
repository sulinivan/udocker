# -*- coding: utf-8 -*-
"""Userspace TCP port forwarding for unprivileged port publishing"""

import select
import socket
import threading

from udocker.msg import Msg


class PortForwarder(object):
    """Forward localhost TCP ports into a running container.
    Container processes share the host network stack in the F, R and S
    execution modes, so a plain userspace TCP proxy is enough and no
    privileges are required. P modes are handled by PRoot itself.
    """

    def __init__(self):
        self._listeners = []
        self._threads = []
        self._connections = []
        self._stop = threading.Event()

    def add(self, host_port, container_port):
        """Register a host port to container port mapping"""
        try:
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", int(host_port)))
            listener.listen(5)
            listener.settimeout(1.0)
        except (OSError, ValueError) as error:
            Msg().err("Error: cannot publish port", host_port, ":",
                      str(error))
            return False
        self._listeners.append(listener)
        thread = threading.Thread(target=self._accept,
                                  args=(listener, int(container_port)))
        thread.daemon = True
        self._threads.append(thread)
        return True

    def start(self):
        """Start serving all registered mappings"""
        for thread in self._threads:
            thread.start()
        return True

    def stop(self):
        """Stop serving and close all sockets"""
        self._stop.set()
        for listener in self._listeners:
            try:
                listener.close()
            except OSError:
                pass
        for (client, upstream) in list(self._connections):
            for sock in (client, upstream):
                try:
                    sock.close()
                except OSError:
                    pass

    def _accept(self, listener, container_port):
        """Accept connections and relay them to the container port"""
        while not self._stop.is_set():
            try:
                (client, dummy) = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                upstream = socket.create_connection(
                    ("127.0.0.1", container_port), timeout=2.0)
            except OSError:
                Msg().err("Error: port forward target unavailable:",
                          container_port)
                try:
                    client.close()
                except OSError:
                    pass
                continue
            self._connections.append((client, upstream))
            thread = threading.Thread(target=self._relay,
                                      args=(client, upstream))
            thread.daemon = True
            thread.start()

    def _relay(self, client, upstream):
        """Relay data in both directions until either side closes"""
        socks = [client, upstream]
        while not self._stop.is_set():
            try:
                (readable, dummy, dummy) = select.select(socks, [], [], 1.0)
            except (OSError, ValueError):
                break
            for sock in readable:
                try:
                    data = sock.recv(65536)
                except OSError:
                    data = b""
                if not data:
                    socks = []
                    break
                other = upstream if sock is client else client
                try:
                    other.sendall(data)
                except OSError:
                    socks = []
                    break
            if not socks:
                break
        for sock in (client, upstream):
            try:
                sock.close()
            except OSError:
                pass
