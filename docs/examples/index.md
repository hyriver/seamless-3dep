# Examples

The example notebooks have several dependencies. You can install all the dependencies
using `micromamba` (or `conda` or `mamba`):

```bash
micormamba create -n dem seamless-3dep pywbt geopandas ipykernel ipywidgets
```

This will create a new environment called `dem` with all the required packages.

Alternatively, you can install the dependencies using `pip`:

```bash
python -m venv ./venv
source ./venv/bin/activate
pip install seamless-3dep pywbt geopandas ipykernel ipywidgets
```

<div class="grid cards" markdown>

- [![DEM Processing](images/dem.png){ loading=lazy }](dem.ipynb "DEM Processing")
    **DEM Processing**

</div>
