# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-04-19

### Fixed

- Snap the read window in `_clip_3dep` to integer pixel boundaries before writing each
    sub-tile. `rasterio.windows.from_bounds` returns a Window with fractional offsets
    and lengths; with the old code, GDAL's float-to-int coercion when serialising the
    GeoTIFF could leave each saved tile on a slightly different rounded pixel grid,
    producing the sub-pixel (~half-pixel, ~4 m at 10 m DEM) NoData strip seen at tile
    seams in external mosaics. After the fix, adjacent tiles share an exact pixel grid
    and tile cleanly without `buff_npixels`. Resolves the seam reproduced in
    [#28](https://github.com/hyriver/seamless-3dep/issues/28).
- Guard `_clip_3dep`'s nodata-to-NaN replace against the case where the source's nodata
    sentinel is itself NaN. The current 3DEP VRTs use a finite sentinel so the existing
    code happens to be fine, but `data == NaN` is always `False` and would have silently
    no-oped if USGS ever changes the product.
- Hash the full sorted tile list when naming the helper VRT in `tiffs_to_da` so
    concurrent calls with overlapping file lists no longer race on a shared
    `<first>.vrt` path (where the loser of the race could have read a half-written or
    other-list VRT).

### Added

- Add a `buff_npixels` parameter to `get_dem` and `get_map` that is forwarded to
    `decompose_bbox` to produce overlapping tiles. This is intended for workflows that
    post-process each tile independently (e.g., running geospatial operations in
    parallel on a per-tile basis) where a small halo of extra pixels around each tile
    avoids edge artifacts in the per-tile outputs. Defaults to `0` to preserve existing
    behavior. Closes [#28](https://github.com/hyriver/seamless-3dep/issues/28).
- Add a new `twi.ipynb` example notebook that demonstrates computing Topographic Wetness
    Index in parallel across buffered DEM tiles, then mosaicking the results.
- Expose a `max_workers` parameter on `get_dem` so power users with very large requests
    can tune the per-tile concurrency. Defaults to `None`, which uses
    `min(8, os.cpu_count(), n_tiles)` (up from the previous fixed cap of 4).
- Add a `res: Literal[10, 30, 60]` parameter to `elevation_bygrid` so callers who don't
    need 10 m fidelity can fall back to the coarser, smaller-to-range-read VRTs.
- Add a new public `Get3DEPErrors` exception class that aggregates per-tile failures
    from a multi-tile `get_dem` call. Exposes `.errors` (list of per-tile exceptions)
    and `.vrt_url` so callers can inspect the failures and decide whether to retry.

### Changed

- Pool source `DatasetReader` instances across tiles in `get_dem`. Each worker borrows a
    reader from a queue, runs one clip, and returns it on success — so the HTTPS
    handshake and initial range read against the source COG-VRT happen once per worker
    instead of once per tile. For 50–100-tile requests this is the dominant cost, and
    the change typically yields a 3–10× speedup over the previous "open per tile"
    behavior.
- Add per-tile retry with exponential backoff (3 attempts, base 0.5 s, 3× backoff) on
    transient I/O errors (`RasterioIOError` / `OSError`) inside `get_dem`. A poisoned
    reader is closed and replaced with a fresh one so other workers keep making
    progress.
- `get_dem` now collects per-tile failures and raises them together as a single
    `Get3DEPErrors` rather than aborting the whole batch on the first failure.
    Already-completed tiles stay on disk so a re-run resumes from the failed ones.
- Update `decompose_bbox` so the returned `sub_width` and `sub_height` reflect the
    actual per-tile pixel dimensions including buffer pixels on both sides when
    `buff_npixels > 0`. Previously the returned pixel counts ignored the buffer, which
    would have caused `get_map` to request the wrong output size from the 3DEP export
    service when combined with a non-zero buffer.
- Validate bbox ordering eagerly in `_check_bbox` (rejects `west >= east` or
    `south >= north` with a message that names the offending values) instead of
    surfacing a confusing "must be within VRT bounds" error from a later check.
- Trim the `dem.ipynb` example to focus on DEM and slope retrieval; the per-tile TWI
    workflow is now covered by the dedicated `twi.ipynb` example.

### Migration

- Multi-tile `get_dem` failures are now raised as `Get3DEPErrors` instead of
    `tiny_retriever.exceptions.ServiceError`. Callers that catch the old exception
    should switch to the new one (or catch `Exception` if they want both).

## [0.4.1] - 2026-03-13

### Fixed

- Fix sub-pixel interpolation in `elevation_bygrid`. Previously, `_transform_xy` called
    `rasterio.transform.rowcol()` with its default `op=numpy.floor`, which snapped every
    query coordinate to the nearest integer pixel index. When the query grid was finer
    than the ~10 m DEM pixels, multiple points mapped to the same pixel and received
    identical values, producing systematic staircase/plateau artifacts. Now fractional
    pixel coordinates are preserved and carried through to the
    `rasterio.windows.Window`, so GDAL's resampling kernel interpolates at the true
    sub-pixel position.

## [0.4.0] - 2026-03-08

### Added

- Add a new function called `elevation_bygrid` that samples elevation values from the
    USGS 10 m seamless DEM VRT at a grid of longitude/latitude coordinates. It reads
    directly from Cloud-Optimized GeoTIFFs (EPSG:4269) and supports configurable
    resampling methods (nearest, bilinear, cubic, cubic spline, and Lanczos) via a
    windowed read approach. This is useful for obtaining elevation values at arbitrary
    point locations without downloading full tiles.
- Add `numpy` as an explicit dependency (previously only a transitive dependency via
    `rasterio`).

### Changed

- Improve thread safety in `get_dem` by opening a fresh `DatasetReader` per tile instead
    of sharing a single instance across threads. The `VRTPool` is now used only for
    metadata (bounds, transform, nodata), not for concurrent reads.
- Add early-return optimization in `get_map`: skip downloading when all requested tiles
    already exist on disk (consistent with `get_dem` behavior).
- Move the `valid_types` tuple in `get_map` to a module-level constant
    (`VALID_MAP_TYPES`).
- Simplify `tiffs_to_da` by skipping the `.rio.clip()` step when the geometry is a
    bounding box, since `.rio.clip_box()` already handles that case.
- Migrate documentation from ReadTheDocs to GitHub Pages with `mike` versioning.
- Add a GitHub Actions workflow (`docs.yml`) for automated documentation deployment.
    Pushes to `main` deploy the `dev` version, and tagged releases deploy a stable
    version via `mike`.
- Add a GitHub Actions workflow (`docs.yml`) for automated documentation deployment.
    Pushes to `main` deploy the `dev` version, and tagged releases deploy a stable
    version via `mike`.

## [0.3.1] - 2025-02-12

### Added

- Add a new function called `tiffs_to_da` that converts a list of GeoTIFF files to a
    `xarray.DataArray` object. This function is useful for combining multiple GeoTIFF
    files that `get_map` and `get_dem` produce, into a single `xarray.DataArray` object
    for further analysis. Note that for using this function `shapely` and `rioxarray`
    need to be installed. The required dependencies did not change, these two are
    optional dependencies that are only needed for this new function.

### Changed

- Switch to using the new
    [TinyRetriever](https://tiny-retriever.readthedocs.io/en/latest/) library that was
    developed partly based on this package. It has the same two dependencies and
    includes the same functionality with some additional features.
- Improve handling of errors when using `build_vrt` function by explicitly catching
    errors raised by `gdalbuildvrt` and raising a more informative error message. This
    should make it easier to debug issues when creating VRT files.

## [0.3.0] - 2025-01-20

### Changed

- Refactor the package to run in Jupyter notebooks without using `nest-asyncio`. This is
    done by creating and initializing a single global event loop thread dedicated to
    only running the asynchronous parts of this package. As a result, `nest-asyncio` is
    no longer needed as a dependency.
- Remove the `out_crs` option from `get_map` since the 3DEP service returns inconsistent
    results when the output CRS is not its default value of 3857. This is a breaking
    change since this value cannot be configured and the default value has changed from
    5070 to 3857.

## [0.2.3] - 2025-01-18

### Changed

- Use `aiohttp` and `aiofiles` for more performant and robust handling of service calls
    and downloading of 3DEP map requests. This should limits the number of connections
    made to the dynamic 3DEP service to avoid hammering the service and can reduce the
    memory usage when downloading large files. As a results, `aiohttp` and `aiofiles`
    are now required dependencies and `urllib3` is no longer needed.
- More robust handling of closing `VRTPool` at exit by creating a new class method
    called `close`. This method is called by the `atexit` module to ensure that the
    pools are closed when the program exits.

## [0.2.2] - 2025-01-13

### Changed

- Considerable improvements in making service calls by creating connection pools using
    `urllib3.HTTPSConnectionPool` and `rasterio.open`. This should improve performance
    and robustness of service calls, and reduce the number of connections made to both
    the static and dynamic 3DEP services. As a results, `urllib3` is now a required
    dependency.
- Add a new private module called `_pools` that contains the connection pools for making
    service calls. The pools are lazily initialized and are shared across threads.
    Especially the VRT pools are created only when a specific resolution is requested,
    and are reused for subsequent requests of the same resolution. As such, the VRT info
    are loaded only once per resolution without using `lru_cache`.

## [0.2.1] - 2025-01-11

### Changed

- Improve downloading of 3DEP map requests in `get_map` by streaming the response
    content to a file instead of loading it into memory. Also make exception handling
    more robust. The function has been refactored for better readability and
    maintainability.
- Change the dependency of `build_vrt` from `gdal` to `libgdal-core` as it is more
    lightweight and does not require the full `gdal` package to be installed.
- Improve documentation.

## [0.2.0] - 2025-01-08

### Changed

- Since 3DEP web service returns incorrect results when `out_crs` is 4326, `get_map`
    will not accept 4326 for the time being and the default value is set to 5070. This
    is a breaking change.
- Improve exception handling when using `ThreadPoolExecutor` to ensure that exceptions
    are raised in the main thread.

## [0.1.0] - 2024-12-20

- Initial release.
