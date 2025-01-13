# Seamless3DEP: Streamlined Access to USGS 3DEP Topographic Data

[![PyPi](https://img.shields.io/pypi/v/seamless-3dep.svg)](https://pypi.python.org/pypi/seamless-3dep)
[![Conda Version](https://img.shields.io/conda/vn/conda-forge/seamless-3dep.svg)](https://anaconda.org/conda-forge/seamless-3dep)
[![CodeCov](https://codecov.io/gh/hyriver/seamless-3dep/branch/main/graph/badge.svg)](https://codecov.io/gh/hyriver/seamless-3dep)
[![Python Versions](https://img.shields.io/pypi/pyversions/seamless-3dep.svg)](https://pypi.python.org/pypi/seamless-3dep)
[![Downloads](https://static.pepy.tech/badge/seamless-3dep)](https://pepy.tech/project/seamless-3dep)

[![CodeFactor](https://www.codefactor.io/repository/github/hyriver/seamless-3dep/badge)](https://www.codefactor.io/repository/github/hyriver/seamless-3dep)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/hyriver/seamless-3dep/HEAD?labpath=docs%2Fexamples)

Seamless3DEP is a lightweight Python package that simplifies access to topographic data
from the USGS
[3D Elevation Program (3DEP)](https://www.usgs.gov/core-science-systems/ngp/3dep).
Whether you need elevation data or its derivatives, Seamless3DEP provides an efficient
interface to both static and dynamic 3DEP products.

Seamless3DEP utilizes connection pooling across threads (safely) to optimize service
calls and minimize redundant connections. This reduces both the service load and the
time required to retrieve data, making it an ideal tool for handling large-scale
topographic data requests.

📚 Full documentation is available [here](https://seamless-3dep.readthedocs.io).

## Available Products

### Static DEMs

- 1/3 arc-second (10 meters)
- 1 arc-second (30 meters)
- 2 arc-second (60 meters)

### Dynamic Products

- Digital Elevation Model (DEM)
- Hillshade Derivatives:
    - Gray Hillshade
    - Multidirectional Hillshade
    - GreyHillshade with Elevation Fill
    - Hillshade with Elevation Tint
- Terrain Analysis:
    - Aspect (Degrees and Map)
    - Slope (Degrees and Map)
    - Height (Ellipsoidal)
- Contours:
    - Contour 25 (Dynamically generates 25 contours for the area of interest)
    - Contour Smoothed 25 (Smoothed version of the 25 contours)

## Core Functions

Seamless3DEP offers four main functions designed for efficient data retrieval and
processing:

- `get_dem`: Retrieves static DEMs within a specified bounding box. The function
    automatically splits large areas into manageable tiles, downloads data as GeoTIFF
    files in WGS84 (EPSG:4326), and supports resolutions of 10m, 30m, or 60m.
- `get_map`: Fetches any 3DEP product (including DEMs) with customizable parameters.
    Works with all available product types, allows custom resolution settings, and
    downloads in NAD83 Conus Albers (EPSG:5070) by default. Supports custom projections
    (except WGS84 due to service limitations).
- `decompose_bbox`: Handles large area requests by breaking down extensive bounding
    boxes into optimal sizes based on resolution and maximum pixel count, ensuring
    efficient data retrieval.
- `build_vrt`: Creates virtual raster datasets by combining multiple GeoTIFF files.
    Requires `libgdal-core` installation and supports efficient data handling for large
    areas. Note that `libgdal-core` is an optional dependency and is not installed when
    `seamless-3dep` is installed from PyPI. However, it is installed as a dependency
    when `seamless-3dep` is installed from `conda-forge`.

## Important Notes

- Bounding box coordinates should be in decimal degrees (WGS84) format: (west, south,
    east, north)
- Default projection for requesting maps is EPSG:5070 (NAD83 Conus Albers)
- WGS84 (EPSG:4326) output projection is not supported in `get_map` due to service
    limitations

## Installation

Choose your preferred installation method:

### Using `pip`

```console
pip install seamless-3dep
```

### Using `micromamba` (recommended)

```console
micromamba install -c conda-forge seamless-3dep
```

Alternatively, you can use `conda` or `mamba`.

## Quick Start Guide

We can retrieve topographic data using Seamless3DEP in just a few lines of code. Then,
we can visualize or even reproject the data using `rioxarray`.

### Retrieving a DEM

```python
from pathlib import Path
import seamless_3dep as sdem
import rioxarray as rxr

# Define area of interest (west, south, east, north)
bbox = (-105.7006276, 39.8472777, -104.869054, 40.298293)
data_dir = Path("data")

# Download DEM
tiff_files = sdem.get_dem(bbox, data_dir)

# Handle single or multiple tiles
if len(tiff_files) == 1:
    dem_file = tiff_files[0]
else:
    dem_file = data_dir / "dem.vrt"
    sdem.build_vrt(dem_file, tiff_files)

# Open with rioxarray
dem = rxr.open_rasterio(dem_file).squeeze(drop=True)
```

![DEM Example](https://raw.githubusercontent.com/hyriver/seamless-3dep/main/docs/examples/images/dem.png)

### Retrieving a Slope Map

```python
slope_files = sdem.get_map("Slope Degrees", bbox, data_dir)
```

![Slope Example](https://raw.githubusercontent.com/hyriver/seamless-3dep/main/docs/examples/images/slope_dynamic.png)

## Contributing

We welcome contributions! Please see the
[contributing](https://seamless-3dep.readthedocs.io/en/latest/CONTRIBUTING/) section for
guidelines and instructions.
