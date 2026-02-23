import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import jsocket
from jsocket import tserver as _tserver


logger = logging.getLogger("jsocket.net_server")
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
ANSI_RESET = "\033[0m"
ANSI_GREEN = "\033[32m"
ANSI_YELLOW = "\033[33m"
ANSI_RED = "\033[31m"


def _summarize_payload(obj):
    data = None
    pad_len = 0
    if isinstance(obj, dict):
        data = obj.get("data")
        pad = obj.get("pad")
        if isinstance(pad, str):
            pad_len = len(pad)
    elif isinstance(obj, str):
        data = obj
    data_len = len(data) if isinstance(data, str) else 0
    return data, data_len, pad_len


class EchoWorker(jsocket.ServerFactoryThread):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.timeout = 2.0

    def _process_message(self, obj):
        if isinstance(obj, dict):
            client_id = obj.get("client") or obj.get("client_id")
            client_id = _tserver._normalize_client_id(client_id) if client_id is not None else None
            if client_id:
                _tserver._set_client_identity(self, client_id)
        data, data_len, pad_len = _summarize_payload(obj)
        logger.info("rx data_len=%s pad_len=%s", data_len, pad_len)
        return {"data": data}


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Minimal JSON socket echo server for quick network testing.",
    )
    parser.add_argument(
        "host",
        help="Bind address (use 0.0.0.0 to listen on all interfaces)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5491,
        help="Port to listen on (default: 5491)",
    )
    return parser.parse_args(argv)


def format_stats(stats):
    def colorize(value):
        try:
            num = int(value)
        except (TypeError, ValueError):
            return str(value)
        if num == 0:
            color = ANSI_GREEN
        elif num <= 3:
            color = ANSI_YELLOW
        else:
            color = ANSI_RED
        return f"{color}{num}{ANSI_RESET}"

    lines = [f"client stats: connected_clients={stats.get('connected_clients', 0)}"]
    clients = stats.get("clients") or {}
    if not clients:
        lines.append("  (no clients)")
        return "\n".join(lines)
    for client_id in sorted(clients.keys()):
        client = clients[client_id]
        display_id = client.get("client_id") or client_id
        failures = client.get("failures") or {}
        lines.append(f"  client={display_id}")
        lines.append(
            "    connected={connected} connects={connects} disconnects={disconnects}".format(
                connected=client.get("connected"),
                connects=client.get("connects"),
                disconnects=client.get("disconnects"),
            )
        )
        lines.append(
            "    messages_in={messages_in} messages_out={messages_out}".format(
                messages_in=client.get("messages_in"),
                messages_out=client.get("messages_out"),
            )
        )
        lines.append(
            "    bytes_in={bytes_in} bytes_out={bytes_out}".format(
                bytes_in=client.get("bytes_in"),
                bytes_out=client.get("bytes_out"),
            )
        )
        lines.append(
            "    avg_payload_in={avg_in:.2f} avg_payload_out={avg_out:.2f}".format(
                avg_in=client.get("avg_payload_in", 0.0),
                avg_out=client.get("avg_payload_out", 0.0),
            )
        )
        lines.append(
            "    failures timeout={timeout} bad_write={bad_write} bad_crc={bad_crc} bad_header={bad_header}".format(
                timeout=colorize(failures.get("timeout", 0)),
                bad_write=colorize(failures.get("bad_write", 0)),
                bad_crc=colorize(failures.get("bad_crc", 0)),
                bad_header=colorize(failures.get("bad_header", 0)),
            )
        )
        lines.append(
            "    failures oversize={oversize} invalid_utf8={invalid_utf8} invalid_json={invalid_json}".format(
                oversize=colorize(failures.get("oversize", 0)),
                invalid_utf8=colorize(failures.get("invalid_utf8", 0)),
                invalid_json=colorize(failures.get("invalid_json", 0)),
            )
        )
        lines.append(
            "    failures handler={handler} framing={framing}".format(
                handler=colorize(failures.get("handler", 0)),
                framing=colorize(failures.get("framing", 0)),
            )
        )
        lines.append(
            "    last_connect_ts={last_connect_ts} last_disconnect_ts={last_disconnect_ts}".format(
                last_connect_ts=client.get("last_connect_ts"),
                last_disconnect_ts=client.get("last_disconnect_ts"),
            )
        )
        lines.append(
            "    last_message_ts={last_message_ts} connected_duration={connected_duration:.2f}".format(
                last_message_ts=client.get("last_message_ts"),
                connected_duration=client.get("connected_duration", 0.0),
            )
        )
        lines.append(
            "    total_connected_duration={total_connected_duration:.2f}".format(
                total_connected_duration=client.get("total_connected_duration", 0.0),
            )
        )
    return "\n".join(lines)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])

    try:
        server = jsocket.ServerFactory(EchoWorker, address=args.host, port=args.port)
    except OSError as exc:
        logger.error("failed to bind %s:%s (%s)", args.host, args.port, exc)
        return 1

    server.start()
    logger.info("listening on %s:%s", args.host, args.port)
    try:
        next_report = time.monotonic() + 10.0
        while True:
            time.sleep(0.5)
            now = time.monotonic()
            if now >= next_report:
                logger.info("%s", format_stats(server.get_client_stats()))
                next_report = now + 10.0
    except KeyboardInterrupt:
        logger.info("shutting down")
    finally:
        server.stop()
        server.join(timeout=3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
