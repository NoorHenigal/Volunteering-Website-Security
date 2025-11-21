"""Custom Granian server with Windows event loop compatibility.

This script uses Granian's loop registry to ensure each worker thread
uses SelectorEventLoop on Windows, which is required for psycopg3 compatibility.
"""

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
        # Directly construct SelectorEventLoop
        return asyncio.SelectorEventLoop()
    # On other platforms, use the default event loop
    return asyncio.new_event_loop()


if __name__ == "__main__":
    # Create and configure Granian server
    server = Granian(
        "app.main:app",
        address="127.0.0.1",
        port=8000,
        interface=Interfaces.ASGI,
        workers=1,
    )

    # Start the server
    server.serve()
