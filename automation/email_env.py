"""Merge SMTP settings from environment variables into automation email config."""

from __future__ import annotations

import os


def apply_email_env_overrides(email_notifications: dict) -> None:
    """
    Non-secret defaults stay in JSON; secrets and overrides come from env when set.

    SMTP_AUTOMATION_ENABLED: true/false/1/0 to force enable or disable.
    SMTP_SERVER, SMTP_PORT, SMTP_SENDER_EMAIL, SMTP_SENDER_PASSWORD, SMTP_RECIPIENT_EMAIL
    """
    truthy = {"1", "true", "yes", "on"}
    falsy = {"0", "false", "no", "off"}

    enabled_env = os.getenv("SMTP_AUTOMATION_ENABLED", "").strip().lower()
    if enabled_env in truthy:
        email_notifications["enabled"] = True
    elif enabled_env in falsy:
        email_notifications["enabled"] = False

    server = os.getenv("SMTP_SERVER", "").strip()
    if server:
        email_notifications["smtp_server"] = server

    port_raw = os.getenv("SMTP_PORT", "").strip()
    if port_raw:
        try:
            email_notifications["smtp_port"] = int(port_raw)
        except ValueError:
            pass

    sender = os.getenv("SMTP_SENDER_EMAIL", "").strip()
    if sender:
        email_notifications["sender_email"] = sender

    password = os.getenv("SMTP_SENDER_PASSWORD", "").strip()
    if password:
        email_notifications["sender_password"] = password

    recipient = os.getenv("SMTP_RECIPIENT_EMAIL", "").strip()
    if recipient:
        email_notifications["recipient_email"] = recipient
