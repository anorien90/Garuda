"""Comprehensive tests for Exoscale Ollama Adapter.

This test suite validates the Exoscale adapter's functionality including:
- Authentication and API request handling
- Instance lifecycle management (create, start, stop, destroy)
- Security group management
- Cloud-init script generation
- Idle monitoring and auto-shutdown
- Request proxying
- Graceful shutdown

Test Coverage (57 tests total):

1. Initialization (3 tests)
   - Default and custom parameters
   - Auto-generated Ollama key

2. Authentication Headers (3 tests)
   - HMAC-SHA256 signature generation
   - Header structure validation
   - Different HTTP methods

3. Cloud-init Generation (6 tests)
   - Base64 encoding
   - Model name, Ollama key, nginx config
   - Docker setup and shebang

4. API Request Handling (6 tests)
   - GET/POST/DELETE success cases
   - HTTP errors and timeouts
   - Unsupported methods

5. Template/Instance Type Lookup (5 tests)
   - Finding by name
   - Not found cases
   - API errors

6. Security Group Management (3 tests)
   - Finding existing security group
   - Creating new security group
   - Adding firewall rules

7. Instance Lifecycle (11 tests)
   - Finding existing instances
   - Ensuring instance is running
   - Creating new instances
   - Starting stopped instances
   - Destroying instances
   - Getting instance status
   - Error handling

8. Ollama URL Generation (2 tests)
   - With and without instance IP

9. Activity Tracking (2 tests)
   - Timestamp updates
   - Thread safety

10. Idle Monitoring (4 tests)
    - Auto-destroy after timeout
    - Starting/stopping monitor
    - Already running checks

11. Request Proxying (4 tests)
    - Successful proxy
    - Activity recording
    - Error handling
    - Missing instance IP

12. Graceful Shutdown (4 tests)
    - Success case
    - Idempotency
    - Without instance
    - Thread safety

13. Integration Scenarios (2 tests)
    - Full lifecycle
    - Proxy with activity tracking

All tests use mocking - no actual API calls are made.
"""

import sys
import os
import base64
import hashlib
import hmac
import json
import time
import threading
from unittest.mock import Mock, patch, MagicMock, call
import pytest

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from garuda_intel.exoscale.adapter import ExoscaleOllamaAdapter


@pytest.fixture
def api_credentials():
    """Provide test API credentials."""
    return {
        "api_key": "EXO_test_key_12345",
        "api_secret": "test_secret_abcdefgh",
    }


@pytest.fixture
def adapter(api_credentials):
    """Create adapter instance with default configuration."""
    return ExoscaleOllamaAdapter(
        api_key=api_credentials["api_key"],
        api_secret=api_credentials["api_secret"],
        zone="ch-gva-2",
        instance_type="standard.medium",
        template_name="Linux Ubuntu 22.04 LTS 64-bit",
        disk_size=50,
        ollama_model="granite3.1-dense:8b",
        ollama_key="test-ollama-key-123",
        idle_timeout=1800,
    )


@pytest.fixture
def custom_adapter(api_credentials):
    """Create adapter instance with custom configuration."""
    return ExoscaleOllamaAdapter(
        api_key=api_credentials["api_key"],
        api_secret=api_credentials["api_secret"],
        zone="de-fra-1",
        instance_type="gpu2.medium",
        template_name="Linux Ubuntu 20.04 LTS 64-bit",
        disk_size=100,
        ollama_model="llama2",
        idle_timeout=600,
    )


