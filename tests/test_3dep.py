from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import rasterio

import seamless_3dep as sdem
from seamless_3dep._pools import _cleanup_pools


@pytest.fixture
def valid_bbox() -> tuple[float, float, float, float]:
    return (-122.0, 37.0, -121.0, 38.0)


@pytest.fixture
def small_res() -> int:
    return 30


@pytest.fixture
def pixel_max() -> int:
    return 1_000_000


def test_decompose_bbox_no_division(
    valid_bbox: tuple[float, float, float, float], small_res: int, pixel_max: int
):
    """Test when bbox is small enough to not require division."""
    boxes, *_ = sdem.decompose_bbox(valid_bbox, small_res, pixel_max * 100)
    assert len(boxes) == 1
    assert boxes[0] == valid_bbox


def test_decompose_bbox_with_division(valid_bbox: tuple[float, float, float, float]):
    """Test when bbox needs to be divided."""
    # Use small pixel_max to force division
    small_pixel_max = 1000
    boxes, *_ = sdem.decompose_bbox(valid_bbox, 30, small_pixel_max)
    assert len(boxes) > 1

    # Check that all boxes are within original bbox
    for box in boxes:
        west, south, east, north = box
        orig_west, orig_south, orig_east, orig_north = valid_bbox
        assert west >= orig_west - 1e-10  # Account for floating point precision
        assert south >= orig_south - 1e-10
        assert east <= orig_east + 1e-10
        assert north <= orig_north + 1e-10


def test_decompose_bbox_with_buffer():
    """Test decompose_bbox with buffer."""
    bbox = (-122.0, 37.0, -121.0, 38.0)
    boxes, *_ = sdem.decompose_bbox(bbox, res=30, pixel_max=1000, buff_npixels=2)
    # Check that boxes overlap due to buffer
    for i in range(len(boxes) - 1):
        current_box = boxes[i]
        next_box = boxes[i + 1]
        # Either boxes should overlap in x or y direction
        has_overlap = (
            (current_box[2] > next_box[0])  # x overlap
            or (current_box[3] > next_box[1])  # y overlap
        )
        assert has_overlap


def test_decompose_bbox_invalid_resolution():
    """Test decompose_bbox with resolution larger than bbox dimension."""
    bbox = (-122.001, 37.001, -122.0, 37.002)  # Very small bbox
    with pytest.raises(ValueError, match="Resolution must be less"):
        sdem.decompose_bbox(bbox, res=10000, pixel_max=1000)


def test_decompose_bbox_aspect_ratio():
    """Test that decomposed boxes maintain approximate aspect ratio."""
    bbox = (-122.0, 37.0, -121.0, 38.0)
    boxes, *_ = sdem.decompose_bbox(bbox, res=30, pixel_max=1000)

    # Calculate original aspect ratio
    orig_width = abs(bbox[2] - bbox[0])
    orig_height = abs(bbox[3] - bbox[1])
    orig_aspect = orig_width / orig_height

    # Calculate aspect ratio of subdivisions
    box = boxes[0]
    sub_width = abs(box[2] - box[0])
    sub_height = abs(box[3] - box[1])
    sub_aspect = sub_width / sub_height

    # Aspect ratios should be similar with some deviation due to rounding
    assert abs(orig_aspect - sub_aspect) < 0.5


def test_decompose_bbox_coverage():
    """Test that decomposed boxes cover the entire original bbox."""
    bbox = (-122.0, 37.0, -121.0, 38.0)
    boxes, *_ = sdem.decompose_bbox(bbox, res=30, pixel_max=1000)

    # Convert boxes to set of points for easier comparison
    points_covered = set()
    for box in boxes:
        west, south, east, north = box
        for x in [west, east]:
            for y in [south, north]:
                points_covered.add((round(x, 6), round(y, 6)))

    # Original bbox corners should be in points covered
    orig_west, orig_south, orig_east, orig_north = bbox
    orig_points = {
        (round(orig_west, 6), round(orig_south, 6)),
        (round(orig_west, 6), round(orig_north, 6)),
        (round(orig_east, 6), round(orig_south, 6)),
        (round(orig_east, 6), round(orig_north, 6)),
    }
    assert orig_points.issubset(points_covered)


def test_dem_and_vrt():
    bbox = (-121.1, 37.9, -121.0, 38.0)
    tiff_files = sdem.get_dem(bbox, "dem_data", 30)
    tiff_files = sdem.get_dem(bbox, "dem_data", 30)
    tiff_files[0].unlink()
    tiff_files = sdem.get_dem(bbox, "dem_data", 30, pixel_max=None)
    with rasterio.open(tiff_files[0]) as src:
        assert src.shape == (359, 359)
    tiff_files = sdem.get_dem(bbox, "dem_data", 30, pixel_max=80000)
    with rasterio.open(tiff_files[0]) as src:
        assert src.shape == (359, 179)
    vrt_file = Path("dem_data", "dem.vrt")
    sdem.build_vrt(vrt_file, tiff_files)
    assert vrt_file.stat().st_size == 1701
    shutil.rmtree("dem_data", ignore_errors=True)


def test_3dep():
    bbox = (-121.1, 37.9, -121.0, 38.0)
    tiff_files = sdem.get_map("Slope Degrees", bbox, "slope_data", 30, pixel_max=None)
    tiff_files = sdem.get_map("Slope Degrees", bbox, "slope_data", 30)
    tiff_files = sdem.get_map("Slope Degrees", bbox, "slope_data", 30)
    with rasterio.open(tiff_files[0]) as src:
        assert src.shape == (371, 293)
    tiff_files = sdem.get_map("Slope Degrees", bbox, "slope_data", 30, pixel_max=80000)
    with rasterio.open(tiff_files[0]) as src:
        assert src.shape == (371, 147)
    shutil.rmtree("slope_data", ignore_errors=True)


def test_3dep_3857():
    bbox = (-121.1, 37.9, -121.0, 38.0)
    tiff_files = sdem.get_map("DEM", bbox, "data_3857", 30, 3857)
    with rasterio.open(tiff_files[0]) as src:
        assert src.shape == (371, 293)
    shutil.rmtree("data_3857", ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def cleanup_after_all_tests():
    """Run cleanup logic at the end of the entire test session."""
    yield  # All tests run before this point
    _cleanup_pools()
