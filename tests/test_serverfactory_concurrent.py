"""Pytest: ServerFactory should handle two clients concurrently."""

import time
import pytest

import jsocket


class EchoWorker(jsocket.ServerFactoryThread):
    """Worker that echoes messages containing 'echo' key."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.timeout = 1.0

    def _process_message(self, obj):
        if isinstance(obj, dict) and 'echo' in obj:
            return obj
        return None


@pytest.mark.integration
@pytest.mark.timeout(15)
def test_serverfactory_handles_two_clients_concurrently():
    """Two clients can connect and receive echoes concurrently."""
    try:
        server = jsocket.ServerFactory(EchoWorker, address='127.0.0.1', port=0)
    except PermissionError as e:
        pytest.skip(f"Socket creation blocked: {e}")

    _, port = server.socket.getsockname()
    server.start()

    try:
        c1 = jsocket.JsonClient(address='127.0.0.1', port=port)
        c2 = jsocket.JsonClient(address='127.0.0.1', port=port)
        assert c1.connect() is True
        assert c2.connect() is True
        c1.timeout = 1.5
        c2.timeout = 1.5

        # Send from both clients without closing the first
        p1 = {"echo": "alpha"}
        p2 = {"echo": "beta"}
        c1.send_obj(p1)
        c2.send_obj(p2)

        # Both should receive echoes without waiting for the other to disconnect
        r1 = c1.read_obj()
        r2 = c2.read_obj()
        assert r1 == p1
        assert r2 == p2

        # At some point, we should have at least two active workers
        time.sleep(0.2)
        assert getattr(server, 'active', 0) >= 2

        c1.close()
        c2.close()
    finally:
        if hasattr(server, 'stop_all'):
            try:
                server.stop_all()
            except RuntimeError:
                pass
        server.stop()
        server.join(timeout=3)
