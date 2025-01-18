from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

import aiofiles
from aiohttp import ClientSession, ClientTimeout, TCPConnector

if TYPE_CHECKING:
    from collections.abc import Sequence
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
        tasks = [_stream_file(session, url, filepath) for url, filepath in zip(urls, files)]
        await asyncio.gather(*tasks)


def is_jupyter_kernel():
    """Check if the code is running in a Jupyter kernel (not IPython terminal)."""
    try:
        from IPython import get_ipython  # pyright: ignore[reportPrivateImportUsage]

        ipython = get_ipython()
    except (ImportError, NameError):
        return False
    if ipython is None:
        return False
    return "Terminal" not in ipython.__class__.__name__


def _get_or_create_event_loop() -> tuple[asyncio.AbstractEventLoop, bool]:
    """Create an event loop."""
    try:
        loop = asyncio.get_running_loop()
        new_loop = False
    except RuntimeError:
        loop = asyncio.new_event_loop()
        new_loop = True
    asyncio.set_event_loop(loop)
    if is_jupyter_kernel():
        import nest_asyncio

        nest_asyncio.apply(loop)
    return loop, new_loop


def stream_write(urls: Sequence[str], file_paths: Sequence[Path]) -> None:
    """Download multiple files concurrently by streaming their content to disk."""
    parent_dirs = {filepath.parent for filepath in file_paths}
    for parent_dir in parent_dirs:
        parent_dir.mkdir(parents=True, exist_ok=True)

    loop, is_new_loop = _get_or_create_event_loop()

    try:
        loop.run_until_complete(_stream_session(urls, file_paths))
    finally:
        if is_new_loop:
            loop.close()
