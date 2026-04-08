from __future__ import annotations

import json
import smtplib
import ssl
from email.message import EmailMessage
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..models import NotificationDeliveryResult
from .slack_service import SlackService
from .settings_service import SettingsService


class NotificationService:
    def __init__(self, settings_service: SettingsService) -> None:
        self.settings_service = settings_service
        self.slack_service = SlackService(settings_service)

    def notify(
        self,
        *,
        event: str,
        title: str,
        lines: list[str],
    ) -> list[NotificationDeliveryResult]:
        settings = self.settings_service.get_settings()
        if not getattr(settings.events, event, False):
            return []

        message = self._build_message(title=title, lines=lines)
        results: list[NotificationDeliveryResult] = []

        if settings.email.enabled:
            results.append(
                self._send_email(
                    subject=title,
                    message=message,
                    smtp_host=settings.email.smtp_host,
                    smtp_port=settings.email.smtp_port,
                    smtp_username=settings.email.smtp_username,
                    smtp_password=settings.email.smtp_password,
                    from_address=settings.email.from_address,
                    to_addresses=settings.email.to_addresses,
                    use_tls=settings.email.use_tls,
                )
            )
        if settings.slack.enabled:
            results.append(self.slack_service.send_plain_text(title, lines))
        if settings.whatsapp.enabled:
            results.append(
                self._send_whatsapp(
                    message=message,
                    access_token=settings.whatsapp.access_token,
                    phone_number_id=settings.whatsapp.phone_number_id,
                    recipient_number=settings.whatsapp.recipient_number,
                    api_version=settings.whatsapp.api_version,
                )
            )
        return results

    def send_test(self, *, channel: str) -> NotificationDeliveryResult:
        settings = self.settings_service.get_settings()
        message = self._build_message(
            title="GigOptimizer Pro test notification",
            lines=[
                "The notification channel is configured and reachable.",
                "You can now route live gig alerts from the dashboard.",
            ],
        )
        if channel == "slack":
            return self.slack_service.send_plain_text("GigOptimizer Pro test notification", [
                "The Slack channel is configured and reachable.",
                "Structured alerts can now flow from comparison, jobs, and reports.",
            ])
        if channel == "email":
            return self._send_email(
                subject="GigOptimizer Pro test email",
                message=message,
                smtp_host=settings.email.smtp_host,
                smtp_port=settings.email.smtp_port,
                smtp_username=settings.email.smtp_username,
                smtp_password=settings.email.smtp_password,
                from_address=settings.email.from_address,
                to_addresses=settings.email.to_addresses,
                use_tls=settings.email.use_tls,
            )
        if channel == "whatsapp":
            return self._send_whatsapp(
                message=message,
                access_token=settings.whatsapp.access_token,
                phone_number_id=settings.whatsapp.phone_number_id,
                recipient_number=settings.whatsapp.recipient_number,
                api_version=settings.whatsapp.api_version,
            )
        return NotificationDeliveryResult(channel=channel, ok=False, detail="Unsupported notification channel.")

    def _build_message(self, *, title: str, lines: list[str]) -> str:
        body = "\n".join(f"- {line}" for line in lines if line)
        return f"{title}\n{body}" if body else title

    def _send_email(
        self,
        *,
        subject: str,
        message: str,
        smtp_host: str,
        smtp_port: int,
        smtp_username: str,
        smtp_password: str,
        from_address: str,
        to_addresses: list[str],
        use_tls: bool,
    ) -> NotificationDeliveryResult:
        if not smtp_host or not smtp_username or not smtp_password or not from_address or not to_addresses:
            return NotificationDeliveryResult(
                channel="email",
                ok=False,
                detail="Email SMTP host, credentials, sender, or recipients are missing.",
            )
        email = EmailMessage()
        email["Subject"] = subject
        email["From"] = from_address
        email["To"] = ", ".join(to_addresses)
        email.set_content(message)

        try:
            if use_tls:
                with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as client:
                    client.starttls(context=ssl.create_default_context())
                    client.login(smtp_username, smtp_password)
                    client.send_message(email)
            else:
                with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20, context=ssl.create_default_context()) as client:
                    client.login(smtp_username, smtp_password)
                    client.send_message(email)
            return NotificationDeliveryResult(channel="email", ok=True, detail="Email notification sent.")
        except Exception as exc:
            return NotificationDeliveryResult(channel="email", ok=False, detail=str(exc))

    def _send_whatsapp(
        self,
        *,
        message: str,
        access_token: str,
        phone_number_id: str,
        recipient_number: str,
        api_version: str,
    ) -> NotificationDeliveryResult:
        if not access_token or not phone_number_id or not recipient_number:
            return NotificationDeliveryResult(
                channel="whatsapp",
                ok=False,
                detail="WhatsApp Cloud API token, phone number ID, or recipient number is missing.",
            )
        url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_number,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message[:4096],
            },
        }
        return self._post_json(
            channel="whatsapp",
            url=url,
            payload=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
            },
        )

    def _post_json(
        self,
        *,
        channel: str,
        url: str,
        payload: dict,
        headers: dict[str, str],
    ) -> NotificationDeliveryResult:
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                **headers,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:
                detail = f"{channel} notification sent ({response.status})."
                return NotificationDeliveryResult(channel=channel, ok=200 <= response.status < 300, detail=detail)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore") if hasattr(exc, "read") else str(exc)
            return NotificationDeliveryResult(channel=channel, ok=False, detail=detail or str(exc))
        except URLError as exc:
            return NotificationDeliveryResult(channel=channel, ok=False, detail=str(exc.reason))
