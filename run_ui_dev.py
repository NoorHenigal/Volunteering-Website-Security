"""UI Development server - serves static files without database.

This script runs a lightweight FastAPI server for UI development that:
- Serves static files (CSS, JS, images)
- Renders HTML templates
- Does NOT require database connection
- Does NOT run authentication or API endpoints
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
    # Create and configure Granian server for UI dev mode
    server = Granian(
        "app.ui_dev:app",
        address="127.0.0.1",
        port=8000,
        interface=Interfaces.ASGI,
        workers=1,
    )

    # Start the server
    server.serve()
