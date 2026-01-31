"""Pytest end-to-end tests for basic client/server echo."""

import time
import pytest

import jsocket


class EchoServer(jsocket.ThreadedServer):
    """Minimal echo server for tests."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.timeout = 2.0
        self.is_connected = False

    def _process_message(self, obj):
        if obj != '':
            if obj.get('message') == 'new connection':
                self.is_connected = True
            # echo back if present
            if 'echo' in obj:
                return obj
        return None


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_end_to_end_echo_and_connection():
    """Server accepts a connection and echoes payloads end-to-end."""
    try:
        server = EchoServer(address='127.0.0.1', port=0)
    except PermissionError as e:
        pytest.skip(f"Socket creation blocked: {e}")

    client = None
    # Discover the ephemeral port chosen by the OS
    _, port = server.socket.getsockname()
    server.start()

    try:
        client = jsocket.JsonClient(address='127.0.0.1', port=port)
        assert client.connect() is True

        # Signal connection and wait briefly for server to process
        client.send_obj({"message": "new connection"})
        time.sleep(0.2)
        assert server.is_connected is True

        # Echo round-trip
        payload = {"echo": "hello", "i": 1}
        client.send_obj(payload)

        # Server only echoes when _process_message returns; give it a moment
        # and then read the response
        echoed = client.read_obj()
        assert echoed == payload
    finally:
        # Cleanup
        if client is not None:
            try:
                client.close()
            except OSError:
                pass
        server.stop()
        server.join(timeout=3)
