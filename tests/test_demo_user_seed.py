from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.domain.models.enums import PerfilEnum
from app.domain.models.user import User
from scripts.seed_demo_user import DemoUserSettings, seed_demo_user


def demo_settings(**overrides) -> DemoUserSettings:
    return DemoUserSettings(_env_file=None, **({
        "DEMO_USER_NAME": "Cliente de demonstração",
        "DEMO_USER_EMAIL": "demo@example.com",
        "DEMO_USER_PASSWORD": "senha-ficticia-de-teste",
    } | overrides))


def test_seed_creates_login_compatible_hash_and_can_be_repeated():
    db = MagicMock(spec=Session)
    db.scalar.return_value = None
    configured = demo_settings()
    user, created = seed_demo_user(db, configured)

    assert created
    assert user.email == configured.DEMO_USER_EMAIL
    assert user.perfil == PerfilEnum.CLIENTE
    assert user.ativo is True
    assert user.senha_hash != configured.DEMO_USER_PASSWORD.get_secret_value()
    assert verify_password(configured.DEMO_USER_PASSWORD.get_secret_value(), user.senha_hash)
    db.commit.assert_called_once()
    db.rollback.assert_not_called()

    original_hash = user.senha_hash
    db.reset_mock()
    db.scalar.return_value = user
    existing, created = seed_demo_user(db, demo_settings(DEMO_USER_PASSWORD="outra-senha"))
    assert existing is user and not created
    assert existing.senha_hash == original_hash
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_seed_rolls_back_failure_without_persisting_plain_password():
    db = MagicMock(spec=Session)
    db.scalar.return_value = None
    db.flush.side_effect = RuntimeError("persistence failure")
    with pytest.raises(RuntimeError, match="persistence failure"):
        seed_demo_user(db, demo_settings())
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_seed_handles_concurrent_unique_email_insert():
    db = MagicMock(spec=Session)
    winner = User(id=uuid4(), nome="Existing", email="demo@example.com", senha_hash="existing")
    db.scalar.side_effect = [None, winner]
    db.flush.side_effect = IntegrityError("INSERT", {}, Exception("unique"))
    user, created = seed_demo_user(db, demo_settings())
    assert user is winner and not created
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_seed_does_not_hide_unrelated_integrity_error():
    db = MagicMock(spec=Session)
    db.scalar.return_value = None
    db.flush.side_effect = IntegrityError("INSERT", {}, Exception("unrelated"))
    with pytest.raises(IntegrityError):
        seed_demo_user(db, demo_settings())
    db.rollback.assert_called_once()


@pytest.mark.parametrize("password", ["", "x" * 73, "é" * 37])
def test_seed_rejects_invalid_password_without_echoing_it(password):
    with pytest.raises(ValueError) as error:
        demo_settings(DEMO_USER_PASSWORD=password)
    assert "input_value" not in str(error.value)
    if password:
        assert password not in str(error.value)


@pytest.mark.parametrize("overrides", [
    {"DEMO_USER_NAME": " "}, {"DEMO_USER_EMAIL": "invalid-email"},
])
def test_seed_validates_identity(overrides):
    with pytest.raises(ValueError):
        demo_settings(**overrides)


def test_seed_password_is_hidden_in_representation():
    configured = demo_settings()
    assert configured.DEMO_USER_PASSWORD.get_secret_value() not in repr(configured)
