# Supabase — runbook de implantação das proteções

Preparado em 2026-11-05 para revisão. **Não executado no Supabase compartilhado.**
As instruções de alteração deste documento são para uma futura janela aprovada;
não constituem autorização. A sessão atual usou apenas PostgreSQL descartável.

## Escopo e responsáveis

Alisson/responsável pelo ambiente autoriza release, janela, backup e recuperação;
Henrique apresenta evidências de persistência/segurança; Luís confirma contratos,
escritores e schema da integração; responsável Flutter confirma o build canônico.
Registrar aprovadores, ambiente, commit imutável e revisão alvo antes de conectar.
Não usar main/HML móveis como identificação de artefato.

Escolher explicitamente uma entrega:

| Artefato | Head esperada | Dependência |
| --- | --- | --- |
| PR #14, base 3ef5080 | d8f4a2c6e901 | schema/contratos PR14 |
| PR #13, e63b0e5 | e3b7c1d9f402 | PR14 e aceite das regras do Luís |
| PR #15, df6f3b4 | f9a2d4c6b803 | PR13 e aceite dos novos contratos |

Não implantar binário PR13/15 sobre schema PR14. Não copiar migrations isoladas,
não criar uma segunda cadeia equivalente e não executar os SQLs de documentação
em paralelo ao Alembic como mecanismo alternativo de versionamento.

## Pré-requisitos e recuperação comprovada

- Credenciais fornecidas por secret manager, fora de Git, terminal/logs e relatório.
  Não imprimir configurações, URLs, JWT, signed URLs ou valores de `.env`.
- Conexão TLS validada e projeto/ambiente confirmados por metadados não secretos;
  distinguir role de migração, runtime SQL e service key do Storage.
- Backup consistente do PostgreSQL com schema, dados, funções, triggers, owners,
  ACLs, memberships e default privileges; observar limitações de exportação das
  roles geridas pelo Supabase. Guardar parâmetros/versão e checksum em cofre.
- Backup independente dos bytes e metadados dos objetos do Storage, configuração
  do bucket e policies; dump SQL de `storage.objects` não é backup dos arquivos.
- Restaurar ambos em ambiente **separado**, testar leitura, ACLs, integridade e
  aplicação. Registrar duração, RPO/RTO aprovados e comandos/ferramentas usados.
  Script `scripts.validate_hml_restore` exige destino isolado e não substitui a
  comprovação de restauração de Storage. Não usar `--no-privileges` como evidência
  de recuperação das ACLs. Sem restauração comprovada, não iniciar implantação.
- Reexecutar suíte com TEST_DATABASE_URL isolada e revisar DER/relatório desta
  entrega. Nenhum skip PostgreSQL pode ser contado como aprovação.

## Descoberta somente leitura do estado real

Não assumir a revisão relatada anteriormente. O registro de 2026-11-02 indicava
`3c9e7a1b5d20`; **o Supabase não foi consultado novamente nesta sessão**.
Antes da janela, com conexão explicitamente READ ONLY, obter:

```sql
BEGIN READ ONLY;
SELECT version_num FROM public.alembic_version;
SELECT current_user, session_user, current_setting('server_version');
SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
       pg_get_userbyid(c.relowner) AS owner
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relkind='r' ORDER BY c.relname;
SELECT schemaname, tablename, policyname, roles, cmd, qual, with_check
FROM pg_policies WHERE schemaname IN ('public','storage');
SELECT p.proname, p.prosecdef, p.proconfig, pg_get_userbyid(p.proowner) AS owner,
       pg_get_functiondef(p.oid) AS definition
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname='public' AND p.proname IN
 ('bloquear_alteracao_aceite_formal','proteger_conclusao_pedido','proteger_auditoria_log');
SELECT t.tgname, t.tgenabled, pg_get_triggerdef(t.oid)
FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND NOT t.tgisinternal;
SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolcanlogin
FROM pg_roles WHERE rolname IN (current_user,'anon','authenticated','service_role');
ROLLBACK;
```

Também revisar memberships herdadas, privilégio CREATE em schemas, ACLs de tabela
e coluna (incluindo PUBLIC), `pg_default_acl` de **cada criador** de objetos e
EXECUTE em funções. Usar `scripts.audit_technical_state` e
`scripts.audit_data_api_access` em modo leitura, guardando apenas evidências
sanitizadas. Catálogos com definições de policies podem conter dados operacionais;
não publicar dump bruto.

