#!/usr/bin/env python3
import socket
import threading
from datetime import datetime, timezone
import platform

CRLF = "\r\n"
PROTOCOL_VERSION = "PCP-CI/1.0"


class P2PServer:
    def __init__(self, port=7734):
        self.port = port
        # List of active peers: list of (peer_name, host, upload_port)
        self.peers = []
        # RFC index: list of (rfc_num, title, peer_name, host, upload_port)
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
        peer_name = None
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
                if 'Hostname' in headers:
                    peer_name = headers['Hostname']
                elif peer_host and not peer_name:
                    peer_name = peer_host
                if 'Port' in headers:
                    try:
                        peer_port = int(headers['Port'])
                    except ValueError:
                        pass

                if peer_host and peer_port and peer_name and not peer_registered:
                    self.register_peer(peer_name, peer_host, peer_port)
                    peer_registered = True

                self.log_request(peer_name, peer_host, peer_port, addr, data)

                response = self.process_request(data)
                if response:
                    client_socket.sendall(response.encode('utf-8'))

        except Exception as e:
            # You can uncomment this for debugging
            # print(f"Error in handle_client: {e}")
            pass
        finally:
            if peer_name is not None and peer_port is not None and peer_host is not None:
                print(f"Peer {peer_name} ({peer_host}:{peer_port}) disconnected")
                self.remove_peer(peer_name, peer_host, peer_port)
            else:
                print(f"Peer at {addr} disconnected before registration")
            client_socket.close()

    def process_request(self, request: str) -> str:
        normalized = request.replace("\r\n", "\n")
        lines = normalized.strip().split('\n')
        if not lines:
            return self._build_response(400, "Bad Request")

        request_line = lines[0].split()
        if len(request_line) < 3:
            return self._build_response(400, "Bad Request")

        method = request_line[0]
        rfc_part = request_line[1:3]  # e.g. ["RFC", "123"]
        version = request_line[-1]

        if version != PROTOCOL_VERSION:
            return self._build_response(505, "PCP-CI Version Not Supported")

        headers = self.extract_headers(request)

        if method == "ADD":
            return self.handle_add(rfc_part, headers)
        elif method == "LOOKUP":
            return self.handle_lookup(rfc_part, headers)
        elif method == "LIST":
            return self.handle_list(headers)
        else:
            return self._build_response(400, "Bad Request")

    def handle_add(self, rfc_part, headers) -> str:
        if len(rfc_part) < 2 or rfc_part[0] != "RFC":
            return self._build_response(400, "Bad Request")

        # RFC number
        try:
            rfc_num = int(rfc_part[1])
        except ValueError:
            return self._build_response(400, "Bad Request")

        host = headers.get("Host", "")
        peer_name = headers.get("Hostname") or host
        port = headers.get("Port", "")
        title = headers.get("Title", "")

        if not host or not port or not title or not peer_name:
            return self._build_response(400, "Bad Request")

        try:
            port_num = int(port)
        except ValueError:
            return self._build_response(400, "Bad Request")

        with self.lock:
            # Register peer if not already present
            if (peer_name, host, port_num) not in self.peers:
                self.peers.insert(0, (peer_name, host, port_num))

            # Register RFC if not already in index for this peer
            record = (rfc_num, title, peer_name, host, port_num)
            if record not in self.rfc_index:
                self.rfc_index.insert(0, record)

        # Echo back as per spec
        body = f"RFC {rfc_num} {title} {peer_name} {host} {port_num}"
        return self._build_response(200, "OK", body)

    def handle_lookup(self, rfc_part, headers) -> str:
        if len(rfc_part) < 2 or rfc_part[0] != "RFC":
            return self._build_response(400, "Bad Request")

        try:
            rfc_num = int(rfc_part[1])
        except ValueError:
            return self._build_response(400, "Bad Request")

        with self.lock:
            matches = [
                f"RFC {r} {t} {n} {h} {p}"
                for (r, t, n, h, p) in self.rfc_index
                if r == rfc_num
            ]

        if matches:
            body = CRLF.join(matches)
            return self._build_response(200, "OK", body)
        else:
            return self._build_response(404, "Not Found")

    def handle_list(self, headers) -> str:
        with self.lock:
            lines = [
                f"RFC {r} {t} {n} {h} {p}"
                for (r, t, n, h, p) in self.rfc_index
            ]

        body = CRLF.join(lines) if lines else ""
        return self._build_response(200, "OK", body)

    def register_peer(self, peer_name: str, host: str, port: int):
        """
        Ensure a peer entry exists for the active connection.
        """
        with self.lock:
            if (peer_name, host, port) not in self.peers:
                self.peers.insert(0, (peer_name, host, port))

    def log_request(self, peer_name, host, port, addr, raw_request):
        """
        Log which peer sent which request line.
        """
        first_line = raw_request.splitlines()[0].strip() if raw_request else "<empty>"
        if peer_name and port:
            peer_label = f"{peer_name}:{port}"
        elif host and port:
            peer_label = f"{host}:{port}"
        else:
            peer_label = f"{addr}"
        print(f"[REQ] {peer_label} -> {first_line}")

    def remove_peer(self, peer_name: str, host: str, port: int):
        """
        Remove all records for a given (host, port) when a peer disconnects.
        """
        with self.lock:
            self.peers = [
                (n, h, p) for (n, h, p) in self.peers
                if not (n == peer_name and h == host and p == port)
            ]

            self.rfc_index = [
                (r, t, n, h, p)
                for (r, t, n, h, p) in self.rfc_index
                if not (n == peer_name and h == host and p == port)
            ]

    def _build_response(self, status_code: int, phrase: str, body: str = "") -> str:
        """Construct RFC-compliant response with standard headers."""
        if body is None:
            body = ""
        body_str = body
        timestamp = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
        os_info = f"{platform.system()} {platform.release()}"
        body_length = len(body_str.encode('utf-8'))

        header_lines = [
            f"{PROTOCOL_VERSION} {status_code} {phrase}",
            f"Date: {timestamp}",
            f"OS: {os_info}",
            f"Last-Modified: {timestamp}",
            f"Content-Length: {body_length}",
            "Content-Type: text/plain",
        ]

        if body_str:
            response_lines = header_lines + ["", body_str]
        else:
            response_lines = header_lines + [""]

        return CRLF.join(response_lines)


if __name__ == "__main__":
    server = P2PServer()
    server.start()
