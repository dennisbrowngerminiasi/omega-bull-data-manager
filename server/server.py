import socket
import json
import time

from stock.stock_data_interface import StockDataInterface

class Server(StockDataInterface):

    def __init__(self, stock_data_manager):
        # we need to make sure to wait for the data to be downloaded
        self.waiting_for_downloading_data = True
        self.package_load = None
        self.stock_data_manager = stock_data_manager
        self.stock_data_manager.register_listener(self)
        self.stock_data_manager.start_downloader_agent()
        self.start_server()

    def on_download_started(self):
        self.waiting_for_downloading_data = True
        self.package_load = None

    def on_download_finished(self):
        all_stock_data = self.stock_data_manager.get_all_stock_data()
        all_stock_data_list = [stock_data.to_list() for stock_data in all_stock_data]
        self.package_load = json.dumps(all_stock_data_list).encode('utf-8')
        self.waiting_for_downloading_data = False

    def start_server(self):
        try:
            # Create a socket
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            # Set a timeout on blocking socket operations
            server_socket.settimeout(300.0)

            # Bind the socket to a specific address
            server_socket.bind(('localhost', 12345))

            # Listen for incoming connections
            server_socket.listen(1)

            print("Server is listening for connections...")

            while True:
                # Accept a connection
                client_socket, client_address = server_socket.accept()
                print(f"Accepted connection from {client_address}")

                if self.waiting_for_downloading_data:
                    client_socket.sendall("Server is busy downloading data. Please wait.".encode('utf-8'))
                    print("Server is busy downloading data. Please wait." + str(client_address))
                    client_socket.close()
                    continue
                else:
                    # Send data in smaller chunks
                    print("Sending data to client: " + str(client_address))
                    for i in range(0, len(self.package_load), 262144):
                        client_socket.sendall(self.package_load[i:i+262144])
                        time.sleep(0.025)
                    client_socket.close()
                    print("Data sent to client: " + str(client_address))

            client_socket.close()
            server_socket.close()

        except Exception as e:
            print(f"Error: {e}")
            return None
        finally:
            # Close the socket
            server_socket.close()
            print('Connection closed')
            print("Server is STOPED")