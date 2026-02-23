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
import json
import socket
import struct
import logging
import time
import zlib

from ._version import __version__

logger = logging.getLogger("jsocket")

FRAME_MAGIC = b"JSN1"
FRAME_HEADER_FMT = "!4sII"
FRAME_HEADER_SIZE = struct.calcsize(FRAME_HEADER_FMT)
DEFAULT_MAX_MESSAGE_SIZE = 10 * 1024 * 1024


class FramingError(RuntimeError):
    """Raised when a message fails framing or integrity checks."""


def _socket_fileno(sock):
    try:
        return sock.fileno()
    except Exception:  # pylint: disable=broad-exception-caught
        return None


class JsonSocket:
    """Lightweight JSON-over-TCP socket wrapper with length-prefixed framing."""

    def __init__(
        self,
        address='127.0.0.1',
        port=5489,
        timeout=2.0,
        max_message_size=DEFAULT_MAX_MESSAGE_SIZE,
        accept_timeout=None,
        recv_timeout=None,
        create_socket=True,
    ):
        self.socket = None
        self.conn = None
        self._timeout = timeout
        self._accept_timeout = timeout if accept_timeout is None else accept_timeout
        self._recv_timeout = timeout if recv_timeout is None else recv_timeout
        self._address = address
        self._port = port
        self._max_message_size = None
        self.max_message_size = max_message_size
        self._last_client_addr = None
        self._is_server = False
        self._is_listening = False
        self._last_read_size = None
        self._last_send_size = None
        if create_socket:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.conn = self.socket
            # Primary socket timeout (accept for servers; connect/read for clients).
            self.socket.settimeout(self._accept_timeout)

    def send_obj(self, obj):
        """Send a JSON-serializable object over the connection."""
        msg = json.dumps(obj, ensure_ascii=False)
        if self.socket:
            payload = msg.encode('utf-8')
            self._last_send_size = len(payload)
            if self._max_message_size is not None and len(payload) > self._max_message_size:
                raise ValueError(f"message exceeds max_message_size ({len(payload)} > {self._max_message_size})")
            checksum = zlib.crc32(payload) & 0xFFFFFFFF
            packed_hdr = struct.pack(FRAME_HEADER_FMT, FRAME_MAGIC, len(payload), checksum)
            self._send(packed_hdr)
            self._send(payload)

    def _send(self, msg):
        """Send all bytes in `msg` to the peer."""
        sent = 0
        while sent < len(msg):
            try:
                chunk = self.conn.send(msg[sent:])
            except OSError as e:
                self._close_connection()
                raise RuntimeError("socket connection broken") from e
            if chunk == 0:
                self._close_connection()
                raise RuntimeError("socket connection broken")
            sent += chunk

    def _read(self, size, allow_timeout=False):
        """Read exactly `size` bytes from the peer or raise on disconnect."""
        data = b''
        while len(data) < size:
            try:
                data_tmp = self.conn.recv(size - len(data))
            except socket.timeout:
                if allow_timeout and not data:
                    raise
                self._close_connection()
                raise FramingError("socket read timeout during message")
            if data_tmp == b'':
                self._close_connection()
                raise RuntimeError("socket connection broken")
            data += data_tmp
        return data

    def _read_header(self):
        """Read and unpack the framing header."""
        header = self._read(FRAME_HEADER_SIZE, allow_timeout=True)
        magic, size, checksum = struct.unpack(FRAME_HEADER_FMT, header)
        if magic != FRAME_MAGIC:
            self._close_connection()
            raise FramingError("invalid message header magic")
        if self._max_message_size is not None and size > self._max_message_size:
            self._close_connection()
            raise FramingError(f"message length {size} exceeds max_message_size {self._max_message_size}")
        return size, checksum

    def read_obj(self):
        """Read a full message and decode it as JSON, returning a Python object."""
        size, checksum = self._read_header()
        self._last_read_size = size
        data = self._read(size)
        actual = zlib.crc32(data) & 0xFFFFFFFF
        if actual != checksum:
            self._close_connection()
            raise FramingError("message checksum mismatch")
        try:
            decoded = data.decode('utf-8')
        except UnicodeDecodeError as e:
            self._close_connection()
            raise FramingError("invalid UTF-8 payload") from e
        try:
            return json.loads(decoded)
        except json.JSONDecodeError as e:
            self._close_connection()
            raise FramingError("invalid JSON payload") from e

    def close(self):
        """Close active connection and the listening socket if open."""
        logger.debug(
            "closing sockets (socket fd=%s, conn fd=%s)",
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
        self._is_listening = False

    def _close_connection(self):
        """Best-effort shutdown and close of the connection socket."""
        logger.debug("closing connection socket (fd=%s)", _socket_fileno(self.conn))
        try:
            if self.conn and self.conn.fileno() != -1:
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
        return getattr(self, "_timeout", None)

    def _set_timeout(self, timeout):
        """Set the socket timeout in seconds and apply to the main socket."""
        self._timeout = timeout
        self._accept_timeout = timeout
        self._recv_timeout = timeout
        sock = getattr(self, "socket", None)
        if sock is not None:
            sock.settimeout(self._accept_timeout)
        conn = getattr(self, "conn", None)
        if conn is not None:
            if getattr(self, "_is_server", False):
                if conn is not sock:
                    conn.settimeout(self._recv_timeout)
            else:
                conn.settimeout(self._recv_timeout)

    def _get_accept_timeout(self):
        """Get the listening/accept timeout in seconds."""
        return getattr(self, "_accept_timeout", getattr(self, "_timeout", None))

    def _set_accept_timeout(self, timeout):
        """Set the listening/accept timeout in seconds."""
        self._accept_timeout = timeout
        sock = getattr(self, "socket", None)
        if sock is not None:
            sock.settimeout(timeout)

    def _get_recv_timeout(self):
        """Get the connection recv timeout in seconds."""
        return getattr(self, "_recv_timeout", getattr(self, "_timeout", None))

    def _set_recv_timeout(self, timeout):
        """Set the connection recv timeout in seconds."""
        self._recv_timeout = timeout
        conn = getattr(self, "conn", None)
        sock = getattr(self, "socket", None)
        if conn is not None:
            if getattr(self, "_is_server", False) and conn is sock:
                return
            conn.settimeout(timeout)

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

    def _get_max_message_size(self):
        """Get the maximum allowed message size in bytes."""
        return self._max_message_size

    def _set_max_message_size(self, size):
        """Set the maximum allowed message size in bytes."""
        if size is None:
            self._max_message_size = None
            return
        size = int(size)
        if size <= 0:
            raise ValueError("max_message_size must be positive")
        self._max_message_size = size

    timeout = property(_get_timeout, _set_timeout, doc='Get/set accept/recv timeout together')
    accept_timeout = property(_get_accept_timeout, _set_accept_timeout, doc='Get/set accept timeout')
    recv_timeout = property(_get_recv_timeout, _set_recv_timeout, doc='Get/set recv timeout')
    address = property(_get_address, _set_address, doc='read only property socket address')
    port = property(_get_port, _set_port, doc='read only property socket port')
    max_message_size = property(_get_max_message_size, _set_max_message_size, doc='Get/set max message size in bytes')


class JsonServer(JsonSocket):
    """Server socket that accepts one connection at a time."""

    def __init__(self, address='127.0.0.1', port=5489, timeout=2.0, accept_timeout=None, recv_timeout=None):
        super().__init__(
            address,
            port,
            timeout=timeout,
            accept_timeout=accept_timeout,
            recv_timeout=recv_timeout,
        )
        self._is_server = True
        self._bind()

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

    def _bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.address, self.port))
        self._is_listening = False

    def _listen(self):
        if self._is_listening:
            return
        self.socket.listen(5)
        self._is_listening = True

    def _accept(self):
        return self.socket.accept()

    def accept_connection(self):
        """Listen and accept a single client connection; set timeout accordingly."""
        self._listen()
        self.conn, addr = self._accept()
        self._last_client_addr = addr
        self.conn.settimeout(self.recv_timeout)
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

    def __init__(self, address='127.0.0.1', port=5489, timeout=2.0, recv_timeout=None):
        super().__init__(address, port, timeout=timeout, recv_timeout=recv_timeout)
        if self.socket is not None:
            self.socket.settimeout(self._recv_timeout)

    def connect(self):
        """Attempt to connect to the server up to 10 times with backoff."""
        def _recreate_socket():
            self._close_socket()
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self._recv_timeout)
            self.conn = self.socket

        for attempt in range(1, 11):
            sock = getattr(self, "socket", None)
            needs_fresh_socket = sock is None
            if not needs_fresh_socket:
                try:
                    needs_fresh_socket = sock.fileno() == -1
                except OSError:
                    needs_fresh_socket = True
            if needs_fresh_socket:
                _recreate_socket()
                logger.debug("created fresh socket before connect attempt %d to %s:%s", attempt, self.address, self.port)
            try:
                logger.debug("connect attempt %d to %s:%s", attempt, self.address, self.port)
                self.socket.connect((self.address, self.port))
            except socket.error as msg:
                logger.error("SockThread Error: %s", msg)
                # Recreate the socket to avoid retrying on a potentially bad fd.
                _recreate_socket()
                logger.debug("recreated socket for retry %d to %s:%s", attempt, self.address, self.port)
                time.sleep(3)
                continue
            logger.info("...Socket Connected")
            # Switch to recv_timeout after successful connection
            self.socket.settimeout(self._recv_timeout)
            return True
        return False
