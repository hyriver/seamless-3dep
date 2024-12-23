"""Module for getting DEM from USGS's 3D Elevation Program (3DEP) or NASADEM dataset."""

# pyright: reportOperatorIssue=false
from __future__ import annotations

from pathlib import Path
import hashlib
from functools import lru_cache
import math
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

import rasterio
import rasterio.windows

__all__ = ["decompose_bbox", "get", "build_vrt"]


@lru_cache
def _get_bounds(url: str) -> tuple[float, float, float, float]:
    """Get bounds of a VRT file."""
    with rasterio.open(url) as src:
        return tuple(src.bounds)


def _check_bbox(bbox: tuple[float, float, float, float]) -> None:
    """Validate that bbox is in correct form."""
    if (
        not isinstance(bbox, Sequence)
        or len(bbox) != 4
        or not all(isinstance(x, int | float) for x in bbox)
    ):
        raise TypeError(
            "`bbox` must be a tuple of form (west, south, east, north) in decimal degrees."
        )


def _check_bounds(
    bbox: tuple[float, float, float, float], bounds: tuple[float, float, float, float]
) -> None:
    """Validate that bbox is within valid bounds."""
    west, south, east, north = bbox
    bounds_west, bounds_south, bounds_east, bounds_north = bounds
    if not (
        bounds_west <= west < east <= bounds_east and bounds_south <= south < north <= bounds_north
    ):
        raise ValueError(f"`bbox` must be within {bounds}.")


