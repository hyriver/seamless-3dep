"""Module for getting DEM from USGS's 3D Elevation Program (3DEP)."""

from __future__ import annotations

import hashlib
import math
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from itertools import repeat
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import rasterio
import rasterio.windows

if TYPE_CHECKING:
    MapTypes = Literal[
        "DEM",
        "Hillshade Gray",
        "Aspect Degrees",
        "Aspect Map",
        "GreyHillshade_elevationFill",
        "Hillshade Multidirectional",
        "Slope Map",
        "Slope Degrees",
        "Hillshade Elevation Tinted",
        "Height Ellipsoidal",
        "Contour 25",
        "Contour Smoothed 25",
    ]

__all__ = ["build_vrt", "decompose_bbox", "get_dem", "get_map"]

MAX_PIXELS = 10_000_000


class DownloadError(Exception):
    """Error raised when download fails."""

    def __init__(self, url: str, err_msg: Exception) -> None:
        message = f"Failed to download from {url}:\n{err_msg}"
        super().__init__(message)


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
        or not all(isinstance(x, (int, float)) for x in bbox)
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


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points using Haversine formula."""
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = (
        math.sin((lat2 - lat1) * 0.5) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) * 0.5) ** 2
    )
    earth_radius_m = 6371008.8
    return 2 * earth_radius_m * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def decompose_bbox(
    bbox: tuple[float, float, float, float],
    resolution: float,
    pixel_max: int,
    buff_npixels: float = 0.0,
) -> tuple[list[tuple[float, float, float, float]], int, int]:
    """Divide a Bbox into equal-area sub-bboxes based on pixel count.

    Parameters
    ----------
    bbox : tuple
        Bounding box coordinates in decimal degrees like so: (west, south, east, north).
    resolution : float
        Resolution of the domain in meters.
    pixel_max : int
        Maximum number of pixels allowed in each sub-bbox.
    buff_npixels : float, optional
        Number of pixels to buffer each sub-bbox by, defaults to 0.

    Returns
    -------
    boxes : list of tuple
        List of sub-bboxes in the form (west, south, east, north).
    sub_width : int
        Width of each sub-bbox in degrees.
    sub_height : int
        Height of each sub-bbox in degrees.
    """
    _check_bbox(bbox)
    west, south, east, north = bbox
    x_dist = _haversine_distance(south, west, south, east)
    y_dist = _haversine_distance(south, west, north, west)

    if resolution > min(x_dist, y_dist):
        raise ValueError("Resolution must be less than the smallest dimension of the bbox.")

    width = math.ceil(x_dist / resolution)
    height = math.ceil(y_dist / resolution)

    # Divisions in each direction maintaining aspect ratio
    aspect_ratio = width / height
    n_boxes = math.ceil((width * height) / pixel_max)
    nx = math.ceil(math.sqrt(n_boxes * aspect_ratio))
    ny = math.ceil(n_boxes / nx)
    dx = (east - west) / nx
    dy = (north - south) / ny

    # Calculate buffer sizes in degrees
    sub_width = math.ceil(width / nx)
    sub_height = math.ceil(height / ny)
    buff_x = dx * (buff_npixels / sub_width)
    buff_y = dy * (buff_npixels / sub_height)

    if width * height <= pixel_max:
        return [bbox], sub_width, sub_height

    boxes = []
    for i in range(nx):
        box_west = west + (i * dx) - buff_x
        box_east = min(west + ((i + 1) * dx), east) + buff_x
        for j in range(ny):
            box_south = south + (j * dy) - buff_y
            box_north = min(south + ((j + 1) * dy), north) + buff_y
            boxes.append((box_west, box_south, box_east, box_north))
    return boxes, sub_width, sub_height


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
            data = src.read(window=window)
            data[data == src.nodata] = math.nan
            with rasterio.open(tiff_path, "w", **meta) as dst:
                dst.write(data)


def _static_dem(
    bbox: tuple[float, float, float, float],
    save_dir: str | Path,
    resolution: Literal[10, 30, 60] = 10,
    pixel_max: int | None = MAX_PIXELS,
) -> list[Path]:
    """Get DEM from 3DEP at 10, 30, or 60 meters resolutions.

    Parameters
    ----------
    bbox : tuple
        Bounding box coordinates in decimal degrees like so: (west, south, east, north).
    save_dir : str or pathlib.Path
        Path to save the GeoTiff files.
    resolution : int, optional
        Resolution of the DEM in meters, by default 10. Must be one of 10, 30, or 60.
    pixel_max : int, optional
        Maximum number of pixels allowed in decomposing the bbox into equal-area sub-bboxes,
        by default MAX_PIXELS. If ``None``, the bbox is not decomposed.

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

    if pixel_max is None:
        _check_bbox(bbox)
        west, south, east, north = bbox
        x_dist = _haversine_distance(south, west, south, east)
        y_dist = _haversine_distance(south, west, north, west)

        if resolution > min(x_dist, y_dist):
            raise ValueError("Resolution must be less than the smallest dimension of the bbox.")
        bbox_list = [bbox]
    else:
        bbox_list, _, _ = decompose_bbox(bbox, resolution, pixel_max)

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
                zip(repeat(vrt_url), bbox_list, tiff_list),
            )
    return tiff_list


def _get_map(url: str, tiff_path: Path) -> None:
    """Call 3DEP's REST API to get the map and save it as a GeoTiff file."""
    try:
        if tiff_path.exists():
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD")) as response:
                if tiff_path.stat().st_size == int(response.headers["Content-Length"]):
                    return
        urllib.request.urlretrieve(url, tiff_path)
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        raise DownloadError(url, e) from e


