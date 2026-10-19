"""Local test endpoints only. No outbound connections, no forwarding to a PC proxy."""
import http.server
import threading
import time


class Proxy(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        data = b"ANDROID_SETUP_TEST_PROXY"
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def do_CONNECT(self):
        # Mihomo uses CONNECT for HTTP upstream nodes, even for plain HTTP targets.
        # Simulate one reserved test destination locally; never open an outbound socket.
        if self.path != "198.51.100.1:80":
            self.send_error(501, "Test fixture does not forward traffic")
            return
        self.connection.settimeout(10)
        self.send_response(200, "Connection established")
        self.end_headers()
        self.wfile.flush()
        request = self.rfile.readline(8192)
        for _ in range(100):
            if self.rfile.readline(8192) in (b"\r\n", b"\n", b""):
                break
        if request.startswith(b"GET "):
            data = b"ANDROID_SETUP_TEST_PROXY"
            self.wfile.write(b"HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: "
                             + str(len(data)).encode() + b"\r\n\r\n" + data)
            self.wfile.flush()
        self.close_connection = True
    def log_message(self, *args): pass


class Direct(Proxy):
    def do_GET(self):
        data = b"ANDROID_SETUP_TEST_DIRECT"
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    servers = [http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
               for port, handler in ((19090, Proxy), (19091, Direct))]
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    print("Local non-forwarding fixtures ready on 19090/19091", flush=True)
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        for server in servers: server.shutdown(); server.server_close()
