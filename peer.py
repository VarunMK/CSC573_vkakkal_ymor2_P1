#!/usr/bin/env python3
import argparse
import socket
import threading
import os
from datetime import datetime
import platform

CRLF = "\r\n"


class P2PPeer:
    def __init__(
        self,
        server_host='localhost',
        server_port=7734,
        rfc_dir=None,
        peer_name=None,
    ):
        self.server_host = server_host
        self.server_port = server_port

        unique_name = peer_name or f"{socket.gethostname()}-{os.getpid()}"
        self.hostname = unique_name
        self.upload_port = None

        self.server_socket = None        # connection to central server
        self.upload_server_socket = None # server socket for GET RFC

        if rfc_dir is None:
            self.rfc_dir = f"{self.hostname}_rfcs"
        else:
            self.rfc_dir = rfc_dir
        os.makedirs(self.rfc_dir, exist_ok=True)

    # -----------------------------
    # Upload server (peer-to-peer)
    # -----------------------------
    def start_upload_server(self):
        self.upload_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.upload_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Bind to any available port
        self.upload_server_socket.bind(('', 0))
        self.upload_port = self.upload_server_socket.getsockname()[1]
        self.upload_server_socket.listen(5)

        print(f"Upload server started on port {self.upload_port}")

        t = threading.Thread(target=self.handle_uploads)
        t.daemon = True
        t.start()

    def handle_uploads(self):
        while True:
            try:
                client_socket, addr = self.upload_server_socket.accept()
                t = threading.Thread(
                    target=self.handle_upload_request, args=(client_socket,)
                )
                t.start()
            except Exception:
                break

    def handle_upload_request(self, client_socket: socket.socket):
        try:
            data = client_socket.recv(4096).decode('utf-8')
            response = self.process_upload_request(data)
            client_socket.sendall(response.encode('utf-8'))
        except Exception:
            pass
        finally:
            client_socket.close()

    def process_upload_request(self, request: str) -> str:
        lines = request.replace("\r\n", "\n").strip().split('\n')
        if not lines:
            return f"P2P-CI/1.0 400 Bad Request{CRLF}{CRLF}"

        request_line = lines[0].split()
        # Expect: GET RFC <num> P2P-CI/1.0
        if len(request_line) < 4 or request_line[0] != "GET" or request_line[1] != "RFC":
            return f"P2P-CI/1.0 400 Bad Request{CRLF}{CRLF}"

        try:
            rfc_num = int(request_line[2])
        except ValueError:
            return f"P2P-CI/1.0 400 Bad Request{CRLF}{CRLF}"

        version = request_line[3]
        if version != "P2P-CI/1.0":
            return f"P2P-CI/1.0 505 P2P-CI Version Not Supported{CRLF}{CRLF}"

        rfc_file = os.path.join(self.rfc_dir, f"rfc{rfc_num}.txt")
        if not os.path.exists(rfc_file):
            return f"P2P-CI/1.0 404 Not Found{CRLF}{CRLF}"

        try:
            with open(rfc_file, 'r') as f:
                content = f.read()

            file_size = len(content.encode('utf-8'))
            last_modified = datetime.utcfromtimestamp(os.path.getmtime(rfc_file)).strftime(
                '%a, %d %b %Y %H:%M:%S GMT'
            )
            current_time = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')

            response_lines = [
                "P2P-CI/1.0 200 OK",
                f"Date: {current_time}",
                f"OS: {platform.system()} {platform.release()}",
                f"Last-Modified: {last_modified}",
                f"Content-Length: {file_size}",
                "Content-Type: text/plain",
                "",
                content,
            ]
            return CRLF.join(response_lines)
        except Exception:
            return f"P2P-CI/1.0 404 Not Found{CRLF}{CRLF}"

    # -----------------------------
    # Connection to central server
    # -----------------------------
    def connect_to_server(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.connect((self.server_host, self.server_port))
        print(f"Connected to server at {self.server_host}:{self.server_port}")

    # -----------------------------
    # P2S operations: ADD / LOOKUP / LIST
    # -----------------------------
    def add_rfc(self, rfc_num: int, title: str):
        lines = [
            f"ADD RFC {rfc_num} P2P-CI/1.0",
            f"Host: {self.hostname}",
            f"Port: {self.upload_port}",
            f"Title: {title}",
            "",
        ]
        request = CRLF.join(lines)

        self.server_socket.sendall(request.encode('utf-8'))
        response = self.server_socket.recv(4096).decode('utf-8')
        print(f"ADD response: {response.strip()}")

    def lookup_rfc(self, rfc_num: int) -> str:
        lines = [
            f"LOOKUP RFC {rfc_num} P2P-CI/1.0",
            f"Host: {self.hostname}",
            f"Port: {self.upload_port}",
            "",
        ]
        request = CRLF.join(lines)

        self.server_socket.sendall(request.encode('utf-8'))
        response = self.server_socket.recv(4096).decode('utf-8')
        print(f"LOOKUP response:\n{response}")
        return response

    def list_rfcs(self) -> str:
        lines = [
            "LIST ALL P2P-CI/1.0",
            f"Host: {self.hostname}",
            f"Port: {self.upload_port}",
            "",
        ]
        request = CRLF.join(lines)

        self.server_socket.sendall(request.encode('utf-8'))
        response = self.server_socket.recv(4096).decode('utf-8')
        print(f"LIST response:\n{response}")
        return response

    # -----------------------------
    # Download from another peer
    # -----------------------------
    def download_rfc(self, rfc_num: int, peer_host: str, peer_port: int) -> bool:
        download_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            download_socket.connect((peer_host, int(peer_port)))

            lines = [
                f"GET RFC {rfc_num} P2P-CI/1.0",
                f"Host: {peer_host}",
                f"OS: {platform.system()} {platform.release()}",
                "",
            ]
            request = CRLF.join(lines)

            download_socket.sendall(request.encode('utf-8'))

            # Read until connection closes
            chunks = []
            while True:
                chunk = download_socket.recv(8192)
                if not chunk:
                    break
                chunks.append(chunk)
            response = b"".join(chunks).decode('utf-8', errors='replace')

            header_sep = f"{CRLF}{CRLF}"
            split_index = response.find(header_sep)
            sep_len = len(header_sep)
            if split_index == -1:
                split_index = response.find("\n\n")
                sep_len = 2

            if split_index == -1:
                self._print_status(400, "Bad Request", f"Malformed response for RFC {rfc_num}")
                return False

            status_line = response[:split_index].splitlines()[0]
            if "200 OK" not in status_line:
                print(status_line)
                return False

            content = response[split_index + sep_len:]

            rfc_file = os.path.join(self.rfc_dir, f"rfc{rfc_num}.txt")
            with open(rfc_file, 'w') as f:
                f.write(content)

            self._print_status(200, "OK", f"RFC {rfc_num} saved to {rfc_file}")
            return True

        except Exception as e:
            self._print_status(400, "Bad Request", f"Download failed for RFC {rfc_num}: {e}")
            return False
        finally:
            download_socket.close()

    # -----------------------------
    # Helper: register local RFC files on startup
    # -----------------------------
    def register_local_rfcs(self):
        if not os.path.exists(self.rfc_dir):
            return

        for filename in os.listdir(self.rfc_dir):
            if filename.startswith("rfc") and filename.endswith(".txt"):
                try:
                    rfc_num = int(filename[3:-4])
                except ValueError:
                    continue

                filepath = os.path.join(self.rfc_dir, filename)
                title = self.extract_rfc_title(filepath) or f"RFC {rfc_num}"
                self.add_rfc(rfc_num, title)

    def extract_rfc_title(self, filepath: str) -> str:
        """
        Attempt to extract the RFC title from the first line of the file.
        """
        try:
            with open(filepath, 'r') as file_obj:
                first_line = file_obj.readline().strip()
        except OSError:
            return None

        if not first_line:
            return None

        if '-' in first_line:
            _, title = first_line.split('-', 1)
            return title.strip() or None

        parts = first_line.split()
        if len(parts) >= 3 and parts[0].upper() == "RFC":
            return " ".join(parts[2:]).strip() or None

        return first_line

    # -----------------------------
    # Main CLI loop
    # -----------------------------
    def run(self):
        self.start_upload_server()
        self.connect_to_server()
        self.register_local_rfcs()

        print("\nP2P Peer started. Commands:")
        print("add <rfc_num> <title> - Add RFC to index")
        print("lookup <rfc_num> - Find peers with RFC")
        print("list - List all RFCs")
        print("download <rfc_num> - Download RFC from peer")
        print("quit - Exit")

        try:
            while True:
                cmd = input("\n> ").strip().split()
                if not cmd:
                    continue

                if cmd[0] == "add" and len(cmd) >= 3:
                    try:
                        rfc_num = int(cmd[1])
                    except ValueError:
                        self._print_status(400, "Bad Request", "RFC number must be integer")
                        continue
                    title = " ".join(cmd[2:])
                    self.add_rfc(rfc_num, title)

                elif cmd[0] == "lookup" and len(cmd) == 2:
                    try:
                        rfc_num = int(cmd[1])
                    except ValueError:
                        self._print_status(400, "Bad Request", "RFC number must be integer")
                        continue
                    self.lookup_rfc(rfc_num)

                elif cmd[0] == "list":
                    if len(cmd) != 1:
                        self._print_status(400, "Bad Request", "LIST takes no arguments")
                        continue
                    self.list_rfcs()

                elif cmd[0] == "download" and len(cmd) == 2:
                    try:
                        rfc_num = int(cmd[1])
                    except ValueError:
                        self._print_status(400, "Bad Request", "RFC number must be integer")
                        continue
                    response = self.lookup_rfc(rfc_num)

                    status_line = self._status_line(response)
                    if "200 OK" not in status_line:
                        self._print_status(404, "Not Found", f"RFC {rfc_num} unavailable")
                        continue

                    entries = self._extract_rfc_entries(response, rfc_num)
                    if not entries:
                        self._print_status(404, "Not Found", f"No peers hosting RFC {rfc_num}")
                        continue

                    print("Available peers:")
                    for idx, entry in enumerate(entries, 1):
                        _, title, host, port = entry
                        print(f"{idx}. {title} ({host}:{port})")

                    selection = input("Select peer [1]: ").strip()
                    if selection:
                        try:
                            choice = int(selection)
                            if not (1 <= choice <= len(entries)):
                                self._print_status(400, "Bad Request", "Selection out of range")
                                continue
                        except ValueError:
                            self._print_status(400, "Bad Request", "Selection must be numeric")
                            continue
                    else:
                        choice = 1

                    _, title, peer_host, peer_port = entries[choice - 1]

                    if self.download_rfc(rfc_num, peer_host, peer_port):
                        # After download, register with server
                        if not title:
                            title = f"RFC {rfc_num}"
                        self.add_rfc(rfc_num, title)

                elif cmd[0] == "quit":
                    break

                else:
                    self._print_status(400, "Bad Request", "Unsupported command or arguments")

        except KeyboardInterrupt:
            pass
        finally:
            if self.server_socket:
                self.server_socket.close()
            if self.upload_server_socket:
                self.upload_server_socket.close()

    def _print_status(self, code: int, phrase: str, message: str = None):
        status_line = f"P2P-CI/1.0 {code} {phrase}"
        if message:
            status_line = f"{status_line}\n{message}"
        print(status_line)

    def _status_line(self, response: str) -> str:
        normalized = response.replace("\r\n", "\n")
        lines = normalized.strip().split('\n')
        return lines[0] if lines else ""

    def _extract_rfc_entries(self, response: str, expected_rfc: int):
        normalized = response.replace("\r\n", "\n")
        lines = [line.strip() for line in normalized.strip().split('\n') if line.strip()]
        entries = []
        for line in lines:
            if not line.startswith("RFC"):
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            try:
                rfc_num = int(parts[1])
            except ValueError:
                continue
            if rfc_num != expected_rfc:
                continue
            host = parts[-2]
            port = parts[-1]
            title = " ".join(parts[2:-2]).strip()
            entries.append((rfc_num, title, host, port))
        return entries


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="P2P-CI peer client")
    parser.add_argument(
        "server_host",
        nargs="?",
        default="localhost",
        help="Hostname or IP of the P2P-CI server (default: localhost)",
    )
    parser.add_argument(
        "--server-port",
        type=int,
        default=7734,
        help="Port of the P2P-CI server (default: 7734)",
    )
    parser.add_argument(
        "--rfc-dir",
        default=None,
        help="Directory holding this peer's RFC files (default: rfcs_<hostname>-<pid>)",
    )
    parser.add_argument(
        "--peer-name",
        default=None,
        help="Override hostname reported to the server (default: host-pid)",
    )

    args = parser.parse_args()

    peer = P2PPeer(
        server_host=args.server_host,
        server_port=args.server_port,
        rfc_dir=args.rfc_dir,
        peer_name=args.peer_name,
    )
    peer.run()
