"""Port management utilities for GangDan CLI."""

import os
import sys
import socket
import subprocess
import signal
from typing import Optional, Tuple


def is_port_in_use(port: int, host: str = "0.0.0.0") -> bool:
    """Check if a port is already in use."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex((host, port))
            return result == 0
    except Exception:
        return False


def find_process_using_port(port: int) -> Optional[Tuple[int, str]]:
    """Find the PID and process name using the given port.
    
    Returns:
        Tuple of (pid, process_name) or None if not found.
    """
    try:
        if sys.platform == "win32":
            # Windows: use netstat
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                timeout=5
            )
            for line in result.stdout.split("\n"):
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        pid = int(parts[-1])
                        # Get process name
                        try:
                            proc_result = subprocess.run(
                                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                                capture_output=True,
                                text=True,
                                timeout=5
                            )
                            lines = proc_result.stdout.strip().split("\n")
                            if lines:
                                # Parse CSV: "ImageName","PID","SessionName","Session#","MemUsage"
                                name = lines[0].split(",")[0].strip('"')
                                return (pid, name)
                        except Exception:
                            return (pid, f"PID {pid}")
        else:
            # Unix/macOS: use lsof
            result = subprocess.run(
                ["lsof", "-i", f":{port}", "-t", "-sTCP:LISTEN"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                pid = int(result.stdout.strip().split("\n")[0])
                # Get process name
                try:
                    proc_result = subprocess.run(
                        ["ps", "-p", str(pid), "-o", "comm="],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    name = proc_result.stdout.strip() or f"PID {pid}"
                    return (pid, name)
                except Exception:
                    return (pid, f"PID {pid}")
    except Exception as e:
        print(f"[Port] Error finding process: {e}", file=sys.stderr)
    
    return None


def kill_process(pid: int) -> bool:
    """Kill a process by PID.
    
    Returns:
        True if successful, False otherwise.
    """
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        else:
            # Try SIGTERM first, then SIGKILL
            try:
                os.kill(pid, signal.SIGTERM)
                import time
                time.sleep(0.5)
                # Check if still running
                try:
                    os.kill(pid, 0)  # Check if process exists
                    # Still running, use SIGKILL
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass  # Process already terminated
                return True
            except ProcessLookupError:
                return True  # Process already gone
            except PermissionError:
                # Try with sudo prompt
                print(f"[Port] Permission denied. Try: kill -9 {pid}", file=sys.stderr)
                return False
    except Exception as e:
        print(f"[Port] Error killing process: {e}", file=sys.stderr)
        return False


def prompt_kill_process(port: int, pid: int, process_name: str, force: bool = False) -> bool:
    """Prompt user to kill the process using the port.
    
    Args:
        port: The port number.
        pid: The process ID.
        process_name: The process name.
        force: If True, skip prompt and kill automatically.
    
    Returns:
        True if process was killed (or force=True), False if user declined.
    """
    if force:
        print(f"[Port] Force killing {process_name} (PID {pid}) on port {port}...")
        return kill_process(pid)
    
    print(f"\n[Port] Port {port} is in use by: {process_name} (PID {pid})")
    print("[Port] Options:")
    print(f"  [y] Yes - Kill {process_name} and start server")
    print("  [n] No  - Exit without starting server")
    print("  [p] Port - Choose a different port")
    
    try:
        response = input("[Port] Kill process? [y/N/p]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n[Port] Cancelled.")
        return False
    
    if response == 'y' or response == 'yes':
        print(f"[Port] Killing {process_name} (PID {pid})...")
        success = kill_process(pid)
        if success:
            print(f"[Port] Process {pid} terminated.")
        else:
            print(f"[Port] Failed to kill process {pid}.", file=sys.stderr)
        return success
    elif response == 'p':
        return False  # Caller should ask for new port
    
    print("[Port] Declined. Exiting.")
    return False


def resolve_port_conflict(port: int, host: str = "0.0.0.0", force: bool = False) -> Tuple[bool, Optional[int]]:
    """Resolve port conflict by optionally killing the process.
    
    Args:
        port: The desired port.
        host: The host to bind to.
        force: If True, automatically kill the process without prompting.
    
    Returns:
        Tuple of (success, new_port):
        - success: True if port is now available
        - new_port: The port to use (may be different if user chose a new one)
    """
    if not is_port_in_use(port, host):
        return (True, port)
    
    process_info = find_process_using_port(port)
    
    if process_info:
        pid, name = process_info
        
        if force:
            if kill_process(pid):
                print(f"[Port] Killed {name} (PID {pid}) on port {port}")
                import time
                time.sleep(0.5)  # Wait for port to be released
                return (True, port)
            else:
                return (False, None)
        
        # Prompt user
        try:
            response = input(f"\n[Port] Port {port} is used by {name} (PID {pid}). Kill it? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n[Port] Cancelled.")
            return (False, None)
        
        if response in ('y', 'yes'):
            if kill_process(pid):
                print(f"[Port] Killed {name} (PID {pid})")
                import time
                time.sleep(0.5)
                return (True, port)
            else:
                print(f"[Port] Failed to kill process.", file=sys.stderr)
                return (False, None)
        else:
            # Ask for new port
            try:
                new_port_str = input(f"[Port] Enter new port (or press Enter to exit): ").strip()
                if new_port_str:
                    new_port = int(new_port_str)
                    if 1 <= new_port <= 65535:
                        if not is_port_in_use(new_port, host):
                            return (True, new_port)
                        else:
                            print(f"[Port] Port {new_port} is also in use.", file=sys.stderr)
                            return resolve_port_conflict(new_port, host, force)
                    else:
                        print("[Port] Invalid port number.", file=sys.stderr)
            except (ValueError, EOFError, KeyboardInterrupt):
                pass
            
            return (False, None)
    else:
        print(f"[Port] Port {port} is in use but could not identify the process.", file=sys.stderr)
        return (False, None)


def get_available_port(start_port: int = 5000, host: str = "0.0.0.0", max_attempts: int = 100) -> int:
    """Find an available port starting from start_port.
    
    Args:
        start_port: The port to start searching from.
        host: The host to check.
        max_attempts: Maximum number of ports to try.
    
    Returns:
        An available port number.
    """
    for port in range(start_port, start_port + max_attempts):
        if not is_port_in_use(port, host):
            return port
    raise RuntimeError(f"No available port found between {start_port} and {start_port + max_attempts}")