### Pré-validação executável por manifesto

`scripts.schema_preflight` foi acrescentado para conferir o catálogo e as
contagens sem modificar o banco. O manifesto de referência deve ser produzido
em banco descartável, com a **mesma revisão descoberta no banco de origem**, a
partir do artefato/repositório revisado. Nunca exportar o banco compartilhado
como sua própria referência: isso apenas confirmaria a divergência existente.

1. Identificar revisão real somente leitura. Parar se desconhecida/múltipla ou
   sem correspondência revisada na cadeia; não usar stamp.
2. Preparar PostgreSQL isolado de mesma versão principal e aplicar ali as
   migrations até aquela revisão. Configurar DATABASE_URL apenas no processo
   local, sem imprimir a URL. `--export-reference` recusa destino remoto.
3. Exportar, revisar o schema e aprovar o SHA-256 dos **bytes exatos** do arquivo.
   O hash não autentica o autor; guardar aprovador, origem, commit e revisão em
   trilha restrita. Não aceitar manifesto fornecido pelo próprio banco auditado.
4. Com DATABASE_URL apontando ao alvo somente leitura, executar a comparação.
   Este passo no Supabase depende da autorização/credencial de leitura do operador;
   não foi executado no ambiente compartilhado nesta rodada.

```powershell
# DATABASE_URL já fornecida ao processo por mecanismo seguro; nunca imprimir.
# Primeiro comando: somente com a configuração do PostgreSQL descartável.
New-Item -ItemType Directory -Path .pytest_tmp_preflight -Force
python -m scripts.schema_preflight --export-reference --output .pytest_tmp_preflight/reference-reviewed.json
Get-FileHash .pytest_tmp_preflight/reference-reviewed.json -Algorithm SHA256
# Depois: configuração somente leitura do alvo e hash efetivamente aprovado.
python -m scripts.schema_preflight --reference .pytest_tmp_preflight/reference-reviewed.json --reference-sha256 "SHA256_APROVADO" --output .pytest_tmp_preflight/preflight-new.json
```

O script exige uma conexão nova e usa REPEATABLE READ READ ONLY, timeout e saída
exclusiva, sem sobrescrever evidências. Confere revisão, versão principal,
colunas/tipos/defaults, PK/UNIQUE/CHECK/FK/índices, enums, funções e triggers.
Recusa leitura parcial por falta de grants/RLS, em vez de reportar zero violações.
Retorna contagens agregadas para vínculos de anexos, aceite, conclusão, progresso,
etapas e homologação. Consulta não aplicável àquela revisão retorna `null`, nunca
zero inventado. Um arquivo vazio produzido por falha não é evidência válida.

Exit 0 comprova apenas a verificação técnica pedida; exit 1 indica divergência
de schema/dados e exit 2 indica verificação indisponível. **Sempre retorna
deployment_authorized=false**. `access_findings` deve ser revisado à parte:
ausência de divergência estrutural não comprova ACLs, roles, backup ou Storage.
`reference_file_sha256` identifica o arquivo aprovado; `reference_content_sha256`
identifica o conteúdo JSON canônico. Os dois hashes podem ser diferentes.

Para anon/authenticated verificar `has_table_privilege` com SELECT, INSERT, UPDATE,
DELETE, TRUNCATE, REFERENCES, TRIGGER e, no PostgreSQL 17+, MAINTAIN. Conferir também
`has_any_column_privilege` e EXECUTE das três funções. Permissão herdada exige
revisão, não revogação indiscriminada de roles do Supabase. RLS não protege
TRUNCATE, DDL nem um owner capaz de desabilitar triggers.

Inventariar `storage.buckets` para o bucket configurado: existente e privado,
limites e MIME; policies/permissões de `storage.objects`, inclusive upload direto,
leitura horizontal, update, upsert e remoção por anon/authenticated. Não imprimir
keys nem listar nomes pessoais de arquivos. Comprovar comportamento por API com
contas e objetos sintéticos autorizados em ambiente de homologação separado.

## Pré-validação dos dados

Executar somente contagens/agregados, em snapshot READ ONLY, para identificar:

- duplicidade de aceite por pedido; pedido concluído sem aceite;
- anexos sem pedido/usuário válido, ocorrência inexistente ou de outro pedido;
- CHECK de progresso fora de 0–100 (NULL é permitido pelo schema);
- etapa concluída sem autor/data ou etapa pendente com esses campos preenchidos;
- pedido em HOMOLOGACAO sem etapas ou com etapa pendente (regra da aplicação);
- divergência entre catálogo efetivo e models/revisões, constraints ausentes,
  triggers desabilitadas, policies inesperadas e grants herdados;
