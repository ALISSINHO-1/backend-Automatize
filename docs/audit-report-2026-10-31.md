| TICKET | SITUAÇÃO INICIAL | ALTERAÇÃO | TESTES | SITUAÇÃO FINAL |
| --- | --- | --- | --- | --- |
| SCRUM-21 | CONCLUÍDO na base existente | Preservados schema, models e conexão; auditados TLS, FKs, constraints e cadeia | PostgreSQL 17, banco vazio/existente, catálogo real READ ONLY, Alembic check | CONCLUÍDO |
| SCRUM-39 | PARCIAL: refresh manual/retorno, sem polling | Polling 30 s nas duas listas e painel, pausa/cancelamento, deduplicação | Timer controlado, mudança visível pela API simulada, Bearer preservado, navegação/dispose | CONCLUÍDO na cópia Flutter recebida |
| SCRUM-82 | PARCIAL: aceite protegido, auditoria SQL mutável, funções inseguras | Migration de search_path e nova proteção append-only preservando FK SET NULL | UPDATE/DELETE, conclusão sem aceite, shadowing, retenção de log, transações reais | PARCIAL: pronto em código da raiz, pendente no ambiente compartilhado |
| SCRUM-87 | PARCIAL: FKs/validação/compensação já existentes, sem reconciliação | MIME HTTP propagado, configuração Storage injetada por aplicação, inventário dry-run conservador | Formatos/MIME, rollback, compensação, commit incerto, escopo, classificação de candidatos | PARCIAL: exclusão controlada/fila operacional ainda não implementadas |
| SCRUM-101 | PARCIAL: implementação existente, criação de etapa falhava | Retirado created_at bloqueado pelo repository; usado default do banco | CRUD de etapas, progresso, FKs/CHECK, rollback e concorrência em PostgreSQL | CONCLUÍDO na raiz; cópia HML preservada ainda falha |
| SCRUM-102 | PARCIAL: consultas do repository sem service/endpoint | Endpoints autenticados e schemas mínimos; vínculo via pedidos preservado | ADMIN/TÉCNICO/CLIENTE, 401/403/404/422, acesso horizontal e query forjada | CONCLUÍDO na raiz |
| SCRUM-103 | PARCIAL: três RLS ausentes no banco; grants amplos | Reutilizada migration RLS existente; nova migration restringe grants/EXECUTE, sem FORCE nem policy permissiva | Roles PostgreSQL reais, RLS default-deny, grants de coluna, backend/Alembic/service_role preservados | PARCIAL: migrations não aplicadas ao real; runtime ainda privilegiado |
| SCRUM-104 | PARCIAL: locks existentes sem comprovação; corrida no legado | Reproduzido overwrite por sessão antiga; recarga FOR UPDATE/populate_existing no ponto necessário | Transações independentes, operações simultâneas de estado/etapa/aceite/responsável, rollback | CONCLUÍDO na raiz |
| SCRUM-105 | PARCIAL: seed DEMO existente sem fluxo completo/restauração | Reutilizado seed, acrescentadas etapas/aceite; dry-run atômico e restore em banco novo | Idempotência, erro tardio com rollback, pg_dump/pg_restore, hashes/contagens/triggers | CONCLUÍDO para PostgreSQL sintético local; objetos Storage fora do restore |

Situações de código referem-se à **raiz Git corrigida** e à cópia Flutter local,
nunca a deploy realizado. Nenhum ticket Jira foi alterado. A seleção do backend
canônico ainda precisa ser confirmada antes de encerrar tickets de entrega.

# Auditoria técnica — 31/10/2026

## Escopo, integridade do trabalho e fontes

Inventário feito antes das alterações. Branch `Henrique-Silva`, HEAD
`1b6203b4b2e6fa90e5f6bf0ac82eb68e795b8ea9`, preservados. A raiz é o backend
versionado. `backend-Automatize-HML/` é uma cópia ignorada pelo Git, sem branch/HEAD
próprios e com diferenças funcionais. O frontend também não tem Git próprio;
seu nome HML não comprova commit remoto. Não houve fetch/checkout/merge/commit,
push, rebase, PR ou operação Jira.

