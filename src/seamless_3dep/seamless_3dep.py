"""Module for getting DEM from USGS's 3D Elevation Program (3DEP)."""

from __future__ import annotations

import hashlib
import math
import os
import shutil
import subprocess
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Literal, overload
from urllib.parse import urlencode

import rasterio
import rasterio.windows

from seamless_3dep._https_download import ServiceError, stream_write
from seamless_3dep._vrt_pools import VRTLinks, VRTPool

if TYPE_CHECKING:
    from pyproj import CRS
    from rasterio.io import DatasetReader
    from rasterio.transform import Affine
    from shapely import Polygon
    from xarray import DataArray

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
    CRSType = int | str | CRS

__all__ = ["build_vrt", "decompose_bbox", "get_dem", "get_map", "tiffs_to_da"]

MAX_PIXELS = 8_000_000


def _check_bbox(bbox: Sequence[float]) -> tuple[float, float, float, float]:
    """Validate that bbox is in correct form."""
    if not (isinstance(bbox, Sequence) and len(bbox) == 4 and all(map(math.isfinite, bbox))):
        raise TypeError(
            "`bbox` must be a tuple of form (west, south, east, north) in decimal degrees."
        )
    return (bbox[0], bbox[1], bbox[2], bbox[3])


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
    bbox: Sequence[float],
    res: int,
    pixel_max: int | None,
    buff_npixels: float = 0.0,
) -> tuple[list[tuple[float, float, float, float]], int, int]:
    """Divide a Bbox into equal-area sub-bboxes based on pixel count.

    Parameters
    ----------
    bbox : tuple
        Bounding box coordinates in decimal degrees like so: (west, south, east, north).
    res : int
        Resolution of the domain in meters.
    pixel_max : int
        Maximum number of pixels allowed in each sub-bbox. If None, the bbox
        is not decomposed.
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
    west, south, east, north = _check_bbox(bbox)
    x_dist = _haversine_distance(south, west, south, east)
    y_dist = _haversine_distance(south, west, north, west)

    if res > min(x_dist, y_dist):
        raise ValueError("Resolution must be less than the smallest dimension of the bbox.")

    width = math.ceil(x_dist / res)
    height = math.ceil(y_dist / res)
    if pixel_max is None or width * height <= pixel_max:
        return [(west, south, east, north)], width, height

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


def _clip_3dep(
    vrt_pool: DatasetReader,
    box: tuple[float, float, float, float],
    tiff_path: Path,
    transform: Affine,
    nodata: float,
) -> None:
    """Clip 3DEP to a bbox and save it as a GeoTiff file with NaN as nodata."""
    if not tiff_path.exists():
        window = rasterio.windows.from_bounds(*box, transform=transform)
        meta = vrt_pool.meta.copy()
        meta.update(
            {
                "driver": "GTiff",
                "height": window.height,
                "width": window.width,
                "transform": rasterio.windows.transform(window, transform),
                "nodata": math.nan,
            }
        )
        data = vrt_pool.read(window=window)
        data[data == nodata] = math.nan
        with rasterio.open(tiff_path, "w", **meta) as dst:
            dst.write(data)


def _create_hash(box: tuple[float, float, float, float], res: int, crs: int) -> str:
    """Create a hash from bbox, resolution, and CRS."""
    return hashlib.sha256(",".join(map(str, [*box, res, crs])).encode()).hexdigest()


def get_dem(
    bbox: Sequence[float],
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
        Maximum number of pixels allowed in each sub-bbox for decomposing the bbox
        into equal-area sub-bboxes, defaults to 8 million. If ``None``, the bbox
        is not decomposed and is downloaded as a single file. Values more than
        8 million are not allowed.

    Returns
    -------
    list of pathlib.Path
        list of GeoTiff files containing the DEM clipped to the bounding box.
    """
    if res not in VRTLinks:
        raise ValueError("`res` must be one of 10, 30, or 60 meters.")

    if pixel_max is not None and pixel_max > MAX_PIXELS:
        raise ValueError(f"`pixel_max` must be less than {MAX_PIXELS}.")

    bbox = _check_bbox(bbox)
    bbox_list, _, _ = decompose_bbox(bbox, res, pixel_max)

    vrt_pool = VRTPool.get_dataset_reader(res)
    vrt_info = VRTPool.get_vrt_info(res)
    _check_bounds(bbox, vrt_info.bounds)

    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    tiff_list = [save_dir / f"dem_{_create_hash(box, res, 4326)}.tiff" for box in bbox_list]
    if all(tiff.exists() for tiff in tiff_list):
        return tiff_list

    max_workers = min(4, os.cpu_count() or 1, len(bbox_list))
    if max_workers == 1:
        _ = [
            _clip_3dep(vrt_pool, box, path, vrt_info.transform, vrt_info.nodata)
            for box, path in zip(bbox_list, tiff_list)
        ]
        return tiff_list

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(_clip_3dep, vrt_pool, box, path, vrt_info.transform, vrt_info.nodata): (
                box,
                path,
            )
            for box, path in zip(bbox_list, tiff_list)
        }
        for future in as_completed(future_to_url):
            try:
                future.result()
            except Exception as e:  # noqa: PERF203
                raise ServiceError(str(e), VRTLinks[res]) from e
    return tiff_list