- se PR13 for escolhido, ocorrências ainda abertas podem bloquear homologação;
  não preenchê-las artificialmente para passar validação;
- inventário read-only do bucket e referências, sem exclusão. Inconsistência,
  inventário incompleto ou commit incerto segue procedimento SCRUM-87 separado.

Exemplos de consultas sem conteúdo pessoal:

```sql
SELECT count(*) AS mismatches
FROM public.anexos a JOIN public.ocorrencias o ON o.id=a.ocorrencia_id
WHERE a.pedido_id<>o.pedido_id;
SELECT count(*) AS duplicated_orders FROM (
  SELECT pedido_id FROM public.aceites_formais GROUP BY pedido_id HAVING count(*)>1
) d;
SELECT count(*) AS completed_without_acceptance FROM public.pedidos p
WHERE p.status='CONCLUIDO' AND NOT EXISTS (
  SELECT 1 FROM public.aceites_formais a WHERE a.pedido_id=p.id
);
SELECT count(*) AS invalid_homologation FROM public.pedidos p
WHERE p.status='HOMOLOGACAO' AND (
 NOT EXISTS (SELECT 1 FROM public.etapas_operacionais e WHERE e.pedido_id=p.id)
 OR EXISTS (SELECT 1 FROM public.etapas_operacionais e WHERE e.pedido_id=p.id AND NOT e.concluida)
);
```

Se uma tabela não existir na revisão descoberta, ajustar a consulta àquela revisão
e registrar a ausência. Não corrigir dados, excluir duplicatas ou usar `stamp`
para contornar divergência. A inicial `fbfba8e84540` era baseline sem DDL na main
e contém DDL no PR14/HML: rótulo igual não comprova schema igual. Validar catálogo
da instalação existente antes de decidir qualquer caminho de upgrade.

## Ordem e execução futura autorizada

```text
fbfba8e84540 -> a4fa37701385 -> fd3fe1dcfeab -> 3c9e7a1b5d20
-> 7b2d4e6f8a10 -> 9d4f2a6c8e11 -> b6e1c8a4d230 -> d8f4a2c6e901
-> e3b7c1d9f402 (somente release PR13/15)
-> f9a2d4c6b803 (somente release PR15)
```

1. Antes da janela: ensaiar upgrade de uma restauração representativa e migrations
   do zero em PostgreSQL 17. `alembic history`, `heads`, `current` devem confirmar
   cadeia única e ancestralidade da revisão atual. Fixar explicitamente o alvo
   aprovado; não usar `head` móvel de checkout diferente.
2. Na janela: confirmar backup/restauração, aprovações e gates; suspender escritas
   e drenar transações/jobs. Aplicar timeout de lock aprovado e não concorrente
   com outro migrador. Não matar transações reais sem plano autorizado.
3. **Somente após aprovação operacional**, o operador executa
   `python -m alembic upgrade <revisao-alvo-aprovada>` no ambiente identificado.
   Nesta sessão esse comando foi usado exclusivamente em banco descartável.
4. Conferir `python -m alembic current`, `heads` e `check`. Exigir revisão atual
   igual ao alvo, uma única head no artefato e
   `No new upgrade operations detected`. Rever logs sem parâmetros secretos.
5. Não executar downgrade automático ou SQL avulso para reabrir acesso se falhar.

## Estado esperado e testes de aceite

| Item | Esperado após PR14 | Limite |
| --- | --- | --- |
| RLS | ativo nas oito tabelas de domínio e alembic_version | sem FORCE; owner/BYPASSRLS privilegiado |
| Data API | PUBLIC/anon/authenticated sem grants de tabela/coluna nesses objetos | não cria policies permissivas nem altera Storage |
| Funções | três SECURITY INVOKER, search_path pg_catalog, pg_temp, referências public qualificadas | EXECUTE sem exposição pública |
| Triggers | aceite, conclusão e auditoria ativas e ligadas às funções corretas | histórico usa autorização/privilégios, sem trigger append-only próprio |
| Anexos | FK composto validado e inicialmente diferido | mantém CASCADE/SET NULL anteriores |
| Alembic | migration role consegue ler/escrever versão; Data API não consegue | runtime não precisa acesso a alembic_version |

