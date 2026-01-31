"""Pytest: ServerFactory concurrency behavior (updated to allow multiple clients)."""

import time
import pytest

import jsocket


class EchoWorker(jsocket.ServerFactoryThread):
    """Worker that echoes messages containing 'echo' key."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.timeout = 1.0

    def _process_message(self, obj):
        # Echo payloads that include 'echo' for verification
        if isinstance(obj, dict) and 'echo' in obj:
            return obj
        return None


@pytest.mark.integration
@pytest.mark.timeout(15)
def test_serverfactory_accepts_multiple_active_clients_concurrently():
    """ServerFactory accepts a second client while the first is active.

    Updated behavior: ServerFactory accepts additional clients while one is
    already active, starting a new worker per connection.
    """
    try:
        server = jsocket.ServerFactory(EchoWorker, address='127.0.0.1', port=0)
    except PermissionError as e:
        pytest.skip(f"Socket creation blocked: {e}")

    # Discover ephemeral port and start server
    _, port = server.socket.getsockname()
    server.start()

    try:
        # First client establishes a connection and gets echoed responses
        c1 = jsocket.JsonClient(address='127.0.0.1', port=port)
        assert c1.connect() is True
        c1.timeout = 1.0
        payload1 = {"echo": "one"}
        c1.send_obj(payload1)
        echoed1 = c1.read_obj()
        assert echoed1 == payload1

        # Second client connects while the first is still active
        c2 = jsocket.JsonClient(address='127.0.0.1', port=port)
        assert c2.connect() is True
        c2.timeout = 1.0
        payload2 = {"echo": "two"}
        c2.send_obj(payload2)

        # Both clients should receive responses
        echoed2 = c2.read_obj()
        assert echoed2 == payload2

        # Active workers should reach at least 2
        time.sleep(0.2)
        assert getattr(server, 'active', 0) >= 2

        # Clean up clients
        c2.close()
        c1.close()
    finally:
        # Stop the server thread and join
        # Ensure any worker threads are stopped to avoid hangs
        if hasattr(server, 'stop_all'):
            try:
                server.stop_all()
            except RuntimeError:
                pass
        server.stop()
        server.join(timeout=3)
