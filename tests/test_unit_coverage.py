"""Unit tests to cover error/edge branches without real network I/O."""

import threading
import socket
import struct
import zlib
import pytest

import jsocket
import jsocket.jsocket_base as jsocket_base
import jsocket.tserver as tserver


class FakeSocket:  # pylint: disable=missing-function-docstring
    """Simple socket stub for unit tests."""

    def __init__(self, fileno_value=1, fileno_exc=None, shutdown_exc=None, close_exc=None):
        self._fileno_value = fileno_value
        self._fileno_exc = fileno_exc
        self._shutdown_exc = shutdown_exc
        self._close_exc = close_exc
        self.shutdown_called = False
        self.close_called = False

    def fileno(self):
        if self._fileno_exc is not None:
            raise self._fileno_exc
        return self._fileno_value

    def shutdown(self, how):  # pylint: disable=unused-argument
        self.shutdown_called = True
        if self._shutdown_exc is not None:
            raise self._shutdown_exc

    def close(self):
        self.close_called = True
        if self._close_exc is not None:
            raise self._close_exc

    def settimeout(self, timeout):  # pylint: disable=unused-argument
        return None

    def send(self, data):
        return len(data)


def _make_base_socket():
    """Build a JsonSocket stub with a fake connection."""
    sock = jsocket_base.JsonSocket.__new__(jsocket_base.JsonSocket)
    sock.socket = object()
    sock.conn = FakeSocket()
    sock._max_message_size = None
    sock._timeout = 1.0
    return sock


def test_send_obj_no_socket_is_noop():
    """send_obj should no-op when socket is None."""
    sock = jsocket_base.JsonSocket.__new__(jsocket_base.JsonSocket)
    sock.socket = None
    sock.send_obj({"x": 1})


def test_send_obj_rejects_oversize():
    """send_obj should reject payloads exceeding max_message_size."""
    sock = jsocket_base.JsonSocket.__new__(jsocket_base.JsonSocket)
    sock.socket = object()
    sock._max_message_size = 1
    with pytest.raises(ValueError):
        sock.send_obj({"x": "too-big"})


def test_read_header_invalid_magic_closes():
    """_read_header should raise when magic bytes are invalid."""
    sock = _make_base_socket()
    closed = {"n": 0}

    def _close():
        """Track close invocations."""
        closed["n"] += 1

    sock._close_connection = _close
    sock._read = lambda *_args, **_kwargs: struct.pack(
        jsocket_base.FRAME_HEADER_FMT,
        b"BAD!",
        1,
        0,
    )
    with pytest.raises(jsocket_base.FramingError):
        sock._read_header()
    assert closed["n"] == 1


def test_read_header_oversize_closes():
    """_read_header should raise when length exceeds max_message_size."""
    sock = _make_base_socket()
    sock._max_message_size = 2
    closed = {"n": 0}

    def _close():
        """Track close invocations."""
        closed["n"] += 1

    sock._close_connection = _close
    sock._read = lambda *_args, **_kwargs: struct.pack(
        jsocket_base.FRAME_HEADER_FMT,
        jsocket_base.FRAME_MAGIC,
        10,
        0,
    )
    with pytest.raises(jsocket_base.FramingError):
        sock._read_header()
    assert closed["n"] == 1


def test_read_obj_invalid_utf8_closes():
    """read_obj should raise when payload is not UTF-8."""
    sock = _make_base_socket()
    closed = {"n": 0}
    data = b"\xff"
    checksum = zlib.crc32(data) & 0xFFFFFFFF

    def _close():
        """Track close invocations."""
        closed["n"] += 1

    sock._close_connection = _close
    sock._read_header = lambda: (len(data), checksum)
    sock._read = lambda _size: data
    with pytest.raises(jsocket_base.FramingError):
        sock.read_obj()
    assert closed["n"] == 1


def test_read_obj_invalid_json_closes():
    """read_obj should raise when payload is not valid JSON."""
    sock = _make_base_socket()
    closed = {"n": 0}
    data = b"not-json"
    checksum = zlib.crc32(data) & 0xFFFFFFFF

    def _close():
        """Track close invocations."""
        closed["n"] += 1

    sock._close_connection = _close
    sock._read_header = lambda: (len(data), checksum)
    sock._read = lambda _size: data
    with pytest.raises(jsocket_base.FramingError):
        sock.read_obj()
    assert closed["n"] == 1