Alterações prévias preservadas: `.env.example`, docs de demonstração/segurança,
seed DEMO, auditor de Data API e seus testes, além da pasta Flutter. Não são
atribuídas a esta auditoria. As correções novas foram feitas na raiz e nas fontes
Flutter, sem substituir a cópia backend HML. Inventário completo em
[audit-inventory-2026-10-31.md](audit-inventory-2026-10-31.md).

## SEGURANÇA SUPABASE

| ALERTA | RISCO | CORREÇÃO | TESTE | STATUS |
| --- | --- | --- | --- | --- |
| etapas_operacionais sem RLS | CRÍTICO: acesso direto com grants de cliente | 7b2d4e6f8a10 existente + 9d4f2a6c8e11 | Negação real de roles e RLS em PostgreSQL | Preparada; continua aberto no real |
| historico_status_pedidos sem RLS | CRÍTICO: adulteração/leitura de histórico | Mesma cadeia | Mesmo teste, sem SQLite | Preparada; continua aberto no real |
| alembic_version sem RLS/grants amplos | ALTO: manipulação de metadados de deploy | Retirar acesso Data API e manter proteção existente, sem expor policy | Alembic upgrade/check e negação aos clientes | Preparada; continua aberto no real |
| bloquear_alteracao_aceite_formal search_path | MÉDIO | path fixo, invoker preservado e EXECUTE restrito | Aceite imutável sob path hostil | Corrigido em migration; não aplicado ao real |
| proteger_conclusao_pedido search_path | ALTO | public.aceites_formais, path fixo, invoker e EXECUTE restrito | Tabela temporária homônima não autoriza concluir | Corrigido em migration; não aplicado ao real |
| Aproximadamente 18 outros alertas | Ainda não classificáveis individualmente | Texto/JSON solicitado; não corrigidos por suposição | Sem inventário para reproduzir | BLOQUEADO por falta da lista |

Classificação, exploração, impacto, necessidade de migration/configuração,
regressão e propostas adicionais estão em
[audit-security-assessment.md](audit-security-assessment.md).

O banco compartilhado foi consultado em transação READ ONLY: PostgreSQL 17.6,
revisão **3c9e7a1b5d20**. As três RLS continuam ausentes; proconfig das duas
funções continua nulo. anon/authenticated têm grants amplos. A role backend tem
BYPASSRLS/CREATEROLE/CREATEDB. Não foi alterada nenhuma configuração ou role.

Bucket privado, RLS em storage.objects/storage.buckets, sem policies encontradas.
SDK alcançou metadados do bucket. Limites de tamanho/MIME do bucket não estão
configurados; limites e inspeção de conteúdo já existem no backend e foram
preservados. Não houve upload, exclusão, limpeza nem download de objetos reais.

Consultas agregadas reais: zero anexos associados a ocorrência de outro pedido,
zero CONCLUIDO sem aceite, zero duplicidades de aceite. Não foram exportados
nomes, e-mails, documentos, tokens, senhas ou credenciais.

## BACKEND — resultados executados

| Execução | Passed | Failed | Skipped | Warnings | Observação |
| --- | --- | --- | --- | --- | --- |
| Baseline sem PostgreSQL, após resolver permissão do sandbox | 479 | 0 | 52 | 2 | `python -m pytest tests -q --tb=short` |
| Integração original da raiz, antes das correções | 46 | 6 | 0 | 2 | Banco local revelou bug de criação de etapas |
| Reprodução dedicada da sessão antiga, antes da proteção | 0 | 1 | 0 | 0 | Sobrescrevia estado atual sem rejeição do cliente |
| Suíte final da raiz com PostgreSQL real | **588** | **0** | **0** | **2** | `python -m pytest tests -q --tb=short`; 101,78 s |
| Cópia backend HML sem PostgreSQL, intocada | 465 | 0 | 56 | 2 | Não comprova funcionalidades PostgreSQL |
| Integração da cópia HML em outro banco local, intocada | 25 | **31** | 0 | 2 | Falhas encadeadas pelo mesmo created_at bloqueado |

