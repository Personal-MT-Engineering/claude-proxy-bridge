"""Single entry point — starts all proxy servers and the WebSocket bridge."""

import asyncio
import logging
import signal
import sys

import uvicorn

from src.config import settings
from src.proxy_server import create_proxy_app
from src.ws_bridge import create_bridge_app


def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


async def run_server(app, host: str, port: int, name: str) -> None:
    """Run a uvicorn server programmatically."""
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level=settings.log_level.lower(),
        access_log=False,
    )
    server = uvicorn.Server(config)

    logger = logging.getLogger(__name__)
    logger.info("Starting %s on %s:%d", name, host, port)

    await server.serve()


async def main_async() -> None:
    logger = logging.getLogger(__name__)

    # Verify claude CLI is available
    try:
        cli_path = settings.resolve_claude_cli()
        logger.info("Found Claude CLI: %s", cli_path)
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)

    # Create apps
    proxy_apps = []
    for mc in settings.models:
        app = create_proxy_app(mc)
        proxy_apps.append((app, mc.port, f"{mc.name}-proxy"))

    bridge_app = create_bridge_app()

    # Start all servers concurrently
    tasks = []
    for app, port, name in proxy_apps:
        tasks.append(asyncio.create_task(run_server(app, settings.host, port, name)))
    tasks.append(asyncio.create_task(run_server(bridge_app, settings.host, settings.bridge_port, "ws-bridge")))

    logger.info("=" * 60)
    logger.info("Claude Proxy Bridge is starting up!")
    logger.info("=" * 60)
    for mc in settings.models:
        logger.info("  %-8s → http://%s:%d/v1/chat/completions", mc.name.title(), settings.host, mc.port)
    logger.info("  %-8s → ws://%s:%d/ws", "Bridge", settings.host, settings.bridge_port)
    logger.info("=" * 60)

    # Wait for all servers (they run forever until cancelled)
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Shutting down...")


def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)

    # Windows-specific event loop policy
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Signal handling
    def handle_shutdown(sig, frame):
        logger.info("Received signal %s, shutting down...", sig)
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_shutdown)

    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Interrupted by user, shutting down...")
    except SystemExit:
        pass


if __name__ == "__main__":
    main()
