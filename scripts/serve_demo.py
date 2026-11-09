"""Serve the offline trace demo on localhost without exposing project secrets."""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from scripts.build_demo_data import ROOT, build


class DemoHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve saved tau2 trace replays locally")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    stats = build()
    demo_dir = Path(ROOT / "demo")
    handler = partial(DemoHandler, directory=str(demo_dir))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"Prepared {stats['catalog_items']} guided traces from {stats['natural_runs']} benchmark runs and {stats['fault_runs']} controlled tests.")
    print(f"Open http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
