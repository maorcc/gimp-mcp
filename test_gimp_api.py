#!/usr/bin/env python3
"""Test script to verify GIMP 3.0 API methods"""

import gi
gi.require_version('Gimp', '3.0')
from gi.repository import Gimp

def test_image_methods():
    """Test what methods are available on Image objects"""
    # Get the Image class methods
    image_methods = [method for method in dir(Gimp.Image) if not method.startswith('_')]
    print("Available Image methods:")
    for method in sorted(image_methods):
        if 'active' in method.lower() or 'drawable' in method.lower() or 'layer' in method.lower():
            print(f"  - {method}")
    
    print("\nLooking for layer-related methods:")
    layer_methods = [method for method in image_methods if 'layer' in method.lower()]
    for method in sorted(layer_methods):
        print(f"  - {method}")

if __name__ == "__main__":
    test_image_methods()
