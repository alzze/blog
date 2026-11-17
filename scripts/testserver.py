#!/usr/bin/env python3
import argparse
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent.parent
RELOAD_PATH = "/__testserver_reload__"
RELOAD_SCRIPT = """
<script>
(() => {
  const version = VERSION;
  async function check() {
    try {
      const response = await fetch('/__testserver_reload__', {cache: 'no-store'});
      if (response.ok && (await response.json()).version !== version) {
        window.location.reload();
        return;
      }
    } catch (_) {}
    window.setTimeout(check, 1000);
  }
  window.setTimeout(check, 1000);
})();
</script>
"""


def snapshot():
    result = {}

    def record(path):
        try:
            stat = path.stat()
        except FileNotFoundError:
            return
        result[path] = (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)

    record(ROOT / "makesite.py")
    for name in ("posts", "templates", "static"):
        for directory, directories, files in os.walk(ROOT / name):
            directories[:] = [d for d in directories if d not in {".git", "__pycache__"}]
            for filename in files:
                record(Path(directory) / filename)
    return result


class DevServer(ThreadingHTTPServer):
    def __init__(self, address):
        self.build_lock = threading.Lock()
        self.version = ""
        super().__init__(address, RequestHandler)

    def build(self, python):
        with self.build_lock:
            print("Building the site...", flush=True)
            result = subprocess.run([python, str(ROOT / "makesite.py")], cwd=ROOT)
            if result.returncode:
                print("Site build failed. Check the error above.", file=sys.stderr)
                return False
            self.version = str(time.time_ns())
            print("Site updated.", flush=True)
            return True


class RequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "dist"), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def response(self, content, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        return io.BytesIO(content)

    def send_head(self):
        with self.server.build_lock:
            url_path = urlsplit(self.path).path
            if url_path == RELOAD_PATH:
                content = json.dumps({"version": self.server.version}).encode("utf-8")
                return self.response(content, "application/json")

            path = Path(self.translate_path(self.path))
            if path.is_dir() and url_path.endswith("/"):
                for index in ("index.html", "index.htm"):
                    if (path / index).is_file():
                        path = path / index
                        break

            if path.is_file() and path.suffix.lower() in {".html", ".htm"}:
                try:
                    content = path.read_bytes()
                except OSError:
                    self.send_error(404, "File unavailable")
                    return None
                script = RELOAD_SCRIPT.replace("VERSION", json.dumps(self.server.version))
                script = script.encode("utf-8")
                closing_body = re.search(br"</body\s*>", content, re.IGNORECASE)
                position = closing_body.start() if closing_body else len(content)
                content = content[:position] + script + content[position:]
                return self.response(content, "text/html; charset=utf-8")

            if "If-Modified-Since" in self.headers:
                del self.headers["If-Modified-Since"]
            return super().send_head()

    def log_request(self, code="-", size="-"):
        if urlsplit(self.path).path != RELOAD_PATH:
            super().log_request(code, size)


def main():
    parser = argparse.ArgumentParser(
        description="Development server with automatic site rebuilds and browser reload."
    )
    parser.add_argument("--host", default="0.0.0.0", help="Listening address")
    parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("Port must be between 0 and 65535")

    python = sys.executable
    venv_python = ROOT / ".venv" / "bin" / "python"
    if sys.prefix == sys.base_prefix and venv_python.is_file():
        python = str(venv_python)

    try:
        server = DevServer((args.host, args.port))
    except OSError as error:
        print(f"Could not start the server: {error}", file=sys.stderr)
        return 1

    with server:
        try:
            previous = snapshot()
            if not server.build(python):
                return 1
        except KeyboardInterrupt:
            return 0

        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        host = args.host if args.host != "0.0.0.0" else "127.0.0.1"
        print(f"\nOpen http://{host}:{server.server_port}", flush=True)
        print("Checking for changes every second. Press Ctrl+C to stop.\n", flush=True)
        try:
            while True:
                time.sleep(1)
                current = snapshot()
                if current != previous:
                    previous = current
                    server.build(python)
        except KeyboardInterrupt:
            print("\nServer stopped.")
        finally:
            server.shutdown()
            worker.join()
    return 0


if __name__ == "__main__":
    sys.exit(main())
