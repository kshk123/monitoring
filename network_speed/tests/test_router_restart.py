"""Tests for RouterRestartManager including config resolution, state handling, and time windows."""

import unittest
from unittest.mock import Mock, patch, MagicMock, mock_open
import json
import tempfile
from pathlib import Path
from datetime import datetime, time
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))


def make_test_config(overrides=None):
    """Create a valid test configuration."""
    config = {
        "router_restart": {
            "fritzbox": {
                "ip": "192.168.1.1",
                "username": "admin",
                "onepassword_ref": "op://Test/Router/password",
            },
            "policy": {
                "speed_threshold_mbps": 50,
                "consecutive_failures": 3,
                "time_window_start": "02:00",
                "time_window_end": "04:00",
            },
            "state": {
                "state_file": "/tmp/test_router_state.json",
            },
            "logging": {
                "enabled": False,  # Disable for tests
                "log_file": "/tmp/test_router.log",
            },
        }
    }
    if overrides:
        # Deep merge overrides
        for key, value in overrides.items():
            if key in config["router_restart"] and isinstance(value, dict):
                config["router_restart"][key].update(value)
            else:
                config["router_restart"][key] = value
    return config


class TestRouterRestartLoggingConfig(unittest.TestCase):
    """Test logging configuration resolution."""
    
    @patch('router_restart.logging')
    @patch('router_restart.Path')
    def test_logging_reads_from_router_restart_section(self, mock_path_cls, mock_logging):
        """Verify logging config is read from router_restart.logging, not top-level."""
        mock_path_instance = Mock()
        mock_path_instance.exists.return_value = False
        mock_path_instance.parent.mkdir = Mock()
        mock_path_cls.return_value = mock_path_instance
        mock_path_cls.home.return_value = Path("/home/user")
        
        from router_restart import RouterRestartManager
        
        config = make_test_config({
            "logging": {
                "enabled": True,
                "log_file": "/custom/path/router.log",
            }
        })
        
        manager = RouterRestartManager(config)
        
        self.assertEqual(manager.log_file, "/custom/path/router.log")
        self.assertTrue(manager.logging_enabled)
    
    @patch('router_restart.logging')
    @patch('router_restart.Path')
    def test_logging_uses_user_writable_default(self, mock_path_cls, mock_logging):
        """Verify default log path is user-writable, not /var/log."""
        mock_path_instance = Mock()
        mock_path_instance.exists.return_value = False
        mock_path_instance.parent.mkdir = Mock()
        mock_path_cls.return_value = mock_path_instance
        mock_path_cls.home.return_value = Path("/home/testuser")
        
        from router_restart import RouterRestartManager
        
        # Config without logging section
        config = {
            "router_restart": {
                "fritzbox": {
                    "ip": "192.168.1.1",
                    "username": "",
                    "onepassword_ref": "op://Test/Router/password",
                },
                "policy": {
                    "speed_threshold_mbps": 50,
                    "consecutive_failures": 3,
                    "time_window_start": "02:00",
                    "time_window_end": "04:00",
                },
                "state": {
                    "state_file": "/tmp/test_state.json",
                },
                # No logging section - should use defaults
            },
        }
        
        manager = RouterRestartManager(config)
        
        # Should NOT be /var/log (which requires root)
        self.assertNotIn("/var/log", manager.log_file)
        # Should be in user's home directory
        self.assertIn(".local", manager.log_file)