def get_map(
    map_type: MapTypes,
    bbox: tuple[float, float, float, float],
    save_dir: str | Path,
    resolution: int = 10,
    pixel_max: int | None = MAX_PIXELS,
) -> list[Path]:
    """Get topo maps within US from 3DEP at any resolution.

    Parameters
    ----------
    map_type : MapTypes
        Type of map to get. Must be one of the following:
        'DEM', 'Hillshade Gray', 'Aspect Degrees', 'Aspect Map', 'GreyHillshade_elevationFill',
        'Hillshade Multidirectional', 'Slope Map', 'Slope Degrees', 'Hillshade Elevation Tinted',
        'Height Ellipsoidal', 'Contour 25', 'Contour Smoothed 25'.
    bbox : tuple
        Bounding box coordinates in decimal degrees like so: (west, south, east, north).
    save_dir : str or pathlib.Path
        Path to save the GeoTiff files.
    resolution : int, optional
        Resolution of the DEM in meters, by default 10.
    pixel_max : int, optional
        Maximum number of pixels allowed in decomposing the bbox into equal-area sub-bboxes,
        by default MAX_PIXELS. If ``None``, the bbox is not decomposed.

    Returns
    -------
    list of pathlib.Path
        list of GeoTiff files containing the DEM clipped to the bounding box.
    """
    valid_types = (
        "DEM",
        "Hillshade Gray",
        "Aspect Degrees",
        "Aspect Map",
        "GreyHillshade_elevationFill",
        "Hillshade Multidirectional",
        "Slope Map",
        "Slope Degrees",
        "Hillshade Elevation Tinted",
        "Height Ellipsoidal",
        "Contour 25",
        "Contour Smoothed 25",
    )
    if map_type not in valid_types:
        raise ValueError(f"`map_type` must be one of {valid_types}.")

    if map_type == "DEM" and resolution in (10, 30, 60):
        return _static_dem(bbox, save_dir, resolution, pixel_max)

    if pixel_max is None:
        _check_bbox(bbox)
        west, south, east, north = bbox
        x_dist = _haversine_distance(south, west, south, east)
        y_dist = _haversine_distance(south, west, north, west)

        if resolution > min(x_dist, y_dist):
            raise ValueError("Resolution must be less than the smallest dimension of the bbox.")

        sub_width = math.ceil(x_dist / resolution)
        sub_height = math.ceil(y_dist / resolution)
        bbox_list = [bbox]
    else:
        bbox_list, sub_width, sub_height = decompose_bbox(bbox, resolution, pixel_max)
    _check_bounds(bbox, (-180.0, -15.0, 180.0, 84.0))

    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    op_name = map_type.replace(" ", "_").lower()
    tiff_list = [
        save_dir / f"{op_name}_{hashlib.sha256(','.join(map(str, box)).encode()).hexdigest()}.tiff"
        for box in bbox_list
    ]
    if all(tiff.exists() for tiff in tiff_list):
        return tiff_list

    params = {
        "bboxSR": "4326",
        "size": ",".join(map(str, (sub_width, sub_height))),
        "format": "tiff",
        "interpolation": "RSP_BilinearInterpolation",
        "f": "image",
    }
    if map_type != "DEM":
        params["renderingRule"] = f'{{"rasterFunction":"{map_type}"}}'

    url = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
    url_list = []
    for box in bbox_list:
        params["bbox"] = ",".join(map(str, box))
        url_list.append(f"{url}?{urllib.parse.urlencode(params)}")

    n_jobs = min(4, len(url_list))
    if n_jobs == 1:
        _get_map(url_list[0], tiff_list[0])
    else:
        with ThreadPoolExecutor(max_workers=n_jobs) as executor:
            executor.map(lambda args: _get_map(*args), zip(url_list, tiff_list))
    return tiff_list


def get_dem(
    bbox: tuple[float, float, float, float],
    save_dir: str | Path,
    resolution: int = 10,
    pixel_max: int | None = MAX_PIXELS,
) -> list[Path]:
    """Get DEM from 3DEP at any resolution.

    Parameters
    ----------
    bbox : tuple
        Bounding box coordinates in decimal degrees like so: (west, south, east, north).
    save_dir : str or pathlib.Path
        Path to save the GeoTiff files.
    resolution : int, optional
        Resolution of the DEM in meters, by default 10.
    pixel_max : int, optional
        Maximum number of pixels allowed in decomposing the bbox into equal-area sub-bboxes,
        by default MAX_PIXELS. If ``None``, the bbox is not decomposed.

    Returns
    -------
    list of pathlib.Path
        list of GeoTiff files containing the DEM clipped to the bounding box.
    """
    return get_map("DEM", bbox, save_dir, resolution, pixel_max)


def build_vrt(
    vrt_path: str | Path, tiff_files: list[str] | list[Path], relative: bool = False
) -> None:
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
    except ImportError as e:
        raise ImportError("GDAL is required to run `build_vrt`.") from e

    vrt_path = Path(vrt_path).resolve()
    tiff_files = [Path(f).resolve() for f in tiff_files]

    if not tiff_files or not all(f.exists() for f in tiff_files):
        raise ValueError("No valid files found.")

    gdal.UseExceptions()
    vrt_options = gdal.BuildVRTOptions(resampleAlg="nearest", addAlpha=False)
    _ = gdal.BuildVRT(vrt_path, tiff_files, options=vrt_options, relativeToVRT=relative)
