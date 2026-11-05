import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy.dialects.postgresql import dialect

from app.core.database import get_db
from app.domain.models.enums import PerfilEnum, StatusPedidoEnum
from app.domain.models.pedido import Pedido
from app.domain.models.user import User
from app.repositories.pedido_repository import PedidoRepository


SECRET = "demandas-test-secret-" + "x" * 32
PASSWORD = "senha correta"


class FakeSession:
    """Small in-memory persistence double that honors SQL equality filters."""

    def __init__(self):
        self.users: dict[UUID, User] = {}
        self.demands: list[Pedido] = []
        self.error: Exception | None = None

    def get(self, model, entity_id):
        if self.error:
            raise self.error
        if model is User:
            return self.users.get(entity_id)
        return next((item for item in self.demands if item.id == entity_id), None)

    def _records_for(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        return list(self.users.values()) if entity is User else list(self.demands)

    @staticmethod
    def _filtered(records, statement):
        for criterion in statement._where_criteria:
            key = getattr(criterion.left, "key", None)
            value = getattr(criterion.right, "value", None)
            if key is not None:
                records = [record for record in records if getattr(record, key) == value]
        return records

    def scalar(self, statement):
        if self.error:
            raise self.error
        records = self._filtered(self._records_for(statement), statement)
        return records[0] if records else None

    def scalars(self, statement):
        if self.error:
            raise self.error
        records = self._filtered(self._records_for(statement), statement)
        records.sort(
            key=lambda item: (
                item.created_at is None,
                item.created_at or datetime.max.replace(tzinfo=timezone.utc),
                item.id.int,
            )
        )
        offset = statement._offset_clause.value if statement._offset_clause is not None else 0
        limit = statement._limit_clause.value if statement._limit_clause is not None else None
        return _FakeScalarResult(records[offset : offset + limit if limit is not None else None])

    def close(self):
        pass


class _FakeScalarResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


def make_user(
    perfil: PerfilEnum | str = PerfilEnum.CLIENTE,
    *,
    user_id: UUID | None = None,
    active: bool | None = True,
    password_hash: str = "unused",
) -> User:
    return User(
        id=user_id or uuid4(),
        nome="Usuário de teste",
        email=f"{uuid4()}@example.com",
        senha_hash=password_hash,
        perfil=perfil,
        ativo=active,
    )


def make_demand(
    client_id: UUID,
    *,
    assigned_id: UUID | None = None,
    demand_id: UUID | None = None,
    created_at: datetime | None = None,
    description: str | None = "Descrição de teste",
    percentage: Decimal | None = Decimal("37.50"),
) -> Pedido:
    timestamp = created_at or datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)
    return Pedido(
        id=demand_id or uuid4(),
        codigo_identificador=f"DEM-{uuid4().hex[:8]}",
        titulo="Demanda de teste",
        descricao=description,
        status=StatusPedidoEnum.PLANEAMENTO,
        percentual_progresso=percentage,
        cliente_id=client_id,
        responsavel_id=assigned_id,
        created_at=timestamp,
        updated_at=timestamp,
    )


def make_token(
    subject: str | int | None,
    *,
    key: str = SECRET,
    algorithm: str = "HS256",
    claims: dict | None = None,
) -> str:
    now = int(datetime.now(timezone.utc).timestamp())
    payload = {"sub": subject, "iat": now - 1, "exp": now + 300}
    if claims is not None:
        payload.update(claims)
    return jwt.encode(payload, key, algorithm=algorithm)


def changed_payload(token: str) -> str:
    header, _payload, signature = token.split(".")
    replacement = base64.urlsafe_b64encode(
        json.dumps({"sub": "tampered"}).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{replacement}.{signature}"


def signed_raw_payload(payload_json: str) -> str:
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(payload_json.encode()).rstrip(b"=").decode()
    signing_input = f"{header}.{payload}".encode()
    signature = hmac.new(SECRET.encode(), signing_input, hashlib.sha256).digest()
    signature_segment = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    return f"{header}.{payload}.{signature_segment}"


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from app.core.config import Settings
    from app.main import create_app

    configured_settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+psycopg2://unit:unit@localhost:5432/unit_test",
        JWT_SECRET_KEY=SECRET,
        ACCESS_TOKEN_EXPIRE_MINUTES=5,
    )
    application = create_app(configured_settings)
    with TestClient(application, raise_server_exceptions=False) as client:
        yield client, application, configured_settings
    application.dependency_overrides.clear()


