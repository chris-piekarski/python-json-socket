import time
import socket
import pytest

import jsocket


class EchoServer(jsocket.ThreadedServer):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.timeout = 2.0
        self.isConnected = False

    def _process_message(self, obj):
        if obj != '':
            if obj.get('message') == 'new connection':
                self.isConnected = True
            # echo back if present
            if 'echo' in obj:
                return obj
        return None


@pytest.mark.timeout(10)
def test_end_to_end_echo_and_connection():
    try:
        server = EchoServer(address='127.0.0.1', port=0)
    except PermissionError as e:
        pytest.skip(f"Socket creation blocked: {e}")

    # Discover the ephemeral port chosen by the OS
    _, port = server.socket.getsockname()
    server.start()

    try:
        client = jsocket.JsonClient(address='127.0.0.1', port=port)
        assert client.connect() is True

        # Signal connection and wait briefly for server to process
        client.send_obj({"message": "new connection"})
        time.sleep(0.2)
        assert server.isConnected is True

        # Echo round-trip
        payload = {"echo": "hello", "i": 1}
        client.send_obj(payload)

        # Server only echoes when _process_message returns; give it a moment
        # and then read the response
        echoed = client.read_obj()
        assert echoed == payload
    finally:
        # Cleanup
        try:
            client.close()
        except Exception:
            pass
        server.stop()
        server.join(timeout=3)
