# Integração final de Henrique — 10/11/2026

## Estado pronto para revisão

Branch: **integracao/henrique-apresentacao-20261110**, base
**ae327b5ac5397b417203e903f842a3d1a4184a24**, origin/HML consultada por fetch
explícito. Worktree: `.pytest_tmp_apresentacao_20261110/integration`.
Entrega organizada em quatro commits locais sobre essa base. Os arquivos do
manifesto foram selecionados por grupo, com revisão de staging, diff e segredos
antes de cada commit. Não houve push, abertura de PR ou merge.

Entregas A e B foram consolidadas no novo worktree por aplicação verificada do
patch composto e inspeção dos fontes reais. Não houve merge, cherry-pick ou
rebase nas branches existentes. Foram preservados por hash 505 arquivos da
Henrique original, 211 da revisão A e 214 da composição B. Nenhum desses arquivos
anteriores foi sobrescrito ou apagado nesta execução.

## Decisões de integração

- Reutilizados `anexos`, seus vínculos e as rotas publicadas; nenhuma tabela ou
  migration nova para imagens.
- Reutilizada a migration d1f da entrega A, descendente da head HML 84db. O
  conteúdo lógico é igual ao anterior; a cópia via Git normaliza finais de linha.
  Nenhuma migration publicada foi editada.
- Chat integrado é o publicado: `/demandas/{pedido_id}/chat/{canal}`. Não se
  acrescenta a migration alternativa c7a nem uma segunda tabela/rota concorrente.
  A implementação local anterior continua intacta na Henrique.
- Preservada a política de participantes da HML: cliente/técnico no canal
  cliente; admin/técnico no interno. ADMIN não ganha acesso ao canal cliente
  por esta mudança. Demanda/canal fora do escopo retorna 404.
- Incorporados ao chat corpo estrito (`autor_id`/extras recusados), recusa de
  caractere nulo e populate_existing sob lock compartilhado. Testes novos provam
  recarga após reatribuição, cursor de outro canal, JWT e autoria correta.
- Não foram removidos testes ou regras de outros membros. A inspeção AST não
  encontrou definições de testes duplicadas. O arquivo de SDK mantém os sete
  testes anteriores da HML e os quinze novos de privacidade/TTL.

## Cadeia Alembic e provas de banco

```text
fbfba8e84540 -> a4fa37701385 -> fd3fe1dcfeab -> 3c9e7a1b5d20
 -> 7b2d4e6f8a10 -> 9d4f2a6c8e11 -> b6e1c8a4d230 -> d8f4a2c6e901
 -> e3b7c1d9f402 -> f9a2d4c6b803 -> 2a6d14c839ef -> 51cb39a0d826
 -> 84db17ce9f26 -> d1f6a8c20391
```

d1f adiciona chave única de suporte no pedido, FK composta de aceite/cliente e
CHECK de conteúdo. Mantém FKs/triggers anteriores, inclusive a manutenção
expressamente permitida por SET NULL na auditoria. Legado incompatível aborta
sem correção automática. Não há migration redundante de RLS/grants ou de chat.

Executados em PostgreSQL 17.11 descartável: heads, upgrade head, current e check.
Uma head/current d1f; `No new upgrade operations detected.` Não houve stamp.

O ensaio adicional partiu do schema sintético 3c9, com dados representativos,
roles, grants amplos/por coluna e RLS antigas. Snapshot foi restaurado em outro
banco, comparado e atualizado. Novo dump/restore do release preservou dados,
schema, owners/ACLs, policies, funções e três triggers nas onze tabelas protegidas.

Não havia snapshot autorizado do principal. Roles globais foram reutilizadas no
mesmo cluster. Não se alega reprodução exata de produção, recuperação de roles
em outro cluster ou restauração de bytes do Storage.

## Testes realmente executados nesta integração

| Execução | Passed | Failed | Errors | Skipped | Warnings |
| --- | --- | --- | --- | --- | --- |
| Suíte completa final | **932** | **0** | **0** | **0** | **2** |
| Chat e roteiro, rodada direcionada | 17 | 0 | 0 | 0 | 2 |
| Comando PowerShell de demo, separado | 1 | 0 | 0 | 0 | 2 |

A suíte completa levou 185,27 s e inclui **331 testes PostgreSQL**. Os demais
601 testes unitários/mocks/SQLite preexistentes também passaram. Não se somam
rodadas repetidas. Warnings: depreciações Starlette/httpx e AnyIO.

| Subconjunto PostgreSQL | Casos |
| --- | --- |
| SCRUM-71 | **18** |
| RLS/grants/triggers/search_path | 38 |
| Runtime restrito/catálogo | 16 |
| Regressão de paridade do PR22 | 7 |
| Invariantes adicionais de aceite/legado/backup | 20 |
| Concorrência de estados/aceite/atribuição/fila | 7 |
| Integridade de anexos | 8 |
| Migration de anexos | 2 |
| Transações Storage/metadados | 4 |
| Upload concorrente/timeout | 3 |
| Revisão conservadora de órfãos | 27 |
| Visibilidade de inventário | 8 |
| Imagens, listagem, assinatura e download controlado | 26 |
| Chat publicado e regressão da integração | 3 + 13 |
| Roteiro ponta a ponta | 1 |

Também foram mantidos testes de models/repositories, JWT, histórico e regras
administrativas. Imagens usam adapter real sobre SDK/HTTP controlado; não são
teste do Supabase compartilhado. O inventário de 1006 objetos e --apply recusado
continuam cobertos. Headers de link, TTL, SHA-256 e decodificação são conferidos.

