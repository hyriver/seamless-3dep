from __future__ import annotations

import itertools
import math
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pytest
import rasterio
import shapely

import seamless_3dep as s3dep
from seamless_3dep._vrt_pools import VRTPool
from seamless_3dep.seamless_3dep import _check_bbox, _check_bounds, _snap_window


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
    boxes, *_ = s3dep.decompose_bbox(valid_bbox, small_res, pixel_max * 100)
    assert len(boxes) == 1
    assert boxes[0] == valid_bbox


def test_decompose_bbox_with_division(valid_bbox: tuple[float, float, float, float]):
    """Test when bbox needs to be divided."""
    # Use small pixel_max to force division
    small_pixel_max = 1000
    boxes, *_ = s3dep.decompose_bbox(valid_bbox, 30, small_pixel_max)
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
    buff = 2
    _, sub_w_nobuff, sub_h_nobuff = s3dep.decompose_bbox(bbox, 30, 1000)
    boxes, sub_w, sub_h = s3dep.decompose_bbox(bbox, 30, 1000, buff_npixels=buff)
    # Returned pixel dims include buffer on both sides
    assert sub_w == sub_w_nobuff + 2 * buff
    assert sub_h == sub_h_nobuff + 2 * buff
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


@pytest.mark.parametrize(
    "bad_bbox",
    [
        "not a sequence",
        (1, 2, 3),  # too short
        (1, 2, 3, 4, 5),  # too long
        (math.nan, 0, 1, 1),  # NaN
        (0, 0, math.inf, 1),  # inf
    ],
)
def test_check_bbox_rejects_malformed(bad_bbox: object):
    """`_check_bbox` rejects non-sequences, wrong lengths, and non-finite values."""
    with pytest.raises(TypeError, match="`bbox` must be"):
        _check_bbox(bad_bbox)


@pytest.mark.parametrize(
    "bad_bbox",
    [
        (1.0, 0.0, 0.0, 1.0),  # west >= east
        (0.0, 1.0, 1.0, 0.0),  # south >= north
        (1.0, 1.0, 1.0, 1.0),  # degenerate
    ],
)
def test_check_bbox_rejects_unordered(bad_bbox: tuple[float, float, float, float]):
    """`_check_bbox` rejects bboxes that are not (W < E, S < N)."""
    with pytest.raises(ValueError, match="ordered"):
        _check_bbox(bad_bbox)


def test_check_bounds_accepts_inside_and_rejects_outside():
    """`_check_bounds` accepts bbox fully inside, rejects partially outside."""
    bounds = (-180.0, -90.0, 180.0, 90.0)
    _check_bounds((-1.0, -1.0, 1.0, 1.0), bounds)  # inside
    _check_bounds(bounds, bounds)  # exactly equal — should pass
    with pytest.raises(ValueError, match="must be within"):
        _check_bounds((-181.0, -1.0, 1.0, 1.0), bounds)
    with pytest.raises(ValueError, match="must be within"):
        _check_bounds((-1.0, -1.0, 1.0, 91.0), bounds)


def test_snap_window_aligns_adjacent_tiles():
    """`_snap_window` must give adjacent fractional windows the same shared edge.

    Regression for the half-pixel gap reported in #28: when two tiles share a
    fractional pixel boundary, both must round to the same integer pixel after
    snapping so the saved GeoTIFFs tile exactly without gap or overlap.
    """
    # Two windows that share a fractional row boundary at row 100.4
    upper = rasterio.windows.Window(col_off=0.3, row_off=10.7, width=50.6, height=89.7)
    lower = rasterio.windows.Window(col_off=0.3, row_off=100.4, width=50.6, height=120.2)
    # Sanity: shared boundary is bit-identical
    assert upper.row_off + upper.height == lower.row_off

    upper_snapped = _snap_window(upper)
    lower_snapped = _snap_window(lower)
    # Shared edge after snapping must match exactly
    assert upper_snapped.row_off + upper_snapped.height == lower_snapped.row_off
    # And horizontal alignment too
    assert upper_snapped.col_off == lower_snapped.col_off
    assert upper_snapped.width == lower_snapped.width


