"""Download multiple files concurrently by streaming their content to disk."""

from __future__ import annotations

import asyncio
import atexit
import sys
from threading import Thread
from typing import TYPE_CHECKING, Any

import aiofiles
from aiohttp import ClientSession, ClientTimeout, TCPConnector

if TYPE_CHECKING:
    from collections.abc import Coroutine, Sequence
    from pathlib import Path

__all__ = ["stream_write"]
CHUNK_SIZE = 1024 * 1024  # Default chunk size of 1 MB
MAX_HOSTS = 4  # Maximum connections to a single host (rate-limited service)
TIMEOUT = 10 * 60  # Timeout for requests in seconds

if sys.platform == "win32":  # pragma: no cover
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class ServiceError(Exception):
    """Exception raised for download errors."""

    def __init__(self, url: str, err: str) -> None:
        self.message = (
            f"Service returned the following error:\nURL: {url}\nERROR: {err}" if url else err
        )
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class AsyncLoopThread(Thread):
    """A thread running an asyncio event loop."""

    def __init__(self):
        super().__init__(daemon=True)
        self.loop = asyncio.new_event_loop()

    def run(self):
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_forever()
        finally:
            # Ensure all asynchronous generators are closed
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            self.loop.close()

    def stop(self):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.join()


# Initialize a single global event loop thread
_loop_handler = AsyncLoopThread()
_loop_handler.start()
# Ensure proper cleanup at application exit
atexit.register(
    lambda: _loop_handler.stop() if _loop_handler and _loop_handler.is_alive() else None
)


def _run_in_event_loop(coro: Coroutine[Any, Any, None]) -> None:
    """Run a coroutine in the dedicated asyncio event loop."""
    asyncio.run_coroutine_threadsafe(coro, _loop_handler.loop).result()


async def _stream_file(session: ClientSession, url: str, filepath: Path) -> None:
    """Stream the response to a file, skipping if already downloaded."""
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
    """Download files concurrently."""
    async with ClientSession(
        connector=TCPConnector(limit_per_host=MAX_HOSTS),
        timeout=ClientTimeout(TIMEOUT),
    ) as session:
        tasks = [
            asyncio.create_task(_stream_file(session, url, filepath))
            for url, filepath in zip(urls, files)
        ]
        await asyncio.gather(*tasks)


def stream_write(urls: Sequence[str], file_paths: Sequence[Path]) -> None:
    """Download multiple files concurrently by streaming their content to disk."""
    parent_dirs = {filepath.parent for filepath in file_paths}
    for parent_dir in parent_dirs:
        parent_dir.mkdir(parents=True, exist_ok=True)

    _run_in_event_loop(_stream_session(urls, file_paths))
