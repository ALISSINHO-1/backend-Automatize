"""Password resets revoke tokens from prior sessions immediately."""
from app.core.security import create_access_token
from app.domain.models.enums import PerfilEnum
from tests.test_demandas_auth import api, fake_db, make_user  # noqa: F401


def test_redefinir_senha_invalida_jwt_emitido_antes(api, fake_db):
    client, _, settings = api
    user = make_user(PerfilEnum.CLIENTE)
    user.token_version = 0
    fake_db.users[user.id] = user
    old_token = create_access_token(str(user.id), settings, token_version=0)
    headers = {"Authorization": "Bearer " + old_token}
    assert client.get("/auth/me", headers=headers).status_code == 200
    user.token_version = 1
    assert client.get("/auth/me", headers=headers).status_code == 401
    new_token = create_access_token(str(user.id), settings, token_version=1)
    assert client.get("/auth/me", headers={"Authorization": "Bearer " + new_token}).status_code == 200


def test_token_version_que_nao_seja_inteiro_e_rejeitado(api, fake_db):
    from datetime import datetime, timezone
    from jose import jwt

    client, _, settings = api
    user = make_user(PerfilEnum.CLIENTE)
    fake_db.users[user.id] = user
    now = int(datetime.now(timezone.utc).timestamp())
    token = jwt.encode(
        {"sub": str(user.id), "iat": now, "exp": now + 300, "ver": "ADMIN"},
        settings.JWT_SECRET_KEY, algorithm="HS256",
    )
    assert client.get("/auth/me", headers={"Authorization": "Bearer " + token}).status_code == 401
