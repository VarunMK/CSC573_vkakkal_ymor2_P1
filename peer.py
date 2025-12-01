#!/usr/bin/env python3
import argparse
import socket
import threading
import os
from datetime import datetime, timezone
import platform

CRLF = "\r\n"


class P2PPeer:
    def __init__(
        self,
        server_host='localhost',
        server_port=7734,
        rfc_dir=None,
        peer_name=None,
        advertised_host='localhost',
        default_protocol_version="PCP-CI/1.0",
    ):
        self.server_host = server_host
        self.server_port = server_port
        self.advertised_host = advertised_host
        self.default_protocol_version = default_protocol_version

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
            return f"{self.default_protocol_version} 400 Bad Request{CRLF}{CRLF}"

        request_line = lines[0].split()
        # Expect: GET RFC <num> <version>
        if len(request_line) < 4 or request_line[0] != "GET" or request_line[1] != "RFC":
            return f"{self.default_protocol_version} 400 Bad Request{CRLF}{CRLF}"

        try:
            rfc_num = int(request_line[2])
        except ValueError:
            return f"{self.default_protocol_version} 400 Bad Request{CRLF}{CRLF}"

        version = request_line[3]
        if version != self.default_protocol_version:
            return f"{self.default_protocol_version} 505 PCP-CI Version Not Supported{CRLF}{CRLF}"

        rfc_file = os.path.join(self.rfc_dir, f"rfc{rfc_num}.txt")
        if not os.path.exists(rfc_file):
            return f"{self.default_protocol_version} 404 Not Found{CRLF}{CRLF}"

        try:
            with open(rfc_file, 'r') as f:
                content = f.read()

            file_size = len(content.encode('utf-8'))
            last_mtime = datetime.fromtimestamp(os.path.getmtime(rfc_file), timezone.utc)
            last_modified = last_mtime.strftime('%a, %d %b %Y %H:%M:%S GMT')
            current_time = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')

            response_lines = [
                f"{self.default_protocol_version} 200 OK",
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
            return f"{self.default_protocol_version} 404 Not Found{CRLF}{CRLF}"

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
    def add_rfc(self, rfc_num: int, version: str):
        rfc_path = os.path.join(self.rfc_dir, f"rfc{rfc_num}.txt")
        if not os.path.exists(rfc_path):
            self._print_status(404, "Not Found", f"Missing file rfc{rfc_num}.txt in {self.rfc_dir}", version)
            return

        title = self.extract_rfc_title(rfc_path) or f"RFC {rfc_num}"

        lines = [
            f"ADD RFC {rfc_num} {version}",
            f"Host: {self.advertised_host}",
            f"Hostname: {self.hostname}",
            f"Port: {self.upload_port}",
            f"Title: {title}",
            "",
        ]
        request = CRLF.join(lines)

        self.server_socket.sendall(request.encode('utf-8'))
        response = self.server_socket.recv(4096).decode('utf-8')
        print(f"ADD response: {response.strip()}")

    def lookup_rfc(self, rfc_num: int, version: str) -> str:
        lines = [
            f"LOOKUP RFC {rfc_num} {version}",
            f"Host: {self.advertised_host}",
            f"Hostname: {self.hostname}",
            f"Port: {self.upload_port}",
            "",
        ]
        request = CRLF.join(lines)

        self.server_socket.sendall(request.encode('utf-8'))
        response = self.server_socket.recv(4096).decode('utf-8')
        print(f"LOOKUP response:\n{response}")
        return response

    def list_rfcs(self, version: str) -> str:
        lines = [
            f"LIST ALL {version}",
            f"Host: {self.advertised_host}",
            f"Hostname: {self.hostname}",
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
    def get_rfc(self, rfc_num: int, peer_host: str, peer_port: int, peer_name: str, version: str) -> bool:
        get_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            get_socket.connect((peer_host, int(peer_port)))

            lines = [
                f"GET RFC {rfc_num} {version}",
                f"Host: {self.advertised_host}",
                f"Hostname: {self.hostname}",
                f"OS: {platform.system()} {platform.release()}",
                "",
            ]
            request = CRLF.join(lines)

            get_socket.sendall(request.encode('utf-8'))

            # Read until connection closes
            chunks = []
            while True:
                chunk = get_socket.recv(8192)
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
                self._print_status(400, "Bad Request", f"Malformed response for RFC {rfc_num}", version)
                return False

            status_line = response[:split_index].splitlines()[0]
            if "200 OK" not in status_line:
                print(status_line)
                return False

            content = response[split_index + sep_len:]

            rfc_file = os.path.join(self.rfc_dir, f"rfc{rfc_num}.txt")
            with open(rfc_file, 'w') as f:
                f.write(content)

            self._print_status(200, "OK", f"RFC {rfc_num} saved to {rfc_file} (from {peer_name})", version)
            return True

        except Exception as e:
            self._print_status(400, "Bad Request", f"GET failed for RFC {rfc_num} from {peer_name}: {e}", version)
            return False
        finally:
            get_socket.close()

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

                self.add_rfc(rfc_num, self.default_protocol_version)

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
        print("add <rfc_num> <protocol> - Add RFC from local file using protocol token")
        print("lookup <rfc_num> <protocol> - Find peers with RFC")
        print("list <protocol> - List all RFCs")
        print("get <rfc_num> <protocol> - Retrieve RFC from peer (uses the same token for LOOKUP/GET)")
        print("quit - Exit")

        try:
            while True:
                cmd = input("\n> ").strip().split()
                if not cmd:
                    continue

                if cmd[0] == "add":
                    if len(cmd) != 3:
                        self._print_status(400, "Bad Request", "Usage: add <rfc_num> <protocol>")
                        continue
                    try:
                        rfc_num = int(cmd[1])
                    except ValueError:
                        self._print_status(400, "Bad Request", "RFC number must be integer")
                        continue
                    version = cmd[2]
                    self.add_rfc(rfc_num, version)

                elif cmd[0] == "lookup" and len(cmd) == 3:
                    try:
                        rfc_num = int(cmd[1])
                    except ValueError:
                        self._print_status(400, "Bad Request", "RFC number must be integer")
                        continue
                    version = cmd[2]
                    self.lookup_rfc(rfc_num, version)

                elif cmd[0] == "list":
                    if len(cmd) != 2:
                        self._print_status(400, "Bad Request", "Usage: list <protocol>")
                        continue
                    version = cmd[1]
                    self.list_rfcs(version)

                elif cmd[0] == "get" and len(cmd) == 3:
                    try:
                        rfc_num = int(cmd[1])
                    except ValueError:
                        self._print_status(400, "Bad Request", "RFC number must be integer")
                        continue
                    version = cmd[2]
                    response = self.lookup_rfc(rfc_num, version)

                    status_line = self._status_line(response)
                    if "200 OK" not in status_line:
                        self._print_status(404, "Not Found", f"RFC {rfc_num} unavailable", version)
                        continue

                    entries = self._extract_rfc_entries(response, rfc_num)
                    if not entries:
                        self._print_status(404, "Not Found", f"No peers hosting RFC {rfc_num}", version)
                        continue

                    print("Available peers:")
                    for idx, entry in enumerate(entries, 1):
                        _, title, peer_name, host, port = entry
                        print(f"{idx}. {title} ({peer_name} @ {host}:{port})")

                    selection = input("Select peer [1]: ").strip()
                    if selection:
                        try:
                            choice = int(selection)
                            if not (1 <= choice <= len(entries)):
                                self._print_status(400, "Bad Request", "Selection out of range", version)
                                continue
                        except ValueError:
                            self._print_status(400, "Bad Request", "Selection must be numeric", version)
                            continue
                    else:
                        choice = 1

                    _, _, peer_name, peer_host, peer_port = entries[choice - 1]

                    if self.get_rfc(rfc_num, peer_host, peer_port, peer_name, version):
                        # After GET, register with server
                        self.add_rfc(rfc_num, self.default_protocol_version)

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

    def _print_status(self, code: int, phrase: str, message: str = None, version: str = None):
        protocol = version or self.default_protocol_version
        status_line = f"{protocol} {code} {phrase}"
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
            if len(parts) < 6:
                continue
            try:
                rfc_num = int(parts[1])
            except ValueError:
                continue
            if rfc_num != expected_rfc:
                continue
            peer_host = parts[-2]
            peer_port = parts[-1]
            peer_name = parts[-3]
            title = " ".join(parts[2:-3]).strip()
            entries.append((rfc_num, title, peer_name, peer_host, peer_port))
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
        help=(
            "Directory holding this peer's RFC files (default: <peer-name>_rfcs if "
            "--peer-name is supplied, otherwise <hostname>-<pid>_rfcs)."
        ),
    )
    parser.add_argument(
        "--peer-name",
        default=None,
        help="Override hostname reported to the server (default: host-pid)",
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="Actual host/IP advertised for this peer's uploads (default: localhost)",
    )
    parser.add_argument(
        "--default-protocol-version",
        default="PCP-CI/1.0",
        help="Protocol token used for automatic requests (default: PCP-CI/1.0)",
    )

    args = parser.parse_args()

    peer = P2PPeer(
        server_host=args.server_host,
        server_port=args.server_port,
        rfc_dir=args.rfc_dir,
        peer_name=args.peer_name,
        advertised_host=args.host,
        default_protocol_version=args.default_protocol_version,
    )
    peer.run()
