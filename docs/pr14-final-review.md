# PR #14 — finalização das pendências de Henrique

Rodada atual: 2026-11-05. Repositório `ALISSINHO-1/backend-Automatize`.
Branch `Henrique-Silva`; HEAD `3ef5080daba43ba1f1fd83100a61219542c22146`.

O trabalho local foi finalizado dentro do escopo autorizado. A limpeza real da
SCRUM-87 continua **PARCIAL**: faltam garantias do provedor e coordenação global
de escritores, além da aprovação operacional. Supabase compartilhado não foi
consultado ou modificado nesta rodada. Nenhuma implantação foi realizada.

## Estado inicial, Git e preservação

Foram conferidos branch, HEAD, status, diff e refs remotas por fetch, sem trocar
branch. GitHub confirmou PR14 **open, merged=false**, head 3ef5080; PR15 também
open, merged=false. Mergeabilidade não equivale a aprovação. Nenhum PR foi
declarado aprovado ou integrado, nem foi enviado comentário/review ao GitHub.

Estado inicial desta rodada (as propostas da revisão anterior já estavam locais):

```text
 M app/infrastructure/storage/reconciliation.py
?? app/infrastructure/storage/cleanup_review.py
?? docs/DER-Automatize.md
?? docs/audit-backend.patch
?? docs/consolidation-session.patch
?? docs/consolidation-vs-HML.patch
?? docs/evidence/
?? docs/pr14-final-review.json
?? docs/pr14-final-review.md
?? docs/storage-orphan-cleanup-strategy.md
?? docs/supabase-deployment-runbook.md
?? frontend-Automatize-HML/
?? tests/integration/test_orphan_cleanup_review.py
?? tests/test_reconcile_storage_cli.py
?? tests/test_restore_validation.py
```

Os oito arquivos propostos anteriormente foram identificados e revisados:

```text
app/infrastructure/storage/reconciliation.py
app/infrastructure/storage/cleanup_review.py
tests/integration/test_orphan_cleanup_review.py
docs/DER-Automatize.md
docs/storage-orphan-cleanup-strategy.md
docs/supabase-deployment-runbook.md
docs/pr14-final-review.md
docs/pr14-final-review.json
```

Os cinco documentos foram lidos integralmente, assim como os dois arquivos de
testes preexistentes não rastreados: `test_reconcile_storage_cli.py` (5 casos) e
`test_restore_validation.py` (2). Eles permanecem sem alterações e passam na
suíte; agora integram explicitamente a lista recomendada para commit. Isso
resolve a lacuna de reprodutibilidade, desde que a lista seja aprovada e publicada.

Foi registrada a integridade dos 121 arquivos inicialmente não rastreados desta
rodada. Somente os sete arquivos da proposta anterior receberam alterações
autorizadas. Os outros 114, incluindo os dois testes, patches, evidências antigas
e cópia Flutter, foram preservados por hash. Nada foi apagado ou staged.

## Correções efetivamente realizadas

1. **Visibilidade de dados na SCRUM-87.** A revisão de candidato exige SELECT e
   ausência de filtragem efetiva por RLS em anexos/pedidos. Resultado vazio de
   role filtrada não pode provar ausência de referência. A recusa ocorre antes
   da consulta ao Storage e não amplia privilégios de nenhuma role. Catálogos e
   funções dessa verificação usam pg_catalog explicitamente; o teste com RLS
   também tenta enganar a leitura por uma pg_class temporária.
2. **Pré-validação executável.** `scripts.schema_preflight` compara revisão e
   catálogo com manifesto da mesma revisão produzido em PostgreSQL isolado,
   verifica SHA-256 do arquivo aprovado e executa contagens em REPEATABLE READ
   READ ONLY. Detecta revisão desconhecida, baseline antigo sem DDL, coluna ou
   função divergente, trigger desabilitada e vínculo de anexo inválido. Não
   migra, não repara dados, não usa stamp e sempre retorna autorização de deploy
   falsa. Artefato exportado não é aprovação humana.
3. **Restauração com proteção preservada.** O ensaio mantém owners e ACLs,
   compara schema, RLS/FORCE, grants de tabela/coluna/defaults, funções e policies,
   verifica as três triggers habilitadas nas ligações corretas e recusa endpoint
   ambíguo antes do dump. A falha não depende de assert do Python.
4. **ACLs equivalentes.** O primeiro ensaio real revelou falso negativo na
   comparação textual. A comparação passou a considerar privilégio, grantor,
   grantee e grant option, preservando a detecção de diferenças efetivas.
