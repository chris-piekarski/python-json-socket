python-json-socket (jsocket)
============================

[![CI](https://github.com/chris-piekarski/python-json-socket/actions/workflows/ci.yml/badge.svg)](https://github.com/chris-piekarski/python-json-socket/actions/workflows/ci.yml)
![PyPI](https://img.shields.io/pypi/v/jsocket.svg)
![Python Versions](https://img.shields.io/pypi/pyversions/jsocket.svg)
![License](https://img.shields.io/pypi/l/jsocket.svg)

Simple JSON-over-TCP sockets for Python. This library provides:

- JsonClient/JsonServer: length‑prefixed JSON message framing over TCP
- ThreadedServer: a single-connection server running in its own thread
- ServerFactory/ServerFactoryThread: a per‑connection worker model for multiple clients

It aims to be small, predictable, and easy to integrate in tests or small services.


Install
-------

```
pip install jsocket
```

Requires Python 3.8+.


Quickstart
----------

Echo server with `ThreadedServer` and a client:

```python
import time
import jsocket

class Echo(jsocket.ThreadedServer):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.timeout = 2.0

    # Return a dict to send a response back to the client
    def _process_message(self, obj):
        if isinstance(obj, dict) and 'echo' in obj:
            return obj
        return None

# Bind to an ephemeral port (port=0)
server = Echo(address='127.0.0.1', port=0)
_, port = server.socket.getsockname()
server.start()

client = jsocket.JsonClient(address='127.0.0.1', port=port)
assert client.connect() is True

payload = {"echo": "hello"}
client.send_obj(payload)
assert client.read_obj() == payload

client.close()
server.stop()
server.join()
```

Per‑connection workers with `ServerFactory`:

```python
import jsocket

class Worker(jsocket.ServerFactoryThread):
    def __init__(self):
        super().__init__()
        self.timeout = 2.0

    def _process_message(self, obj):
        if isinstance(obj, dict) and 'message' in obj:
            return {"reply": f"got: {obj['message']}"}

server = jsocket.ServerFactory(Worker, address='127.0.0.1', port=5489)
server.start()
# Connect one or more clients; one Worker is spawned per connection
```


API Highlights
--------------

- JsonClient:
  - `connect()` returns True on success
  - `send_obj(dict)` sends a JSON object
  - `read_obj()` blocks until a full message is received; raises `socket.timeout` or `RuntimeError("socket connection broken")`
  - `timeout` property controls socket timeouts

- ThreadedServer:
  - Subclass and implement `_process_message(self, obj) -> Optional[dict]`
  - Return a dict to send a response; return `None` to send nothing
  - `start()`, `stop()`, `join()` manage the server thread
  - `send_obj(dict)` sends to the currently connected client

- ServerFactory / ServerFactoryThread:
  - `ServerFactoryThread` is a worker that handles one client connection
  - `ServerFactory` accepts connections and spawns a worker per client


Examples and Tests
------------------

- Examples: see `examples/example_servers.py` and `scripts/smoke_test.py`
- Pytest: end-to-end and listener tests under `tests/`
  - Run: `pytest -q`


Behavior-Driven Tests (Behave)
------------------------------

- Steps live under `features/steps/` and environment hooks in `features/environment.py`.
- To run Behave scenarios, add one or more `.feature` files under `features/` and run:
  - `pip install -r requirements-dev.txt`
  - `PYTHONPATH=. behave -f progress2`
- A minimal example feature:

  ```gherkin
  Feature: Echo round-trip
    Scenario: client/server echo
      Given I start the server
      And I connect the client
      When the client sends the object {"echo": "hi"}
      Then the client sees a message {"echo": "hi"}
  ```


Notes
-----

- Message framing uses a 4‑byte big‑endian length header followed by a JSON payload encoded as UTF‑8.
- On disconnect, reads raise `RuntimeError("socket connection broken")` so callers can distinguish cleanly from timeouts.
- Binding with `port=0` lets the OS choose an ephemeral port; find it with `server.socket.getsockname()`.


Links
-----

- PyPI: https://pypi.org/project/jsocket/
- License: see `LICENSE`
