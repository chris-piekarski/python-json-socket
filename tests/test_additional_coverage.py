"""Additional tests to exercise error/edge paths for higher coverage.

These tests avoid real network I/O by monkeypatching/stubbing where possible.
"""

import threading
import time
import socket
import pytest

import jsocket
import jsocket.tserver as tserver


def test_client_connect_failure_returns_false(monkeypatch):
    """JsonClient.connect should return False after repeated failures."""

    def fail_connect(self, addr):  # pylint: disable=unused-argument
        raise OSError("boom")

    # Short-circuit sleeps so the test is fast
    monkeypatch.setattr(jsocket.jsocket_base.time, "sleep", lambda *_: None)
    monkeypatch.setattr(socket.socket, "connect", fail_connect, raising=True)

    try:
        client = jsocket.JsonClient(address="127.0.0.1", port=9)
    except PermissionError as e:  # sandboxed environments may forbid sockets
        pytest.skip(f"Socket creation blocked: {e}")
    assert client.connect() is False


def test_close_idempotent_and_connected_guard():
    """close() is safe to call multiple times; connected guard tolerates None."""
    # Client close idempotence
    try:
        c = jsocket.JsonClient(address="127.0.0.1", port=0)
    except PermissionError as e:  # sandboxed environments may forbid sockets
        pytest.skip(f"Socket creation blocked: {e}")
    c.close()
    c.close()  # should not raise

    # Server connected property guard (None conn)
    try:
        s = jsocket.JsonServer(address="127.0.0.1", port=0)
    except PermissionError as e:  # sandboxed environments may forbid sockets
        pytest.skip(f"Socket creation blocked: {e}")
    s.conn = None
    assert s.connected is False
    s.close()


def test_jsonserver_sets_reuseaddr(monkeypatch):
    """JsonServer should set SO_REUSEADDR before binding."""
    calls = []
    orig_setsockopt = socket.socket.setsockopt

    def tracking_setsockopt(self, level, optname, value):
        calls.append((level, optname, value))
        return orig_setsockopt(self, level, optname, value)

    monkeypatch.setattr(socket.socket, "setsockopt", tracking_setsockopt, raising=True)

    try:
        server = jsocket.JsonServer(address="127.0.0.1", port=0)
    except PermissionError as e:  # sandboxed environments may forbid sockets
        pytest.skip(f"Socket creation blocked: {e}")
    server.close()

    assert any(
        level == socket.SOL_SOCKET and optname == socket.SO_REUSEADDR and value in (1, True)
        for level, optname, value in calls
    )


def test_threadedserver_timeout_then_exception_triggers_close():
    """ThreadedServer should ignore timeouts and close on generic exceptions."""
    state = {"step": 0, "close_calls": 0}

    class ProbeServer(jsocket.ThreadedServer):
        """ThreadedServer stub that avoids real sockets."""
        # pylint: disable=non-parent-init-called

        def __init__(self):  # pylint: disable=super-init-not-called
            # Do not call super to avoid binding sockets
            threading.Thread.__init__(self)
            self._is_alive = True
            self._address = "127.0.0.1"
            self._port = 0
            self._stats_lock = threading.Lock()
            self._client_started_at = None
            self._client_id = None
            self._last_client_addr = ("127.0.0.1", 0)

        def accept_connection(self):
            """No-op; simulate an accepted connection."""
            # No-op; simulate an accepted connection
            return None

        def read_obj(self):
            """Simulate timeout, then error, then timeouts."""
            # First a timeout, then an exception, then timeouts until stopped
            if state["step"] == 0:
                state["step"] = 1
                raise socket.timeout("t")
            if state["step"] == 1:
                state["step"] = 2
                raise ValueError("boom")
            raise socket.timeout("t")

        def _process_message(self, obj):  # pragma: no cover - not reached
            return None

        def _close_connection(self):
            state["close_calls"] += 1

        def close(self):
            """No-op: avoid touching real sockets."""
            # Avoid base close touching real sockets
            return None

    srv = ProbeServer()
    srv.start()
    # Let the loop process the two read attempts
    time.sleep(0.1)
    srv.stop()
    srv.join(timeout=1.0)
    # One close due to ValueError path
    assert state["close_calls"] == 1