@pytest.fixture
def fake_db(api):
    _client, application, _settings = api
    session = FakeSession()

    def override_db():
        yield session

    application.dependency_overrides[get_db] = override_db
    return session


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_token_issued_by_json_login_is_accepted_by_protected_route(api, fake_db):
    client, _application, settings = api
    from app.core.security import hash_password

    user = make_user(password_hash=hash_password(PASSWORD))
    fake_db.users[user.id] = user
    demand = make_demand(user.id)
    fake_db.demands = [demand, make_demand(uuid4())]

    login = client.post(
        "/auth/login",
        json={"email": user.email, "senha": PASSWORD},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])["sub"] == str(user.id)

    response = client.get("/demandas", headers=bearer(token))
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(demand.id)]


@pytest.mark.parametrize(
    "authorization",
    [None, "Basic abc", "Bearer", "Bearer a b"],
    ids=["missing", "wrong-scheme", "empty-bearer", "malformed-token"],
)
def test_missing_or_malformed_bearer_is_generic_401(api, fake_db, authorization):
    client, _application, _settings = api
    headers = {} if authorization is None else {"Authorization": authorization}
    response = client.get("/demandas", headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "Não foi possível autenticar."}


def test_invalid_signatures_algorithms_and_claims_are_generic_401(api, fake_db):
    client, _application, _settings = api
    now = int(datetime.now(timezone.utc).timestamp())
    valid = make_token(str(uuid4()))
    cases = [
        make_token(str(uuid4()), key="different-secret-" + "x" * 32),
        make_token(str(uuid4()), algorithm="HS384"),
        changed_payload(valid),
        make_token(str(uuid4()), claims={"sub": None}),
        make_token(str(uuid4()), claims={"iat": None}),
        make_token(str(uuid4()), claims={"iat": "123"}),
        make_token(str(uuid4()), claims={"exp": 1.5}),
        signed_raw_payload('["not", "a", "claims", "object"]'),
        make_token("not-a-uuid"),
        make_token(123),
        make_token(str(uuid4()), claims={"iat": now + 60, "exp": now + 600}),
        make_token(str(uuid4()), claims={"iat": now - 10, "exp": now - 10}),
        make_token(str(uuid4()), claims={"iat": now - 100, "exp": now - 1}),
    ]
    incomplete = [
        {"iat": now - 1, "exp": now + 300},
        {"sub": str(uuid4()), "exp": now + 300},
        {"sub": str(uuid4()), "iat": now - 1},
    ]
    cases.extend(jwt.encode(claims, SECRET, algorithm="HS256") for claims in incomplete)

    responses = [client.get("/demandas", headers=bearer(token)) for token in cases]
    assert all(response.status_code == 401 for response in responses)
    assert all(response.headers["www-authenticate"] == "Bearer" for response in responses)
    assert all(response.json() == {"detail": "Não foi possível autenticar."} for response in responses)


def test_user_must_exist_and_be_active(api, fake_db):
    client, _application, _settings = api
    missing_id = uuid4()
    inactive = make_user(active=False)
    fake_db.users[inactive.id] = inactive

    for token in (make_token(str(missing_id)), make_token(str(inactive.id))):
        response = client.get("/demandas", headers=bearer(token))
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.json() == {"detail": "Não foi possível autenticar."}


def test_database_failure_during_user_lookup_is_not_401(api, fake_db):
    client, _application, _settings = api
    fake_db.error = RuntimeError("database-secret")

    response = client.get("/demandas", headers=bearer(make_token(str(uuid4()))))

    assert response.status_code == 500
    assert response.status_code != 401
    assert "database-secret" not in response.text