def test_snap_window_handles_negative_offsets():
    """`_snap_window` must work when the requested bbox extends past the source."""
    # E.g. a bbox that starts before the VRT's upper-left → negative col_off/row_off.
    w = rasterio.windows.Window(col_off=-2.4, row_off=-1.6, width=10.7, height=8.3)
    snapped = _snap_window(w)
    # Endpoints round consistently: round(-2.4) = -2, round(-2.4 + 10.7) = round(8.3) = 8
    assert snapped.col_off == -2
    assert snapped.col_off + snapped.width == round(w.col_off + w.width)
    assert snapped.row_off == -2
    assert snapped.row_off + snapped.height == round(w.row_off + w.height)


def test_decompose_bbox_invalid_resolution():
    """Test decompose_bbox with resolution larger than bbox dimension."""
    bbox = (-122.001, 37.001, -122.0, 37.002)  # Very small bbox
    with pytest.raises(ValueError, match="Resolution must be less"):
        s3dep.decompose_bbox(bbox, 10000, 1000)


def test_decompose_bbox_aspect_ratio():
    """Test that decomposed boxes maintain approximate aspect ratio."""
    bbox = (-122.0, 37.0, -121.0, 38.0)
    boxes, *_ = s3dep.decompose_bbox(bbox, 30, 1000)

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
    boxes, *_ = s3dep.decompose_bbox(bbox, 30, 1000)

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


@pytest.mark.network
def test_dem_and_vrt(tmp_path):
    bbox = (-121.1, 37.9, -121.0, 38.0)
    dem_dir = tmp_path / "dem_data"
    tiff_files = s3dep.get_dem(bbox, dem_dir, 30)
    tiff_files = s3dep.get_dem(bbox, dem_dir, 30)
    tiff_files[0].unlink()
    tiff_files = s3dep.get_dem(bbox, dem_dir, 30, pixel_max=None)
    with rasterio.open(tiff_files[0]) as src:
        # 0.1 deg span at 1 arc-second resolution = 360 pixels exactly.
        assert src.shape == (360, 360)
    tiff_files = s3dep.get_dem(bbox, dem_dir, 30, pixel_max=80000)
    with rasterio.open(tiff_files[0]) as src:
        assert src.shape == (360, 180)
    vrt_file = dem_dir / "dem.vrt"
    s3dep.build_vrt(vrt_file, tiff_files)
    assert vrt_file.stat().st_size > 0
    dem = s3dep.tiffs_to_da(tiff_files, bbox, 4326)
    assert dem.shape == (360, 360)
    dem = s3dep.tiffs_to_da(tiff_files, shapely.box(*bbox), 4326)
    assert dem.shape == (360, 360)


@pytest.mark.network
def test_adjacent_tile_alignment(tmp_path):
    """Tiles produced by `get_dem` must share an exact pixel grid.

    Regression for #28: at the bbox from the issue,
    (-121.766, 45.165, -121.518, 45.671) at 10 m decomposes into two
    vertically stacked tiles. Before the fix in `_snap_window`, the
    fractional-window write left a ~half-pixel (~4 m) gap at the seam.
    After the fix, adjacent tiles must lie on the same source pixel
    grid: the north tile's south edge and the south tile's north edge
    must agree to far below pixel precision (any residual mismatch is
    pure float arithmetic noise from recomputing bounds via transforms).
    """
    bbox = (-121.766, 45.165, -121.518, 45.671)
    tiff_files = s3dep.get_dem(bbox, tmp_path / "alignment", res=10)
    assert len(tiff_files) >= 2

    info: list[tuple[float, float, float, float, float]] = []
    for f in tiff_files:
        with rasterio.open(f) as src:
            b = src.bounds
            pixel_height = abs(src.transform.e)
            info.append((b.left, b.right, b.top, b.bottom, pixel_height))

    by_top = sorted(info, key=lambda r: -r[2])
    paired = False
    for prev, curr in itertools.pairwise(by_top):
        prev_left, prev_right, _, prev_bottom, prev_dy = prev
        curr_left, curr_right, curr_top, _, _curr_dy = curr
        if prev_left == curr_left and prev_right == curr_right:
            # Old behavior left a ~half-pixel (~half of `dy`) gap. Require
            # the residual to be orders of magnitude tighter than a pixel.
            assert abs(prev_bottom - curr_top) < 1e-3 * prev_dy, (
                f"Adjacent tiles misaligned by {prev_bottom - curr_top} deg "
                f"(pixel height = {prev_dy})"
            )
            paired = True
    assert paired, "Expected at least one pair of vertically adjacent tiles"


