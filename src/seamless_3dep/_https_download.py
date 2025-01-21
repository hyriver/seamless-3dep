"""Download multiple files concurrently by streaming their content to disk."""

from __future__ import annotations

import asyncio
import atexit
import sys
from threading import Event, Thread
from typing import TYPE_CHECKING

import aiofiles
from aiohttp import ClientSession, ClientTimeout, TCPConnector

if TYPE_CHECKING:
    from collections.abc import Coroutine, Sequence
    from pathlib import Path
    from typing import Any

__all__ = ["stream_write"]

CHUNK_SIZE = 1024 * 1024  # Write chunk size of 1 MB
MAX_HOSTS = 4  # Maximum connections to a single host
TIMEOUT = 10 * 60  # Timeout for requests in seconds

if sys.platform == "win32":  # pragma: no cover
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class ServiceError(Exception):
    """Exception raised for download errors."""

    def __init__(self, url: str, err: str) -> None:
        self.message = f"Service error:\nURL: {url}\nERROR: {err}"
        super().__init__(self.message)


class AsyncLoopThread(Thread):
    """A dedicated thread for running asyncio event loop of ``aiohttp``."""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.loop = asyncio.new_event_loop()
        self._running = Event()

    def run(self) -> None:
        """Run the event loop in this thread."""
        asyncio.set_event_loop(self.loop)
        self._running.set()
        try:
            self.loop.run_forever()
        finally:
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            self.loop.close()
            self._running.clear()

    def stop(self) -> None:
        """Stop the event loop thread."""
        if self._running.is_set():
            self.loop.call_soon_threadsafe(self.loop.stop)
            self._running.wait()


async def _stream_file(session: ClientSession, url: str, filepath: Path) -> None:
    """Stream a single file's content to disk."""
    async with session.get(url) as response:
        if response.status != 200:
            raise ServiceError(str(response.url), await response.text())

        remote_size = int(response.headers.get("Content-Length", -1))
        if filepath.exists() and filepath.stat().st_size == remote_size:
            return

        async with aiofiles.open(filepath, "wb") as file:
            async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                await file.write(chunk)


async def _stream_session(urls: Sequence[str], files: Sequence[Path]) -> None:
    """Download multiple files concurrently within a session."""
    async with ClientSession(
        connector=TCPConnector(limit_per_host=MAX_HOSTS), timeout=ClientTimeout(TIMEOUT)
    ) as session:
        tasks = [
            asyncio.create_task(_stream_file(session, url, filepath))
            for url, filepath in zip(urls, files)
        ]
        await asyncio.gather(*tasks)


# Initialize the global event loop thread
_loop_handler = AsyncLoopThread()
_loop_handler.start()
atexit.register(lambda: _loop_handler.stop())


def _run_in_event_loop(coro: Coroutine[Any, Any, None]) -> None:
    """Run a coroutine in the dedicated event loop thread."""
    future = asyncio.run_coroutine_threadsafe(coro, _loop_handler.loop)
    # Raise any exceptions that occurred
    future.result()


def stream_write(urls: Sequence[str], file_paths: Sequence[Path]) -> None:
    """Download multiple files concurrently by streaming their content to disk."""
    parent_dirs = {filepath.parent for filepath in file_paths}
    for parent_dir in parent_dirs:
        parent_dir.mkdir(parents=True, exist_ok=True)

    _run_in_event_loop(_stream_session(urls, file_paths))
