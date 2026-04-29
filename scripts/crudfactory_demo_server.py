from __future__ import annotations

import argparse
import os
import socketserver
from wsgiref.simple_server import WSGIServer, make_server


class QuietWSGIServer(WSGIServer):
    """Small WSGI server class used only for the local CRUDFactory demo."""

    allow_reuse_address = True

    def server_bind(self) -> None:
        """Bind without reverse DNS lookups that can hang local demos."""
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = int(port)
        self.setup_environ()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the CRUDFactory demo server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.django_project.settings")

    from django.core.wsgi import get_wsgi_application

    application = get_wsgi_application()
    server = make_server(
        args.host,
        args.port,
        application,
        server_class=QuietWSGIServer,
    )

    print(f"Serving CRUDFactory demo at http://{args.host}:{args.port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
