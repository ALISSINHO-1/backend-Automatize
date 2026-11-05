# Segurança Supabase — evidência e plano revisável

## Evidência atual, somente leitura

Inspeções de 31/10/2026: PostgreSQL 17.6, banco compartilhado na revisão
`3c9e7a1b5d20`. Cada consulta foi precedida de SET TRANSACTION READ ONLY e
verificação de transaction_read_only. Nenhum registro de aplicação foi exportado.

`etapas_operacionais`, `historico_status_pedidos` e `alembic_version` continuam
sem RLS. As outras seis tabelas de domínio têm RLS, sem policies em public.
anon/authenticated têm privilégios efetivos amplos nas nove tabelas. Isso é
evidência de configuração perigosa; não foi feita exploração pela Data API real.
Nas três sem RLS, falta a barreira que impediria acesso direto com essas roles.
RLS não protege operações globais como TRUNCATE/REFERENCES; grants são uma camada
separada. Não foi executado TRUNCATE, nem mesmo como teste.

As duas funções de trigger são SECURITY INVOKER, pertencem à role usada pelo
backend, têm proconfig nulo e EXECUTE efetivo para anon/authenticated. Não são
SECURITY DEFINER. O risco de search_path é resolução de objeto errado no contexto
de execução; não há evidência de elevação por definer nessas funções.

A role SQL do backend tem BYPASSRLS, CREATEROLE e CREATEDB. Não é superuser, mas
é excessivamente privilegiada para runtime. O banco deve continuar atrás da
autorização FastAPI enquanto a separação entre runtime e migrator não é projetada.

Bucket configurado: privado, sem limite de tamanho/MIME no provedor. objects e
buckets têm RLS; nenhuma policy de Storage encontrada. O SDK conseguiu ler os
metadados do bucket. Clientes Flutter não acessam o SDK: validação e upload passam
pelo backend. Não foram criadas policies nem alteradas configurações de bucket.

Contagens somente leitura: zero anexos ligados a ocorrência de outro pedido;
zero pedidos CONCLUIDO sem aceite; zero aceites duplicados por pedido. Isso
descreve o snapshot consultado, sem provar ausência de toda inconsistência.

## Arquitetura confirmada

As oito tabelas de domínio e alembic_version **não precisam ser acessadas pela
Data API** nos consumidores encontrados. Domínio passa por FastAPI/SQLAlchemy.
Storage usa SDK Supabase com credencial de servidor. Não há motivo demonstrado
para policies permissivas de anon/authenticated nas tabelas de domínio.

Não adicionar FK ADMIN → TECNICO: ela não existe no modelo. O vínculo técnico →
cliente é um EXISTS de pedidos com cliente_id/responsavel_id. Service e endpoints
impedem que parâmetros do usuário substituam o ator autenticado.

## Classificação dos cinco alertas conhecidos

| Objeto | Severidade | Exploração/impacto | Correção | Migration / Supabase | Regressão e teste |
| --- | --- | --- | --- | --- | --- |
| public.etapas_operacionais sem RLS | CRÍTICO | Grants efetivos permitem que a Data API contorne o backend; leitura/alteração de checklist | Reutilizar 7b2d4e6f8a10 + REVOKEs de 9d4f2a6c8e11 | Migration sim; alteração manual de configuração não | Sem FORCE/policy permissiva; PostgreSQL real nega SELECT/UPDATE/DELETE e testa RLS isoladamente |
| public.historico_status_pedidos sem RLS | CRÍTICO | Leitura e adulteração de histórico fora da autorização FastAPI | Mesma cadeia existente + REVOKEs | Migration sim; configuração não | Preserva acesso SQL do backend e migrations; PostgreSQL real |
| public.alembic_version sem RLS | ALTO | Leitura/modificação de metadados de versão; pode comprometer deploys futuros | Remover acesso anon/authenticated/PUBLIC; manter RLS já prevista, sem policy de exposição | Migration sim; configuração não | Alembic upgrade/check funcionam e roles cliente não têm acesso |
| public.bloquear_alteracao_aceite_formal, search_path mutável | MÉDIO | Superfície de resolução mutável; função não consulta relações e não é definer | CREATE OR REPLACE com SECURITY INVOKER e search_path pg_catalog,pg_temp; revogar EXECUTE cliente/PUBLIC | Migration sim; configuração não | Regra/mensagem/SQLSTATE preservados; UPDATE/DELETE negados sob search_path hostil |
| public.proteger_conclusao_pedido, search_path mutável | ALTO | Uma relação temporária aceites_formais pode sombrear a consulta original e falsificar a existência de aceite | Qualificar public.aceites_formais + search_path fixo + EXECUTE restrito | Migration sim; configuração não | Teste cria tabela temporária homônima no PostgreSQL descartável; conclusão continua bloqueada |

Essas correções estão preparadas e testadas localmente. **Continuam pendentes no
banco compartilhado.** Não confundir arquivo Alembic com correção aplicada ao
ambiente. Nada foi executado nele além das consultas de leitura documentadas.

## Outros achados confirmados, distintos dos ~18 alertas não recebidos

