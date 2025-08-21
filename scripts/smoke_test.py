import logging
import time
import threading

import jsocket


logger = logging.getLogger("smoke")
logger.setLevel(logging.DEBUG)
logging.basicConfig(level=logging.DEBUG, format='[%(levelname)s] %(message)s')


class MyServer(jsocket.ThreadedServer):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.timeout = 2.0
        self.isConnected = False

    def _process_message(self, obj):
        if obj != '':
            if obj.get('message') == 'new connection':
                logger.info("server: new connection message")
                self.isConnected = True


def main():
    server = MyServer()
    server.start()
    time.sleep(0.5)

    client = jsocket.JsonClient()
    assert client.connect(), "client could not connect"

    # Scenario: Start Server
    client.send_obj({"message": "new connection"})
    # Give server time to process
    time.sleep(0.2)
    assert server.isConnected is True, "server did not observe connection"

    # Scenario: Server Response
    server.send_obj({"message": "welcome"})
    msg = client.read_obj()
    assert msg == {"message": "welcome"}, f"unexpected message: {msg}"

    # Scenario: Stop Server
    server.stop()
    server.join(timeout=3)
    assert not server._isAlive, "server thread still alive"
    client.close()
    logger.info("smoke test OK")


if __name__ == "__main__":
    main()