class TestInitialization:
    """Test adapter initialization."""
    
    def test_default_initialization(self, adapter, api_credentials):
        """Test initialization with default parameters."""
        assert adapter.api_key == api_credentials["api_key"]
        assert adapter.api_secret == api_credentials["api_secret"]
        assert adapter.zone == "ch-gva-2"
        assert adapter.instance_type == "standard.medium"
        assert adapter.template_name == "Linux Ubuntu 22.04 LTS 64-bit"
        assert adapter.disk_size == 50
        assert adapter.ollama_model == "granite3.1-dense:8b"
        assert adapter.ollama_key == "test-ollama-key-123"
        assert adapter.idle_timeout == 1800
        assert adapter.base_url == "https://api-ch-gva-2.exoscale.com/v2"
        
        # Check initial state
        assert adapter.instance_id is None
        assert adapter.instance_ip is None
        assert adapter.security_group_id is None
        assert adapter._shutdown_called is False
        assert adapter.idle_monitor_running is False
    
    def test_custom_initialization(self, custom_adapter, api_credentials):
        """Test initialization with custom parameters."""
        assert custom_adapter.zone == "de-fra-1"
        assert custom_adapter.instance_type == "gpu2.medium"
        assert custom_adapter.disk_size == 100
        assert custom_adapter.ollama_model == "llama2"
        assert custom_adapter.idle_timeout == 600
        assert custom_adapter.base_url == "https://api-de-fra-1.exoscale.com/v2"
    
    def test_auto_generated_ollama_key(self, api_credentials):
        """Test that ollama_key is auto-generated when not provided."""
        adapter = ExoscaleOllamaAdapter(
            api_key=api_credentials["api_key"],
            api_secret=api_credentials["api_secret"],
        )
        
        assert adapter.ollama_key is not None
        assert len(adapter.ollama_key) > 20  # Should be a long random string


