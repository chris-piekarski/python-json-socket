"""Pytest: server should accept multiple clients sequentially without restart."""

import time
import pytest

import jsocket


class EchoServer(jsocket.ThreadedServer):
    """Echo server used to verify listener persistence."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.timeout = 1.0

    def _process_message(self, obj):
        # Echo round-trip for verification
        if isinstance(obj, dict) and 'echo' in obj:
            return obj
        return None


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_server_accepts_multiple_clients_sequentially():
    """Regression test: listener remains open after a client disconnects."""
    try:
        server = EchoServer(address='127.0.0.1', port=0)
    except PermissionError as e:
        pytest.skip(f"Socket creation blocked: {e}")

    # OS picks an ephemeral port
    _, port = server.socket.getsockname()
    server.start()

    try:
        # First client lifecycle
        c1 = jsocket.JsonClient(address='127.0.0.1', port=port)
        assert c1.connect() is True
        payload1 = {"echo": "one"}
        c1.send_obj(payload1)
        echoed1 = c1.read_obj()
        assert echoed1 == payload1
        c1.close()

        # Give the server a brief moment to recycle the connection
        time.sleep(0.2)

        # Second client should connect and communicate without server restart
        c2 = jsocket.JsonClient(address='127.0.0.1', port=port)
        assert c2.connect() is True
        payload2 = {"echo": "two"}
        c2.send_obj(payload2)
        echoed2 = c2.read_obj()
        assert echoed2 == payload2
        c2.close()
    finally:
        server.stop()
        server.join(timeout=3)