@pytest.mark.network
def test_3dep(tmp_path):
    bbox = (-121.1, 37.9, -121.0, 38.0)
    slope_dir = tmp_path / "slope_data"
    tiff_files = s3dep.get_map("Slope Degrees", bbox, slope_dir, 30, pixel_max=None)
    tiff_files = s3dep.get_map("Slope Degrees", bbox, slope_dir, 30)
    with rasterio.open(tiff_files[0]) as src:
        assert src.shape == (371, 293)
    tiff_files = s3dep.get_map("Slope Degrees", bbox, slope_dir, 30, pixel_max=80000)
    with rasterio.open(tiff_files[0]) as src:
        assert src.shape == (371, 147)


def test_build_vrt_pixel_function_changes_overlap_resolution(tmp_path):
    """`pixel_function="min"` (or "max") must change how overlapping pixels resolve.

    Build two tiny GeoTIFFs that overlap in one row of pixels but disagree on the
    value there. Default `gdalbuildvrt` is "last input wins"; with
    `pixel_function="min"`/"max" the overlap row collapses to the per-pixel
    extremum. Verifying both directions gives confidence the flag is actually
    being plumbed through to the gdalbuildvrt CLI.
    """
    rasterio_transform = pytest.importorskip("rasterio.transform")

    transform = rasterio_transform.from_origin(0.0, 10.0, 1.0, 1.0)
    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "width": 4,
        "height": 4,
        "count": 1,
        "transform": transform,
        "crs": "EPSG:4326",
    }

    # Top tile covers rows 0-3 of pixel-space (y in [10, 6]) with value 10.0.
    top = tmp_path / "top.tiff"
    with rasterio.open(top, "w", **profile) as dst:
        dst.write(np.full((4, 4), 10.0, dtype="float32"), 1)

    # Bottom tile covers rows 3-6 (y in [7, 3]) with value 20.0; overlaps the
    # top tile on row 3.
    bottom = tmp_path / "bottom.tiff"
    bottom_profile = {**profile, "transform": rasterio_transform.from_origin(0.0, 7.0, 1.0, 1.0)}
    with rasterio.open(bottom, "w", **bottom_profile) as dst:
        dst.write(np.full((4, 4), 20.0, dtype="float32"), 1)

    for fn, expected_overlap in [("min", 10.0), ("max", 20.0)]:
        vrt = tmp_path / f"{fn}.vrt"
        s3dep.build_vrt(vrt, [top, bottom], pixel_function=fn)
        with rasterio.open(vrt) as src:
            data = src.read(1)
        # The overlap row (y in [7, 6]) should be the chosen extremum.
        # Find the row whose y-band straddles the overlap by inspecting bounds.
        y_top = src.bounds.top
        overlap_row = round(y_top - 7.0)  # one row of overlap at y=7
        assert data[overlap_row].tolist() == [expected_overlap] * 4, (
            f"pixel_function={fn!r}: overlap row was {data[overlap_row].tolist()!r}, "
            f"expected {expected_overlap}"
        )