5. **DER.** Models e todas as oito migrations foram relidos. Nomes efetivos de
   PK/FK, índices implícitos e relacionamentos não identificadores foram
   esclarecidos. Schema PR14 e propostas PR13/15 continuam separados.
6. **Entrega reproduzível.** Foram acrescentados 28 casos nesta rodada; os sete
   casos preexistentes foram revisados para inclusão explícita. Documentação,
   fontes do provedor e evidências atuais foram consolidadas sem misturar
   snapshots, frontend ou patches antigos.

Nenhum model, migration, regra de negócio, endpoint ou contrato público da API
foi alterado. Os helpers/scripts operacionais não concedem acesso à Data API.

## Testes desta rodada

| Execução | Passed | Failed | Errors | Skipped | Warnings | PostgreSQL |
| --- | --- | --- | --- | --- | --- | --- |
| Suíte completa final | 748 | 0 | 0 | 0 | 1 | 204 |
| Específicos, rodada intermediária | 53 | 0 | 0 | 0 | 0 | 35 |

A suíte final foi `python -m pytest tests -q`, com TEST_DATABASE_URL apontando
exclusivamente ao PostgreSQL descartável e logs/JUnit próprios. Nenhum teste foi
ignorado por falta de configuração. O warning é a depreciação Starlette/httpx
do TestClient. Os arquivos temporários ficam ignorados, fora da entrega.

Contagem final: **694** casos do commit publicado (contagem histórica da rodada
anterior) + **19** casos propostos anteriormente + **7** testes não rastreados
revisados + **28** casos novos desta rodada = **748** executados agora. Não se
atribui 748 ao commit remoto. Os 28 novos são: 8 recusas adicionais na SCRUM-87,
9 testes PostgreSQL de pré-validação, 4 testes de CLI e 7 de segurança do restore.

Subconjuntos executados dentro da suíte final, sem somar testes sobrepostos:

- SCRUM-71: **18 PostgreSQL**, preservando as quatro situações exigidas.
- Revisão segura de órfãos: **27 PostgreSQL**, Storage simulado e delete nunca
  chamado; concorrência, referência nova, reutilização de path/ID/versão,
  timeout, desconexão PostgreSQL e recuperação, visibilidade e snapshots antigos.
- Pré-validação estrutural/de dados: **9 PostgreSQL**.
- RLS/grants/triggers/search_path e runtime: **34 + 16 PostgreSQL**.
- Integridade/migration/compensação de anexos: **8 + 2 + 4 PostgreSQL**.
- Concorrência existente: **6 PostgreSQL**; autenticação `/auth/me`: **8
  PostgreSQL + 13 unitários**, incluindo ADMIN/TECNICO/CLIENTE e recusas.

Houve três falhas iniciais nos testes novos por uso de Mock sem protocolo de
context manager; corrigidas para MagicMock. Não eram regressões da aplicação.
A rodada específica repetida passou. Rodadas completas intermediárias com 747
também passaram; a final inclui adicionalmente o teste de revisão desconhecida.

**Resultados históricos, não reexecutados como snapshots nesta rodada:** commit
publicado PR14: 694/168 PG; árvore local anterior: 720/187 PG; snapshot PR15:
768/203 PG. Eles estão identificados separadamente no JSON e não foram
reutilizados como contagens atuais. A proposta PR15 não recebeu nossas mudanças.

Ambiente atual: Python 3.14.7, SQLAlchemy
2.1.6, Alembic
1.20.1, psycopg2-binary
2.9.13, PostgreSQL
17.11 (Debian 17.11-1.pgdg13+2). Venv isolada existente reutilizada; nenhuma
instalação pip nova é alegada. Nenhuma dependência foi acrescentada.

## Alembic, schema e restauração

`heads/current/check/history`: uma única head **d8f4a2c6e901**,
current igual à head e **No new upgrade operations detected**. Migrations do
zero, upgrade de banco existente e preservação de dados/permissões foram testados.
Nenhuma migration foi criada ou alterada nesta rodada.

O dump/restore foi executado de fato em bancos sintéticos separados do mesmo
contêiner local rotulado. Fonte: 3 usuários, 2 pedidos, 1 ocorrência, 2 etapas,
1 aceite, 9 logs de auditoria, 1 anexo, 3 registros de histórico e 1 versão
Alembic. Linhas/fingerprints e segurança ficaram iguais; três triggers ativas,
revisão d8f4a2c6e901 e Alembic check limpo no destino restaurado. O teste não usa
clean, no-owner ou no-privileges e preservou os bancos/evidências locais.

