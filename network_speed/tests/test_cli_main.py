"""Tests for CLI main() function and partial config handling."""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import tempfile
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))


class TestMainPartialConfig(unittest.TestCase):
    """Test that main() handles partial configs with defaults."""
    
    def setUp(self):
        """Reset module state."""
        import speed_test
        speed_test._config = None
        speed_test._thread_started = False
        speed_test.retry_interval = None
        speed_test.normal_interval = None
        speed_test.socket_timeout = None
        speed_test._prometheus_manager = None
        speed_test._router_restart_manager = None
    
    @patch('speed_test.app.run')
    @patch('speed_test.start_speedtest_thread')
    @patch('argparse.ArgumentParser.parse_args')
    def test_main_with_minimal_config(self, mock_args, mock_thread, mock_run):
        """Test main() works with minimal config (all keys missing)."""
        import speed_test
        
        # Create a minimal config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("# Minimal config\n")
            temp_path = f.name
        
        try:
            mock_args.return_value = Mock(config=temp_path)
            
            # Should not raise KeyError
            speed_test.main()
            
            # Should use defaults
            self.assertEqual(speed_test.retry_interval, speed_test._DEFAULT_RETRY_INTERVAL)
            self.assertEqual(speed_test.normal_interval, speed_test._DEFAULT_NORMAL_INTERVAL)
            self.assertEqual(speed_test.socket_timeout, speed_test._DEFAULT_SOCKET_TIMEOUT)
        finally:
            os.unlink(temp_path)
    
    @patch('speed_test.app.run')
    @patch('speed_test.start_speedtest_thread')
    @patch('argparse.ArgumentParser.parse_args')
    def test_main_with_partial_speedtest_config(self, mock_args, mock_thread, mock_run):
        """Test main() works with partial speedtest config."""
        import speed_test
        
        # Create config with only retry_interval
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("speedtest:\n  retry_interval: 120\n")
            temp_path = f.name
        
        try:
            mock_args.return_value = Mock(config=temp_path)
            
            speed_test.main()
            
            # Custom value should be used
            self.assertEqual(speed_test.retry_interval, 120)
            # Defaults for missing keys
            self.assertEqual(speed_test.normal_interval, speed_test._DEFAULT_NORMAL_INTERVAL)
            self.assertEqual(speed_test.socket_timeout, speed_test._DEFAULT_SOCKET_TIMEOUT)
        finally:
            os.unlink(temp_path)
    
    @patch('speed_test.app.run')
    @patch('speed_test.start_speedtest_thread')
    @patch('argparse.ArgumentParser.parse_args')
    def test_main_with_empty_config_file(self, mock_args, mock_thread, mock_run):
        """Test main() works with empty config file."""
        import speed_test
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("")  # Empty file
            temp_path = f.name
        
        try:
            mock_args.return_value = Mock(config=temp_path)
            
            # Should not raise AttributeError (config is None)
            speed_test.main()
            
            # Should use all defaults
            self.assertEqual(speed_test.retry_interval, speed_test._DEFAULT_RETRY_INTERVAL)
        finally:
            os.unlink(temp_path)
    
    @patch('speed_test.app.run')
    @patch('speed_test.start_speedtest_thread')
    @patch('argparse.ArgumentParser.parse_args')
    def test_main_default_port(self, mock_args, mock_thread, mock_run):
        """Test main() uses default port when not specified."""
        import speed_test
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("speedtest:\n  retry_interval: 60\n")  # No metrics_port
            temp_path = f.name
        
        try:
            mock_args.return_value = Mock(config=temp_path)
            
            speed_test.main()
            
            # Should use default port 5000
            mock_run.assert_called_once()
            call_kwargs = mock_run.call_args.kwargs
            self.assertEqual(call_kwargs.get('port'), 5000)
        finally:
            os.unlink(temp_path)


class TestMainConsistencyWithWsgi(unittest.TestCase):
    """Test that main() and WSGI mode behave consistently."""
    
    def setUp(self):
        """Reset module state."""
        import speed_test
        speed_test._config = None
        speed_test._thread_started = False
        speed_test.retry_interval = None
        speed_test.normal_interval = None
        speed_test.socket_timeout = None
    
    @patch('speed_test.load_config')
    @patch('speed_test.threading.Thread')
    def test_wsgi_partial_config_matches_main(self, mock_thread, mock_load_config):
        """Test WSGI mode with partial config produces same result as main()."""
        import speed_test
        
        partial_config = {
            "speedtest": {
                "retry_interval": 90
                # Other keys missing
            }
        }
        mock_load_config.return_value = partial_config
        mock_thread.return_value = Mock()
        
        # WSGI mode - load via _ensure_config_loaded
        speed_test._ensure_config_loaded()
        
        wsgi_retry = speed_test.retry_interval
        wsgi_normal = speed_test.normal_interval
        wsgi_timeout = speed_test.socket_timeout
        
        # Both should use same defaults
        self.assertEqual(wsgi_retry, 90)
        self.assertEqual(wsgi_normal, speed_test._DEFAULT_NORMAL_INTERVAL)
        self.assertEqual(wsgi_timeout, speed_test._DEFAULT_SOCKET_TIMEOUT)


if __name__ == '__main__':
    unittest.main()
