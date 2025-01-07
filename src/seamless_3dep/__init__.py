"""Top-level package for SeamlessDEM."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from seamless_3dep.seamless_3dep import build_vrt, decompose_bbox, get_dem, get_map

try:
    __version__ = version("seamless_3dep")
except PackageNotFoundError:
    __version__ = "999"

__all__ = [
    "__version__",
    "build_vrt",
    "decompose_bbox",
    "get_dem",
    "get_map",
]
