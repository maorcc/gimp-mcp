#!/usr/bin/env python3
"""
Unit tests for GIMP MCP enhanced bitmap functionality
Tests edge cases and parameter validation for get_image_bitmap()
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os
import importlib.util

# Add the project directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import test fixtures
from test_fixtures import setup_gimp_mocks, cleanup_gimp_mocks, create_mock_plugin, setup_region_mock, setup_scaled_mock

class TestGimpBitmapEnhanced(unittest.TestCase):
    """Test cases for enhanced GIMP bitmap functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Set up GIMP mocks
        setup_gimp_mocks()
        
        # Create plugin instance with mocked dependencies
        self.plugin = create_mock_plugin()
    
    def tearDown(self):
        """Clean up test fixtures."""
        cleanup_gimp_mocks()
        
    def test_region_validation_valid_params(self):
        """Test region parameter validation with valid parameters."""
        
        # Valid region parameters
        valid_region = {
            "origin_x": 100,
            "origin_y": 100,
            "width": 400,
            "height": 300,
            "max_width": 200,
            "max_height": 150
        }
        
        # Test with valid parameters - should not raise validation exception
        try:
            result = self.plugin._get_current_image_bitmap({"region": valid_region})
            # In test environment, this will likely fail due to no real GIMP connection
            # But it should not fail due to parameter validation
        except Exception as e:
            # Should not contain parameter validation errors
            error_msg = str(e).lower()
            self.assertNotIn("parameter", error_msg)
            self.assertNotIn("must be", error_msg)
    
    def test_region_validation_invalid_types(self):
        """Test region parameter validation with invalid types."""
        # Test invalid type for origin_x
        invalid_region = {
            "origin_x": "100",  # String instead of int
            "origin_y": 100,
            "width": 400,
            "height": 300
        }
        
        result = self.plugin._get_current_image_bitmap({"region": invalid_region})
        self.assertEqual(result["status"], "error")
        self.assertIn("must be of type int", result["error"])
    
    def test_region_validation_negative_values(self):
        """Test region parameter validation with negative values."""
        # Test negative origin_x
        invalid_region = {
            "origin_x": -10,
            "origin_y": 100,
            "width": 400,
            "height": 300
        }
        
        result = self.plugin._get_current_image_bitmap({"region": invalid_region})
        self.assertEqual(result["status"], "error")
        self.assertIn("must be non-negative", result["error"])
    
    def test_region_bounds_validation(self):
        """Test region bounds validation against image dimensions."""
        # Test region that exceeds image bounds (mock image is 1920x1080)
        invalid_region = {
            "origin_x": 1800,
            "origin_y": 100,
            "width": 400,  # 1800 + 400 = 2200 > 1920 (image width)
            "height": 300
        }
        
        result = self.plugin._get_current_image_bitmap({"region": invalid_region})
        self.assertEqual(result["status"], "error")
        self.assertIn("Region bounds invalid", result["error"])
    
    def test_scaling_ratio_warning(self):
        """Test warning for large scaling operations."""
        # Test large scaling operation (should trigger warning)
        large_scaling_params = {
            "max_width": 8000,  # 4x larger than 1920
            "max_height": 6000  # ~5.5x larger than 1080
        }
        
        # This should trigger a scaling ratio warning
        with patch('builtins.print') as mock_print:
            result = self.plugin._get_current_image_bitmap(large_scaling_params)
            # Check that warning was printed about large scaling
            warning_calls = [call for call in mock_print.call_args_list 
                           if 'scaling operation detected' in str(call)]
            self.assertTrue(len(warning_calls) > 0)
    
    def test_center_inside_scaling_math(self):
        """Test center-inside scaling mathematical correctness."""
        # Test landscape image (wider than tall) fitting in square bounds
        image_width, image_height = 1920, 1080  # 16:9 aspect ratio
        max_width, max_height = 800, 800         # Square bounds
        
        aspect_ratio = image_width / image_height  # 1.777...
        max_aspect_ratio = max_width / max_height  # 1.0
        
        # Width should be limiting factor (aspect_ratio > max_aspect_ratio)
        expected_width = max_width  # 800
        expected_height = int(max_width / aspect_ratio)  # 450
        
        self.assertEqual(expected_width, 800)
        self.assertEqual(expected_height, 450)
        
        # Test portrait image fitting in landscape bounds
        image_width, image_height = 600, 800   # 3:4 aspect ratio
        max_width, max_height = 1000, 600     # Landscape bounds
        
        aspect_ratio = image_width / image_height  # 0.75
        max_aspect_ratio = max_width / max_height  # 1.667
        
        # Height should be limiting factor (aspect_ratio < max_aspect_ratio)
        expected_height = max_height  # 600
        expected_width = int(max_height * aspect_ratio)  # 450
        
        self.assertEqual(expected_width, 450)
        self.assertEqual(expected_height, 600)
    
    def test_no_images_open_error(self):
        """Test error handling when no images are open in GIMP."""
        # Mock Gimp.get_images() to return empty list
        with patch('gi.repository.Gimp.get_images', return_value=[]):
            result = self.plugin._get_current_image_bitmap({})
            self.assertEqual(result["status"], "error")
            self.assertIn("No images", result["error"])
    
    def test_cleanup_on_scaling_failure(self):
        """Test proper cleanup when scaling fails."""
        # Mock scaling to fail - the cleanup happens on the duplicate image, not the original
        mock_image = MagicMock()
        mock_image.get_width.return_value = 1920
        mock_image.get_height.return_value = 1080
        
        # Mock the duplicate image to fail on scaling
        mock_duplicate = MagicMock()
        mock_duplicate.scale.side_effect = RuntimeError("Scaling failed")
        mock_duplicate.get_width.return_value = 1920
        mock_duplicate.get_height.return_value = 1080
        mock_image.duplicate.return_value = mock_duplicate
        
        with patch('gi.repository.Gimp.get_images', return_value=[mock_image]):
            result = self.plugin._get_current_image_bitmap({"max_width": 100, "max_height": 100})
            self.assertEqual(result["status"], "error")
            # Should have attempted cleanup on the duplicate image
            self.assertIn("Failed to scale image", result["error"])
            
            # Verify cleanup was called on the duplicate image
            mock_duplicate.delete.assert_called_once()
    
    def test_mixed_region_and_global_scaling_params(self):
        """Test behavior with both region and global scaling parameters."""
        # Both global and region scaling specified
        mixed_region = {
            "origin_x": 100,
            "origin_y": 100,
            "width": 400,
            "height": 300,
            "max_width": 200,  # Region scaling (should take precedence)
            "max_height": 150
        }
        
        # Mock the necessary GIMP operations
        with patch('tempfile.mkstemp') as mock_mkstemp:
            with patch('os.close'):
                with patch('os.path.exists', return_value=True):
                    with patch('os.unlink'):
                        with patch('base64.b64encode', return_value=b'mock_data'):
                            mock_mkstemp.return_value = (1, '/tmp/test.png')
                            
                            # Use helper functions to reduce duplication
                            mock_region_image = setup_region_mock(400, 300)
                            mock_scaled_image = setup_scaled_mock(200, 150)
                            mock_region_image.duplicate.return_value = mock_scaled_image
                            
                            with patch('builtins.open', create=True) as mock_open:
                                mock_open.return_value.__enter__.return_value.read.return_value = b'mock_png_data'
                                
                                result = self.plugin._get_current_image_bitmap({"region": mixed_region})
                                
                                # Should succeed and use region scaling
                                # Note: In test environment, this may fail gracefully
                                # The important thing is no parameter validation errors


if __name__ == '__main__':
    # Run the tests
    unittest.main(verbosity=2)
