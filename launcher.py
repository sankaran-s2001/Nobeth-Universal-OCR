"""
Production-grade deployment launcher for Nobeth Universal OCR.
Coordinates environment checks, virtualenv validation, dependency caching,
configuration onboarding, dynamic port selection, browser launch, and Streamlit execution.
"""

import sys
import os
import subprocess
import hashlib
import socket
import time
import shutil
import webbrowser
import logging
import threading
from typing import Optional, Tuple

# ==============================================================================
# 1. PATH DEFINITIONS & DIRECTORY PREPARATION
# ==============================================================================
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(PROJECT_ROOT, ".venv")
VENV_PYTHON = os.path.join(VENV_DIR, "Scripts", "python.exe")
VENV_PIP = os.path.join(VENV_DIR, "Scripts", "pip.exe")

LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
BOOTSTRAP_LOG = os.path.join(LOG_DIR, "bootstrap.log")

STATE_DIR = os.path.join(PROJECT_ROOT, ".project_state")
FINGERPRINT_FILE = os.path.join(STATE_DIR, "requirements.fingerprint")
LEGACY_HASH_FILE = os.path.join(STATE_DIR, "requirements.sha256")
PID_FILE = os.path.join(STATE_DIR, "running_server.pid")
PORT_FILE = os.path.join(STATE_DIR, "running_server.port")

ENV_FILE = os.path.join(PROJECT_ROOT, ".env")
ENV_EXAMPLE = os.path.join(PROJECT_ROOT, ".env.example")
REQUIREMENTS_FILE = os.path.join(PROJECT_ROOT, "requirements.txt")
APP_ENTRYPOINT = os.path.join(PROJECT_ROOT, "app.py")

# Ensure required local directories exist
try:
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)
except Exception:
    pass

