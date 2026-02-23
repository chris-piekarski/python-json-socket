import argparse
import json
import logging
import secrets
import socket
import struct
import sys
import threading
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import jsocket
from jsocket import jsocket_base


logger = logging.getLogger("jsocket.net_client")
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

PERF_PAD_RANGES = (
    (0, 0),
    (8, 64),
    (64, 256),
    (256, 1024),
    (1024, 4096),
    (4096, 16384),
    (16384, 65536),
    (65536, 131072),
)
ADAPTIVE_SLOW_PAD_RANGE = (0, 256)
ADAPTIVE_BURST_PAD_RANGE = (0, 8192)
ADAPTIVE_LARGE_PAD_RANGE = (65536, 262144)
ERROR_RATE = 0.05


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Minimal JSON socket client for quick network testing.",
    )
    parser.add_argument("host", help="Server IP or hostname")
    parser.add_argument(
        "--port",
        type=int,
        default=5491,
        help="Server port (default: 5491)",
    )
    parser.add_argument(
        "--message",
        help="JSON payload to send (defaults to {\"message\": \"ping\"})",
    )
    parser.add_argument(
        "--mode",
        choices=("ping", "performance", "adaptive"),
        default="ping",
        help="Client mode (default: ping)",
    )
    parser.add_argument(
        "--num",
        type=int,
        default=1,
        help="Number of clients to run in parallel (default: 1)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=100,
        help="Messages per client in performance mode (default: 100)",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=2,
        help="Adaptive mode cycles per client (default: 2)",
    )
    parser.add_argument(
        "--error",
        type=int,
        default=0,
        help="Enable random error injection when set to 1 (default: 0)",
    )
    parser.add_argument(
        "--read",
        type=int,
        default=1,
        help="Read responses when set to 1 (default: 1). Set to 0 to skip reads.",
    )
    return parser.parse_args(argv)


