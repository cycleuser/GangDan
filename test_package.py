#!/usr/bin/env python3
"""
GangDan Comprehensive Test Script
===================================
Tests every phase of the package lifecycle:

  Phase 1 - Source integrity checks
  Phase 2 - Import & module tests
  Phase 3 - CLI interface tests
  Phase 4 - Dev server startup & HTTP tests
  Phase 5 - Package build tests
  Phase 6 - Wheel contents verification
  Phase 7 - Clean venv install & run tests

Usage:
    python test_package.py              # Run all tests
    python test_package.py --phase 1    # Run specific phase (1-7)
    python test_package.py --skip-venv  # Skip Phase 7 (needs python3-venv)
"""

import argparse
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACKAGE_DIR = ROOT / "gangdan"
DIST_DIR = ROOT / "dist"

# ── helpers ──────────────────────────────────────────────────────────────────

class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

PASS_COUNT = 0
FAIL_COUNT = 0
SKIP_COUNT = 0


def header(title: str):
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'=' * 64}")
    print(f"  {title}")
    print(f"{'=' * 64}{Colors.RESET}\n")


def check(description: str, condition: bool, detail: str = ""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"  {Colors.GREEN}PASS{Colors.RESET}  {description}")
    else:
        FAIL_COUNT += 1
        msg = f"  {Colors.RED}FAIL{Colors.RESET}  {description}"
        if detail:
            msg += f"  -- {detail}"
        print(msg)
    return condition


def skip(description: str, reason: str = ""):
    global SKIP_COUNT
    SKIP_COUNT += 1
    msg = f"  {Colors.YELLOW}SKIP{Colors.RESET}  {description}"
    if reason:
        msg += f"  -- {reason}"
    print(msg)


def run_cmd(cmd: str, timeout: int = 60, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        timeout=timeout, cwd=cwd or ROOT,
    )


def wait_for_server(host: str, port: int, timeout: int = 15) -> bool:
    """Poll until the server responds or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            conn = http.client.HTTPConnection(host, port, timeout=2)
            conn.request("GET", "/")
            resp = conn.getresponse()
            conn.close()
            if resp.status in (200, 302):
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def http_get(host: str, port: int, path: str, timeout: int = 5) -> tuple:
    """Return (status_code, body) for a GET request."""
    try:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", errors="replace")
        status = resp.status
        conn.close()
        return status, body
    except Exception as e:
        return 0, str(e)


def http_post_json(host: str, port: int, path: str, data: dict) -> tuple:
    """Return (status_code, body) for a POST JSON request."""
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        payload = json.dumps(data)
        conn.request("POST", path, body=payload,
                      headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", errors="replace")
        status = resp.status
        conn.close()
        return status, body
    except Exception as e:
        return 0, str(e)


def start_server(cmd: str, port: int, env=None, cwd=None) -> subprocess.Popen:
    """Start a server process and wait for it to be ready."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    proc = subprocess.Popen(
        cmd, shell=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=full_env, cwd=cwd or ROOT,
    )
    return proc


def stop_server(proc: subprocess.Popen):
    """Terminate a server process."""
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def ensure_port_free(port: int):
    """Kill any process listening on the given port."""
    try:
        r = subprocess.run(
            f"lsof -ti :{port}", shell=True, capture_output=True, text=True,
        )
        if r.stdout.strip():
            for pid in r.stdout.strip().split():
                subprocess.run(f"kill {pid}", shell=True)
            time.sleep(1)
    except Exception:
        pass


# ── Phase 1: Source integrity ────────────────────────────────────────────────

