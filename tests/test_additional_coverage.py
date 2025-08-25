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


def test_threadedserver_timeout_then_exception_triggers_close(monkeypatch):
    """ThreadedServer should ignore timeouts and close on generic exceptions."""

    class ProbeServer(jsocket.ThreadedServer):
        def __init__(self):
            # Do not call super to avoid binding sockets
            threading.Thread.__init__(self)
            self._is_alive = True
            self._close_calls = 0
            self._reads = iter([
                lambda: (_ for _ in ()).throw(socket.timeout("t")),
                lambda: (_ for _ in ()).throw(ValueError("boom")),
            ])

        def accept_connection(self):
            # No-op; simulate an accepted connection
            return None

        def read_obj(self):
            # First a timeout, then an exception, then timeouts until stopped
            st = getattr(self, "_state", 0)
            if st == 0:
                self._state = 1
                raise socket.timeout("t")
            if st == 1:
                self._state = 2
                raise ValueError("boom")
            raise socket.timeout("t")

        def _process_message(self, obj):  # pragma: no cover - not reached
            return None

        def _close_connection(self):
            self._close_calls += 1

        def close(self):
            # Avoid base close touching real sockets
            return None

    srv = ProbeServer()
    srv.start()
    # Let the loop process the two read attempts
    time.sleep(0.1)
    srv.stop()
    srv.join(timeout=1.0)
    # One close due to ValueError path
    assert srv._close_calls == 1


def test_serverfactorythread_exception_closes_connection():
    """ServerFactoryThread should close the connection when handler raises."""

    class BoomWorker(jsocket.ServerFactoryThread):
        def __init__(self):
            # Avoid base JsonSocket init
            threading.Thread.__init__(self)
            self._is_alive = True
            self.closed = False

        def _process_message(self, obj):  # pylint: disable=unused-argument
            raise ValueError("boom")

        def read_obj(self):
            return {"echo": 1}

        def _close_connection(self):
            self.closed = True

    w = BoomWorker()
    w.start()
    w.join(timeout=1.0)
    assert w.closed is True


def test_serverfactory_accept_error_branch(monkeypatch):
    """ServerFactory should continue on accept() errors and then stop cleanly."""

    class EchoWorker(jsocket.ServerFactoryThread):
        def __init__(self):
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
        # On second call, request stop
        server._is_alive = False

    monkeypatch.setattr(server, "accept_connection", flappy_accept)

    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    t.join(timeout=1.0)
    assert calls["n"] >= 1
