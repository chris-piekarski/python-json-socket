"""Pytest: multiple clients reconnect with staggered delays (poor man's perf test)."""

import random
import threading
import time
import pytest

import jsocket


class EchoWorker(jsocket.ServerFactoryThread):
    """Echo worker for concurrent reconnect testing."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.timeout = 0.5

    def _process_message(self, obj):
        if isinstance(obj, dict) and "echo" in obj:
            return obj
        return None


def _client_roundtrip(port, client_id, prefix, count):
    client = None
    try:
        client = jsocket.JsonClient(address="127.0.0.1", port=port)
        assert client.connect() is True
        for i in range(count):
            payload = {"echo": f"{client_id}-{prefix}-{i}"}
            client.send_obj(payload)
            assert client.read_obj() == payload
    finally:
        if client is not None:
            try:
                client.close()
            except OSError:
                pass


def _run_client_sequence(context, client_id, delay):
    try:
        context["start_event"].wait()
        _client_roundtrip(context["port"], client_id, "first", 3)
        time.sleep(delay)
        _client_roundtrip(context["port"], client_id, "second", 2)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        with context["errors_lock"]:
            context["errors"].append(exc)


def _spawn_clients(context, delays):
    threads = []
    for i, delay in enumerate(delays):
        thread = threading.Thread(
            target=_run_client_sequence,
            args=(context, i, delay),
        )
        threads.append(thread)
        thread.start()
    return threads


def _join_clients(threads, errors):
    for thread in threads:
        thread.join(timeout=5)
    for thread in threads:
        if thread.is_alive():
            errors.append(RuntimeError("client thread did not finish"))


@pytest.mark.integration
@pytest.mark.timeout(20)
def test_serverfactory_many_clients_reconnect_with_random_delays():
    """Ten clients send echoes, disconnect, and reconnect after random delays."""
    try:
        server = jsocket.ServerFactory(EchoWorker, address="127.0.0.1", port=0)
    except PermissionError as e:
        pytest.skip(f"Socket creation blocked: {e}")

    _, port = server.socket.getsockname()
    server.start()

    num_clients = 10
    rng = random.Random(1337)
    delays = [rng.uniform(0.1, 0.6) for _ in range(num_clients)]

    start_event = threading.Event()
    errors = []
    errors_lock = threading.Lock()
    context = {
        "port": port,
        "start_event": start_event,
        "errors": errors,
        "errors_lock": errors_lock,
    }

    threads = _spawn_clients(context, delays)
    try:
        start_event.set()
        _join_clients(threads, errors)
        assert not errors, f"client errors: {errors}"
    finally:
        if hasattr(server, "stop_all"):
            try:
                server.stop_all()
            except OSError:
                pass
        server.stop()
        server.join(timeout=3)
