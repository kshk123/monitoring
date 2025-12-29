"""Tests for package structure and entrypoint importability."""

import unittest
import sys
from pathlib import Path
import importlib
import tempfile
import os

# Add src to path for testing
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))


class TestPackageImportability(unittest.TestCase):
    """Test that the package can be imported correctly."""
    
    def test_src_package_has_init(self):
        """Verify src/__init__.py exists for package importability."""
        init_path = Path(__file__).parent.parent / 'src' / '__init__.py'
        self.assertTrue(init_path.exists(), 
                       "src/__init__.py must exist for entrypoint 'src.speed_test:main' to work")
    
    def test_speed_test_module_importable(self):
        """Test that speed_test module can be imported."""
        try:
            import speed_test
            self.assertTrue(hasattr(speed_test, 'main'))
            self.assertTrue(hasattr(speed_test, 'app'))
            self.assertTrue(callable(speed_test.main))
        except ImportError as e:
            self.fail(f"Failed to import speed_test: {e}")
    
    def test_speed_test_imports_local_modules(self):
        """Test that speed_test imports PrometheusManager and RouterRestartManager."""
        import speed_test
        # These should be importable via the try/except fallback
        self.assertTrue(hasattr(speed_test, 'PrometheusManager'))
        self.assertTrue(hasattr(speed_test, 'RouterRestartManager'))
    
    def test_prometheus_manager_importable(self):
        """Test that prometheus_manager module can be imported."""
        try:
            import prometheus_manager
            self.assertTrue(hasattr(prometheus_manager, 'PrometheusManager'))
        except ImportError as e:
            self.fail(f"Failed to import prometheus_manager: {e}")
    
    def test_router_restart_importable(self):
        """Test that router_restart module can be imported."""
        try:
            import router_restart
            self.assertTrue(hasattr(router_restart, 'RouterRestartManager'))
        except ImportError as e:
            self.fail(f"Failed to import router_restart: {e}")
    
    def test_main_function_exists_and_callable(self):
        """Test that the entrypoint main function exists."""
        from speed_test import main
        self.assertTrue(callable(main))


class TestConfigPathResolution(unittest.TestCase):
    """Test config path resolution for different execution contexts."""
    
    def test_resolve_absolute_path(self):
        """Test that absolute paths are used as-is."""
        from speed_test import _resolve_config_path
        
        abs_path = "/etc/speedtest/config.yaml"
        result = _resolve_config_path(abs_path)
        
        self.assertEqual(str(result), abs_path)
        self.assertTrue(result.is_absolute())
    
    def test_resolve_relative_path_project_root(self):
        """Test that relative paths are resolved from project root."""
        from speed_test import _resolve_config_path, _PROJECT_ROOT
        
        # The default config.yaml should be found at project root
        result = _resolve_config_path("config.yaml")
        
        expected = _PROJECT_ROOT / "config.yaml"
        self.assertEqual(result, expected)
    
    def test_resolve_path_falls_back_to_project_root(self):
        """Test fallback to project root when file doesn't exist in CWD."""
        from speed_test import _resolve_config_path, _PROJECT_ROOT
        
        # Non-existent file should default to project root path
        result = _resolve_config_path("nonexistent.yaml")
        
        expected = _PROJECT_ROOT / "nonexistent.yaml"
        self.assertEqual(result, expected)
    
    def test_load_config_from_project_root(self):
        """Test that config loads correctly regardless of CWD."""
        from speed_test import load_config, _PROJECT_ROOT
        
        # Save original CWD
        original_cwd = os.getcwd()
        
        try:
            # Change to a different directory (e.g., temp)
            with tempfile.TemporaryDirectory() as tmpdir:
                os.chdir(tmpdir)
                
                # Should still find config.yaml at project root
                config = load_config("config.yaml")
                
                self.assertIsInstance(config, dict)
                self.assertIn("speedtest", config)
        finally:
            os.chdir(original_cwd)
    
    def test_load_config_absolute_path(self):
        """Test loading config from absolute path."""
        from speed_test import load_config
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("speedtest:\n  retry_interval: 123\n")
            temp_path = f.name
        
        try:
            config = load_config(temp_path)
            self.assertEqual(config["speedtest"]["retry_interval"], 123)
        finally:
            os.unlink(temp_path)
    
    def test_load_config_file_not_found(self):
        """Test that FileNotFoundError is raised for missing config."""
        from speed_test import load_config
        
        with self.assertRaises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")
    
    def test_load_config_empty_file_returns_dict(self):
        """Test that empty config file returns empty dict, not None."""
        from speed_test import load_config
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("")  # Empty file
            temp_path = f.name
        
        try:
            config = load_config(temp_path)
            self.assertIsInstance(config, dict)
            self.assertEqual(config, {})
        finally:
            os.unlink(temp_path)
    
    def test_load_config_whitespace_only_returns_dict(self):
        """Test that whitespace-only config file returns empty dict."""
        from speed_test import load_config
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("   \n\n  \n")  # Whitespace only
            temp_path = f.name
        
        try:
            config = load_config(temp_path)
            self.assertIsInstance(config, dict)
            self.assertEqual(config, {})
        finally:
            os.unlink(temp_path)
    
    def test_load_config_non_dict_returns_empty_dict(self):
        """Test that non-dict YAML returns empty dict."""
        from speed_test import load_config
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("- item1\n- item2\n")  # YAML list, not dict
            temp_path = f.name
        
        try:
            config = load_config(temp_path)
            self.assertIsInstance(config, dict)
            self.assertEqual(config, {})
        finally:
            os.unlink(temp_path)


class TestConfigPathInDifferentContexts(unittest.TestCase):
    """Test config resolution simulating different execution contexts."""
    
    def test_systemd_execution_context(self):
        """Simulate systemd running from / or /root."""
        from speed_test import _resolve_config_path, _PROJECT_ROOT
        
        original_cwd = os.getcwd()
        
        try:
            # Simulate systemd context (root directory)
            os.chdir("/")
            
            result = _resolve_config_path("config.yaml")
            
            # Should still resolve to project root
            self.assertEqual(result, _PROJECT_ROOT / "config.yaml")
        finally:
            os.chdir(original_cwd)
    
    def test_pytest_from_repo_root(self):
        """Simulate pytest running from repo root (parent of network_speed)."""
        from speed_test import _resolve_config_path, _PROJECT_ROOT
        
        original_cwd = os.getcwd()
        
        try:
            # Simulate running from repo root
            repo_root = _PROJECT_ROOT.parent
            if repo_root.exists():
                os.chdir(repo_root)
                
                result = _resolve_config_path("config.yaml")
                
                # Should still resolve to project root
                self.assertEqual(result, _PROJECT_ROOT / "config.yaml")
        finally:
            os.chdir(original_cwd)


if __name__ == '__main__':
    unittest.main()
