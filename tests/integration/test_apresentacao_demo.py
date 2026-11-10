"""Three-minute rehearsal using real PostgreSQL and controlled private Storage."""
from hashlib import sha256
from urllib.parse import urlsplit

from tests import amostras
from tests.integration.test_imagens_api import (  # noqa: F401
    provider, image_client, client, settings, atores, auth, demanda_id,
)
from tests.integration.test_demandas_acoes_api import _homologar, ACEITE


def test_roteiro_apresentacao(image_client, auth, demanda_id, provider):
    base=f"/demandas/{demanda_id}"
    assert image_client.get(base).status_code == 401
    assert image_client.get(base,headers=auth["outro_cliente"]).status_code == 404
    print("1/5 JWT e isolamento: sem token 401; outro cliente 404.")
    for canal,perfil in (("cliente","cliente"),("interno","admin")):
        assert image_client.post(base+f"/chat/{canal}",headers=auth[perfil],json={"texto":"Demonstração local"}).status_code == 201
        assert image_client.get(base+f"/chat/{canal}",headers=auth["tecnico"]).status_code == 200
    assert image_client.get(base+"/chat/interno",headers=auth["cliente"]).status_code == 404
    print("2/5 Chat: dois canais; canal interno bloqueado ao cliente.")
    original=amostras.png()
    uploaded=image_client.post(base+"/evidencias",headers=auth["cliente"],files={"arquivo":("demo.png",original,"image/png")})
    assert uploaded.status_code == 201
    listed=image_client.get(base+"/anexos",headers=auth["cliente"])
    assert listed.status_code == 200 and len(listed.json()) == 1
    access=image_client.get(listed.json()[0]["referencia_acesso"],headers=auth["cliente"])
    assert access.status_code == 200 and access.json()["validade_segundos"] == 300
    parsed=urlsplit(access.json()["url"])
    with provider.http() as download:
        fetched=download.get(parsed.path+"?"+parsed.query)
        assert fetched.status_code == 200 and sha256(fetched.content).digest() == sha256(original).digest()
    print("3/5 PNG: metadata PostgreSQL, URL 300 s e bytes íntegros; Storage simulado.")
    _homologar(image_client,auth,demanda_id)
    accepted=image_client.post(base+"/aceite",headers=auth["cliente"],json=ACEITE)
    assert accepted.status_code == 201
    assert image_client.get(base,headers=auth["cliente"]).json()["status"] == "CONCLUIDO"
    assert image_client.patch(base,headers=auth["admin"],json={"titulo":"Bloqueada","descricao":"Não alterar"}).status_code == 409
    print("4/5 Etapas, aceite e conclusão: fluxo válido; demanda concluída imutável.")
    history=image_client.get(base+"/historico",headers=auth["cliente"])
    assert history.status_code == 200 and any(event["acao"]=="ACEITE_FORMAL" for event in history.json())
    print("5/5 Auditoria preservada. Supabase compartilhado não acessado; limpeza real desabilitada.")
