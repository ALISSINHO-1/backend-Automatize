from uuid import uuid4

from tests.integration.test_demandas_acoes_api import (  # noqa: F401
    atores, auth, client, demanda_id, settings,
)


def test_admin_lists_technicians_without_private_fields(client, auth, atores):
    response = client.get("/usuarios/tecnicos", headers=auth["admin"])
    assert response.status_code == 200
    assert str(atores["tecnico"].id) in {row["id"] for row in response.json()}
    assert all(set(row) == {"id", "nome", "perfil", "ativo"} for row in response.json())
    for profile in ("cliente", "tecnico"):
        assert client.get("/usuarios/tecnicos", headers=auth[profile]).status_code == 403


def test_clients_require_jwt_and_technical_scope(client, auth, atores, demanda_id):
    assert client.get("/usuarios/clientes").status_code == 401
    for profile in ("cliente", "outro_cliente", "admin"):
        assert client.get("/usuarios/clientes", headers=auth[profile]).status_code == 403
    response = client.get("/usuarios/clientes", headers=auth["tecnico"])
    assert response.status_code == 200
    assert {row["id"] for row in response.json()} == {str(atores["cliente"].id)}
    for target in (atores["outro_cliente"].id, uuid4()):
        assert client.get(f"/usuarios/clientes/{target}", headers=auth["tecnico"]).status_code == 404
    own_client = client.get(f'/usuarios/clientes/{atores["cliente"].id}', headers=auth["tecnico"])
    assert own_client.status_code == 200


def test_technical_scope_cannot_be_overridden_by_query(client, auth, atores, demanda_id):
    result = client.get("/usuarios/clientes", headers=auth["tecnico"], params={
        "responsavel_id": str(atores["admin"].id), "cliente_id": str(atores["outro_cliente"].id),
    })
    assert {row["id"] for row in result.json()} == {str(atores["cliente"].id)}
    assert client.get("/usuarios/clientes?limit=101", headers=auth["tecnico"]).status_code == 422
