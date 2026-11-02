# Persistência: hardening de Data API, anexos e TLS

## Estado revisado em 02/11/2026

As correções já estão integradas à cadeia Alembic da branch Henrique-Silva:
`7b2d4e6f8a10` habilita RLS, `9d4f2a6c8e11` fixa search_path e revoga grants,
e `b6e1c8a4d230` protege a auditoria. A finalização acrescentou
`d8f4a2c6e901` para o vínculo composto de anexo/ocorrência/pedido; esse é o novo head.
Não criar migrations equivalentes nem executar o SQL manual antigo.
`data_api_hardening.sql` permanece apenas como artefato histórico.

A leitura atual do Supabase confirmou revisão `3c9e7a1b5d20`, três tabelas sem
RLS e funções sem search_path fixo: **implementado em código não significa
aplicado no Supabase**. Não houve gravação nesse ambiente.

O auditor `python -m scripts.audit_technical_state --storage-probe` usa conexão
com default_transaction_read_only, limites de tempo e confirmação de READ ONLY.
Exporta metadados de permissões, PUBLIC/colunas, defaults, roles, triggers,
functions, policies e bucket, sem URLs, credenciais ou registros de usuários.
Código de saída 0 significa inspeção concluída; não significa ambiente seguro.
Para avaliar os critérios de acesso das tabelas, há também
`python -m scripts.audit_data_api_access` (0: sem findings nesses critérios;
1: findings; 2: indisponível). Nenhum deles substitui testes reais de privilégios.

A role SQL atual tem BYPASSRLS/CREATEROLE/CREATEDB e ownership. Separar migrator
de runtime continua necessário antes de afirmar menor privilégio em produção.
Os testes novos exercitam uma proposta de runtime sem ownership/DDL, com
BYPASSRLS para a arquitetura backend-only existente e apenas SELECT/INSERT em
aceite, auditoria e histórico. Essa role existe somente durante transações de
testes descartáveis; não foi criada/configurada no Supabase.

O bucket auditado está privado, sem policies para clientes; os grants de CRUD
do schema Storage não equivalem a acesso permitido quando RLS nega as linhas.
Não revogar grants globais do schema gerenciado nem criar policies permissivas
para silenciar alertas. Nenhum objeto foi enviado, baixado ou excluído.

Resultados e pendências atuais:
[relatório final de Henrique](../finalizacao-henrique-2026-11-02.md).

## Data API: histórico da auditoria de 31/10/2026

O texto desta seção registra o estado e o plano anteriores à integração. As
restrições de integração e de ambiente abaixo não descrevem o estado atual.

O acesso de domínio desta branch passa pelo FastAPI/SQLAlchemy. Não há chamadas
de PostgREST para users, pedidos, ocorrências, anexos, aceites, auditoria, histórico
ou etapas. O SDK Supabase é usado para objetos no schema Storage. As consultas
diretas do frontend às tabelas de domínio não são parte do contrato encontrado.

As referências remotas foram atualizadas sem merge: origin/HML está em e51b27f
e origin/Luis-Santini em 4b946f8. As duas contêm a migration original
`7b2d4e6f8a10_habilita_rls_nas_tabelas.py`, do commit d97da09, cujo
down_revision é `3c9e7a1b5d20`. Ela já implementa ENABLE ROW LEVEL SECURITY nas
oito tabelas de domínio e em alembic_version. Não cria policies nem revoga grants.
Sem policies, bloqueia SELECT/INSERT/UPDATE/DELETE da Data API para roles sujeitas
a RLS; não restringe operações como TRUNCATE por RLS. O backend proprietário ou
BYPASSRLS permanece autorizado. Grants efetivos ainda precisam de menor privilégio.

Reutilizar essa migration original. Sua integração depende da reconciliação de
`3c9e7a1b5d20`, expressamente adiada para o item 5. Nenhuma revisão foi copiada,
recriada ou alterada. Não executar upgrade/stamp/downgrade para contornar isso.

`data_api_hardening.sql` é agora SOMENTE um complemento de permissões para revisão,
NÃO uma migration executável automaticamente. Não foi aplicado ao Supabase.
Ele exige RLS já habilitado pela cadeia original e não contém ALTER TABLE ENABLE
RLS concorrente. Depois do item 5, inspecionar novamente os grants e, se necessário,
levar apenas os REVOKEs revisados a uma migration descendente do head integrado.

