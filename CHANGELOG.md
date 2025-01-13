# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

### Changed

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
