import json
from unittest.mock import MagicMock, patch

import pytest
from jinja2 import DictLoader, Environment

from src.components.services.email_service import EmailService

# --- Fixture ---


@pytest.fixture
def email_service():
    # Mock the logger
    mock_logger = MagicMock()
    # Minimal template environment
    mock_env = Environment(loader=DictLoader({}))

    service = EmailService(
        logger=mock_logger,
        api_url="https://fake-api.example.com/send",
        channel_key="fake-channel",
        sender_email="noreply@example.com",
        template_env=mock_env,
    )
    return service


# --- Tests for email validation ---


def test_validate_emails_success(email_service):
    email_service._validate_emails(["test@example.com"], "To")  # should not raise


def test_validate_emails_empty_list(email_service):
    with pytest.raises(ValueError, match="To email list cannot be empty"):
        email_service._validate_emails([], "To")


def test_validate_emails_invalid_email(email_service):
    with pytest.raises(ValueError, match="Invalid To email: bad-email"):
        email_service._validate_emails(["bad-email"], "To")


# --- Tests for _render_html_content ---


def test_render_html_content_success(email_service):
    # Add a dummy template
    email_service.template_env.loader.mapping["fake.html"] = "{{ name }}"
    result = email_service._render_html_content({"name": "User"}, "fake.html")
    assert "User" in result


def test_render_html_content_no_template(email_service):
    result = email_service._render_html_content("body text", None)
    assert result is None


def test_render_html_content_failure(email_service):
    # Patch get_template to raise exception
    email_service.template_env.get_template = MagicMock(
        side_effect=Exception("Render fail")
    )
    with pytest.raises(Exception, match="Render fail"):
        email_service._render_html_content({"name": "User"}, "bad.html")


# --- Tests for _validate_inputs ---


def test_validate_inputs_success(email_service):
    email_service._validate_inputs(
        ["to@example.com"], "Subject", "Body", ["cc@example.com"], ["bcc@example.com"]
    )


def test_validate_inputs_invalid_subject(email_service):
    with pytest.raises(ValueError, match="Subject must be a non-empty string"):
        email_service._validate_inputs(["to@example.com"], "", "Body", None, None)


def test_validate_inputs_missing_body(email_service):
    with pytest.raises(ValueError, match="Body cannot be empty"):
        email_service._validate_inputs(["to@example.com"], "Hello", None, None, None)


# --- Tests for _build_payload ---


def test_build_payload_with_html(email_service):
    email_service._render_html_content = MagicMock(return_value="<html>Rendered</html>")
    payload = email_service._build_payload(
        ["to@example.com"],
        "Subject",
        {"k": "v"},
        ["cc@example.com"],
        ["bcc@example.com"],
        "template.html",
        [{"filename": "f.txt", "content": "abc"}],
    )
    assert payload["html_content"] == "<html>Rendered</html>"
    assert "attachments" in payload
    assert payload["body"] == json.dumps({"k": "v"})


def test_build_payload_without_html(email_service):
    payload = email_service._build_payload(
        ["to@example.com"],
        "Subject",
        "Just a string",
        None,
        None,
        None,
        None,
    )
    assert "html_content" not in payload
    assert payload["body"] == "Just a string"


# --- Tests for _make_api_call ---


@patch("src.components.services.email_service.requests.post")
def test_make_api_call_success(mock_post, email_service):
    fake_resp = MagicMock()
    fake_resp.json.return_value = {"task_id": "123"}
    fake_resp.raise_for_status.return_value = None
    mock_post.return_value = fake_resp

    payload = {"to_emails": ["a@b.com"]}
    result = email_service._make_api_call(payload)

    assert result == {"task_id": "123"}
    mock_post.assert_called_once()


@patch("src.components.services.email_service.requests.post")
def test_make_api_call_retries_and_fails(mock_post, email_service):
    mock_post.side_effect = Exception("Network error")

    payload = {"to_emails": ["a@b.com"]}
    with pytest.raises(ValueError, match="Email API call failed: Network error"):
        email_service._make_api_call(payload)

    assert mock_post.call_count == 3  # retry logic tested


# --- Tests for send_email ---


@patch.object(EmailService, "_make_api_call", return_value={"status": "ok"})
def test_send_email_success(mock_api, email_service):
    email_service._render_html_content = MagicMock(return_value=None)
    result = email_service.send_email(
        to_emails=["to@example.com"],
        subject="Hi",
        body="Body",
    )
    assert result == {"status": "ok"}
    mock_api.assert_called_once()


@patch.object(EmailService, "_make_api_call", return_value={"status": "ok"})
def test_send_email_with_template_and_attachments(mock_api, email_service):
    email_service._render_html_content = MagicMock(return_value="<html>Hello</html>")
    result = email_service.send_email(
        to_emails=["to@example.com"],
        subject="Hi",
        body={"name": "user"},
        cc_emails=["cc@example.com"],
        bcc_emails=["bcc@example.com"],
        html_template="template.html",
        attachments=[{"filename": "file.txt", "content": "ZGF0YQ=="}],
    )
    assert "status" in result
    mock_api.assert_called_once()
