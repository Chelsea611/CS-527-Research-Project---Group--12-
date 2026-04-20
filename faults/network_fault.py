"""
Real Network Fault Handler
- Fault:    Shuts down a real TCP server so connections fail
- Recovery: Restarts the TCP server and verifies a real connection works
"""

import socket
import threading
import time


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class NetworkFaultHandler:
    def __init__(self, host="127.0.0.1", port=None):
        self.host = host
        self.port = port or find_free_port()
        self._server_socket = None
        self._server_thread = None
        self._running = False
        self._is_down = False
        self.start_server()

    def start_server(self):
        # Wait for OS to release the port before rebinding
        for attempt in range(5):
            try:
                self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._server_socket.bind((self.host, self.port))
                self._server_socket.listen(5)
                self._server_socket.settimeout(1.0)
                self._running = True
                self._is_down = False
                self._server_thread = threading.Thread(target=self._serve, daemon=True)
                self._server_thread.start()
                return True
            except OSError:
                time.sleep(0.3 * (attempt + 1))
        return False

    def _serve(self):
        while self._running:
            try:
                conn, _ = self._server_socket.accept()
                conn.send(b"OK")
                conn.close()
            except socket.timeout:
                continue
            except Exception:
                break

    def stop_server(self):
        self._running = False
        self._is_down = True
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
        self._server_socket = None
        if self._server_thread:
            self._server_thread.join(timeout=2.0)
        self._server_thread = None
        time.sleep(0.5)   # let OS release port

    def trigger_fault(self):
        self.stop_server()

    def try_recover(self):
        success = self.start_server()
        if not success:
            return False, "Failed to bind server to port"
        time.sleep(0.3)
        return self._verify_connection()

    def _verify_connection(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            sock.connect((self.host, self.port))
            response = sock.recv(16)
            sock.close()
            if response == b"OK":
                return True, "TCP connection verified — server responding"
            return False, f"Unexpected response: {response}"
        except ConnectionRefusedError:
            return False, "Connection refused — server not up yet"
        except socket.timeout:
            return False, "Connection timed out"
        except Exception as e:
            return False, str(e)

    def is_healthy(self):
        if self._is_down:
            return False
        ok, _ = self._verify_connection()
        return ok
