"""Create and manage connection pools for the seamless-3dep package."""

from __future__ import annotations

import atexit
from dataclasses import dataclass
from threading import Lock
from typing import TYPE_CHECKING, ClassVar, Literal

import rasterio
from urllib3 import HTTPSConnectionPool, Retry

if TYPE_CHECKING:
    from rasterio.io import DatasetReader
    from rasterio.transform import Affine

Resolution = Literal[10, 30, 60]
VRTLinks = {
    10: "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/USGS_Seamless_DEM_13.vrt",
    30: "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1/TIFF/USGS_Seamless_DEM_1.vrt",
    60: "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/2/TIFF/USGS_Seamless_DEM_2.vrt",
}


class HTTPSPool:
    """Singleton to manage an HTTPS connection pool."""

    _instance = None
    _lock = Lock()

    @classmethod
    def get_instance(cls) -> HTTPSConnectionPool:
        """Retrieve or create a shared HTTPS connection pool."""
        if cls._instance is None:
            with cls._lock:
                # Double-check locking
                if cls._instance is None:
                    cls._instance = HTTPSConnectionPool(
                        "elevation.nationalmap.gov",
                        maxsize=10,
                        block=True,
                        retries=Retry(
                            total=5,
                            backoff_factor=0.5,
                            status_forcelist=[500, 502, 504],
                            allowed_methods=["HEAD", "GET"],
                        ),
                    )
        return cls._instance


@dataclass
class VRTInfo:
    """Metadata for a VRT dataset."""

    bounds: tuple[float, float, float, float]
    transform: Affine
    nodata: float


class VRTPool:
    _instances: ClassVar[dict[int, DatasetReader]] = {}
    _info: ClassVar[dict[int, VRTInfo]] = {}
    _lock: ClassVar[Lock] = Lock()

    @classmethod
    def get_pool(cls, resolution: int) -> DatasetReader:
        """Retrieve or initialize a DatasetReader for the given resolution."""
        if resolution not in cls._instances:
            with cls._lock:
                if resolution not in cls._instances:  # Double-check locking
                    pool = rasterio.open(VRTLinks[resolution])
                    cls._instances[resolution] = pool
                    cls._info[resolution] = VRTInfo(
                        bounds=tuple(pool.bounds),
                        transform=pool.transform,
                        nodata=pool.nodata,
                    )
        return cls._instances[resolution]

    @classmethod
    def get_vrt_info(cls, resolution: int) -> VRTInfo:
        """Retrieve metadata for the given resolution."""
        return cls._info[resolution]


HTTPs = HTTPSPool.get_instance()


def _cleanup_pools():
    """Cleanup the HTTPS connection pool and DatasetReaders."""
    with HTTPSPool._lock:
        if HTTPs:
            HTTPs.close()
    with VRTPool._lock:
        for reader in VRTPool._instances.values():
            if reader:
                reader.close()


atexit.register(_cleanup_pools)
