# Homologação e restauração isoladas

Este procedimento usa apenas dados sintéticos e PostgreSQL descartável local.
Não serve para operar o Supabase compartilhado. A URL explícita deve ter host
loopback, porta explícita e nome contendo `test`; os scripts recusam outro alvo.
Nunca passar a URL do ambiente compartilhado como TEST_DATABASE_URL ou HML_DATABASE_URL.

## Subir PostgreSQL descartável

```powershell
docker run --detach --rm --name automatize-audit-20261031 --label automatize.audit=2026-10-31 --publish 127.0.0.1:55439:5432 --env POSTGRES_DB=automatize_test --env POSTGRES_HOST_AUTH_METHOD=trust postgres:17
$env:TEST_DATABASE_URL='postgresql+psycopg2://postgres@127.0.0.1:55439/automatize_test'
```

O trust é exclusivo do container descartável, vinculado a loopback, sem dados
reais. Não reutilizar essa configuração em servidor compartilhado. O banco de
testes não é uma cópia de produção. Não há senha fixa em código ou no comando.
Instalar as dependências já declaradas no projeto e usar o Python da `.venv`.

## Testes e migrations

```powershell
python -m pytest tests -q
python -m alembic heads
python -m alembic history
$env:DATABASE_URL=$env:TEST_DATABASE_URL
python -m alembic upgrade head
python -m alembic check
Remove-Item Env:DATABASE_URL
```

Não é preciso definir DATABASE_URL globalmente para executar pytest. As fixtures
trocam temporariamente essa variável para Alembic, restaurando-a depois. Os testes
de configuração que esperam ausência de DATABASE_URL devem continuar isolados.
As fixtures criam roles anon/authenticated/service_role apenas no cluster local.
SCRUM-71: fixtures que chegam a HOMOLOGACAO precisam cadastrar ao menos uma etapa
e concluir todas. Demanda sem etapas deve ser usada somente nos testes que
verificam a recusa da transição. Não adaptar a regra para fixtures antigas.
Os testes normais desfazem suas transações; testes de concorrência precisam de
commits visíveis entre conexões e deixam dados sintéticos até destruir o container.
Testes de upgrade e seed criam outros bancos vazios nesse mesmo cluster.

Head final: `b6e1c8a4d230`. As duas migrations novas recusam downgrade automático:
não é seguro reconstruir grants anteriores ou desproteger evidência por adivinhação.
Esse bloqueio é explícito; não é uma promessa de downgrade testado.

## Massa reproduzível

Definir `HML_DATABASE_URL` explicitamente para um banco local descartável migrado.
Fornecer as três variáveis `DEMO_ADMIN_PASSWORD`, `DEMO_TECNICO_PASSWORD` e
`DEMO_CLIENTE_PASSWORD` pelo ambiente ou gerenciador de segredos; não salvar seus
valores em documentação, argumentos de linha de comando ou no Git. Os e-mails
DEMO são configuráveis. O novo comando não carrega essas senhas de `.env`.

```powershell
python -m scripts.seed_hml_environment
python -m scripts.seed_hml_environment --apply
```

O primeiro comando faz dry-run real e desfaz tudo. O segundo persiste apenas no
alvo local validado. O processo reutiliza o seed existente de três perfis e sua
ocorrência, acrescenta uma etapa pendente e uma entrega aprovada com etapa
concluída, histórico, auditoria e aceite formal. Não altera contas existentes,
não redefine senhas e recusa conflitos. Uma transação externa com savepoints
torna atômicos os commits dos services: erro tardio desfaz toda a massa.
Repetição com a mesma configuração preserva IDs e contagens.

Arquivos de Storage não são fabricados por esse seed. Criar metadata apontando
para um arquivo inexistente violaria a integridade auditada. Uploads são testados
com Storage simulado e conteúdo validado. Uma massa com objetos reais exige
Storage de homologação isolado e um plano de backup dos objetos separado.

## Restauração comprovável sem sobrescrita

```powershell
python -m scripts.validate_hml_restore --container automatize-audit-20261031
```

O script exige HML_DATABASE_URL local e confere o label e a porta publicados do
container. Usa pg_dump custom e pg_restore em um banco **novo e vazio**, sem
`--clean`. Não faz DROP, TRUNCATE, downgrade, stamp nem restaura sobre banco
existente. O arquivo temporário fica dentro do container. Verifica contagem e
hash de todas as linhas de nove tabelas, revisão Alembic e presença de três
triggers, sem exportar conteúdo de registros ou hashes de senha na saída.

Para validar também a restauração de ACLs, não usar `--no-privileges`: criar as
roles locais necessárias, restaurar no banco vazio e comparar RLS, grants e
EXECUTE de funções. O ensaio de 01/11/2026 executou pg_restore com `--no-owner`
e `--exit-on-error`, preservando ACLs; catálogo de acesso e hashes coincidiram.
O helper anterior usa `--no-privileges` e verifica somente dados/triggers;
esse modo não deve ser interpretado como validação da política de acesso.

A restauração cobre somente PostgreSQL sintético. Não equivale a restore de
Supabase Auth, configuração do provedor, secrets ou objetos do Storage. Um plano
de desastre de produção precisa desses itens, RPO/RTO e ensaio próprio aprovado.

## Reconciliação de anexos

```powershell
python -m scripts.reconcile_storage
```

Esse comando é exclusivamente READ ONLY, com snapshot REPEATABLE READ de
metadados PostgreSQL/Storage. Não baixa arquivos. Exporta somente hash do caminho
e classificação. Ausência de timestamps, inventário incompleto, caminhos
desconhecidos, objeto recente (24 h) ou pedido ainda existente impedem inferência
de limpeza. Mesmo um candidato continua com `delete: false`. Guardar a saída
JSON em local operacional restrito para revisão. Não existe opção `--apply`.
O inventário agora compara as duas direções: objeto sem registro e registro sem
objeto no bucket configurado. Sem snapshot completo, não conclui ausência de
arquivo. A comparação usa metadados do Storage, sem baixar ou excluir conteúdo.

Uma exclusão controlada futura exige: confirmação humana de cada candidato,
revalidação independente em nova leitura, exclusão de casos ambíguos, janela sem
uploads/commits concorrentes, trilha durável e credencial específica. Não foi
implementada nem executada limpeza no Storage real. SCRUM-87 permanece parcial.

## Encerramento

Depois da revisão das evidências locais, parar somente o container criado para
esta auditoria. Ele foi iniciado com `--rm`; seus bancos e arquivos temporários
são descartáveis. Não usar comandos de limpeza sobre outros containers ou volumes.
