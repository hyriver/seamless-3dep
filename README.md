# Seamless3DEP: Topographic Maps retrieval from 3DEP

[![PyPi](https://img.shields.io/pypi/v/seamless-3dep.svg)](https://pypi.python.org/pypi/seamless-3dep)
[![Conda Version](https://img.shields.io/conda/vn/conda-forge/seamless-3dep.svg)](https://anaconda.org/conda-forge/seamless-3dep)
[![CodeCov](https://codecov.io/gh/hyriver/seamless-3dep/branch/main/graph/badge.svg)](https://codecov.io/gh/hyriver/seamless-3dep)
[![Python Versions](https://img.shields.io/pypi/pyversions/seamless-3dep.svg)](https://pypi.python.org/pypi/seamless-3dep)
[![Downloads](https://static.pepy.tech/badge/seamless-3dep)](https://pepy.tech/project/seamless-3dep)

[![CodeFactor](https://www.codefactor.io/repository/github/hyriver/seamless-3dep/badge)](https://www.codefactor.io/repository/github/hyriver/seamless-3dep)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/hyriver/seamless-3dep/HEAD?labpath=docs%2Fexamples)

## Features

Seamless3DEP is an open-source light-weight Python package that provides a simple and
efficient way to retrieve topographic maps from the
[3D Elevation Program (3DEP)](https://www.usgs.gov/core-science-systems/ngp/3dep).
This web service provides both dynamic and static elevation products.
The static products are DEMs at three different resolutions
(1/3 arc-second (10 m), 1 arc-second (30 m), and 2 arc-second (60 m)). The dynamic
products are various elevation derivatives, such as hillshade, slope, aspect, and
contours. Here's the full list of available products:

- DEM
- Hillshade Gray
- Aspect Degrees
- Aspect Map
- GreyHillshade Elevation Fill
- Hillshade Multidirectional
- Slope Degrees
- Slope Map
- Hillshade Elevation Tinted
- Height Ellipsoidal
- Contour 25
- Contour Smoothed 25

Seamless3DEP has four functions:

- `get_dem`: Retrieve DEM within a bounding box at any resolution. When the
    give resolution is 10, 30, or 60, the function will return the static DEM.
    This function, under the hood, decomposes the bounding box into smaller ones
    based on the maximum pixel size of 8 million. Then, saves the DEM tiles
    as GeoTIFF files and returns the file paths. The default resolution is 10.
- `get_map`: Retrieve any of the map products within a bounding box at any
    resolution. Similar to the `get_dem` function, this function returns the
    file paths of the downloaded GeoTIFF files. The default resolution is 10.
- `decompose_bbox`: Decompose a large bounding box into smaller based on maximum
    pixel size. Both `get_dem` and `get_map` functions use this function to
    decompose the bounding box into smaller ones with a default maximum pixel
    size of 8 million.
- `build_vrt`: Build a virtual raster file (VRT) from a list of raster files.
    This function can be used to build a VRT file from the downloaded GeoTIFF files.
    Note that GDAL must be installed to use this function which is an optional
    dependency.

Note that the input bounding box should be in the format of (west, south, east, north)
in decimal degrees (WGS84). By default, maps are in 5070 projection. Note that at the
moment, due to an issue with 3DEP web service, the `out_crs` parameter in `get_map`
should not be set to 4326 since the service does not return the correct projection

## Installation

You can install `seamless-3dep` using `pip`:

```console
pip install seamless-3dep
```

Alternatively, `seamless-3dep` can be installed from the `conda-forge`
repository using
[micromamba](https://mamba.readthedocs.io/en/latest/installation/micromamba-installation.html/):

```console
micromamba install -c conda-forge seamless-3dep
```

## Quick start

Here's a quick example to retrieve a DEM within a bounding box:

```python
from pathlib import Path
import seamless_3dep as sdem

bbox = (-105.7006276, 39.8472777, -104.869054, 40.298293)
data_dir = Path("data")
tiff_files = sdem.get_dem(bbox, data_dir)
if len(tiff_files) == 1:
    dem_file = tiff_files[0]
else:
    dem_file = data_dir / "dem.vrt"
    sdem.build_vrt(dem_file, tiff_files)
dem = rxr.open_rasterio(dem_file).squeeze(drop=True)
```

![image](https://raw.githubusercontent.com/hyriver/seamless-3dep/main/docs/examples/images/dem.png)

Now, let's get slope:

```python
tiff_files = sdem.get_map("Slope Degrees", bbox, data_dir)
slope = data_dir / "slope.vrt"
sdem.build_vrt(slope, slope_files)
```

![image](https://raw.githubusercontent.com/hyriver/seamless-3dep/main/docs/examples/images/slope_dynamic.png)

## Contributing

Contributions are appreciated and very welcomed. Please read
[CONTRIBUTING.md](https://github.com/hyriver/seamless-3dep/blob/main/CONTRIBUTING.md)
for instructions.