def phase1_source_integrity():
    header("Phase 1: Source Integrity Checks")

    # Required package files
    required_files = [
        PACKAGE_DIR / "__init__.py",
        PACKAGE_DIR / "__main__.py",
        PACKAGE_DIR / "cli.py",
        PACKAGE_DIR / "app.py",
        PACKAGE_DIR / "templates" / "index.html",
        PACKAGE_DIR / "static" / "css" / "style.css",
    ]
    for f in required_files:
        check(f"Package file exists: {f.relative_to(ROOT)}", f.exists())

    # JS files
    js_dir = PACKAGE_DIR / "static" / "js"
    expected_js = {"chat.js", "docs.js", "i18n.js", "markdown.js",
                   "settings.js", "terminal.js", "utils.js"}
    actual_js = {f.name for f in js_dir.glob("*.js")} if js_dir.exists() else set()
    check(f"All 7 JS files present", expected_js == actual_js,
          f"missing: {expected_js - actual_js}" if expected_js != actual_js else "")

    # Root packaging files
    for name in ["pyproject.toml", "MANIFEST.in", "LICENSE", "README.md"]:
        check(f"Root file exists: {name}", (ROOT / name).exists())

    # pyproject.toml content
    toml_text = (ROOT / "pyproject.toml").read_text()
    check("pyproject.toml has entry point",
          'gangdan = "gangdan.cli:main"' in toml_text)
    check("pyproject.toml has dependencies",
          "flask>=" in toml_text and "chromadb>=" in toml_text)
    check("pyproject.toml has package-data for templates",
          "templates" in toml_text)
    check("pyproject.toml has package-data for static",
          "static" in toml_text)

    # __init__.py has version
    init_text = (PACKAGE_DIR / "__init__.py").read_text()
    check("__init__.py defines __version__", "__version__" in init_text)

    # app.py uses _get_data_dir
    app_text = (PACKAGE_DIR / "app.py").read_text()
    check("app.py uses _get_data_dir() for DATA_DIR",
          "def _get_data_dir" in app_text and "DATA_DIR = _get_data_dir()" in app_text)
    check("app.py supports GANGDAN_DATA_DIR env var",
          "GANGDAN_DATA_DIR" in app_text)
    check("app.py detects site-packages for install mode",
          "site-packages" in app_text)

    # No old root app.py
    check("Old root app.py removed", not (ROOT / "app.py").exists())
    check("Old root templates/ removed", not (ROOT / "templates").exists())
    check("Old root static/ removed", not (ROOT / "static").exists())


# ── Phase 2: Import & module tests ──────────────────────────────────────────

def phase2_import_tests():
    header("Phase 2: Import & Module Tests")

    # Test import gangdan
    r = run_cmd(f'{sys.executable} -c "import gangdan; print(gangdan.__version__)"')
    check("import gangdan succeeds", r.returncode == 0, r.stderr.strip()[:120])
    if r.returncode == 0:
        ver = r.stdout.strip()
        check(f"gangdan.__version__ is set (got '{ver}')", len(ver) > 0)

    # Test import gangdan.cli
    r = run_cmd(f'{sys.executable} -c "from gangdan.cli import main; print(\'OK\')"')
    check("import gangdan.cli.main succeeds", r.returncode == 0,
          r.stderr.strip()[:120])

    # Test import gangdan.app (this triggers full init including ChromaDB)
    r = run_cmd(
        f'{sys.executable} -c "from gangdan.app import app; print(type(app).__name__)"',
        timeout=30,
    )
    check("import gangdan.app succeeds", r.returncode == 0,
          r.stderr.strip()[:120])
    if r.returncode == 0:
        check("app object is Flask instance",
              "Flask" in r.stdout.strip())

    # Test data dir detection: when running from source should be ./data
    r = run_cmd(
        f'{sys.executable} -c "'
        f'from gangdan.app import DATA_DIR; print(DATA_DIR)"'
    )
    if r.returncode == 0:
        check("DATA_DIR resolves (from source = ./data)",
              "data" in r.stdout.strip().lower())

    # Test GANGDAN_DATA_DIR env override
    r = run_cmd(
        f'GANGDAN_DATA_DIR=/tmp/gangdan_test_xyzzy {sys.executable} -c "'
        f'from gangdan.app import DATA_DIR; print(DATA_DIR)"'
    )
    if r.returncode == 0:
        check("GANGDAN_DATA_DIR env override works",
              "gangdan_test_xyzzy" in r.stdout.strip())
    else:
        check("GANGDAN_DATA_DIR env override works", False, r.stderr.strip()[:120])


# ── Phase 3: CLI tests ──────────────────────────────────────────────────────

