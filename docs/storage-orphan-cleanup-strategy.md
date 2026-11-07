# SCRUM-87 — estratégia de limpeza controlada

Revisão: 2026-11-05. **Nenhuma limpeza foi habilitada ou executada.** O CLI
`python -m scripts.reconcile_storage --dry-run --output <arquivo-novo.json>`
continua somente leitura. `--apply` é recusado antes de carregar configurações
ou abrir conexão. Não executar essa opção no ambiente compartilhado.

## O que existe

`reconciliation.py` classifica objetos e referências nos dois sentidos.
`scripts/reconcile_storage.py` faz inventário integral dos metadados do bucket
configurado, referências de `public.anexos` e IDs de `public.pedidos`, em uma
transação `REPEATABLE READ READ ONLY`. Erro de consulta produz inventário
incompleto; ausência de permissão não equivale a bucket vazio. Não há paginação
do SDK nem download de arquivos. O inventário SQL não comprova a existência dos
bytes físicos; isso exige consulta ao serviço de Storage.

Na preparação sobre `a462850`, o inventário também passou a exigir visibilidade
completa de anexos/pedidos e de storage.buckets/storage.objects. Falta de SELECT,
RLS filtrando linhas, bucket inexistente ou público abortam o inventário, sem
criar recibo completo. Isso fecha a lacuna entre a verificação posterior e a
captura inicial. Não concede privilégios nem altera policies.

O recibo contém IDs opacos, hashes dos caminhos/bucket, timestamps, contagens,
integridade SHA-256 e `apply_supported=false`; não contém credenciais nem nomes
de objetos. O hash detecta alteração em relação ao recibo aprovado; não autentica
o autor. Guardar o recibo original em repositório de evidências restrito, junto
da aprovação identificada e do hash aprovado. A saída é criada exclusivamente,
sem sobrescrever inventário anterior.

`cleanup_review.py` acrescenta um **ensaio de segunda verificação**, sem adapter
de produção e sem método de exclusão. Recebe o recibo, hash/bucket e IDs
explicitamente aprovados; consulta banco e Storage novamente. Sua conexão deve
ser nova, `READ COMMITTED READ ONLY`, para enxergar commits entre as consultas.
O snapshot do inventário antigo não serve como segunda verificação.

A revisão agora exige SELECT de tabela e ausência de filtragem efetiva por RLS
em `anexos` e `pedidos`, usando `require_complete_visibility`. Resultado vazio de
uma role sem acesso completo não prova ausência de referência. Falha nessa
condição retorna `database_visibility_incomplete` antes de consultar o Storage.
Catálogos e funções usados nessa verificação são qualificados com `pg_catalog`;
o teste com RLS inclui tentativa de shadowing por uma `pg_class` temporária.

Mesmo com todas as condições simuladas satisfeitas, o resultado é
`delete=false, reason=execution_not_enabled`. Flags de coordenação e exclusão
condicional são entradas de simulação, não comprovantes de capacidade real.
O CLI atual não chama esse ensaio e não ganhou executor.

## Condições obrigatórias para um executor futuro

1. Alisson/responsável operacional aprova a janela, escopo, executor, responsáveis
   pela recuperação e retenção de backups. Luís confirma todos os escritores
   concorrentes. Não basta aprovar genericamente a SCRUM-87.
2. Inventariar **todo** o bucket e as referências, registrar início/fim, revisão
   Alembic, ambiente e completude. Não inferir ausência de páginas incompletas,
   falhas de rede ou metadados inacessíveis. Comparar também referências sem objeto.
3. Selecionar exclusivamente IDs presentes naquele inventário como candidatos.
   Aprovação humana deve vincular ator, data, bucket, hash integral do recibo e
   lista exata de IDs. Paths digitados, curingas, prefixos e novos objetos ficam
   fora do lote. Um recibo de outro ambiente/bucket deve ser recusado.
4. Recusar objetos criados ou atualizados nas últimas 24 horas (limite conservador
   atual), sem timestamps confiáveis, com caminho desconhecido/ambíguo, ID
   duplicado, referência existente ou pedido ainda existente. Idade não prova
   abandono. Commits incertos e compensações pendentes exigem análise específica.
5. **Estabelecer uma barreira real contra escritores antes de revalidar.**
   Suspender uploads e esperar uploads, commits, transações em retry e compensações
   em andamento terminarem. A suspensão precisa abranger FastAPI, workers,
   operadores, SQL direto e credenciais privilegiadas de Storage. Alternativa
   futura: protocolo de reserva/fencing obrigatório para todos os escritores,
   mantido até o término e recuperação do lote. Lock consultivo isolado em um
   script, `FOR UPDATE` sobre linhas inexistentes ou REPEATABLE READ não coordenam
   Storage e PostgreSQL. Não existe esse protocolo distribuído no projeto hoje.
6. Consultar o banco novamente em visão atual e obter metadados frescos do objeto
   por identidade. Validar pedido, referências em qualquer registro de anexo,
   bucket, path, ID, timestamps e geração. Repetir imediatamente antes da ação;
   manter a barreira durante a ação. Commit novo ou mudança de referência aborta
   o candidato e exige novo inventário/aprovação, sem expansão automática do lote.
7. Demonstrar em ambiente isolado que o provedor suporta remoção condicional da
   **mesma geração**: identidade/versão opaca e operação atômica compare-and-delete,
   ou mecanismo equivalente formalmente comprovado. ETag, hash, UUID do catálogo
   ou HEAD seguido de `remove([path])` não são garantia atômica por si só.
   `SupabaseStorage.delete` atual usa remoção por caminho, sem precondição de
   versão; por isso é inadequado como executor de reconciliação. O inventário
   atual não coleta versão de objeto; `ObjectEvidence.version` opcional é apenas
   um ponto de extensão para um adapter com essa capacidade comprovada.
