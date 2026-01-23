import smtplib
import requests

class WebhookDispatcher:
    """
    Sends POST payloads to webhook endpoints.
    """
    def send(self, url, payload: dict):
        try:
            return requests.post(url, json=payload, timeout=5)
        except Exception as e:
            return {"error": str(e)}


class EmailDispatcher:
    """
    Sends email notifications (SMTP scaffold).
    """
    def __init__(self, smtp_host=None, smtp_port=587, username=None, password=None):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password

    def send(self, to_email, subject, body):
        message = f"Subject: {subject}\n\n{body}"
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.sendmail(self.username, to_email, message)
        except Exception as e:
            return {"error": str(e)}