def phase3_cli_tests():
    header("Phase 3: CLI Interface Tests")

    # --version via module
    r = run_cmd(f"{sys.executable} -m gangdan --version")
    check("python -m gangdan --version exits 0", r.returncode == 0)
    if r.returncode == 0:
        check("--version outputs version string",
              "gangdan" in r.stdout.lower() and any(c.isdigit() for c in r.stdout))

    # --help via module
    r = run_cmd(f"{sys.executable} -m gangdan --help")
    check("python -m gangdan --help exits 0", r.returncode == 0)
    if r.returncode == 0:
        out = r.stdout.lower()
        check("--help shows --host option", "--host" in out)
        check("--help shows --port option", "--port" in out)
        check("--help shows --debug option", "--debug" in out)
        check("--help shows --data-dir option", "--data-dir" in out)
        check("--help shows --version option", "--version" in out)

    # gangdan CLI entry point (if installed)
    r = run_cmd("gangdan --version 2>&1", timeout=10)
    if r.returncode == 0:
        check("gangdan CLI entry point works", True)
    else:
        skip("gangdan CLI entry point", "not in PATH (not installed or PATH issue)")

    # Invalid argument
    r = run_cmd(f"{sys.executable} -m gangdan --nonexistent 2>&1")
    check("Invalid argument returns non-zero exit code", r.returncode != 0)


# ── Phase 4: Dev server & HTTP tests ────────────────────────────────────────

def phase4_server_tests():
    header("Phase 4: Dev Server Startup & HTTP Tests")

    port = 15234
    data_dir = tempfile.mkdtemp(prefix="gangdan_test_")
    proc = None

    try:
        ensure_port_free(port)
        # Start server
        cmd = (f"{sys.executable} -m gangdan --port {port} --host 127.0.0.1")
        proc = start_server(cmd, port, env={"GANGDAN_DATA_DIR": data_dir})

        ready = wait_for_server("127.0.0.1", port, timeout=20)
        check("Server starts and responds within 20s", ready)

        if not ready:
            stop_server(proc)
            print(f"    Server failed to start within timeout")
            return

        # ── HTML page tests ──

        status, body = http_get("127.0.0.1", port, "/")
        check("GET / returns 200", status == 200)
        check("GET / returns HTML with <html>", "<html" in body.lower())
        check("GET / contains app title", "GangDan" in body or "gangdan" in body.lower())
        check("GET / includes style.css link", "style.css" in body)
        check("GET / includes JS files", "chat.js" in body or "settings.js" in body)
        check("GET / includes KaTeX CDN", "katex" in body.lower())

        # ── Static file tests ──

        status, body = http_get("127.0.0.1", port, "/static/css/style.css")
        check("GET /static/css/style.css returns 200", status == 200)
        check("style.css has CSS content", "color" in body or "font" in body or "{" in body)

        for js_name in ["chat.js", "i18n.js", "settings.js", "utils.js"]:
            status, _ = http_get("127.0.0.1", port, f"/static/js/{js_name}")
            check(f"GET /static/js/{js_name} returns 200", status == 200)

        # ── API endpoint tests ──

        status, body = http_get("127.0.0.1", port, "/api/models", timeout=35)
        check("GET /api/models responds (200 or 500 if Ollama offline)",
              status in (200, 500),
              f"status={status}" if status not in (200, 500) else "")
        if status == 200:
            try:
                data = json.loads(body)
                check("/api/models returns JSON with 'available' key",
                      "available" in data)
            except json.JSONDecodeError:
                check("/api/models returns valid JSON", False, "invalid JSON")

        status, body = http_get("127.0.0.1", port, "/api/docs/list")
        check("GET /api/docs/list returns 200", status == 200)

        status, body = http_get("127.0.0.1", port, "/api/export")
        check("GET /api/export returns 200", status == 200)

        status, body = http_post_json("127.0.0.1", port, "/api/set-language",
                                       {"language": "en"})
        check("POST /api/set-language returns 200", status == 200)

        status, body = http_post_json("127.0.0.1", port, "/api/settings",
                                       {"ollama_url": "http://localhost:11434"})
        check("POST /api/settings returns 200", status == 200)

        status, body = http_post_json("127.0.0.1", port, "/api/stop", {})
        check("POST /api/stop returns 200", status == 200)

        status, body = http_post_json("127.0.0.1", port, "/api/clear", {})
        check("POST /api/clear returns 200", status == 200)

        # ── Data directory tests (small delay for disk flush) ──
        time.sleep(0.5)

        check("Data directory created at custom path",
              Path(data_dir).exists())
        check("GANGDAN_DATA_DIR env var respected (chroma subdir created)",
              (Path(data_dir) / "chroma").exists())
        check("GANGDAN_DATA_DIR env var respected (docs subdir created)",
              (Path(data_dir) / "docs").exists())
        # Config file is written by save_config() on settings change
        config_file = Path(data_dir) / "gangdan_config.json"
        # Trigger an explicit save and retry
        http_post_json("127.0.0.1", port, "/api/settings",
                       {"ollama_url": "http://localhost:11434"})
        for _ in range(6):
            if config_file.exists():
                break
            time.sleep(0.5)
        check("Config file created in data directory", config_file.exists(),
              f"files: {[p.name for p in Path(data_dir).iterdir()]}" if not config_file.exists() else "")
        if config_file.exists():
            try:
                cfg = json.loads(config_file.read_text())
                check("Config file is valid JSON", True)
                check("Config file has ollama_url", "ollama_url" in cfg)
            except json.JSONDecodeError:
                check("Config file is valid JSON", False)

    finally:
        stop_server(proc)
        # Cleanup
        shutil.rmtree(data_dir, ignore_errors=True)


