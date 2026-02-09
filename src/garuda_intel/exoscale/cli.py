"""Exoscale Ollama CLI - Manage remote Ollama instances.

This CLI provides commands to manage Exoscale Ollama instances:
- status: Show instance status
- start: Manually start/create instance
- stop: Manually stop/destroy instance
- logs: Show instance information
"""

import argparse
import logging
import os
import sys
from typing import Optional

from .adapter import ExoscaleOllamaAdapter


def get_adapter_from_env() -> Optional[ExoscaleOllamaAdapter]:
    """Create adapter from environment variables.
    
    Returns:
        ExoscaleOllamaAdapter instance or None if required vars missing
    """
    api_key = os.environ.get("EXOSCALE_API_KEY")
    api_secret = os.environ.get("EXOSCALE_API_SECRET")
    
    if not api_key or not api_secret:
        print("Error: EXOSCALE_API_KEY and EXOSCALE_API_SECRET must be set")
        return None
    
    zone = os.environ.get("EXOSCALE_ZONE", "at-vie-2")
    instance_type = os.environ.get("EXOSCALE_INSTANCE_TYPE", "a5000.small")
    template = os.environ.get("EXOSCALE_TEMPLATE", "Linux Ubuntu 22.04 LTS 64-bit")
    disk_size = int(os.environ.get("EXOSCALE_DISK_SIZE", "50"))
    ollama_model = os.environ.get("EXOSCALE_OLLAMA_MODEL") or os.environ.get("GARUDA_OLLAMA_MODEL", "granite3.1-dense:8b")
    ollama_key = os.environ.get("EXOSCALE_OLLAMA_KEY")
    idle_timeout = int(os.environ.get("EXOSCALE_IDLE_TIMEOUT", "1800"))
    
    return ExoscaleOllamaAdapter(
        api_key=api_key,
        api_secret=api_secret,
        zone=zone,
        instance_type=instance_type,
        template_name=template,
        disk_size=disk_size,
        ollama_model=ollama_model,
        ollama_key=ollama_key,
        idle_timeout=idle_timeout,
    )


def cmd_status(args):
    """Show Exoscale Ollama instance status."""
    adapter = get_adapter_from_env()
    if not adapter:
        return 1
    
    # Check for existing instance
    instance = adapter._find_existing_instance()
    
    if not instance:
        print("Status: No instance found")
        print(f"Instance name: {adapter.INSTANCE_NAME_TAG}")
        return 0
    
    instance_id = instance.get("id")
    state = instance.get("state")
    public_ip = instance.get("public-ip")
    instance_type = instance.get("instance-type", {}).get("name", "unknown")
    
    print(f"Status: {state}")
    print(f"Instance ID: {instance_id}")
    print(f"Instance type: {instance_type}")
    print(f"Public IP: {public_ip or 'N/A'}")
    print(f"Zone: {adapter.zone}")
    
    if state == "running" and public_ip:
        ollama_url = f"http://{public_ip}:{adapter.NGINX_PROXY_PORT}/api/generate"
        print(f"Ollama URL: {ollama_url}")
    
    return 0


def cmd_start(args):
    """Manually start or create Exoscale Ollama instance."""
    adapter = get_adapter_from_env()
    if not adapter:
        return 1
    
    print("Starting Exoscale Ollama instance...")
    ollama_url = adapter.ensure_instance()
    
    if ollama_url:
        print(f"✓ Instance ready")
        print(f"Ollama URL: {ollama_url}")
        print(f"API Key: {adapter.ollama_key}")
        print("\nSet these environment variables to use:")
        print(f"export GARUDA_OLLAMA_URL='{ollama_url}'")
        print(f"export EXOSCALE_OLLAMA_KEY='{adapter.ollama_key}'")
        return 0
    else:
        print("✗ Failed to start instance")
        return 1


def cmd_stop(args):
    """Manually stop/destroy Exoscale Ollama instance."""
    adapter = get_adapter_from_env()
    if not adapter:
        return 1
    
    # Find instance first
    instance = adapter._find_existing_instance()
    if not instance:
        print("No instance found to stop")
        return 0
    
    adapter.instance_id = instance.get("id")
    
    print(f"Stopping instance {adapter.instance_id}...")
    if adapter.destroy_instance():
        print("✓ Instance destroyed")
        return 0
    else:
        print("✗ Failed to destroy instance")
        return 1


def cmd_logs(args):
    """Show detailed instance information."""
    adapter = get_adapter_from_env()
    if not adapter:
        return 1
    
    instance = adapter._find_existing_instance()
    
    if not instance:
        print("No instance found")
        return 0
    
    print("=== Exoscale Ollama Instance ===")
    print(f"ID: {instance.get('id')}")
    print(f"Name: {instance.get('name')}")
    print(f"State: {instance.get('state')}")
    print(f"Zone: {instance.get('zone', {}).get('name')}")
    print(f"Type: {instance.get('instance-type', {}).get('name')}")
    print(f"Template: {instance.get('template', {}).get('name')}")
    print(f"Disk size: {instance.get('disk-size')} GB")
    print(f"Public IP: {instance.get('public-ip')}")
    print(f"IPv6: {instance.get('ipv6-address')}")
    print(f"Created: {instance.get('created-at')}")
    
    # Security groups
    security_groups = instance.get('security-groups', [])
    if security_groups:
        print("\nSecurity groups:")
        for sg in security_groups:
            print(f"  - {sg.get('name')} ({sg.get('id')})")
    
    return 0


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Manage Exoscale Ollama instances",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment variables:
  EXOSCALE_API_KEY          Exoscale API key (required)
  EXOSCALE_API_SECRET       Exoscale API secret (required)
  EXOSCALE_ZONE             Exoscale zone (default: ch-gva-2)
  EXOSCALE_INSTANCE_TYPE    Instance type (default: standard.medium)
  EXOSCALE_TEMPLATE         OS template (default: Linux Ubuntu 22.04 LTS 64-bit)
  EXOSCALE_DISK_SIZE        Disk size in GB (default: 50)
  EXOSCALE_OLLAMA_KEY       API key for Ollama proxy (auto-generated if not set)
  EXOSCALE_IDLE_TIMEOUT     Idle timeout in seconds (default: 1800)
  GARUDA_OLLAMA_MODEL       Ollama model to use (default: granite3.1-dense:8b)

Examples:
  garuda-exoscale status
  garuda-exoscale start
  garuda-exoscale stop
  garuda-exoscale logs
        """
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    subparsers.add_parser("status", help="Show instance status")
    subparsers.add_parser("start", help="Start or create instance")
    subparsers.add_parser("stop", help="Stop/destroy instance")
    subparsers.add_parser("logs", help="Show detailed instance information")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Execute command
    commands = {
        "status": cmd_status,
        "start": cmd_start,
        "stop": cmd_stop,
        "logs": cmd_logs,
    }
    
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
