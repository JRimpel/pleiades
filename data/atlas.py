"""World Atlas preprocessing shared by training and the WNY grid.

Units follow GFZ DOI 10.5880/GFZ.1.4.2016.001: artificial mcd/m².
Natural background 0.171 mcd/m² is added before magnitude conversion.
"""
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform


def artificial_to_mpsas(artificial_mcd):
    values = np.asarray(artificial_mcd, dtype=float)
    valid = np.isfinite(values) & (values >= 0)
    luminance_cd = (np.where(valid, values, 0) + .171) / 1000
    return np.where(valid, -2.5 * np.log10(luminance_cd / 108000), np.nan)


def sample_atlas(path, latitudes, longitudes):
    latitudes, longitudes = np.asarray(latitudes), np.asarray(longitudes)
    if latitudes.shape != longitudes.shape or latitudes.ndim != 1:
        raise ValueError('Latitude/longitude must be matching 1-D arrays')
    with rasterio.open(Path(path)) as raster:
        if raster.crs is None:
            raise ValueError('Raster must declare a coordinate reference system')
        x, y = transform('EPSG:4326', raster.crs, longitudes.tolist(), latitudes.tolist())
        order = np.lexsort((x, y))
        sampled = list(raster.sample([(x[i], y[i]) for i in order], masked=True))
        result = np.full(len(x), np.nan)
        for index, value in zip(order, sampled):
            if not np.ma.is_masked(value[0]):
                result[index] = float(value[0])
    return artificial_to_mpsas(result)
