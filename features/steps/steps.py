import json
import logging
from behave import given, when, then, use_step_matcher

import jsocket


logger = logging.getLogger("jsocket.behave")
use_step_matcher("re")


class MyServer(jsocket.ThreadedServer):
    def __init__(self):
        super(MyServer, self).__init__()
        self.timeout = 2.0
        self.isConnected = False

    def _process_message(self, obj):
        if obj != '':
            if obj.get('message') == "new connection":
                self.isConnected = True


@given(r"I start the server")
def start_server(context):
    context.jsonserver = MyServer()
    context.jsonserver.start()


@given(r"I connect the client")
def connect_client(context):
    context.jsonclient = jsocket.JsonClient()
    context.jsonclient.connect()


@when(r"the client sends the object (\{.*\})")
def client_sends_object(context, obj):
    context.jsonclient.send_obj(json.loads(obj))


@when(r"the server sends the object (\{.*\})")
def server_sends_object(context, obj):
    context.jsonserver.send_obj(json.loads(obj))


@then(r"the client sees a message (\{.*\})")
def client_sees_message(context, obj):
    expected = json.loads(obj)
    msg = context.jsonclient.read_obj()
    assert msg == expected, "%s" % expected


@then(r"I see a connection")
def see_connection(context):
    assert context.jsonserver.isConnected is True, "%s" % False


@given(r"I stop the server")
def stop_server(context):
    context.jsonserver.stop()


@then(r"I see a stopped server")
def see_stopped_server(context):
    assert context.jsonserver._isAlive is False, "%s" % False


@then(r"I close the client")
def close_client(context):
    context.jsonclient.close()

