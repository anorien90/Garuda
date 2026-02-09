"""Tests for Ollama Exoscale proxy component.

Tests validate:
- Flask app correctly exposes Ollama-compatible endpoints
- Adapter initialization with environment variables
- Proxy behavior (mocked)
- Health check endpoints
- Streaming response handling
- Activity recording on requests

Note: This modifies sys.path to import from ollama-exoscale directory.
For production testing, install the component as a package first.
"""

import json
import os
import sys
import time
import unittest
from unittest.mock import Mock, MagicMock, patch

# Add ollama-exoscale directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ollama-exoscale"))


class TestExoscaleAdapter(unittest.TestCase):
    """Test cases for ExoscaleOllamaAdapter."""
    
    @patch.dict(os.environ, {
        'EXOSCALE_API_KEY': 'test_key',
        'EXOSCALE_API_SECRET': 'test_secret',
        'EXOSCALE_ZONE': 'at-vie-2',
        'EXOSCALE_INSTANCE_TYPE': 'a5000.small',
        'OLLAMA_MODEL': 'llama2',
        'EXOSCALE_IDLE_TIMEOUT': '600'
    })
    @patch('exoscale_adapter.Client')
    def test_adapter_initialization(self, mock_client_cls):
        """Test adapter initialization with environment variables."""
        from exoscale_adapter import ExoscaleOllamaAdapter
        
        adapter = ExoscaleOllamaAdapter()
        
        # Verify environment variables were read
        self.assertEqual(adapter.api_key, 'test_key')
        self.assertEqual(adapter.api_secret, 'test_secret')
        self.assertEqual(adapter.zone_name, 'at-vie-2')
        self.assertEqual(adapter.instance_type, 'a5000.small')
        self.assertEqual(adapter.ollama_model, 'llama2')
        self.assertEqual(adapter.idle_timeout, 600)
        
        # Verify client was initialized with correct params
        mock_client_cls.assert_called_once_with(
            key='test_key', secret='test_secret', zone='at-vie-2'
        )
    
    @patch('exoscale_adapter.Client')
    def test_adapter_missing_credentials(self, mock_client_cls):
        """Test adapter raises error when credentials are missing."""
        from exoscale_adapter import ExoscaleOllamaAdapter, ExoscaleAuthError
        
        with self.assertRaises(ExoscaleAuthError):
            ExoscaleOllamaAdapter(api_key='', api_secret='')
    
    @patch.dict(os.environ, {
        'EXOSCALE_API_KEY': 'test_key',
        'EXOSCALE_API_SECRET': 'test_secret'
    })
    @patch('exoscale_adapter.Client')
    def test_get_remote_url(self, mock_client_cls):
        """Test getting remote URL."""
        from exoscale_adapter import ExoscaleOllamaAdapter
        
        adapter = ExoscaleOllamaAdapter()
        
        # No instance IP yet
        self.assertIsNone(adapter.get_remote_url())
        
        # Set instance IP
        adapter.instance_ip = '1.2.3.4'
        url = adapter.get_remote_url()
        self.assertEqual(url, 'http://1.2.3.4:11434')
    
    @patch.dict(os.environ, {
        'EXOSCALE_API_KEY': 'test_key',
        'EXOSCALE_API_SECRET': 'test_secret'
    })
    @patch('exoscale_adapter.Client')
    def test_record_activity(self, mock_client_cls):
        """Test activity recording."""
        from exoscale_adapter import ExoscaleOllamaAdapter
        
        adapter = ExoscaleOllamaAdapter()
        
        initial_time = adapter.last_activity
        time.sleep(0.1)
        adapter.record_activity()
        
        self.assertGreater(adapter.last_activity, initial_time)
    
    @patch.dict(os.environ, {
        'EXOSCALE_API_KEY': 'test_key',
        'EXOSCALE_API_SECRET': 'test_secret'
    })
    @patch('exoscale_adapter.Client')
    def test_ensure_security_group_existing(self, mock_client_cls):
        """Test finding existing security group."""
        from exoscale_adapter import ExoscaleOllamaAdapter
        
        adapter = ExoscaleOllamaAdapter()
        
        # Mock list_security_groups returning an existing one
        adapter.client.list_security_groups.return_value = {
            "security-groups": [
                {"name": "garuda-ollama-sg", "id": "sg-123"}
            ]
        }
        
        sg_id = adapter._ensure_security_group()
        
        self.assertEqual(sg_id, "sg-123")
        self.assertEqual(adapter.security_group_id, "sg-123")
    
    @patch.dict(os.environ, {
        'EXOSCALE_API_KEY': 'test_key',
        'EXOSCALE_API_SECRET': 'test_secret'
    })
    @patch('exoscale_adapter.Client')
    def test_find_existing_instance(self, mock_client_cls):
        """Test finding existing instance."""
        from exoscale_adapter import ExoscaleOllamaAdapter
        
        adapter = ExoscaleOllamaAdapter()
        
        # Mock list_instances returning an existing one
        adapter.client.list_instances.return_value = {
            "instances": [
                {"name": "garuda-ollama", "id": "inst-123", "state": "running",
                 "public_ip": "1.2.3.4"}
            ]
        }
        
        instance = adapter._find_existing_instance()
        
        self.assertIsNotNone(instance)
        self.assertEqual(instance["id"], "inst-123")
        self.assertEqual(instance["state"], "running")
    
    @patch.dict(os.environ, {
        'EXOSCALE_API_KEY': 'test_key',
        'EXOSCALE_API_SECRET': 'test_secret'
    })
    @patch('exoscale_adapter.Client')
    def test_find_no_existing_instance(self, mock_client_cls):
        """Test when no existing instance is found."""
        from exoscale_adapter import ExoscaleOllamaAdapter
        
        adapter = ExoscaleOllamaAdapter()
        adapter.client.list_instances.return_value = {"instances": []}
        
        instance = adapter._find_existing_instance()
        self.assertIsNone(instance)
    
    @patch.dict(os.environ, {
        'EXOSCALE_API_KEY': 'test_key',
        'EXOSCALE_API_SECRET': 'test_secret'
    })
    @patch('exoscale_adapter.Client')
    def test_get_instance_status(self, mock_client_cls):
        """Test getting instance status."""
        from exoscale_adapter import ExoscaleOllamaAdapter
        
        adapter = ExoscaleOllamaAdapter()
        
        # No instance ID
        self.assertIsNone(adapter.get_instance_status())
        
        # With instance ID
        adapter.instance_id = "inst-123"
        adapter.client.get_instance.return_value = {
            "id": "inst-123", "state": "running"
        }
        
        status = adapter.get_instance_status()
        self.assertEqual(status, "running")
    
    @patch.dict(os.environ, {
        'EXOSCALE_API_KEY': 'test_key',
        'EXOSCALE_API_SECRET': 'test_secret'
    })
    @patch('exoscale_adapter.Client')
    def test_destroy_instance_no_instance(self, mock_client_cls):
        """Test destroy when no instance exists."""
        from exoscale_adapter import ExoscaleOllamaAdapter
        
        adapter = ExoscaleOllamaAdapter()
        self.assertFalse(adapter.destroy_instance())
    
    @patch.dict(os.environ, {
        'EXOSCALE_API_KEY': 'test_key',
        'EXOSCALE_API_SECRET': 'test_secret'
    })
    @patch('exoscale_adapter.Client')
    def test_shutdown_idempotent(self, mock_client_cls):
        """Test that shutdown is idempotent."""
        from exoscale_adapter import ExoscaleOllamaAdapter
        
        adapter = ExoscaleOllamaAdapter()
        
        # First shutdown
        adapter.shutdown()
        self.assertTrue(adapter._shutdown_called)
        
        # Second shutdown should be a no-op
        adapter.shutdown()
        self.assertTrue(adapter._shutdown_called)
    
    @patch.dict(os.environ, {
        'EXOSCALE_API_KEY': 'test_key',
        'EXOSCALE_API_SECRET': 'test_secret'
    })
    @patch('exoscale_adapter.Client')
    def test_cloud_init_generation(self, mock_client_cls):
        """Test cloud-init script generation."""
        import base64
        from exoscale_adapter import ExoscaleOllamaAdapter
        
        adapter = ExoscaleOllamaAdapter(
            api_key='test_key',
            api_secret='test_secret',
            ollama_model='llama2',
        )
        
        user_data = adapter._generate_cloud_init()
        
        # Should be base64 encoded
        decoded = base64.b64decode(user_data).decode()
        self.assertIn("#!/bin/bash", decoded)
        self.assertIn("ollama pull llama2", decoded)
        self.assertIn("docker run", decoded)
        self.assertIn("11434", decoded)
    
    @patch.dict(os.environ, {
        'EXOSCALE_API_KEY': 'test_key',
        'EXOSCALE_API_SECRET': 'test_secret'
    })
    @patch('exoscale_adapter.Client')
    def test_async_create_instance(self, mock_client_cls):
        """Test async instance creation returns immediately."""
        from exoscale_adapter import ExoscaleOllamaAdapter
        
        adapter = ExoscaleOllamaAdapter()
        
        # Mock methods to simulate slow creation
        adapter.client.list_instances.return_value = {"instances": []}
        adapter._find_template_id = Mock(return_value="template-123")
        adapter._find_instance_type_id = Mock(return_value="type-123")
        adapter._ensure_security_group = Mock(return_value="sg-123")
        
        # Mock instance creation to be slow (simulate real scenario)
        def slow_create(*args, **kwargs):
            import time
            time.sleep(1)  # Simulate slow operation
            return {"id": "op-123", "reference": {"id": "inst-123"}}
        
        adapter.client.create_instance.side_effect = slow_create
        adapter.client.wait = Mock()
        
        # Call create_instance (should start background thread and return immediately)
        result = adapter.create_instance()
        
        # Should return True (provisioning started)
        self.assertTrue(result)
        
        # Status should be provisioning (not blocking)
        status = adapter.get_provisioning_status()
        self.assertIn(status["status"], ["provisioning", "ready"])
        
        # Clean up - wait for thread to finish
        if adapter.provisioning_thread:
            adapter.provisioning_thread.join(timeout=5)
    
    @patch.dict(os.environ, {
        'EXOSCALE_API_KEY': 'test_key',
        'EXOSCALE_API_SECRET': 'test_secret'
    })
    @patch('exoscale_adapter.Client')
    def test_ensure_instance_with_running(self, mock_client_cls):
        """Test ensure_instance with a running instance."""
        from exoscale_adapter import ExoscaleOllamaAdapter
        
        adapter = ExoscaleOllamaAdapter()
        
        # Mock a running instance
        adapter.client.list_instances.return_value = {
            "instances": [
                {"name": "garuda-ollama", "id": "inst-123", "state": "running",
                 "public_ip": "1.2.3.4"}
            ]
        }
        
        url = adapter.ensure_instance()
        
        # Should return URL immediately
        self.assertEqual(url, "http://1.2.3.4:11434")
        self.assertEqual(adapter.get_provisioning_status()["status"], "ready")


