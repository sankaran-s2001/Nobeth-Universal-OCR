"""
Unit and integration tests for launcher.py and first-time setup flows.
Validates Python detection, non-destructive venv handling, requirements fingerprinting,
beginner-friendly .env onboarding, port scanning, instance reuse, and error recovery.
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch
import pytest

from launcher import (
    check_write_permissions,
    check_python_version,
    is_venv_healthy,
    ensure_virtual_env,
    calculate_requirements_fingerprint,
    verify_runtime_dependencies,
    ensure_dependencies,
    extract_api_key_from_env,
    is_api_key_valid,
    ensure_environment_config,
    is_port_busy,
    find_free_port,
    check_running_instance,
)


# ==============================================================================
# 1. PYTHON VERSION POLICY TESTS
# ==============================================================================
def test_python_version_311_recommended():
    vi = types.SimpleNamespace(major=3, minor=11, micro=7)
    ok, ver, label = check_python_version(vi)
    assert ok is True
    assert ver == "3.11.7"
    assert label == "FULLY SUPPORTED"


def test_python_version_310_312_supported():
    for minor in [10, 12]:
        vi = types.SimpleNamespace(major=3, minor=minor, micro=2)
        ok, ver, label = check_python_version(vi)
        assert ok is True
        assert ver == f"3.{minor}.2"
        assert label == "SUPPORTED"


def test_python_version_39_unsupported():
    vi = types.SimpleNamespace(major=3, minor=9, micro=13)
    ok, ver, label = check_python_version(vi)
    assert ok is False
    assert ver == "3.9.13"
    assert label == "UNSUPPORTED"


def test_python_version_313_warning():
    vi = types.SimpleNamespace(major=3, minor=13, micro=0)
    ok, ver, label = check_python_version(vi)
    assert ok is True
    assert label == "UNTESTED VERSION"


# ==============================================================================
# 2. WRITE PERMISSION CHECKS
# ==============================================================================
def test_write_permissions_success(tmp_path):
    ok, dur_ms, err = check_write_permissions(str(tmp_path))
    assert ok is True
    assert dur_ms >= 0.0
    assert err is None


def test_write_permissions_failure():
    # An invalid path that cannot be written to
    invalid_path = r"Z:\NonExistentDriveDirectory_12345"
    ok, dur_ms, err = check_write_permissions(invalid_path)
    assert ok is False
    assert err is not None


# ==============================================================================
# 3. VIRTUAL ENVIRONMENT HEALTH & SETUP
# ==============================================================================
def test_is_venv_healthy_missing_directory(tmp_path):
    fake_venv = tmp_path / ".venv"
    fake_python = fake_venv / "Scripts" / "python.exe"
    ok, diag = is_venv_healthy(str(fake_venv), str(fake_python))
    assert ok is False
    assert "does not exist" in diag.lower()


def test_is_venv_healthy_missing_python_exe(tmp_path):
    fake_venv = tmp_path / ".venv"
    fake_venv.mkdir()
    fake_python = fake_venv / "Scripts" / "python.exe"
    ok, diag = is_venv_healthy(str(fake_venv), str(fake_python))
    assert ok is False
    assert "missing" in diag.lower()


def test_ensure_virtual_env_creates_when_missing(tmp_path):
    fake_venv = tmp_path / ".venv"
    fake_python = fake_venv / "Scripts" / "python.exe"

    with patch("launcher.is_venv_healthy") as mock_healthy:
        # First check (before creation): unhealthy
        # Second check (after creation): healthy
        mock_healthy.side_effect = [(False, "Missing"), (True, "Healthy")]
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            ok, status, dur = ensure_virtual_env(str(fake_venv), str(fake_python), sys.executable)
            assert ok is True
            assert status == "CREATED"
            assert dur >= 0.0
            mock_run.assert_called_once_with([sys.executable, "-m", "venv", str(fake_venv)], check=True, stdout=-3)


def test_ensure_virtual_env_preserves_healthy(tmp_path):
    fake_venv = tmp_path / ".venv"
    fake_python = fake_venv / "Scripts" / "python.exe"

    with patch("launcher.is_venv_healthy", return_value=(True, "Healthy")):
        with patch("subprocess.run") as mock_run:
            ok, status, dur = ensure_virtual_env(str(fake_venv), str(fake_python), sys.executable)
            assert ok is True
            assert status == "READY"
            mock_run.assert_not_called()


# ==============================================================================
# 4. DEPENDENCY MANAGEMENT & CACHING
# ==============================================================================
def test_requirements_fingerprint_changes_with_content(tmp_path):
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("streamlit>=1.46.0\n", encoding="utf-8")
    fp1 = calculate_requirements_fingerprint(str(req_file))

    req_file.write_text("streamlit>=1.46.0\ngoogle-genai>=2.16.0\n", encoding="utf-8")
    fp2 = calculate_requirements_fingerprint(str(req_file))

    assert fp1 != fp2
    assert ":" in fp1  # Contains hash:py_version


def test_ensure_dependencies_cached(tmp_path):
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("streamlit>=1.46.0\n", encoding="utf-8")
    state_dir = tmp_path / ".project_state"
    state_dir.mkdir()

    # Pre-write matching fingerprint
    fp = calculate_requirements_fingerprint(str(req_file))
    (state_dir / "requirements.fingerprint").write_text(fp, encoding="utf-8")

    fake_python = str(tmp_path / "python.exe")

    with patch("launcher.verify_runtime_dependencies", return_value=True):
        with patch("subprocess.run") as mock_run:
            ok, status, dur = ensure_dependencies(fake_python, str(req_file), str(state_dir))
            assert ok is True
            assert status == "VERIFIED"
            mock_run.assert_not_called()


def test_ensure_dependencies_pip_install_on_mismatch(tmp_path):
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("streamlit>=1.46.0\n", encoding="utf-8")
    state_dir = tmp_path / ".project_state"
    state_dir.mkdir()

    fake_python = str(tmp_path / "python.exe")

    with patch("launcher.verify_runtime_dependencies", return_value=True):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            ok, status, dur = ensure_dependencies(fake_python, str(req_file), str(state_dir))
            assert ok is True
            assert status == "INSTALLED"
            mock_run.assert_called_once_with([fake_python, "-m", "pip", "install", "-r", str(req_file)])
            # Fingerprint was saved
            assert (state_dir / "requirements.fingerprint").exists()


def test_ensure_dependencies_pip_failure(tmp_path):
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("streamlit>=1.46.0\n", encoding="utf-8")
    state_dir = tmp_path / ".project_state"
    state_dir.mkdir()

    fake_python = str(tmp_path / "python.exe")

    with patch("launcher.verify_runtime_dependencies", return_value=False):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            ok, status, dur = ensure_dependencies(fake_python, str(req_file), str(state_dir))
            assert ok is False
            assert "failed" in status.lower()


# ==============================================================================
# 5. ENVIRONMENT CONFIGURATION (.env) TESTS
# ==============================================================================
def test_api_key_validation():
    assert is_api_key_valid("AIzaSyD-1234567890abcdef") is True
    assert is_api_key_valid("my_custom_valid_key_12345") is True

    # Placeholders and invalid formats
    assert is_api_key_valid("") is False
    assert is_api_key_valid(None) is False
    assert is_api_key_valid("   ") is False
    assert is_api_key_valid("your_gemini_api_key_here") is False
    assert is_api_key_valid("your_actual_key_here") is False
    assert is_api_key_valid("None") is False
    assert is_api_key_valid("TODO") is False
    assert is_api_key_valid("short") is False


def test_env_case_a_missing_creates_and_prompts(tmp_path):
    env_file = tmp_path / ".env"
    example_file = tmp_path / ".env.example"
    example_file.write_text("GEMINI_API_KEY=your_gemini_api_key_here\nGEMINI_MODEL=gemini-3.1-flash-lite\n", encoding="utf-8")

    assert not env_file.exists()

    ok, status, msg = ensure_environment_config(str(env_file), str(example_file), open_editor=False)
    assert ok is False
    assert status == "ACTION REQUIRED"
    assert env_file.exists()  # Copied from example
    # Verify example was not mutated
    assert "your_gemini_api_key_here" in example_file.read_text(encoding="utf-8")


def test_env_case_b_placeholder_key_prompts(tmp_path):
    env_file = tmp_path / ".env"
    example_file = tmp_path / ".env.example"
    example_file.write_text("GEMINI_API_KEY=your_gemini_api_key_here\n", encoding="utf-8")
    env_file.write_text("GEMINI_API_KEY=your_gemini_api_key_here\n", encoding="utf-8")

    ok, status, msg = ensure_environment_config(str(env_file), str(example_file), open_editor=False)
    assert ok is False
    assert status == "ACTION REQUIRED"


def test_env_case_c_valid_key_continues(tmp_path):
    env_file = tmp_path / ".env"
    example_file = tmp_path / ".env.example"
    example_file.write_text("GEMINI_API_KEY=your_gemini_api_key_here\n", encoding="utf-8")
    env_file.write_text("GEMINI_API_KEY=AIzaSyD_TestValidKey1234567890\n", encoding="utf-8")

    ok, status, msg = ensure_environment_config(str(env_file), str(example_file), open_editor=False)
    assert ok is True
    assert status == "VALID"


def test_env_never_overwrites_existing_user_env(tmp_path):
    env_file = tmp_path / ".env"
    example_file = tmp_path / ".env.example"
    example_file.write_text("GEMINI_API_KEY=your_gemini_api_key_here\n", encoding="utf-8")
    custom_content = "GEMINI_API_KEY=custom_key_that_user_typed\nCUSTOM_VAR=123\n"
    env_file.write_text(custom_content, encoding="utf-8")

    ensure_environment_config(str(env_file), str(example_file), open_editor=False)
    # File content must remain exactly identical
    assert env_file.read_text(encoding="utf-8") == custom_content


# ==============================================================================
# 6. PORT DETECTION & RUNNING INSTANCE CHECKS
# ==============================================================================
def test_find_free_port():
    port = find_free_port(start_port=8501)
    assert isinstance(port, int)
    assert port >= 8501


def test_check_running_instance_clean_on_stale(tmp_path):
    pid_file = tmp_path / "running_server.pid"
    port_file = tmp_path / "running_server.port"

    # Write a PID that doesn't exist
    pid_file.write_text("9999999", encoding="utf-8")
    port_file.write_text("8501", encoding="utf-8")

    is_running, pid, port = check_running_instance(str(pid_file), str(port_file))
    assert is_running is False
    # Stale files should have been cleaned up
    assert not pid_file.exists()
    assert not port_file.exists()


# ==============================================================================
# 7. PATHS WITH SPACES SUPPORT
# ==============================================================================
def test_paths_with_spaces_supported(tmp_path):
    spaced_dir = tmp_path / "Nobeth Universal OCR Test Folder"
    spaced_dir.mkdir()
    ok, dur, err = check_write_permissions(str(spaced_dir))
    assert ok is True
    assert err is None


def test_env_example_key_synced_if_edited_by_user(tmp_path):
    env_file = tmp_path / ".env"
    example_file = tmp_path / ".env.example"
    # User edited .env.example with their real key, while .env was placeholder
    example_file.write_text("GEMINI_API_KEY=AIzaSyD_UserPastedKeyInExampleFile\n", encoding="utf-8")
    env_file.write_text("GEMINI_API_KEY=your_gemini_api_key_here\n", encoding="utf-8")

    ok, status, msg = ensure_environment_config(str(env_file), str(example_file), open_editor=False)
    assert ok is True
    assert status == "VALID"
    # Verify .env was updated with the user's key from .env.example
    assert "AIzaSyD_UserPastedKeyInExampleFile" in env_file.read_text(encoding="utf-8")

