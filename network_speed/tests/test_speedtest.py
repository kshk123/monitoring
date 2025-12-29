import unittest
from unittest.mock import Mock, patch, MagicMock
import threading
import time
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from speed_test import app, take_speedtest_sample, speedtest_thread, metrics_lock
import speed_test


class TestSpeedTestSample(unittest.TestCase):
    """Test the take_speedtest_sample function"""
    
    def setUp(self):
        """Reset global variables before each test"""
        speed_test.download_speed = None
        speed_test.upload_speed = None
    
    @patch('speed_test.speedtest.Speedtest')
    def test_successful_speedtest(self, mock_speedtest_class):
        """Test that speedtest successfully updates global variables"""
        mock_st = Mock()
        mock_st.download.return_value = 100 * 1024 * 1024
        mock_st.upload.return_value = 50 * 1024 * 1024
        mock_speedtest_class.return_value = mock_st
        
        take_speedtest_sample()
        
        mock_st.get_best_server.assert_called_once()
        mock_st.download.assert_called_once()
        mock_st.upload.assert_called_once()
        self.assertAlmostEqual(speed_test.download_speed, 100.0, places=1)
        self.assertAlmostEqual(speed_test.upload_speed, 50.0, places=1)
    
    @patch('speed_test.speedtest.Speedtest')
    def test_speedtest_with_lock(self, mock_speedtest_class):
        """Test that speedtest updates are thread-safe"""
        mock_st = Mock()
        mock_st.download.return_value = 100 * 1024 * 1024
        mock_st.upload.return_value = 50 * 1024 * 1024
        mock_speedtest_class.return_value = mock_st
        
        with metrics_lock:
            initial_download = speed_test.download_speed
        
        take_speedtest_sample()
        
        with metrics_lock:
            final_download = speed_test.download_speed
        
        self.assertIsNone(initial_download)
        self.assertIsNotNone(final_download)


class TestMetricsEndpoint(unittest.TestCase):
    """Test the Flask /metrics endpoint"""
    
    def setUp(self):
        """Setup Flask test client"""
        self.client = app.test_client()
        self.client.testing = True
        speed_test.download_speed = None
        speed_test.upload_speed = None
        # Avoid starting background thread during unit tests
        self._thread_patcher = patch('speed_test.start_speedtest_thread')
        self._thread_patcher.start()
    
    def tearDown(self):
        """Stop any active patchers."""
        self._thread_patcher.stop()
    
    def test_metrics_no_data(self):
        """Test metrics endpoint when no data is available"""
        response = self.client.get('/metrics')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'text/plain')
        
        data = response.data.decode('utf-8')
        self.assertIn('internet_speed_download_mbps nan', data)
        self.assertIn('internet_speed_upload_mbps nan', data)
    
    def test_metrics_with_data(self):
        """Test metrics endpoint with actual speed data"""
        with metrics_lock:
            speed_test.download_speed = 150.5
            speed_test.upload_speed = 25.3
        
        response = self.client.get('/metrics')
        self.assertEqual(response.status_code, 200)
        
        data = response.data.decode('utf-8')
        self.assertIn('internet_speed_download_mbps 150.5', data)
        self.assertIn('internet_speed_upload_mbps 25.3', data)
    
    def test_metrics_format(self):
        """Test that metrics are in Prometheus format"""
        with metrics_lock:
            speed_test.download_speed = 100.0
            speed_test.upload_speed = 50.0
        
        response = self.client.get('/metrics')
        data = response.data.decode('utf-8')
        
        lines = data.strip().split('\n')
        self.assertEqual(len(lines), 6)
        self.assertIn('# HELP internet_speed_download_mbps', data)
        self.assertIn('# TYPE internet_speed_download_mbps gauge', data)
        self.assertIn('internet_speed_download_mbps 100.0', data)
        self.assertIn('# HELP internet_speed_upload_mbps', data)
        self.assertIn('# TYPE internet_speed_upload_mbps gauge', data)
        self.assertIn('internet_speed_upload_mbps 50.0', data)


