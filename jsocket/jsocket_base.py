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


def _socket_fileno(sock):
    try:
        return sock.fileno()
    except Exception:  # pylint: disable=broad-exception-caught
        return None


class JsonSocket:
    """Lightweight JSON-over-TCP socket wrapper."""

    def __init__(self, address='127.0.0.1', port=5489, timeout=60.0):
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
            payload = '<message>{}</message>'.format(msg)
            self._send(payload)

    def _send(self, msg):
        """Send all bytes in `msg` over the connection."""
        msg = msg.encode()
        sent_bytes = 0
        while sent_bytes < len(msg):
            sent_bytes += self.conn.send(msg[sent_bytes:])

    def read_obj(self):
        """Recv until </message> end marker received."""
        buf = b''
        while True:
            buf += self.conn.recv(1024)
            # close on 0 bytes (close marker)
            if len(buf) == 0:
                self.close()
                break
            if buf.find(b'<message>') == 0 and buf.find(b'</message>') == len(buf)-10:
                buf = buf.replace(b'<message>', b'')
                buf = buf.replace(b'</message>', b'')
                return json.loads(buf)

    def close(self):
        """Close active connection and the listening socket if open."""
        logger.debug(
            "Closing sockets (socket fd=%s, conn fd=%s)",
            _socket_fileno(self.socket),
            _socket_fileno(self.conn),
        )
        self._close_connection()
        self._close_socket()

    def _close_socket(self):
        """Best-effort shutdown and close of the main socket."""
        logger.debug("closing main socket (fd=%s)", _socket_fileno(self.socket))
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
        logger.debug("closing connection socket (fd=%s)", _socket_fileno(self.conn))
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

    def _set_address(self, _address):
        """No-op: address is read-only after initialization."""
        return None

    def _get_port(self):
        """Return the configured bind port."""
        return self._port

    def _set_port(self, _port):
        """No-op: port is read-only after initialization."""
        return None

    timeout = property(_get_timeout, _set_timeout, doc='Get/set the socket timeout')
    address = property(_get_address, _set_address, doc='read only property socket address')
    port = property(_get_port, _set_port, doc='read only property socket port')


class JsonServer(JsonSocket):
    """Server socket that accepts one connection at a time."""

    def __init__(self, address='127.0.0.1', port=5489):
        super().__init__(address, port)
        self._bind()

    def _bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.address, self.port))
        self.socket.listen(1)

    def _accept(self):
        return self.socket.accept()

    def accept_connection(self):
        """Listen and accept a single client connection; set timeout accordingly."""
        self.conn, addr = self._accept()
        self.conn.settimeout(self.timeout)
        logger.debug(
            "connection accepted, conn socket (%s,%d,%s)", addr[0], addr[1], str(self.conn.gettimeout())
        )

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
        for attempt in range(1, 11):
            try:
                logger.debug("connect attempt %d to %s:%s", attempt, self.address, self.port)
                self.socket.connect((self.address, self.port))
                logger.info("Socket connected...")
                return True
            except Exception as msg:
                logger.error("SockThread Error: %s", msg)
                # Recreate the socket to avoid retrying on a potentially bad fd.
                self._close_socket()
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(self._timeout)
                self.conn = self.socket
                logger.debug("Recreated socket for retry %d to %s:%s", attempt, self.address, self.port)
                time.sleep(3)
        return False