class TestOllamaExoscaleApp(unittest.TestCase):
    """Test cases for Flask application."""
    
    def setUp(self):
        """Set up test client."""
        self.env_patcher = patch.dict(os.environ, {
            'EXOSCALE_API_KEY': 'test_key',
            'EXOSCALE_API_SECRET': 'test_secret'
        })
        self.env_patcher.start()
        
        self.exoscale_patcher = patch('exoscale_adapter.Client')
        self.mock_client_cls = self.exoscale_patcher.start()
        
        # Import app after patching
        import importlib
        import app as flask_app
        importlib.reload(flask_app)
        self.flask_app = flask_app
        self.app = flask_app.app
        self.client = self.app.test_client()
    
    def tearDown(self):
        """Clean up patches."""
        self.exoscale_patcher.stop()
        self.env_patcher.stop()
    
    def test_health_check_get(self):
        """Test health check GET endpoint."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.decode(), "Ollama is running")
    
    def test_health_check_head(self):
        """Test health check HEAD endpoint."""
        response = self.client.head('/')
        self.assertEqual(response.status_code, 200)
    
    def test_status_endpoint(self):
        """Test status endpoint."""
        response = self.client.get('/status')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertIn('service', data)
        self.assertEqual(data['service'], 'ollama-exoscale')
        self.assertIn('zone', data)
        self.assertIn('instance_type', data)
    
    @patch('app.proxy_request')
    def test_generate_endpoint(self, mock_proxy):
        """Test generate endpoint."""
        mock_proxy.return_value = ({"response": "test"}, 200)
        
        response = self.client.post('/api/generate',
                                    json={'model': 'llama2', 'prompt': 'test'})
        
        self.assertEqual(response.status_code, 200)
        mock_proxy.assert_called_once()
    
    @patch('app.proxy_request')
    def test_chat_endpoint(self, mock_proxy):
        """Test chat endpoint."""
        mock_proxy.return_value = ({"message": {"content": "test"}}, 200)
        
        response = self.client.post('/api/chat',
                                    json={'model': 'llama2', 'messages': []})
        
        self.assertEqual(response.status_code, 200)
        mock_proxy.assert_called_once()
    
    @patch('app.proxy_request')
    def test_embeddings_endpoint(self, mock_proxy):
        """Test embeddings endpoint."""
        mock_proxy.return_value = ({"embedding": [0.1, 0.2]}, 200)
        
        response = self.client.post('/api/embeddings',
                                    json={'model': 'llama2', 'prompt': 'test'})
        
        self.assertEqual(response.status_code, 200)
        mock_proxy.assert_called_once()
    
    @patch('app.proxy_request')
    def test_list_models_endpoint(self, mock_proxy):
        """Test list models endpoint."""
        mock_proxy.return_value = ({"models": []}, 200)
        
        response = self.client.get('/api/tags')
        
        self.assertEqual(response.status_code, 200)
        mock_proxy.assert_called_once()
    
    @patch('app.proxy_request')
    def test_show_model_endpoint(self, mock_proxy):
        """Test show model endpoint."""
        mock_proxy.return_value = ({"modelfile": "FROM llama2"}, 200)
        
        response = self.client.post('/api/show',
                                    json={'name': 'llama2'})
        
        self.assertEqual(response.status_code, 200)
        mock_proxy.assert_called_once()
    
    @patch('app.proxy_request')
    def test_pull_model_endpoint(self, mock_proxy):
        """Test pull model endpoint."""
        mock_proxy.return_value = ({"status": "success"}, 200)
        
        response = self.client.post('/api/pull',
                                    json={'name': 'llama2'})
        
        self.assertEqual(response.status_code, 200)
        mock_proxy.assert_called_once()
    
    @patch('app.proxy_request')
    def test_delete_model_endpoint(self, mock_proxy):
        """Test delete model endpoint."""
        mock_proxy.return_value = ({"status": "success"}, 200)
        
        response = self.client.delete('/api/delete',
                                      json={'name': 'llama2'})
        
        self.assertEqual(response.status_code, 200)
        mock_proxy.assert_called_once()
    
    def test_generate_no_json(self):
        """Test generate endpoint with no JSON data."""
        response = self.client.post('/api/generate',
                                    content_type='application/json')
        self.assertIn(response.status_code, [400, 415])


class TestProxyRequest(unittest.TestCase):
    """Test cases for proxy_request function."""
    
    def setUp(self):
        """Set up test environment."""
        self.env_patcher = patch.dict(os.environ, {
            'EXOSCALE_API_KEY': 'test_key',
            'EXOSCALE_API_SECRET': 'test_secret'
        })
        self.env_patcher.start()
        
        self.exoscale_patcher = patch('exoscale_adapter.Client')
        self.mock_client_cls = self.exoscale_patcher.start()
        
        import importlib
        import app as flask_app
        importlib.reload(flask_app)
        self.flask_app = flask_app
    
    def tearDown(self):
        """Clean up patches."""
        self.exoscale_patcher.stop()
        self.env_patcher.stop()
    
    def test_proxy_request_no_instance(self):
        """Test proxy request when instance can't be started."""
        # Patch ensure_remote_instance and get_provisioning_status on the module
        with patch.object(self.flask_app, 'ensure_remote_instance', return_value=None):
            with patch.object(self.flask_app, 'get_provisioning_status',
                              return_value={"status": "error", "error": "Test error"}):
                with self.flask_app.app.app_context():
                    result = self.flask_app.proxy_request(
                        '/api/generate', method='POST', json_data={'prompt': 'test'}
                    )
        
        # Should return error response
        self.assertEqual(result[1], 503)
    
    def test_proxy_request_provisioning(self):
        """Test proxy request when instance is being provisioned."""
        # Patch ensure_remote_instance to return None (provisioning)
        with patch.object(self.flask_app, 'ensure_remote_instance', return_value=None):
            with patch.object(self.flask_app, 'get_provisioning_status',
                              return_value={"status": "provisioning"}):
                with self.flask_app.app.app_context():
                    result = self.flask_app.proxy_request(
                        '/api/generate', method='POST', json_data={'prompt': 'test'}
                    )
        
        # Should return 503 with provisioning flag
        self.assertEqual(result[1], 503)
        data = json.loads(result[0].data)
        self.assertTrue(data.get('provisioning'))
    
    def test_proxy_request_success(self):
        """Test successful proxy request."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "test"}
        mock_response.headers = {'Content-Type': 'application/json'}
        
        with patch.object(self.flask_app, 'ensure_remote_instance',
                          return_value="http://1.2.3.4:11434"):
            with patch.object(self.flask_app.requests, 'post',
                              return_value=mock_response):
                with self.flask_app.app.app_context():
                    result = self.flask_app.proxy_request(
                        '/api/generate', method='POST', json_data={'prompt': 'test'}
                    )
        
        self.assertEqual(result[1], 200)
    
    def test_proxy_request_timeout(self):
        """Test proxy request timeout."""
        import requests as req_lib
        
        with patch.object(self.flask_app, 'ensure_remote_instance',
                          return_value="http://1.2.3.4:11434"):
            with patch.object(self.flask_app.requests, 'post',
                              side_effect=req_lib.exceptions.Timeout()):
                with self.flask_app.app.app_context():
                    result = self.flask_app.proxy_request(
                        '/api/generate', method='POST', json_data={'prompt': 'test'}
                    )
        
        # Should return timeout error
        self.assertEqual(result[1], 504)


if __name__ == '__main__':
    unittest.main()