Limites explícitos: roles globais foram reutilizadas no mesmo cluster; não foi
ensaiada recuperação de credenciais/roles em outro cluster. Bytes do Storage
não foram restaurados. Não é comprovação de backup ou recuperação do Supabase
real; esses itens dependem da operação e permanecem gates do runbook.

A inicial fbfba8e84540 mantém ID que na main era baseline sem DDL. O teste novo
reproduz esse cenário e recusa equivalência com o schema reescrito, mesmo com
rótulo Alembic igual. Não reaplicar inicial nem mascarar divergência com stamp.

## Segurança, SCRUM-87 e limites do provedor

No catálogo local: nove tabelas com RLS, sem grants Data API de tabela/coluna,
sem policies permissivas novas; três funções SECURITY INVOKER com search_path
pg_catalog, pg_temp e referências public qualificadas; três triggers habilitadas.
Aceites/auditoria imutáveis, conclusão indevida e shadowing bloqueados. Histórico
depende de autorização e privilégios; não ganhou trigger append-only fictícia.
Owner/BYPASSRLS continua uma fronteira privilegiada.

O adapter instalado implementa remove(paths), sem parâmetro de geração/ID ou
precondição por objeto, conforme [referência Python oficial](https://supabase.com/docs/reference/python/storage-from-remove).
A [compatibilidade S3](https://supabase.com/docs/guides/storage/s3/compatibility)
informa ausência de versionamento e não comprova compare-and-delete de geração
no DeleteObject. HEAD/GET condicionais não tornam uma exclusão subsequente
atômica. Essa é uma limitação do contrato comprovado, não uma suposição sobre
todas as possíveis versões futuras do provedor.

**SCRUM-87 não está concluída.** Não há executor de limpeza, coordenação global
de escritores ou recuperação de exclusão implementados. O ensaio sempre recusa
execução e o CLI continua rejeitando apply antes de conectar. Inventário,
revalidação e hash isoladamente não autorizam remoção. Nenhum arquivo real foi
excluído; nenhum registro de storage.objects foi removido por SQL.

## Compatibilidade e decisões externas

Refs consultadas por fetch e inspeção somente leitura:

| Referência | Commit |
| --- | --- |
| main | 2c023432521d521e0055a2129b1d34b44445ab9a |
| HML | f4f89e787cde2333f4b99696e7c9d15a61fdfabb |
| Luís / PR13 | e63b0e52707ad6bbbe4cd5a8c596408f1b53dc67 |
| Alisson-Rodrigues | 0bdd681722ecb56ec18a674d2998e3a21eda76d0 |
| Alisson / PR15 | df6f3b4ea944e4082da196162a10f4b7dc44f5b5 |

Luís já contém 3ef5080; PR15 deriva desse Luís. Nenhuma revisão compartilhada
diverge entre PR14/Luís/PR15. Cadeia proposta:
`d8f4a2c6e901 -> e3b7c1d9f402 -> f9a2d4c6b803`. HML está em 7b2d4e6f8a10.
Não duplicar migrations nem substituir arquivos pelo snapshot antigo do Alisson.

| Dependência | Decisão pendente |
| --- | --- |
| Alisson + Luís | Aceitar bloqueio adicional por ocorrência aberta da SCRUM-98; SCRUM-71 continua exigindo ao menos uma etapa e todas concluídas |
| Luís | Confirmar motivo de reatribuição e conflito 409 na mesma atribuição; atualizar descrição do PR13 e alinhar consumidores |
| Alisson + Luís | Aprovar contratos de anexos privados/signed URL, filtros/indicadores e gestão de etapas do PR15, com migração/binário correspondentes |
| Operação | Revisão real do schema, backup/restauração completos, janela, writers drenados, runtime/migrator, defaults por criador e grants herdados |
| Operação SCRUM87 | Comprovar fencing e exclusão condicional de geração, backup dos bytes, intenção durável e recuperação; depois obter aprovação explícita |
| Frontend canônico | Consumir auth/me e validar redirects por perfil e histórico; a cópia local não rastreada não é evidência de E2E e não foi alterada |

MAINTAIN direto é removido por REVOKE ALL, mas a pós-condição da migration antiga
9d4 não lista herança exclusiva desse privilégio. Auditoria/testes atuais verificam
MAINTAIN e o runbook exige interromper se houver herança. Não se modificou role
real nem migration antiga para adivinhar a arquitetura de credenciais.

Supabase atual **não foi consultado**. O registro de 2026-11-02 em 3c9e7a1b5d20
é histórico, não prova do estado atual. Estado esperado depois de deploy aprovado
PR14: d8, RLS/grants/funções/triggers e FK composto protegidos. Policies/bucket e
bytes do Storage real não foram validados ou alterados nesta rodada.

| Área | Implementado localmente | Testado nesta rodada | Aplicado/verificado no Supabase | Situação |
| --- | --- | --- | --- | --- |
| DER e scripts operacionais | sim | catálogo/check/restore e testes | não aplicável à documentação | entrega local pronta para revisão |
| SCRUM71 | preservada | 18 PG | não | sem alteração de regra |
| SCRUM82 | sim | sim | não | PARCIAL no ambiente |
| SCRUM87 | integridade, compensação, inventário e recusa segura | sim | não | PARCIAL; exclusão segura não comprovada |
| SCRUM103 | proteções existentes e verificação de visibilidade | sim | não | PARCIAL; deploy/roles/defaults/Storage pendentes |

## Qualidade e lista exata de entrega

`git diff --check` e `git diff --cached --check`: exit 0. Há somente avisos
de conversão LF/CRLF, sem erro de whitespace. Nenhum marcador de conflito,
segredo correspondente ao .env local, JWT literal, bytecode ou .env real nos
arquivos rastreados/da entrega. Verificação adicional de whitespace também cobre
os arquivos novos, que git diff sozinho não examina. Nada staged; HEAD e branch
inalterados. Os 114 arquivos não rastreados fora da proposta continuam intactos.

Estado Git final, incluindo os arquivos preexistentes preservados:

```text
 M app/infrastructure/database/data_api_security.py
 M app/infrastructure/storage/reconciliation.py
 M scripts/validate_hml_restore.py
?? app/infrastructure/storage/cleanup_review.py
?? docs/DER-Automatize.md
?? docs/audit-backend.patch
?? docs/consolidation-session.patch
?? docs/consolidation-vs-HML.patch
?? docs/evidence/
?? docs/pr14-final-review.json
?? docs/pr14-final-review.md
?? docs/storage-orphan-cleanup-strategy.md
?? docs/supabase-deployment-runbook.md
?? frontend-Automatize-HML/
?? scripts/schema_preflight.py
?? tests/integration/test_orphan_cleanup_review.py
?? tests/integration/test_schema_preflight.py
?? tests/test_reconcile_storage_cli.py
?? tests/test_restore_safety.py
?? tests/test_restore_validation.py
?? tests/test_schema_preflight_cli.py
```

Recomendo **16 arquivos** para o próximo commit, após revisão:

```text
app/infrastructure/database/data_api_security.py
app/infrastructure/storage/reconciliation.py
app/infrastructure/storage/cleanup_review.py
scripts/schema_preflight.py
scripts/validate_hml_restore.py
tests/integration/test_orphan_cleanup_review.py
tests/integration/test_schema_preflight.py
tests/test_schema_preflight_cli.py
tests/test_restore_safety.py
tests/test_reconcile_storage_cli.py
tests/test_restore_validation.py
docs/DER-Automatize.md
docs/supabase-deployment-runbook.md
docs/storage-orphan-cleanup-strategy.md
docs/pr14-final-review.md
docs/pr14-final-review.json
```

Os dois testes preexistentes são incluídos expressamente, sem alterações.
Não versionar .env, snapshots, .pytest_tmp*, venv, bytecode, dumps, credenciais
sintéticas, cópia Flutter, patches antigos ou docs/evidence preexistente.
Nenhum desses arquivos foi apagado. Nenhum add, commit, push, merge, rebase ou
deploy foi executado. O contêiner descartável foi parado após as leituras, sem
remover bancos, dumps ou arquivos locais.

Comandos seguros para revisão (arquivos novos devem ser abertos diretamente,
pois git diff não os apresenta enquanto não rastreados):

```powershell
git status --short
git branch -vv
git diff --check
git diff --cached --check
git diff -- app/infrastructure/database/data_api_security.py app/infrastructure/storage/reconciliation.py scripts/validate_hml_restore.py
git diff origin/main...HEAD --stat
git diff HEAD origin/Luis-Santini -- alembic/versions app
git diff origin/Luis-Santini origin/fix/api-finalizacao-20261103 -- alembic/versions app
git log --graph --oneline --decorate --all -20
```

Mensagem sugerida: `fix: reforça pré-validação e restore; documenta segurança do PR14`.
Atualização sugerida ao PR: informar 748 testes locais/204 PG/18 SCRUM71,
distinguir o commit publicado e snapshots históricos, anexar DER/runbook e
registrar explicitamente ausência de deploy e apply desabilitado. Publicação e
qualquer integração continuam aguardando aprovação do usuário/responsáveis.
