#!/usr/bin/env python3
"""
Simplified unit tests for GIMP MCP bitmap parameter validation
Tests the core validation logic without complex module imports
"""

import unittest

class TestBitmapValidation(unittest.TestCase):
    """Test parameter validation logic for bitmap functionality."""
    
    def test_region_parameter_validation(self):
        """Test the region parameter validation logic."""
        
        def validate_region_params(region):
            """Extracted validation logic from the plugin."""
            if not region:
                return None
                
            # Validate region parameter types
            for key, expected_type in [("origin_x", int), ("origin_y", int), 
                                     ("width", int), ("height", int),
                                     ("max_width", int), ("max_height", int)]:
                if key in region and region[key] is not None:
                    if not isinstance(region[key], expected_type):
                        return f"Region parameter '{key}' must be of type {expected_type.__name__}, got {type(region[key]).__name__}"
                    if region[key] < 0:
                        return f"Region parameter '{key}' must be non-negative, got {region[key]}"
            return None
        
        # Test valid parameters
        valid_region = {
            "origin_x": 100,
            "origin_y": 100,
            "width": 400,
            "height": 300,
            "max_width": 200,
            "max_height": 150
        }
        self.assertIsNone(validate_region_params(valid_region))
        
        # Test invalid types
        invalid_type_region = {"origin_x": "100", "origin_y": 100}
        error = validate_region_params(invalid_type_region)
        self.assertIsNotNone(error)
        self.assertIn("must be of type int", error)
        
        # Test negative values
        negative_region = {"origin_x": -10, "origin_y": 100}
        error = validate_region_params(negative_region)
        self.assertIsNotNone(error)
        self.assertIn("must be non-negative", error)
        
        # Test None values (should be allowed)
        none_region = {"origin_x": None, "origin_y": 100}
        self.assertIsNone(validate_region_params(none_region))
        
        # Test empty region
        self.assertIsNone(validate_region_params({}))
    
    def test_region_bounds_validation(self):
        """Test region bounds validation against image dimensions."""
        
        def validate_region_bounds(origin_x, origin_y, width, height, img_width, img_height):
            """Extracted bounds validation logic."""
            if any(param is None for param in [origin_x, origin_y, width, height]):
                return "For region selection, all parameters are required: origin_x, origin_y, width, height"
            
            if (origin_x < 0 or origin_y < 0 or 
                origin_x + width > img_width or 
                origin_y + height > img_height):
                return f"Region bounds invalid. Image size: {img_width}x{img_height}, requested region: ({origin_x},{origin_y}) {width}x{height}"
            
            return None
        
        # Test valid bounds
        error = validate_region_bounds(100, 100, 400, 300, 1920, 1080)
        self.assertIsNone(error)
        
        # Test region exceeding width
        error = validate_region_bounds(1800, 100, 400, 300, 1920, 1080)
        self.assertIsNotNone(error)
        self.assertIn("Region bounds invalid", error)
        
        # Test region exceeding height
        error = validate_region_bounds(100, 900, 400, 300, 1920, 1080)
        self.assertIsNotNone(error)
        self.assertIn("Region bounds invalid", error)
        
        # Test negative origin
        error = validate_region_bounds(-10, 100, 400, 300, 1920, 1080)
        self.assertIsNotNone(error)
        self.assertIn("Region bounds invalid", error)
        
        # Test missing parameters
        error = validate_region_bounds(None, 100, 400, 300, 1920, 1080)
        self.assertIsNotNone(error)
        self.assertIn("all parameters are required", error)
    
    def test_center_inside_scaling_math(self):
        """Test center-inside scaling mathematical correctness."""
        
        def calculate_center_inside_dimensions(current_width, current_height, max_width, max_height):
            """Extracted center-inside scaling logic."""
            aspect_ratio = current_width / current_height
            max_aspect_ratio = max_width / max_height
            
            if aspect_ratio > max_aspect_ratio:
                # Width is the limiting factor
                target_width = max_width
                target_height = int(max_width / aspect_ratio)
            else:
                # Height is the limiting factor
                target_height = max_height
                target_width = int(max_height * aspect_ratio)
            
            return target_width, target_height
        
        # Test landscape image (16:9) fitting in square bounds
        width, height = calculate_center_inside_dimensions(1920, 1080, 800, 800)
        self.assertEqual(width, 800)
        self.assertEqual(height, 450)  # 800 / (1920/1080) = 450
        
        # Test portrait image (3:4) fitting in landscape bounds
        width, height = calculate_center_inside_dimensions(600, 800, 1000, 600)
        self.assertEqual(width, 450)   # 600 * (600/800) = 450
        self.assertEqual(height, 600)
        
        # Test exact aspect ratio match
        width, height = calculate_center_inside_dimensions(1920, 1080, 960, 540)
        self.assertEqual(width, 960)
        self.assertEqual(height, 540)
        
        # Test no scaling needed (image smaller than bounds)
        width, height = calculate_center_inside_dimensions(400, 300, 800, 600)
        self.assertEqual(width, 800)   # Scales up to fit bounds
        self.assertEqual(height, 600)
    
    def test_scaling_ratio_calculation(self):
        """Test scaling ratio calculation for performance warnings."""
        
        def calculate_scaling_ratio(target_width, target_height, current_width, current_height):
            """Calculate scaling ratio (area change)."""
            return (target_width * target_height) / (current_width * current_height)
        
        # Test no scaling
        ratio = calculate_scaling_ratio(1920, 1080, 1920, 1080)
        self.assertEqual(ratio, 1.0)
        
        # Test 2x upscaling (4x area)
        ratio = calculate_scaling_ratio(3840, 2160, 1920, 1080)
        self.assertEqual(ratio, 4.0)
        
        # Test downscaling
        ratio = calculate_scaling_ratio(960, 540, 1920, 1080)
        self.assertEqual(ratio, 0.25)
        
        # Test large upscaling (should trigger warning)
        ratio = calculate_scaling_ratio(7680, 4320, 1920, 1080)  # 4K to 8K
        self.assertEqual(ratio, 16.0)
        self.assertGreater(ratio, 4.0)  # Should trigger warning
    
    def test_parameter_extraction_logic(self):
        """Test parameter extraction from nested region structure."""
        
        def extract_parameters(params):
            """Extract parameters from params dict with region nesting."""
            max_width = params.get("max_width")
            max_height = params.get("max_height")
            
            region = params.get("region", {})
            origin_x = region.get("origin_x")
            origin_y = region.get("origin_y")
            region_width = region.get("width")
            region_height = region.get("height")
            scaled_to_width = region.get("max_width")
            scaled_to_height = region.get("max_height")
            
            return {
                "max_width": max_width,
                "max_height": max_height,
                "origin_x": origin_x,
                "origin_y": origin_y,
                "region_width": region_width,
                "region_height": region_height,
                "scaled_to_width": scaled_to_width,
                "scaled_to_height": scaled_to_height
            }
        
        # Test global scaling only
        params = {"max_width": 800, "max_height": 600}
        result = extract_parameters(params)
        self.assertEqual(result["max_width"], 800)
        self.assertEqual(result["max_height"], 600)
        self.assertIsNone(result["origin_x"])
        
        # Test region extraction only
        params = {
            "region": {
                "origin_x": 100,
                "origin_y": 100,
                "width": 400,
                "height": 300
            }
        }
        result = extract_parameters(params)
        self.assertIsNone(result["max_width"])
        self.assertEqual(result["origin_x"], 100)
        self.assertEqual(result["region_width"], 400)
        
        # Test region with scaling
        params = {
            "region": {
                "origin_x": 100,
                "origin_y": 100,
                "width": 400,
                "height": 300,
                "max_width": 200,
                "max_height": 150
            }
        }
        result = extract_parameters(params)
        self.assertEqual(result["origin_x"], 100)
        self.assertEqual(result["scaled_to_width"], 200)
        self.assertEqual(result["scaled_to_height"], 150)
        
        # Test empty params
        result = extract_parameters({})
        self.assertIsNone(result["max_width"])
        self.assertIsNone(result["origin_x"])


if __name__ == '__main__':
    # Run the tests
    unittest.main(verbosity=2)
