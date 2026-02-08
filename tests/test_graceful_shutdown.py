"""Tests for graceful shutdown functionality."""

import sys
import os
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from garuda_intel.webapp.utils.shutdown import ShutdownManager


def test_shutdown_manager_initialization():
    """Test ShutdownManager initializes with correct state."""
    print("\n=== Test: ShutdownManager initialization ===")
    
    shutdown_mgr = ShutdownManager()
    
    assert not shutdown_mgr.is_shutting_down()
    print("✓ ShutdownManager initialized with shutdown=False")


def test_shutdown_manager_request_shutdown():
    """Test ShutdownManager tracks shutdown state correctly."""
    print("\n=== Test: ShutdownManager request_shutdown ===")
    
    shutdown_mgr = ShutdownManager()
    
    assert not shutdown_mgr.is_shutting_down()
    print("✓ Initially not shutting down")
    
    shutdown_mgr.request_shutdown()
    
    assert shutdown_mgr.is_shutting_down()
    print("✓ After request_shutdown, is_shutting_down returns True")
    
    # Calling again should be idempotent
    shutdown_mgr.request_shutdown()
    assert shutdown_mgr.is_shutting_down()
    print("✓ Multiple request_shutdown calls are idempotent")


def test_shutdown_manager_thread_safety():
    """Test ShutdownManager is thread-safe."""
    print("\n=== Test: ShutdownManager thread safety ===")
    
    shutdown_mgr = ShutdownManager()
    results = []
    
    def check_shutdown():
        for _ in range(100):
            results.append(shutdown_mgr.is_shutting_down())
    
    def request_shutdown():
        shutdown_mgr.request_shutdown()
    
    # Start multiple threads checking and requesting shutdown
    threads = []
    for _ in range(5):
        t = threading.Thread(target=check_shutdown)
        threads.append(t)
        t.start()
    
    shutdown_thread = threading.Thread(target=request_shutdown)
    shutdown_thread.start()
    
    for t in threads:
        t.join()
    shutdown_thread.join()
    
    # After all threads finish, should be shutting down
    assert shutdown_mgr.is_shutting_down()
    print("✓ ShutdownManager is thread-safe")


def test_shutdown_manager_in_flask_app():
    """Test ShutdownManager integration concept with dict config."""
    print("\n=== Test: ShutdownManager in config dict ===")
    
    shutdown_mgr = ShutdownManager()
    
    # Simulate Flask app.config dictionary
    app_config = {}
    app_config['shutdown_manager'] = shutdown_mgr
    
    assert 'shutdown_manager' in app_config
    assert isinstance(app_config['shutdown_manager'], ShutdownManager)
    print("✓ ShutdownManager can be stored in config dict")
    
    retrieved_mgr = app_config.get('shutdown_manager')
    assert retrieved_mgr is shutdown_mgr
    assert not retrieved_mgr.is_shutting_down()
    print("✓ ShutdownManager can be retrieved from config dict")
    
    retrieved_mgr.request_shutdown()
    assert app_config['shutdown_manager'].is_shutting_down()
    print("✓ ShutdownManager state changes reflected in config dict")


if __name__ == "__main__":
    test_shutdown_manager_initialization()
    test_shutdown_manager_request_shutdown()
    test_shutdown_manager_thread_safety()
    test_shutdown_manager_in_flask_app()
    print("\n✅ All graceful shutdown tests passed!")
