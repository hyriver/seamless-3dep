# ---
# jupyter:
#   jupytext:
#     cell_metadata_filter: -all
#     formats: ipynb,py:percent
#     notebook_metadata_filter: kernelspec,jupytext
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.3
#   kernelspec:
#     display_name: dev
#     language: python
#     name: python3
# ---

# %% [markdown]
# # DEM Processing

# %%
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import whitebox_workflows as wbw

import seamless_3dep as s3dep

# %% [markdown]
# Let's start by getting a HUC8 geometry from [GeoConnex](https://docs.geoconnex.us/) web service for St. Vrain region in Colorado. Note that we need to make sure that geometry is in 4326 projection.

# %%
url = "https://reference.geoconnex.us/collections/hu08/items/10190005"
vrain = gpd.read_file(url)
geom_org = vrain.to_crs(4326).union_all()
geom = vrain.to_crs(3857).buffer(5e3).to_crs(4326).union_all()

# %% [markdown]
# We can use `get_dem` to get the DEM in 4326 projection. If you prefer a projected CRS for downstream analysis, use `get_map` instead, which returns the DEM in 3857. Here we'll use `get_map` and add a small 5-km buffer to the bounding box so edge pixels aren't lost when the output is reprojected.

# %%
data_dir = Path("data")
dem_tiffs = s3dep.get_map("DEM", geom.bounds, data_dir, 10)

# %% [markdown]
# We then use `tiffs_to_da` to read the data into an `xarray.DataArray` and plot it.

# %%
dem = s3dep.tiffs_to_da(dem_tiffs, geom_org.bounds, crs=4326)

# %%
ax = dem.plot.imshow(robust=True)
ax.figure.savefig("images/dem.png")

# %% [markdown]
# Next, we use `whitebox_workflows` to compute the slope from the retrieved DEM tiles.

# %%
wbe = wbw.WbEnvironment()


def compute_slope(dem_path: Path) -> Path:
    slope_path = dem_path.with_name(dem_path.name.replace("dem", "slope"))
    dem = wbe.read_raster(dem_path.as_posix())
    dem = wbe.hydrology.depressions_storage.breach_depressions_least_cost(
        dem=dem, dist=50, minimize_dist=True, flat_increment=None, fill_deps=True
    )
    slope = wbe.terrain.derivatives.slope(input=dem, units="degrees")
    wbe.write_raster(slope, slope_path.as_posix())
    return slope_path


slope_wbt_files = [compute_slope(dem_path) for dem_path in dem_tiffs]

# %%
slope = s3dep.tiffs_to_da(slope_wbt_files, geom_org.bounds, crs=4326)
ax = slope.plot.imshow(robust=True)
ax.figure.savefig("images/slope_wbt.png")

# %% [markdown]
# We can also directly get slope using `get_map` function and passing `map_type="Slope Degrees"`.

# %%
slope_tiffs = s3dep.get_map("Slope Degrees", geom.bounds, data_dir, 10)
slope = s3dep.tiffs_to_da(slope_tiffs, geom_org.bounds, crs=4326)
ax = slope.plot.imshow(robust=True)
ax.figure.savefig("images/slope_dynamic.png")