def test_tiffs_to_da_rejects_non_iterable_and_missing_files():
    """`tiffs_to_da` reports clear errors before touching the network."""
    bbox = (-122.0, 37.0, -121.0, 38.0)
    with pytest.raises(TypeError, match="iterable"):
        s3dep.tiffs_to_da(123, bbox)
    with pytest.raises(ValueError, match="No valid"):
        s3dep.tiffs_to_da([], bbox)
    with pytest.raises(ValueError, match="No valid"):
        s3dep.tiffs_to_da([Path("/does/not/exist.tiff")], bbox)


def test_get_dem_cache_hit_skips_network(tmp_path, monkeypatch):
    """If every expected tile already exists, `get_dem` must not touch the network."""
    bbox = (-122.0, 37.0, -121.99, 37.01)  # tiny enough to be a single tile

    # Pre-create the file with the exact filename `get_dem` will look for.
    from seamless_3dep.seamless_3dep import MAX_PIXELS

    bbox_list, _, _ = s3dep.decompose_bbox(bbox, 30, MAX_PIXELS)
    save_dir = tmp_path / "cached"
    save_dir.mkdir()
    from seamless_3dep.seamless_3dep import _create_hash

    expected = save_dir / f"dem_{_create_hash(bbox_list[0], 30, 4326)}.tiff"
    expected.touch()

    # Sabotage `_run_clip_pool` so any attempt to actually fetch raises.
    def _fail_pool(*args, **kwargs):
        msg = "Cache-hit path should not invoke _run_clip_pool"
        raise AssertionError(msg)

    monkeypatch.setattr("seamless_3dep.seamless_3dep._run_clip_pool", _fail_pool)
    # Stub out VRTPool.get_vrt_info so we don't go to the network for metadata.
    from seamless_3dep._vrt_pools import VRTInfo

    fake_info = VRTInfo(
        bounds=(-180.0, -90.0, 180.0, 90.0),
        transform=rasterio.transform.from_origin(-180.0, 90.0, 1.0, 1.0),
        nodata=0.0,
    )
    monkeypatch.setattr("seamless_3dep.seamless_3dep.VRTPool.get_vrt_info", lambda res: fake_info)

    out = s3dep.get_dem(bbox, save_dir, 30)
    assert out == [expected]


def test_build_vrt_failure():
    """Test that `build_vrt` raises an error when given empty TIFF files."""
    with TemporaryDirectory() as tmpdir:
        vrt_path = Path(tmpdir) / "output.vrt"
        tiff1 = Path(tmpdir) / "empty1.tif"
        tiff1.touch()
        tiff2 = Path(tmpdir) / "empty2.tif"
        tiff2.touch()
        tiff3 = Path(tmpdir) / "empty3.tif"

        with pytest.raises(RuntimeError) as excinfo:
            s3dep.build_vrt(vrt_path, [tiff1, tiff2])

        assert "Command 'gdalbuildvrt" in str(excinfo.value)

        with pytest.raises(ValueError, match="No valid") as excinfo:
            s3dep.build_vrt(vrt_path, [tiff1, tiff2, tiff3])

        assert "No valid files" in str(excinfo.value)


@pytest.mark.network
def test_subpixel_interpolation():
    """Test that sub-pixel query points produce distinct interpolated values.

    When query points are spaced finer than the ~10m DEM pixel size,
    each point should get a unique interpolated value rather than being
    snapped to the nearest pixel center (which would cause staircase artifacts).
    """
    # At ~40N latitude, 10m ≈ 0.0001 degrees
    # Create a grid much finer than the DEM pixel size
    longs = np.linspace(-105.5, -105.499, 10)  # ~11m span, 10 points
    lats = np.linspace(40.0, 40.001, 10)  # ~111m span, 10 points

    elev = s3dep.elevation_bygrid(longs, lats, window=5, resampling=1)
    assert elev.shape == (10, 10)
    n_unique = len(np.unique(elev))
    # With proper sub-pixel interpolation, nearly all values should be unique
    # Without it (pixel snapping), many points would share the same value
    assert n_unique > elev.size * 0.8


@pytest.fixture(scope="session", autouse=True)
def cleanup_after_all_tests():
    """Run cleanup logic at the end of the entire test session."""
    yield  # All tests run before this point
    VRTPool.close()
