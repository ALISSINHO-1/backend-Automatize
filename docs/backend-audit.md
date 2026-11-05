# Auditoria do backend — 23/10/2026

Auditoria da branch Henrique-Silva após a integração da HML. As alterações preexistentes foram preservadas. Não houve commit, push, nova execução de merge, reset, execução de seed, alteração de credenciais ou escrita no PostgreSQL. As migrations existentes não foram alteradas.

## Problemas encontrados e origem

- `app/core/config.py` estava simplificado e não oferecia `cors_origins`, JWT nem os métodos de validação exigidos pela aplicação e pelos testes. A configuração completa foi recuperada de `MERGE_HEAD` e complementada com Storage. O defeito já existia antes desta auditoria; a configuração da HML consultada tinha os campos de autenticação. A HML não foi executada isoladamente.
- `pedido_service.py` e `requirements.txt` ainda estavam não resolvidos no índice, apesar de seus conteúdos não conterem marcadores de conflito. A resolução foi revisada e marcada com `git add` somente nesses dois arquivos. Isso não finalizou o merge anterior.
- Vinte arquivos de bytecode Python 3.13 estavam no índice. Foram retirados com `git rm --cached`, mantendo os arquivos locais. `.gitignore` já cobria bytecode e agora também cobre os diretórios temporários usados nesta auditoria.
- `pydantic-settings` estava declarado nos requirements, mas ausente do Python disponível. Foi instalado em `.venv`, criado com acesso aos pacotes já instalados no ambiente, sem instalação global.
- `app/core/storage.py` criava cliente Supabase ao importar e duplicava a fábrica da infraestrutura. Os imports antigos foram preservados com inicialização sob demanda.
- `AnexoService` podia apagar o arquivo remoto após uma falha de refresh que ocorresse depois de um commit bem-sucedido. A compensação agora cobre apenas a fase de persistência anterior à confirmação.
- A atualização de status validava o autor somente após enviar a atualização ao repositório. A validação agora precede o update/flush, preservando rollback e histórico na mesma transação.
- `AprovacaoService.homologar_entrega` era um `pass`. Foi implementado o registro de aceite com versão, declaração, timestamp, hash de evidência, conclusão do pedido, histórico e auditoria.
- Há duplicação preexistente de enums e schemas. `app/config.py` está vazio. Esses arquivos foram preservados para não remover interfaces de outros integrantes.
- `PedidoService.calcular_progresso` e `validar_e_transitar` já eram TODOs na HML. Continuam preservados, pois a equipe ainda precisa definir as regras completas de progresso e transição.

## Arquivos alterados nesta auditoria

| Arquivo | Alteração |
| --- | --- |
| `app/core/config.py` | Recupera configuração HML, JWT, CORS e validação de banco; acrescenta Supabase e oculta chaves no repr. |
| `alembic/env.py` | Obtém e valida URL pelo Settings, sem exigir JWT; trata `%` para ConfigParser. |
| `requirements.txt` | Preserva dependências das duas implementações; fixa Passlib 1.7.4 e mantém bcrypt 4.3.0. |
| `app/services/pedido_service.py` | Preserva CRUD e interfaces HML; valida autor antes de atualizar status. |
| `app/services/anexo_service.py` | Impede remoção do objeto remoto por falha de refresh após commit. |
| `app/services/aprovacao_service.py` | Persiste aceite, histórico e auditoria atomicamente; valida cliente e homologação; serializa aprovações com bloqueio do pedido. |
| `app/core/storage.py` | Compatibilidade dos imports existentes e cliente sob demanda. |
| `app/infrastructure/storage/supabase_storage.py` | Fábrica única do cliente Supabase. |
| `app/domain/models/__init__.py` | Inclui histórico em `__all__`. |
| `.env.example` | Declara variáveis vazias de Supabase e seed, sem credenciais reais. |
| `.gitignore` | Ignora os temporários de pytest da auditoria. |
| `scripts/__init__.py`, `scripts/seed_demo_user.py` | Comando manual, idempotente e sem efeitos ao importar. |
| `tests/services/test_pedido_service.py` | Confirma ausência de update quando falta autor da mudança de status. |
| `tests/services/test_anexo_service.py` | Cobre falha de commit e falha de refresh após commit. |
| `tests/services/test_aprovacao_service.py` | Cobre evidência, autorização, status, bloqueio SQL, repetição, histórico, auditoria e rollback. |
| `tests/test_demo_user_seed.py` | Cobre hash compatível com login, repetição, corrida de e-mail único, validação e rollback. |
| `tests/test_storage.py` | Cobre inicialização sob demanda, compatibilidade, bucket, upload/delete e falhas do provedor. |
| `tests/test_migrations_constraints.py` | Compila upgrade PostgreSQL offline e verifica cadeia, tabelas, enums, PKs, UNIQUE, CHECK, FKs e exclusões. |
| `README.md`, `docs/backend-audit.md` | Documentam ambiente, seed, verificações, limites e pendências. |

