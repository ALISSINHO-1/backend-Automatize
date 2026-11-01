# Inventário anterior às correções — 2026-10-31

Backend ativo: raiz deste workspace, branch `Henrique-Silva`, HEAD
`1b6203b4b2e6fa90e5f6bf0ac82eb68e795b8ea9`. Referência local `origin/HML`:
`e51b27f`. Não houve fetch, checkout, merge ou commit nesta auditoria.
`backend-Automatize-HML/` é uma cópia sem `.git`, diferente do backend ativo
(17 dos 64 arquivos Python de app idênticos). Não foi usada como fonte para
sobrescrever a raiz. `frontend-Automatize-HML/` também não tem `.git` próprio:
branch/HEAD HML do frontend não comprováveis pelos arquivos recebidos.

Estado Git inicial: `.env.example` modificado; não versionados:
`docs/demonstracao.md`, `docs/security/`, `frontend-Automatize-HML/`,
`scripts/audit_data_api_access.py`, `scripts/seed_demo_environment.py` e
`tests/repositories/test_demo_environment_seed.py`. Preservar esse trabalho.

Python 3.14.7; FastAPI 0.141.1; SQLAlchemy 2.0.52; Alembic 1.20.0;
psycopg2-binary 2.9.13; Supabase SDK 2.33.0; pytest 9.1.1.
Flutter 3.47.2 stable; Dart 3.13.2; pubspec exige Dart ^3.12.2.
Versão PostgreSQL depende de inspeção do catálogo; não deduzida do driver.

## Estrutura existente

Backend: `app/domain/models` (users, pedidos, ocorrências, anexos, aceite,
auditoria, histórico, etapas); repositories; services de leitura, ciclo de vida,
aceite e anexos; schemas legados e de domínio; endpoints `/auth/login`,
`/demandas` e ações; router `/pedidos` sem endpoints implementados.
JWT HS256 com sub/iat/exp, usuário ativo carregado do banco a cada requisição.
Leitura isolada por cliente/responsável; escrita centralizada em DemandService
nas rotas atuais. SQLAlchemy para domínio; Supabase SDK somente Storage.
Etapas e aceite possuem model/repository/service, transação e testes existentes.
Upload já valida extensão, MIME, estrutura e conteúdo; tem compensação e
tratamento de commit incerto. Não recriar essas proteções.

Cadeia encontrada: `fbfba8e84540 → a4fa37701385 → fd3fe1dcfeab →
3c9e7a1b5d20 → 7b2d4e6f8a10`. Uma head. A última habilita RLS em nove
tabelas, sem policies, GRANT/REVOKE ou FORCE. As funções criadas em `3c9...`
não fixam search_path. Repositories de usuários já têm técnicos e clientes
por responsável via pedidos, mas faltam service/endpoint próprios.

Frontend: rotas protegidas, login JSON, token somente em memória, interceptor
Bearer com invalidação de sessão atual em 401 e preservação em 403. Há um
interceptor legado duplicado sem consumidores. Existem duas telas de listagem,
dashboard, detalhes, histórico, homologação e seleção de anexos. Serviços reais
cobrem listagem/criação; homologação e anexos ainda têm ações demonstrativas.
Não há Timer/Stream de atualização periódica nas listas no estado inicial.

## Busca de pendências

Nenhum marcador de conflito encontrado nas fontes examinadas. TODO em
`app/api/v1/endpoints/pedidos.py` corresponde a router legado vazio, não à
ausência das rotas reais de demandas. `pass` em exceções, schema herdado,
migration de sincronização vazia e doubles de testes é legítimo no contexto.
Sem NotImplementedError ou FIXME encontrado nas fontes ativas examinadas.
`.env.example` é o único arquivo .env/bytecode versionado encontrado no índice;
valores de `.env` nunca são impressos.

## Diagnóstico inicial

Não há fundamento para recriar banco, etapas ou uploads. Priorizar search_path,
privilégios da Data API, endpoints administrativos com escopo, atualização
periódica Flutter e comprovação real de migrations/concorrência em PostgreSQL.
HOMOLOGACAO sem etapas é permitido atualmente e requer decisão de negócio.
PedidoService.atualizar contém validação de transições, mas ainda recebe só
usuario_id e permite edição de responsável/progresso: revisar consumidores.
Auditoria consistente nas transações não equivale a imutabilidade no banco.
Os ~18 alertas adicionais não foram fornecidos; não inventar sua lista.

Baseline inicial: comando pytest no sandbox: 435 passed, 52 skipped,
44 erros de preparação por permissão de temporários, 4 warnings. Repetição
com variáveis sintéticas globais: 478 passed, 1 failed, 52 skipped, 2 warnings;
a falha é no teste que espera ausência de DATABASE_URL, contaminado por essa
sobrescrita. Reexecução sem sobrescrita em andamento. Nenhuma escrita em banco
compartilhado autorizada ou executada.
