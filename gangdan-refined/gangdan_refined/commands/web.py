"""gd-web - Start the web server.

Usage:
    gd-web                      # Start on default port 5000
    gd-web --port 8080          # Start on custom port
    gd-web --host 0.0.0.0      # Bind to all interfaces
    gd-web --port 5001 --open  # Start and open browser
"""

from __future__ import annotations

import argparse
import sys


def main(args=None) -> None:
    parser = argparse.ArgumentParser(
        prog="gd-web",
        description="Start the GangDan web server",
    )
    parser.add_argument("--port", "-p", type=int, default=5000, help="Port (default: 5000)")
    parser.add_argument("--host", "-H", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    parser.add_argument("--open", "-o", action="store_true", help="Open browser after starting")
    from .common import add_common_args, init_env
    add_common_args(parser)
    parsed = parser.parse_args(args)
    init_env(parsed)

    from ..core.config import load_config
    load_config()

    try:
        from ..web.app import create_app

        app = create_app()

        if parsed.open:
            import webbrowser
            webbrowser.open(f"http://{parsed.host}:{parsed.port}")

        print(f"[GangDan] Starting web server on {parsed.host}:{parsed.port}", file=sys.stderr)
        app.run(host=parsed.host, port=parsed.port, debug=False, threaded=True)

    except ImportError as e:
        print(f"[GangDan] Web dependencies not installed: {e}", file=sys.stderr)
        print("[GangDan] Install with: pip install gangdan-refined[web]", file=sys.stderr)
        sys.exit(1)