def test_serverfactorythread_exception_closes_connection():
    """ServerFactoryThread should close the connection when handler raises."""

    class BoomWorker(jsocket.ServerFactoryThread):
        """Worker that raises to trigger close handling."""
        # pylint: disable=non-parent-init-called

        def __init__(self):  # pylint: disable=super-init-not-called
            # Avoid base JsonSocket init
            threading.Thread.__init__(self)
            self._is_alive = True
            self.closed = False

        def _process_message(self, obj):  # pylint: disable=unused-argument
            raise ValueError("boom")

        def read_obj(self):
            """Return a single payload to trigger processing."""
            return {"echo": 1}

        def _close_connection(self):
            self.closed = True

    w = BoomWorker()
    w.start()
    w.join(timeout=1.0)
    assert w.closed is True


def test_serverfactorythread_closes_socket_after_run():
    """ServerFactoryThread should close the swapped socket when exiting."""
    if not hasattr(socket, "socketpair"):
        pytest.skip("socketpair unavailable")

    try:
        client_sock, server_sock = socket.socketpair()
    except OSError as e:
        pytest.skip(f"Socketpair blocked: {e}")

    class CloseWorker(jsocket.ServerFactoryThread):
        """Worker that reuses an existing socket."""
        # pylint: disable=non-parent-init-called

        def __init__(self, sock):  # pylint: disable=super-init-not-called
            threading.Thread.__init__(self)
            self._is_alive = False
            self.socket = sock
            self.conn = sock

        def _process_message(self, obj):  # pragma: no cover - not used here
            return None

    worker = CloseWorker(server_sock)
    try:
        assert worker.socket.fileno() != -1
        worker.run()
        assert worker.socket.fileno() == -1
    finally:
        try:
            client_sock.close()
        except OSError:
            pass
        try:
            server_sock.close()
        except OSError:
            pass


def test_serverfactory_accept_error_branch(monkeypatch):
    """ServerFactory should continue on accept() errors and then stop cleanly."""

    class EchoWorker(jsocket.ServerFactoryThread):
        """Worker stub for accept error branch test."""
        # pylint: disable=non-parent-init-called

        def __init__(self):  # pylint: disable=super-init-not-called
            threading.Thread.__init__(self)
            self._is_alive = False

        def _process_message(self, obj):  # pragma: no cover - not used here
            return None

    # Real factory to get run loop; we'll stub accept_connection to raise
    try:
        server = jsocket.ServerFactory(EchoWorker, address="127.0.0.1", port=0)
    except PermissionError as e:  # sandboxed environments may forbid sockets
        pytest.skip(f"Socket creation blocked: {e}")

    calls = {"n": 0}

    def flappy_accept():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("accept failed")
        # On second call, request stop without accepting a connection
        server.stop()
        raise RuntimeError("accept stopped")

    monkeypatch.setattr(server, "accept_connection", flappy_accept)
    monkeypatch.setattr(server, "_wait_for_accept", lambda: True)

    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    t.join(timeout=1.0)
    assert calls["n"] >= 1


def test_wakeup_init_fallback_success(monkeypatch):
    """_init_wakeup should fall back to TCP pair when socketpair is unavailable."""

    class WakeServer(tserver.ThreadedServer):
        def __init__(self):
            threading.Thread.__init__(self)
            self._wakeup_r = None
            self._wakeup_w = None

        def _process_message(self, obj):  # pragma: no cover - not used
            return None

    class FakeReader:
        def setblocking(self, flag):  # pylint: disable=unused-argument
            return None

    class FakeWriter:
        def __init__(self):
            self.connected = False

        def connect(self, addr):  # pylint: disable=unused-argument
            self.connected = True

        def setblocking(self, flag):  # pylint: disable=unused-argument
            return None

    class FakeListener:
        def __init__(self, reader):
            self.reader = reader

        def setsockopt(self, *args, **kwargs):  # pylint: disable=unused-argument
            return None

        def bind(self, addr):  # pylint: disable=unused-argument
            return None

        def listen(self, backlog):  # pylint: disable=unused-argument
            return None

        def getsockname(self):
            return ("127.0.0.1", 12345)

        def accept(self):
            return self.reader, ("127.0.0.1", 12345)

        def close(self):
            return None

    reader = FakeReader()
    writer = FakeWriter()
    listener = FakeListener(reader)
    sockets = [listener, writer]

    def fake_socket(*args, **kwargs):  # pylint: disable=unused-argument
        return sockets.pop(0)

    monkeypatch.setattr(socket, "socketpair", lambda: (_ for _ in ()).throw(AttributeError()))
    monkeypatch.setattr(socket, "socket", fake_socket, raising=True)

    srv = WakeServer()
    srv._init_wakeup()

    assert srv._wakeup_r is reader
    assert srv._wakeup_w is writer


