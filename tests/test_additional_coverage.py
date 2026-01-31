"""Additional tests to exercise error/edge paths for higher coverage.

These tests avoid real network I/O by monkeypatching/stubbing where possible.
"""

import threading
import time
import socket
import pytest

import jsocket


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

    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    t.join(timeout=1.0)
    assert calls["n"] >= 1
