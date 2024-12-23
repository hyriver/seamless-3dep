import pytest
import math
import seamless_3dep as sdem

def test_basic_bbox_no_decomposition():
    """Test when bbox is small enough to not need decomposition"""
    bbox = (-122.5, 37.5, -122.0, 38.0)
    resolution = 1000  # 1km
    pixel_max = 100000
    
    result = sdem.decompose_bbox(bbox, resolution, pixel_max)
    assert len(result) == 1
    assert result[0] == bbox

def test_basic_bbox_with_buffer():
    """Test single bbox with buffer"""
    bbox = (-122.5, 37.5, -122.0, 38.0)
    resolution = 1000  # 1km
    pixel_max = 100000
    buff_pixel = 10
    
    result = sdem.decompose_bbox(bbox, resolution, pixel_max, buff_pixel)
    assert len(result) == 1
    
    # Buffer should extend beyond original bbox
    buffered = result[0]
    assert buffered[0] < bbox[0]  # west
    assert buffered[1] < bbox[1]  # south
    assert buffered[2] > bbox[2]  # east
    assert buffered[3] > bbox[3]  # north

def test_decomposition_no_buffer():
    """Test bbox decomposition without buffer"""
    bbox = (-122.5, 37.5, -122.0, 38.0)
    resolution = 100  # 100m
    pixel_max = 1000
    
    result = sdem.decompose_bbox(bbox, resolution, pixel_max)
    assert len(result) > 1
    
    # Check each sub-bbox is within original bbox
    for sub_bbox in result:
        assert sub_bbox[0] >= bbox[0]  # west
        assert sub_bbox[1] >= bbox[1]  # south
        assert sub_bbox[2] <= bbox[2]  # east
        assert sub_bbox[3] <= bbox[3]  # north

def test_decomposition_with_buffer():
    """Test bbox decomposition with buffer"""
    bbox = (-122.5, 37.5, -122.0, 38.0)
    resolution = 100  # 100m
    pixel_max = 1000
    buff_pixel = 10
    
    result = sdem.decompose_bbox(bbox, resolution, pixel_max, buff_pixel)
    assert len(result) > 1
    
    # Get original sub-boxes for comparison
    original = sdem.decompose_bbox(bbox, resolution, pixel_max, 0)
    
    # Check each buffered sub-bbox extends beyond its original
    for buff_box, orig_box in zip(result, original):
        assert buff_box[0] < orig_box[0]  # west
        assert buff_box[1] < orig_box[1]  # south
        assert buff_box[2] > orig_box[2]  # east
        assert buff_box[3] > orig_box[3]  # north

def test_resolution_validation():
    """Test resolution validation"""
    bbox = (-122.5, 37.5, -122.0, 38.0)
    resolution = 1000000  # 1000km, larger than bbox
    pixel_max = 1000
    
    with pytest.raises(ValueError, match="Resolution must be less than the smallest dimension"):
        sdem.decompose_bbox(bbox, resolution, pixel_max)

def test_invalid_bbox():
    """Test invalid bbox validation"""
    invalid_bbox = (-122.5, 37.5, -123.0, 38.0)  # west > east
    resolution = 100
    pixel_max = 1000
    
    with pytest.raises(ValueError):
        sdem.decompose_bbox(invalid_bbox, resolution, pixel_max)

def test_buffer_size_consistency():
    """Test that buffer size is consistent across sub-boxes"""
    bbox = (-122.5, 37.5, -122.0, 38.0)
    resolution = 100  # 100m
    pixel_max = 1000
    buff_pixel = 10
    
    result = sdem.decompose_bbox(bbox, resolution, pixel_max, buff_pixel)
    
    # Calculate expected buffer size for first box
    first_box = result[0]
    first_buffer_x = abs(first_box[0] - sdem.decompose_bbox(bbox, resolution, pixel_max)[0][0])
    first_buffer_y = abs(first_box[1] - sdem.decompose_bbox(bbox, resolution, pixel_max)[0][1])
    
    # Check buffer consistency across all boxes
    for buff_box, orig_box in zip(result, sdem.decompose_bbox(bbox, resolution, pixel_max)):
        buffer_x = abs(buff_box[0] - orig_box[0])
        buffer_y = abs(buff_box[1] - orig_box[1])
        
        # Allow for small floating point differences
        assert math.isclose(buffer_x, first_buffer_x, rel_tol=1e-9)
        assert math.isclose(buffer_y, first_buffer_y, rel_tol=1e-9)

def test_bbox_coverage():
    """Test that decomposed boxes cover the entire original bbox"""
    bbox = (-122.5, 37.5, -122.0, 38.0)
    resolution = 100  # 100m
    pixel_max = 1000
    
    result = sdem.decompose_bbox(bbox, resolution, pixel_max)
    
    # Check no gaps between boxes
    for i in range(len(result) - 1):
        current_box = result[i]
        next_box = result[i + 1]
        
        # Either boxes should align on x or y coordinate
        x_aligned = math.isclose(current_box[2], next_box[0], rel_tol=1e-9)
        y_aligned = math.isclose(current_box[3], next_box[1], rel_tol=1e-9)
        assert x_aligned or y_aligned