Comandos executados, com configuração SQL local recebida pelo processo e valores
de conexão omitidos:

```powershell
python -m alembic heads
python -m alembic upgrade head
python -m alembic current
python -m alembic check
python -m pytest tests -q --tb=short --basetemp=.pytest_tmp_final -p no:cacheprovider --junitxml=.pytest_tmp_evidence/final.xml
python -m scripts.validate_security_release --container automatize-presentation-test-20261110 --audit-label presentation-2026-11-10 --output .pytest_tmp_evidence/restore.json
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/demo_apresentacao.ps1
python -m scripts.audit_secrets
git diff --check
```

## Quatro commits locais para publicação autorizada

| Grupo | Mensagem do commit | Escopo |
| --- | --- | --- |
| 1 | `fix(db): vincular aceite ao cliente e consolidar validacao de seguranca` | Migration/models, auditorias, restore, testes SQL/migrations e revisão de rollout |
| 2 | `feat(anexos): validar bucket privado e acesso temporario a imagens` | Endpoints, schema público, service/repository, adapter e testes de imagens |
| 3 | `fix(chat): validar payload e revalidar vinculos na integracao` | Endpoint publicado e regressões adicionais |
| 4 | `test(demo): preparar roteiro reproduzivel e evidencias da apresentacao` | Demo local, roteiro, descrição de PR, manifesto e resultados atuais |

O manifesto exato para revisão/seleção é
`docs/integracao-final-henrique-20261110-files.txt`. Não usar seleção abrangente.
A proposta contém **32 arquivos: 18 modificados e 14 novos**. O diff completo
para leitura está em `docs/integracao-final-henrique-20261110.diff` na pasta
original; ele é um artefato de revisão e não faz parte dos commits propostos.
Os quatro commits locais foram autorizados na solicitação de organização da
entrega. Publicação continua pendente: nenhum push, PR ou merge foi executado.
A descrição de PR para HML está pronta em
`docs/pr-integracao-henrique-20261110.md`.

Na organização dos commits, o conteúdo dos 32 arquivos foi comparado exatamente
ao diff anteriormente validado, e o JUnit preservado confirmou 932 aprovados,
331 PostgreSQL e 18 SCRUM-71. A suíte não foi reexecutada nesta organização:
código, migrations, testes e script de demonstração permaneceram idênticos;
somente quatro documentos deste manifesto foram atualizados para registrar
os commits e o plano de publicação. Nenhum resultado novo foi inventado.

Foram conferidos os quatro grupos sem mistura de arquivos: 14 de integridade
e segurança, nove de imagens/anexos, dois de chat e sete de demo/documentação.
A auditoria examinou o conteúdo staged, incluindo busca por segredos conhecidos
do .env original sem imprimir seus valores. Os hashes das outras worktrees
foram comparados antes de cada commit e ao final.

Após autorização de publicação e nova conferência das referências remotas,
executar na worktree de integração:

```powershell
git fetch origin '+refs/heads/HML:refs/remotes/origin/HML'
git log --oneline origin/HML..HEAD
git diff --check origin/HML...HEAD
git diff --stat origin/HML...HEAD
git push -u origin integracao/henrique-apresentacao-20261110
gh pr create --base HML --head integracao/henrique-apresentacao-20261110 --title "Integra seguranca de persistencia, imagens privadas e validacao final de Henrique" --body-file docs/pr-integracao-henrique-20261110.md
```

Esses comandos são um plano, não foram executados. Se a HML avançar, revisar
as diferenças e a compatibilidade antes de publicar; não fazer merge automático.

Os relatórios/JSON históricos copiados das entregas anteriores permanecem no
worktree para referência, mas estão fora da proposta de commit. Dumps, patches
de transporte, resultados brutos, caches, cópias completas frontend/backend e
segredos também ficam fora. Não foram apagados.

## Pendências externas e estado de apresentação

Pronto: demonstração local reproduzível, código consolidado, testes atuais,
diff concreto, manifesto seletivo, quatro commits locais e descrição de PR.

Pendente de Alisson/responsáveis:

1. Nomes e privilégios efetivos das roles SQL da FastAPI e do Alembic no Render.
   `postgres` foi medido somente no cluster de teste; owner não prova identidade.
2. Snapshot fiel do principal, com ACLs/roles reais, e ensaio isolado correspondente.
3. Validação autorizada de upload/listagem/download no Storage real e recuperação
   dos bytes, sem expor keys/signed URLs.
4. Revisão da migration/legado e diff, autorização explícita de publicação/PR
   e, depois, rollout. Os quatro commits locais já foram autorizados.

SCRUM-87 fica em dry-run; falta coordenação global e exclusão condicional segura
por geração. A limpeza real permanece desabilitada. Sem alteração nos Supabase
principal/HML ou em objetos Storage. As regras integradas dos demais membros e
todas as branches anteriores foram preservadas.

Auditoria final: zero correspondências potenciais de credenciais nos arquivos
propostos e nos versionados; zero bytecode versionado. O .env preexistente da
árvore original foi sinalizado só pelo nome e permanece fora da proposta.
`git diff --check` passou, assim como a aplicação de verificação do patch em
índice privado da HML. Nesta organização, cada staging foi limitado ao grupo
aprovado e passou em `git diff --cached --check`; o índice final fica vazio.
