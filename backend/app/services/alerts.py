from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


class SourceAlertService:
    @staticmethod
    def _get_recipients() -> list[str]:
        raw = (settings.alert_email_to or os.getenv("ALERT_EMAIL_TO") or "").replace(";", ",")
        return [value.strip() for value in raw.split(",") if value.strip()]

    @staticmethod
    def _smtp_config() -> tuple[str | None, int, str | None, str | None, bool, str | None]:
        host = settings.smtp_host or os.getenv("SMTP_HOST")
        port = int(settings.smtp_port or os.getenv("SMTP_PORT") or 587)
        username = settings.smtp_username or os.getenv("SMTP_USERNAME")
        password = settings.smtp_password or os.getenv("SMTP_PASSWORD")
        use_tls = bool(settings.smtp_use_tls if settings.smtp_use_tls is not None else os.getenv("SMTP_USE_TLS", "true").lower() not in {"0", "false", "no"})
        sender = settings.alert_email_from or os.getenv("ALERT_EMAIL_FROM")
        return host, port, username, password, use_tls, sender

    @classmethod
    def notify_source_failure(
        cls,
        source_name: str,
        error: str,
        *,
        source_id: int | None = None,
        source_url: str | None = None,
    ) -> bool:
        subject = f"Defense Brief source failure: {source_name}"
        source_label = f" (ID {source_id})" if source_id is not None else ""
        body_lines = [
            f"Source: {source_name}{source_label}",
            f"Website: {source_url or 'Not provided'}",
            f"Error: {error}",
            "This is an automated alert from the Defense Brief collection pipeline.",
        ]
        message = "\n".join(body_lines)

        logger.warning("Source collection failed for %s: %s", source_name, error)

        recipients = cls._get_recipients()
        host, port, username, password, use_tls, sender = cls._smtp_config()

        if not host or not recipients:
            logger.info("SMTP alerting is not configured; source failure was only logged for %s", source_name)
            return False

        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = sender or username or "noreply@localhost"
            msg["To"] = ", ".join(recipients)
            msg.set_content(message)

            if use_tls:
                with smtplib.SMTP(host, port) as server:
                    server.starttls()
                    if username and password:
                        server.login(username, password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(host, port) as server:
                    if username and password:
                        server.login(username, password)
                    server.send_message(msg)

            logger.info("Sent source failure alert for %s to %s", source_name, recipients)
            return True
        except Exception:
            logger.exception("Failed to send source failure alert for %s", source_name)
            return False


def alert_source_failure(
    source_name: str,
    error: str,
    *,
    source_id: int | None = None,
    source_url: str | None = None,
) -> bool:
    return SourceAlertService.notify_source_failure(
        source_name,
        error,
        source_id=source_id,
        source_url=source_url,
    )


def notify_health_summary(summaries: list[dict]) -> bool:
    """Send an aggregated health summary email for multiple sources.

    `summaries` is a list of dicts containing at least: name, source_id, status, last_success_at, last_failure_at
    """
    if not summaries:
        return False

    recipients = SourceAlertService._get_recipients()
    host, port, username, password, use_tls, sender = SourceAlertService._smtp_config()

    if not host or not recipients:
        logger.info("SMTP alerting is not configured; health summary not sent")
        return False

    critical = [s for s in summaries if s.get('status') == 'critical']
    warning = [s for s in summaries if s.get('status') == 'warning']
    paused = [s for s in summaries if s.get('status') == 'paused']

    subject = f"Defense Brief: Health summary — {len(critical)} critical, {len(warning)} warning, {len(paused)} paused"

    lines = [
        "Defense Brief — automated health summary",
        "",
        f"Critical: {len(critical)}",
    ]
    if critical:
        lines.append("")
        lines.append("Critical sources:")
        for s in critical:
            lines.append(f"- {s.get('name')} (ID {s.get('source_id')}) — last_success: {s.get('last_success_at')}, last_failure: {s.get('last_failure_at')}")

    if warning:
        lines.append("")
        lines.append(f"Warning: {len(warning)}")
        lines.append("")
        lines.append("Warning sources:")
        for s in warning:
            lines.append(f"- {s.get('name')} (ID {s.get('source_id')}) — last_success: {s.get('last_success_at')}")

    if paused:
        lines.append("")
        lines.append(f"Paused: {len(paused)}")
        lines.append("")
        lines.append("Paused sources:")
        for s in paused:
            lines.append(f"- {s.get('name')} (ID {s.get('source_id')})")

    message = "\n".join(lines)

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = sender or username or "noreply@localhost"
        msg["To"] = ", ".join(recipients)
        msg.set_content(message)

        if use_tls:
            with smtplib.SMTP(host, port) as server:
                server.starttls()
                if username and password:
                    server.login(username, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port) as server:
                if username and password:
                    server.login(username, password)
                server.send_message(msg)

        logger.info("Sent health summary alert to %s", recipients)
        return True
    except Exception:
        logger.exception("Failed to send health summary alert")
        return False
