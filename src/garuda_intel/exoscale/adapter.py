"""Exoscale Ollama Adapter - Remote Ollama instance management.

This module manages the lifecycle of Ollama instances on Exoscale cloud:
- Create/start/stop/destroy compute instances
- Configure security groups for secure access
- Set up nginx reverse proxy with API key authentication
- Monitor idle time and auto-shutdown to save costs
- Proxy requests to remote Ollama with transparent authentication
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
from typing import Dict, Any, Optional
import requests


class ExoscaleAuthError(Exception):
    """Raised when Exoscale API returns authentication/authorization errors (401/403)."""
    pass


class ExoscaleOllamaAdapter:
    """Adapter for managing remote Ollama instances on Exoscale cloud.
    
    Features:
    - Automatic instance lifecycle management
    - Security group and firewall configuration
    - Nginx reverse proxy with API key authentication
    - Idle monitoring with auto-shutdown
    - Transparent request proxying
    """
    
    SECURITY_GROUP_NAME = "garuda-ollama-sg"
    INSTANCE_NAME_TAG = "garuda-ollama"
    NGINX_PROXY_PORT = 11435
    OLLAMA_INTERNAL_PORT = 11434
    INSTANCE_STARTUP_TIMEOUT = 300  # Maximum wait time for instance to start (seconds)
    CLOUD_INIT_WAIT_TIME = 60  # Wait time for cloud-init to complete (seconds)
    IDLE_CHECK_INTERVAL = 60  # How often to check for idle timeout (seconds)
    
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        zone: str = "at-vie-2",
        instance_type: str = "a5000.small",
        template_name: str = "Linux Ubuntu 22.04 LTS 64-bit",
        disk_size: int = 50,
        ollama_model: str = "granite3.1-dense:8b",
        ollama_key: Optional[str] = None,
        idle_timeout: int = 1800,
    ):
        """Initialize Exoscale Ollama adapter.
        
        Args:
            api_key: Exoscale API key
            api_secret: Exoscale API secret
            zone: Exoscale zone (e.g., 'ch-gva-2', 'de-fra-1', 'at-vie-1')
            instance_type: Instance type (e.g., 'standard.medium', 'gpu2.medium')
            template_name: OS template name
            disk_size: Root disk size in GB
            ollama_model: Ollama model to pull on startup
            ollama_key: API key for Ollama proxy (auto-generated if None)
            idle_timeout: Seconds of inactivity before auto-shutdown
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.zone = zone
        self.instance_type = instance_type
        self.template_name = template_name
        self.disk_size = disk_size
        self.ollama_model = ollama_model
        self.ollama_key = ollama_key or secrets.token_urlsafe(32)
        self.idle_timeout = idle_timeout
        
        self.base_url = f"https://api-{zone}.exoscale.com/v2"
        self.logger = logging.getLogger(__name__)
        
        # Instance tracking
        self.instance_id: Optional[str] = None
        self.instance_ip: Optional[str] = None
        self.security_group_id: Optional[str] = None
        
        # Shutdown protection
        self._shutdown_called = False
        self._shutdown_lock = threading.Lock()
        
        # Activity tracking for idle shutdown
        self.last_activity = time.time()
        self.activity_lock = threading.Lock()
        self.idle_monitor_thread: Optional[threading.Thread] = None
        self.idle_monitor_running = False
    
    def _auth_headers(self, method: str, path: str, body: str = "") -> Dict[str, str]:
        """Generate Exoscale API v2 auth headers using HMAC-SHA256.
        
        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            path: API path (e.g., '/instance')
            body: Request body JSON string
            
        Returns:
            Dictionary of HTTP headers including authorization
        """
        expiration = str(int(time.time()) + 600)  # 10 minute expiration
        message = f"{method} {path}\n{body}\n{expiration}"
        signature = hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return {
            "Authorization": f"EXO2-HMAC-SHA256 credential={self.api_key},expires={expiration},signature={signature}",
            "Content-Type": "application/json",
        }
    
    def _api_request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        timeout: int = 30,
    ) -> Optional[Dict[str, Any]]:
        """Make an authenticated request to Exoscale API.
        
        Args:
            method: HTTP method
            path: API endpoint path
            data: Request body data
            timeout: Request timeout in seconds
            
        Returns:
            Response JSON data or None on error
        """
        url = f"{self.base_url}{path}"
        body = json.dumps(data) if data else ""
        headers = self._auth_headers(method, path, body)
        
        try:
            if method == "GET":
                resp = requests.get(url, headers=headers, timeout=timeout)
            elif method == "POST":
                resp = requests.post(url, headers=headers, data=body, timeout=timeout)
            elif method == "DELETE":
                resp = requests.delete(url, headers=headers, timeout=timeout)
            else:
                self.logger.error(f"Unsupported HTTP method: {method}")
                return None
            
            resp.raise_for_status()
            
            # Some DELETE operations return 204 No Content
            if resp.status_code == 204:
                return {}
            
            return resp.json()
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code in (401, 403):
                self.logger.error(f"Exoscale API authentication failed: {e}")
                raise ExoscaleAuthError(
                    f"Exoscale API authentication/authorization failed (HTTP {e.response.status_code}). "
                    "Check your EXOSCALE_API_KEY and EXOSCALE_API_SECRET."
                ) from e
            self.logger.error(f"Exoscale API request failed: {e}")
            return None
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Exoscale API request failed: {e}")
            return None
    
    def _find_template(self) -> Optional[str]:
        """Find the template ID by name.
        
        Returns:
            Template ID or None if not found
        """
        result = self._api_request("GET", "/template")
        if not result or "templates" not in result:
            return None
        
        for template in result["templates"]:
            if template.get("name") == self.template_name:
                return template.get("id")
        
        self.logger.warning(f"Template '{self.template_name}' not found")
        return None
    
    def _find_instance_type(self) -> Optional[str]:
        """Find the instance type ID by name.
        
        Returns:
            Instance type ID or None if not found
        """
        result = self._api_request("GET", "/instance-type")
        if not result or "instance-types" not in result:
            return None
        
        for itype in result["instance-types"]:
            if itype.get("name") == self.instance_type:
                return itype.get("id")
        
        self.logger.warning(f"Instance type '{self.instance_type}' not found")
        return None
    
    def _ensure_security_group(self) -> Optional[str]:
        """Ensure security group exists with proper rules.
        
        Creates a security group allowing inbound traffic on port 11435 (nginx proxy).
        
        Returns:
            Security group ID or None on error
        """
        # Check if security group already exists
        result = self._api_request("GET", "/security-group")
        if result and "security-groups" in result:
            for sg in result["security-groups"]:
                if sg.get("name") == self.SECURITY_GROUP_NAME:
                    self.logger.info(f"Found existing security group: {sg.get('id')}")
                    return sg.get("id")
        
        # Create new security group
        self.logger.info(f"Creating security group '{self.SECURITY_GROUP_NAME}'")
        sg_data = {"name": self.SECURITY_GROUP_NAME}
        result = self._api_request("POST", "/security-group", sg_data)
        if not result or "id" not in result:
            self.logger.error("Failed to create security group")
            return None
        
        sg_id = result["id"]
        
        # Add rule to allow inbound traffic on port 11435
        rule_data = {
            "description": "Allow Ollama proxy access",
            "start-port": self.NGINX_PROXY_PORT,
            "end-port": self.NGINX_PROXY_PORT,
            "protocol": "tcp",
            "cidr": "0.0.0.0/0",
        }
        
        rule_result = self._api_request("POST", f"/security-group/{sg_id}/rules", rule_data)
        if not rule_result:
            self.logger.warning(f"Failed to add firewall rule to security group {sg_id}")
        
        self.logger.info(f"Security group created: {sg_id}")
        return sg_id
    
    def _generate_cloud_init(self) -> str:
        """Generate cloud-init user-data script.
        
        The script:
        - Installs Docker
        - Runs ollama/ollama container
        - Installs and configures nginx as reverse proxy
        - Pulls the configured Ollama model
        
        Returns:
            Base64-encoded cloud-init script
        """
        script = f"""#!/bin/bash
set -e

# Update system
apt-get update
apt-get install -y ca-certificates curl gnupg nginx

# Install Docker
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io

# Start Ollama container on localhost
docker run -d --name ollama -p 127.0.0.1:{self.OLLAMA_INTERNAL_PORT}:{self.OLLAMA_INTERNAL_PORT} ollama/ollama:latest

# Wait for Ollama to be ready
sleep 10

# Pull the model
docker exec ollama ollama pull {self.ollama_model}

# Configure nginx reverse proxy with API key check
cat > /etc/nginx/sites-available/ollama-proxy << 'EOF'
server {{
    listen {self.NGINX_PROXY_PORT};
    
    location / {{
        # Check for API key header
        if ($http_x_ollama_key != "{self.ollama_key}") {{
            return 401;
        }}
        
        proxy_pass http://127.0.0.1:{self.OLLAMA_INTERNAL_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Disable buffering for streaming responses
        proxy_buffering off;
    }}
}}
EOF

# Enable the site
ln -sf /etc/nginx/sites-available/ollama-proxy /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test and reload nginx
nginx -t
systemctl reload nginx

echo "Garuda Ollama setup complete"
"""
        
        return base64.b64encode(script.encode()).decode()
    
    def _find_existing_instance(self) -> Optional[Dict[str, Any]]:
        """Find existing Garuda Ollama instance by name tag.
        
        Returns:
            Instance data or None if not found
        """
        result = self._api_request("GET", "/instance")
        if not result or "instances" not in result:
            return None
        
        for instance in result["instances"]:
            if instance.get("name") == self.INSTANCE_NAME_TAG:
                return instance
        
        return None
    
    def create_instance(self) -> Optional[str]:
        """Create a new Exoscale compute instance with Ollama.
        
        Returns:
            Ollama URL (http://ip:port/api/generate) or None on error
        """
        # Ensure security group exists
        sg_id = self._ensure_security_group()
        if not sg_id:
            self.logger.error("Failed to create/find security group")
            return None
        
        self.security_group_id = sg_id
        
        # Find template and instance type
        template_id = self._find_template()
        instance_type_id = self._find_instance_type()
        
        if not template_id or not instance_type_id:
            self.logger.error("Failed to find template or instance type")
            return None
        
        # Generate cloud-init script
        user_data = self._generate_cloud_init()
        
        # Create instance
        self.logger.info(f"Creating instance '{self.INSTANCE_NAME_TAG}'")
        instance_data = {
            "name": self.INSTANCE_NAME_TAG,
            "instance-type": {"id": instance_type_id},
            "template": {"id": template_id},
            "disk-size": self.disk_size,
            "security-groups": [{"id": sg_id}],
            "user-data": user_data,
        }
        
        result = self._api_request("POST", "/instance", instance_data, timeout=60)
        if not result or "id" not in result:
            self.logger.error("Failed to create instance")
            return None
        
        self.instance_id = result["id"]
        self.logger.info(f"Instance created: {self.instance_id}")
        
        # Wait for instance to be running and get IP
        max_wait = self.INSTANCE_STARTUP_TIMEOUT
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            instance = self._api_request("GET", f"/instance/{self.instance_id}")
            if instance:
                state = instance.get("state")
                if state == "running":
                    # Get public IP
                    public_ip = instance.get("public-ip")
                    if public_ip:
                        self.instance_ip = public_ip
                        self.logger.info(f"Instance running at {public_ip}")
                        
                        # Wait for cloud-init to complete
                        self.logger.info(f"Waiting for cloud-init to complete ({self.CLOUD_INIT_WAIT_TIME}s)")
                        time.sleep(self.CLOUD_INIT_WAIT_TIME)
                        
                        return self.get_ollama_url()
                
                self.logger.debug(f"Instance state: {state}, waiting...")
            
            time.sleep(10)
        
        self.logger.error("Instance failed to start within timeout")
        return None
    
    def ensure_instance(self) -> Optional[str]:
        """Ensure an Ollama instance is running.
        
        Checks for existing instance, starts if stopped, creates if missing.
        
        Returns:
            Ollama URL or None on error
        """
        # Check for existing instance
        instance = self._find_existing_instance()
        
        if instance:
            self.instance_id = instance.get("id")
            state = instance.get("state")
            
            if state == "running":
                self.instance_ip = instance.get("public-ip")
                self.logger.info(f"Found running instance: {self.instance_id} at {self.instance_ip}")
                return self.get_ollama_url()
            elif state == "stopped":
                self.logger.info(f"Found stopped instance {self.instance_id}, starting...")
                # Start the instance
                start_result = self._api_request("PUT", f"/instance/{self.instance_id}:start")
                if start_result:
                    # Wait for it to be running
                    time.sleep(30)
                    instance = self._api_request("GET", f"/instance/{self.instance_id}")
                    if instance and instance.get("state") == "running":
                        self.instance_ip = instance.get("public-ip")
                        return self.get_ollama_url()
        
        # No existing instance, create new one
        self.logger.info("No existing instance found, creating new one")
        return self.create_instance()
    
    def destroy_instance(self) -> bool:
        """Destroy the Ollama instance.
        
        Returns:
            True if successful, False otherwise
        """
        if not self.instance_id:
            self.logger.warning("No instance to destroy")
            return False
        
        self.logger.info(f"Destroying instance {self.instance_id}")
        result = self._api_request("DELETE", f"/instance/{self.instance_id}")
        
        if result is not None:  # 204 No Content returns {}
            self.instance_id = None
            self.instance_ip = None
            self.logger.info("Instance destroyed successfully")
            return True
        
        self.logger.error("Failed to destroy instance")
        return False
    
    def get_instance_status(self) -> Optional[str]:
        """Get the current instance status.
        
        Returns:
            Instance state (running, stopped, etc.) or None
        """
        if not self.instance_id:
            return None
        
        instance = self._api_request("GET", f"/instance/{self.instance_id}")
        if instance:
            return instance.get("state")
        
        return None
    
    def get_ollama_url(self) -> Optional[str]:
        """Get the Ollama API URL for the remote instance.
        
        Returns:
            Full Ollama URL (http://ip:port/api/generate) or None
        """
        if not self.instance_ip:
            return None
        
        return f"http://{self.instance_ip}:{self.NGINX_PROXY_PORT}/api/generate"
    
    def record_activity(self):
        """Record activity timestamp for idle monitoring."""
        with self.activity_lock:
            self.last_activity = time.time()
    
    def _idle_monitor_loop(self):
        """Background thread loop for idle monitoring."""
        while self.idle_monitor_running:
            time.sleep(self.IDLE_CHECK_INTERVAL)
            
            with self.activity_lock:
                idle_time = time.time() - self.last_activity
            
            if idle_time > self.idle_timeout:
                self.logger.info(f"Instance idle for {idle_time:.0f}s, shutting down")
                self.destroy_instance()
                break
    
    def start_idle_monitor(self):
        """Start the idle monitoring thread."""
        if self.idle_monitor_thread and self.idle_monitor_thread.is_alive():
            self.logger.warning("Idle monitor already running")
            return
        
        self.idle_monitor_running = True
        self.idle_monitor_thread = threading.Thread(
            target=self._idle_monitor_loop,
            daemon=True,
            name="ExoscaleIdleMonitor"
        )
        self.idle_monitor_thread.start()
        self.logger.info(f"Idle monitor started (timeout: {self.idle_timeout}s)")
    
    def stop_idle_monitor(self):
        """Stop the idle monitoring thread."""
        if self.idle_monitor_thread:
            self.idle_monitor_running = False
            self.idle_monitor_thread.join(timeout=5)
            self.logger.info("Idle monitor stopped")
    
    def proxy_request(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Proxy a request to the remote Ollama instance.
        
        Adds the X-Ollama-Key header for authentication and forwards the request.
        Records activity for idle monitoring.
        
        Args:
            payload: Ollama API request payload
            
        Returns:
            Response JSON or None on error
        """
        if not self.instance_ip:
            self.logger.error("No instance IP available for proxying")
            return None
        
        url = self.get_ollama_url()
        headers = {"X-Ollama-Key": self.ollama_key}
        
        try:
            self.record_activity()
            resp = requests.post(url, json=payload, headers=headers, timeout=300)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Proxy request failed: {e}")
            return None
    
    def shutdown(self):
        """Shutdown the adapter and cleanup resources.
        
        Called when the webapp exits. Stops idle monitor and destroys instance.
        Protected against duplicate calls from signal handlers and atexit.
        """
        with self._shutdown_lock:
            if self._shutdown_called:
                self.logger.debug("Shutdown already called, skipping")
                return
            self._shutdown_called = True
        
        self.logger.info("Shutting down Exoscale adapter")
        self.stop_idle_monitor()
        if self.instance_id:
            self.destroy_instance()