# ── Phase 5: Package build tests ────────────────────────────────────────────

def phase5_build_tests():
    header("Phase 5: Package Build Tests")

    # Clean old dist
    for d in [DIST_DIR, ROOT / "build", ROOT / "gangdan.egg-info"]:
        if d.exists():
            shutil.rmtree(d)

    # Build
    r = run_cmd(f"{sys.executable} -m build", timeout=120)
    check("python -m build exits 0", r.returncode == 0,
          r.stderr.strip()[-200:] if r.returncode != 0 else "")

    if r.returncode != 0:
        print("    Build failed, skipping remaining Phase 5 checks.")
        return

    # Check outputs
    wheels = list(DIST_DIR.glob("*.whl"))
    tarballs = list(DIST_DIR.glob("*.tar.gz"))

    check("Wheel file (.whl) produced", len(wheels) == 1,
          f"found {len(wheels)}")
    check("Source dist (.tar.gz) produced", len(tarballs) == 1,
          f"found {len(tarballs)}")

    if wheels:
        whl = wheels[0]
        check(f"Wheel filename contains 'gangdan'", "gangdan" in whl.name)
        check(f"Wheel filename contains version", "1.0.0" in whl.name)
        check(f"Wheel is py3-none-any", "py3-none-any" in whl.name)
        size_kb = whl.stat().st_size / 1024
        check(f"Wheel size is reasonable ({size_kb:.0f} KB)", 30 < size_kb < 500)


# ── Phase 6: Wheel contents verification ────────────────────────────────────

def phase6_wheel_contents():
    header("Phase 6: Wheel Contents Verification")

    wheels = list(DIST_DIR.glob("*.whl")) if DIST_DIR.exists() else []
    if not wheels:
        skip("All Phase 6 checks", "no wheel found (build phase may have been skipped)")
        return

    whl = wheels[0]
    with zipfile.ZipFile(whl, "r") as zf:
        names = zf.namelist()

    def has(pattern):
        return any(pattern in n for n in names)

    # Python modules
    check("Wheel contains gangdan/__init__.py", has("gangdan/__init__.py"))
    check("Wheel contains gangdan/__main__.py", has("gangdan/__main__.py"))
    check("Wheel contains gangdan/cli.py", has("gangdan/cli.py"))
    check("Wheel contains gangdan/app.py", has("gangdan/app.py"))

    # Templates
    check("Wheel contains gangdan/templates/index.html",
          has("gangdan/templates/index.html"))

    # Static CSS
    check("Wheel contains gangdan/static/css/style.css",
          has("gangdan/static/css/style.css"))

    # Static JS (all 7)
    expected_js = ["chat.js", "docs.js", "i18n.js", "markdown.js",
                   "settings.js", "terminal.js", "utils.js"]
    for js in expected_js:
        check(f"Wheel contains gangdan/static/js/{js}",
              has(f"gangdan/static/js/{js}"))

    # Metadata
    check("Wheel contains METADATA", has("METADATA"))
    check("Wheel contains entry_points.txt", has("entry_points.txt"))
    check("Wheel contains LICENSE", has("LICENSE"))

    # Ensure NO data files leak into wheel
    check("Wheel does NOT contain data/", not has("data/chroma"))
    check("Wheel does NOT contain images/", not has("images/"))

    # Entry point content
    ep_files = [n for n in names if n.endswith("entry_points.txt")]
    if ep_files:
        with zipfile.ZipFile(whl, "r") as zf:
            ep_text = zf.read(ep_files[0]).decode()
        check("Entry point maps gangdan to gangdan.cli:main",
              "gangdan.cli:main" in ep_text)