Em homologação isolada, testar UPDATE/DELETE de aceite e auditoria recusados,
conclusão sem aceite recusada, rollback, shadowing de `aceites_formais` por tabela
temporária e as quatro situações SCRUM-71: sem etapa, uma pendente e múltiplas
com pendência bloqueadas; ao menos uma e todas concluídas permitidas.

Validar SELECT/INSERT/UPDATE/DELETE/TRUNCATE/DDL negados a anon/authenticated;
MAINTAIN sem grant e EXECUTE negado. Com runtime previsto, login e ciclo completo
da API continuam funcionando. Owner/BYPASSRLS não substitui autorização FastAPI.
Role restrita proposta nos testes tem BYPASSRLS sem superuser/CREATE/DDL e
evidências SELECT/INSERT; adoção real exige credencial e decisão do ambiente.

Testar JWT via POST `/auth/login` e GET `/auth/me` para ADMIN/TECNICO/CLIENTE,
campos `id,nome,email,perfil`, 401 para ausência/inválido/expirado/inativo ou usuário
inexistente, e nenhum parâmetro que permita consultar outra identidade. Conferir
acesso horizontal, anexos inválidos, compensação e histórico. JWT próprio da API
não deve ser tratado como permissão direta no Supabase Storage.

Storage: bucket privado, anon/authenticated sem acesso direto indevido, backend
com upload permitido e upsert=false, arquivo de outro cliente inacessível.
PR15 acrescenta signed URLs curtas/no-store; ensaiar apenas se esse artefato for
aprovado. Não inserir objeto de teste no bucket compartilhado sem autorização
específica. Reexecutar Security Advisor e guardar diferenças sanitizadas.

## Aprovação, interrupção e recuperação

Aprovar somente se backup/restauração comprovados, catálogo consistente, dados
sem violações, cadeia única, `current==alvo`, check limpo, ACLs efetivas corretas,
triggers/funções ativas e testes de API/Storage aprovados pelo responsável.
Não confundir pipeline verde com aprovação para produção.

Interromper por qualquer erro/timeout, revisão desconhecida, privilégio herdado,
schema divergente, dado inválido, escritor não drenado, falha de autorização,
bucket público inesperado ou ausência de evidência. Preservar evidências e
manter manutenção; não compensar enfraquecendo RLS/triggers/constraints.

As revisões 9d4/b6/d8 recusam downgrade automático por desenho. Em falha,
confirmar primeiro até onde a transação Alembic foi confirmada e comparar
catálogo/revisão. Preferir correção incremental ensaiada. Voltar o binário só se
compatível com o schema remanescente. Recuperação por backup exige decisão
explícita, destino separado, análise de escritas após backup e aceite de RPO;
validar antes de trocar tráfego. Não restaurar destrutivamente sobre produção
como reação automática. Roles/ACLs, configuração e bytes do Storage também
precisam recuperação. A limpeza de órfãos não faz parte deste deploy; permanece
desabilitada conforme [estratégia SCRUM-87](storage-orphan-cleanup-strategy.md).

Defaults amplos por criador, service roles e runtime excessivamente privilegiado
permanecem uma decisão operacional. As migrations fecham objetos existentes,
não alteram globalmente default privileges nem credenciais. Qualquer novo objeto
deve passar pela mesma auditoria antes de exposição.

## Ensaio de restauração realizado localmente

Nesta rodada, `scripts.validate_hml_restore` foi executado de fato contra fonte
sintética nova no contêiner rotulado. Preserva owners/ACLs: não utiliza no-owner,
no-privileges ou clean. Compara linhas, catálogo, owners, RLS/FORCE, grants de
tabela/coluna, defaults, funções e policies; exige as três triggers habilitadas
nas tabelas/funções corretas e usa falha explícita, inclusive com Python otimizado.
ACLs são comparadas por privilégio/grantor/grantee/grant option, evitando falsas
diferenças de ordem/representação. Endpoint libpq ambíguo e IPv6 alternativo são
recusados antes do dump; localhost é vinculado à publicação Docker IPv4 conferida.

O resultado completo está em `pr14-final-review.json`. Limites: restauração entre
bancos do mesmo cluster reutiliza as roles globais; não comprova recuperação de
roles/credenciais em outro cluster nem restauração dos bytes do Storage. Estes
itens continuam obrigatórios antes do deploy real. Dumps, dados sintéticos e
evidências locais são preservados fora da entrega Git.
