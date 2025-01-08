"""Module for getting DEM from USGS's 3D Elevation Program (3DEP)."""

from __future__ import annotations

import hashlib
import math
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
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

MAX_PIXELS = 8_000_000


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
    res: int,
    pixel_max: int | None = MAX_PIXELS,
    buff_npixels: float = 0.0,
) -> tuple[list[tuple[float, float, float, float]], int, int]:
    """Divide a Bbox into equal-area sub-bboxes based on pixel count.

    Parameters
    ----------
    bbox : tuple
        Bounding box coordinates in decimal degrees like so: (west, south, east, north).
    res : int
        Resolution of the domain in meters.
    pixel_max : int, optional
        Maximum number of pixels allowed in each sub-bbox. If None, the bbox
        is not decomposed. Defaults to 8 million.
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

    if res > min(x_dist, y_dist):
        raise ValueError("Resolution must be less than the smallest dimension of the bbox.")

    width = math.ceil(x_dist / res)
    height = math.ceil(y_dist / res)
    if pixel_max is None or width * height <= pixel_max:
        return [bbox], width, height

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


def _create_hash(box: tuple[float, float, float, float], res: int, crs: int) -> str:
    """Create a hash from bbox, resolution, and CRS."""
    return hashlib.sha256(",".join(map(str, [*box, res, crs])).encode()).hexdigest()


def get_dem(
    bbox: tuple[float, float, float, float],
    save_dir: str | Path,
    res: Literal[10, 30, 60] = 10,
    pixel_max: int | None = MAX_PIXELS,
) -> list[Path]:
    """Get DEM from 3DEP at 10, 30, or 60 meters resolutions.

    Notes
    -----
    If you need a different resolution, use the ``get_map`` function
    with ``map_type="DEM"``.

    Parameters
    ----------
    bbox : tuple
        Bounding box coordinates in decimal degrees: (west, south, east, north).
    save_dir : str or pathlib.Path
        Path to save the GeoTiff files.
    res : {10, 30, 60}, optional
        Target resolution of the DEM in meters, by default 10.
        Must be one of 10, 30, or 60.
    pixel_max : int, optional
        Maximum number of pixels allowed in decomposing the bbox into equal-area
        sub-bboxes, by default 8 million. If ``None``, the bbox is not decomposed.

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
    if res not in url:
        raise ValueError("`res` must be one of 10, 30, or 60 meters.")

    bbox_list, _, _ = decompose_bbox(bbox, res, pixel_max)

    vrt_url = url[res]
    _check_bounds(bbox, _get_bounds(vrt_url))

    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    tiff_list = [save_dir / f"dem_{_create_hash(box, res, 4326)}.tiff" for box in bbox_list]
    if all(tiff.exists() for tiff in tiff_list):
        return tiff_list

    n_jobs = min(4, len(bbox_list))
    if n_jobs == 1:
        _clip_3dep(vrt_url, bbox_list[0], tiff_list[0])
    else:
        with ThreadPoolExecutor(max_workers=n_jobs) as executor:
            future_to_url = {
                executor.submit(_clip_3dep, vrt_url, box, path): (box, path)
                for box, path in zip(bbox_list, tiff_list)
            }
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    future.result()
                except Exception as e:
                    raise DownloadError(vrt_url, e) from e
    return tiff_list


def _get_map(url: str, tiff_path: Path) -> None:
    """Call 3DEP's REST API to get the map and save it as a GeoTiff file."""
    if tiff_path.exists():
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD")) as r:
            if tiff_path.stat().st_size == int(r.headers["Content-Length"]):
                return
    urllib.request.urlretrieve(url, tiff_path)


def get_map(
    map_type: MapTypes,
    bbox: tuple[float, float, float, float],
    save_dir: str | Path,
    res: int = 10,
    out_crs: int = 5070,
    pixel_max: int | None = MAX_PIXELS,
) -> list[Path]:
    """Get topo maps within US from 3DEP at any resolution.

    Parameters
    ----------
    map_type : MapTypes
        Type of map to get. Must be one of the following:

        - ``'DEM'``
        - ``'Hillshade Gray'``
        - ``'Aspect Degrees'``
        - ``'Aspect Map'``
        - ``'GreyHillshade_elevationFill'``
        - ``'Hillshade Multidirectional'``
        - ``'Slope Map'``
        - ``'Slope Degrees'``
        - ``'Hillshade Elevation Tinted'``
        - ``'Height Ellipsoidal'``
        - ``'Contour 25'``
        - ``'Contour Smoothed 25'``
    bbox : tuple
        Bounding box coordinates in decimal degrees (WG84): (west, south, east, north).
    save_dir : str or pathlib.Path
        Path to save the GeoTiff files.
    res : int, optional
        Target resolution of the map in meters, by default 10.
    out_crs : int, optional
        Coordinate reference system of the output GeoTiff, by default 5070. This must
        be a well-known ID (WKID) like 3857 or 5070. Do not use 4326 since at the moment
        the 3DEP web service does not return correct results.
    pixel_max : int, optional
        Maximum number of pixels allowed in decomposing the bbox into equal-area
        sub-bboxes, by default 8 million. If ``None``, the bbox is not decomposed.

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

    if not isinstance(out_crs, int):
        raise TypeError("`out_crs` must be an integer representing WKID.")

    if out_crs == 4326:
        msg = "`out_crs` cannot be 4326 since 3DEP does not return correct results."
        msg += " Use a different CRS like 3857 or 5070."
        raise ValueError(msg)

    bbox_list, sub_width, sub_height = decompose_bbox(bbox, res, pixel_max)

    _check_bounds(bbox, (-180.0, -15.0, 180.0, 84.0))
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    rule = map_type.replace(" ", "_").lower()
    tiff_list = [save_dir / f"{rule}_{_create_hash(box, res, out_crs)}.tiff" for box in bbox_list]
    if all(tiff.exists() for tiff in tiff_list):
        return tiff_list

    params = {
        "bboxSR": 4326,
        "imageSR": out_crs,
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
        params["bbox"] = ",".join(str(round(c, 6)) for c in box)
        url_list.append(f"{url}?{urllib.parse.urlencode(params)}")

    n_jobs = min(4, len(url_list))
    if n_jobs == 1:
        _get_map(url_list[0], tiff_list[0])
    else:
        with ThreadPoolExecutor(max_workers=n_jobs) as executor:
            future_to_url = {
                executor.submit(_get_map, url, path): url for url, path in zip(url_list, tiff_list)
            }
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    future.result()
                except urllib.error.HTTPError as e:
                    raise DownloadError(url, e) from e
    return tiff_list


def build_vrt(
    vrt_path: str | Path, tiff_files: list[str] | list[Path], relative: bool = False
) -> None:
    """Create a VRT from a list of GeoTIFF tiles.

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