def get_map(
    map_type: MapTypes,
    bbox: Sequence[float],
    save_dir: str | Path,
    res: int = 10,
    pixel_max: int | None = MAX_PIXELS,
) -> list[Path]:
    """Get topo maps in 3857 coordinate system within US from 3DEP at any resolution.

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
    pixel_max : int, optional
        Maximum number of pixels allowed in each sub-bbox for decomposing the bbox
        into equal-area sub-bboxes, defaults to 8 million. If ``None``, the bbox
        is not decomposed and is downloaded as a single file. Values more than
        8 million are not allowed.

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

    if pixel_max is not None and pixel_max > MAX_PIXELS:
        raise ValueError(f"`pixel_max` must be less than {MAX_PIXELS}.")

    bbox = _check_bbox(bbox)
    bbox_list, sub_width, sub_height = decompose_bbox(bbox, res, pixel_max)

    _check_bounds(bbox, (-180.0, -15.0, 180.0, 84.0))
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    rule = map_type.replace(" ", "_").lower()
    tiff_list = [save_dir / f"{rule}_{_create_hash(box, res, 3857)}.tiff" for box in bbox_list]
    params = {
        "bboxSR": 4326,
        "imageSR": 3857,
        "size": f"{sub_width},{sub_height}",
        "format": "tiff",
        "interpolation": "RSP_BilinearInterpolation",
        "f": "image",
    }
    if map_type != "DEM":
        params["renderingRule"] = f'{{"rasterFunction":"{map_type}"}}'

    url = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
    pq_list = [
        f"{url}?bbox={','.join(str(round(c, 6)) for c in box)}&{urlencode(params)}"
        for box in bbox_list
    ]
    stream_write(pq_list, tiff_list)
    return tiff_list


@overload
def _path2str(path: Path | str) -> str: ...


@overload
def _path2str(path: list[Path] | list[str]) -> list[str]: ...


def _path2str(path: Path | str | list[Path] | list[str]) -> str | list[str]:
    if isinstance(path, (list, tuple)):
        return [Path(p).resolve().as_posix() for p in path]
    return Path(path).resolve().as_posix()


def build_vrt(vrt_path: str | Path, tiff_files: list[str] | list[Path]) -> None:
    """Create a VRT from a list of GeoTIFF tiles.

    Notes
    -----
    This function requires the installation of ``libgdal-core``. The recommended
    approach is to use ``conda`` (or alternatives like ``mamba`` or ``micromamba``).
    However, if using the system's package manager is the only option, ensure that
    the ``gdal-bin`` or ``gdal`` package is installed. For detailed instructions,
    refer to the GDAL documentation [here](https://gdal.org/download.html).
    When ``seamless-3dep`` is installed from Conda, ``libgdal-core`` is installed
    as a dependency and this function works without any additional steps.

    Parameters
    ----------
    vrt_path : str or Path
        Path to save the output VRT file.
    tiff_files : list of str or Path
        List of file paths to include in the VRT.
    """
    if shutil.which("gdalbuildvrt") is None:
        raise ImportError("GDAL (`libgdal-core`) is required to run `build_vrt`.")

    vrt_path = Path(vrt_path).resolve()
    tiff_files = [Path(f).resolve() for f in tiff_files]

    if not tiff_files or not all(f.exists() for f in tiff_files):
        raise ValueError("No valid files found.")

    command = [
        "gdalbuildvrt",
        "-r",
        "nearest",
        "-overwrite",
        _path2str(vrt_path),
        *_path2str(tiff_files),
    ]
    try:
        subprocess.run(command, check=True, text=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        msg = f"Command '{' '.join(e.cmd)}' failed with error:\n{e.stderr.strip()}"
        raise RuntimeError(msg) from e


def tiffs_to_da(
    tiff_files: list[Path], geometry: Polygon | Sequence[float], crs: CRSType = 4326
) -> DataArray:
    """Convert a list of tiff files to a vrt file and return a xarray.DataArray.

    Parameters
    ----------
    tiff_files : list of Path
        List of file paths to convert to a DataArray.
    geometry : Polygon or Sequence
        Polygon or bounding box in the form (west, south, east, north).
    crs : int, str, or CRS, optional
        Coordinate reference system of the input geometry, by default 4326.

    Returns
    -------
    xarray.DataArray
        DataArray containing the clipped data.
    """
    try:
        import rioxarray as rxr
        import shapely
    except ImportError as e:
        msg = "This function requires `shapely` and `rioxarray` to be installed."
        raise ImportError(msg) from e

    if not isinstance(tiff_files, Iterable):
        raise TypeError("`tiff_files` must be an iterable of file paths.")

    if isinstance(geometry, shapely.Polygon):
        geom = geometry
    elif isinstance(geometry, Sequence):
        geom = shapely.box(*_check_bbox(geometry))
    else:
        raise TypeError(
            "`geometry` must be a shapely Polygon or an iterable of form (west, south, east, north)."
        )

    tiff_files = [Path(f).resolve() for f in tiff_files]

    if not tiff_files or not all(f.exists() for f in tiff_files):
        raise ValueError("No valid files found.")

    first = tiff_files[0]
    if len(tiff_files) == 1:
        file = first
    else:
        file = first.with_suffix(".vrt")
        build_vrt(file, tiff_files)
    return (
        rxr.open_rasterio(file)
        .squeeze(drop=True)
        .rio.clip_box(*geom.bounds, crs=crs)
        .rio.clip([geom], crs=crs)
    )