8. Não reutilizar caminhos de upload e manter `upsert=false`. Os UUIDs gerados
   atualmente reduzem colisões, mas não impedem que outra credencial reutilize
   um caminho. Substituição do mesmo path, ainda que com o mesmo conteúdo,
   invalida o candidato se identidade/geração mudou. Sem barreira efetiva e
   identidade condicional comprovada, **abortar sem excluir**.
9. Antes da ação, verificar backup dos bytes e metadados, checksum, permissões,
   plano de recuperação e restauração ensaiada. Quarentena só serve se preservar
   essas evidências e não introduzir nova corrida. Não presumir que backup
   PostgreSQL inclui bytes do Storage ou que o provedor oferece versionamento.
10. Registrar intenção durável antes da ação e resultado depois, em trilha restrita
    fora da transação que possa sofrer rollback: ator/aprovador, recibo, ID,
    geração, horários, estado anterior, motivo, request ID e referência do backup.
    Não registrar JWT, signed URLs, keys ou paths sensíveis em logs públicos.
    Falha na trilha de intenção deve impedir a ação.
11. Timeout na exclusão é resultado **incerto**. Não repetir por path. Reconsultar
    a mesma identidade/geração sob a barreira; ausência daquela geração é no-op
    auditado, objeto substituto é recusado. Idempotência é por lote+ID+geração,
    nunca por nome de arquivo. Falha na reconsulta interrompe o lote.
12. Liberar escritores somente após reconciliar resultados e compensações,
    conferir referências e anexos de clientes sintéticos e obter aceite operacional.

Estas condições são proposta operacional; não representam novos models,
migrations, filas ou tabelas implementadas. Não se autoriza exclusão baseada
somente em duas leituras: há sempre uma janela após a última leitura.

## Testes e limites

`tests/integration/test_orphan_cleanup_review.py` usa PostgreSQL descartável e
Storage simulado que falha caso qualquer delete seja invocado. Cobre commit
concorrente entre verificações, referências novas, pedido existente sem anexo,
timeouts na primeira/segunda consulta ao Storage, substituição de ID/versão/path,
objeto recente, timestamps ausentes/ambíguos, path desconhecido, aprovação ausente,
recibo alterado, coordenação/versão/API condicional ausentes, objeto desaparecido
e troca depois da última leitura. Até o cenário estável recusa execução.

Os testes demonstram recusa segura, não uma exclusão atômica real no Supabase.
As compensações de upload já existentes em `AnexoService`/`SupabaseStorage`
continuam separadas desta proposta; commit incerto preserva objeto para revisão.
Nenhum fluxo novo contorna a autorização dos endpoints ou remove objetos reais.

Foram acrescentados testes com role sem SELECT e com SELECT porém filtrada por
RLS; invalidação da conexão PostgreSQL durante a segunda verificação e recuperação
do pool; rejeição de transação antiga/ativa; candidato duplicado; referência já
existente e conteúdo sanitizado do registro de revisão. O resultado contém ID,
hash aprovado, timestamp, motivo e `delete=false`; persistência durável de intenção
e recuperação de exclusão continuam requisitos de um executor futuro, não uma
funcionalidade alegada pelo ensaio.

## Limite comprovado do adapter disponível

Na instalação examinada, `storage3` implementa `remove(paths)` enviando apenas
`prefixes` ao endpoint de remoção. Não recebe geração/ID nem precondição atômica
por objeto. A [referência oficial Python](https://supabase.com/docs/reference/python/storage-from-remove)
também documenta uma lista de caminhos. A [compatibilidade S3 oficial](https://supabase.com/docs/guides/storage/s3/compatibility)
informa ausência de versionamento; condições de HEAD/GET não constituem contrato
de compare-and-delete de uma geração. A tabela de DeleteObject não comprova essa
garantia. Isso não demonstra que nenhuma versão futura possa oferecê-la; demonstra
que o contrato necessário não está comprovado no adapter e nas fontes consultadas.

Não usar DELETE SQL em `storage.objects` como alternativa: remover metadados não
é uma operação coordenada de remoção dos bytes. Não promover ETag ou timestamp
a identidade imutável sem contrato do provedor. A operação destrutiva permanece
desabilitada, inclusive após todos os testes locais passarem.

**Situação SCRUM-87:** vínculo/validação/compensação/inventário implementados e
testados localmente; estratégia e ensaio de revisão disponíveis. Limpeza real
continua pendente de capacidade técnica comprovada, aprovação e execução
operacional. Não classificar a limpeza como concluída ou aplicada no Supabase.

## Complemento operacional sobre a462850

O mapa de escritores, alternativas de quarentena, coordenação global, auditoria
durável e o plano separado de backup/restore dos bytes estão em
[storage-backup-recovery-runbook.md](storage-backup-recovery-runbook.md).
Quarentena lógica mantém o objeto original; mover/copiar e depois excluir não
elimina a corrida e continua sem implementação destrutiva.

Testes novos exercitam o adapter real sobre SDK simulado em outra thread, com
PostgreSQL real: bytes chegam antes do commit, o inventário os recusa como recentes,
commit posterior passa a proteger a referência, timeout tenta compensação e falha
da compensação deixa estado explícito para revisão. Reutilização de caminho
referenciado não remove essa proteção. As recusas existentes de ID/versão trocados,
referência concorrente e falha de rede continuam na suíte.

HML/main já receberam PR13/15 remotamente; isso não implanta as proteções no
Supabase nem integra o complemento a462850 a essas branches. A branch local
continua sem alterações de contratos, sem novas migrations e com apply recusado.
