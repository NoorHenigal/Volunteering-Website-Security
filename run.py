"""Unified Granian server with Windows event loop compatibility.

This script uses Granian's loop registry to ensure each worker thread
uses SelectorEventLoop on Windows, which is required for psycopg3 compatibility.

Usage:
    python run.py           # Run main application
    python run.py --ui-dev  # Run UI development mode (no database)
"""

import argparse
import asyncio
import sys

from granian import Granian, loops
from granian.constants import Interfaces


@loops.register("auto")
def build_loop() -> asyncio.AbstractEventLoop:
    """Build event loop with Windows compatibility.

    Returns:
        asyncio.AbstractEventLoop: Configured event loop
    """
    if sys.platform == "win32":
        # Directly construct SelectorEventLoop for psycopg3 compatibility
        return asyncio.SelectorEventLoop()
    # On other platforms, use the default event loop
    return asyncio.new_event_loop()


def main() -> None:
    """Parse arguments and start the appropriate server."""
    parser = argparse.ArgumentParser(description="Run the volunteering web application")
    parser.add_argument(
        "--ui-dev",
        action="store_true",
        help="Run in UI development mode (no database required)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host address to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker processes (default: 1)",
    )
    args = parser.parse_args()

    # Select the appropriate application module
    app_path = "app.ui_dev:app" if args.ui_dev else "app.main:app"

    # Create and configure Granian server
    server = Granian(
        app_path,
        address=args.host,
        port=args.port,
        interface=Interfaces.ASGI,
        workers=args.workers,
    )

    # Start the server
    server.serve()


if __name__ == "__main__":
    main()