def test_close_socket_handles_oserrors():
    """_close_socket should swallow shutdown/close errors."""
    sock = jsocket_base.JsonSocket.__new__(jsocket_base.JsonSocket)
    sock.socket = FakeSocket(shutdown_exc=OSError("boom"), close_exc=OSError("boom"))
    sock._close_socket()


def test_close_socket_handles_fileno_error():
    """_close_socket should swallow fileno errors."""
    sock = jsocket_base.JsonSocket.__new__(jsocket_base.JsonSocket)
    sock.socket = FakeSocket(fileno_exc=OSError("boom"))
    sock._close_socket()


def test_close_connection_handles_oserrors():
    """_close_connection should swallow shutdown/close errors."""
    sock = jsocket_base.JsonSocket.__new__(jsocket_base.JsonSocket)
    sock.conn = FakeSocket(shutdown_exc=OSError("boom"), close_exc=OSError("boom"))
    sock._close_connection()


def test_close_connection_handles_fileno_error():
    """_close_connection should swallow fileno errors."""
    sock = jsocket_base.JsonSocket.__new__(jsocket_base.JsonSocket)
    sock.conn = FakeSocket(fileno_exc=OSError("boom"))
    sock._close_connection()


def test_properties_and_max_message_size_setters():
    """Property setters should accept None and reject non-positive sizes."""
    sock = jsocket_base.JsonSocket.__new__(jsocket_base.JsonSocket)
    sock._max_message_size = 123
    assert sock._get_max_message_size() == 123
    assert sock._set_address("x") is None
    assert sock._set_port(1) is None
    sock._set_max_message_size(None)
    assert sock._max_message_size is None
    with pytest.raises(ValueError):
        sock._set_max_message_size(0)


def test_jsonserver_close_connection_handles_errors():
    """JsonServer._close_connection should swallow shutdown/close errors."""
    server = jsocket_base.JsonServer.__new__(jsocket_base.JsonServer)
    server.socket = object()
    server.conn = FakeSocket(shutdown_exc=OSError("boom"), close_exc=OSError("boom"))
    server._close_connection()


def test_jsonserver_close_connection_handles_fileno_error():
    """JsonServer._close_connection should swallow fileno errors."""
    server = jsocket_base.JsonServer.__new__(jsocket_base.JsonServer)
    server.socket = object()
    server.conn = FakeSocket(fileno_exc=OSError("boom"))
    server._close_connection()


def test_jsonserver_connected_handles_fileno_error():
    """JsonServer.connected should tolerate fileno errors."""
    server = jsocket_base.JsonServer.__new__(jsocket_base.JsonServer)
    server.socket = object()
    server.conn = FakeSocket(fileno_exc=OSError("boom"))
    assert server.connected is False


def test_response_summary_and_format_client_id():
    """Helper formatting should cover dict/list/str and IPv6 cases."""
    assert tserver._response_summary({"a": 1}) == "type=dict keys=1"
    assert tserver._response_summary([1, 2]) == "type=list items=2"
    assert tserver._response_summary("x") == "type=str"
    assert tserver._format_client_id(("::1", 9999)) == "[::1]:9999"
    assert tserver._format_client_id(None) == "unknown"


class _BaseServer(tserver.ThreadedServer):  # pylint: disable=missing-function-docstring
    """ThreadedServer stub for base-method coverage."""

    def __init__(self):  # pylint: disable=super-init-not-called
        threading.Thread.__init__(self)
        self._is_alive = False
        self._stats_lock = threading.Lock()
        self._client_started_at = None
        self._client_id = None
        self._last_client_addr = None
        self.conn = None

    def _process_message(self, obj):
        return super()._process_message(obj)


class _AcceptErrorServer(tserver.ThreadedServer):  # pylint: disable=missing-function-docstring
    """ThreadedServer stub that raises on accept."""

    def __init__(self, alive):  # pylint: disable=super-init-not-called
        threading.Thread.__init__(self)
        self._is_alive = alive
        self._address = "127.0.0.1"
        self._port = 0
        self._stats_lock = threading.Lock()
        self._client_started_at = None
        self._client_id = None
        self._last_client_addr = None

    def accept_connection(self):
        raise RuntimeError("boom")

    def _process_message(self, obj):  # pragma: no cover - not used
        return None


