"""Tests for WSGI mode where main() is never called."""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))


class TestWsgiModeConfig(unittest.TestCase):
    """Test that app works correctly when main() is not called (WSGI mode)."""
    
    def setUp(self):
        """Reset module state before each test."""
        import speed_test
        speed_test._config = None
        speed_test._thread_started = False
        speed_test.retry_interval = None
        speed_test.normal_interval = None
        speed_test.socket_timeout = None
        speed_test.download_speed = None
        speed_test.upload_speed = None
    
    @patch('speed_test.load_config')
    @patch('speed_test.threading.Thread')
    def test_ensure_config_loaded_with_config_file(self, mock_thread, mock_load_config):
        """Test that _ensure_config_loaded loads config from file."""
        import speed_test
        
        mock_load_config.return_value = {
            "speedtest": {
                "retry_interval": 120,
                "normal_interval": 7200,
                "socket_timeout": 60,
            }
        }
        
        speed_test._ensure_config_loaded()
        
        mock_load_config.assert_called_once()
        self.assertEqual(speed_test.retry_interval, 120)
        self.assertEqual(speed_test.normal_interval, 7200)
        self.assertEqual(speed_test.socket_timeout, 60)
    
    @patch('speed_test.load_config')
    @patch('speed_test.threading.Thread')
    def test_ensure_config_loaded_uses_defaults_on_missing_file(self, mock_thread, mock_load_config):
        """Test that defaults are used when config file is missing."""
        import speed_test
        
        mock_load_config.side_effect = FileNotFoundError("Config not found")
        
        speed_test._ensure_config_loaded()
        
        # Should use defaults, not crash
        self.assertEqual(speed_test.retry_interval, speed_test._DEFAULT_RETRY_INTERVAL)
        self.assertEqual(speed_test.normal_interval, speed_test._DEFAULT_NORMAL_INTERVAL)
        self.assertEqual(speed_test.socket_timeout, speed_test._DEFAULT_SOCKET_TIMEOUT)
    
    @patch('speed_test.load_config')
    @patch('speed_test.threading.Thread')
    def test_ensure_config_loaded_uses_defaults_for_missing_keys(self, mock_thread, mock_load_config):
        """Test that defaults are used for missing config keys."""
        import speed_test
        
        mock_load_config.return_value = {
            "speedtest": {
                "retry_interval": 90,
                # normal_interval and socket_timeout missing
            }
        }
        
        speed_test._ensure_config_loaded()
        
        self.assertEqual(speed_test.retry_interval, 90)
        self.assertEqual(speed_test.normal_interval, speed_test._DEFAULT_NORMAL_INTERVAL)
        self.assertEqual(speed_test.socket_timeout, speed_test._DEFAULT_SOCKET_TIMEOUT)
    
    @patch('speed_test.load_config')
    @patch('speed_test.threading.Thread')
    def test_ensure_config_loaded_only_runs_once(self, mock_thread, mock_load_config):
        """Test that config is only loaded once."""
        import speed_test
        
        mock_load_config.return_value = {"speedtest": {"retry_interval": 100}}
        
        speed_test._ensure_config_loaded()
        speed_test._ensure_config_loaded()
        speed_test._ensure_config_loaded()
        
        # Should only be called once
        mock_load_config.assert_called_once()
    
    @patch('speed_test.load_config')
    @patch('speed_test.threading.Thread')
    def test_start_speedtest_thread_loads_config_first(self, mock_thread, mock_load_config):
        """Test that start_speedtest_thread ensures config is loaded."""
        import speed_test
        
        mock_load_config.return_value = {
            "speedtest": {
                "retry_interval": 60,
                "normal_interval": 3600,
                "socket_timeout": 30,
            }
        }
        mock_thread_instance = Mock()
        mock_thread.return_value = mock_thread_instance
        
        # Simulate WSGI mode - config not loaded yet
        self.assertIsNone(speed_test.retry_interval)
        
        speed_test.start_speedtest_thread()
        
        # Config should now be loaded
        self.assertEqual(speed_test.retry_interval, 60)
        # Thread should be started
        mock_thread_instance.start.assert_called_once()
    
    @patch('speed_test.load_config')
    @patch('speed_test.threading.Thread')
    def test_get_sleep_interval_never_returns_none(self, mock_thread, mock_load_config):
        """Test that get_sleep_interval never returns None after config loaded."""
        import speed_test
        
        mock_load_config.return_value = {"speedtest": {}}
        
        speed_test._ensure_config_loaded()
        
        with speed_test.metrics_lock:
            interval = speed_test.get_sleep_interval()
        
        self.assertIsNotNone(interval)
        self.assertIsInstance(interval, (int, float))
        self.assertGreater(interval, 0)


class TestWsgiModeMetricsEndpoint(unittest.TestCase):
    """Test /metrics endpoint in WSGI mode."""
    
    def setUp(self):
        """Reset module state."""
        import speed_test
        speed_test._config = None
        speed_test._thread_started = False
        speed_test.retry_interval = None
        speed_test.normal_interval = None
        speed_test.socket_timeout = None
        speed_test.download_speed = None
        speed_test.upload_speed = None
    
    @patch('speed_test.load_config')
    @patch('speed_test.threading.Thread')
    def test_metrics_endpoint_works_without_main(self, mock_thread, mock_load_config):
        """Test that /metrics works when main() was never called."""
        import speed_test
        
        mock_load_config.return_value = {
            "speedtest": {
                "retry_interval": 60,
                "normal_interval": 3600,
                "socket_timeout": 30,
            },
            "prometheus": {"metrics_enabled": True}
        }
        mock_thread.return_value = Mock()
        
        client = speed_test.app.test_client()
        
        response = client.get('/metrics')
        
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'internet_speed_download_mbps', response.data)
    
    @patch('speed_test.load_config')
    @patch('speed_test.threading.Thread')
    def test_metrics_endpoint_handles_missing_config(self, mock_thread, mock_load_config):
        """Test that /metrics uses defaults when config.yaml is missing."""
        import speed_test
        
        # Simulate missing config file
        mock_load_config.side_effect = FileNotFoundError("Config not found")
        mock_thread.return_value = Mock()
        
        client = speed_test.app.test_client()
        
        # Should NOT raise 500 error
        response = client.get('/metrics')
        
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'internet_speed_download_mbps', response.data)
        # Config should be empty dict (defaults used)
        self.assertEqual(speed_test._config, {})
    
    @patch('speed_test.load_config')
    @patch('speed_test.threading.Thread')
    def test_metrics_endpoint_wheel_install_scenario(self, mock_thread, mock_load_config):
        """Test /metrics works in wheel install scenario (no config.yaml bundled)."""
        import speed_test
        
        # First call raises (no config), simulating wheel install
        mock_load_config.side_effect = FileNotFoundError("No config.yaml in wheel")
        mock_thread.return_value = Mock()
        
        client = speed_test.app.test_client()
        
        # Multiple requests should all work with defaults
        for _ in range(3):
            response = client.get('/metrics')
            self.assertEqual(response.status_code, 200)
        
        # Defaults should be applied
        self.assertEqual(speed_test.retry_interval, speed_test._DEFAULT_RETRY_INTERVAL)
        self.assertEqual(speed_test.normal_interval, speed_test._DEFAULT_NORMAL_INTERVAL)


if __name__ == '__main__':
    unittest.main()
