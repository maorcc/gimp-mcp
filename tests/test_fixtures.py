"""
Test fixtures and mocks for GIMP MCP plugin testing.
Provides mock objects for GIMP API to enable testing without GIMP installation.
"""

import sys
from unittest.mock import MagicMock, Mock


class MockGimpImageBaseType:
    """Mock for Gimp.ImageBaseType enum."""
    RGB = 0
    GRAY = 1
    INDEXED = 2


class MockGimpLayerMode:
    """Mock for Gimp.LayerMode enum."""
    NORMAL = 0


class MockGimpPrecision:
    """Mock for Gimp.Precision enum."""
    U8_LINEAR = 100
    U8_GAMMA = 150
    U16_LINEAR = 200
    U16_GAMMA = 250
    U32_LINEAR = 300
    U32_GAMMA = 350
    HALF_LINEAR = 500
    HALF_GAMMA = 550
    FLOAT_LINEAR = 600
    FLOAT_GAMMA = 650
    DOUBLE_LINEAR = 700
    DOUBLE_GAMMA = 750


class MockGimpLayer:
    """Mock for GIMP Layer object."""
    def __init__(self):
        self.get_name = Mock(return_value="Test Layer")
        self.get_width = Mock(return_value=1920)
        self.get_height = Mock(return_value=1080)
        self.has_alpha = Mock(return_value=True)
        self.get_type = Mock(return_value=MockGimpImageBaseType.RGB)
        self.get_mode = Mock(return_value=MockGimpLayerMode.NORMAL)


class MockGimpImage:
    """Mock for GIMP Image object."""
    def __init__(self):
        self.get_width = Mock(return_value=1920)
        self.get_height = Mock(return_value=1080)
        self.get_base_type = Mock(return_value=MockGimpImageBaseType.RGB)
        self.get_precision = Mock(return_value=MockGimpPrecision.U8_LINEAR)
        self.get_layers = Mock(return_value=[MockGimpLayer()])
        self.get_active_layer = Mock(return_value=MockGimpLayer())
        self.select_rectangle = Mock(return_value=None)
        self.select_none = Mock(return_value=None)
        self.duplicate = Mock(return_value=None)  # Will be set dynamically in tests
        self.merge_visible_layers = Mock(return_value=MockGimpLayer())
        self.flatten = Mock(return_value=MockGimpLayer())
        self.insert_layer = Mock(return_value=None)
        self.scale = Mock(return_value=None)
        self.delete = Mock(return_value=None)


class MockGimpSelection:
    """Mock for Gimp.Selection static methods."""
    @staticmethod
    def none(image):
        return None


class MockGimpPlugin:
    """Mock for Gimp.PlugIn base class."""
    __gtype__ = Mock()  # Make it a class attribute, not instance
    
    def __init__(self):
        pass

class MockGimp:
    """Mock for main Gimp module."""
    ImageBaseType = MockGimpImageBaseType
    LayerMode = MockGimpLayerMode
    Precision = MockGimpPrecision
    Selection = MockGimpSelection
    PlugIn = MockGimpPlugin  # Add PlugIn class for inheritance
    
    @staticmethod
    def get_images():
        return [MockGimpImage()]
    
    @staticmethod
    def main(plugin_type, args):
        pass
    
    class Image:
        @staticmethod
        def new(width, height, base_type):
            return MockGimpImage()
    
    class Layer:
        @staticmethod
        def new(image, name, width, height, layer_type, opacity, mode):
            return MockGimpLayer()
    
    @staticmethod
    def edit_copy(layers):
        return None
    
    @staticmethod
    def edit_paste(layer, paste_into):
        return [MockGimpLayer()]
    
    @staticmethod
    def floating_sel_anchor(selection):
        return None


class MockGi:
    """Mock for gi module."""
    
    @staticmethod
    def require_version(module, version):
        """Mock gi.require_version() - does nothing in tests."""
        pass
    
    class repository:
        Gimp = MockGimp
        GLib = Mock()  # Mock GLib dependency


def setup_gimp_mocks():
    """Set up GIMP mocks in sys.modules to enable plugin import."""
    # Mock gi module
    gi_mock = MockGi()
    sys.modules['gi'] = gi_mock
    sys.modules['gi.repository'] = gi_mock.repository
    sys.modules['gi.repository.Gimp'] = MockGimp
    
    return gi_mock


def cleanup_gimp_mocks():
    """Clean up GIMP mocks from sys.modules."""
    modules_to_remove = [
        'gi',
        'gi.repository', 
        'gi.repository.Gimp'
    ]
    
    for module in modules_to_remove:
        if module in sys.modules:
            del sys.modules[module]


def setup_region_mock(width=400, height=300):
    """Helper to create standardized region mock objects."""
    mock_region_image = MagicMock()
    mock_region_image.get_width.return_value = width
    mock_region_image.get_height.return_value = height
    mock_region_image.get_layers.return_value = [MockGimpLayer()]
    mock_region_image.get_active_layer.return_value = MockGimpLayer()
    return mock_region_image


def setup_scaled_mock(width=200, height=150):
    """Helper to create standardized scaled image mock objects."""
    mock_scaled_image = MagicMock()
    mock_scaled_image.get_width.return_value = width
    mock_scaled_image.get_height.return_value = height
    mock_scaled_image.get_layers.return_value = [MockGimpLayer()]
    mock_scaled_image.get_active_layer.return_value = MockGimpLayer()
    return mock_scaled_image


def create_mock_plugin():
    """Create a mock MCPPlugin instance with mocked GIMP dependencies."""
    setup_gimp_mocks()
    
    # Import plugin module with dash handling
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "gimp_mcp_plugin", 
        "/home/fred/dev/gimp-mcp/gimp-mcp-plugin.py"
    )
    module = importlib.util.module_from_spec(spec)
    
    # Prevent Gimp.main execution during import
    original_main = MockGimp.main
    MockGimp.main = lambda *args: None
    
    try:
        spec.loader.exec_module(module)
        plugin = module.MCPPlugin()
        return plugin
    finally:
        MockGimp.main = original_main