class TestRouterRestartStateHandling(unittest.TestCase):
    """Test state JSON loading with corruption handling."""
    
    @patch('router_restart.logging')
    def test_load_state_file_not_exists(self, mock_logging):
        """Test default state when file doesn't exist."""
        from router_restart import RouterRestartManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_test_config({
                "state": {"state_file": f"{tmpdir}/nonexistent.json"}
            })
            
            manager = RouterRestartManager(config)
            
            self.assertEqual(manager.state["consecutive_failures"], 0)
            self.assertIsNone(manager.state["last_restart_time"])
    
    @patch('router_restart.logging')
    def test_load_state_valid_json(self, mock_logging):
        """Test loading valid state JSON."""
        from router_restart import RouterRestartManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            state_file.write_text(json.dumps({
                "consecutive_failures": 5,
                "last_restart_time": "2025-01-01T00:00:00"
            }))
            
            config = make_test_config({
                "state": {"state_file": str(state_file)}
            })
            
            manager = RouterRestartManager(config)
            
            self.assertEqual(manager.state["consecutive_failures"], 5)
            self.assertEqual(manager.state["last_restart_time"], "2025-01-01T00:00:00")
    
    @patch('router_restart.logging')
    def test_load_state_corrupt_json(self, mock_logging):
        """Test fallback when state JSON is corrupt."""
        from router_restart import RouterRestartManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            state_file.write_text("{ invalid json !!!")
            
            config = make_test_config({
                "state": {"state_file": str(state_file)}
            })
            
            manager = RouterRestartManager(config)
            
            # Should fall back to defaults, not crash
            self.assertEqual(manager.state["consecutive_failures"], 0)
            self.assertIsNone(manager.state["last_restart_time"])
    
    @patch('router_restart.logging')
    def test_load_state_partial_json(self, mock_logging):
        """Test handling of partial/incomplete state JSON."""
        from router_restart import RouterRestartManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            # Missing last_restart_time
            state_file.write_text(json.dumps({
                "consecutive_failures": 2
            }))
            
            config = make_test_config({
                "state": {"state_file": str(state_file)}
            })
            
            manager = RouterRestartManager(config)
            
            # Should preserve valid data and fill in missing
            self.assertEqual(manager.state["consecutive_failures"], 2)
            self.assertIsNone(manager.state["last_restart_time"])
    
    @patch('router_restart.logging')
    def test_load_state_wrong_type(self, mock_logging):
        """Test handling when state JSON is not a dict."""
        from router_restart import RouterRestartManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            state_file.write_text(json.dumps([1, 2, 3]))  # Array instead of object
            
            config = make_test_config({
                "state": {"state_file": str(state_file)}
            })
            
            manager = RouterRestartManager(config)
            
            # Should fall back to defaults
            self.assertEqual(manager.state["consecutive_failures"], 0)
            self.assertIsNone(manager.state["last_restart_time"])


class TestRouterRestartTimeWindow(unittest.TestCase):
    """Test time window restart logic."""
    
    @patch('router_restart.logging')
    def test_within_normal_time_window(self, mock_logging):
        """Test detection when within a normal time window (e.g., 02:00-04:00)."""
        from router_restart import RouterRestartManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_test_config({
                "state": {"state_file": f"{tmpdir}/state.json"},
                "policy": {
                    "time_window_start": "02:00",
                    "time_window_end": "04:00",
                }
            })
            
            manager = RouterRestartManager(config)
            
            # Mock datetime.now() to return 03:00
            with patch('router_restart.datetime') as mock_dt:
                mock_dt.now.return_value.time.return_value = time(3, 0)
                mock_dt.strptime = datetime.strptime
                
                # Need to reinitialize to get proper time parsing
                manager.time_window_start = time(2, 0)
                manager.time_window_end = time(4, 0)
                
                self.assertTrue(manager._is_within_time_window())
    
    @patch('router_restart.logging')
    def test_outside_normal_time_window(self, mock_logging):
        """Test detection when outside a normal time window."""
        from router_restart import RouterRestartManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_test_config({
                "state": {"state_file": f"{tmpdir}/state.json"},
            })
            
            manager = RouterRestartManager(config)
            manager.time_window_start = time(2, 0)
            manager.time_window_end = time(4, 0)
            
            with patch('router_restart.datetime') as mock_dt:
                mock_dt.now.return_value.time.return_value = time(12, 0)  # Noon
                
                self.assertFalse(manager._is_within_time_window())
    
    @patch('router_restart.logging')
    def test_midnight_crossing_time_window(self, mock_logging):
        """Test time window that crosses midnight (e.g., 23:00-02:00)."""
        from router_restart import RouterRestartManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_test_config({
                "state": {"state_file": f"{tmpdir}/state.json"},
            })
            
            manager = RouterRestartManager(config)
            manager.time_window_start = time(23, 0)
            manager.time_window_end = time(2, 0)
            
            with patch('router_restart.datetime') as mock_dt:
                # Test at 23:30 - should be within
                mock_dt.now.return_value.time.return_value = time(23, 30)
                self.assertTrue(manager._is_within_time_window())
                
                # Test at 01:00 - should be within
                mock_dt.now.return_value.time.return_value = time(1, 0)
                self.assertTrue(manager._is_within_time_window())
                
                # Test at 12:00 - should be outside
                mock_dt.now.return_value.time.return_value = time(12, 0)
                self.assertFalse(manager._is_within_time_window())