As outras alterações que já estavam staged antes desta auditoria não são atribuídas a este trabalho.

## Verificações executadas

- Primeiro `python -m pytest tests -q`: 52 passaram, 13 falharam e 44 tiveram erro de preparação de temporários no sandbox. Nova execução com acesso aos temporários confirmou que a configuração incompleta também impedia esses testes. Todos esses problemas precediam as alterações desta auditoria.
- Após restaurar configuração e instalar a dependência ausente: 109 testes existentes passaram.
- Suíte final: **147 passed**, sem falhas e sem skips. Dois avisos de depreciação do ambiente FastAPI/Starlette/AnyIO foram mantidos visíveis.
- Comando final na `.venv`: `python -m pytest tests -q --tb=short --basetemp=.pytest_tmp_final -o cache_dir=.pytest_tmp_cache_final`. As opções adicionais só colocam os temporários dentro do workspace.
- Após o ajuste final de import para o enum persistido: os 19 testes do aceite passaram novamente.
- `python -m alembic current`: **`fd3fe1dcfeab (head)`**.
- `python -m alembic check`: **`No new upgrade operations detected.`**
- Os dois comandos Alembic foram executados em subprocessos com `default_transaction_read_only=on`, timeout de conexão e saída filtrada. A tentativa no sandbox falhou por acesso de rede; a execução autorizada fora dele passou.
- Inspeção adicional do catálogo PostgreSQL somente leitura: **7 PKs, 13 FKs, UNIQUEs, CHECK de progresso e índices declarados consistentes com os modelos**.
- A geração SQL offline compilou as migrations desde a base até o head sem conexão ou DDL no banco real.
- Repositórios continuam sem commit; não foi encontrado uso de `session.query` legado. Imports da API foram exercitados pelos testes.
- Não restam entradas não resolvidas no índice nem bytecode versionado. `git diff --check` passa. `git diff --cached --check` ainda aponta uma linha em branco extra preexistente no fim de `tests/test_demandas_auth.py:473`; não afeta a execução e foi preservada junto às alterações staged da HML.

Os testes de escrita usam sessões e Storage simulados. Não foi aplicado um upgrade em um PostgreSQL vazio nem executado upload real nesta auditoria. A inspeção de catálogo e o Alembic confirmam o esquema existente, sem testar inserts negativos no banco real.

## Situação das tarefas

O status se refere ao escopo descrito no pedido, sem atualizar nenhum sistema externo.

| Tarefa | Status | Evidência e limite |
| --- | --- | --- |
| SCRUM-26 | Concluída | Cadeia inicial Alembic compilada offline; banco no head. |
| SCRUM-73 | Concluída | Ocorrência tem FK obrigatória para pedido com CASCADE; modelo, migration e catálogo conferidos. |
| SCRUM-23 | Concluída | Pedido relacionado ao cliente obrigatório e responsável opcional por FKs para users; consultas autenticadas e testes de escopo existentes passam. |
| SCRUM-24 | Concluída | Histórico modelado, migrado e indexado; mudanças de status registradas na mesma transação, com testes de rollback. |
| SCRUM-25 | Concluída | PKs, UNIQUEs, CHECK, FKs, políticas CASCADE/SET NULL e índices existentes conferidos. Não foi presumida necessidade de criar novos índices sem análise de consultas. |
| SCRUM-47 | Parcialmente concluída | Persistência de aceite, validação e transação implementadas e testadas; falta integrar rota autenticada e alinhar schemas HML de aprovação a UUID e às evidências requeridas. |
| SCRUM-48 | Concluída | Estrutura, migration, metadados e orquestração de anexos existentes, com testes ampliados. |
| SCRUM-49 | Concluída | Integração Supabase/bucket e compensação implementadas e testadas com provedor simulado; upload real não repetido. |
| SCRUM-50 | Concluída | Aceite e anexos constam da migration inicial e do banco existente; nenhuma migration duplicada criada. |
| SCRUM-67 | Concluída | Verificação SQL offline, constraints dos modelos, catálogo real e Alembic current/check aprovados. |
| SCRUM-39 | Pendente, conforme solicitado | Apenas análise; nenhum scheduler ou mecanismo de atualização automática foi implementado. |