def test_wakeup_init_fallback_failure(monkeypatch):
    """_init_wakeup should leave wakeup sockets unset when fallback fails."""

    class WakeServer(tserver.ThreadedServer):
        def __init__(self):
            threading.Thread.__init__(self)
            self._wakeup_r = None
            self._wakeup_w = None

        def _process_message(self, obj):  # pragma: no cover - not used
            return None

    monkeypatch.setattr(socket, "socketpair", lambda: (_ for _ in ()).throw(AttributeError()))
    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: (_ for _ in ()).throw(OSError()))

    srv = WakeServer()
    srv._init_wakeup()
    assert srv._wakeup_r is None
    assert srv._wakeup_w is None


def test_wakeup_signal_and_drain_cover_errors(monkeypatch):
    """_signal_wakeup and _drain_wakeup should ignore socket errors."""

    class WakeServer(tserver.ThreadedServer):
        def __init__(self):
            threading.Thread.__init__(self)
            self._wakeup_r = None
            self._wakeup_w = None

        def _process_message(self, obj):  # pragma: no cover - not used
            return None

    class BadSender:
        def send(self, data):  # pylint: disable=unused-argument
            raise OSError("boom")

    class BadReader:
        def recv(self, size):  # pylint: disable=unused-argument
            raise OSError("boom")

    srv = WakeServer()
    srv._wakeup_w = BadSender()
    srv._signal_wakeup()

    srv._wakeup_r = None
    srv._drain_wakeup()

    srv._wakeup_r = BadReader()
    srv._drain_wakeup()


def test_wakeup_close_handles_errors():
    """_close_wakeup should ignore close errors."""

    class WakeServer(tserver.ThreadedServer):
        def __init__(self):
            threading.Thread.__init__(self)
            self._wakeup_r = None
            self._wakeup_w = None

        def _process_message(self, obj):  # pragma: no cover - not used
            return None

    class BadClose:
        def close(self):
            raise OSError("boom")

    srv = WakeServer()
    srv._wakeup_r = BadClose()
    srv._wakeup_w = BadClose()
    srv._close_wakeup()
    assert srv._wakeup_r is None
    assert srv._wakeup_w is None


def test_wait_for_accept_paths(monkeypatch):
    """_wait_for_accept should handle listen/select/wakeup paths."""

    class WaitServer(tserver.ThreadedServer):
        def __init__(self):
            threading.Thread.__init__(self)
            self._is_alive = True
            self.socket = object()
            self._wakeup_r = object()
            self._address = "127.0.0.1"
            self._port = 0

        def _process_message(self, obj):  # pragma: no cover - not used
            return None

        def _listen(self):
            return None

    srv = WaitServer()

    def listen_fail():
        raise OSError("boom")

    srv._listen = listen_fail
    assert srv._wait_for_accept() is False

    srv._listen = lambda: None
    monkeypatch.setattr(tserver.select, "select", lambda *_: (_ for _ in ()).throw(ValueError("boom")))
    assert srv._wait_for_accept() is False

    drained = {"n": 0}

    def drain():
        drained["n"] += 1

    srv._drain_wakeup = drain
    monkeypatch.setattr(tserver.select, "select", lambda *_: ([srv._wakeup_r], [], []))
    assert srv._wait_for_accept() is False
    assert drained["n"] == 1

    monkeypatch.setattr(tserver.select, "select", lambda *_: ([srv.socket], [], []))
    assert srv._wait_for_accept() is True

    srv._is_alive = False
    assert srv._wait_for_accept() is False


