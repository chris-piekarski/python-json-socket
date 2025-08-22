import json
import logging
import time
from behave import given, when, then, use_step_matcher

import jsocket


logger = logging.getLogger("jsocket.behave")
use_step_matcher("re")


# Persist server/client across scenarios for this feature file
SERVER = None
CLIENT = None
SERVER_PORT = None


class MyServer(jsocket.ThreadedServer):
    def __init__(self, **kwargs):
        super(MyServer, self).__init__(**kwargs)
        self.timeout = 2.0
        self.isConnected = False

    def _process_message(self, obj):
        if obj != '':
            if obj.get('message') == "new connection":
                self.isConnected = True


@given(r"I start the server")
def start_server(context):
    global SERVER
    global SERVER_PORT
    # Start a fresh server if one is not present or not alive
    if SERVER is None or not getattr(SERVER, '_isAlive', False):
        # Bind to an ephemeral port to avoid port conflicts
        SERVER = MyServer(address='127.0.0.1', port=0)
        SERVER.start()
        # Discover the chosen port
        _, SERVER_PORT = SERVER.socket.getsockname()
    context.jsonserver = SERVER


@given(r"I connect the client")
def connect_client(context):
    global CLIENT
    global SERVER_PORT
    if CLIENT is None:
        # Ensure we connect to the server's actual port
        if SERVER_PORT is None:
            start_server(context)
        CLIENT = jsocket.JsonClient(address='127.0.0.1', port=SERVER_PORT)
        if not CLIENT.connect():
            raise AssertionError("client could not connect to server")
    context.jsonclient = CLIENT


@when(r"the client sends the object (\{.*\})")
def client_sends_object(context, obj):
    context.jsonclient.send_obj(json.loads(obj))


@when(r"the server sends the object (\{.*\})")
def server_sends_object(context, obj):
    # Ensure a running server and a connected client exist
    start_server(context)
    connect_client(context)
    # Wait briefly until the server has an accepted connection
    t0 = time.time()
    while not context.jsonserver.connected and (time.time() - t0) < 2.0:
        time.sleep(0.05)
    context.jsonserver.send_obj(json.loads(obj))


@then(r"the client sees a message (\{.*\})")
def client_sees_message(context, obj):
    expected = json.loads(obj)
    msg = context.jsonclient.read_obj()
    assert msg == expected, "%s" % expected


@then(r"I see a connection")
def see_connection(context):
    # Give the server a short time to process the prior message
    t0 = time.time()
    while not context.jsonserver.isConnected and (time.time() - t0) < 2.0:
        time.sleep(0.05)
    assert context.jsonserver.isConnected is True, "%s" % False


@given(r"I stop the server")
def stop_server(context):
    global SERVER
    server = SERVER if SERVER is not None else getattr(context, 'jsonserver', None)
    if server is not None:
        server.stop()
        # Give the thread a moment to terminate cleanly
        try:
            server.join(timeout=2.0)
        except Exception:
            pass
    SERVER = server


@then(r"I see a stopped server")
def see_stopped_server(context):
    # Prefer context server, fall back to global
    server = getattr(context, 'jsonserver', None)
    if server is None:
        server = SERVER
    assert server is not None and server._isAlive is False, "%s" % False


@then(r"I close the client")
def close_client(context):
    global CLIENT
    client = CLIENT if CLIENT is not None else getattr(context, 'jsonclient', None)
    if client is not None:
        try:
            client.close()
        except Exception:
            pass
    CLIENT = client