Ainda falta integrar e testar a rota de aprovação com o usuário autenticado, bem como realizar um teste funcional de apresentação que inclua login, pedido em homologação e aceite. A rota de upload também não existe atualmente. Esses pontos exigem coordenação com o responsável pelas rotas; os contratos existentes foram preservados. A confirmação visual no frontend e um ensaio de upload real continuam como validações de integração. As regras gerais de progresso e regressão da HML continuam pendentes de definição pela equipe.

## Seed de demonstração

Configure `DEMO_USER_NAME`, `DEMO_USER_EMAIL` e `DEMO_USER_PASSWORD` no ambiente ou no `.env` local e escolha explicitamente o banco de desenvolvimento com `DATABASE_URL`. Execute manualmente `python -m scripts.seed_demo_user`.

O seed cria apenas um CLIENTE ativo, usando exatamente `app.core.security.hash_password`. Não há senha em migration nem texto puro no banco. A senha usa o mesmo limite de 72 bytes UTF-8 do login, sem truncamento. Execuções repetidas preservam a conta existente e não mudam senha, perfil ou estado de ativação. A restrição UNIQUE protege execuções concorrentes. Erros do comando não imprimem detalhes de conexão ou valores sensíveis.

Nenhum usuário foi criado durante este trabalho. A configuração real não foi exibida ou alterada.

## SCRUM-39: abordagem sugerida

Usar polling no frontend sobre `GET /demandas`, com Bearer, intervalo definido pela experiência desejada, atualização ao recuperar o foco, preservação da paginação/filtros, cancelamento de requisições e tratamento de expiração. Pausar ao ocultar a aba por `visibilitychange`. Esta é uma recomendação para a arquitetura inspecionada; não foi implementada. SSE pode ser avaliado se a equipe exigir atualização imediata, incluindo decisão de autenticação e distribuição de eventos entre instâncias. Um scheduler backend de uma hora não faria a tela aberta atualizar sozinha.

Referências consultadas: [bcrypt: changelog oficial](https://pypi.org/project/bcrypt/) e [MDN: Page Visibility API](https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API). Bcrypt 5 mudou o comportamento acima de 72 bytes; mantivemos a combinação instalada que passou nos testes, sem adaptar senhas ou substituir o mecanismo de autenticação.

## Revisão e envio pelo responsável

O merge anterior continua em andamento, com os conflitos resolvidos no índice. Antes do commit, revise tanto as mudanças já staged da HML quanto as alterações desta auditoria:

```powershell
git status
git diff
git diff --cached
git diff --check
git diff --cached --check
.\.venv\Scripts\Activate.ps1
python -m pytest tests -q
```

Adicione somente os arquivos revisados. Não inclua os dois dumps `pedido_service_henrique.txt` e `pedido_service_hml.txt` sem necessidade:

```powershell
git add -- .env.example .gitignore README.md alembic/env.py requirements.txt app/core/config.py app/core/storage.py app/domain/models/__init__.py app/infrastructure/storage/supabase_storage.py app/services/pedido_service.py app/services/anexo_service.py app/services/aprovacao_service.py scripts/__init__.py scripts/seed_demo_user.py tests/services/test_pedido_service.py tests/services/test_anexo_service.py tests/services/test_aprovacao_service.py tests/test_demo_user_seed.py tests/test_storage.py tests/test_migrations_constraints.py docs/backend-audit.md
git diff --cached --stat
git diff --cached --check
git status
git commit -m "Integra HML e valida backend, anexos e seed de demonstracao"
git push origin Henrique-Silva
```

O commit acima finalizará o merge que já estava aberto. Os comandos de commit e push são apenas instruções para o responsável; não foram executados pelo agente.
