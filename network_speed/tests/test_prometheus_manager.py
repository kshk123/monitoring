"""Tests for PrometheusManager startup/shutdown behavior."""

import unittest
from unittest.mock import Mock, patch, MagicMock
import subprocess
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from prometheus_manager import PrometheusManager


class TestPrometheusManagerInit(unittest.TestCase):
    """Test PrometheusManager initialization."""
    
    def test_default_config(self):
        """Test initialization with minimal config uses defaults."""
        config = {}
        manager = PrometheusManager(config)
        
        self.assertEqual(manager.binary, "prometheus")
        self.assertIn("prometheus.yml", str(manager.config_file))
        self.assertIn("data", str(manager.data_dir))
    
    def test_custom_config(self):
        """Test initialization with custom config values."""
        config = {
            "binary_path": "/custom/prometheus",
            "config_file": "custom/config.yml",
            "data_dir": "custom/data",
        }
        manager = PrometheusManager(config)
        
        self.assertEqual(manager.binary, "/custom/prometheus")
        self.assertIn("custom/config.yml", str(manager.config_file))
        self.assertIn("custom/data", str(manager.data_dir))


class TestPrometheusManagerStartup(unittest.TestCase):
    """Test PrometheusManager startup behavior."""
    
    @patch('prometheus_manager.subprocess.run')
    @patch('prometheus_manager.subprocess.Popen')
    def test_start_already_running(self, mock_popen, mock_run):
        """Test that start skips when Prometheus is already running."""
        mock_run.return_value = Mock(returncode=0)  # pgrep finds process
        
        config = {"config_file": "prometheus.yml"}
        manager = PrometheusManager(config)
        manager.config_file = Mock()
        manager.config_file.exists.return_value = True
        
        manager.start()
        
        mock_popen.assert_not_called()
    
    @patch('prometheus_manager.subprocess.run')
    @patch('prometheus_manager.subprocess.Popen')
    def test_start_config_not_found(self, mock_popen, mock_run):
        """Test that start fails gracefully when config file doesn't exist."""
        mock_run.return_value = Mock(returncode=1)  # pgrep finds nothing
        
        config = {}
        manager = PrometheusManager(config)
        manager.config_file = Path("/nonexistent/config.yml")
        
        manager.start()
        
        mock_popen.assert_not_called()
    
    @patch('prometheus_manager.subprocess.run')
    @patch('prometheus_manager.subprocess.Popen')
    @patch('prometheus_manager.Path.mkdir')
    def test_start_success(self, mock_mkdir, mock_popen, mock_run):
        """Test successful Prometheus startup."""
        mock_run.return_value = Mock(returncode=1)  # pgrep finds nothing
        mock_process = Mock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process
        
        config = {}
        manager = PrometheusManager(config)
        manager.config_file = Mock()
        manager.config_file.exists.return_value = True
        manager.data_dir = Mock()
        
        manager.start()
        
        mock_popen.assert_called_once()
        # Verify DEVNULL is used (not PIPE) to prevent buffer blocking
        call_kwargs = mock_popen.call_args.kwargs
        self.assertEqual(call_kwargs.get('stdout'), subprocess.DEVNULL)
        self.assertEqual(call_kwargs.get('stderr'), subprocess.DEVNULL)
    
    @patch('prometheus_manager.subprocess.run')
    @patch('prometheus_manager.subprocess.Popen')
    def test_start_popen_failure(self, mock_popen, mock_run):
        """Test that start handles Popen failure gracefully."""
        mock_run.return_value = Mock(returncode=1)
        mock_popen.side_effect = FileNotFoundError("prometheus not found")
        
        config = {}
        manager = PrometheusManager(config)
        manager.config_file = Mock()
        manager.config_file.exists.return_value = True
        manager.data_dir = Mock()
        
        # Should not raise
        manager.start()
        
        self.assertIsNone(manager._process)


class TestPrometheusManagerShutdown(unittest.TestCase):
    """Test PrometheusManager shutdown behavior."""
    
    def test_stop_when_not_started(self):
        """Test that stop does nothing when process wasn't started."""
        config = {}
        manager = PrometheusManager(config)
        
        # Should not raise
        manager.stop()
        
        self.assertIsNone(manager._process)
    
    def test_stop_success(self):
        """Test successful Prometheus shutdown."""
        config = {}
        manager = PrometheusManager(config)
        
        mock_process = Mock()
        manager._process = mock_process
        
        manager.stop()
        
        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called_once_with(timeout=5)
        self.assertIsNone(manager._process)
    
    def test_stop_terminate_timeout_kills(self):
        """Test that stop kills process if terminate times out."""
        config = {}
        manager = PrometheusManager(config)
        
        mock_process = Mock()
        mock_process.wait.side_effect = subprocess.TimeoutExpired("prometheus", 5)
        manager._process = mock_process
        
        manager.stop()
        
        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()
        self.assertIsNone(manager._process)


class TestPrometheusManagerPipeHandling(unittest.TestCase):
    """Test that Prometheus pipe handling doesn't cause blocking."""
    
    @patch('prometheus_manager.subprocess.run')
    @patch('prometheus_manager.subprocess.Popen')
    @patch('prometheus_manager.Path.mkdir')
    def test_uses_devnull_not_pipe(self, mock_mkdir, mock_popen, mock_run):
        """Verify DEVNULL is used instead of PIPE to prevent buffer blocking."""
        mock_run.return_value = Mock(returncode=1)
        mock_popen.return_value = Mock(pid=123)
        
        config = {}
        manager = PrometheusManager(config)
        manager.config_file = Mock()
        manager.config_file.exists.return_value = True
        manager.data_dir = Mock()
        
        manager.start()
        
        # This is the critical fix - using DEVNULL prevents blocking
        call_kwargs = mock_popen.call_args.kwargs
        self.assertNotEqual(call_kwargs.get('stdout'), subprocess.PIPE,
                           "stdout=PIPE can cause blocking; use DEVNULL")
        self.assertNotEqual(call_kwargs.get('stderr'), subprocess.PIPE,
                           "stderr=PIPE can cause blocking; use DEVNULL")


if __name__ == '__main__':
    unittest.main()