O primeiro comando no sandbox teve 44 erros de preparação por permissão de
temporários; não foram contados como bugs funcionais. Uma repetição com variáveis
sintéticas globais contaminou o teste que espera ausência de DATABASE_URL; foi
repetida sem a sobrescrita, obtendo o baseline verde acima. Na primeira suíte
completa após novos endpoints, um teste ainda esperava só três routers; foi
atualizado para incluir o router administrativo e a suíte final passou.

Warnings remanescentes são depreciações FastAPI/Starlette relacionadas a httpx e
AnyIO BlockingPortal; não foram silenciados nem provocaram atualização ampla de
dependências. Python 3.14.7, FastAPI 0.141.1, SQLAlchemy 2.0.52, Alembic 1.20.0,
psycopg2-binary 2.9.13, Supabase SDK 2.33.0 e pytest 9.1.1.

As falhas da cópia HML não foram escondidas nem confundidas com os 588 testes da
raiz. Ela preserva a implementação recebida, incluindo regra de homologação mais
restrita. Selecionar essa cópia como entrega exige transportar correções após
revisão e executar sua suíte novamente; o trabalho não foi feito por cópia cega.

## FRONTEND — resultados executados

Flutter 3.47.2 stable, Dart 3.13.2. Baseline: flutter analyze sem problemas e
29 testes aprovados. Após correções: analyze sem problemas e **31 testes
aprovados**. O teste integrado usa HTTP simulado, interceptor real e tela real:
muda a resposta, avança 30 s, verifica o texto novo e o mesmo Bearer; abrir outra
tela suspende consultas, retornar atualiza uma vez e dispose cancela o timer.
Há teste separado de pausa/resume e requisição ainda pendente sem duplicação.
Falha transitória HTTP 503 é exibida e a lista se recupera no próximo polling,
preservando o JWT.

A homologação e a seleção de anexos continuam explicitamente demonstrativas.
Histórico fixo atribuído a todas as demandas foi removido; a integração real ainda
é necessária. Não foi reescrita toda a interface nem inventada regra de perfil.
Autorização permanece obrigatória no backend. A UI atual tem foco em CLIENTE;
um login ADMIN não ganha automaticamente um fluxo completo de administração.

## ALEMBIC

Cadeia final única:

```text
fbfba8e84540 → a4fa37701385 → fd3fe1dcfeab → 3c9e7a1b5d20
→ 7b2d4e6f8a10 → 9d4f2a6c8e11 → b6e1c8a4d230
```

`python -m alembic heads`: uma head, **b6e1c8a4d230**.
`history`: down_revisions lineares, sem branch acidental.
`upgrade head`: passou em PostgreSQL 17 descartável, desde vazio e desde 3c9e7a1b5d20
com dados sintéticos e grants Supabase simulados por roles reais.
`check`: **No new upgrade operations detected.**

Migrations originais não foram reescritas. As migrations novas não têm rollback
automático de segurança: downgrade é recusado para não inventar grants anteriores
ou reabrir acesso. Nenhum downgrade, stamp ou migration foi aplicado ao banco real.
As rotinas de restauração usam banco novo, nunca restauração sobre existente.

## INTEGRAÇÃO

- Flutter → FastAPI: login, listagem e cadastro CLIENTE têm contratos compatíveis;
  atualização periódica usa a mesma API. Homologação, histórico, detalhes buscados
  só por ID e anexos não compõem ainda um fluxo completo integrado.
