"""Pytest: server stats reporting for active client connections."""

import time
import pytest

import jsocket


class EchoServer(jsocket.ThreadedServer):
    """ThreadedServer that echoes payloads for stats tests."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.timeout = 1.0

    def _process_message(self, obj):
        if isinstance(obj, dict):
            return obj
        return None


class EchoWorker(jsocket.ServerFactoryThread):
    """ServerFactory worker that echoes payloads for stats tests."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.timeout = 1.0

    def _process_message(self, obj):
        if isinstance(obj, dict):
            return obj
        return None


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_threadedserver_client_stats():
    """ThreadedServer exposes connected client duration stats."""
    try:
        server = EchoServer(address='127.0.0.1', port=0)
    except PermissionError as e:
        pytest.skip(f"Socket creation blocked: {e}")

    client = None
    _, port = server.socket.getsockname()
    server.start()

    try:
        client = jsocket.JsonClient(address='127.0.0.1', port=port)
        assert client.connect() is True
        payload = {"echo": "stats"}
        client.send_obj(payload)
        assert client.read_obj() == payload

        time.sleep(0.05)
        stats = server.get_client_stats()
        assert stats["connected_clients"] == 1
        assert len(stats["clients"]) == 1
        duration = next(iter(stats["clients"].values()))
        assert duration >= 0.0

        client.close()
        time.sleep(0.2)
        stats_after = server.get_client_stats()
        assert stats_after["connected_clients"] == 0
    finally:
        if client is not None:
            try:
                client.close()
            except OSError:
                pass
        server.stop()
        server.join(timeout=3)


@pytest.mark.integration
@pytest.mark.timeout(15)
def test_serverfactory_client_stats():
    """ServerFactory exposes connected client duration stats."""
    try:
        server = jsocket.ServerFactory(EchoWorker, address='127.0.0.1', port=0)
    except PermissionError as e:
        pytest.skip(f"Socket creation blocked: {e}")

    c1 = None
    c2 = None
    _, port = server.socket.getsockname()
    server.start()

    try:
        c1 = jsocket.JsonClient(address='127.0.0.1', port=port)
        c2 = jsocket.JsonClient(address='127.0.0.1', port=port)
        assert c1.connect() is True
        assert c2.connect() is True

        p1 = {"echo": "one"}
        p2 = {"echo": "two"}
        c1.send_obj(p1)
        c2.send_obj(p2)
        assert c1.read_obj() == p1
        assert c2.read_obj() == p2

        time.sleep(0.1)
        stats = server.get_client_stats()
        assert stats["connected_clients"] == 2
        assert len(stats["clients"]) == 2
        assert all(duration >= 0.0 for duration in stats["clients"].values())
    finally:
        if c1 is not None:
            try:
                c1.close()
            except OSError:
                pass
        if c2 is not None:
            try:
                c2.close()
            except OSError:
                pass
        if hasattr(server, 'stop_all'):
            try:
                server.stop_all()
            except RuntimeError:
                pass
        server.stop()
        server.join(timeout=3)