O complemento retira privilégios explícitos de domínio e de alembic_version
de anon/authenticated/PUBLIC, inclusive privilégios de coluna. Não cria policies
de acesso direto: a arquitetura usa o backend. Não modifica storage/auth, não
revoga privilégios diretos de service_role, não força RLS sobre o proprietário.
As verificações transacionais recusam tabelas ausentes, roles inadequados,
views/RPCs definer expostos, privilégios herdados residuais e perda de CRUD do
backend. Executar com a mesma role SQL usada pelo FastAPI e verificar os grants
antes/depois. Uma role backend diferente da atual exige revisar as premissas.

Verificador somente leitura:

```powershell
python -m scripts.audit_data_api_access
```

Saída 0: nenhum problema nos critérios de tabelas/roles do verificador; 1:
permissões/RLS precisam de correção; 2: inspeção indisponível. Nenhum código de
saída afirma que RPCs, views, autenticação HTTP ou a Data API foram testados.
Os testes unitários usam fatos sintéticos de catálogo, não simulam PostgreSQL.
Não há Docker/PostgreSQL descartável disponível nesta execução; negações reais
de UPDATE/DELETE após aplicação do SQL devem ser testadas em ambiente isolado.
O banco compartilhado é inspecionado somente em transação READ ONLY. Nesta revisão
o catálogo ainda aponta `3c9e7a1b5d20`, sem RLS em histórico, etapas e alembic_version,
e sem policies public. Logo `7b2d4e6f8a10` está disponível na HML, mas não aplicada
nesse banco. Nenhuma alteração persistente de permissões foi executada.

## Validação dos anexos

PDF é interpretado com pypdf em modo estrito: catálogo, árvore de páginas,
referências, streams e conteúdo das páginas. PNG/JPEG usam Pillow verify e
decodificação real, inclusive frames permitidos. Não há execução de JavaScript,
ações ou anexos embutidos do PDF; nenhum renderizador externo é chamado.
Os tipos permitidos continuam PDF/PNG/JPG/JPEG/DOC/DOCX. DOC/DOCX mantêm sua
inspeção de contêiner. PDF criptografado é rejeitado porque seu conteúdo não
pode ser validado sem senha. Isso não é uma solução antivírus/CDR.

Os parsers PDF/imagem rodam em processo separado com Python isolado e ambiente
sem credenciais da aplicação: entrada 10 MiB, timeout 8 s, CPU 5 s, memória
512 MiB, 200 páginas, 10 mil objetos xref, 50 mil nós, profundidade 64, stream
20 MiB e orçamento de decodificação de 50 MiB. Imagens têm limite de 16 milhões
de pixels acumulados, dimensão 16384 e 10 frames. Linux usa resource; Windows
usa Job Objects via ctypes. Falha ao impor limites ou timeout rejeita o arquivo.
Esses limites são por validação; dimensionar concorrência no deployment continua
necessário. Não foi implementada fila, endpoint ou regra de negócio.

MIME específico incompatível é rejeitado. MIME genérico application/octet-stream
é permitido e substituído pelo formato validado. A integração no AnexoService é
somente a passagem desse parâmetro à validação, sem mudança de transações.

Novas dependências: pypdf 6.21.2+ (Python puro) e Pillow 13.x (decodificadores
mantidos, com wheels Python 3.14 Windows/Linux). A alternativa sem dependências
seria implementar parsers/decodificadores próprios, inadequado para essa camada.
Não é necessário instalar libmagic, Ghostscript ou compilador. Validado nesta
execução em Windows/Python 3.14; Linux precisa ser executado no CI.

## PostgreSQL/TLS

A validação usa a resolução de parâmetros do dialect psycopg2 do SQLAlchemy,
incluindo multihost, hostaddr, query e precedência de connect_args. Há nova
verificação do_connect imediatamente antes do driver. Destino remoto/indefinido
recebe sslmode=require e gssencmode=disable; disable/allow/prefer remotos são
rejeitados. verify-ca/verify-full são preservados. DSN aninhado, service, aliases
opacos e parâmetros duplicados conflitantes são rejeitados. Endereços herdados
de PGHOSTADDR/PGSERVICE também impedem a exceção local. PGSSLMODE não pode
desabilitar o modo explícito exigido para remoto. Parâmetros fora da lista
suportada falham com mensagem genérica, sem URL/valores.

PostgreSQL local descartável permanece permitido sem TLS; SQLite criado
diretamente pelos testes não passa por essa configuração de produção.
require exige criptografia, não substitui verify-full com CA configurada.
TLS backend->pooler deve ser verificado no driver; pg_stat_ssl através do pooler
descreve o trecho pooler->PostgreSQL. Nenhuma configuração do provedor foi alterada.

Fora desta mudança: limpeza/reconciliação de objetos órfãos, integração da revisão
do Luís, regras de estados/conclusão/aceite/progresso e endpoints/frontend.
