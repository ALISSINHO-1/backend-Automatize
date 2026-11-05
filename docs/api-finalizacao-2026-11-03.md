# Complementos da API — 03/11/2026

Base: commit `e63b0e5` da branch Luis-Santini, incluindo a consolidacao do Henrique.
Este complemento depende do PR #13 do backend; nao substitui esse PR.

## Consulta e indicadores — SCRUM-93

`GET /demandas` preserva a resposta em lista e aceita `offset`/`limit` (1 a 100).
Filtros opcionais combinaveis: `busca` (titulo ou codigo, literal, sem diferenciar
maiusculas), `status`, `cliente_id`, `responsavel_id`, `criado_de` e `criado_ate`.
Datas sao inclusivas e precisam de fuso, como `2026-11-03T00:00:00-03:00`.
Intervalo invertido, identificador invalido e filtro invalido retornam 422.

`GET /demandas/indicadores` usa os mesmos filtros e retorna, por exemplo:

```json
{"total": 3, "por_status": {"PLANEAMENTO": 2, "EXECUCAO": 1, "HOMOLOGACAO": 0, "CONCLUIDO": 0}}
```

Os totais abrangem o conjunto filtrado inteiro, independentemente da pagina atual.
O escopo do JWT e aplicado junto dos filtros: informar outro cliente ou tecnico
nunca amplia a permissao. O front deve consumir este endpoint para contadores.

## Anexos privados — SCRUM-55

1. Upload existente: `POST /demandas/{id}/evidencias`, multipart com campo `arquivo`.
2. `GET /demandas/{id}/anexos?offset=0&limit=100` retorna metadados e
   `referencia_acesso`, sem caminho interno do bucket nem chave do Storage.
3. Chame a referencia com Bearer: `GET /demandas/{id}/anexos/{anexo_id}/acesso`.
4. Abra a `url` assinada retornada. Validade de 300 segundos; resposta inclui
   `expira_em`, `validade_segundos` e `Cache-Control: no-store`.

Somente quem consulta a demanda pode listar ou solicitar o link. IDs inexistentes,
anexos de outra demanda e acesso fora de escopo retornam 404; sem token, 401.
Falha de assinatura/configuracao retorna 503 sem detalhes internos. A listagem nao
precisa conectar ao Storage. Mantenha o bucket privado e nao grave links em logs.
Logout ou reatribuicao impedem novos links, mas nao revogam um link ja emitido antes
dos cinco minutos. A expiracao real depende do Supabase e deve ser homologada no
ambiente; os testes automatizados usam Storage substituto.

## Etapas — SCRUM-92

- `POST /demandas/{id}/etapas`: descricao e `ordem` opcional; omitida, vai ao final.
- `GET /demandas/{id}/etapas`: inclui `ordem`, a partir de 1.
- `PATCH /demandas/{id}/etapas/{etapa_id}`: descricao e/ou ordem. Reposicionar
  desloca as outras etapas e mantem sequencia continua.
- `DELETE /demandas/{id}/etapas/{etapa_id}?motivo=...`: motivo de 10 a 500
  caracteres; retorna 204. Somente etapa pendente em PLANEAMENTO ou EXECUCAO.
- Conclusao existente: `POST /demandas/{id}/etapas/{etapa_id}/conclusao`, em EXECUCAO.

ADMIN ou tecnico responsavel alteram; CLIENTE somente consulta. Etapa de outro pedido
recebe 404. Etapa concluida e alteracoes durante HOMOLOGACAO/CONCLUIDO recebem 409.
Edicao e remocao geram auditoria com autor do JWT; remocao registra descricao,
posicao e motivo. O progresso e recalculado pelo backend; consulte a demanda.
Zero etapas continua bloqueando homologacao.

Migration nova: `f9a2d4c6b803`, apos `e3b7c1d9f402`; adiciona ordem com backfill
por data e UUID, sem remover etapas. Nao executada no banco compartilhado.

## Contratos existentes — SCRUM-56

| Operacao | Contrato implementado |
|---|---|
| Identidade | `GET /auth/me` |
| Edicao da demanda | `PATCH /demandas/{id}` |
| Aceite formal | `POST /demandas/{id}/aceite` |
| Rejeicao | `POST /demandas/{id}/rejeicao` |
| Auditoria | `GET /demandas/{id}/historico` |
| Atribuicao | `PUT /demandas/{id}/responsavel` |
| Ocorrencias | `GET/POST /demandas/{id}/ocorrencias` |
| Resolucao | `POST /demandas/{id}/ocorrencias/{ocorrencia_id}/resolucao` |

Nao criar aliases `/aprovar` ou `/rejeitar` apenas por constarem em titulos antigos
do Jira. `/docs` e `/openapi.json` mostram os contratos disponiveis.
Codigos: 200 consulta/edicao, 201 criacao, 204 exclusao, 401 sem sessao, 403 perfil
proibido, 404 fora do escopo/inexistente, 409 conflito, 422 entrada invalida e
503 Storage indisponivel.

## Validacao automatica — SCRUM-94, 65 e 85

Workflow `.github/workflows/api.yml`: PostgreSQL 16 descartavel em localhost,
Python 3.12, dependencias, papeis Supabase apenas no banco de teste, upgrade Alembic,
verificacao de modelos, suite completa e relatorio JUnit. Executa em PRs e pushes
nas branches configuradas. Nao usa segredos de producao.

Reproducao local (banco LOCAL descartavel com nome contendo `test`):

```bash
python -m pip install -r requirements.txt
export TEST_DATABASE_URL='postgresql+psycopg2://postgres:SENHA_LOCAL@localhost:5432/automatize_test'
export DATABASE_URL="$TEST_DATABASE_URL"
export JWT_SECRET_KEY='chave-exclusiva-de-teste-com-mais-de-32-caracteres'
python -m scripts.prepare_test_database
alembic upgrade head
alembic check
python -m pytest -q
```

Sem PostgreSQL: `python -m pytest -q --ignore=tests/integration`. Essa execucao
valida contratos com SQLite e Storage substituto; nao certifica triggers, RLS,
concorrencia PostgreSQL ou expiracao real dos links.

## Preparacao de deploy — SCRUM-57

Dockerfile: Python 3.12, usuario sem privilegios, porta `PORT` (padrao 8000),
healthcheck `/health` e documentacao `/docs`. Migrations sao uma etapa separada
antes de subir a versao, depois de backup e teste de restauracao.
Configure no provedor `DATABASE_URL`, `JWT_SECRET_KEY`, `JWT_ALGORITHM=HS256`,
`CORS_ORIGINS` com as origens exatas do Flutter Web, `SUPABASE_URL`,
`SUPABASE_KEY` e `STORAGE_BUCKET_NAME`. Segredos ficam no servidor.
O PostgreSQL remoto exige TLS conforme a validacao existente.

Build local: `docker build -t automatize-api .`; iniciar:
`docker run --rm --env-file .env -p 8000:8000 automatize-api`.

Ainda requer hospedagem definida, credenciais no provedor, URL HTTPS, teste CORS,
login dos tres perfis e envio/consulta/expiracao de anexo no Supabase real.
Este PR prepara o deploy, mas nao publica servico nem aplica migrations no banco compartilhado.
