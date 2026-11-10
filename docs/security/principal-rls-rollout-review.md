# Preparacao da seguranca do Supabase principal (revisao, sem deploy)

## Escopo e decisao

**NAO EXECUTAR NO SUPABASE COMPARTILHADO SEM REVISAO DO ALISSON.**

O banco principal estava em Alembic `3c9e7a1b5d20` na consulta de 2026-11-08, e as tabelas `public.etapas_operacionais`, `public.historico_status_pedidos` e `public.alembic_version` estavam com RLS desabilitada e com privilegios SELECT/INSERT/UPDATE/DELETE acessiveis a `anon` e `authenticated`. Na HML as tres tabelas estavam com RLS habilitada e esses grants negados; Alembic HML estava em `84db17ce9f26`.

As migrations **ja existentes** `7b2d4e6f8a10` (habilita RLS) e `9d4f2a6c8e11` (REVOKE de grants publicos, inclusive grants por coluna) atendem esse objetivo. **Nao criar outra migration redundante**, nao alterar seus IDs ou marcar a revisao do banco com `alembic stamp`. Outras migrations intermediarias devem ser aplicadas na ordem, conforme o artefato integrado e seu historico real.

## Roles e fluxo de acesso

- FastAPI e Alembic leem `DATABASE_URL` via `Settings`, usam SQLAlchemy/psycopg2 e conexao direta PostgreSQL, e nao fazem acesso ao dominio via Supabase Data API.
- O codigo **nao revela o usuario SQL efetivo** do `DATABASE_URL` configurado no Render; o responsavel pelo deploy precisa confirmar somente o **nome da role**, sem compartilhar senha ou DSN.
- No catalogo do principal, `postgres` e proprietario das tres tabelas, possui `BYPASSRLS`; `service_role` tambem possui `BYPASSRLS`. Isso nao prova que FastAPI e Alembic usam uma delas.
- Antes do deploy, verificar que a role de runtime consegue SELECT/INSERT/UPDATE nas tabelas de etapa e historico, e que a role de migracao consegue consultar e atualizar `public.alembic_version`. Se forem roles separadas, testar ambas.
- Preservar a autorizacao no backend JWT; sem politicas de Data API destinadas a usuarios externos. RLS nao equivale a verificacao de perfis do FastAPI.

## Consultas de preflight SOMENTE LEITURA

Executar **na conta principal, somente com autorizacao de consulta**, sem copiar senhas:

```sql
SELECT version_num FROM public.alembic_version;
SELECT current_user, session_user;
SELECT c.relname, c.relowner::regrole::text AS owner_role,
       c.relrowsecurity, c.relforcerowsecurity
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relname IN
('etapas_operacionais','historico_status_pedidos','alembic_version')
ORDER BY c.relname;
SELECT c.relname, r.rolname,
  has_table_privilege(r.oid,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') AS any_table_grant,
  has_any_column_privilege(r.oid,c.oid,'SELECT,INSERT,UPDATE,REFERENCES') AS any_column_grant
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
CROSS JOIN pg_roles r
WHERE n.nspname='public'
 AND c.relname IN ('etapas_operacionais','historico_status_pedidos','alembic_version')
 AND r.rolname IN ('anon','authenticated')
ORDER BY c.relname, r.rolname;
```

## Ensaio obrigatorio ANTES da producao

1. Criar backup do principal e **restaurar em PostgreSQL descartavel**, com roles, ACLs, defaults e triggers relevantes. Confirmar que o snapshot reflete **grants e RLS reais do principal**, nao apenas um banco criado do zero.
2. Conferir a cadeia Alembic no commit de release escolhido, incluindo `7b2d4e6f8a10` e `9d4f2a6c8e11`, todas as revisoes intermediarias, e divergencias das migrations iniciais.
3. Executar no banco descartavel `alembic upgrade head`, `alembic current`, `alembic heads`, `alembic check` usando a role de migracao prevista.
4. Verificar que `anon` e `authenticated` nao conseguem SELECT/INSERT/UPDATE/DELETE/TRUNCATE nem grants por coluna e que a RLS esta ativada.
5. Testar com a **mesma role SQL prevista no Render** os fluxos FastAPI de leitura/escrita de etapas e historico de status. Confirmar leitura e atualizacao de `alembic_version` pela role de migracao; preservar objetos e dados.
6. Rodar a suite de integracao PostgreSQL e anexar evidencias ao PR. O CI do GitHub usa PostgreSQL descartavel novo e **nao substitui** o ensaio de restauracao com ACLs reais.
7. Em caso de erro, interromper implantacao e revisar roles/grants. Nao criar permissoes genericas em `anon` ou `authenticated`, nao aplicar downgrade de seguranca e nao editar manualmente `alembic_version`.

## Rollout no principal: BLOQUEADO ate aprovacao

Aprovacao da equipe, janela, backup testado, identidades SQL verificadas, release integrado definido e validacao HML sao precondicoes. Executar a cadeia Alembic **uma vez** no principal somente apos autorizacao. A seguir, repetir preflight e smoke tests autenticados e consultar Security Advisor. Rollback de seguranca exige plano manual revisado; nunca reabrir grants automaticamente.

## Evidencias de revisao

A verificacao remota neste PR foi **somente leitura**. Nao houve aplicacao de migration, alteracao de grants/RLS, backup real, nem verificacao com as credenciais efetivas do Render. Atualizacao 2026-11-10: GitHub Actions da head 1d2eb08 concluiu com success (run 42523914594, API e PostgreSQL, Ubuntu/Python 3.12/PostgreSQL 16). Esse CI nao cobre as alteracoes locais nao publicadas. Resultados locais atuais e limites: docs/validacao-final-banco-imagens.md.

## CI conferido em 10/11/2026

O CI do PR22 esta aprovado para a head 1d2eb08. [Execucao no GitHub Actions](https://github.com/ALISSINHO-1/backend-Automatize/actions/runs/42523914594). O PR continua draft e nao integrado; sucesso de CI nao autoriza deploy nem prova equivalencia com o principal. Esta atualizacao e local e preserva o relato historico acima.
