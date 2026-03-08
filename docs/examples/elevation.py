# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: '1.16.0'
#   kernelspec:
#     display_name: dev
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Adding Elevation to a Climate Dataset

# %% [markdown]
# A common task in geospatial analysis is enriching an existing dataset
# with elevation information. For example, climate datasets defined on a
# regular longitude/latitude grid often benefit from an elevation
# variable for analyses that depend on altitude (lapse-rate corrections,
# orographic effects, etc.).
#
# In this example we create a synthetic climate dataset on a grid over
# Colorado, then use `seamless_3dep.elevation_bygrid` to add a matching
# elevation variable.

# %%
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

import seamless_3dep as s3dep

# %% [markdown]
# ## Create a synthetic climate dataset
#
# We define a regular grid of longitude and latitude values covering
# part of the Colorado Front Range and generate two dummy climate
# variables — temperature and precipitation — filled with random values.

# %%
rng = np.random.default_rng(42)

longs = np.linspace(-105.8, -104.8, 50)
lats = np.linspace(39.8, 40.3, 30)

temperature = 15.0 + 5.0 * rng.standard_normal((len(lats), len(longs)))
precipitation = np.abs(50.0 + 20.0 * rng.standard_normal((len(lats), len(longs))))

ds = xr.Dataset(
    {
        "temperature": (["lat", "lon"], temperature, {"units": "degC", "long_name": "Temperature"}),
        "precipitation": (
            ["lat", "lon"],
            precipitation,
            {"units": "mm", "long_name": "Precipitation"},
        ),
    },
    coords={"lon": longs, "lat": lats},
)
print(ds)

# %% [markdown]
# ## Retrieve elevation at grid points
#
# `elevation_bygrid` reads directly from the USGS 10 m seamless DEM VRT
# (Cloud-Optimized GeoTIFFs in EPSG:4269) and returns a 2-D array of
# shape `(len(lats), len(longs))` that aligns with our grid.

# %%
elevation = s3dep.elevation_bygrid(longs, lats)
elevation.shape

# %% [markdown]
# We can add this array as a new variable to the existing dataset.

# %%
ds["elevation"] = xr.DataArray(
    elevation,
    dims=["lat", "lon"],
    attrs={"units": "m", "long_name": "Elevation"},
)
print(ds)

# %% [markdown]
# ## Visualise the results

# %%
fig, axes = plt.subplots(1, 3, figsize=(15, 4))

ds["temperature"].plot(ax=axes[0], robust=True)
axes[0].set_title("Temperature")

ds["precipitation"].plot(ax=axes[1], robust=True)
axes[1].set_title("Precipitation")

ds["elevation"].plot(ax=axes[2], robust=True)
axes[2].set_title("Elevation (10 m DEM)")

fig.tight_layout()
fig.savefig("images/elevation_grid.png")
plt.show()

# %% [markdown]
# ## Using different resampling methods
#
# By default `elevation_bygrid` uses bilinear interpolation
# (`resampling=1`), but you can choose any DEM-applicable method:
#
# | Code | Method         | Notes                        |
# |-----:|:---------------|:-----------------------------|
# |    0 | nearest        | fastest, no interpolation    |
# |    1 | bilinear       | good general-purpose default |
# |    2 | cubic          | sharper than bilinear        |
# |    3 | cubic_spline   | smooth spline interpolation  |
# |    4 | lanczos        | high-quality windowed sinc   |

# %%
elev_nearest = s3dep.elevation_bygrid(longs, lats, resampling=0)
elev_lanczos = s3dep.elevation_bygrid(longs, lats, resampling=4)

diff = elev_lanczos - elev_nearest

fig, ax = plt.subplots(figsize=(6, 4))
im = ax.pcolormesh(longs, lats, diff, cmap="RdBu_r", shading="auto")
fig.colorbar(im, ax=ax, label="Lanczos − Nearest (m)")
ax.set_xlabel("Longitude")
ax.set_ylabel("Latitude")
ax.set_title("Resampling Difference")
fig.tight_layout()
fig.savefig("images/resampling_diff.png")
plt.show()