| Objeto | Severidade | Exploração/impacto | Recomendação | Migration / Supabase | Regressão |
| --- | --- | --- | --- | --- | --- |
| Grants efetivos de nove tabelas para anon/authenticated/PUBLIC | ALTO | Ampliam impacto de RLS ausente ou RPCs; TRUNCATE não é bloqueado por RLS, embora não seja endpoint REST normal | 9d4f2a6c8e11 remove grants de tabela e coluna e falha se privilégios herdados restarem | Migration sim; alteração manual não | Médio se existir consumidor externo não encontrado; backend e SDK Storage preservados |
| Role PostgreSQL de runtime | ALTO | Comprometimento da API tem impacto administrativo/contorna RLS | Separar runtime, migrator e operação; remover CREATEROLE/CREATEDB/TRUNCATE/DDL do runtime com grants explícitos e estratégia RLS revisada | Depende de desenho de roles e configuração do deploy/Supabase | Alto; somente proposto, nenhuma role do provedor alterada |
| auditoria_logs aceita UPDATE/DELETE direto no estado inicial | ALTO | Ator com DML SQL altera evidência; não havia endpoint de edição | b6e1c8a4d230 e repository append-only, preservando FK SET NULL em trigger aninhada | Migration sim; configuração não | Médio; testes de alteração, exclusão e exclusão de pedido preservando payload passaram |
| Storage sem limites no bucket | MÉDIO | Credencial privilegiada ou outro consumidor pode contornar limites da API | Manter validação de conteúdo existente; revisar limites/mime do bucket em mudança separada | Migration não; configuração de bucket sim | Médio; não alterado automaticamente |
| Anexos sem FK composta ocorrência/pedido | MÉDIO | SQL direto pode criar par inconsistente apesar de FKs individuais; API já valida e bloqueia ocorrência durante upload | Avaliar UNIQUE composto e FK composta após preflight do legado; zero pares inconsistentes na consulta atual | Migration sim se adotado; configuração não | Médio; proposta para revisão, sem alteração automática de constraints legadas |
| Falha de compensação ou commit incerto de anexo | MÉDIO | Pode sobrar objeto; apagá-lo cegamente também pode destruir arquivo válido | Compensação existente preservada; inventário READ ONLY conservador; projetar fila durável/revisão operacional | Não para dry-run; arquitetura posterior pode exigir | Médio/alto para exclusão; nenhuma exclusão implementada ou executada no real |
| Login público sem rate limit próprio encontrado | MÉDIO | Tentativas repetidas de credenciais; não foi realizado ataque | Definir limitação no gateway/API e observabilidade sem credenciais | Migration não; infraestrutura possivelmente | Médio; proposto, sem mudança de arquitetura |
| Logout sem revogação central de JWT | BAIXO | Token copiado pode continuar válido até expirar; banco revalida usuário ativo/perfil | Decidir necessidade de revogação por sessão; preservar expiração atual e invalidar usuário quando necessário | Depende do desenho | Médio; comportamento documentado, não alterado |
| RLS habilitada sem policies em domínio backend-only | FALSO POSITIVO / NÃO APLICÁVEL para recomendação de criar policy permissiva | Default-deny é intencional para clientes diretos; backend owner/BYPASSRLS é autorizado pela API | Não criar policy para silenciar Advisor | Não exige policy; REVOKEs sim | FORCE sem desenho quebraria o backend; não aplicado |
| Alembic metadata visível na Data API | INFORMATIVO para necessidade funcional; ALTO para grants atuais | Nenhum consumidor legítimo encontrado | Não expor alembic_version; retirar grants | Migration sim | Testado com upgrade e check reais |

Não há fonte para identificar ou classificar **cada um dos aproximadamente
18 outros alertas**. Seu texto/JSON foi solicitado. Essa parte permanece
BLOQUEADA por falta do inventário do Advisor; as linhas acima não fingem ser os
18 alertas. Configurações de Supabase Auth, MFA, leaked password protection,
network restrictions e backups gerenciados não são inferidas do código FastAPI.

## Migrations, privilégios e limites

7b2d4e6f8a10 foi lida integralmente: down_revision 3c9e7a1b5d20, nove ENABLE
RLS, sem policies/grants/revokes/FORCE. Seu downgrade só desabilita três tabelas,
assumindo um estado histórico que não é universal; não foi executado.

9d4f2a6c8e11 é descendente único. Qualifica objetos de funções; preserva owner,
triggers e regras; usa invoker e limita EXECUTE; remove acesso direto de clientes
e PUBLIC, inclusive grants de coluna. Roles Supabase ausentes são toleradas no
PostgreSQL comum; privilégios herdados remanescentes abortam a transação. Não
amplia grants de service_role, não toca auth/storage e não usa FORCE.

b6e1c8a4d230 protege payload/timestamp/identidade da auditoria e DELETE. A única
exceção é uma ação FK aninhada que desliga referências de pais efetivamente
removidos, preservando o payload; mantém as regras existentes de retenção.
Triggers não são barreira contra administrador que possa desabilitá-las, nem
substituem a retirada de TRUNCATE/DDL da role de runtime.

Os testes cobrem banco vazio, upgrade desde 3c9e7a1b5d20 com dados e grants,
preservação de service_role, negação de clientes, search_path, aceite e auditoria.
Downgrade das migrations de segurança é deliberadamente recusado para não
reabrir acesso com grants inventados; revisar plano de rollback antes de deploy.

## Fontes primárias usadas na revisão

- [PostgreSQL — Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- [PostgreSQL — CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html)
- [Supabase — Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [SQLAlchemy — Populate Existing](https://docs.sqlalchemy.org/en/20/orm/queryguide/api.html#populate-existing)