- FastAPI → PostgreSQL: conexão e metadata reais inspecionadas em leitura; fluxo
  de escrita exercitado somente no PostgreSQL local real.
- Autenticação: JWT assinado, sub/iat/exp, expiração, usuário ativo, 401 genérico;
  Flutter mantém token em memória e invalida apenas a sessão atual em 401.
- Autorização: ADMIN, técnico responsável e cliente dono validados no backend;
  consultas de usuários vinculam técnico/cliente por pedidos, sem FK artificial.
- Storage: SDK real alcança bucket privado; testes de upload/erro/compensação usam
  fake/mocks, incluindo DB real em casos de integração. Não há prova de upload
  real E2E em HML isolado nesta execução.

Mapa completo de URLs/métodos/schemas/camadas/tabelas e incompatibilidades em
[audit-integration-map.md](audit-integration-map.md).

## SCRUM-87: compensação e órfãos

Preservadas validações de extensão/MIME/conteúdo, PDF/PNG/JPEG e DOC/DOCX,
limites de recursos e isolamento dos parsers. O endpoint passou a encaminhar o
MIME declarado ao validador que já existia; antes esse dado se perdia.
Configuração de Storage agora acompanha os Settings da aplicação injetada,
evitando que app de teste/HML use silenciosamente a configuração global de outro
ambiente. Inicialização segue lazy; imports não abrem o cliente remoto.

Falha confirmada de persistência compensa o upload; falha de refresh depois do
commit preserva o arquivo; commit incerto e falha de compensação não causam
exclusão cega. Permanecem riscos de objeto órfão por queda de processo, exclusão
de pedido com cascade de metadata ou falha operacional de compensação.

O novo inventário é READ ONLY e conservador, com evidências em hash, nunca
exclusão. Não equivale a mecanismo completo de limpeza. Projetar execução
controlada e trilha durável permanece pendente. Não há arquivos reais apagados.

## Massa HML e restauração

Seed existente foi reutilizado, sem senha fixa e sem redefinir contas. Novo
wrapper local fornece etapas pendentes/concluídas, ocorrência, aceite, histórico
e auditoria. É idempotente, configurável, default dry-run e atômico mesmo com
commits internos dos services. Teste injeta erro tardio e confirma zero linhas
persistidas. Anexos não são inventados sem objeto real correspondente.

Foi criada massa sintética em banco dedicado, aplicada duas vezes, exportada
com pg_dump e restaurada em banco novo do mesmo container. Todas as contagens e
hashes coincidiram; três triggers e head foram preservados. Isso não inclui
backup de Storage, Supabase Auth ou configuração gerenciada. Procedimento em
[hml-validation-runbook.md](hml-validation-runbook.md).

## Segredos, conflitos e diffs

Scanner reportou apenas: **segredo potencial encontrado em arquivo .env**.
O arquivo é ignorado. Nenhuma correspondência dos segredos configurados ou de
JWTs completos nos arquivos versionados examinados; zero bytecodes versionados.
Não é certificação de histórico Git completo, de todo segredo possível ou de
artefatos externos. `.env.example` já estava alterado antes e foi preservado.

`git diff --check` passou. Busca final ancorada por marcadores de conflito não
encontrou ocorrências nas fontes ativas. Pass em exceções/classes herdadas e
migration vazia foi analisado como legítimo; TODO no router legado pedidos não
significa ausência das rotas reais de demandas. Não houve refatoração estética,
renomeação de tabelas ou troca de pedidos para demands.

Patch de revisão do backend: [audit-backend.patch](audit-backend.patch), incluindo
fontes/testes versionados alterados e novos arquivos desta auditoria. Exclui
`.env.example` e os arquivos preexistentes não versionados. O frontend não tem
base Git própria para afirmar um diff incremental exato. Fontes alteradas:
`lib/app/app.dart`, as duas telas de listagem, `painel_screen.dart` e
`demand_details_page.dart`; novas fontes `lib/core/network/periodic_refresh.dart`
e os dois testes de polling. Nenhum diff fictício foi atribuído ao frontend.

