"""Create and manage connection pools for the seamless-3dep package."""

from __future__ import annotations

import atexit
from dataclasses import dataclass
from threading import Lock
from typing import TYPE_CHECKING, ClassVar, Literal

import rasterio

if TYPE_CHECKING:
    from rasterio.io import DatasetReader
    from rasterio.transform import Affine

Resolution = Literal[10, 30, 60]
VRTLinks = {
    10: "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/USGS_Seamless_DEM_13.vrt",
    30: "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1/TIFF/USGS_Seamless_DEM_1.vrt",
    60: "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/2/TIFF/USGS_Seamless_DEM_2.vrt",
}


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
    def get_dataset_reader(cls, resolution: int) -> DatasetReader:
        """Retrieve or initialize a DatasetReader for the given resolution."""
        if resolution not in cls._instances:
            with cls._lock:
                if resolution not in cls._instances:  # Double-check locking
                    try:
                        pool = rasterio.open(VRTLinks[resolution])
                        cls._instances[resolution] = pool
                        cls._info[resolution] = VRTInfo(
                            bounds=tuple(pool.bounds),
                            transform=pool.transform,
                            nodata=pool.nodata,
                        )
                    except Exception as e:
                        raise RuntimeError(
                            f"Failed to open VRT for resolution {resolution}: {e}"
                        ) from e
        return cls._instances[resolution]

    @classmethod
    def get_vrt_info(cls, resolution: int) -> VRTInfo:
        """Retrieve metadata for the given resolution."""
        _ = cls.get_dataset_reader(resolution)
        return cls._info[resolution]

    @classmethod
    def close(cls):
        """Cleanup the DatasetReaders."""
        with cls._lock:
            for reader in cls._instances.values():
                if reader:
                    reader.close()
            cls._instances.clear()
            cls._info.clear()


atexit.register(VRTPool.close)
