import json
import socket
import time

from stock.stock_data_interface import StockDataInterface


class Server(StockDataInterface):
    """Simple TCP server to provide stock data to clients.

    The server understands a small set of commands that allow clients to
    retrieve either all available stock data or just the latest quote for a
    specific ticker. Unknown commands result in a help message that lists the
    supported commands.
    """

    def __init__(self, stock_data_manager):
        # Ensure we wait for data to be downloaded before answering requests
        self.waiting_for_downloading_data = True
        self.package_load = None
        self.stock_data_manager = stock_data_manager
        self.stock_data_manager.register_listener(self)
        self.stock_data_manager.start_downloader_agent()
        self.start_server()

    # ------------------------------------------------------------------
    # Callbacks from ``StockDataManager``
    # ------------------------------------------------------------------
    def on_download_started(self):
        self.waiting_for_downloading_data = True
        self.package_load = None

    def on_download_finished(self):
        all_stock_data = self.stock_data_manager.get_all_stock_data()
        all_stock_data_list = [stock_data.to_list() for stock_data in all_stock_data]
        self.package_load = json.dumps(all_stock_data_list).encode("utf-8")
        self.waiting_for_downloading_data = False

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------
    @staticmethod
    def _command_help() -> str:
        """Return formatted description of supported commands."""
        commands = {
            "ALL": "Send all available stock data in JSON format.",
            "TICKER <SYMBOL>": "Send the latest price and volume for the given ticker symbol.",
            "HELP": "List available commands.",
        }
        return "\n".join(f"{cmd} - {desc}" for cmd, desc in commands.items())

    def _latest_ticker_payload(self, ticker: str):
        """Return JSON payload for the latest data of ``ticker``.

        Parameters
        ----------
        ticker: str
            Stock ticker to search for.

        Returns
        -------
        bytes | None
            JSON encoded payload or ``None`` if ticker not found.
        """

        for stock_data in self.stock_data_manager.get_all_stock_data():
            if stock_data.ticker.upper() == ticker.upper():
                row = stock_data.df.iloc[-1]
                payload = {
                    "Ticker": stock_data.ticker,
                    "Date": row["Date"].strftime("%Y-%m-%d")
                    if hasattr(row["Date"], "strftime")
                    else str(row["Date"]),
                    "Open": row["Open"],
                    "High": row["High"],
                    "Low": row["Low"],
                    "Close": row["Close"],
                    "Volume": int(row["Volume"]),
                }
                return json.dumps(payload).encode("utf-8")

        return None

    # ------------------------------------------------------------------
    # Server loop
    # ------------------------------------------------------------------
    def start_server(self):
        server_socket = None
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.settimeout(300.0)
            server_socket.bind(("localhost", 12345))
            server_socket.listen(1)
            print("Server is listening for connections...")

            while True:
                client_socket, client_address = server_socket.accept()
                print(f"Accepted connection from {client_address}")

                if self.waiting_for_downloading_data:
                    msg = "Server is busy downloading data. Please wait."
                    client_socket.sendall(msg.encode("utf-8"))
                    print(msg + str(client_address))
                    client_socket.close()
                    continue

                try:
                    client_socket.settimeout(5.0)
                    command = client_socket.recv(1024).decode("utf-8").strip()

                    if not command or command.upper() == "HELP":
                        client_socket.sendall(self._command_help().encode("utf-8"))

                    elif command.upper() == "ALL":
                        for i in range(0, len(self.package_load), 262144):
                            client_socket.sendall(self.package_load[i : i + 262144])
                            time.sleep(0.025)

                    elif command.upper().startswith("TICKER"):
                        parts = command.split()
                        if len(parts) == 2:
                            data = self._latest_ticker_payload(parts[1])
                            if data:
                                client_socket.sendall(data)
                            else:
                                client_socket.sendall(
                                    f"Ticker {parts[1].upper()} not found".encode("utf-8")
                                )
                        else:
                            client_socket.sendall(b"Usage: TICKER <SYMBOL>")

                    else:
                        msg = f"Unknown command: {command}\n{self._command_help()}"
                        client_socket.sendall(msg.encode("utf-8"))

                except Exception as exc:  # noqa: BLE001
                    err_msg = f"Error processing request: {exc}"
                    client_socket.sendall(err_msg.encode("utf-8"))
                    print(err_msg)
                finally:
                    client_socket.close()
                    print(f"Connection closed: {client_address}")

        except Exception as e:  # noqa: BLE001
            print(f"Error: {e}")
        finally:
            if server_socket is not None:
                server_socket.close()
            print("Server stopped")

