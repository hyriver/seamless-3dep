# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

### Changed

## [0.2.0] - 2024-12-20

### Changed

- Since 3DEP web service returns incorrect results when `out_crs` is 4326,
    `get_map` will not accept 4326 for the time being and the default value
    is set to 5070. This is a breaking change.
- Improve exception handling when using `ThreadPoolExecutor` to ensure that
    exceptions are raised in the main thread.

## [0.1.0] - 2024-12-20

- Initial release.
