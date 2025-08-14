import socket
import sys


def send_command(command: str, host: str = "127.0.0.1", port: int = 12345) -> str:
    """Send ``command`` to the stock server and return its response.

    Parameters
    ----------
    command: str
        Command supported by the server (e.g. ``ALL``, ``HELP`` or ``TICKER AAPL``).
    host: str, optional
        Server hostname or IP address. Defaults to ``127.0.0.1``.
    port: int, optional
        Server port. Defaults to ``12345``.
    """
    with socket.create_connection((host, port)) as sock:
        sock.sendall(command.encode("utf-8"))
        chunks = []
        while True:
            data = sock.recv(4096)
            if not data:
                break
            chunks.append(data)
    return b"".join(chunks).decode("utf-8")


def request_all(host: str = "127.0.0.1", port: int = 12345) -> str:
    """Return the full stock dataset from the server."""
    return send_command("ALL", host, port)


def request_ticker(symbol: str, host: str = "127.0.0.1", port: int = 12345) -> str:
    """Return the latest quote for ``symbol`` from the server."""
    return send_command(f"TICKER {symbol}", host, port)


def request_help(host: str = "127.0.0.1", port: int = 12345) -> str:
    """Return the help text listing supported commands."""
    return send_command("HELP", host, port)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python utils/client_example.py <COMMAND> [ARGS] [HOST] [PORT]")
        print("Examples:")
        print("  python utils/client_example.py HELP")
        print("  python utils/client_example.py ALL 127.0.0.1 12345")
        print("  python utils/client_example.py TICKER AAPL 127.0.0.1 12345")
        sys.exit(1)

    cmd = sys.argv[1].upper()
    host = sys.argv[3] if len(sys.argv) > 3 else "127.0.0.1"
    port = int(sys.argv[4]) if len(sys.argv) > 4 else 12345

    if cmd == "ALL":
        print(request_all(host, port))
    elif cmd == "HELP":
        print(request_help(host, port))
    elif cmd == "TICKER":
        if len(sys.argv) < 3:
            print("Ticker symbol required.\nUsage: python utils/client_example.py TICKER <SYMBOL> [HOST] [PORT]")
            sys.exit(1)
        print(request_ticker(sys.argv[2], host, port))
    else:
        print("Unknown command. Use HELP to list available commands.")
