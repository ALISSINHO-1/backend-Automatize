"""Links de e-mail devem abrir as rotas Flutter Web por hash."""
import pytest

from app.core.config import Settings
from app.services.email_sender import EmailSender


@pytest.mark.parametrize("purpose,path", [
    ("VERIFICAR_EMAIL", "verificar-email"),
    ("REDEFINIR_SENHA", "redefinir-senha"),
])
def test_links_abrem_a_rota_flutter_web(monkeypatch, purpose, path):
    messages = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            assert host == "smtp.example.com"
            assert port == 587

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def ehlo(self):
            pass

        def starttls(self, context):
            pass

        def login(self, user, password):
            assert user == "no-reply@example.com"
            assert password == "senha-teste"

        def send_message(self, message):
            messages.append(message)

    monkeypatch.setattr("app.services.email_sender.smtplib.SMTP", FakeSMTP)
    settings = Settings(
        SMTP_HOST="smtp.example.com",
        SMTP_PORT=587,
        SMTP_USERNAME="no-reply@example.com",
        SMTP_PASSWORD="senha-teste",
        SMTP_FROM_EMAIL="no-reply@example.com",
        PUBLIC_APP_BASE_URL="https://automatize-dev-hml.pages.dev",
    )

    EmailSender(settings).send_token(
        email="cliente@example.com",
        token="token-de-teste-seguro",
        purpose=purpose,
    )

    assert len(messages) == 1
    assert (
        f"https://automatize-dev-hml.pages.dev/#/{path}?token=token-de-teste-seguro"
        in messages[0].get_content()
    )
