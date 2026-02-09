"""Exoscale Ollama Adapter - Remote Ollama instance management using python-exoscale SDK.

This module manages the lifecycle of Ollama instances on Exoscale cloud:
- Create/start/stop/destroy compute instances
- Configure security groups for secure access
- Set up Docker container with Ollama on instance via cloud-init
- Monitor idle time and auto-shutdown to save costs
- Provide remote URL for proxying requests

Uses the official python-exoscale v2 API client:
https://exoscale.github.io/python-exoscale/
"""

import base64
import logging
import os
import threading
import time
from typing import Any, Dict, Optional

from exoscale.api.v2 import Client


class ExoscaleAuthError(Exception):
    """Raised when Exoscale API returns authentication/authorization errors."""
    pass


class ExoscaleOllamaAdapter:
    """Adapter for managing remote Ollama instances on Exoscale cloud using python-exoscale SDK.
    
    Features:
    - Automatic instance lifecycle management
    - Security group and firewall configuration
    - Ollama Docker container setup via cloud-init
    - Idle monitoring with auto-shutdown
    - Remote URL provider for proxy
    """
    
    SECURITY_GROUP_NAME = "garuda-ollama-sg"
    INSTANCE_NAME = "garuda-ollama"
    OLLAMA_PORT = 11434
    INSTANCE_STARTUP_TIMEOUT = 300  # Maximum wait time for instance to start (seconds)
    CLOUD_INIT_WAIT_TIME = 60  # Wait time for cloud-init to complete (seconds)
    IDLE_CHECK_INTERVAL = 60  # How often to check for idle timeout (seconds)
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        zone: Optional[str] = None,
        instance_type: Optional[str] = None,
        template_name: Optional[str] = None,
        disk_size: Optional[int] = None,
        ollama_model: Optional[str] = None,
        idle_timeout: Optional[int] = None,
    ):
        """Initialize Exoscale Ollama adapter.
        
        Args:
            api_key: Exoscale API key (defaults to EXOSCALE_API_KEY env var)
            api_secret: Exoscale API secret (defaults to EXOSCALE_API_SECRET env var)
            zone: Exoscale zone (defaults to EXOSCALE_ZONE env var or 'at-vie-2')
            instance_type: Instance type (defaults to EXOSCALE_INSTANCE_TYPE env var or 'a5000.small')
            template_name: OS template name (defaults to EXOSCALE_TEMPLATE env var)
            disk_size: Root disk size in GB (defaults to EXOSCALE_DISK_SIZE env var or 50)
            ollama_model: Ollama model to pull on startup (defaults to OLLAMA_MODEL env var)
            idle_timeout: Seconds of inactivity before auto-shutdown (defaults to EXOSCALE_IDLE_TIMEOUT or 1800)
        """
        self.api_key = api_key or os.getenv("EXOSCALE_API_KEY", "")
        self.api_secret = api_secret or os.getenv("EXOSCALE_API_SECRET", "")
        self.zone_name = zone or os.getenv("EXOSCALE_ZONE", "at-vie-2")
        self.instance_type = instance_type or os.getenv("EXOSCALE_INSTANCE_TYPE", "a5000.small")
        self.template_name = template_name or os.getenv(
            "EXOSCALE_TEMPLATE", "Linux Ubuntu 22.04 LTS 64-bit"
        )
        
        if disk_size is not None:
            self.disk_size = disk_size
        else:
            try:
                self.disk_size = int(os.getenv("EXOSCALE_DISK_SIZE", "50"))
            except ValueError as e:
                raise ValueError(
                    f"EXOSCALE_DISK_SIZE must be a valid integer, "
                    f"got: {os.getenv('EXOSCALE_DISK_SIZE')}"
                ) from e
        
        self.ollama_model = ollama_model or os.getenv("OLLAMA_MODEL", "granite3.1-dense:8b")
        
        if idle_timeout is not None:
            self.idle_timeout = idle_timeout
        else:
            try:
                self.idle_timeout = int(os.getenv("EXOSCALE_IDLE_TIMEOUT", "1800"))
            except ValueError as e:
                raise ValueError(
                    f"EXOSCALE_IDLE_TIMEOUT must be a valid integer, "
                    f"got: {os.getenv('EXOSCALE_IDLE_TIMEOUT')}"
                ) from e
        
        self.logger = logging.getLogger(__name__)
        
        # Validate credentials
        if not self.api_key or not self.api_secret:
            raise ExoscaleAuthError(
                "Exoscale API credentials not provided. "
                "Set EXOSCALE_API_KEY and EXOSCALE_API_SECRET environment variables."
            )
        
        # Initialize Exoscale v2 API client with zone
        try:
            self.client = Client(
                key=self.api_key,
                secret=self.api_secret,
                zone=self.zone_name,
            )
        except Exception as e:
            self.logger.error(f"Failed to initialize Exoscale client: {e}")
            raise ExoscaleAuthError(f"Failed to initialize Exoscale client: {e}") from e
        
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
    
    def _find_template_id(self) -> Optional[str]:
        """Find the template ID by name.
        
        Returns:
            Template ID or None if not found
        """
        try:
            result = self.client.list_templates(visibility="public")
            templates = result.get("templates", [])
            for template in templates:
                if template.get("name") == self.template_name:
                    return template.get("id")
        except Exception as e:
            self.logger.error(f"Failed to list templates: {e}")
        
        self.logger.warning(f"Template '{self.template_name}' not found")
        return None
    
    def _find_instance_type_id(self) -> Optional[str]:
        """Find the instance type ID by name.
        
        Returns:
            Instance type ID or None if not found
        """
        try:
            result = self.client.list_instance_types()
            instance_types = result.get("instance-types", [])
            for itype in instance_types:
                if itype.get("name") == self.instance_type:
                    return itype.get("id")
        except Exception as e:
            self.logger.error(f"Failed to list instance types: {e}")
        
        self.logger.warning(f"Instance type '{self.instance_type}' not found")
        return None
    
    def _ensure_security_group(self) -> Optional[str]:
        """Ensure security group exists with proper rules.
        
        Creates a security group allowing inbound traffic on port 11434 (Ollama).
        
        Returns:
            Security group ID or None on error
        """
        # Check if security group already exists
        try:
            result = self.client.list_security_groups()
            for sg in result.get("security-groups", []):
                if sg.get("name") == self.SECURITY_GROUP_NAME:
                    sg_id = sg.get("id")
                    self.logger.info(f"Found existing security group: {sg_id}")
                    self.security_group_id = sg_id
                    return sg_id
        except Exception as e:
            self.logger.warning(f"Error listing security groups: {e}")
        
        # Create new security group
        try:
            self.logger.info(f"Creating security group '{self.SECURITY_GROUP_NAME}'")
            op = self.client.create_security_group(
                name=self.SECURITY_GROUP_NAME,
                description="Security group for Garuda Ollama instances",
            )
            self.client.wait(op["id"])
            
            # Get the created security group ID from the operation reference
            sg_id = op.get("reference", {}).get("id")
            if not sg_id:
                # Fallback: list security groups to find it
                result = self.client.list_security_groups()
                for sg in result.get("security-groups", []):
                    if sg.get("name") == self.SECURITY_GROUP_NAME:
                        sg_id = sg.get("id")
                        break
            
            if not sg_id:
                self.logger.error("Failed to get security group ID after creation")
                return None
            
            # Add rule to allow inbound traffic on Ollama port
            rule_op = self.client.add_rule_to_security_group(
                id=sg_id,
                flow_direction="ingress",
                protocol="tcp",
                start_port=self.OLLAMA_PORT,
                end_port=self.OLLAMA_PORT,
                network="0.0.0.0/0",
                description="Allow Ollama access",
            )
            self.client.wait(rule_op["id"])
            
            self.logger.info(f"Security group created: {sg_id}")
            self.security_group_id = sg_id
            return sg_id
        except Exception as e:
            self.logger.error(f"Failed to create security group: {e}")
            return None
    
    def _generate_cloud_init(self) -> str:
        """Generate cloud-init user-data script.
        
        The script:
        - Installs Docker
        - Runs ollama/ollama container exposed on 0.0.0.0:11434
        - Pulls the configured Ollama model
        
        Returns:
            Base64-encoded cloud-init script
        """
        script = f"""#!/bin/bash
set -e

# Update system
apt-get update
apt-get install -y ca-certificates curl gnupg

# Install Docker
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io

# Start Ollama container on all interfaces
docker run -d --name ollama -p 0.0.0.0:{self.OLLAMA_PORT}:{self.OLLAMA_PORT} ollama/ollama:latest

# Wait for Ollama to be ready
sleep 10

# Pull the model
docker exec ollama ollama pull {self.ollama_model}

echo "Garuda Ollama setup complete"
"""
        
        return base64.b64encode(script.encode()).decode()
    
    def _find_existing_instance(self) -> Optional[Dict[str, Any]]:
        """Find existing Garuda Ollama instance by name.
        
        Returns:
            Instance dict or None if not found
        """
        try:
            result = self.client.list_instances()
            for instance in result.get("instances", []):
                if instance.get("name") == self.INSTANCE_NAME:
                    return instance
        except Exception as e:
            self.logger.warning(f"Error listing instances: {e}")
        
        return None
    
    def create_instance(self) -> Optional[str]:
        """Create a new Exoscale compute instance with Ollama.
        
        Returns:
            Remote Ollama base URL (http://ip:port) or None on error
        """
        # Ensure security group exists
        sg_id = self._ensure_security_group()
        if not sg_id:
            self.logger.error("Failed to create/find security group")
            return None
        
        # Find template and instance type IDs
        template_id = self._find_template_id()
        instance_type_id = self._find_instance_type_id()
        
        if not template_id or not instance_type_id:
            self.logger.error("Failed to find template or instance type")
            return None
        
        # Generate cloud-init script
        user_data = self._generate_cloud_init()
        
        # Create instance
        try:
            self.logger.info(f"Creating instance '{self.INSTANCE_NAME}'")
            op = self.client.create_instance(
                name=self.INSTANCE_NAME,
                instance_type={"id": instance_type_id},
                template={"id": template_id},
                disk_size=self.disk_size,
                security_groups=[{"id": sg_id}],
                user_data=user_data,
            )
            self.client.wait(op["id"])
            
            # Get instance ID from operation reference
            self.instance_id = op.get("reference", {}).get("id")
            if not self.instance_id:
                self.logger.error("Failed to get instance ID from operation")
                return None
            
            self.logger.info(f"Instance created: {self.instance_id}")
        except Exception as e:
            self.logger.error(f"Failed to create instance: {e}")
            return None
        
        # Wait for instance to be running and get public IP
        max_wait = self.INSTANCE_STARTUP_TIMEOUT
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            try:
                instance = self.client.get_instance(id=self.instance_id)
                state = instance.get("state")
                
                if state == "running":
                    public_ip = instance.get("public_ip")
                    if public_ip:
                        self.instance_ip = public_ip
                        self.logger.info(f"Instance running at {public_ip}")
                        
                        # Wait for cloud-init to complete
                        self.logger.info(
                            f"Waiting for cloud-init ({self.CLOUD_INIT_WAIT_TIME}s)"
                        )
                        time.sleep(self.CLOUD_INIT_WAIT_TIME)
                        
                        return self.get_remote_url()
                
                self.logger.debug(f"Instance state: {state}, waiting...")
            except Exception as e:
                self.logger.warning(f"Error checking instance state: {e}")
            
            time.sleep(10)
        
        self.logger.error("Instance failed to start within timeout")
        return None
    
    def ensure_instance(self) -> Optional[str]:
        """Ensure an Ollama instance is running.
        
        Checks for existing instance, starts if stopped, creates if missing.
        
        Returns:
            Remote Ollama base URL (http://ip:port) or None on error
        """
        # Check for existing instance
        instance = self._find_existing_instance()
        
        if instance:
            self.instance_id = instance.get("id")
            state = instance.get("state")
            
            if state == "running":
                self.instance_ip = instance.get("public_ip")
                self.logger.info(
                    f"Found running instance: {self.instance_id} at {self.instance_ip}"
                )
                return self.get_remote_url()
            elif state == "stopped":
                self.logger.info(f"Found stopped instance {self.instance_id}, starting...")
                try:
                    op = self.client.start_instance(id=self.instance_id)
                    self.client.wait(op["id"])
                    
                    # Wait and get updated instance info
                    time.sleep(10)
                    instance = self.client.get_instance(id=self.instance_id)
                    if instance.get("state") == "running":
                        self.instance_ip = instance.get("public_ip")
                        return self.get_remote_url()
                except Exception as e:
                    self.logger.error(f"Failed to start instance: {e}")
        
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
        
        try:
            self.logger.info(f"Destroying instance {self.instance_id}")
            op = self.client.delete_instance(id=self.instance_id)
            self.client.wait(op["id"])
            self.instance_id = None
            self.instance_ip = None
            self.logger.info("Instance destroyed successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to destroy instance: {e}")
            return False
    
    def get_instance_status(self) -> Optional[str]:
        """Get the current instance status.
        
        Returns:
            Instance state (running, stopped, etc.) or None
        """
        if not self.instance_id:
            return None
        
        try:
            instance = self.client.get_instance(id=self.instance_id)
            return instance.get("state")
        except Exception as e:
            self.logger.warning(f"Error getting instance status: {e}")
        
        return None
    
    def get_remote_url(self) -> Optional[str]:
        """Get the base URL for the remote Ollama instance.
        
        Returns:
            Base URL (http://ip:port) or None
        """
        if not self.instance_ip:
            return None
        
        return f"http://{self.instance_ip}:{self.OLLAMA_PORT}"
    
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
    
    def shutdown(self):
        """Shutdown the adapter and cleanup resources.
        
        Stops idle monitor and destroys instance.
        Protected against duplicate calls.
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