def _haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate great-circle distance between two points using haversine formula."""
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng/2)**2
    earth_radius_m = 6371008.8
    return 2 * earth_radius_m * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def decompose_bbox(
    bbox: tuple[float, float, float, float],
    resolution: float,
    pixel_max: int,
    buff_npixels: int = 0,
) -> list[tuple[float, float, float, float]]:
    """Divide a Bbox into equal-area sub-bboxes.

    Parameters
    ----------
    bbox : tuple
        Bounding box coordinates in decimal degrees like so: (west, south, east, north).
    resolution : float
        Resolution of the domain in meters.
    pixel_max : int
        Maximum number of pixels allowed in each sub-bbox.
    buff_npixels : int, optional
        Number of pixels to buffer each sub-bbox by, defaults to 0.

    Returns
    -------
    list of tuple
        List of sub-bboxes in the form (west, south, east, north).
    """
    _check_bbox(bbox)
    west, south, east, north = bbox
    x_dist = _haversine_distance(south, west, south, east)
    y_dist = _haversine_distance(south, west, north, west)

    if resolution > min(x_dist, y_dist):
        raise ValueError("Resolution must be less than the smallest dimension of the bbox.")
    
    width = math.ceil(x_dist / resolution)
    height = math.ceil(y_dist / resolution)

    if width * height <= pixel_max:
        return [bbox]
    
    # Divisions in each direction maintaining aspect ratio
    aspect_ratio = width / height
    n_boxes = math.ceil((width * height) / pixel_max)
    nx = math.ceil(math.sqrt(n_boxes * aspect_ratio))
    ny = math.ceil(n_boxes / nx)
    dx = (east - west) / nx
    dy = (north - south) / ny

    # Calculate buffer sizes in degrees
    sub_width = width / nx
    sub_height = height / ny
    buff_x = dx * (buff_npixels / sub_width)
    buff_y = dy * (buff_npixels / sub_height)

    boxes = []
    for i in range(nx):
        box_west = west + (i * dx) - buff_x
        box_east = min(west + ((i + 1) * dx), east) + buff_x
        for j in range(ny):
            box_south = south + (j * dy) - buff_y
            box_north = min(south + ((j + 1) * dy), north) + buff_y
            boxes.append((box_west, box_south, box_east, box_north))
    return boxes


def _clip_3dep(vrt_url: str, box: tuple[float, float, float, float], tiff_path: Path) -> None:
    """Clip 3DEP to a bbox and save it as a GeoTiff file with NaN as nodata."""
    if not tiff_path.exists():
        with rasterio.open(vrt_url) as src:
            window = rasterio.windows.from_bounds(*box, transform=src.transform)
            meta = src.meta.copy()
            meta.update(
                {
                    "driver": "GTiff",
                    "height": window.height,
                    "width": window.width,
                    "transform": rasterio.windows.transform(window, src.transform),
                    "nodata": math.nan,
                }
            )

            # Read and mask data
            data = src.read(window=window)
            data[data == src.nodata] = math.nan

            with rasterio.open(tiff_path, "w", **meta) as dst:
                dst.write(data)


def get(
    bbox: tuple[float, float, float, float],
    save_dir: str | Path,
    resolution: Literal[10, 30, 60] = 10,
    pixel_max: int | None = 10_000_000,
) -> list[Path]:
    """Get DEM within US from USGS's 3D Hydrography Elevation Data Program (3DEP).

    Parameters
    ----------
    bbox : tuple
        Bounding box coordinates in decimal degrees like so: (west, south, east, north).
    vrt_path : str or pathlib.Path
        Path to save the VRT file, e.g., ``'dem.vrt'``.
    resolution : int, optional
        Resolution of the DEM in meters, by default 10. Must be one of 10, 30, or 60.
    pixel_max : int, optional
        Maximum number of pixels allowed in decomposing the bbox into equal-area sub-bboxes,
        by default 10_000_000. If ``None``, the bbox is not decomposed.

    Returns
    -------
    list of pathlib.Path
        list of GeoTiff files containing the DEM clipped to the bounding box.
    """
    base_url = "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation"
    url = {
        10: f"{base_url}/13/TIFF/USGS_Seamless_DEM_13.vrt",
        30: f"{base_url}/1/TIFF/USGS_Seamless_DEM_1.vrt",
        60: f"{base_url}/2/TIFF/USGS_Seamless_DEM_2.vrt",
    }
    if resolution not in url:
        raise ValueError("Resolution must be one of 10, 30, or 60 meters.")

    bbox_list = [bbox] if pixel_max is None else decompose_bbox(bbox, resolution, pixel_max)
    vrt_url = url[resolution]
    _check_bounds(bbox, _get_bounds(vrt_url))

    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    tiff_list = [
        save_dir / f"dem_{hashlib.sha256(','.join(map(str, box)).encode()).hexdigest()}.tiff"
        for box in bbox_list
    ]
    if all(tiff.exists() for tiff in tiff_list):
        return tiff_list

    n_jobs = min(4, len(bbox_list))
    if n_jobs == 1:
        _clip_3dep(vrt_url, bbox_list[0], tiff_list[0])
    else:
        with ThreadPoolExecutor(max_workers=n_jobs) as executor:
            executor.map(
                lambda args: _clip_3dep(*args),
                zip([vrt_url] * len(bbox_list), bbox_list, tiff_list, strict=True),
            )
    return tiff_list


def build_vrt(vrt_path: str | Path, tiff_files: list[str] | list[Path], relative: bool = False) -> None:
    """Create a VRT from tiles.

    Notes
    -----
    This function requires GDAL to be installed.

    Parameters
    ----------
    vrt_path : str or Path
        Path to save the output VRT file.
    tiff_files : list of str or Path
        List of file paths to include in the VRT.
    relative : bool, optional
        If True, use paths relative to the VRT file (default is False).
    """
    try:
        from osgeo import gdal  # pyright: ignore[reportMissingImports]
    except ImportError:
        raise ImportError("GDAL is required to run this function.")

    vrt_path = Path(vrt_path).resolve()
    tiff_files = [Path(f).resolve() for f in tiff_files]

    if not tiff_files or not all(f.exists() for f in tiff_files):
        raise ValueError("No valid files found.")

    gdal.UseExceptions()
    vrt_options = gdal.BuildVRTOptions(resampleAlg='nearest', addAlpha=False)
    _ = gdal.BuildVRT(vrt_path, tiff_files, options=vrt_options, relativeToVRT=relative)