# ── Phase 7: Clean venv install & run tests ──────────────────────────────────

def phase7_venv_install():
    header("Phase 7: Clean Venv Install & Run Tests")

    wheels = list(DIST_DIR.glob("*.whl")) if DIST_DIR.exists() else []
    if not wheels:
        skip("All Phase 7 checks", "no wheel found")
        return

    whl = wheels[0]
    venv_dir = ROOT / ".test_venv"

    # Cleanup previous test venv
    if venv_dir.exists():
        shutil.rmtree(venv_dir)

    try:
        # Create venv -- try normal first, fall back to --without-pip + bootstrap
        r = run_cmd(f"{sys.executable} -m venv {venv_dir}")
        if r.returncode != 0:
            # Fallback: create without pip, then bootstrap pip manually
            r = run_cmd(f"{sys.executable} -m venv --without-pip {venv_dir}")
            if r.returncode != 0:
                skip("All Phase 7 checks",
                     "python3 -m venv --without-pip also failed")
                return

        venv_python = venv_dir / "bin" / "python"
        venv_pip = venv_dir / "bin" / "pip"
        venv_gangdan = venv_dir / "bin" / "gangdan"

        check("Venv created successfully", venv_python.exists())

        # Bootstrap pip if it's missing (--without-pip case)
        if not venv_pip.exists():
            print(f"\n  Bootstrapping pip into venv via get-pip.py...")
            get_pip = Path(tempfile.gettempdir()) / "get-pip.py"
            if not get_pip.exists():
                r = run_cmd(
                    f"curl -sSL https://bootstrap.pypa.io/get-pip.py -o {get_pip}",
                    timeout=60,
                )
                if r.returncode != 0:
                    skip("All Phase 7 checks", "failed to download get-pip.py")
                    return
            r = run_cmd(f"{venv_python} {get_pip}", timeout=120)
            if r.returncode != 0:
                skip("All Phase 7 checks",
                     f"get-pip.py failed: {r.stderr.strip()[:120]}")
                return
        check("pip available in venv", venv_pip.exists() or
              run_cmd(f"{venv_python} -m pip --version").returncode == 0)

        # Install wheel
        pip_cmd = str(venv_pip) if venv_pip.exists() else f"{venv_python} -m pip"
        print(f"\n  Installing wheel into clean venv (this may take a while)...")
        r = run_cmd(f"{pip_cmd} install {whl}", timeout=300)
        check("pip install wheel succeeds", r.returncode == 0,
              r.stderr.strip()[-200:] if r.returncode != 0 else "")

        if r.returncode != 0:
            return

        # Check entry point exists
        check("gangdan CLI entry point created in venv", venv_gangdan.exists())

        # All venv tests run from neutral cwd to avoid picking up local source
        neutral_cwd = tempfile.gettempdir()

        # --version
        r = run_cmd(f"{venv_gangdan} --version", cwd=neutral_cwd)
        check("gangdan --version in venv exits 0", r.returncode == 0)
        if r.returncode == 0:
            check("gangdan --version outputs correct version",
                  "1.0.0" in r.stdout)

        # --help
        r = run_cmd(f"{venv_gangdan} --help", cwd=neutral_cwd)
        check("gangdan --help in venv exits 0", r.returncode == 0)

        # python -m gangdan --version
        r = run_cmd(f"{venv_python} -m gangdan --version", cwd=neutral_cwd)
        check("python -m gangdan --version in venv exits 0", r.returncode == 0)

        # Import test
        r = run_cmd(
            f'{venv_python} -c "from gangdan import __version__; print(__version__)"',
            cwd=neutral_cwd,
        )
        check("import gangdan in venv succeeds", r.returncode == 0)

        # Data dir detection: in venv (running from neutral cwd) should resolve to ~/.gangdan
        r = run_cmd(
            f'{venv_python} -c "from gangdan.app import DATA_DIR; print(DATA_DIR)"',
            timeout=30, cwd=tempfile.gettempdir(),
        )
        if r.returncode == 0:
            resolved = r.stdout.strip()
            check("DATA_DIR in venv resolves to ~/.gangdan",
                  ".gangdan" in resolved,
                  f"got: {resolved}")
        else:
            check("DATA_DIR in venv resolves", False, r.stderr.strip()[:120])

        # Start server from venv and test HTTP
        port = 15235
        data_dir = tempfile.mkdtemp(prefix="gangdan_venv_test_")
        proc = None

        try:
            ensure_port_free(port)
            cmd = f"{venv_gangdan} --port {port} --host 127.0.0.1 --data-dir {data_dir}"
            proc = start_server(cmd, port, cwd=neutral_cwd)
            ready = wait_for_server("127.0.0.1", port, timeout=25)
            check("Server from venv install starts and responds", ready)

            if ready:
                status, body = http_get("127.0.0.1", port, "/")
                check("Venv server GET / returns 200", status == 200)
                check("Venv server serves HTML", "<html" in body.lower())

                status, _ = http_get("127.0.0.1", port, "/static/css/style.css")
                check("Venv server serves static CSS", status == 200)

                status, _ = http_get("127.0.0.1", port, "/static/js/chat.js")
                check("Venv server serves static JS", status == 200)

                status, body = http_get("127.0.0.1", port, "/api/models", timeout=35)
                check("Venv server /api/models responds",
                      status in (200, 500))
        finally:
            stop_server(proc)
            shutil.rmtree(data_dir, ignore_errors=True)

    finally:
        # Cleanup venv
        if venv_dir.exists():
            shutil.rmtree(venv_dir, ignore_errors=True)


