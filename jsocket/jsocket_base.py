""" @namespace jsocket_base
    Contains JsonSocket, JsonServer and JsonClient implementations (json object message passing server and client).
"""
__author__   = "Christopher Piekarski"
__email__    = "chris@cpiekarski.com"
__copyright__= """
    Copyright (C) 2011 by
    Christopher Piekarski <chris@cpiekarski.com>

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""
__version__  = "1.0.3"

import json
import socket
import struct
import logging
import time

logger = logging.getLogger("jsocket")


class JsonSocket:
    """Lightweight JSON-over-TCP socket wrapper with length-prefixed framing."""

    def __init__(self, address='127.0.0.1', port=5489, timeout=2.0):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.conn = self.socket
        self._timeout = timeout
        self._address = address
        self._port = port
        # Ensure the primary socket respects timeout for accept/connect operations
        self.socket.settimeout(self._timeout)

    def send_obj(self, obj):
        """Send a JSON-serializable object over the connection."""
        msg = json.dumps(obj, ensure_ascii=False)
        if self.socket:
            payload = msg.encode('utf-8')
            frmt = f"={len(payload)}s"
            packed_msg = struct.pack(frmt, payload)
            packed_hdr = struct.pack('!I', len(packed_msg))
            self._send(packed_hdr)
            self._send(packed_msg)

    def _send(self, msg):
        """Send all bytes in `msg` to the peer."""
        sent = 0
        while sent < len(msg):
            sent += self.conn.send(msg[sent:])

    def _read(self, size):
        """Read exactly `size` bytes from the peer or raise on disconnect."""
        data = b''
        while len(data) < size:
            data_tmp = self.conn.recv(size - len(data))
            data += data_tmp
            if data_tmp == b'':
                raise RuntimeError("socket connection broken")
        return data

    def _msg_length(self):
        """Read and unpack the 4-byte big-endian length header."""
        d = self._read(4)
        s = struct.unpack('!I', d)
        return s[0]

    def read_obj(self):
        """Read a full message and decode it as JSON, returning a Python object."""
        size = self._msg_length()
        data = self._read(size)
        frmt = f"={size}s"
        msg = struct.unpack(frmt, data)
        return json.loads(msg[0].decode('utf-8'))

    def close(self):
        """Close active connection and the listening socket if open."""
        logger.debug("closing all connections")
        self._close_connection()
        self._close_socket()

    def _close_socket(self):
        """Best-effort shutdown and close of the main socket."""
        logger.debug("closing main socket")
        try:
            if self.socket and self.socket.fileno() != -1:
                try:
                    self.socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    self.socket.close()
                except OSError:
                    pass
        except OSError:
            pass

    def _close_connection(self):
        """Best-effort shutdown and close of the accepted connection socket."""
        logger.debug("closing the connection socket")
        try:
            if self.conn and self.conn is not self.socket and self.conn.fileno() != -1:
                try:
                    self.conn.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    self.conn.close()
                except OSError:
                    pass
        except OSError:
            pass

    def _get_timeout(self):
        """Get the current socket timeout in seconds."""
        return self._timeout

    def _set_timeout(self, timeout):
        """Set the socket timeout in seconds and apply to the main socket."""
        self._timeout = timeout
        self.socket.settimeout(timeout)

    def _get_address(self):
        """Return the configured bind address."""
        return self._address

    def _set_address(self, address):
        """No-op: address is read-only after initialization."""
        pass

    def _get_port(self):
        """Return the configured bind port."""
        return self._port

    def _set_port(self, port):
        """No-op: port is read-only after initialization."""
        pass

    timeout = property(_get_timeout, _set_timeout, doc='Get/set the socket timeout')
    address = property(_get_address, _set_address, doc='read only property socket address')
    port = property(_get_port, _set_port, doc='read only property socket port')


class JsonServer(JsonSocket):
    """Server socket that accepts one connection at a time."""

    def __init__(self, address='127.0.0.1', port=5489):
        super().__init__(address, port)
        self._bind()

    def _bind(self):
        self.socket.bind((self.address, self.port))

    def _listen(self):
        self.socket.listen(5)

    def _accept(self):
        return self.socket.accept()

    def accept_connection(self):
        """Listen and accept a single client connection; set timeout accordingly."""
        self._listen()
        self.conn, addr = self._accept()
        self.conn.settimeout(self.timeout)
        logger.debug(
            "connection accepted, conn socket (%s,%d,%s)", addr[0], addr[1], str(self.conn.gettimeout())
        )

    def _reset_connection_ref(self):
        """Reset the server's connection reference to the listening socket."""
        self.conn = self.socket

    def _is_connected(self):
        try:
            return (self.conn is not None) and (self.conn is not self.socket) and (self.conn.fileno() != -1)
        except (OSError, AttributeError):
            return False

    connected = property(_is_connected, doc="True if server has an active client connection")


class JsonClient(JsonSocket):
    """Client socket for connecting to a JsonServer and exchanging JSON messages."""

    def __init__(self, address='127.0.0.1', port=5489):
        super().__init__(address, port)

    def connect(self):
        """Attempt to connect to the server up to 10 times with backoff."""
        for _ in range(10):
            try:
                self.socket.connect((self.address, self.port))
            except socket.error as msg:
                logger.error("SockThread Error: %s", msg)
                time.sleep(3)
                continue
            logger.info("...Socket Connected")
            return True
        return False
