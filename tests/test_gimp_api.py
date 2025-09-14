#!/usr/bin/env python3
"""Test GIMP API compatibility and method availability"""

import unittest
from unittest.mock import Mock, patch
from test_fixtures import setup_gimp_mocks, cleanup_gimp_mocks, create_mock_plugin

class TestGimpApiCompatibility(unittest.TestCase):
    """Test GIMP API method availability and compatibility"""
    
    def setUp(self):
        """Set up test fixtures."""
        setup_gimp_mocks()
        self.plugin = create_mock_plugin()

    def tearDown(self):
        """Clean up test fixtures."""
        cleanup_gimp_mocks()
    
    def test_image_methods_availability(self):
        """Test that required Image methods are available in our mocks"""
        # Test core image methods used by the plugin
        from gi.repository import Gimp
        
        # Verify our mock has the required methods
        image = Gimp.Image.new(100, 100, Gimp.ImageBaseType.RGB)
        
        # Test method availability
        self.assertTrue(hasattr(image, 'get_width'))
        self.assertTrue(hasattr(image, 'get_height'))
        self.assertTrue(hasattr(image, 'get_base_type'))
        self.assertTrue(hasattr(image, 'duplicate'))
        self.assertTrue(hasattr(image, 'scale'))
        self.assertTrue(hasattr(image, 'delete'))
        
        # Test method calls work
        self.assertEqual(image.get_width(), 1920)  # From mock
        self.assertEqual(image.get_height(), 1080)  # From mock
        
    def test_layer_methods_availability(self):
        """Test that required Layer methods are available in our mocks"""
        from gi.repository import Gimp
        
        # Create a mock layer
        layer = Gimp.Layer.new(None, "test", 100, 100, 
                              Gimp.ImageBaseType.RGB, 100, 
                              Gimp.LayerMode.NORMAL)
        
        # Test method availability
        self.assertTrue(hasattr(layer, 'get_width'))
        self.assertTrue(hasattr(layer, 'get_height'))
        self.assertTrue(hasattr(layer, 'get_name'))
        
        # Test method calls work
        self.assertEqual(layer.get_width(), 1920)  # From mock
        self.assertEqual(layer.get_height(), 1080)  # From mock
        self.assertEqual(layer.get_name(), "Test Layer")  # From mock

    def test_gimp_static_methods(self):
        """Test that required static GIMP methods work"""
        from gi.repository import Gimp
        
        # Test get_images method
        images = Gimp.get_images()
        self.assertIsInstance(images, list)
        self.assertTrue(len(images) > 0)
        
        # Test main method exists (won't actually call it)
        self.assertTrue(hasattr(Gimp, 'main'))

if __name__ == '__main__':
    unittest.main(verbosity=2)
