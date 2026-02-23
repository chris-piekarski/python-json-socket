""" @namespace tserver
    Contains ThreadedServer, ServerFactoryThread and ServerFactory implementations. 
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
import threading
import socket
import select
import time
import logging
import abc
from typing import Optional
from contextlib import contextmanager

from jsocket import jsocket_base
from ._version import __version__

logger = logging.getLogger("jsocket.tserver")


def _response_summary(resp_obj) -> str:
    if isinstance(resp_obj, dict):
        return f"type=dict keys={len(resp_obj)}"
    if isinstance(resp_obj, (list, tuple)):
        return f"type={type(resp_obj).__name__} items={len(resp_obj)}"
    return f"type={type(resp_obj).__name__}"


def _format_client_id(addr) -> str:
    try:
        host, port = addr[0], addr[1]
        if ":" in host:
            return f"[{host}]:{port}"
        return f"{host}:{port}"
    except Exception:  # pylint: disable=broad-exception-caught
        return "unknown"


def _now_ts() -> float:
    return time.time()


def _new_failure_counts() -> dict:
    return {
        "timeout": 0,
        "bad_write": 0,
        "bad_crc": 0,
        "bad_header": 0,
        "oversize": 0,
        "invalid_utf8": 0,
        "invalid_json": 0,
        "handler": 0,
        "framing": 0,
    }


def _new_client_stats(client_id: str) -> dict:
    return {
        "client_id": client_id,
        "connected": False,
        "connects": 0,
        "disconnects": 0,
        "messages_in": 0,
        "messages_out": 0,
        "bytes_in": 0,
        "bytes_out": 0,
        "total_connected_duration": 0.0,
        "failures": _new_failure_counts(),
        "last_connect_ts": None,
        "last_disconnect_ts": None,
        "last_message_ts": None,
        "_connected_since": None,
    }


def _clone_client_stats(stats: dict) -> dict:
    return {
        **stats,
        "failures": dict(stats.get("failures", {})),
    }


def _format_client_stats(stats: dict, now_mono: float) -> dict:
    snapshot = _clone_client_stats(stats)
    messages_in = snapshot.get("messages_in", 0) or 0
    messages_out = snapshot.get("messages_out", 0) or 0
    bytes_in = snapshot.get("bytes_in", 0) or 0
    bytes_out = snapshot.get("bytes_out", 0) or 0
    snapshot["avg_payload_in"] = bytes_in / messages_in if messages_in else 0.0
    snapshot["avg_payload_out"] = bytes_out / messages_out if messages_out else 0.0
    connected = snapshot.get("connected") is True
    connected_since = snapshot.get("_connected_since")
    current_duration = now_mono - connected_since if (connected and connected_since) else 0.0
    snapshot["connected_duration"] = current_duration
    total = snapshot.get("total_connected_duration", 0.0) or 0.0
    snapshot["total_connected_duration"] = total + current_duration if connected else total
    snapshot.pop("_connected_since", None)
    return snapshot


@contextmanager
def _stats_guard(obj):
    lock = getattr(obj, "_stats_lock", None)
    if lock is None:
        yield
    else:
        with lock:
            yield


def _ensure_stats_state(obj):
    if not hasattr(obj, "_client_stats"):
        obj._client_stats = {}
    if not hasattr(obj, "_active_client_id"):
        obj._active_client_id = None


def _get_active_client_id(obj):
    client_id = getattr(obj, "_active_client_id", None)
    if client_id:
        return client_id
    return getattr(obj, "_client_id", None)


def _get_or_create_stats(obj, client_id: str) -> dict:
    _ensure_stats_state(obj)
    stats = obj._client_stats.get(client_id)
    if stats is None:
        stats = _new_client_stats(client_id)
        obj._client_stats[client_id] = stats
    return stats


def _note_connect(obj, client_id: str) -> None:
    if not client_id:
        client_id = "unknown"
    with _stats_guard(obj):
        stats = _get_or_create_stats(obj, client_id)
        stats["connected"] = True
        stats["connects"] += 1
        stats["last_connect_ts"] = _now_ts()
        if stats.get("_connected_since") is None:
            stats["_connected_since"] = time.monotonic()
        obj._active_client_id = client_id


def _note_disconnect(obj) -> None:
    client_id = _get_active_client_id(obj)
    if not client_id:
        return
    with _stats_guard(obj):
        stats = _get_or_create_stats(obj, client_id)
        if not stats.get("connected"):
            return
        stats["connected"] = False
        stats["disconnects"] += 1
        stats["last_disconnect_ts"] = _now_ts()
        connected_since = stats.get("_connected_since")
        if connected_since is not None:
            duration = time.monotonic() - connected_since
            stats["total_connected_duration"] = (stats.get("total_connected_duration") or 0.0) + duration
        stats["_connected_since"] = None
        obj._active_client_id = None


def _note_message_in(obj, size) -> None:
    client_id = _get_active_client_id(obj)
    if not client_id:
        return
    msg_size = int(size) if size is not None else 0
    with _stats_guard(obj):
        stats = _get_or_create_stats(obj, client_id)
        stats["messages_in"] += 1
        stats["bytes_in"] += msg_size
        stats["last_message_ts"] = _now_ts()


def _note_message_out(obj, size) -> None:
    client_id = _get_active_client_id(obj)
    if not client_id:
        return
    msg_size = int(size) if size is not None else 0
    with _stats_guard(obj):
        stats = _get_or_create_stats(obj, client_id)
        stats["messages_out"] += 1
        stats["bytes_out"] += msg_size
        stats["last_message_ts"] = _now_ts()


def _note_failure(obj, kind: str) -> None:
    client_id = _get_active_client_id(obj)
    if not client_id:
        return
    with _stats_guard(obj):
        stats = _get_or_create_stats(obj, client_id)
        failures = stats.get("failures")
        if failures is None:
            failures = _new_failure_counts()
            stats["failures"] = failures
        failures[kind] = failures.get(kind, 0) + 1


def _framing_failure_kind(error: Exception) -> str:
    msg = str(error)
    if "invalid message header magic" in msg:
        return "bad_header"
    if "checksum mismatch" in msg:
        return "bad_crc"
    if "exceeds max_message_size" in msg:
        return "oversize"
    if "invalid UTF-8 payload" in msg:
        return "invalid_utf8"
    if "invalid JSON payload" in msg:
        return "invalid_json"
    if "socket read timeout" in msg:
        return "timeout"
    return "framing"


def _note_framing_failure(obj, error: Exception) -> None:
    _note_failure(obj, _framing_failure_kind(error))


def _max_ts(left, right):
    if left is None:
        return right
    if right is None:
        return left
    return right if right > left else left


def _normalize_client_id(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value.strip() or None
    return str(value)


def _extract_client_id(obj):
    if not isinstance(obj, dict):
        return None
    if "client" in obj:
        return _normalize_client_id(obj.get("client"))
    if "client_id" in obj:
        return _normalize_client_id(obj.get("client_id"))
    return None


def _set_client_identity(obj, new_client_id: str) -> None:
    if not new_client_id:
        return
    current_id = _get_active_client_id(obj)
    if current_id == new_client_id:
        return
    _ensure_stats_state(obj)
    with _stats_guard(obj):
        existing = obj._client_stats.get(current_id) if current_id else None
        if existing is None:
            existing = _new_client_stats(new_client_id)
        existing["client_id"] = new_client_id
        target = obj._client_stats.get(new_client_id)
        if target is None:
            obj._client_stats[new_client_id] = existing
        else:
            obj._client_stats[new_client_id] = _merge_client_stats(target, existing)
        if current_id and current_id != new_client_id:
            obj._client_stats.pop(current_id, None)
        obj._active_client_id = new_client_id
        if hasattr(obj, "_client_id"):
            obj._client_id = new_client_id


def _merge_client_stats(dest: dict, src: dict) -> dict:
    if not dest:
        return _clone_client_stats(src)
    dest.setdefault("client_id", src.get("client_id"))
    for key in ("connects", "disconnects", "messages_in", "messages_out", "bytes_in", "bytes_out"):
        dest[key] = dest.get(key, 0) + (src.get(key, 0) or 0)
    dest["total_connected_duration"] = (dest.get("total_connected_duration") or 0.0) + (
        src.get("total_connected_duration") or 0.0
    )
    dest_failures = dest.get("failures")
    if dest_failures is None:
        dest_failures = _new_failure_counts()
        dest["failures"] = dest_failures
    for key, value in (src.get("failures") or {}).items():
        dest_failures[key] = dest_failures.get(key, 0) + (value or 0)
    dest["last_connect_ts"] = _max_ts(dest.get("last_connect_ts"), src.get("last_connect_ts"))
    dest["last_disconnect_ts"] = _max_ts(dest.get("last_disconnect_ts"), src.get("last_disconnect_ts"))
    dest["last_message_ts"] = _max_ts(dest.get("last_message_ts"), src.get("last_message_ts"))
    if src.get("connected"):
        dest["connected"] = True
        src_since = src.get("_connected_since")
        dest_since = dest.get("_connected_since")
        if dest_since is None or (src_since is not None and src_since < dest_since):
            dest["_connected_since"] = src_since
    return dest


def _rekey_stats_map(stats_map: dict) -> dict:
    if not stats_map:
        return {}
    rekeyed = {}
    for client_id, stats in stats_map.items():
        key = stats.get("client_id") or client_id
        if key in rekeyed:
            rekeyed[key] = _merge_client_stats(rekeyed[key], stats)
        else:
            rekeyed[key] = _clone_client_stats(stats)
            rekeyed[key]["client_id"] = key
    return rekeyed


def _stats_from_thread(thread) -> dict:
    if hasattr(thread, "_get_client_stats_internal"):
        return thread._get_client_stats_internal()
    client_id = getattr(thread, "_client_id", None)
    if not client_id:
        name = getattr(thread, "name", None)
        if name:
            client_id = f"thread-{name}"
    if not client_id:
        return {}
    stats = _new_client_stats(client_id)
    stats["connected"] = True
    stats["connects"] = 1
    started_at = getattr(thread, "_client_started_at", None)
    if started_at is not None:
        stats["_connected_since"] = started_at
    return {client_id: stats}


class ThreadedServer(threading.Thread, jsocket_base.JsonServer, metaclass=abc.ABCMeta):
    """Single-threaded server that accepts one connection and processes messages in its thread."""

    def __init__(self, **kwargs):
        threading.Thread.__init__(self)
        jsocket_base.JsonServer.__init__(self, **kwargs)
        self._is_alive = False
        self._stats_lock = threading.Lock()
        self._client_started_at = None
        self._client_id = None
        self._client_stats = {}
        self._active_client_id = None
        self._wakeup_r = None
        self._wakeup_w = None
        self._init_wakeup()

    def _init_wakeup(self):
        """Create a wakeup socketpair to interrupt blocking accept."""
        try:
            self._wakeup_r, self._wakeup_w = socket.socketpair()
            self._wakeup_r.setblocking(False)
            self._wakeup_w.setblocking(False)
            return
        except (AttributeError, OSError):
            pass
        # Fallback: create a loopback TCP pair
        listener = None
        writer = None
        reader = None
        try:
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            writer = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            writer.connect(listener.getsockname())
            reader, _ = listener.accept()
            reader.setblocking(False)
            writer.setblocking(False)
            self._wakeup_r, self._wakeup_w = reader, writer
        except OSError:
            for sock in (reader, writer):
                if sock is None:
                    continue
                try:
                    sock.close()
                except OSError:
                    pass
            self._wakeup_r, self._wakeup_w = None, None
        finally:
            if listener is not None:
                try:
                    listener.close()
                except OSError:
                    pass

    def _signal_wakeup(self):
        """Wake the accept loop if it is blocked."""
        sock = getattr(self, "_wakeup_w", None)
        if sock is None:
            return
        try:
            sock.send(b"\x00")
        except OSError:
            pass

    def _drain_wakeup(self):
        sock = getattr(self, "_wakeup_r", None)
        if sock is None:
            return
        try:
            while True:
                if not sock.recv(1024):
                    break
        except (BlockingIOError, OSError):
            pass

    def _close_wakeup(self):
        for sock in (getattr(self, "_wakeup_r", None), getattr(self, "_wakeup_w", None)):
            if sock is None:
                continue
            try:
                sock.close()
            except OSError:
                pass
        self._wakeup_r = None
        self._wakeup_w = None

    def _wait_for_accept(self) -> bool:
        """Block until a client can be accepted or a wakeup is signaled."""
        sock = getattr(self, "socket", None)
        wake = getattr(self, "_wakeup_r", None)
        if sock is None or wake is None:
            return True
        try:
            if hasattr(self, "_listen"):
                self._listen()
        except OSError as e:
            logger.debug("listen error on %s:%s: %s", self.address, self.port, e)
            return False
        while getattr(self, "_is_alive", False):
            try:
                readable, _, _ = select.select([sock, wake], [], [], None)
            except (OSError, ValueError) as e:
                logger.debug("select error on %s:%s: %s", self.address, self.port, e)
                return False
            if wake in readable:
                self._drain_wakeup()
                return False
            if sock in readable:
                return True
        return False

    @abc.abstractmethod
    def _process_message(self, obj) -> Optional[dict]:
        """Pure Virtual Method

        This method is called every time a JSON object is received from a client

        @param obj JSON "key: value" object received from client
        @retval None or a response object
        """
        # Return None in the base class to satisfy linters; subclasses should override.
        return None

    def _record_client_start(self):
        addr = getattr(self, "_last_client_addr", None)
        if addr is None:
            try:
                addr = self.conn.getpeername()
            except OSError:
                addr = None
        client_id = _format_client_id(addr)
        with self._stats_lock:
            self._client_started_at = time.monotonic()
            self._client_id = client_id
        _note_connect(self, client_id)

    def _clear_client_stats(self):
        with self._stats_lock:
            self._client_started_at = None
            self._client_id = None
            self._active_client_id = None

    def get_client_stats(self) -> dict:
        """Return per-client stats including connects, messages, failures, and timestamps."""
        _ensure_stats_state(self)
        with _stats_guard(self):
            stats_map = {cid: _clone_client_stats(stats) for cid, stats in self._client_stats.items()}
        stats_map = _rekey_stats_map(stats_map)
        now = time.monotonic()
        clients = {cid: _format_client_stats(stats, now) for cid, stats in stats_map.items()}
        connected = sum(1 for stats in clients.values() if stats.get("connected"))
        return {"connected_clients": connected, "clients": clients}

    def _accept_client(self) -> bool:
        """Accept an incoming connection; return True when a client connects."""
        if not self._wait_for_accept():
            return False
        try:
            self.accept_connection()
        except socket.timeout as e:
            logger.debug("accept timeout on %s:%s: %s", self.address, self.port, e)
            return False
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Avoid noisy error logs during normal shutdown/sequencing
            if self._is_alive:
                logger.debug("accept error on %s:%s: %s", self.address, self.port, e)
                return False
            logger.debug("server stopping; accept loop exiting (%s:%s)", self.address, self.port)
            self._is_alive = False
            return False
        self._record_client_start()
        return True

    def _handle_client_messages(self):
        """Read, process, and respond to client messages until disconnect."""
        while self._is_alive:
            try:
                obj = self.read_obj()
            except socket.timeout as e:
                logger.debug("read timeout waiting for client data: %s", e)
                _note_failure(self, "timeout")
                continue
            except jsocket_base.FramingError as e:
                _note_framing_failure(self, e)
                logger.debug("framing error (%s): %s", type(e).__name__, e)
                self._close_connection()
                break
            except Exception as e:  # pylint: disable=broad-exception-caught
                # Treat client disconnects as normal; keep logs at info/debug
                msg = str(e)
                if isinstance(e, RuntimeError) and 'socket connection broken' in msg:
                    logger.info("client connection broken, closing connection")
                else:
                    logger.debug("handler error (%s): %s", type(e).__name__, e)
                    _note_failure(self, "handler")
                self._close_connection()
                break
            client_id = _extract_client_id(obj)
            if client_id:
                _set_client_identity(self, client_id)
            _note_message_in(self, getattr(self, "_last_read_size", None))
            try:
                resp_obj = self._process_message(obj)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.debug("handler error (%s): %s", type(e).__name__, e)
                _note_failure(self, "handler")
                self._close_connection()
                break
            if resp_obj is not None:
                logger.debug("sending response (%s)", _response_summary(resp_obj))
                try:
                    self.send_obj(resp_obj)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    msg = str(e)
                    if isinstance(e, RuntimeError) and 'socket connection broken' in msg:
                        logger.info("client connection broken, closing connection")
                    else:
                        logger.debug("send error (%s): %s", type(e).__name__, e)
                    _note_failure(self, "bad_write")
                    self._close_connection()
                    break
                _note_message_out(self, getattr(self, "_last_send_size", None))
        _note_disconnect(self)
        self._clear_client_stats()

    def run(self):
        # Ensure the run loop is active even when run() is invoked directly
        # (tests may call run() in a separate thread without invoking start()).
        if not self._is_alive:
            self._is_alive = True
        while self._is_alive:
            if not self._accept_client():
                continue
            self._handle_client_messages()
        # Ensure sockets are cleaned up when the server stops
        try:
            self.close()
        except OSError:
            pass
        self._close_wakeup()

    def start(self):
        """ Starts the threaded server. 
            The newly living know nothing of the dead
            
            @retval None 
        """
        self._is_alive = True
        super().start()
        logger.debug("Threaded Server started on %s:%s", self.address, self.port)

    def stop(self):
        """ Stops the threaded server.
            The life of the dead is in the memory of the living 

            @retval None 
        """
        self._is_alive = False
        self._signal_wakeup()
        logger.debug("Threaded Server stopped on %s:%s", self.address, self.port)


class ServerFactoryThread(threading.Thread, jsocket_base.JsonSocket, metaclass=abc.ABCMeta):
    """Per-connection worker thread used by ServerFactory."""

    def __init__(self, **kwargs):
        create_socket = kwargs.pop("create_socket", False)
        thread_kwargs = {}
        for key in ("group", "target", "name", "args", "kwargs", "daemon"):
            if key in kwargs:
                thread_kwargs[key] = kwargs.pop(key)
        threading.Thread.__init__(self, **thread_kwargs)
        self.socket = None
        self.conn = None
        jsocket_base.JsonSocket.__init__(self, create_socket=create_socket, **kwargs)
        self._is_alive = False
        self._stats_lock = threading.Lock()
        self._client_started_at = None
        self._client_id = None
        self._client_stats = {}
        self._active_client_id = None

    def swap_socket(self, new_sock):
        """ Swaps the existing socket with a new one. Useful for setting socket after a new connection.

            @param new_sock socket to replace the existing default jsocket.JsonSocket object 
            @retval None
        """
        existing_socket = getattr(self, "socket", None)
        if existing_socket is not None and existing_socket is not new_sock:
            try:
                self._close_socket()
            except OSError:
                pass
        self.socket = new_sock
        self.conn = self.socket
        try:
            timeout = getattr(self, "_recv_timeout", getattr(self, "_timeout", None))
            if timeout is not None:
                self.socket.settimeout(timeout)
        except OSError:
            pass
        try:
            addr = new_sock.getpeername()
        except OSError:
            addr = None
        self._client_id = _format_client_id(addr)
        self._client_started_at = time.monotonic()
        _note_connect(self, self._client_id)

    def run(self):
        """ Should exit when client closes socket conn.
            Can force an exit with force_stop.
        """
        while self._is_alive:
            try:
                obj = self.read_obj()
            except socket.timeout as e:
                logger.debug("worker read timeout waiting for data: %s", e)
                _note_failure(self, "timeout")
                continue
            except jsocket_base.FramingError as e:
                _note_framing_failure(self, e)
                logger.debug("worker framing error (%s): %s", type(e).__name__, e)
                self._is_alive = False
                break
            except Exception as e:  # pylint: disable=broad-exception-caught
                msg = str(e)
                if isinstance(e, RuntimeError) and "socket connection broken" in msg:
                    logger.info("client connection broken, closing connection")
                else:
                    logger.debug("worker error (%s): %s", type(e).__name__, e)
                    _note_failure(self, "handler")
                self._is_alive = False
                break
            client_id = _extract_client_id(obj)
            if client_id:
                _set_client_identity(self, client_id)
            _note_message_in(self, getattr(self, "_last_read_size", None))
            try:
                resp_obj = self._process_message(obj)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.debug("worker handler error (%s): %s", type(e).__name__, e)
                _note_failure(self, "handler")
                self._is_alive = False
                break
            if resp_obj is not None:
                logger.debug("sending response (%s)", _response_summary(resp_obj))
                try:
                    self.send_obj(resp_obj)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    msg = str(e)
                    if isinstance(e, RuntimeError) and "socket connection broken" in msg:
                        logger.info("client connection broken, closing connection")
                    else:
                        logger.debug("worker send error (%s): %s", type(e).__name__, e)
                    _note_failure(self, "bad_write")
                    self._is_alive = False
                    break
                _note_message_out(self, getattr(self, "_last_send_size", None))
        _note_disconnect(self)
        self._close_connection()
        if hasattr(self, "socket"):
            self._close_socket()

    @abc.abstractmethod
    def _process_message(self, obj) -> Optional[dict]:
        """Pure Virtual Method - Implementer must define protocol

        @param obj JSON "key: value" object received from client
        @retval None or a response object
        """
        # Return None in the base class to satisfy linters; subclasses should override.
        return None

    def start(self):
        """ Starts the factory thread. 
            The newly living know nothing of the dead

            @retval None
        """
        self._is_alive = True
        super().start()
        logger.debug("ServerFactoryThread started (%s)", self.name)

    def force_stop(self):
        """ Force stops the factory thread.
            Should exit when client socket is closed under normal conditions.
            The life of the dead is in the memory of the living.

            @retval None
        """
        self._is_alive = False
        logger.debug("ServerFactoryThread stopped (%s)", self.name)

    def _get_client_stats_internal(self) -> dict:
        _ensure_stats_state(self)
        with _stats_guard(self):
            return {cid: _clone_client_stats(stats) for cid, stats in self._client_stats.items()}


class ServerFactory(ThreadedServer):
    """Accepts clients and spawns a ServerFactoryThread per connection."""
    def __init__(self, server_thread, **kwargs):
        init_kwargs = {
            "address": kwargs["address"],
            "port": kwargs["port"],
        }
        if "timeout" in kwargs:
            init_kwargs["timeout"] = kwargs["timeout"]
        if "accept_timeout" in kwargs:
            init_kwargs["accept_timeout"] = kwargs["accept_timeout"]
        if "recv_timeout" in kwargs:
            init_kwargs["recv_timeout"] = kwargs["recv_timeout"]
        ThreadedServer.__init__(self, **init_kwargs)
        if not issubclass(server_thread, ServerFactoryThread):
            raise TypeError("serverThread not of type", ServerFactoryThread)
        self._thread_type = server_thread
        self._threads = []
        self._threads_lock = threading.Lock()
        self._client_stats_archive = {}
        self._thread_args = kwargs
        self._thread_args.pop('address', None)
        self._thread_args.pop('port', None)
        self._thread_args.pop('accept_timeout', None)

    def _process_message(self, obj) -> Optional[dict]:
        """ServerFactory does not process messages itself."""
        return None

    def run(self):
        # Ensure the run loop is active even when run() is invoked directly
        # (tests may call run() in a separate thread without invoking start()).
        if not self._is_alive:
            self._is_alive = True
        while self._is_alive:
            self._purge_threads()
            while not self.connected and self._is_alive:
                if not self._wait_for_accept():
                    continue
                try:
                    self.accept_connection()
                except socket.timeout as e:
                    logger.debug("factory accept timeout on %s:%s: %s", self.address, self.port, e)
                    continue
                except Exception as e:  # pylint: disable=broad-exception-caught
                    if self._is_alive:
                        logger.exception("factory accept error on %s:%s: %s", self.address, self.port, e)
                    else:
                        logger.debug("factory stopping; accept loop exiting (%s:%s)", self.address, self.port)
                    continue
                else:
                    # Hand off the accepted connection to the worker
                    accepted_conn = self.conn
                    # Reset server connection reference so we can accept again
                    self._reset_connection_ref()
                    if not self._is_alive:
                        # Server is stopping; close the accepted connection without spawning a worker.
                        try:
                            accepted_conn.shutdown(socket.SHUT_RDWR)
                        except OSError:
                            pass
                        try:
                            accepted_conn.close()
                        except OSError:
                            pass
                        break
                    try:
                        tmp = self._thread_type(**self._thread_args)
                        tmp.swap_socket(accepted_conn)
                        tmp.start()
                    except Exception as e:  # pylint: disable=broad-exception-caught
                        # Worker construction/hand-off failed; ensure the accepted connection is closed
                        try:
                            accepted_conn.shutdown(socket.SHUT_RDWR)
                        except OSError:
                            pass
                        try:
                            accepted_conn.close()
                        except OSError:
                            pass
                        if self._is_alive:
                            logger.exception(
                                "factory worker handoff error on %s:%s: %s",
                                self.address,
                                self.port,
                                e,
                            )
                        else:
                            logger.debug(
                                "factory stopping; worker handoff aborted (%s:%s)",
                                self.address,
                                self.port,
                            )
                        # Continue accepting new connections
                        continue
                    with self._threads_lock:
                        self._threads.append(tmp)
                    try:
                        addr = accepted_conn.getpeername()
                    except OSError:
                        addr = None
                    logger.debug("factory spawned worker %s for %s", tmp.name, _format_client_id(addr))
                    break

        self._wait_to_exit()
        self.close()

    def stop_all(self):
        """Stop and join all active worker threads."""
        while True:
            with self._threads_lock:
                threads = [t for t in self._threads if t.is_alive()]
            if not threads:
                break
            for t in threads:
                t.force_stop()
                t.join()
            self._purge_threads()

    def _archive_thread_stats(self, thread):
        if getattr(thread, "_stats_archived", False):
            return
        stats_map = _stats_from_thread(thread)
        if not stats_map:
            thread._stats_archived = True
            return
        # Dead threads should never be marked connected in the archive.
        for stats in stats_map.values():
            stats["connected"] = False
            stats["_connected_since"] = None
        with _stats_guard(self):
            archive = getattr(self, "_client_stats_archive", None)
            if archive is None:
                self._client_stats_archive = {}
                archive = self._client_stats_archive
            for client_id, stats in stats_map.items():
                if client_id not in archive:
                    archive[client_id] = _clone_client_stats(stats)
                else:
                    archive[client_id] = _merge_client_stats(archive[client_id], stats)
        thread._stats_archived = True

    def _purge_threads(self):
        # Rebuild list to avoid mutating while iterating, archiving stats for finished threads.
        with self._threads_lock:
            alive = []
            dead = []
            for t in self._threads:
                if t.is_alive():
                    alive.append(t)
                else:
                    dead.append(t)
            self._threads = alive
        for t in dead:
            self._archive_thread_stats(t)

    def stop(self):
        # Stop accepting and stop all workers
        self._is_alive = False
        self._signal_wakeup()
        try:
            self.stop_all()
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        logger.debug("ServerFactory stopped on %s:%s", self.address, self.port)

    def _wait_to_exit(self):
        """Block until all worker threads have finished."""
        while self._get_num_of_active_threads():
            time.sleep(0.2)

    def _get_num_of_active_threads(self):
        with self._threads_lock:
            threads = list(self._threads)
        return len([True for x in threads if x.is_alive()])

    def get_client_stats(self) -> dict:
        """Return per-client stats including connects, messages, failures, and timestamps."""
        with self._threads_lock:
            threads = list(self._threads)
        # Archive any finished threads encountered.
        for t in threads:
            if not t.is_alive():
                self._archive_thread_stats(t)
        alive = [t for t in threads if t.is_alive()]
        with _stats_guard(self):
            archive = getattr(self, "_client_stats_archive", {}) or {}
            combined = {cid: _clone_client_stats(stats) for cid, stats in archive.items()}
        for t in alive:
            stats_map = _stats_from_thread(t)
            for client_id, stats in stats_map.items():
                existing = combined.get(client_id)
                if existing is None:
                    combined[client_id] = _clone_client_stats(stats)
                else:
                    combined[client_id] = _merge_client_stats(existing, stats)
        combined = _rekey_stats_map(combined)
        now = time.monotonic()
        clients = {cid: _format_client_stats(stats, now) for cid, stats in combined.items()}
        connected = sum(1 for stats in clients.values() if stats.get("connected"))
        return {"connected_clients": connected, "clients": clients}

    active = property(_get_num_of_active_threads, doc="number of active threads")
