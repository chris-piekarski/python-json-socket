"""Pytest: client reconnects after server restart."""

import socket
import time
import pytest

import jsocket


class EchoServer(jsocket.ThreadedServer):
    """Echo server used to verify reconnects after restart."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.timeout = 0.5

    def _process_message(self, obj):
        if isinstance(obj, dict) and "echo" in obj:
            return obj
        return None


@pytest.mark.integration
@pytest.mark.timeout(15)
def test_client_reconnects_after_server_restart():
    """Client can reconnect after the server stops and restarts."""
    try:
        server = EchoServer(address="127.0.0.1", port=0)
    except PermissionError as e:
        pytest.skip(f"Socket creation blocked: {e}")

    client = None
    _, port = server.socket.getsockname()
    server.start()

    try:
        client = jsocket.JsonClient(address="127.0.0.1", port=port)
        client.timeout = 0.5
        assert client.connect() is True

        payload = {"echo": "first"}
        client.send_obj(payload)
        assert client.read_obj() == payload

        # Stop server while the client is still connected.
        server.stop()
        server.join(timeout=3)

        # The client should observe a failure when talking to a stopped server.
        saw_disconnect = False
        try:
            client.send_obj({"echo": "after-stop"})
            client.read_obj()
        except (OSError, RuntimeError, socket.timeout):
            saw_disconnect = True
        assert saw_disconnect is True

        # Wait a few seconds before restarting.
        time.sleep(2.0)

        # Restart server on the same port.
        server = EchoServer(address="127.0.0.1", port=port)
        server.start()

        # Reconnect the client without explicitly recreating it.
        assert client.connect() is True

        payload2 = {"echo": "second"}
        client.send_obj(payload2)
        assert client.read_obj() == payload2
    finally:
        if client is not None:
            try:
                client.close()
            except OSError:
                pass
        if server is not None:
            server.stop()
            server.join(timeout=3)
