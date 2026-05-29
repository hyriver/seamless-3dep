"""Top-level package for Seamless3dep."""

from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from seamless_3dep.seamless_3dep import (
        Get3DEPErrors,
        build_vrt,
        decompose_bbox,
        elevation_bygrid,
        get_dem,
        get_global_dem,
        get_image_server,
        get_map,
        tiffs_to_da,
    )

try:
    __version__ = version("seamless_3dep")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

# ---------------------------------------------------------------------------
# Lazy public API: heavy imports are deferred until first access.  The
# TYPE_CHECKING block above gives pyright/mypy full visibility without
# executing any imports at runtime.
# ---------------------------------------------------------------------------

_LAZY_IMPORTS: dict[str, tuple[str, str | None]] = {
    "Get3DEPErrors": ("seamless_3dep.seamless_3dep", "Get3DEPErrors"),
    "build_vrt": ("seamless_3dep.seamless_3dep", "build_vrt"),
    "decompose_bbox": ("seamless_3dep.seamless_3dep", "decompose_bbox"),
    "elevation_bygrid": ("seamless_3dep.seamless_3dep", "elevation_bygrid"),
    "get_global_dem": ("seamless_3dep.seamless_3dep", "get_global_dem"),
    "get_dem": ("seamless_3dep.seamless_3dep", "get_dem"),
    "get_image_server": ("seamless_3dep.seamless_3dep", "get_image_server"),
    "get_map": ("seamless_3dep.seamless_3dep", "get_map"),
    "tiffs_to_da": ("seamless_3dep.seamless_3dep", "tiffs_to_da"),
}

__all__ = [
    "Get3DEPErrors",
    "__version__",
    "build_vrt",
    "decompose_bbox",
    "elevation_bygrid",
    "get_dem",
    "get_global_dem",
    "get_image_server",
    "get_map",
    "tiffs_to_da",
]


def __dir__() -> list[str]:
    return __all__


def __getattr__(name: str) -> object:
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        import importlib

        mod = importlib.import_module(module_path)
        val = mod if attr is None else getattr(mod, attr)
        globals()[name] = val
        return val
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


# ---------------------------------------------------------------------------
# Eager-import override: set EAGER_IMPORT=1 (any non-"0"/non-empty value) to
# load all lazy members immediately.  Useful in CI and for profiling.
# ---------------------------------------------------------------------------
if os.environ.get("EAGER_IMPORT", "") not in ("", "0"):
    for _name in _LAZY_IMPORTS:
        __getattr__(_name)