def random_hex(min_len=4, max_len=64):
    length = secrets.randbelow(max_len - min_len + 1) + min_len
    return secrets.token_hex((length + 1) // 2)[:length]


def random_pad_size(min_len, max_len):
    if max_len <= min_len:
        return min_len
    return secrets.randbelow(max_len - min_len + 1) + min_len


def random_pad_from_ranges(ranges):
    min_len, max_len = secrets.choice(ranges)
    return random_pad_size(min_len, max_len)


def payload_from_message(raw, data):
    if raw is None:
        return {"data": data}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {"message": raw}
    if isinstance(payload, dict):
        payload["data"] = data
        return payload
    return {"data": data, "message": payload}


def _connect_client(host, port, client_id):
    client = jsocket.JsonClient(address=host, port=port)
    if not client.connect():
        raise RuntimeError(f"client {client_id} could not connect to {host}:{port}")
    logger.info("client %s connected to %s:%s", client_id, host, port)
    return client


def _make_payload(client_id, seq, label, pad_size):
    data = random_hex()
    payload = {
        "client": client_id,
        "seq": seq,
        "label": label,
        "data": data,
    }
    if pad_size:
        payload["pad"] = "x" * pad_size
    return payload, data


def _extract_response_data(response):
    if isinstance(response, dict):
        return response.get("data")
    if isinstance(response, str):
        return response
    return None


def _send_and_expect(client, payload, expected_data, read_response):
    client.send_obj(payload)
    if not read_response:
        return None
    response = client.read_obj()
    echoed = _extract_response_data(response)
    if echoed != expected_data:
        raise RuntimeError(f"unexpected response data {echoed!r} (expected {expected_data!r})")
    return response


def _send_corrupt_payload(client, payload):
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    mode = secrets.choice(("bad_crc", "bad_header", "invalid_json"))
    if mode == "invalid_json":
        raw = b"{"
    checksum = zlib.crc32(raw) & 0xFFFFFFFF
    if mode == "bad_crc":
        checksum ^= 0xFFFFFFFF
    magic = jsocket_base.FRAME_MAGIC
    if mode == "bad_header":
        magic = b"BAD0"
    header = struct.pack(jsocket_base.FRAME_HEADER_FMT, magic, len(raw), checksum)
    conn = client.conn
    conn.sendall(header)
    conn.sendall(raw)


def _send_maybe_with_error(client, payload, expected_data, enable_errors, read_response):
    if enable_errors and secrets.randbelow(1000) < int(ERROR_RATE * 1000):
        _send_corrupt_payload(client, payload)
        return False
    _send_and_expect(client, payload, expected_data, read_response)
    return True


def _send_partial_payload(client, payload):
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    checksum = zlib.crc32(raw) & 0xFFFFFFFF
    header = struct.pack(jsocket_base.FRAME_HEADER_FMT, jsocket_base.FRAME_MAGIC, len(raw), checksum)
    conn = client.conn
    conn.sendall(header)
    cutoff = max(1, len(raw) // 2)
    conn.sendall(raw[:cutoff])


def _wait_for_disconnect(client, max_wait=5.0):
    deadline = time.monotonic() + max_wait
    conn = client.conn
    while time.monotonic() < deadline:
        try:
            chunk = conn.recv(1)
            if not chunk:
                return True
        except socket.timeout:
            continue
        except OSError:
            return True
    return False


def _run_ping(client_id, args):
    data = random_hex()
    payload = payload_from_message(args.message, data)
    client = _connect_client(args.host, args.port, client_id)
    try:
        logger.info("client %s sent %s", client_id, payload)
        response = _send_and_expect(client, payload, data, args.read == 1)
    finally:
        client.close()

    if args.num == 1 and response is not None:
        print(response)
    else:
        if response is not None:
            logger.info("client %s received %s", client_id, response)


def _run_performance(client_id, args):
    client = _connect_client(args.host, args.port, client_id)
    start = time.monotonic()
    try:
        for i in range(args.count):
            pad_size = random_pad_from_ranges(PERF_PAD_RANGES)
            payload, data = _make_payload(client_id, i, "perf", pad_size)
            ok = _send_maybe_with_error(client, payload, data, args.error == 1, args.read == 1)
            if not ok:
                client.close()
                client = _connect_client(args.host, args.port, client_id)
            if i and i % 100 == 0:
                logger.info("client %s progress %s/%s", client_id, i, args.count)
    finally:
        client.close()
    elapsed = max(time.monotonic() - start, 1e-6)
    rate = args.count / elapsed
    logger.info(
        "client %s performance %s messages in %.2fs (%.1f msg/s)",
        client_id,
        args.count,
        elapsed,
        rate,
    )


def _adaptive_cycle(client_id, args, cycle_index):
    seq = cycle_index * 10000
    client = _connect_client(args.host, args.port, client_id)
    try:
        for i in range(5):
            pad_size = random_pad_size(*ADAPTIVE_SLOW_PAD_RANGE)
            payload, data = _make_payload(client_id, seq, "slow", pad_size)
            ok = _send_maybe_with_error(client, payload, data, args.error == 1, args.read == 1)
            if not ok:
                client.close()
                client = _connect_client(args.host, args.port, client_id)
            seq += 1
            time.sleep(1.0)
    finally:
        client.close()

    time.sleep(0.5)

    # Force at least one server-side recv timeout by sending a partial frame.
    client = _connect_client(args.host, args.port, client_id)
    try:
        pad_size = random_pad_size(256, 4096)
        payload, _ = _make_payload(client_id, seq, "timeout", pad_size)
        _send_partial_payload(client, payload)
        _wait_for_disconnect(client, max_wait=6.0)
        seq += 1
    finally:
        client.close()

    time.sleep(0.5)

    client = _connect_client(args.host, args.port, client_id)
    try:
        for i in range(25):
            pad_size = random_pad_size(*ADAPTIVE_BURST_PAD_RANGE)
            payload, data = _make_payload(client_id, seq, "burst", pad_size)
            ok = _send_maybe_with_error(client, payload, data, args.error == 1, args.read == 1)
            if not ok:
                client.close()
                client = _connect_client(args.host, args.port, client_id)
            seq += 1
        for i in range(3):
            pad_size = random_pad_size(*ADAPTIVE_LARGE_PAD_RANGE)
            payload, data = _make_payload(client_id, seq, "large", pad_size)
            ok = _send_maybe_with_error(client, payload, data, args.error == 1, args.read == 1)
            if not ok:
                client.close()
                client = _connect_client(args.host, args.port, client_id)
            seq += 1
            time.sleep(0.2)
    finally:
        client.close()

    logger.info("client %s adaptive cycle %s complete", client_id, cycle_index + 1)


def _run_adaptive(client_id, args):
    for cycle_index in range(args.cycles):
        _adaptive_cycle(client_id, args, cycle_index)


def _client_worker(client_id, args, results, lock):
    ok = True
    try:
        if args.mode == "ping":
            _run_ping(client_id, args)
        elif args.mode == "performance":
            _run_performance(client_id, args)
        else:
            _run_adaptive(client_id, args)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        ok = False
        logger.error("client %s failed: %s", client_id, exc)
    with lock:
        results.append(ok)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    if args.num < 1:
        logger.error("--num must be >= 1")
        return 2
    if args.count < 1:
        logger.error("--count must be >= 1")
        return 2
    if args.cycles < 1:
        logger.error("--cycles must be >= 1")
        return 2

    threads = []
    results = []
    lock = threading.Lock()
    for i in range(args.num):
        client_id = i + 1
        t = threading.Thread(
            target=_client_worker,
            args=(client_id, args, results, lock),
            daemon=False,
        )
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    if not results or not all(results):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
