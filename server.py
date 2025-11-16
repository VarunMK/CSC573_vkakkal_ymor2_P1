#!/usr/bin/env python3
import socket
import threading

CRLF = "\r\n"


class P2PServer:
    def __init__(self, port=7734):
        self.port = port
        # List of active peers: list of (hostname, upload_port)
        self.peers = []
        # RFC index: list of (rfc_num, title, hostname, upload_port)
        self.rfc_index = []
        self.lock = threading.Lock()

    def start(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('', self.port))
        server_socket.listen(5)
        print(f"Server listening on port {self.port}")

        try:
            while True:
                client_socket, addr = server_socket.accept()
                print(f"Connection from {addr}")
                client_thread = threading.Thread(
                    target=self.handle_client, args=(client_socket, addr)
                )
                client_thread.start()
        except KeyboardInterrupt:
            print("Server shutting down")
        finally:
            server_socket.close()

    def extract_headers(self, raw_request: str):
        """
        Helper to parse headers from a P2S request.
        Returns a dict like {"Host": "...", "Port": "...", "Title": "..."}
        """
        headers = {}
        normalized = raw_request.replace("\r\n", "\n")
        lines = normalized.strip().split('\n')
        for line in lines[1:]:
            if ':' in line:
                key, value = line.split(':', 1)
                headers[key.strip()] = value.strip()
        return headers

    def handle_client(self, client_socket: socket.socket, addr):
        """
        Handle all requests from a single peer connection.
        When the peer disconnects, remove its records from the database.
        """
        peer_host = None
        peer_port = None
        peer_registered = False

        try:
            while True:
                data = client_socket.recv(4096).decode('utf-8')
                if not data:
                    break

                # Track Host and Port for cleanup later
                headers = self.extract_headers(data)
                if 'Host' in headers:
                    peer_host = headers['Host']
                if 'Port' in headers:
                    try:
                        peer_port = int(headers['Port'])
                    except ValueError:
                        pass

                if peer_host and peer_port and not peer_registered:
                    self.register_peer(peer_host, peer_port)
                    peer_registered = True

                self.log_request(peer_host, peer_port, addr, data)

                response = self.process_request(data)
                if response:
                    client_socket.sendall(response.encode('utf-8'))

        except Exception as e:
            # You can uncomment this for debugging
            # print(f"Error in handle_client: {e}")
            pass
        finally:
            if peer_host is not None and peer_port is not None:
                print(f"Peer {peer_host}:{peer_port} disconnected")
                self.remove_peer(peer_host, peer_port)
            else:
                print(f"Peer at {addr} disconnected before registration")
            client_socket.close()

    def process_request(self, request: str) -> str:
        normalized = request.replace("\r\n", "\n")
        lines = normalized.strip().split('\n')
        if not lines:
            return f"P2P-CI/1.0 400 Bad Request{CRLF}{CRLF}"

        request_line = lines[0].split()
        if len(request_line) < 3:
            return f"P2P-CI/1.0 400 Bad Request{CRLF}{CRLF}"

        method = request_line[0]
        rfc_part = request_line[1:3]  # e.g. ["RFC", "123"]
        version = request_line[-1]

        if version != "P2P-CI/1.0":
            return f"P2P-CI/1.0 505 P2P-CI Version Not Supported{CRLF}{CRLF}"

        headers = self.extract_headers(request)

        if method == "ADD":
            return self.handle_add(rfc_part, headers)
        elif method == "LOOKUP":
            return self.handle_lookup(rfc_part, headers)
        elif method == "LIST":
            return self.handle_list(headers)
        else:
            return f"P2P-CI/1.0 400 Bad Request{CRLF}{CRLF}"

    def handle_add(self, rfc_part, headers) -> str:
        if len(rfc_part) < 2 or rfc_part[0] != "RFC":
            return f"P2P-CI/1.0 400 Bad Request{CRLF}{CRLF}"

        # RFC number
        try:
            rfc_num = int(rfc_part[1])
        except ValueError:
            return f"P2P-CI/1.0 400 Bad Request{CRLF}{CRLF}"

        host = headers.get("Host", "")
        port = headers.get("Port", "")
        title = headers.get("Title", "")

        if not host or not port or not title:
            return f"P2P-CI/1.0 400 Bad Request{CRLF}{CRLF}"

        try:
            port_num = int(port)
        except ValueError:
            return f"P2P-CI/1.0 400 Bad Request{CRLF}{CRLF}"

        with self.lock:
            # Register peer if not already present
            if (host, port_num) not in self.peers:
                self.peers.insert(0, (host, port_num))

            # Register RFC if not already in index for this peer
            record = (rfc_num, title, host, port_num)
            if record not in self.rfc_index:
                self.rfc_index.insert(0, record)

        # Echo back as per spec
        body = f"RFC {rfc_num} {title} {host} {port_num}"
        return f"P2P-CI/1.0 200 OK{CRLF}{CRLF}{body}{CRLF}{CRLF}"

    def handle_lookup(self, rfc_part, headers) -> str:
        if len(rfc_part) < 2 or rfc_part[0] != "RFC":
            return f"P2P-CI/1.0 400 Bad Request{CRLF}{CRLF}"

        try:
            rfc_num = int(rfc_part[1])
        except ValueError:
            return f"P2P-CI/1.0 400 Bad Request{CRLF}{CRLF}"

        with self.lock:
            matches = [
                f"RFC {r} {t} {h} {p}"
                for (r, t, h, p) in self.rfc_index
                if r == rfc_num
            ]

        if matches:
            body = CRLF.join(matches)
            return f"P2P-CI/1.0 200 OK{CRLF}{CRLF}{body}{CRLF}{CRLF}"
        else:
            return f"P2P-CI/1.0 404 Not Found{CRLF}{CRLF}"

    def handle_list(self, headers) -> str:
        with self.lock:
            lines = [
                f"RFC {r} {t} {h} {p}"
                for (r, t, h, p) in self.rfc_index
            ]

        body = CRLF.join(lines) if lines else ""
        return f"P2P-CI/1.0 200 OK{CRLF}{CRLF}{body}{CRLF}{CRLF}"

    def register_peer(self, host: str, port: int):
        """
        Ensure a peer entry exists for the active connection.
        """
        with self.lock:
            if (host, port) not in self.peers:
                self.peers.insert(0, (host, port))

    def log_request(self, host, port, addr, raw_request):
        """
        Log which peer sent which request line.
        """
        first_line = raw_request.splitlines()[0].strip() if raw_request else "<empty>"
        if host and port:
            peer_label = f"{host}:{port}"
        else:
            peer_label = f"{addr}"
        print(f"[REQ] {peer_label} -> {first_line}")

    def remove_peer(self, host: str, port: int):
        """
        Remove all records for a given (host, port) when a peer disconnects.
        """
        with self.lock:
            self.peers = [
                (h, p) for (h, p) in self.peers
                if not (h == host and p == port)
            ]

            self.rfc_index = [
                (r, t, h, p) for (r, t, h, p) in self.rfc_index
                if not (h == host and p == port)
            ]


if __name__ == "__main__":
    server = P2PServer()
    server.start()
