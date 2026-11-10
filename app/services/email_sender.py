"""SMTP TLS obrigatorio. Links nunca sao registrados em log."""
from email.message import EmailMessage
import smtplib
import ssl
from urllib.parse import urlencode, urlparse

from app.core.config import Settings


class EmailDeliveryError(RuntimeError):
    pass


class EmailSender:
    def __init__(self, settings: Settings):
        self.settings = settings

    @staticmethod
    def ready(settings: Settings) -> bool:
        base = settings.PUBLIC_APP_BASE_URL or ""
        parsed = urlparse(base)
        return bool(
            settings.SMTP_HOST and settings.SMTP_USERNAME
            and settings.SMTP_PASSWORD
            and settings.SMTP_FROM_EMAIL
            and parsed.scheme == "https"
            and parsed.netloc and not parsed.username
            and not parsed.password and not parsed.query
            and not parsed.fragment
        )

    def send_token(self, *, email: str, token: str, purpose: str) -> None:
        if not self.ready(self.settings):
            raise EmailDeliveryError("Envio de email nao configurado.")
        is_verification = purpose == "VERIFICAR_EMAIL"
        if purpose not in ("VERIFICAR_EMAIL", "REDEFINIR_SENHA"):
            raise ValueError("Finalidade de token invalida.")
        path = "verificar-email" if is_verification else "redefinir-senha"
        url = (self.settings.PUBLIC_APP_BASE_URL or "").rstrip("/") + "/" + path + "?" + urlencode({"token": token})
        message = EmailMessage()
        message["From"] = self.settings.SMTP_FROM_EMAIL
        message["To"] = email
        message["Subject"] = (
            "Confirme seu e-mail no Automatize"
            if is_verification else "Redefina sua senha no Automatize"
        )
        message.set_content(
            ("Confirme seu e-mail no Automatize: " if is_verification
             else "Redefina sua senha no Automatize: ")
            + url + "\n\n"
            + "Este link e de uso unico e expira em "
            + ("30 minutos." if is_verification else "15 minutos.")
            + " Se nao solicitou, ignore esta mensagem.\n"
        )
        try:
            with smtplib.SMTP(self.settings.SMTP_HOST, self.settings.SMTP_PORT, timeout=8) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
                smtp.login(
                    self.settings.SMTP_USERNAME,
                    self.settings.SMTP_PASSWORD.get_secret_value(),
                )
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            # Nunca registrar senha/token no log e nem devolver causa de transporte.
            raise EmailDeliveryError("Falha ao enviar mensagem de verificacao.") from None