# ── Main ─────────────────────────────────────────────────────────────────────

PHASES = {
    1: ("Source Integrity", phase1_source_integrity),
    2: ("Import & Module", phase2_import_tests),
    3: ("CLI Interface", phase3_cli_tests),
    4: ("Dev Server & HTTP", phase4_server_tests),
    5: ("Package Build", phase5_build_tests),
    6: ("Wheel Contents", phase6_wheel_contents),
    7: ("Clean Venv Install", phase7_venv_install),
}


def main():
    parser = argparse.ArgumentParser(description="GangDan package test suite")
    parser.add_argument("--phase", type=int, choices=range(1, 8),
                        help="Run only a specific phase (1-7)")
    parser.add_argument("--skip-venv", action="store_true",
                        help="Skip Phase 7 (clean venv install)")
    args = parser.parse_args()

    print(f"{Colors.BOLD}")
    print(f"  GangDan Package Test Suite")
    print(f"  Python: {sys.executable} ({sys.version.split()[0]})")
    print(f"  Project: {ROOT}")
    print(f"{Colors.RESET}")

    phases_to_run = [args.phase] if args.phase else list(PHASES.keys())

    if args.skip_venv and 7 in phases_to_run:
        phases_to_run.remove(7)

    for num in phases_to_run:
        name, func = PHASES[num]
        try:
            func()
        except Exception as e:
            print(f"\n  {Colors.RED}Phase {num} ({name}) crashed: {e}{Colors.RESET}")

    # Summary
    total = PASS_COUNT + FAIL_COUNT + SKIP_COUNT
    print(f"\n{Colors.BOLD}{'=' * 64}")
    print(f"  RESULTS: {Colors.GREEN}{PASS_COUNT} passed{Colors.RESET}"
          f"{Colors.BOLD}, {Colors.RED}{FAIL_COUNT} failed{Colors.RESET}"
          f"{Colors.BOLD}, {Colors.YELLOW}{SKIP_COUNT} skipped{Colors.RESET}"
          f"{Colors.BOLD}  (total: {total})")
    print(f"{'=' * 64}{Colors.RESET}\n")

    sys.exit(1 if FAIL_COUNT > 0 else 0)


if __name__ == "__main__":
    main()