class TestSpeedTestThread(unittest.TestCase):
    """Test the background speedtest thread logic"""
    
    def setUp(self):
        """Reset global variables"""
        speed_test.download_speed = None
        speed_test.upload_speed = None
        speed_test.retry_interval = 1  # Short intervals for testing
        speed_test.normal_interval = 2
    
    @patch('speed_test.time.sleep')
    @patch('speed_test.take_speedtest_sample')
    def test_retry_interval_when_no_data(self, mock_sample, mock_sleep):
        """Test that retry interval is used when no data exists"""
        mock_sample.side_effect = [None, KeyboardInterrupt()]
        
        try:
            speedtest_thread()
        except KeyboardInterrupt:
            pass
        
        mock_sleep.assert_called()
        first_call_interval = mock_sleep.call_args_list[0][0][0]
        self.assertEqual(first_call_interval, speed_test.retry_interval)
    
    @patch('speed_test.time.sleep')
    @patch('speed_test.take_speedtest_sample')
    def test_normal_interval_with_data(self, mock_sample, mock_sleep):
        """Test that normal interval is used after data is available"""
        def set_speed():
            speed_test.download_speed = 100.0
            speed_test.upload_speed = 50.0
        
        mock_sample.side_effect = [set_speed(), KeyboardInterrupt()]
        
        try:
            speedtest_thread()
        except KeyboardInterrupt:
            pass
        
        mock_sleep.assert_called()
        if len(mock_sleep.call_args_list) > 0:
            first_call_interval = mock_sleep.call_args_list[0][0][0]
            self.assertEqual(first_call_interval, speed_test.normal_interval)
    
    @patch('speed_test.time.sleep')
    @patch('speed_test.take_speedtest_sample')
    @patch('speed_test.logging')
    def test_config_retrieval_error_handling(self, mock_logging, mock_sample, mock_sleep):
        """Test ConfigRetrievalError is handled properly"""
        import speedtest
        mock_sample.side_effect = [speedtest.ConfigRetrievalError("Test error"), KeyboardInterrupt()]
        
        try:
            speedtest_thread()
        except KeyboardInterrupt:
            pass
        
        mock_logging.warning.assert_called()
        mock_sleep.assert_called()
    
    @patch('speed_test.time.sleep')
    @patch('speed_test.take_speedtest_sample')
    @patch('speed_test.logging')
    def test_generic_exception_handling(self, mock_logging, mock_sample, mock_sleep):
        """Test generic exceptions are handled properly"""
        mock_sample.side_effect = [Exception("Test error"), KeyboardInterrupt()]
        
        try:
            speedtest_thread()
        except KeyboardInterrupt:
            pass
        
        mock_logging.exception.assert_called()
        mock_sleep.assert_called()


class TestThreadSafety(unittest.TestCase):
    """Test thread safety of global variable access"""
    
    def setUp(self):
        """Reset globals"""
        speed_test.download_speed = None
        speed_test.upload_speed = None
    
    def test_concurrent_access(self):
        """Test that concurrent reads/writes don't cause issues"""
        results = []
        
        def writer():
            for i in range(10):
                with metrics_lock:
                    speed_test.download_speed = float(i)
                    speed_test.upload_speed = float(i * 2)
                time.sleep(0.001)
        
        def reader():
            for _ in range(10):
                with metrics_lock:
                    dl = speed_test.download_speed
                    ul = speed_test.upload_speed
                    if dl is not None and ul is not None:
                        results.append((dl, ul))
                time.sleep(0.001)
        
        writer_thread = threading.Thread(target=writer)
        reader_thread = threading.Thread(target=reader)
        
        writer_thread.start()
        reader_thread.start()
        
        writer_thread.join()
        reader_thread.join()
        
        for dl, ul in results:
            self.assertAlmostEqual(ul, dl * 2, places=1)


if __name__ == '__main__':
    unittest.main()