class TestRouterRestartConsecutiveFailures(unittest.TestCase):
    """Test consecutive failure counting logic."""
    
    @patch('router_restart.logging')
    def test_failure_increments_counter(self, mock_logging):
        """Test that low speed increments failure counter."""
        from router_restart import RouterRestartManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_test_config({
                "state": {"state_file": f"{tmpdir}/state.json"},
                "policy": {"speed_threshold_mbps": 50, "consecutive_failures": 3}
            })
            
            manager = RouterRestartManager(config)
            manager.state["consecutive_failures"] = 0
            
            # Mock to prevent actual restart
            with patch.object(manager, '_is_within_time_window', return_value=False):
                manager.check_and_restart(30)  # Below threshold
            
            self.assertEqual(manager.state["consecutive_failures"], 1)
    
    @patch('router_restart.logging')
    def test_good_speed_resets_counter(self, mock_logging):
        """Test that good speed resets failure counter."""
        from router_restart import RouterRestartManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_test_config({
                "state": {"state_file": f"{tmpdir}/state.json"},
                "policy": {"speed_threshold_mbps": 50}
            })
            
            manager = RouterRestartManager(config)
            manager.state["consecutive_failures"] = 5
            
            manager.check_and_restart(100)  # Above threshold
            
            self.assertEqual(manager.state["consecutive_failures"], 0)


class TestRouterRestartLoggingHandlers(unittest.TestCase):
    """Test that logging handlers are added correctly."""
    
    def test_no_duplicate_file_handlers(self):
        """Test that repeated instantiation doesn't duplicate file handlers."""
        import logging
        from router_restart import RouterRestartManager
        
        root_logger = logging.getLogger()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = f"{tmpdir}/router.log"
            config = make_test_config({
                "state": {"state_file": f"{tmpdir}/state.json"},
                "logging": {
                    "enabled": True,
                    "log_file": log_file,
                }
            })
            
            # Count file handlers before
            initial_file_handlers = [
                h for h in root_logger.handlers
                if isinstance(h, logging.FileHandler)
            ]
            initial_count = len(initial_file_handlers)
            
            # Create manager multiple times
            manager1 = RouterRestartManager(config)
            manager2 = RouterRestartManager(config)
            manager3 = RouterRestartManager(config)
            
            # Count file handlers after
            final_file_handlers = [
                h for h in root_logger.handlers
                if isinstance(h, logging.FileHandler)
            ]
            
            # Should only have added ONE handler, not three
            self.assertEqual(len(final_file_handlers), initial_count + 1)
            
            # Cleanup - remove the handler we added
            for h in final_file_handlers:
                if h not in initial_file_handlers:
                    root_logger.removeHandler(h)
                    h.close()
    
    @patch('router_restart.logging')
    def test_tilde_expansion_in_log_path(self, mock_logging):
        """Test that ~ is expanded in log file path."""
        from router_restart import RouterRestartManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_test_config({
                "state": {"state_file": f"{tmpdir}/state.json"},
                "logging": {
                    "enabled": True,
                    "log_file": "~/.local/log/test.log",
                }
            })
            
            manager = RouterRestartManager(config)
            
            # Should have expanded ~
            self.assertNotIn("~", manager.log_file)
            self.assertIn(str(Path.home()), manager.log_file)
    
    @patch('router_restart.logging')
    def test_tilde_expansion_in_state_file(self, mock_logging):
        """Test that ~ is expanded in state file path."""
        from router_restart import RouterRestartManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_test_config({
                "state": {"state_file": "~/router_state.json"},
                "logging": {"enabled": False}
            })
            
            manager = RouterRestartManager(config)
            
            # Should have expanded ~
            self.assertNotIn("~", str(manager.state_file))
            self.assertIn(str(Path.home()), str(manager.state_file))