class _RunServer(tserver.ThreadedServer):  # pylint: disable=missing-function-docstring
    """ThreadedServer stub that forces close error."""

    def __init__(self):  # pylint: disable=super-init-not-called
        threading.Thread.__init__(self)
        self._is_alive = False
        self._stats_lock = threading.Lock()
        self._client_started_at = None
        self._client_id = None

    def _accept_client(self):
        self._is_alive = False
        return False

    def close(self):
        raise OSError("boom")

    def _process_message(self, obj):  # pragma: no cover - not used
        return None


class _PeernameRaises:  # pylint: disable=missing-function-docstring
    """Object that raises on getpeername()."""

    def getpeername(self):
        raise OSError("boom")


class _Worker(tserver.ServerFactoryThread):  # pylint: disable=missing-function-docstring
    """Worker stub that sends a response once."""

    def __init__(self):  # pylint: disable=super-init-not-called
        threading.Thread.__init__(self)
        self._is_alive = True
        self.sent = False
        self.closed = False

    def read_obj(self):
        if self.sent:
            raise RuntimeError("boom")
        return {"x": 1}

    def _process_message(self, obj):  # pylint: disable=unused-argument
        return {"ok": True}

    def send_obj(self, obj):  # pylint: disable=unused-argument
        self.sent = True

    def _close_connection(self):
        self.closed = True

    def _close_socket(self):
        return None


class _FactoryBase(tserver.ServerFactoryThread):  # pylint: disable=missing-function-docstring
    """Worker stub that calls base _process_message."""

    def __init__(self):  # pylint: disable=super-init-not-called
        threading.Thread.__init__(self)
        self._is_alive = False

    def _process_message(self, obj):
        return super()._process_message(obj)


class _FactoryWorker(tserver.ServerFactoryThread):  # pylint: disable=missing-function-docstring
    """Worker stub without processing logic."""

    def __init__(self):  # pylint: disable=super-init-not-called
        threading.Thread.__init__(self)
        self._is_alive = False

    def _process_message(self, obj):  # pragma: no cover - not used
        return None


class _StoppingFactory(tserver.ServerFactory):  # pylint: disable=missing-function-docstring
    """ServerFactory stub that stops immediately."""

    def __init__(self):  # pylint: disable=super-init-not-called
        self._is_alive = True
        self._thread_type = _FactoryWorker
        self._thread_args = {}
        self._threads = []
        self._threads_lock = threading.Lock()
        self.socket = object()
        self.conn = None
        self.address = "127.0.0.1"
        self.port = 0
        self.accepted = FakeSocket()

    def accept_connection(self):
        self.conn = self.accepted
        self._is_alive = False

    def _purge_threads(self):
        return None

    def _wait_to_exit(self):
        return None

    def close(self):
        return None


class _StopAllRaises(tserver.ServerFactory):  # pylint: disable=missing-function-docstring
    """ServerFactory stub that raises in stop_all."""

    def __init__(self):  # pylint: disable=super-init-not-called
        self._is_alive = True
        self._address = "127.0.0.1"
        self._port = 0

    def stop_all(self):
        raise RuntimeError("boom")


class _DeadThread:  # pylint: disable=missing-function-docstring
    """Thread stub that is not alive."""

    def is_alive(self):
        return False


class _AliveThread:  # pylint: disable=missing-function-docstring
    """Thread stub that is alive without a client id."""

    def __init__(self):
        self._client_started_at = None
        self._client_id = None
        self.name = "alive-1"

    def is_alive(self):
        return True


class _ThreadWithName:  # pylint: disable=missing-function-docstring
    """Thread stub that is alive with a name."""

    def __init__(self):
        self._client_started_at = None
        self._client_id = None
        self.name = "t1"

    def is_alive(self):
        return True