# ==============================================================================
# 2. LOGGING CONFIGURATION & FORMATTING HELPERS
# ==============================================================================
logging.basicConfig(
    filename=BOOTSTRAP_LOG,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def log_step(step_num: int, label: str, status: str, details: Optional[str] = None):
    """Prints a professionally aligned startup step with stable ASCII status labels."""
    detail_str = f" ({details})" if details else ""
    line = f" [{step_num:02d}] {label:<24} : {status:<15}{detail_str}"
    print(line)
    logging.info(f"STEP {step_num:02d} | {label} | {status} | {details or ''}")


def print_banner(title: str = "STARTUP"):
    print("============================================================")
    print(f" NOBETH UNIVERSAL OCR | {title}")
    print("============================================================")


# ==============================================================================
# 3. WRITE PERMISSION CHECK
# ==============================================================================
def check_write_permissions(root_dir: str = PROJECT_ROOT) -> Tuple[bool, float, Optional[str]]:
    """Checks whether the project root directory is writable."""
    t0 = time.perf_counter()
    test_file = os.path.join(root_dir, f".write_test_{os.getpid()}")
    try:
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("write_test")
        if os.path.exists(test_file):
            os.remove(test_file)
        dur_ms = (time.perf_counter() - t0) * 1000.0
        return True, dur_ms, None
    except Exception as e:
        dur_ms = (time.perf_counter() - t0) * 1000.0
        return False, dur_ms, str(e)


# ==============================================================================
# 4. PYTHON VERSION POLICY
# ==============================================================================
def check_python_version(version_info=None) -> Tuple[bool, str, str]:
    """
    Validates Python version against supported matrix:
    - 3.11: Fully Supported (Recommended)
    - 3.10, 3.12: Supported
    - < 3.10: Unsupported
    - >= 3.13: Warning
    """
    vi = version_info or sys.version_info
    version_str = f"{vi.major}.{vi.minor}.{vi.micro}"

    if vi.major < 3 or (vi.major == 3 and vi.minor < 10):
        return False, version_str, "UNSUPPORTED"

    if vi.major == 3 and vi.minor == 11:
        return True, version_str, "FULLY SUPPORTED"
    elif vi.major == 3 and vi.minor in [10, 12]:
        return True, version_str, "SUPPORTED"
    else:
        return True, version_str, "UNTESTED VERSION"


# ==============================================================================
# 5. VIRTUAL ENVIRONMENT VALIDATION & CREATION
# ==============================================================================
def is_venv_healthy(venv_dir: str = VENV_DIR, venv_python: str = VENV_PYTHON) -> Tuple[bool, str]:
    """
    Validates if .venv exists, has correct python executable, matches current Python version,
    and has functional pip.
    """
    if not os.path.isdir(venv_dir):
        return False, "Virtual environment directory does not exist."
    if not os.path.isfile(venv_python):
        return False, f"Python executable missing in virtual environment ({venv_python})."

    try:
        v_out = subprocess.check_output(
            [venv_python, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        venv_version = v_out.decode().strip()
        current_version = f"{sys.version_info.major}.{sys.version_info.minor}"
        if venv_version != current_version:
            return False, f"Virtual environment Python ({venv_version}) does not match host Python ({current_version})."
    except Exception as e:
        return False, f"Virtual environment Python failed execution: {e}"

    try:
        p_out = subprocess.run(
            [venv_python, "-m", "pip", "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        if p_out.returncode != 0:
            return False, "pip is not functional inside the virtual environment."
    except Exception as e:
        return False, f"pip check failed inside virtual environment: {e}"

    return True, "Virtual environment is healthy."


def ensure_virtual_env(
    venv_dir: str = VENV_DIR,
    venv_python: str = VENV_PYTHON,
    sys_python: str = sys.executable,
) -> Tuple[bool, str, float]:
    """
    Ensures a valid virtual environment exists.
    If healthy, reuses it non-destructively.
    If missing, creates it.
    If corrupted/mismatched, rebuilds it safely.
    """
    t0 = time.perf_counter()
    healthy, diagnosis = is_venv_healthy(venv_dir, venv_python)

    if healthy:
        dur = time.perf_counter() - t0
        return True, "READY", dur

    # Virtual environment exists but is corrupted or copied from another computer
    if os.path.exists(venv_dir):
        logging.warning(f"Rebuilding corrupted venv: {diagnosis}")
        try:
            shutil.rmtree(venv_dir, ignore_errors=True)
            if os.path.exists(venv_dir):
                time.sleep(1.0)
                shutil.rmtree(venv_dir)
        except Exception as e:
            dur = time.perf_counter() - t0
            return False, f"Could not remove corrupted .venv: {e}", dur

    # Create fresh virtual environment
    try:
        subprocess.run([sys_python, "-m", "venv", venv_dir], check=True, stdout=subprocess.DEVNULL)
        # Verify created venv
        h_after, diag_after = is_venv_healthy(venv_dir, venv_python)
        dur = time.perf_counter() - t0
        if h_after:
            return True, "CREATED", dur
        return False, f"Created venv is unhealthy: {diag_after}", dur
    except Exception as e:
        dur = time.perf_counter() - t0
        return False, f"venv creation failed: {e}", dur


# ==============================================================================
# 6. DEPENDENCY MANAGEMENT & CACHING
# ==============================================================================
def calculate_requirements_fingerprint(req_file: str = REQUIREMENTS_FILE, python_version: Optional[str] = None) -> str:
    """Calculates a composite fingerprint of requirements.txt SHA-256 and Python version."""
    if not os.path.exists(req_file):
        raise FileNotFoundError(f"Requirements file not found at: {req_file}")

    sha256 = hashlib.sha256()
    with open(req_file, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    req_hash = sha256.hexdigest()

    py_ver = python_version or f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    return f"{req_hash}:{py_ver}"


def verify_runtime_dependencies(venv_python: str = VENV_PYTHON) -> bool:
    """Verifies all required core packages can be imported inside the venv Python."""
    if not os.path.exists(venv_python):
        return False
    check_code = (
        "import streamlit; "
        "import google.genai; "
        "import pydantic; "
        "import PIL; "
        "import cv2; "
        "import fitz; "
        "import dotenv"
    )
    try:
        res = subprocess.run([venv_python, "-c", check_code], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        return res.returncode == 0
    except Exception:
        return False


def ensure_dependencies(
    venv_python: str = VENV_PYTHON,
    req_file: str = REQUIREMENTS_FILE,
    state_dir: str = STATE_DIR,
) -> Tuple[bool, str, float]:
    """
    Validates dependencies against fingerprint cache and core runtime imports.
    If cached and valid, skips installation.
    If missing or outdated, runs pip install and updates cache upon success.
    """
    t0 = time.perf_counter()
    if not os.path.exists(req_file):
        dur = time.perf_counter() - t0
        return False, "requirements.txt not found", dur

    try:
        current_fingerprint = calculate_requirements_fingerprint(req_file)
    except Exception as e:
        dur = time.perf_counter() - t0
        return False, str(e), dur

    # Check cached fingerprint
    cached_fingerprint = ""
    fp_path = os.path.join(state_dir, "requirements.fingerprint")
    legacy_path = os.path.join(state_dir, "requirements.sha256")

    if os.path.exists(fp_path):
        try:
            with open(fp_path, "r", encoding="utf-8") as f:
                cached_fingerprint = f.read().strip()
        except Exception:
            pass
    elif os.path.exists(legacy_path):
        try:
            with open(legacy_path, "r", encoding="utf-8") as f:
                cached_fingerprint = f.read().strip()
        except Exception:
            pass

    # Fast path: cache matches and imports succeed
    if (cached_fingerprint == current_fingerprint or cached_fingerprint == current_fingerprint.split(":")[0]) and verify_runtime_dependencies(venv_python):
        dur = time.perf_counter() - t0
        return True, "VERIFIED", dur

    # Installation required
    print("      Installing dependencies from requirements.txt (this may take a minute)...")
    try:
        res = subprocess.run([venv_python, "-m", "pip", "install", "-r", req_file])
        if res.returncode != 0:
            dur = time.perf_counter() - t0
            return False, f"pip install failed with returncode {res.returncode}", dur
    except Exception as e:
        dur = time.perf_counter() - t0
        return False, f"pip installation command error: {e}", dur

    # Verify imports after installation
    if verify_runtime_dependencies(venv_python):
        try:
            with open(fp_path, "w", encoding="utf-8") as f:
                f.write(current_fingerprint)
        except Exception as e:
            logging.warning(f"Failed to write requirements fingerprint: {e}")
        dur = time.perf_counter() - t0
        return True, "INSTALLED", dur
    else:
        dur = time.perf_counter() - t0
        return False, "Core runtime dependencies failed import verification after install", dur


# ==============================================================================
# 7. ENVIRONMENT CONFIGURATION (.env VALIDATION)
# ==============================================================================
def extract_api_key_from_env(env_path: str = ENV_FILE) -> Optional[str]:
    """Reads GEMINI_API_KEY from .env safely without printing or exposing secrets."""
    if not os.path.exists(env_path):
        return None
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == "GEMINI_API_KEY":
                    return v.strip().strip('"').strip("'")
    except Exception as e:
        logging.warning(f"Error reading .env: {e}")
    return None


def is_api_key_valid(raw_key: Optional[str]) -> bool:
    """Checks whether a Gemini API key is configured and not a known placeholder."""
    if not raw_key:
        return False
    clean = raw_key.strip().strip('"').strip("'")
    if not clean:
        return False
    known_placeholders = {
        "your_gemini_api_key_here",
        "your_actual_key_here",
        "your_key_here",
        "none",
        "todo",
        "placeholder",
        "enter_key_here",
        "insert_key_here",
    }
    if clean.lower() in known_placeholders:
        return False
    return len(clean) >= 8


def ensure_environment_config(
    env_path: str = ENV_FILE,
    example_path: str = ENV_EXAMPLE,
    open_editor: bool = True,
) -> Tuple[bool, str, str]:
    """
    Validates .env configuration according to specification:
    Case A: .env does not exist -> copy from template, guide user, open Notepad, stop.
    Case B: .env exists with placeholder key -> guide user, open Notepad, stop.
    Case C: .env exists with valid key -> proceed directly.
    """
    created_new = False
    if not os.path.exists(env_path):
        if not os.path.exists(example_path):
            return False, "FAILED", f"Template file {example_path} is missing."
        try:
            shutil.copy(example_path, env_path)
            created_new = True
        except Exception as e:
            return False, "FAILED", f"Could not create .env from template: {e}"

    key = extract_api_key_from_env(env_path)

    # If .env does not have a valid key, check if user updated .env.example instead
    if not is_api_key_valid(key) and os.path.exists(example_path):
        example_key = extract_api_key_from_env(example_path)
        if is_api_key_valid(example_key):
            try:
                shutil.copy(example_path, env_path)
                key = example_key
                logging.info("Synced valid Gemini API key from .env.example to .env.")
            except Exception:
                pass

    if is_api_key_valid(key):
        return True, "VALID", "Key configured"

    # Guide user through one-time configuration
    title = "ONE-TIME CONFIGURATION REQUIRED" if created_new else "CONFIGURATION ACTION REQUIRED"
    print("\n============================================================")
    print(f" NOBETH UNIVERSAL OCR: {title}")
    print("============================================================")
    print("\n Your Google Gemini API key must be configured before startup.\n")
    print(" Instructions:")
    print("   Step 1: Open the .env file in Notepad.")
    print("   Step 2: Find the line beginning with: GEMINI_API_KEY=")
    print("   Step 3: Replace the example placeholder with your actual Gemini API key.")
    print("   Step 4: Save the file using Ctrl+S.")
    print("   Step 5: Close Notepad.")
    print("   Step 6: Double-click run.bat again to launch the application.\n")
    print(" Get a free Gemini API key at:")
    print("   https://aistudio.google.com/app/apikey\n")
    print(" IMPORTANT: Keep your API key private. Never share it or commit it to Git.")
    print("============================================================")
    print(" Startup paused for configuration.")
    print("============================================================\n")

    if open_editor and os.name == "nt":
        try:
            subprocess.Popen(["notepad.exe", env_path])
        except Exception:
            pass

    return False, "ACTION REQUIRED", "GEMINI_API_KEY requires configuration in .env"


# ==============================================================================
# 8. PORT SELECTION & RUNNING INSTANCE MANAGEMENT
# ==============================================================================
def is_port_busy(port: int) -> bool:
    """Returns True if the port is occupied on localhost or any interface."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.15)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except socket.error:
            pass

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("", port))
            return False
        except socket.error:
            return True


def find_free_port(start_port: int = 8501, max_scan: int = 100) -> int:
    port = start_port
    while is_port_busy(port) and port < start_port + max_scan:
        logging.info(f"Port {port} is occupied. Scanning next port.")
        port += 1
    return port


def check_running_instance(pid_file: str = PID_FILE, port_file: str = PORT_FILE) -> Tuple[bool, Optional[int], Optional[int]]:
    """Checks if a previously started server belongs to this project and is still running."""
    if not os.path.exists(pid_file) or not os.path.exists(port_file):
        return False, None, None

    try:
        with open(pid_file, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
        with open(port_file, "r", encoding="utf-8") as f:
            port = int(f.read().strip())
    except Exception:
        return False, None, None

    is_active = False
    try:
        # Check if PID is active on Windows
        output = subprocess.check_output(f'tasklist /FI "PID eq {pid}" /NH', shell=True).decode(errors="ignore")
        if str(pid) in output and "python" in output.lower():
            is_active = True
    except Exception:
        pass

    if is_active and is_port_busy(port):
        return True, pid, port

    # Clean up stale files
    try:
        os.remove(pid_file)
    except Exception:
        pass
    try:
        os.remove(port_file)
    except Exception:
        pass

    return False, None, None


# ==============================================================================
# 9. STREAMLIT SERVER STARTUP & CLEAN SHUTDOWN
# ==============================================================================
def launch_browser_thread(port: int, max_wait_sec: float = 30.0):
    """Waits for the Streamlit server port to become active, then opens the browser once."""
    url = f"http://localhost:{port}"
    logging.info(f"Monitoring port {port} for web browser launch...")
    start_t = time.perf_counter()
    server_ready = False

    while (time.perf_counter() - start_t) < max_wait_sec:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                s.connect(("127.0.0.1", port))
                server_ready = True
                break
        except Exception:
            time.sleep(0.5)

    if server_ready:
        time.sleep(0.2)
        try:
            webbrowser.open(url)
            logging.info(f"Browser opened at {url}")
        except Exception as e:
            logging.warning(f"Could not auto-open browser: {e}")


def start_streamlit_server(
    port: int,
    venv_python: str = VENV_PYTHON,
    entrypoint: str = APP_ENTRYPOINT,
    project_root: str = PROJECT_ROOT,
):
    """Starts the Streamlit server and handles graceful Ctrl+C shutdown."""
    log_step(7, "Streamlit server", "STARTING", f"Port {port}")

    try:
        with open(PORT_FILE, "w", encoding="utf-8") as f:
            f.write(str(port))
    except Exception as e:
        logging.warning(f"Failed to write port file: {e}")

    # Launch browser thread
    b_thread = threading.Thread(target=launch_browser_thread, args=(port,), daemon=True)
    b_thread.start()

    max_mb_str = os.getenv("MAX_FILE_SIZE_MB", "50")
    cmd = [
        venv_python,
        "-m",
        "streamlit",
        "run",
        entrypoint,
        "--server.port",
        str(port),
        "--server.fileWatcherType",
        "poll",
        "--server.maxUploadSize",
        max_mb_str,
    ]

    print("\n------------------------------------------------------------")
    print(f" Web Application URL : http://localhost:{port}")
    print(" Logs & Terminal     : Live output below (Press Ctrl+C to stop)")
    print("------------------------------------------------------------\n")

    process = None
    try:
        process = subprocess.Popen(cmd, cwd=project_root)
        try:
            with open(PID_FILE, "w", encoding="utf-8") as f:
                f.write(str(process.pid))
        except Exception as e:
            logging.warning(f"Failed to write PID file: {e}")

        process.wait()
    except KeyboardInterrupt:
        print("\n[INFO] Graceful shutdown initiated (Ctrl+C)...")
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
    except Exception as e:
        print(f"\n[ERROR] Streamlit server failed during execution: {e}")
        logging.error(f"Process execution error: {e}")
        sys.exit(1)
    finally:
        # Clean up state files
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except Exception:
                pass
        if os.path.exists(PORT_FILE):
            try:
                os.remove(PORT_FILE)
            except Exception:
                pass
        print("[INFO] Server stopped cleanly.")


# ==============================================================================
# 10. MAIN LAUNCHER ENTRYPOINT
# ==============================================================================
def main():
    print_banner("STARTUP")

    # Step 1: Python Detection
    t0_py = time.perf_counter()
    is_supported, py_ver, py_status = check_python_version()
    dur_py = (time.perf_counter() - t0_py) * 1000.0

    if not is_supported:
        log_step(1, "Python runtime", "FAILED", f"Python {py_ver} is unsupported")
        print("\n============================================================")
        print(" Nobeth Universal OCR requires Python 3.10, 3.11, or 3.12.")
        print(f" Current interpreter: Python {py_ver}")
        print(" Please install Python 3.11 from: https://www.python.org/downloads/")
        print("============================================================\n")
        sys.exit(1)

    log_step(1, "Python runtime", "READY", f"Python {py_ver} ({py_status}) in {dur_py:.1f} ms")

    # Step 2: Workspace Write Check
    writable, dur_write, write_err = check_write_permissions()
    if not writable:
        log_step(2, "Workspace write check", "FAILED", write_err)
        print("\n[ERROR] The application directory is not writable.")
        print("Please copy the project folder to a writable location (e.g. Desktop or Documents).")
        sys.exit(1)
    log_step(2, "Workspace write check", "SUCCESS", f"{dur_write:.1f} ms")

    # Step 3: Check for Existing Server Instance
    is_running, run_pid, run_port = check_running_instance()
    if is_running:
        print("\n============================================================")
        print(" NOBETH UNIVERSAL OCR | ALREADY RUNNING")
        print("============================================================")
        print(f" An active instance is already running on port {run_port} (PID: {run_pid}).")
        print(" Reopening the application in your default browser...")
        print(f" URL: http://localhost:{run_port}")
        print("============================================================\n")
        try:
            webbrowser.open(f"http://localhost:{run_port}")
        except Exception:
            pass
        print("Application is live in your browser.")
        print("Press Enter to close this launcher window...")
        try:
            input()
        except Exception:
            pass
        sys.exit(0)

    # Validate application entrypoint exists
    if not os.path.exists(APP_ENTRYPOINT):
        log_step(3, "Application entrypoint", "FAILED", f"Missing {APP_ENTRYPOINT}")
        sys.exit(1)

    # Step 3: Virtual Environment
    venv_ok, venv_status, venv_dur = ensure_virtual_env()
    if not venv_ok:
        log_step(3, "Virtual environment", "FAILED", venv_status)
        sys.exit(1)
    if venv_dur >= 1.0:
        venv_timing = f"{venv_dur:.1f} s"
    else:
        venv_timing = f"{venv_dur * 1000.0:.1f} ms"
    log_step(3, "Virtual environment", "READY", f".venv in {venv_timing}")

    # Step 4: Dependencies
    dep_ok, dep_status, dep_dur = ensure_dependencies()
    if not dep_ok:
        log_step(4, "Dependencies", "FAILED", dep_status)
        print("\n[ERROR] Dependency installation could not be completed.")
        print("Please verify your internet connection and try running run.bat again.")
        sys.exit(1)
    if dep_dur >= 1.0:
        dep_timing = f"{dep_dur:.1f} s"
    else:
        dep_timing = f"{dep_dur * 1000.0:.1f} ms"
    log_step(4, "Dependencies", "VERIFIED", f"{dep_timing}")

    # Step 5: Configuration (.env)
    env_ok, env_status, env_details = ensure_environment_config()
    if not env_ok:
        log_step(5, "Configuration (.env)", env_status, env_details)
        # Exit cleanly with code 1 so run.bat knows setup is paused for configuration
        sys.exit(1)
    log_step(5, "Configuration (.env)", "VALID", "Key configured")

    # Step 6: Network Port
    port = find_free_port(8501)
    log_step(6, "Network port", "READY", f"Port {port}")

    # Step 7: Streamlit Server
    start_streamlit_server(port)


if __name__ == "__main__":
    main()
