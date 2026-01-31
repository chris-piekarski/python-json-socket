"""Integration tests for network failure scenarios."""

import socket
import struct
import threading
import time
import pytest

import jsocket


class EchoServer(jsocket.ThreadedServer):
    """Echo server used for failure scenario tests."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.timeout = 0.5

    def _process_message(self, obj):
        if isinstance(obj, dict) and "echo" in obj:
            return obj
        return None


class EchoWorker(jsocket.ServerFactoryThread):
    """Echo worker for ServerFactory shutdown tests."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.timeout = 0.5

    def _process_message(self, obj):
        if isinstance(obj, dict) and "echo" in obj:
            return obj
        return None


class NoResponseServer(jsocket.ThreadedServer):
    """Server that reads client messages but does not respond."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.timeout = 0.5

    def _process_message(self, obj):  # pylint: disable=unused-argument
        return None


def _send_partial_payload(address, port, payload, partial_len):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(1.0)
        sock.connect((address, port))
        header = struct.pack("!I", len(payload))
        sock.sendall(header)
        if partial_len:
            sock.sendall(payload[:partial_len])
    finally:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        sock.close()


def _send_invalid_payload(address, port, payload):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(1.0)
        sock.connect((address, port))
        header = struct.pack("!I", len(payload))
        sock.sendall(header + payload)
    finally:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        sock.close()


def _connect_client(port):
    client = jsocket.JsonClient(address="127.0.0.1", port=port)
    client.timeout = 0.5
    assert client.connect() is True
    return client


def _roundtrip(client, payload):
    client.send_obj(payload)
    assert client.read_obj() == payload


def _assert_disconnect(client):
    saw_error = False
    try:
        client.send_obj({"echo": "after-stop"})
        client.read_obj()
    except (OSError, RuntimeError, socket.timeout):
        saw_error = True
    assert saw_error is True


def _run_idle_client(port, ready_event, idle_time):
    client = None
    try:
        client = _connect_client(port)
        ready_event.set()
        time.sleep(idle_time)
    finally:
        if client is not None:
            try:
                client.close()
            except OSError:
                pass


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_threadedserver_recovers_from_partial_message_disconnect():
    """Server recovers after client drops mid-message."""
    try:
        server = EchoServer(address="127.0.0.1", port=0)
    except PermissionError as e:
        pytest.skip(f"Socket creation blocked: {e}")

    client = None
    _, port = server.socket.getsockname()
    server.start()

    try:
        payload = b'{"echo": "partial"}'
        _send_partial_payload("127.0.0.1", port, payload, partial_len=5)
        time.sleep(0.2)

        client = _connect_client(port)
        _roundtrip(client, {"echo": "ok"})
    finally:
        if client is not None:
            try:
                client.close()
            except OSError:
                pass
        server.stop()
        server.join(timeout=3)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_threadedserver_client_read_times_out_without_response():
    """Client read times out when server does not respond."""
    try:
        server = NoResponseServer(address="127.0.0.1", port=0)
    except PermissionError as e:
        pytest.skip(f"Socket creation blocked: {e}")

    client = None
    _, port = server.socket.getsockname()
    server.start()

    try:
        client = _connect_client(port)
        client.timeout = 0.2
        client.send_obj({"echo": "no-response"})
        with pytest.raises(socket.timeout):
            client.read_obj()
    finally:
        if client is not None:
            try:
                client.close()
            except OSError:
                pass
        server.stop()
        server.join(timeout=3)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_threadedserver_handles_invalid_json_and_continues():
    """Server handles invalid JSON payloads and continues accepting clients."""
    try:
        server = EchoServer(address="127.0.0.1", port=0)
    except PermissionError as e:
        pytest.skip(f"Socket creation blocked: {e}")

    client = None
    _, port = server.socket.getsockname()
    server.start()

    try:
        _send_invalid_payload("127.0.0.1", port, b"not-json")
        time.sleep(0.2)

        client = _connect_client(port)
        _roundtrip(client, {"echo": "ok"})
    finally:
        if client is not None:
            try:
                client.close()
            except OSError:
                pass
        server.stop()
        server.join(timeout=3)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_serverfactory_fast_client_not_blocked_by_slow_client():
    """Fast client should round-trip while slow client stays connected."""
    try:
        server = jsocket.ServerFactory(EchoWorker, address="127.0.0.1", port=0)
    except PermissionError as e:
        pytest.skip(f"Socket creation blocked: {e}")

    fast_client = None
    _, port = server.socket.getsockname()
    server.start()

    ready_event = threading.Event()
    idle_thread = threading.Thread(
        target=_run_idle_client,
        args=(port, ready_event, 1.0),
    )
    idle_thread.start()

    try:
        assert ready_event.wait(timeout=1.0) is True
        fast_client = _connect_client(port)
        started = time.monotonic()
        _roundtrip(fast_client, {"echo": "fast"})
        elapsed = time.monotonic() - started
        assert elapsed < 1.0
    finally:
        if fast_client is not None:
            try:
                fast_client.close()
            except OSError:
                pass
        idle_thread.join(timeout=2.0)
        if hasattr(server, "stop_all"):
            try:
                server.stop_all()
            except OSError:
                pass
        server.stop()
        server.join(timeout=3)


@pytest.mark.integration
@pytest.mark.timeout(15)
def test_serverfactory_stop_with_active_clients():
    """ServerFactory shuts down cleanly with active client connections."""
    try:
        server = jsocket.ServerFactory(EchoWorker, address="127.0.0.1", port=0)
    except PermissionError as e:
        pytest.skip(f"Socket creation blocked: {e}")

    c1 = None
    c2 = None
    _, port = server.socket.getsockname()
    server.start()

    try:
        c1 = _connect_client(port)
        c2 = _connect_client(port)
        _roundtrip(c1, {"echo": "alpha"})
        _roundtrip(c2, {"echo": "beta"})

        server.stop()
        server.join(timeout=3)
        assert server.is_alive() is False

        _assert_disconnect(c1)
        _assert_disconnect(c2)
    finally:
        for client in (c1, c2):
            if client is not None:
                try:
                    client.close()
                except OSError:
                    pass
        if hasattr(server, "stop_all"):
            try:
                server.stop_all()
            except OSError:
                pass
        server.stop()
        server.join(timeout=3)
