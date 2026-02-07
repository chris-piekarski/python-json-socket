# pylint: disable=not-callable, missing-function-docstring, duplicate-code
"""Behave step implementations for json socket scenarios.

Note: Pylint is unaware of Behave's decorator callables, and step helpers
intentionally mirror test setup patterns, so we disable those checks here.
"""

import json
import logging
import time
import socket
from behave import given, when, then, use_step_matcher

import jsocket


logger = logging.getLogger("jsocket.behave")
use_step_matcher("re")


class MyServer(jsocket.ThreadedServer):
    """Simple echo server used by Behave scenarios."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not any(key in kwargs for key in ("timeout", "accept_timeout", "recv_timeout")):
            self.timeout = 2.0

    def _process_message(self, obj):
        # Echo payloads that include 'echo' for verification
        if isinstance(obj, dict) and 'echo' in obj:
            return obj
        return None


@given(r"I start the server")
def start_server(context):
    # Bind to an ephemeral port to avoid port conflicts
    context.jsonserver = MyServer(address='127.0.0.1', port=0)
    context.jsonserver.start()
    # Discover the chosen port
    _, context.server_port = context.jsonserver.socket.getsockname()


@given(r"I start the server with accept timeout (\d+(?:\.\d+)?) seconds")
def start_server_with_accept_timeout(context, seconds):
    # Bind to an ephemeral port to avoid port conflicts
    context.jsonserver = MyServer(
        address='127.0.0.1',
        port=0,
        accept_timeout=float(seconds),
    )
    context.jsonserver.start()
    # Discover the chosen port
    _, context.server_port = context.jsonserver.socket.getsockname()


@given(r"I start the server with accept timeout (\d+(?:\.\d+)?) seconds and recv timeout (\d+(?:\.\d+)?) seconds")
def start_server_with_accept_and_recv_timeout(context, accept_seconds, recv_seconds):
    # Bind to an ephemeral port to avoid port conflicts
    context.jsonserver = MyServer(
        address='127.0.0.1',
        port=0,
        accept_timeout=float(accept_seconds),
        recv_timeout=float(recv_seconds),
    )
    context.jsonserver.start()
    # Discover the chosen port
    _, context.server_port = context.jsonserver.socket.getsockname()


@given(r"I connect the client")
def connect_client(context):
    port = getattr(context, 'server_port', None)
    if port is None:
        start_server(context)
        port = context.server_port
    context.jsonclient = jsocket.JsonClient(address='127.0.0.1', port=port)
    assert context.jsonclient.connect() is True, "client could not connect to server"


@when(r"the client sends the object (\{.*\})")
def client_sends_object(context, obj):
    context.jsonclient.send_obj(json.loads(obj))


@when(r"I wait (\d+(?:\.\d+)?) seconds")
def wait_seconds(context, seconds):
    time.sleep(float(seconds))


@when(r"the server sends the object (\{.*\})")
def server_sends_object(context, obj):
    # Wait briefly until the server has an accepted connection
    t0 = time.time()
    while not context.jsonserver.connected and (time.time() - t0) < 2.0:
        time.sleep(0.05)
    context.jsonserver.send_obj(json.loads(obj))


@then(r"the client sees a message (\{.*\})")
def client_sees_message(context, obj):
    expected = json.loads(obj)
    msg = context.jsonclient.read_obj()
    assert msg == expected, f"{expected}"


@then(r"within (\d+(?:\.\d+)?) seconds the server is connected")
def within_seconds_server_connected(context, seconds):
    deadline = time.time() + float(seconds)
    while time.time() < deadline:
        if getattr(context.jsonserver, 'connected', False):
            return
        time.sleep(0.05)
    assert False, "server did not become connected in time"


@given(r"I stop the server")
@when(r"I stop the server")
def stop_server(context):
    server = getattr(context, 'jsonserver', None)
    if server is not None:
        server.stop()
        # Give the thread a moment to terminate cleanly
        try:
            server.join(timeout=2.0)
        except RuntimeError:
            pass


@then(r"the server is stopped")
def see_stopped_server(context):
    server = getattr(context, 'jsonserver', None)
    assert server is not None, "server not initialized"
    # Wait briefly for the thread to terminate
    deadline = time.time() + 2.0
    while server.is_alive() and time.time() < deadline:
        time.sleep(0.05)
    assert not server.is_alive(), "server did not stop in time"


@then(r"I close the client")
def close_client(context):
    client = getattr(context, 'jsonclient', None)
    if client is not None:
        try:
            client.close()
        except OSError:
            pass


@given(r"I disconnect the client")
def disconnect_client(context):
    close_client(context)


@given(r"I connect a new client")
def connect_new_client(context):
    # Replace existing client with a fresh one on the same server port
    port = getattr(context, 'server_port', None)
    assert port is not None, "server port not available; start server first"
    context.jsonclient = jsocket.JsonClient(address='127.0.0.1', port=port)
    assert context.jsonclient.connect() is True, "client could not connect to server"


@when(r"the client attempts to read with timeout (\d+(?:\.\d+)?) seconds")
def client_attempts_read_with_timeout(context, seconds):
    # Set client socket timeout and attempt a read, capturing outcome
    client = getattr(context, 'jsonclient', None)
    assert client is not None, "client not initialized"
    client.timeout = float(seconds)
    context.client_read_exception = None
    context.client_read_value = None
    try:
        context.client_read_value = client.read_obj()
    except Exception as e:  # pylint: disable=broad-exception-caught
        context.client_read_exception = e


@then(r"the client read fails with timeout or disconnect")
def client_read_fails(context):
    e = getattr(context, 'client_read_exception', None)
    # Either a socket.timeout or a RuntimeError("socket connection broken") is acceptable
    assert e is not None, f"client read unexpectedly succeeded: {getattr(context, 'client_read_value', None)!r}"
    acceptable = isinstance(e, socket.timeout) or (
        isinstance(e, RuntimeError) and 'socket connection broken' in str(e)
    )
    assert acceptable, f"unexpected exception type: {type(e)} {e}"