def test_each_application_uses_its_injected_jwt_secret(api, fake_db, tmp_path, monkeypatch):
    client_a, _application_a, settings_a = api
    user = make_user()
    fake_db.users[user.id] = user
    token = make_token(str(user.id), key=settings_a.JWT_SECRET_KEY)

    from app.core.config import Settings
    from app.main import create_app

    settings_b = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+psycopg2://unit:unit@localhost:5432/unit_test",
        JWT_SECRET_KEY="second-application-secret-" + "x" * 32,
    )
    application_b = create_app(settings_b)
    application_b.dependency_overrides[get_db] = lambda: _yield(fake_db)
    with TestClient(application_b, raise_server_exceptions=False) as client_b:
        response = client_b.get("/demandas", headers=bearer(token))
    application_b.dependency_overrides.clear()

    assert client_a.get("/demandas", headers=bearer(token)).status_code == 200
    assert response.status_code == 401


def _yield(value):
    yield value


def test_access_policy_is_applied_to_list_and_detail_before_pagination(api, fake_db):
    client, _application, _settings = api
    client_user = make_user(PerfilEnum.CLIENTE)
    technician = make_user(PerfilEnum.TECNICO)
    administrator = make_user(PerfilEnum.ADMIN)
    fake_db.users.update({
        client_user.id: client_user,
        technician.id: technician,
        administrator.id: administrator,
    })
    first = make_demand(client_user.id, assigned_id=technician.id, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    second = make_demand(client_user.id, assigned_id=uuid4(), created_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
    technician_only = make_demand(uuid4(), assigned_id=technician.id, created_at=datetime(2026, 1, 3, tzinfo=timezone.utc))
    other = make_demand(uuid4(), assigned_id=uuid4(), created_at=datetime(2026, 1, 4, tzinfo=timezone.utc))
    fake_db.demands = [other, second, technician_only, first]

    for user, expected in (
        (administrator, {first.id, second.id, technician_only.id, other.id}),
        (client_user, {first.id, second.id}),
        (technician, {first.id, technician_only.id}),
    ):
        token = make_token(str(user.id))
        response = client.get("/demandas", headers=bearer(token))
        assert response.status_code == 200
        assert {UUID(item["id"]) for item in response.json()} == expected

        for demand in fake_db.demands:
            detail = client.get(f"/demandas/{demand.id}", headers=bearer(token))
            if demand.id in expected:
                assert detail.status_code == 200
            else:
                assert detail.status_code == 404

    token = make_token(str(client_user.id))
    page = client.get("/demandas?offset=1&limit=1", headers=bearer(token))
    assert page.status_code == 200
    assert [item["id"] for item in page.json()] == [str(second.id)]


def test_unknown_profile_is_forbidden_and_missing_or_foreign_detail_is_404(api, fake_db):
    client, _application, _settings = api
    unknown = make_user("AUDITOR")
    ordinary = make_user(PerfilEnum.CLIENTE)
    fake_db.users.update({unknown.id: unknown, ordinary.id: ordinary})
    demand = make_demand(ordinary.id)
    foreign_demand = make_demand(uuid4())
    fake_db.demands = [demand, foreign_demand]

    for endpoint in ("/demandas", f"/demandas/{demand.id}"):
        response = client.get(endpoint, headers=bearer(make_token(str(unknown.id))))
        assert response.status_code == 403

    for endpoint in (f"/demandas/{uuid4()}", f"/demandas/{foreign_demand.id}"):
        response = client.get(endpoint, headers=bearer(make_token(str(ordinary.id))))
        assert response.status_code == 404


def test_invalid_uuid_and_pagination_return_422_for_authenticated_user(api, fake_db):
    client, _application, _settings = api
    user = make_user()
    fake_db.users[user.id] = user
    headers = bearer(make_token(str(user.id)))

    assert client.get("/demandas/not-a-uuid", headers=headers).status_code == 422
    for query in ("offset=-1", "limit=0", "limit=101"):
        assert client.get(f"/demandas?{query}", headers=headers).status_code == 422


def test_empty_list_is_returned_when_repository_finds_no_records(api, fake_db):
    client, _application, _settings = api
    user = make_user(PerfilEnum.ADMIN)
    fake_db.users[user.id] = user

    response = client.get("/demandas", headers=bearer(make_token(str(user.id))))

    assert response.status_code == 200
    assert response.json() == []


def test_repository_applies_scope_order_and_pagination_in_one_query():
    database = MagicMock()
    database.scalars.return_value.all.return_value = []
    repository = PedidoRepository(database)
    owner_id = uuid4()

    result = repository.list_for_access_scope(
        cliente_id=owner_id,
        offset=12,
        limit=3,
    )

    assert result == []
    statement = database.scalars.call_args.args[0]
    compiled = statement.compile(dialect=dialect())
    sql = str(compiled)
    assert "pedidos.cliente_id" in sql
    assert "ORDER BY pedidos.created_at ASC, pedidos.id ASC" in sql
    assert sql.index("WHERE") < sql.index("ORDER BY") < sql.index("LIMIT") < sql.index("OFFSET")
    assert owner_id in compiled.params.values()
    assert 3 in compiled.params.values()
    assert 12 in compiled.params.values()


def test_response_serializes_uuid_dates_decimal_and_null_fields(api, fake_db):
    client, _application, _settings = api
    user = make_user()
    fake_db.users[user.id] = user
    timestamp = datetime(2026, 5, 6, 7, 8, tzinfo=timezone.utc)
    demand = make_demand(
        user.id,
        demand_id=UUID("ca57c5bc-0efa-4202-9c3e-7b46c560bbef"),
        created_at=timestamp,
        description=None,
        percentage=None,
    )
    demand.responsavel_id = None
    fake_db.demands = [demand]

    response = client.get(f"/demandas/{demand.id}", headers=bearer(make_token(str(user.id))))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "id", "codigo_identificador", "titulo", "descricao", "status",
        "percentual_progresso", "cliente_id", "responsavel_id", "created_at", "updated_at",
    }
    assert body["id"] == str(demand.id)
    assert body["cliente_id"] == str(user.id)
    assert body["descricao"] is None
    assert body["responsavel_id"] is None
    assert body["percentual_progresso"] is None
    assert body["created_at"] == timestamp.isoformat().replace("+00:00", "Z")
    assert body["updated_at"] == timestamp.isoformat().replace("+00:00", "Z")

    demand.percentual_progresso = Decimal("37.50")
    response = client.get(f"/demandas/{demand.id}", headers=bearer(make_token(str(user.id))))
    assert response.json()["percentual_progresso"] == "37.50"


def test_openapi_documents_bearer_only_on_protected_reads(api):
    client, _application, _settings = api
    schema = client.get("/openapi.json").json()

    security_scheme = schema["components"]["securitySchemes"]["BearerAuth"]
    assert security_scheme["type"] == "http"
    assert security_scheme["scheme"] == "bearer"
    assert schema["paths"]["/demandas"]["get"]["security"] == [{"BearerAuth": []}]
    assert schema["paths"]["/demandas/{id}"]["get"]["security"] == [{"BearerAuth": []}]
    list_response = schema["paths"]["/demandas"]["get"]["responses"]["200"]
    detail_response = schema["paths"]["/demandas/{id}"]["get"]["responses"]["200"]
    assert list_response["content"]["application/json"]["example"][0]["status"] == "PLANEAMENTO"
    assert detail_response["content"]["application/json"]["example"]["percentual_progresso"] == "0.00"
    assert "WWW-Authenticate" in schema["paths"]["/demandas"]["get"]["responses"]["401"]["headers"]
    response_schema = schema["components"]["schemas"]["DemandaResponse"]["properties"]
    assert response_schema["percentual_progresso"]["anyOf"][0]["type"] == "string"
    assert "security" not in schema["paths"]["/auth/login"]["post"]
    assert "security" not in schema["paths"]["/health"]["get"]

