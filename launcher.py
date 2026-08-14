"""
Production-grade deployment launcher for Nobeth Universal OCR.
Coordinates environment checks, virtualenv recovery, caching, configuration validation,
dynamic port selection, browser launch, and Streamlit execution.
"""

import sys
import os
import subprocess
import hashlib
import socket
import time
import shutil
import urllib.request
import webbrowser
import logging
import threading

# 1. PATH CONFIGURATION
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(PROJECT_ROOT, ".venv")
VENV_PYTHON = os.path.join(VENV_DIR, "Scripts", "python.exe")
VENV_PIP = os.path.join(VENV_DIR, "Scripts", "pip.exe")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
BOOTSTRAP_LOG = os.path.join(LOG_DIR, "bootstrap.log")
STATE_DIR = os.path.join(PROJECT_ROOT, ".project_state")
HASH_FILE = os.path.join(STATE_DIR, "requirements.sha256")
PID_FILE = os.path.join(STATE_DIR, "running_server.pid")
PORT_FILE = os.path.join(STATE_DIR, "running_server.port")
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")
ENV_EXAMPLE = os.path.join(PROJECT_ROOT, ".env.example")
REQUIREMENTS_FILE = os.path.join(PROJECT_ROOT, "requirements.txt")
APP_ENTRYPOINT = os.path.join(PROJECT_ROOT, "app.py")

# Ensure required local directories exist
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(STATE_DIR, exist_ok=True)

# 2. SETUP SECURE LOGGING
logging.basicConfig(
    filename=BOOTSTRAP_LOG,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)


def log_user(msg: str, level: str = "INFO"):
    """Logs to the bootstrap log file and prints to stdout with simple ASCII tags."""
    logging.info(msg)
    if level == "ERROR":
        print(f"[ERROR] {msg}")
    elif level == "WARN":
        print(f"[WARN]  {msg}")
    else:
        print(f"[INFO]  {msg}")


# 3. WRITE PERMISSION CHECK
def check_write_permissions():
    test_file = os.path.join(PROJECT_ROOT, ".write_test")
    try:
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
    except Exception as e:
        log_user("Project root directory is not writable. Please check permissions.", "ERROR")
        logging.error(f"Write check failed: {e}")
        sys.exit(1)


# 4. PYTHON VERSION POLICY
def check_python_version():
    vi = sys.version_info
    version_str = f"{vi.major}.{vi.minor}.{vi.micro}"
    
    if vi.major < 3 or (vi.major == 3 and vi.minor < 10):
        print("==================================================")
        print(f"Python Version : {version_str}")
        print("Status         : Unsupported")
        print("Minimum supported version: Python 3.10")
        print("Please install Python 3.10 or newer.")
        print("Official download: https://www.python.org/downloads/")
        print("==================================================")
        logging.error(f"Unsupported Python version: {version_str}")
        input("Press enter to exit...")
        sys.exit(1)
    
    print("==================================================")
    print("NOBETH UNIVERSAL OCR")
    print("One-Click Launcher")
    print("==================")
    
    if vi.major == 3 and vi.minor == 11:
        print(f"Python Version : {version_str}")
        print("Status         : Fully Supported")
    elif vi.major == 3 and vi.minor in [10, 12]:
        print(f"Python Version : {version_str}")
        print("Status         : Supported")
    else:
        print(f"Python Version : {version_str}")
        print("Status         : Supported")
        print("\nNote:")
        print("This Python version is outside the project's primary tested version,")
        print("but the launcher will continue automatically.")
    print("==================================================")
    logging.info(f"Python interpreter verified: {version_str}")