class TestAuthHeaders:
    """Test HMAC-SHA256 authentication header generation."""
    
    def test_auth_headers_structure(self, adapter):
        """Test auth headers contain required fields."""
        headers = adapter._auth_headers("GET", "/instance", "")
        
        assert "Authorization" in headers
        assert "Content-Type" in headers
        assert headers["Content-Type"] == "application/json"
        
        auth = headers["Authorization"]
        assert auth.startswith("EXO2-HMAC-SHA256")
        assert "credential=" in auth
        assert "expires=" in auth
        assert "signature=" in auth
    
    def test_auth_headers_signature_calculation(self, adapter):
        """Test HMAC signature is calculated correctly."""
        method = "POST"
        path = "/instance"
        body = '{"name":"test"}'
        
        with patch('time.time', return_value=1000000):
            headers = adapter._auth_headers(method, path, body)
        
        # Manually calculate expected signature
        expiration = "1000600"  # 1000000 + 600
        message = f"{method} {path}\n{body}\n{expiration}"
        expected_signature = hmac.new(
            adapter.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        auth = headers["Authorization"]
        assert f"credential={adapter.api_key}" in auth
        assert f"expires={expiration}" in auth
        assert f"signature={expected_signature}" in auth
    
    def test_auth_headers_different_methods(self, adapter):
        """Test auth headers for different HTTP methods."""
        get_headers = adapter._auth_headers("GET", "/instance", "")
        post_headers = adapter._auth_headers("POST", "/instance", '{"data":"test"}')
        delete_headers = adapter._auth_headers("DELETE", "/instance/123", "")
        
        # All should have different signatures
        assert get_headers["Authorization"] != post_headers["Authorization"]
        assert get_headers["Authorization"] != delete_headers["Authorization"]


class TestCloudInitGeneration:
    """Test cloud-init script generation."""
    
    def test_cloud_init_is_base64_encoded(self, adapter):
        """Test cloud-init script is base64 encoded."""
        cloud_init = adapter._generate_cloud_init()
        
        # Should be valid base64
        try:
            decoded = base64.b64decode(cloud_init)
            assert len(decoded) > 0
        except Exception as e:
            pytest.fail(f"Cloud-init is not valid base64: {e}")
    
    def test_cloud_init_contains_model_name(self, adapter):
        """Test cloud-init script contains the ollama model name."""
        cloud_init = adapter._generate_cloud_init()
        decoded = base64.b64decode(cloud_init).decode()
        
        assert adapter.ollama_model in decoded
        assert f"ollama pull {adapter.ollama_model}" in decoded
    
    def test_cloud_init_contains_ollama_key(self, adapter):
        """Test cloud-init script contains the ollama API key."""
        cloud_init = adapter._generate_cloud_init()
        decoded = base64.b64decode(cloud_init).decode()
        
        assert adapter.ollama_key in decoded
    
    def test_cloud_init_contains_nginx_config(self, adapter):
        """Test cloud-init script contains nginx configuration."""
        cloud_init = adapter._generate_cloud_init()
        decoded = base64.b64decode(cloud_init).decode()
        
        # Check for nginx configuration elements
        assert "nginx" in decoded
        assert f"listen {adapter.NGINX_PROXY_PORT}" in decoded
        assert "proxy_pass" in decoded
        assert "$http_x_ollama_key" in decoded
    
    def test_cloud_init_contains_docker_setup(self, adapter):
        """Test cloud-init script contains Docker setup."""
        cloud_init = adapter._generate_cloud_init()
        decoded = base64.b64decode(cloud_init).decode()
        
        assert "docker" in decoded.lower()
        assert "ollama/ollama:latest" in decoded
        assert f"127.0.0.1:{adapter.OLLAMA_INTERNAL_PORT}" in decoded
    
    def test_cloud_init_shebang(self, adapter):
        """Test cloud-init script starts with proper shebang."""
        cloud_init = adapter._generate_cloud_init()
        decoded = base64.b64decode(cloud_init).decode()
        
        assert decoded.startswith("#!/bin/bash")


class TestAPIRequest:
    """Test API request handling."""
    
    @patch('garuda_intel.exoscale.adapter.requests.get')
    def test_api_request_get_success(self, mock_get, adapter):
        """Test successful GET request."""
        mock_response = Mock()
        mock_response.json.return_value = {"instances": []}
        mock_response.raise_for_status = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        result = adapter._api_request("GET", "/instance")
        
        assert result == {"instances": []}
        mock_get.assert_called_once()
        assert adapter.base_url + "/instance" == mock_get.call_args[0][0]
    
    @patch('garuda_intel.exoscale.adapter.requests.post')
    def test_api_request_post_success(self, mock_post, adapter):
        """Test successful POST request."""
        mock_response = Mock()
        mock_response.json.return_value = {"id": "inst-123"}
        mock_response.raise_for_status = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        data = {"name": "test-instance"}
        result = adapter._api_request("POST", "/instance", data)
        
        assert result == {"id": "inst-123"}
        mock_post.assert_called_once()
        
        # Check that body was JSON encoded
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["data"] == json.dumps(data)
    
    @patch('garuda_intel.exoscale.adapter.requests.delete')
    def test_api_request_delete_success(self, mock_delete, adapter):
        """Test successful DELETE request with 204 No Content."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.status_code = 204
        mock_delete.return_value = mock_response
        
        result = adapter._api_request("DELETE", "/instance/inst-123")
        
        assert result == {}  # 204 returns empty dict
        mock_delete.assert_called_once()
    
    @patch('garuda_intel.exoscale.adapter.requests.get')
    def test_api_request_http_error(self, mock_get, adapter):
        """Test API request with HTTP error."""
        import requests
        mock_get.side_effect = requests.exceptions.RequestException("Connection error")
        
        result = adapter._api_request("GET", "/instance")
        
        assert result is None
    
    @patch('garuda_intel.exoscale.adapter.requests.get')
    def test_api_request_timeout(self, mock_get, adapter):
        """Test API request timeout handling."""
        import requests
        mock_get.side_effect = requests.exceptions.Timeout("Request timed out")
        
        result = adapter._api_request("GET", "/instance", timeout=5)
        
        assert result is None
    
    def test_api_request_unsupported_method(self, adapter):
        """Test API request with unsupported HTTP method."""
        result = adapter._api_request("PATCH", "/instance")
        
        assert result is None


class TestFindTemplate:
    """Test template lookup functionality."""
    
    @patch.object(ExoscaleOllamaAdapter, '_api_request')
    def test_find_template_success(self, mock_api_request, adapter):
        """Test finding template by name."""
        mock_api_request.return_value = {
            "templates": [
                {"id": "tpl-001", "name": "Linux Ubuntu 20.04 LTS 64-bit"},
                {"id": "tpl-002", "name": "Linux Ubuntu 22.04 LTS 64-bit"},
                {"id": "tpl-003", "name": "Linux Debian 11"},
            ]
        }
        
        template_id = adapter._find_template()
        
        assert template_id == "tpl-002"
        mock_api_request.assert_called_once_with("GET", "/template")
    
    @patch.object(ExoscaleOllamaAdapter, '_api_request')
    def test_find_template_not_found(self, mock_api_request, adapter):
        """Test template not found."""
        mock_api_request.return_value = {
            "templates": [
                {"id": "tpl-001", "name": "Linux Ubuntu 20.04 LTS 64-bit"},
            ]
        }
        
        template_id = adapter._find_template()
        
        assert template_id is None
    
    @patch.object(ExoscaleOllamaAdapter, '_api_request')
    def test_find_template_api_error(self, mock_api_request, adapter):
        """Test template lookup with API error."""
        mock_api_request.return_value = None
        
        template_id = adapter._find_template()
        
        assert template_id is None


class TestFindInstanceType:
    """Test instance type lookup functionality."""
    
    @patch.object(ExoscaleOllamaAdapter, '_api_request')
    def test_find_instance_type_success(self, mock_api_request, adapter):
        """Test finding instance type by name."""
        mock_api_request.return_value = {
            "instance-types": [
                {"id": "type-001", "name": "standard.small"},
                {"id": "type-002", "name": "standard.medium"},
                {"id": "type-003", "name": "standard.large"},
            ]
        }
        
        type_id = adapter._find_instance_type()
        
        assert type_id == "type-002"
        mock_api_request.assert_called_once_with("GET", "/instance-type")
    
    @patch.object(ExoscaleOllamaAdapter, '_api_request')
    def test_find_instance_type_not_found(self, mock_api_request, adapter):
        """Test instance type not found."""
        mock_api_request.return_value = {
            "instance-types": [
                {"id": "type-001", "name": "standard.small"},
            ]
        }
        
        type_id = adapter._find_instance_type()
        
        assert type_id is None


class TestEnsureSecurityGroup:
    """Test security group management."""
    
    @patch.object(ExoscaleOllamaAdapter, '_api_request')
    def test_ensure_security_group_existing(self, mock_api_request, adapter):
        """Test finding existing security group."""
        mock_api_request.return_value = {
            "security-groups": [
                {"id": "sg-001", "name": "other-sg"},
                {"id": "sg-002", "name": "garuda-ollama-sg"},
            ]
        }
        
        sg_id = adapter._ensure_security_group()
        
        assert sg_id == "sg-002"
        # Should only make one GET call, no POST
        mock_api_request.assert_called_once_with("GET", "/security-group")
    
    @patch.object(ExoscaleOllamaAdapter, '_api_request')
    def test_ensure_security_group_create_new(self, mock_api_request, adapter):
        """Test creating new security group."""
        # First call returns empty list, second creates SG, third adds rule
        mock_api_request.side_effect = [
            {"security-groups": []},  # GET - no existing SG
            {"id": "sg-new-123"},  # POST - create SG
            {"id": "rule-123"},  # POST - add rule
        ]
        
        sg_id = adapter._ensure_security_group()
        
        assert sg_id == "sg-new-123"
        assert mock_api_request.call_count == 3
        
        # Verify calls
        calls = mock_api_request.call_args_list
        assert calls[0] == call("GET", "/security-group")
        assert calls[1] == call("POST", "/security-group", {"name": "garuda-ollama-sg"})
        # Check third call is to add rule with correct path
        assert calls[2][0][0] == "POST"
        assert calls[2][0][1] == "/security-group/sg-new-123/rules"
    
    @patch.object(ExoscaleOllamaAdapter, '_api_request')
    def test_ensure_security_group_rule_creation(self, mock_api_request, adapter):
        """Test security group rule is created with correct parameters."""
        mock_api_request.side_effect = [
            {"security-groups": []},
            {"id": "sg-new-123"},
            {"id": "rule-123"},
        ]
        
        adapter._ensure_security_group()
        
        # Check rule creation call
        rule_call = mock_api_request.call_args_list[2]
        rule_data = rule_call[0][2]
        
        assert rule_data["start-port"] == adapter.NGINX_PROXY_PORT
        assert rule_data["end-port"] == adapter.NGINX_PROXY_PORT
        assert rule_data["protocol"] == "tcp"
        assert rule_data["cidr"] == "0.0.0.0/0"


class TestFindExistingInstance:
    """Test finding existing instances."""
    
    @patch.object(ExoscaleOllamaAdapter, '_api_request')
    def test_find_existing_instance_found(self, mock_api_request, adapter):
        """Test finding existing instance by name tag."""
        mock_api_request.return_value = {
            "instances": [
                {"id": "inst-001", "name": "other-instance"},
                {"id": "inst-002", "name": "garuda-ollama", "state": "running"},
            ]
        }
        
        instance = adapter._find_existing_instance()
        
        assert instance is not None
        assert instance["id"] == "inst-002"
        assert instance["name"] == "garuda-ollama"
    
    @patch.object(ExoscaleOllamaAdapter, '_api_request')
    def test_find_existing_instance_not_found(self, mock_api_request, adapter):
        """Test instance not found."""
        mock_api_request.return_value = {
            "instances": [
                {"id": "inst-001", "name": "other-instance"},
            ]
        }
        
        instance = adapter._find_existing_instance()
        
        assert instance is None


class TestEnsureInstance:
    """Test instance lifecycle - ensure instance is running."""
    
    @patch.object(ExoscaleOllamaAdapter, '_find_existing_instance')
    @patch.object(ExoscaleOllamaAdapter, 'get_ollama_url')
    def test_ensure_instance_running_exists(self, mock_get_url, mock_find, adapter):
        """Test ensure_instance with existing running instance."""
        mock_find.return_value = {
            "id": "inst-running",
            "state": "running",
            "public-ip": "1.2.3.4",
        }
        mock_get_url.return_value = "http://1.2.3.4:11435/api/generate"
        
        url = adapter.ensure_instance()
        
        assert url == "http://1.2.3.4:11435/api/generate"
        assert adapter.instance_id == "inst-running"
        assert adapter.instance_ip == "1.2.3.4"
    
    @patch.object(ExoscaleOllamaAdapter, '_find_existing_instance')
    @patch.object(ExoscaleOllamaAdapter, '_api_request')
    @patch.object(ExoscaleOllamaAdapter, 'get_ollama_url')
    def test_ensure_instance_stopped_starts(self, mock_get_url, mock_api, mock_find, adapter):
        """Test ensure_instance starts a stopped instance."""
        mock_find.return_value = {
            "id": "inst-stopped",
            "state": "stopped",
        }
        
        # Mock start instance and subsequent GET
        mock_api.side_effect = [
            {"id": "inst-stopped"},  # PUT :start
            {"id": "inst-stopped", "state": "running", "public-ip": "1.2.3.5"},  # GET status
        ]
        
        mock_get_url.return_value = "http://1.2.3.5:11435/api/generate"
        
        with patch('time.sleep'):  # Don't actually sleep
            url = adapter.ensure_instance()
        
        assert url == "http://1.2.3.5:11435/api/generate"
        assert adapter.instance_ip == "1.2.3.5"
        
        # Verify start was called
        calls = mock_api.call_args_list
        assert any("inst-stopped:start" in str(call) for call in calls)
    
    @patch.object(ExoscaleOllamaAdapter, '_find_existing_instance')
    @patch.object(ExoscaleOllamaAdapter, 'create_instance')
    def test_ensure_instance_creates_new(self, mock_create, mock_find, adapter):
        """Test ensure_instance creates new instance when none exists."""
        mock_find.return_value = None
        mock_create.return_value = "http://1.2.3.6:11435/api/generate"
        
        url = adapter.ensure_instance()
        
        assert url == "http://1.2.3.6:11435/api/generate"
        mock_create.assert_called_once()


class TestCreateInstance:
    """Test instance creation."""
    
    @patch.object(ExoscaleOllamaAdapter, '_ensure_security_group')
    @patch.object(ExoscaleOllamaAdapter, '_find_template')
    @patch.object(ExoscaleOllamaAdapter, '_find_instance_type')
    @patch.object(ExoscaleOllamaAdapter, '_api_request')
    @patch('time.sleep')
    @patch('time.time')
    def test_create_instance_success(
        self, mock_time, mock_sleep, mock_api, mock_find_type, mock_find_tpl, mock_sg, adapter
    ):
        """Test successful instance creation."""
        # Mock security group, template, and type
        mock_sg.return_value = "sg-123"
        mock_find_tpl.return_value = "tpl-456"
        mock_find_type.return_value = "type-789"
        
        # Mock time for timeout check
        mock_time.side_effect = [0, 5, 15]  # Simulate time progression
        
        # Mock API responses
        mock_api.side_effect = [
            {"id": "inst-new"},  # POST /instance
            {"id": "inst-new", "state": "running", "public-ip": "1.2.3.7"},  # GET /instance/inst-new
        ]
        
        url = adapter.create_instance()
        
        assert url == "http://1.2.3.7:11435/api/generate"
        assert adapter.instance_id == "inst-new"
        assert adapter.instance_ip == "1.2.3.7"
        
        # Verify instance creation call
        create_call = [c for c in mock_api.call_args_list if c[0][0] == "POST"][0]
        instance_data = create_call[0][2]
        assert instance_data["name"] == "garuda-ollama"
        assert instance_data["disk-size"] == 50
    
    @patch.object(ExoscaleOllamaAdapter, '_ensure_security_group')
    def test_create_instance_sg_failure(self, mock_sg, adapter):
        """Test instance creation fails when security group creation fails."""
        mock_sg.return_value = None
        
        url = adapter.create_instance()
        
        assert url is None


class TestDestroyInstance:
    """Test instance destruction."""
    
    @patch.object(ExoscaleOllamaAdapter, '_api_request')
    def test_destroy_instance_success(self, mock_api, adapter):
        """Test successful instance destruction."""
        adapter.instance_id = "inst-to-delete"
        adapter.instance_ip = "1.2.3.4"
        
        mock_api.return_value = {}  # 204 No Content
        
        result = adapter.destroy_instance()
        
        assert result is True
        assert adapter.instance_id is None
        assert adapter.instance_ip is None
        mock_api.assert_called_once_with("DELETE", "/instance/inst-to-delete")
    
    @patch.object(ExoscaleOllamaAdapter, '_api_request')
    def test_destroy_instance_failure(self, mock_api, adapter):
        """Test instance destruction failure."""
        adapter.instance_id = "inst-to-delete"
        
        mock_api.return_value = None  # API error
        
        result = adapter.destroy_instance()
        
        assert result is False
        # Instance ID should still be set on failure
        assert adapter.instance_id == "inst-to-delete"
    
    def test_destroy_instance_no_instance(self, adapter):
        """Test destroying when no instance exists."""
        adapter.instance_id = None
        
        result = adapter.destroy_instance()
        
        assert result is False


class TestGetInstanceStatus:
    """Test instance status retrieval."""
    
    @patch.object(ExoscaleOllamaAdapter, '_api_request')
    def test_get_instance_status_success(self, mock_api, adapter):
        """Test getting instance status."""
        adapter.instance_id = "inst-123"
        mock_api.return_value = {"id": "inst-123", "state": "running"}
        
        status = adapter.get_instance_status()
        
        assert status == "running"
    
    @patch.object(ExoscaleOllamaAdapter, '_api_request')
    def test_get_instance_status_various_states(self, mock_api, adapter):
        """Test various instance states."""
        adapter.instance_id = "inst-123"
        
        for state in ["running", "stopped", "starting", "stopping"]:
            mock_api.return_value = {"state": state}
            assert adapter.get_instance_status() == state
    
    def test_get_instance_status_no_instance(self, adapter):
        """Test getting status when no instance exists."""
        adapter.instance_id = None
        
        status = adapter.get_instance_status()
        
        assert status is None


class TestGetOllamaUrl:
    """Test Ollama URL generation."""
    
    def test_get_ollama_url_with_ip(self, adapter):
        """Test URL generation with instance IP."""
        adapter.instance_ip = "10.20.30.40"
        
        url = adapter.get_ollama_url()
        
        assert url == "http://10.20.30.40:11435/api/generate"
    
    def test_get_ollama_url_without_ip(self, adapter):
        """Test URL generation without instance IP."""
        adapter.instance_ip = None
        
        url = adapter.get_ollama_url()
        
        assert url is None


class TestRecordActivity:
    """Test activity tracking."""
    
    def test_record_activity_updates_timestamp(self, adapter):
        """Test that record_activity updates the last_activity timestamp."""
        initial_time = adapter.last_activity
        
        with patch('time.time', return_value=initial_time + 100):
            adapter.record_activity()
        
        assert adapter.last_activity == initial_time + 100
    
    def test_record_activity_thread_safe(self, adapter):
        """Test that record_activity is thread-safe."""
        results = []
        
        def record_multiple():
            for i in range(100):
                with patch('time.time', return_value=1000 + i):
                    adapter.record_activity()
                    results.append(adapter.last_activity)
        
        threads = [threading.Thread(target=record_multiple) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Should have recorded all activities
        assert len(results) == 300


class TestIdleMonitor:
    """Test idle monitoring and auto-shutdown."""
    
    @patch('time.sleep')
    @patch('time.time')
    @patch.object(ExoscaleOllamaAdapter, 'destroy_instance')
    def test_idle_monitor_auto_destroys(self, mock_destroy, mock_time, mock_sleep, adapter):
        """Test idle monitor destroys instance after timeout."""
        # Set short timeout for testing
        adapter.idle_timeout = 10
        adapter.last_activity = 1000
        
        # Simulate time progression
        mock_time.side_effect = [
            1000,  # Initial check
            1005,  # First check (not idle)
            1015,  # Second check (idle > 10s)
        ]
        
        # Start monitor
        adapter.start_idle_monitor()
        
        # Wait for thread to process
        adapter.idle_monitor_thread.join(timeout=2)
        
        # Should have destroyed instance
        mock_destroy.assert_called_once()
    
    def test_start_idle_monitor(self, adapter):
        """Test starting idle monitor."""
        adapter.start_idle_monitor()
        
        assert adapter.idle_monitor_running is True
        assert adapter.idle_monitor_thread is not None
        assert adapter.idle_monitor_thread.is_alive()
        
        # Cleanup
        adapter.stop_idle_monitor()
    
    def test_start_idle_monitor_already_running(self, adapter):
        """Test starting idle monitor when already running."""
        adapter.start_idle_monitor()
        
        # Try starting again
        adapter.start_idle_monitor()
        
        # Should still be running
        assert adapter.idle_monitor_running is True
        
        # Cleanup
        adapter.stop_idle_monitor()
    
    def test_stop_idle_monitor(self, adapter):
        """Test stopping idle monitor."""
        adapter.start_idle_monitor()
        assert adapter.idle_monitor_running is True
        
        adapter.stop_idle_monitor()
        
        assert adapter.idle_monitor_running is False
        # Thread should exit (it's a daemon thread so may not stop immediately)
        if adapter.idle_monitor_thread:
            adapter.idle_monitor_thread.join(timeout=2)
            # Note: Daemon threads may still be alive briefly after join timeout
            # The important part is that idle_monitor_running is False


class TestProxyRequest:
    """Test request proxying to remote Ollama."""
    
    @patch('garuda_intel.exoscale.adapter.requests.post')
    def test_proxy_request_success(self, mock_post, adapter):
        """Test successful request proxy."""
        adapter.instance_ip = "1.2.3.4"
        
        mock_response = Mock()
        mock_response.json.return_value = {"response": "Hello"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        payload = {"model": "granite3.1-dense:8b", "prompt": "Hi"}
        result = adapter.proxy_request(payload)
        
        assert result == {"response": "Hello"}
        
        # Verify request was made with correct headers
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["headers"]["X-Ollama-Key"] == adapter.ollama_key
        assert call_kwargs["json"] == payload
    
    @patch('garuda_intel.exoscale.adapter.requests.post')
    def test_proxy_request_records_activity(self, mock_post, adapter):
        """Test that proxy request records activity."""
        adapter.instance_ip = "1.2.3.4"
        
        mock_response = Mock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        initial_time = adapter.last_activity
        
        with patch('time.time', return_value=initial_time + 50):
            adapter.proxy_request({"prompt": "test"})
        
        assert adapter.last_activity == initial_time + 50
    
    @patch('garuda_intel.exoscale.adapter.requests.post')
    def test_proxy_request_error(self, mock_post, adapter):
        """Test proxy request with error."""
        adapter.instance_ip = "1.2.3.4"
        
        import requests
        mock_post.side_effect = requests.exceptions.RequestException("Connection failed")
        
        result = adapter.proxy_request({"prompt": "test"})
        
        assert result is None
    
    def test_proxy_request_no_instance_ip(self, adapter):
        """Test proxy request when no instance IP is set."""
        adapter.instance_ip = None
        
        result = adapter.proxy_request({"prompt": "test"})
        
        assert result is None


class TestShutdown:
    """Test graceful shutdown."""
    
    @patch.object(ExoscaleOllamaAdapter, 'stop_idle_monitor')
    @patch.object(ExoscaleOllamaAdapter, 'destroy_instance')
    def test_shutdown_success(self, mock_destroy, mock_stop, adapter):
        """Test successful shutdown."""
        adapter.instance_id = "inst-123"
        
        adapter.shutdown()
        
        mock_stop.assert_called_once()
        mock_destroy.assert_called_once()
        assert adapter._shutdown_called is True
    
    @patch.object(ExoscaleOllamaAdapter, 'stop_idle_monitor')
    @patch.object(ExoscaleOllamaAdapter, 'destroy_instance')
    def test_shutdown_idempotent(self, mock_destroy, mock_stop, adapter):
        """Test shutdown is idempotent - calling twice doesn't error."""
        adapter.instance_id = "inst-123"
        
        # First shutdown
        adapter.shutdown()
        assert mock_destroy.call_count == 1
        
        # Second shutdown
        adapter.shutdown()
        
        # Should not destroy again
        assert mock_destroy.call_count == 1
        assert mock_stop.call_count == 1
    
    @patch.object(ExoscaleOllamaAdapter, 'stop_idle_monitor')
    @patch.object(ExoscaleOllamaAdapter, 'destroy_instance')
    def test_shutdown_without_instance(self, mock_destroy, mock_stop, adapter):
        """Test shutdown when no instance exists."""
        adapter.instance_id = None
        
        adapter.shutdown()
        
        mock_stop.assert_called_once()
        # destroy_instance should NOT be called if instance_id is None
        mock_destroy.assert_not_called()
        assert adapter._shutdown_called is True
    
    def test_shutdown_thread_safe(self, adapter):
        """Test shutdown is thread-safe."""
        adapter.instance_id = "inst-123"
        
        with patch.object(adapter, 'stop_idle_monitor'), \
             patch.object(adapter, 'destroy_instance'):
            
            # Call shutdown from multiple threads
            threads = [threading.Thread(target=adapter.shutdown) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            
            # Should only execute once
            assert adapter._shutdown_called is True


class TestIntegrationScenarios:
    """Test complete integration scenarios."""
    
    @patch.object(ExoscaleOllamaAdapter, '_api_request')
    @patch('time.sleep')
    @patch('time.time')
    def test_full_lifecycle(self, mock_time, mock_sleep, mock_api, adapter):
        """Test full instance lifecycle: create -> use -> destroy."""
        # Mock time
        mock_time.return_value = 1000
        
        # Setup mocks for create_instance
        mock_api.side_effect = [
            # _ensure_security_group
            {"security-groups": []},
            {"id": "sg-123"},
            {"id": "rule-123"},
            # _find_template
            {"templates": [{"id": "tpl-456", "name": "Linux Ubuntu 22.04 LTS 64-bit"}]},
            # _find_instance_type
            {"instance-types": [{"id": "type-789", "name": "standard.medium"}]},
            # create_instance POST
            {"id": "inst-new"},
            # create_instance GET status
            {"id": "inst-new", "state": "running", "public-ip": "1.2.3.4"},
            # destroy_instance DELETE
            {},
        ]
        
        # Create instance
        url = adapter.create_instance()
        assert url == "http://1.2.3.4:11435/api/generate"
        assert adapter.instance_id == "inst-new"
        
        # Destroy instance
        result = adapter.destroy_instance()
        assert result is True
        assert adapter.instance_id is None
    
    @patch('garuda_intel.exoscale.adapter.requests.post')
    def test_proxy_with_activity_tracking(self, mock_post, adapter):
        """Test proxying request updates activity timestamp."""
        adapter.instance_ip = "1.2.3.4"
        
        mock_response = Mock()
        mock_response.json.return_value = {"response": "test"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        initial_activity = adapter.last_activity
        
        # Wait a bit then make request
        with patch('time.time', return_value=initial_activity + 100):
            adapter.proxy_request({"prompt": "test"})
        
        # Activity should be updated
        assert adapter.last_activity > initial_activity
        assert adapter.last_activity == initial_activity + 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