class TestRouterRestartMetrics(unittest.TestCase):
    """Test router restart metrics tracking."""
    
    def setUp(self):
        """Reset metrics and clear instances before each test."""
        import router_restart
        # Clear active instances
        with router_restart._instances_lock:
            router_restart._active_instances.clear()
    
    def test_get_router_restart_metrics_returns_none_when_no_instances(self):
        """Test that get_router_restart_metrics returns None when no manager exists."""
        from router_restart import get_router_restart_metrics
        
        metrics = get_router_restart_metrics()
        self.assertIsNone(metrics)
    
    @patch('router_restart.logging')
    def test_get_router_restart_metrics_returns_dict_with_instance(self, mock_logging):
        """Test that get_router_restart_metrics returns expected structure with active manager."""
        from router_restart import RouterRestartManager, get_router_restart_metrics
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_test_config({
                "state": {"state_file": f"{tmpdir}/state.json"},
                "logging": {"enabled": False}
            })
            
            manager = RouterRestartManager(config)
            
            metrics = get_router_restart_metrics()
            
            self.assertIsInstance(metrics, dict)
            self.assertIn("restart_total", metrics)
            self.assertIn("restart_last_timestamp", metrics)
            self.assertIn("restart_failures_total", metrics)
            self.assertIn("router_id", metrics)
            self.assertEqual(metrics["router_id"], "192.168.1.1")
    
    @patch('router_restart.FritzConnection')
    @patch('router_restart.logging')
    def test_successful_restart_increments_counter(self, mock_logging, mock_fc_class):
        """Test that successful restart increments the counter."""
        from router_restart import RouterRestartManager, get_router_restart_metrics
        
        # Mock FritzConnection
        mock_fc = Mock()
        mock_fc_class.return_value = mock_fc
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_test_config({
                "state": {"state_file": f"{tmpdir}/state.json"},
                "logging": {"enabled": False}
            })
            
            manager = RouterRestartManager(config)
            
            # Verify initial state
            initial_metrics = get_router_restart_metrics()
            self.assertEqual(initial_metrics["restart_total"], 0)
            
            # Mock password retrieval
            with patch.object(manager, '_get_fritzbox_password', return_value='password'):
                result = manager._restart_fritzbox()
            
            self.assertTrue(result)
            
            # Check metrics incremented
            new_metrics = get_router_restart_metrics()
            self.assertEqual(new_metrics["restart_total"], 1)
            self.assertIsNotNone(new_metrics["restart_last_timestamp"])
    
    @patch('router_restart.FritzConnection')
    @patch('router_restart.logging')
    def test_failed_restart_increments_failure_counter(self, mock_logging, mock_fc_class):
        """Test that failed restart increments the failure counter."""
        from router_restart import RouterRestartManager, get_router_restart_metrics
        
        # Mock FritzConnection to raise exception
        mock_fc_class.side_effect = Exception("Connection failed")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_test_config({
                "state": {"state_file": f"{tmpdir}/state.json"},
                "logging": {"enabled": False}
            })
            
            manager = RouterRestartManager(config)
            
            # Verify initial state
            initial_metrics = get_router_restart_metrics()
            self.assertEqual(initial_metrics["restart_failures_total"], 0)
            
            # Mock password retrieval
            with patch.object(manager, '_get_fritzbox_password', return_value='password'):
                result = manager._restart_fritzbox()
            
            self.assertFalse(result)
            
            # Check failure counter incremented
            new_metrics = get_router_restart_metrics()
            self.assertEqual(new_metrics["restart_failures_total"], 1)
    
    @patch('router_restart.logging')
    def test_multiple_instances_aggregate_metrics(self, mock_logging):
        """Test that multiple instances have their metrics aggregated."""
        from router_restart import RouterRestartManager, get_router_restart_metrics
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config1 = make_test_config({
                "state": {"state_file": f"{tmpdir}/state1.json"},
                "logging": {"enabled": False}
            })
            config1["router_restart"]["fritzbox"]["ip"] = "192.168.1.1"
            
            config2 = make_test_config({
                "state": {"state_file": f"{tmpdir}/state2.json"},
                "logging": {"enabled": False}
            })
            config2["router_restart"]["fritzbox"]["ip"] = "192.168.1.2"
            
            manager1 = RouterRestartManager(config1)
            manager2 = RouterRestartManager(config2)
            
            # Set different metrics on each
            manager1._restart_total = 3
            manager2._restart_total = 2
            
            # Aggregated total should be 5
            metrics = get_router_restart_metrics()
            self.assertEqual(metrics["restart_total"], 5)
            # Router ID should be None for multiple routers
            self.assertIsNone(metrics["router_id"])
    
    @patch('router_restart.logging')
    def test_close_unregisters_instance(self, mock_logging):
        """Test that close() properly unregisters the instance."""
        import router_restart
        from router_restart import RouterRestartManager, get_router_restart_metrics
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_test_config({
                "state": {"state_file": f"{tmpdir}/state.json"},
                "logging": {"enabled": False}
            })
            
            manager = RouterRestartManager(config)
            
            # Verify it's registered
            self.assertIsNotNone(get_router_restart_metrics())
            with router_restart._instances_lock:
                self.assertIn(manager, router_restart._active_instances)
            
            # Close and verify it's unregistered
            manager.close()
            
            with router_restart._instances_lock:
                self.assertNotIn(manager, router_restart._active_instances)
            self.assertIsNone(get_router_restart_metrics())
    
    @patch('router_restart.logging')
    def test_close_is_idempotent(self, mock_logging):
        """Test that close() can be called multiple times safely."""
        from router_restart import RouterRestartManager, get_router_restart_metrics
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_test_config({
                "state": {"state_file": f"{tmpdir}/state.json"},
                "logging": {"enabled": False}
            })
            
            manager = RouterRestartManager(config)
            
            # Close multiple times - should not raise
            manager.close()
            manager.close()
            manager.close()
            
            self.assertIsNone(get_router_restart_metrics())
    
    @patch('router_restart.logging')
    def test_duplicate_registration_prevented(self, mock_logging):
        """Test that the same instance cannot be registered twice."""
        import router_restart
        from router_restart import RouterRestartManager, _register_instance
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_test_config({
                "state": {"state_file": f"{tmpdir}/state.json"},
                "logging": {"enabled": False}
            })
            
            manager = RouterRestartManager(config)
            
            # Try to register again
            _register_instance(manager)
            _register_instance(manager)
            
            # Should only be in the set once
            with router_restart._instances_lock:
                count = len(router_restart._active_instances)
            self.assertEqual(count, 1)
    
    @patch('router_restart.logging')
    def test_del_unregisters_instance(self, mock_logging):
        """Test that __del__ properly unregisters the instance."""
        import router_restart
        from router_restart import RouterRestartManager, get_router_restart_metrics
        import gc
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_test_config({
                "state": {"state_file": f"{tmpdir}/state.json"},
                "logging": {"enabled": False}
            })
            
            manager = RouterRestartManager(config)
            
            # Verify it's registered
            self.assertIsNotNone(get_router_restart_metrics())
            
            # Delete the manager and force garbage collection
            del manager
            gc.collect()
            
            # Should be unregistered
            self.assertIsNone(get_router_restart_metrics())


if __name__ == '__main__':
    unittest.main()