class _ThreadLock:  # pylint: disable=missing-function-docstring
    """Context manager stub for thread locks."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _StatsFactory(tserver.ServerFactory):  # pylint: disable=missing-function-docstring
    """ServerFactory stub with dead threads."""

    def __init__(self):  # pylint: disable=super-init-not-called
        self._threads = [_DeadThread()]
        self._threads_lock = _ThreadLock()


class _StatsFactoryAlive(tserver.ServerFactory):  # pylint: disable=missing-function-docstring
    """ServerFactory stub with live threads."""

    def __init__(self):  # pylint: disable=super-init-not-called
        self._threads = [_AliveThread(), _ThreadWithName()]
        self._threads_lock = _ThreadLock()


def test_base_process_message_returns_none():
    """Base _process_message should return None."""
    srv = _BaseServer()
    assert srv._process_message({"x": 1}) is None


def test_record_client_start_handles_getpeername_error():
    """_record_client_start should handle getpeername errors."""
    srv = _BaseServer()
    srv.conn = _PeernameRaises()
    srv._record_client_start()
    assert srv._client_id == "unknown"


def test_accept_client_error_branches():
    """_accept_client should handle accept exceptions."""
    srv_alive = _AcceptErrorServer(alive=True)
    assert srv_alive._accept_client() is False
    assert srv_alive._is_alive is True

    srv_stopping = _AcceptErrorServer(alive=False)
    assert srv_stopping._accept_client() is False
    assert srv_stopping._is_alive is False


def test_run_sets_alive_and_handles_close_error():
    """run() should tolerate close() raising OSError."""
    srv = _RunServer()
    srv.run()
    assert srv._is_alive is False


def test_serverfactorythread_swap_socket_handles_getpeername_error():
    """swap_socket should handle getpeername errors."""
    worker = _FactoryWorker()
    worker.swap_socket(_PeernameRaises())
    assert worker._client_id == "unknown"


def test_serverfactorythread_run_sends_response_and_closes():
    """run() should send a response and close on error."""
    worker = _Worker()
    worker.run()
    assert worker.sent is True
    assert worker.closed is True


def test_serverfactorythread_base_process_message_returns_none():
    """Base worker _process_message should return None."""
    worker = _FactoryBase()
    assert worker._process_message({"x": 1}) is None


def test_serverfactory_init_type_error(monkeypatch):
    """ServerFactory should reject non-worker classes."""

    def fake_init(self, address, port):  # pylint: disable=unused-argument
        """Stub ThreadedServer initializer for isolation."""
        self.address = address
        self.port = port
        self.conn = None
        self.socket = None
        self._is_alive = False
        self._stats_lock = threading.Lock()
        self._client_started_at = None
        self._client_id = None

    monkeypatch.setattr(tserver.ThreadedServer, "__init__", fake_init, raising=True)

    class NotAWorker:
        """Dummy class that is not a ServerFactoryThread."""

    with pytest.raises(TypeError):
        tserver.ServerFactory(NotAWorker, address="127.0.0.1", port=0)


def test_serverfactory_process_message_returns_none(monkeypatch):
    """ServerFactory._process_message should return None."""

    def fake_init(self, address, port):  # pylint: disable=unused-argument
        """Stub ThreadedServer initializer for isolation."""
        self.address = address
        self.port = port
        self.conn = None
        self.socket = None
        self._is_alive = False
        self._stats_lock = threading.Lock()
        self._client_started_at = None
        self._client_id = None

    monkeypatch.setattr(tserver.ThreadedServer, "__init__", fake_init, raising=True)

    factory = tserver.ServerFactory(_FactoryWorker, address="127.0.0.1", port=0)
    assert factory._process_message({"x": 1}) is None


def test_serverfactory_run_closes_accepted_conn_when_stopping():
    """ServerFactory should close accepted connections when stopping."""
    factory = _StoppingFactory()
    factory.run()
    assert factory.accepted.shutdown_called is True
    assert factory.accepted.close_called is True


def test_serverfactory_stop_swallows_exception():
    """ServerFactory.stop should swallow stop_all errors."""
    factory = _StopAllRaises()
    factory.stop()
    assert factory._is_alive is False


def test_serverfactory_get_client_stats_skips_dead_threads():
    """get_client_stats should ignore dead threads."""
    factory = _StatsFactory()
    stats = factory.get_client_stats()
    assert stats["connected_clients"] == 0
    assert stats["clients"] == {}


def test_serverfactory_get_client_stats_active_threads():
    """get_client_stats should report active threads."""
    factory = _StatsFactoryAlive()
    stats = factory.get_client_stats()
    assert stats["connected_clients"] == 2
    assert len(stats["clients"]) == 2