## Respostas finais

1. **Backend está estável?** A raiz corrigida passa 588 testes, incluindo real
   PostgreSQL; não declaro todo artefato HML estável, pois a cópia tem 31 falhas de
   integração e ainda falta escolher a referência de entrega.
2. **Frontend está estável?** Analyze e 31 testes passam; funcionalmente parcial
   para homologação, histórico e anexos, sem certificação de produção.
3. **Compatíveis?** Parcialmente: login/listagem/cadastro CLIENTE sim; fluxo
   completo ainda não. Nenhum contrato foi alterado para esconder a lacuna.
4. **PostgreSQL/Supabase integrados?** Conexão SQL e leitura de bucket sim;
   privilégio mínimo e rollout de migrations no ambiente real ainda pendentes.
5. **Migrations consistentes?** Sim na raiz, uma head, criação do zero, upgrade
   de existente e check reais; downgrade de segurança é deliberadamente bloqueado.
6. **Três RLS tratados em código/migration?** Sim; continuam ausentes no real.
7. **Dois Function Search Path tratados?** Sim, com teste de shadowing; não
   aplicados ao real.
8. **Aceite formal protegido?** Sim contra DML normal nos caminhos e triggers
   testados; nenhum teste destrutivo foi feito no banco compartilhado.
9. **Conclusão indevida bloqueada?** Sim pela máquina de estados/aceite nos
   caminhos API e pelos triggers cobertos; role administrativa não é fronteira
   contra quem possa desabilitar triggers ou forjar dados diretamente por SQL.
10. **Anexos protegidos DB/Storage?** Validação, escopo e compensação cobertos;
    não existe transação distribuída nem garantia absoluta contra órfãos.
11. **Existe risco de órfão?** Sim; reconciliação dry-run identifica candidatos,
    não os apaga nem resolve todos os incidentes automaticamente.
12. **Perfis isolados?** Sim nos endpoints FastAPI testados, inclusive acesso
    horizontal. A Data API real ainda tem as três exposições confirmadas.
13. **SCRUM-39 funciona?** Sim nos testes da lista com API simulada e ciclo de
    vida; não foi alegado E2E real de navegador/dispositivo com servidor remoto.
14. **Tickets candidatos a CONCLUÍDO?** SCRUM-21; e SCRUM-39/101/102/104/105
    quanto à implementação/testes locais, após aceitar a raiz como referência e
    revisar os diffs. Nenhuma movimentação Jira foi feita.
15. **Parciais?** SCRUM-82/103 dependem de rollout revisado e validação real;
    SCRUM-87 depende de operação de reconciliação/limpeza controlada e teste
    Storage em HML isolado. Se a cópia HML for canônica, SCRUM-101 e demais
    correções da raiz precisam ser integradas e retestadas antes de conclusão.
16. **Decisões do grupo?** Backend canônico e reconciliação da regra de etapas:
    raiz permite zero, cópia HML exige ao menos uma. A regra já existe nessa
    cópia, portanto não foi substituída por decisão técnica. Também falta definir
    contrato/integração do histórico existente, operação de órfãos e roles runtime.
17. **Impedimentos para produção?** Três RLS/grants e funções ainda inseguros
    no ambiente real; runtime excessivamente privilegiado; lista incompleta do
    Advisor; backend canônico indefinido; 31 falhas da cópia HML; homologação,
    histórico e anexos Flutter incompletos; ausência de E2E com Storage isolado,
    operação de órfãos e plano completo de recuperação incluindo objetos/secrets.

Nenhum commit, push, merge, PR, mudança de produção ou exclusão de dados reais.
O container PostgreSQL descartável criado para os testes foi encerrado depois da
validação; somente seus bancos sintéticos e arquivos temporários foram removidos.
Revisar relatórios, diffs e evidências antes de autorizar a próxima etapa.
