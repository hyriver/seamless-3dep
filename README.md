# SeamlessDEM: DEM Retrieval from 3DEP or NASADEM

[![PyPi](https://img.shields.io/pypi/v/seamless-3dep.svg)](https://pypi.python.org/pypi/seamless-3dep)
[![Conda Version](https://img.shields.io/conda/vn/conda-forge/seamless-3dep.svg)](https://anaconda.org/conda-forge/seamless-3dep)
[![CodeCov](https://codecov.io/gh/hyriver/seamless-3dep/branch/main/graph/badge.svg)](https://codecov.io/gh/hyriver/seamless-3dep)
[![Python Versions](https://img.shields.io/pypi/pyversions/seamless-3dep.svg)](https://pypi.python.org/pypi/seamless-3dep)
[![Downloads](https://static.pepy.tech/badge/seamless-3dep)](https://pepy.tech/project/seamless-3dep)

[![CodeFactor](https://www.codefactor.io/repository/github/hyriver/seamless-3dep/badge)](https://www.codefactor.io/repository/github/hyriver/seamless-3dep)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/hyriver/seamless-3dep/HEAD?labpath=docs%2Fexamples)

## Features

SeamlessDEM is an open-source Python package that provides a simple and
efficient way to retrieve digital elevation models (DEMs) from the
[3D Elevation Program (3DEP)](https://www.usgs.gov/core-science-systems/ngp/3dep)
at three different resolutions (1/3 arc-second, 1 arc-second, and 2 arc-second)
and the [NASADEM](https://lpdaac.usgs.gov/products/nasadem_hgtv001/) at 1 arc-second resolution.

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

Once HySetter is installed, you can use the CLI to subset hydroclimate
data via a configuration file. The configuration file is a YAML file
that specifies the data source, the area of interest (AOI), and the
output directory. You can find an example configuration file in the
[config_demo.yml](https://github.com/hyriver/seamless-3dep/blob/main/config_demo.yml).

![image](https://raw.githubusercontent.com/hyriver/seamless-3dep/main/hs_help.svg){.align-center}

## Contributing

Contributions are appreciated and very welcomed. Please read
[CONTRIBUTING.md](https://github.com/hyriver/seamless-3dep/blob/main/CONTRIBUTING.md)
for instructions.