def test_accept_client_timeout_branch():
    """_accept_client should return False on socket.timeout."""

    class TimeoutServer(tserver.ThreadedServer):
        def __init__(self):
            threading.Thread.__init__(self)
            self._is_alive = True
            self._stats_lock = threading.Lock()
            self._client_started_at = None
            self._client_id = None
            self._address = "127.0.0.1"
            self._port = 0

        def _process_message(self, obj):  # pragma: no cover - not used
            return None

        def _wait_for_accept(self):
            return True

        def accept_connection(self):
            raise socket.timeout("t")

    srv = TimeoutServer()
    assert srv._accept_client() is False


def test_serverfactorythread_kwargs_and_swap_error_branches():
    """ServerFactoryThread should accept thread kwargs and ignore swap errors."""

    class Worker(tserver.ServerFactoryThread):
        def _process_message(self, obj):  # pragma: no cover - not used
            return None

    worker = Worker(name="w1", daemon=True)
    assert worker.name == "w1"
    assert worker.daemon is True

    class BadSocket:
        def settimeout(self, timeout):  # pylint: disable=unused-argument
            raise OSError("boom")

        def getpeername(self):
            return ("127.0.0.1", 12345)

    worker.socket = object()

    def close_raises():
        raise OSError("boom")

    worker._close_socket = close_raises
    worker.swap_socket(BadSocket())


def test_serverfactorythread_run_with_none_response():
    """ServerFactoryThread.run should handle None responses."""

    class NoneRespWorker(tserver.ServerFactoryThread):
        # pylint: disable=non-parent-init-called
        def __init__(self):
            threading.Thread.__init__(self)
            self._is_alive = True
            self.closed = False
            self.socket = object()

        def read_obj(self):
            self._is_alive = False
            return {"x": 1}

        def _process_message(self, obj):  # pylint: disable=unused-argument
            return None

        def _close_connection(self):
            self.closed = True

        def _close_socket(self):
            return None

    worker = NoneRespWorker()
    worker.run()
    assert worker.closed is True


def test_serverfactory_accept_timeout_and_close_branches(monkeypatch):
    """ServerFactory.run should handle accept timeouts and close accepted conns on stop."""

    def fake_init(self, address, port, timeout=2.0, accept_timeout=None, recv_timeout=None):
        self.address = address
        self.port = port
        self._address = address
        self._port = port
        self.socket = object()
        self.conn = self.socket
        self._is_alive = True
        self._stats_lock = threading.Lock()
        self._client_started_at = None
        self._client_id = None
        self._threads = []
        self._threads_lock = threading.Lock()

    monkeypatch.setattr(tserver.ThreadedServer, "__init__", fake_init, raising=True)

    class Worker(tserver.ServerFactoryThread):
        def _process_message(self, obj):  # pragma: no cover - not used
            return None

    factory = tserver.ServerFactory(Worker, address="127.0.0.1", port=0)
    monkeypatch.setattr(factory, "_wait_for_accept", lambda: True)
    monkeypatch.setattr(factory, "_purge_threads", lambda: None)
    monkeypatch.setattr(factory, "_wait_to_exit", lambda: None)
    monkeypatch.setattr(factory, "close", lambda: None)

    called = {"timeout": 0}

    def accept_timeout():
        called["timeout"] += 1
        factory._is_alive = False
        raise socket.timeout("t")

    monkeypatch.setattr(factory, "accept_connection", accept_timeout)
    factory.run()
    assert called["timeout"] == 1

    class CloseRaises:
        def shutdown(self, how):  # pylint: disable=unused-argument
            raise OSError("boom")

        def close(self):
            raise OSError("boom")

        def fileno(self):  # pragma: no cover - safety for connected()
            return 5

    def accept_then_stop():
        factory.conn = CloseRaises()
        factory._is_alive = False

    monkeypatch.setattr(factory, "accept_connection", accept_then_stop)
    factory._is_alive = True
    factory.run()
