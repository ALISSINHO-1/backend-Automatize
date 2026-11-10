"""Real PostgreSQL + actual Storage adapter over a controlled private provider.

The HTTP download simulator proves byte handling and denied/expired links;
it is not a claim about live Supabase policies or signed-URL implementation.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
from io import BytesIO
import time
from urllib.parse import urlencode, urlsplit
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.testclient import TestClient
from jose import jwt
from PIL import Image
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError, DBAPIError
from sqlalchemy.orm import Session

from app.api.v1.endpoints.demandas_acoes import get_demand_service
from app.core.security import create_access_token
from app.domain.models import Anexo
from app.domain.models.enums import PerfilEnum
from app.infrastructure.storage.file_validation import TAMANHO_MAXIMO_BYTES
from app.infrastructure.storage.supabase_storage import SupabaseStorage
from app.services.anexo_service import AnexoService
from app.services.demand_service import DemandService
from tests import amostras
from tests.integration.test_demandas_acoes_api import settings, client, atores, auth, demanda_id  # noqa: F401
from tests.integration.test_migration_upgrade import fresh_database, upgrade
from tests.integration.test_storage_inventory_visibility import storage_catalog  # noqa: F401


class PrivateProvider:
    """No real credentials, network connection or shared bucket."""
    def __init__(self):
        self.storage = self
        self.objects = {}
        self.uploads = self.removes = self.signs = 0
        self.public = False
        self.failure = None
        self.now = int(time.time())
        self.key = b"local-simulator-only"
        self.adapter = SupabaseStorage(client=self, bucket="private-test")

    def get_bucket(self, bucket):
        assert bucket == "private-test"
        if self.failure == "bucket-missing":
            raise RuntimeError("provider-private-information")
        return {"public": self.public}

    def from_(self, bucket):
        assert bucket == "private-test"
        return self

    def upload(self, *, path, file, file_options):
        self.uploads += 1
        assert file_options["upsert"] == "false"
        assert path not in self.objects
        if self.failure == "upload-before":
            raise RuntimeError("provider-private-information")
        self.objects[path] = (bytes(file), file_options["content-type"])
        if self.failure in {"upload-timeout", "compensation-failure"}:
            raise TimeoutError("provider-private-information")

    def remove(self, paths):
        self.removes += 1
        if self.failure == "compensation-failure":
            raise RuntimeError("provider-private-information")
        for path in paths:
            self.objects.pop(path, None)

    def signature(self, path, expires):
        return hmac.new(self.key, f"{path}|{expires}".encode(), sha256).hexdigest()

    def create_signed_url(self, path, expires_in):
        self.signs += 1
        assert expires_in == 300
        if self.failure == "sign" or path not in self.objects:
            raise RuntimeError("provider-private-information")
        expires = self.now + expires_in
        query = urlencode({"expires": expires, "signature": self.signature(path, expires)})
        return {"signedURL": f"https://storage.test.invalid/sign/{path}?{query}"}

    def http(self):
        app = FastAPI()

        @app.get("/sign/{path:path}")
        def signed(path: str, expires: int, signature: str):
            if expires <= self.now or not hmac.compare_digest(signature, self.signature(path, expires)):
                raise HTTPException(403)
            if path not in self.objects:
                raise HTTPException(404)
            data, mime = self.objects[path]
            return Response(data, media_type=mime)

        @app.get("/object/{path:path}")
        def unsigned(path: str):
            raise HTTPException(403)

        return TestClient(app)


@pytest.fixture
def provider():
    return PrivateProvider()


@pytest.fixture
def image_client(client, db, provider):
    client.app.dependency_overrides[get_demand_service] = lambda: DemandService(
        db, anexo_service=AnexoService(db, storage=provider.adapter),
    )
    return client


def upload(client, auth, pedido, *, perfil="cliente", name="foto.png", data=None, mime="image/png"):
    return client.post(f"/demandas/{pedido}/evidencias", headers=auth[perfil],
                       files={"arquivo": (name, amostras.png() if data is None else data, mime)})


@pytest.mark.parametrize("perfil", ["cliente", "tecnico", "admin"])
@pytest.mark.parametrize("nome,data,mime,formato", [
    ("foto.png", amostras.png(), "image/png", "PNG"),
    ("foto.jpeg", amostras.jpeg(), "image/jpeg", "JPEG"),
], ids=["png", "jpeg"])
def test_upload_listagem_link_download_integro(image_client, db, auth, atores, demanda_id, provider, perfil, nome, data, mime, formato):
    response = upload(image_client, auth, demanda_id, perfil=perfil, name=nome, data=data, mime=mime)
    assert response.status_code == 201, response.text
    saved = db.get(Anexo, UUID(response.json()["id"]))
    assert saved.enviado_por_id == atores[perfil].id
    assert saved.pedido_id == UUID(demanda_id) and saved.tamanho_bytes == len(data)
    metadata = image_client.get(f"/demandas/{demanda_id}/anexos", headers=auth[perfil])
    assert metadata.status_code == 200
    item = metadata.json()[0]
    assert item["enviado_por_id"] == str(atores[perfil].id)
    assert "caminho_storage" not in item and "url" not in item
    access = image_client.get(item["referencia_acesso"], headers=auth[perfil])
    assert access.status_code == 200
    assert access.headers["cache-control"] == "no-store"
    assert access.headers["referrer-policy"] == "no-referrer"
    assert access.json()["validade_segundos"] == 300
    deadline = datetime.fromisoformat(access.json()["expira_em"].replace("Z", "+00:00"))
    assert datetime.now(timezone.utc) < deadline <= datetime.now(timezone.utc) + timedelta(seconds=301)
    signed = urlsplit(access.json()["url"])
    with provider.http() as storage_http:
        downloaded = storage_http.get(signed.path + "?" + signed.query)
        assert downloaded.status_code == 200 and downloaded.headers["content-type"] == mime
        assert sha256(downloaded.content).digest() == sha256(data).digest()
        with Image.open(BytesIO(downloaded.content)) as image:
            image.load()
            with Image.open(BytesIO(data)) as original:
                assert image.format == formato and image.size == original.size
        assert storage_http.get("/object/" + saved.caminho_storage).status_code == 403
        assert storage_http.get("/object/" + saved.caminho_storage, headers=auth[perfil]).status_code == 403
        assert storage_http.get(signed.path + "?" + signed.query + "corrupt").status_code == 403
        provider.now += 301
        assert storage_http.get(signed.path + "?" + signed.query).status_code == 403


@pytest.mark.parametrize("nome,data,mime", [
    ("falso.png", b"\x89PNG\r\n\x1a\ninvalid", "image/png"),
    ("errado.jpg", amostras.png(), "image/jpeg"),
    ("mime.png", amostras.png(), "image/jpeg"),
    ("vazio.png", b"", "image/png"),
    ("grande.png", b"x" * (TAMANHO_MAXIMO_BYTES + 1), "image/png"),
], ids=["invalid-png", "wrong-extension", "wrong-mime", "empty", "above-limit"])
def test_invalidos_nunca_chegam_ao_storage(image_client, auth, demanda_id, provider, nome, data, mime):
    assert upload(image_client, auth, demanda_id, name=nome, data=data, mime=mime).status_code == 422
    assert provider.uploads == 0 and not provider.objects


@pytest.mark.parametrize("failure", ["bucket-missing", "bucket-public", "upload-before", "upload-timeout", "compensation-failure"])
def test_falhas_sanitizadas_e_compensacao(image_client, db, auth, demanda_id, provider, failure):
    provider.failure = failure
    provider.public = failure == "bucket-public"
    response = upload(image_client, auth, demanda_id)
    assert response.status_code == 503
    assert "provider-private-information" not in response.text
    assert db.scalar(select(func.count()).select_from(Anexo).where(Anexo.pedido_id == UUID(demanda_id))) == 0
    assert bool(provider.objects) is (failure == "compensation-failure")
    if failure in {"bucket-missing", "bucket-public"}:
        assert provider.uploads == 0 and provider.removes == 0


def test_persistencia_fk_invalida_compensa_bytes(db, demanda_id, provider):
    with pytest.raises(IntegrityError) as error:
        AnexoService(db, storage=provider.adapter).criar(
            pedido_id=UUID(demanda_id), enviado_por_id=uuid4(), nome_arquivo="foto.png",
            conteudo=amostras.png(), content_type="image/png",
        )
    assert error.value.orig.pgcode == "23503"
    assert provider.uploads == 1 and provider.removes == 1 and not provider.objects


def test_ack_de_commit_perdido_preserva_metadata_e_bytes(image_client, db, auth, demanda_id, provider, monkeypatch):
    commit = db.commit
    def uncertain():
        commit()
        raise OperationalError("COMMIT", {}, Exception("provider-private-information"), connection_invalidated=True)
    monkeypatch.setattr(db, "commit", uncertain)
    response = upload(image_client, auth, demanda_id)
    assert response.status_code == 503 and "provider-private-information" not in response.text
    assert provider.removes == 0 and len(provider.objects) == 1
    assert db.scalar(select(func.count()).select_from(Anexo).where(Anexo.pedido_id == UUID(demanda_id))) == 1


@pytest.mark.parametrize("nome,data,mime", [
    ("laudo.pdf", amostras.pdf(), "application/pdf"),
    ("laudo.docx", amostras.docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
])
def test_documentos_existentes_continuam_suportados(image_client, auth, demanda_id, nome, data, mime):
    assert upload(image_client, auth, demanda_id, name=nome, data=data, mime=mime).status_code == 201
    assert len(image_client.get(f"/demandas/{demanda_id}/anexos", headers=auth["cliente"]).json()) == 1


def test_externo_e_anexo_de_outra_demanda_nao_geram_link(image_client, auth, demanda_id, provider):
    response = upload(image_client, auth, demanda_id)
    item_id = response.json()["id"]
    for suffix in ("/anexos", f"/anexos/{item_id}/acesso"):
        assert image_client.get(f"/demandas/{demanda_id}{suffix}", headers=auth["outro_cliente"]).status_code == 404
    assert upload(image_client, auth, demanda_id, perfil="outro_cliente").status_code == 404
    other = image_client.post("/demandas", headers=auth["cliente"], json={"titulo": "Outra demanda", "descricao": "Separada"}).json()["id"]
    assert image_client.get(f"/demandas/{other}/anexos/{item_id}/acesso", headers=auth["cliente"]).status_code == 404
    assert provider.signs == 0


@pytest.mark.parametrize("state", ["invalid", "expired"])
def test_jwt_invalido_ou_expirado_nao_acessa_imagens(image_client, settings, atores, demanda_id, provider, state):
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    token = "invalid" if state == "invalid" else jwt.encode({"sub": str(atores["cliente"].id), "iat": old, "exp": old + timedelta(hours=1)}, settings.JWT_SECRET_KEY, algorithm="HS256")
    headers = {"Authorization": "Bearer " + token}
    base = f"/demandas/{demanda_id}"
    assert image_client.get(base + "/anexos", headers=headers).status_code == 401
    assert image_client.get(base + f"/anexos/{uuid4()}/acesso", headers=headers).status_code == 401
    assert image_client.post(base + "/evidencias", headers=headers, files={"arquivo": ("foto.png", amostras.png(), "image/png")}).status_code == 401
    assert provider.uploads == 0 and provider.signs == 0


def test_paginacao_e_paths_de_metadados_nao_autorizam_acesso(image_client, db, auth, demanda_id, provider):
    ids = [upload(image_client, auth, demanda_id).json()["id"] for _ in range(3)]
    assert len(provider.objects) == 3
    base = f"/demandas/{demanda_id}/anexos"
    page = image_client.get(base, headers=auth["cliente"], params={"offset": 1, "limit": 1}).json()
    assert [a["id"] for a in page] == sorted(ids)[1:2]
    assert image_client.get(base, headers=auth["cliente"], params={"limit": 101}).status_code == 422
    db.execute(text("UPDATE public.anexos SET caminho_storage=:path WHERE id=:id"), {"path": f"pedidos/{uuid4()}/{uuid4()}.png", "id": UUID(ids[0])})
    assert image_client.get(base + f"/{ids[0]}/acesso", headers=auth["cliente"]).status_code == 503
    assert provider.signs == 0


def test_inventario_sql_nao_trunca_na_pagina_1000(storage_catalog):
    from scripts.reconcile_storage import inventory
    old = datetime.now(timezone.utc) - timedelta(days=3)
    with storage_catalog.begin() as connection:
        connection.execute(text("INSERT INTO storage.objects VALUES (:id,'synthetic-private',:path,:old,:old)"),
                           [{"id": uuid4(), "path": f"pedidos/{uuid4()}/{uuid4()}.png", "old": old} for _ in range(1005)])
    with storage_catalog.connect() as connection:
        report = inventory(connection, "synthetic-private")
    assert report["complete_snapshot"] is True and report["counts"]["storage_objects"] == 1006
    assert len(report["objects"]) == 1006 and report["apply_supported"] is False
    assert all(obj["delete"] is False for obj in report["objects"])


@pytest.fixture
def image_database(engine, monkeypatch):
    from app.domain.models import User
    database = fresh_database(engine)
    upgrade(database, monkeypatch)
    try:
        with Session(database) as session:
            owner = User(id=uuid4(), nome="Synthetic image owner", email=f"{uuid4()}@test.invalid",
                         senha_hash="unused", perfil=PerfilEnum.CLIENTE, ativo=True)
            session.add(owner)
            session.commit()
            pedido = DemandService(session).criar(owner, titulo="Private image lock", descricao="Isolated concurrent read")
            yield database, owner.id, pedido.id
    finally:
        database.dispose()


def test_leitura_de_imagem_bloqueia_reatribuicao_ate_terminar(image_database, provider):
    from app.domain.models import User
    database, owner, pedido = image_database
    with Session(database) as uploader:
        anexo = AnexoService(uploader, storage=provider.adapter).criar(
            pedido_id=pedido, enviado_por_id=owner, nome_arquivo="foto.png", conteudo=amostras.png(), content_type="image/png")
        item_id = anexo.id
    with Session(database) as reader, database.connect() as writer:
        usuario = reader.get(User, owner)
        service = DemandService(reader, anexo_service=AnexoService(reader, storage=provider.adapter))
        assert service.acessar_anexo(usuario, pedido, item_id).startswith("https://")
        writer.exec_driver_sql("SET LOCAL lock_timeout='200ms'")
        with pytest.raises(DBAPIError) as error:
            writer.execute(text("UPDATE public.pedidos SET responsavel_id=NULL WHERE id=:id"), {"id": pedido})
        assert error.value.orig.pgcode == "55P03"
        writer.rollback()
