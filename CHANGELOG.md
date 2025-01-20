# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

### Changed

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
