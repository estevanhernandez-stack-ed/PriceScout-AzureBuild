
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, UTC
from app.security_config import (
    validate_password_strength,
    is_default_password,
    get_json_depth,
    sanitize_log_data,
    sanitize_sql_like_pattern,
    sanitize_filename,
    get_security_config,
    check_login_attempts,
    record_failed_login,
    reset_login_attempts,
    validate_uploaded_file
)

class MockSessionState(dict):
    def __getattr__(self, key):
        return self.get(key)
    def __setattr__(self, key, value):
        self[key] = value

def test_validate_password_strength():
    # Valid password
    valid, msg = validate_password_strength("Password123!")
    assert valid is True
    assert msg == ""

    # Too short
    valid, msg = validate_password_strength("Short1!")
    assert valid is False
    assert "at least 8 characters" in msg

    # No uppercase
    valid, msg = validate_password_strength("password123!")
    assert valid is False
    assert "uppercase letter" in msg

    # No lowercase
    valid, msg = validate_password_strength("PASSWORD123!")
    assert valid is False
    assert "lowercase letter" in msg

    # No digit
    valid, msg = validate_password_strength("Password!!!")
    assert valid is False
    assert "number" in msg

    # No special char
    valid, msg = validate_password_strength("Password123")
    assert valid is False
    assert "special character" in msg

def test_is_default_password():
    assert is_default_password("admin", "admin") is True
    assert is_default_password("admin", "wrong") is False
    assert is_default_password("user", "admin") is False

def test_get_json_depth():
    assert get_json_depth({"a": 1}) == 1
    assert get_json_depth({"a": {"b": 2}}) == 2
    assert get_json_depth([{"a": 1}, {"b": {"c": 3}}]) == 3
    assert get_json_depth("simple string") == 0

def test_sanitize_log_data():
    data = {
        "username": "testuser",
        "password": "secretpassword",
        "some_long_id": "ABC1234567890XYZ1234567890", # Should be truncated
        "api_key": "sk-1234567890abcdef12345", # Should be redacted due to key name
        "nested": {
            "token": "bearer-token-123"
        },
        "list": [{"auth": "abc"}, "normal"]
    }
    sanitized = sanitize_log_data(data)
    
    assert sanitized["username"] == "testuser"
    assert sanitized["password"] == "***REDACTED***"
    assert sanitized["some_long_id"] == "ABC1...7890" 
    assert sanitized["api_key"] == "***REDACTED***"
    assert sanitized["nested"]["token"] == "***REDACTED***"
    assert sanitized["list"][0]["auth"] == "***REDACTED***"
    assert sanitized["list"][1] == "normal"

def test_sanitize_sql_like_pattern():
    assert sanitize_sql_like_pattern("test%pattern_") == r"test\%pattern\_"

def test_sanitize_filename():
    assert sanitize_filename("../../etc/passwd") == "etcpasswd"
    assert sanitize_filename("safe_file.json") == "safe_file.json"
    assert sanitize_filename("file<name>.db") == "filename.db"

def test_get_security_config():
    config = get_security_config()
    assert "max_login_attempts" in config
    assert config["max_login_attempts"] == 5

@patch("streamlit.session_state", MockSessionState())
def test_login_attempts_flow():
    with patch("streamlit.error") as mock_error, patch("streamlit.warning") as mock_warning:
        username = "test_user"
        assert check_login_attempts(username) is True
        for i in range(5):
            record_failed_login(username)
        assert check_login_attempts(username) is False
        mock_error.assert_called()
        reset_login_attempts(username)
        assert check_login_attempts(username) is True

def test_validate_uploaded_file():
    mock_file = MagicMock()
    
    # 1. Valid JSON
    mock_file.getvalue.return_value = b'{"a": 1, "b": 2}'
    valid, msg = validate_uploaded_file(mock_file, "json")
    assert valid is True
    
    # 2. Too nested JSON
    # Code uses depth > MAX_JSON_DEPTH (which is 10 by default)
    mock_file.getvalue.return_value = b'{"a": ' * 12 + b'1' + b'}' * 12
    valid, msg = validate_uploaded_file(mock_file, "json")
    assert valid is False
    assert "too deeply nested" in msg
    
    # 3. Invalid JSON
    mock_file.getvalue.return_value = b'{"a": 1'
    valid, msg = validate_uploaded_file(mock_file, "json")
    assert valid is False
    assert "Invalid JSON" in msg
    
    # 4. Valid DB
    mock_file.getvalue.return_value = b"SQLite format 3\x00" + b"x" * 100
    valid, msg = validate_uploaded_file(mock_file, "db")
    assert valid is True

def test_check_session_timeout():
    from app.security_config import check_session_timeout
    
    # 1. No last_activity
    real_state = MockSessionState()
    with patch("streamlit.session_state", real_state):
        assert check_session_timeout() is True
        assert "last_activity" in real_state
    
    # 2. Timed out
    with patch("streamlit.warning") as mock_warn:
        real_state = MockSessionState({
            "last_activity": datetime.now() - timedelta(minutes=61),
            "user_name": "testuser"
        })
        with patch("streamlit.session_state", real_state):
            with patch("app.users.clear_session_token"), patch("app.cookie_manager.clear_login_cookie"):
                assert check_session_timeout() is False
                assert len(real_state) == 0
                mock_warn.assert_called()