# 5. ENVIRONMENT / CONFIG VALIDATION
def check_environment_config():
    if not os.path.exists(ENV_FILE):
        if os.path.exists(ENV_EXAMPLE):
            try:
                shutil.copy(ENV_EXAMPLE, ENV_FILE)
                log_user("Created .env file from template (.env.example).")
            except Exception as e:
                log_user("Failed to copy .env.example to .env.", "ERROR")
                logging.error(f"Copying .env failed: {e}")
                sys.exit(1)
        else:
            log_user("Configuration template (.env.example) is missing.", "ERROR")
            sys.exit(1)

    # Read .env (without loading secrets into process log outputs)
    api_key_valid = False
    try:
        with open(ENV_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k == "GEMINI_API_KEY":
                    # Check if present and not placeholder
                    if v and v != "your_gemini_api_key_here" and len(v) > 10:
                        api_key_valid = True
    except Exception as e:
        log_user("Failed to read .env file.", "ERROR")
        logging.error(f"Reading .env failed: {e}")
        sys.exit(1)

    if not api_key_valid:
        print("\nConfiguration Status : Incomplete")
        print("Gemini API key is not configured.")
        print("Please configure GEMINI_API_KEY in your local `.env` file.")
        print(f"Path: {ENV_FILE}")
        print("Then restart the application.")
        logging.error("GEMINI_API_KEY is missing or contains placeholder.")
        input("\nPress enter to exit...")
        sys.exit(1)

    log_user("Configuration  : Valid")


def is_port_busy(port: int) -> bool:
    """Returns True if the port is occupied on localhost or any interface."""
    # 1. Try to connect to localhost on this port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.15)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except socket.error:
            pass

    # 2. Try to bind to all interfaces on this port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("", port))
            return False
        except socket.error:
            return True


def find_free_port(start_port: int = 8501) -> int:
    port = start_port
    while is_port_busy(port):
        logging.info(f"Port {port} is occupied. Scanning next port.")
        port += 1
    return port


# 7. SILENT VENV MANAGEMENT
def is_venv_healthy() -> bool:
    """Validates if .venv exists, has correct python executable, and matches current Python version."""
    if not os.path.exists(VENV_DIR) or not os.path.exists(VENV_PYTHON):
        return False
    try:
        # Verify that venv Python version matches this launcher's Python version
        v_out = subprocess.check_output([VENV_PYTHON, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"], stderr=subprocess.DEVNULL)
        venv_version = v_out.decode().strip()
        current_version = f"{sys.version_info.major}.{sys.version_info.minor}"
        return venv_version == current_version
    except Exception as e:
        logging.warning(f"Venv health check failed: {e}")
        return False


def build_virtual_env():
    log_user("Preparing virtual environment...")
    if os.path.exists(VENV_DIR):
        try:
            # Delete corrupted or mismatched venv
            shutil.rmtree(VENV_DIR, ignore_errors=True)
            # Second pass fallback if locked
            if os.path.exists(VENV_DIR):
                time.sleep(1.0)
                shutil.rmtree(VENV_DIR)
        except Exception as e:
            log_user("Could not delete old virtual environment folder. Close any locking programs.", "ERROR")
            logging.error(f"rmtree .venv failed: {e}")
            sys.exit(1)

    try:
        # Create virtualenv silently using selected interpreter
        subprocess.run([sys.executable, "-m", "venv", VENV_DIR], check=True, stdout=subprocess.DEVNULL)
        log_user("Virtual env    : Created successfully")
    except Exception as e:
        log_user("Failed to create virtual environment.", "ERROR")
        logging.error(f"Venv creation command failed: {e}")
        sys.exit(1)


# 8. LIGHTWEIGHT RUNTIME IMPORT AND CACHE CHECK
def calculate_requirements_hash() -> str:
    if not os.path.exists(REQUIREMENTS_FILE):
        log_user("requirements.txt not found.", "ERROR")
        sys.exit(1)
    sha256 = hashlib.sha256()
    with open(REQUIREMENTS_FILE, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


def verify_runtime_dependencies() -> bool:
    """Verifies all required core packages can be imported inside the venv Python."""
    if not os.path.exists(VENV_PYTHON):
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
        res = subprocess.run([VENV_PYTHON, "-c", check_code], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return res.returncode == 0
    except Exception:
        return False


def check_internet_connection() -> bool:
    try:
        # Attempt to reach google public DNS (quick connection check)
        urllib.request.urlopen("https://www.google.com", timeout=3.0)
        return True
    except Exception:
        return False


def install_dependencies(req_hash: str):
    log_user("Installing required dependencies (this may take a minute)...")
    
    # 1. Upgrade pip first
    try:
        subprocess.run([VENV_PYTHON, "-m", "pip", "install", "--upgrade", "pip"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    except Exception:
        pass # Not critical to fail launcher if pip upgrade fails

    # 2. Install requirements with bounded retries (max 3)
    max_attempts = 3
    success = False
    for attempt in range(1, max_attempts + 1):
        log_user(f"Attempting connection and installation (Attempt {attempt} of {max_attempts})...")
        try:
            res = subprocess.run(
                [VENV_PYTHON, "-m", "pip", "install", "-r", REQUIREMENTS_FILE],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=180
            )
            if res.returncode == 0:
                success = True
                break
        except subprocess.TimeoutExpired:
            log_user("Connection timed out during pip install.", "WARN")
        except Exception as e:
            logging.warning(f"Pip install attempt {attempt} failed: {e}")
        time.sleep(2.0)

    if not success:
        log_user("\n==================================================", "ERROR")
        log_user("STARTUP FAILED", "ERROR")
        log_user("Reason:", "ERROR")
        log_user("Unable to install required dependencies.", "ERROR")
        log_user("This process requires internet access.", "ERROR")
        log_user("Details have been written to logs\\bootstrap.log.", "ERROR")
        log_user("==================================================", "ERROR")
        sys.exit(1)

    # 3. Final validation check
    if verify_runtime_dependencies():
        # Store hash only after successful verification
        try:
            with open(HASH_FILE, "w") as f:
                f.write(req_hash)
            log_user("Dependencies   : Installed & Verified")
        except Exception as e:
            logging.warning(f"Failed to save requirements hash: {e}")
    else:
        log_user("Dependencies could not be verified after installation.", "ERROR")
        sys.exit(1)


# 9. DYNAMIC RUNNER & BROWSER LAUNCHER
def launch_browser_thread(port: int):
    """Waits for the Streamlit server port to become active, then opens the browser."""
    url = f"http://localhost:{port}"
    logging.info(f"Monitoring port {port} for web browser launch...")
    
    # Try up to 30 times (15 seconds)
    for _ in range(30):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                s.connect(("127.0.0.1", port))
                logging.info(f"Port {port} responded. Spawning default browser...")
                break
        except Exception:
            time.sleep(0.5)
            
    # Spawn default browser
    try:
        webbrowser.open(url)
    except Exception as e:
        log_user(f"Failed to auto-launch default browser: {e}", "WARN")
        log_user(f"Please open your browser manually at: {url}")


def check_running_instance() -> bool:
    """Checks if a previously started server is already running to prevent duplicate launches."""
    if not os.path.exists(PID_FILE) or not os.path.exists(PORT_FILE):
        return False
        
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
        with open(PORT_FILE, "r") as f:
            port = int(f.read().strip())
    except Exception:
        return False

    # Check if PID is still active and is Python/Streamlit on Windows
    is_active = False
    try:
        # NH hides header. Outputs running task information if PID exists.
        output = subprocess.check_output(f'tasklist /FI "PID eq {pid}" /NH', shell=True).decode(errors="ignore")
        if str(pid) in output and "python" in output.lower():
            is_active = True
    except Exception:
        pass

    # Verify that the port is actually still listening
    if is_active and is_port_busy(port):
        log_user(f"Application is already running on port {port} (PID: {pid}).")
        log_user("Reopening active application session in default browser...")
        try:
            webbrowser.open(url=f"http://localhost:{port}")
        except Exception:
            pass
        return True

    return False


def start_streamlit_server(port: int):
    # Log startup state
    try:
        with open(PORT_FILE, "w") as f:
            f.write(str(port))
    except Exception as e:
        logging.warning(f"Failed to write running port file: {e}")

    log_user("Streamlit      : Ready")
    log_user(f"Starting server on port {port}...")
    
    # Launch browser on separate background thread
    b_thread = threading.Thread(target=launch_browser_thread, args=(port,), daemon=True)
    b_thread.start()

    # Streamlit execution command
    cmd = [
        VENV_PYTHON,
        "-m",
        "streamlit",
        "run",
        APP_ENTRYPOINT,
        "--server.port",
        str(port),
        "--server.fileWatcherType",
        "poll"
    ]
    
    try:
        process = subprocess.Popen(cmd, cwd=PROJECT_ROOT)
        
        # Write running PID
        try:
            with open(PID_FILE, "w") as f:
                f.write(str(process.pid))
        except Exception as e:
            logging.warning(f"Failed to write running PID file: {e}")

        # Keep server running in foreground
        process.wait()
    except KeyboardInterrupt:
        log_user("Server shutdown requested via keyboard interrupt.")
    except Exception as e:
        log_user("\nStreamlit server failed during execution.", "ERROR")
        logging.error(f"Process execution error: {e}")
        input("Press enter to exit...")
        sys.exit(1)


# 10. MAIN PROCESS FLOW
def main():
    check_write_permissions()
    check_python_version()
    
    # Check for running server instances first
    if check_running_instance():
        # Instance exists and browser was reopened, exit safely
        sys.exit(0)

    # Validate entrypoint file
    if not os.path.exists(APP_ENTRYPOINT):
        log_user("Application entrypoint not found.", "ERROR")
        log_user(f"Expected: {APP_ENTRYPOINT}", "ERROR")
        sys.exit(1)

    # 1. Verify/create Virtualenv
    if not is_venv_healthy():
        build_virtual_env()
    else:
        log_user("Virtual env    : Ready")

    # 2. Verify/install Dependencies
    req_hash = calculate_requirements_hash()
    cached_hash = ""
    if os.path.exists(HASH_FILE):
        try:
            with open(HASH_FILE, "r") as f:
                cached_hash = f.read().strip()
        except Exception:
            pass

    # Check if cache matches and imports succeed
    if req_hash == cached_hash and verify_runtime_dependencies():
        log_user("Dependencies   : Verified")
    else:
        # Hash mismatch or missing imports: run install
        # Check internet connection first
        if not check_internet_connection():
            log_user("\n==================================================", "ERROR")
            log_user("STARTUP FAILED", "ERROR")
            log_user("Reason:", "ERROR")
            log_user("Missing dependencies need to be installed, but no", "ERROR")
            log_user("internet connection was detected.", "ERROR")
            log_user("==================================================", "ERROR")
            sys.exit(1)
        install_dependencies(req_hash)

    # 3. Environment configuration checks (No prompts)
    check_environment_config()

    # 4. Port scanner
    port = find_free_port(8501)
    
    # 5. Start Streamlit and launch browser
    start_streamlit_server(port)


if __name__ == "__main__":
    main()
