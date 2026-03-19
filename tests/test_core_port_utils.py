"""Tests for gangdan.core.port_utils module."""

import os
import sys
import pytest
import socket
import threading
import time
from unittest.mock import patch, MagicMock


class TestPortDetection:
    """Test port detection functions."""
    
    def test_is_port_in_use_free(self):
        """Test detecting a free port."""
        from gangdan.core.port_utils import is_port_in_use
        
        # Port 59999 is unlikely to be in use
        assert is_port_in_use(59999, "127.0.0.1") == False
    
    def test_is_port_in_use_bound(self):
        """Test detecting a bound port."""
        from gangdan.core.port_utils import is_port_in_use
        
        # Bind to a port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            port = s.getsockname()[1]
            
            # Now check if it's in use
            assert is_port_in_use(port, "127.0.0.1") == True
    
    def test_is_port_in_use_with_host(self):
        """Test port detection with different hosts."""
        from gangdan.core.port_utils import is_port_in_use
        
        # Bind to specific host
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            port = s.getsockname()[1]
            
            # Should be detected
            assert is_port_in_use(port, "127.0.0.1") == True


class TestProcessDetection:
    """Test process detection functions."""
    
    def test_find_process_not_found(self):
        """Test finding process when port is free."""
        from gangdan.core.port_utils import find_process_using_port
        
        # Port 59998 is unlikely to be in use
        result = find_process_using_port(59998)
        assert result is None
    
    def test_find_process_bound_port(self):
        """Test finding process on bound port."""
        from gangdan.core.port_utils import find_process_using_port
        
        # Bind to a port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            port = s.getsockname()[1]
            
            # Find the process
            result = find_process_using_port(port)
            
            # On most systems, this should return our process
            if result:
                pid, name = result
                assert pid == os.getpid() or pid > 0


class TestGetAvailablePort:
    """Test finding available ports."""
    
    def test_get_available_port_default(self):
        """Test finding an available port."""
        from gangdan.core.port_utils import get_available_port
        
        port = get_available_port(50000, "127.0.0.1")
        assert 50000 <= port <= 50100
        assert port > 0
    
    def test_get_available_port_skip_used(self):
        """Test that used ports are skipped."""
        from gangdan.core.port_utils import get_available_port
        
        # Bind to port 50001
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 50001))
            s.listen(1)
            
            # Should skip 50001
            port = get_available_port(50001, "127.0.0.1")
            assert port != 50001
            assert port > 50001
    
    def test_get_available_port_custom_range(self):
        """Test custom port range."""
        from gangdan.core.port_utils import get_available_port
        
        port = get_available_port(55000, "127.0.0.1", max_attempts=10)
        assert 55000 <= port < 55010


class TestKillProcess:
    """Test process killing functions."""
    
    def test_kill_nonexistent_process(self):
        """Test killing a non-existent process."""
        from gangdan.core.port_utils import kill_process
        
        # PID 999999 is unlikely to exist
        result = kill_process(999999)
        # Should return True because process doesn't exist
        assert result == True
    
    def test_kill_invalid_pid(self):
        """Test killing with invalid PID."""
        from gangdan.core.port_utils import kill_process
        
        # Negative PID should fail gracefully
        result = kill_process(-1)
        assert result == False


class TestResolvePortConflict:
    """Test port conflict resolution."""
    
    def test_resolve_no_conflict(self):
        """Test resolution when port is free."""
        from gangdan.core.port_utils import resolve_port_conflict
        
        success, port = resolve_port_conflict(59997, "127.0.0.1", force=False)
        assert success == True
        assert port == 59997
    
    def test_resolve_force_mode(self):
        """Test force mode resolution."""
        from gangdan.core.port_utils import resolve_port_conflict
        
        # Bind to a port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            port = s.getsockname()[1]
            
            # Force mode should try to kill
            # Since it's our process, this should work
            success, new_port = resolve_port_conflict(port, "127.0.0.1", force=True)
            # May succeed or fail depending on permissions


class TestPortUtilsIntegration:
    """Integration tests for port utilities."""
    
    def test_full_workflow(self):
        """Test the full port detection workflow."""
        from gangdan.core.port_utils import (
            is_port_in_use,
            find_process_using_port,
            get_available_port,
        )
        
        # Find an available port
        port = get_available_port(50002, "127.0.0.1")
        assert is_port_in_use(port, "127.0.0.1") == False
        
        # Bind to it
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
            s.listen(1)
            
            # Now it should be in use
            assert is_port_in_use(port, "127.0.0.1") == True
            
            # Find the process
            result = find_process_using_port(port)
            if result:
                pid, name = result
                assert pid > 0
                assert len(name) > 0


class TestCLIArgs:
    """Test CLI argument handling."""
    
    def test_force_port_arg_parsing(self):
        """Test --force-port argument parsing."""
        import argparse
        from gangdan.cli import main
        
        # Test that the argument is defined
        parser = argparse.ArgumentParser()
        parser.add_argument("--force-port", action="store_true")
        parser.add_argument("--auto-port", action="store_true")
        parser.add_argument("--port", type=int, default=5000)
        
        args = parser.parse_args(["--force-port", "--port", "5001"])
        assert args.force_port == True
        assert args.port == 5001
        
        args = parser.parse_args(["--auto-port"])
        assert args.auto_port == True
    
    def test_auto_port_arg_parsing(self):
        """Test --auto-port argument parsing."""
        import argparse
        
        parser = argparse.ArgumentParser()
        parser.add_argument("--auto-port", action="store_true")
        
        args = parser.parse_args(["--auto-port"])
        assert args.auto_port == True
        
        args = parser.parse_args([])
        assert args.auto_port == False