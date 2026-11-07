# Storage — backup, recuperação e alternativa à limpeza

Base técnica: Henrique-Silva `a462850`. Procedimento preparado para aprovação,
sem conexão ou alteração no Supabase compartilhado nesta rodada.

## Fronteiras comprovadas

O SDK instalado é storage3 2.33.0. `remove(paths)` envia uma lista de caminhos
ao endpoint de remoção; não recebe ID/geração/precondição individual. A
[referência Python](https://supabase.com/docs/reference/python/storage-from-remove)
documenta esse contrato. A [compatibilidade S3](https://supabase.com/docs/guides/storage/s3/compatibility)
informa ausência de versionamento e não comprova compare-and-delete por geração.
Condições de HEAD/GET não tornam o delete posterior atômico. ETag do conteúdo
também não diferencia necessariamente duas gerações com bytes iguais.

Portanto não há suporte suficiente **comprovado para o adapter atual** para
implementar o limpador destrutivo solicitado. Não se afirma impossibilidade de
qualquer versão futura do servidor. Não foram habilitados apply, move, remoção
SQL de storage.objects, nem substituição de objetos.

[Backups PostgreSQL do Supabase não incluem os bytes do Storage](https://supabase.com/docs/guides/platform/backups).
Restaurar storage.objects recupera metadados, não os arquivos. Um dump isolado,
uma listagem ou duas leituras de metadados não comprovam um ponto de recuperação
consistente dos dois sistemas.

## Inventário de todos os escritores identificados

| Caminho | Operação efetiva | Coordenação e risco |
| --- | --- | --- |
| POST /demandas/{id}/evidencias → DemandService.registrar_evidencia | valida ator/escopo/estado e mantém FOR UPDATE do pedido durante o envio | serializa aquele pedido, sem barreira global do bucket |
| AnexoService.criar → SupabaseStorage.upload | valida conteúdo e envia com UUID novo e upsert=false | bytes existem antes do commit dos metadados |
| SupabaseStorage.upload, exceção do SDK | tenta remover somente o caminho UUID gerado para compensar ACK incerto | timeout não prova ausência do objeto; falha da compensação é reportada |
| AnexoRepository.create + AnexoService | registra vínculo pedido/ocorrência/autor, anexo e auditoria no PostgreSQL | FKs e transação; falha pré-commit tenta compensação |
| AnexoService, falha de banco/auditoria | rollback e compensação do upload | commit com conexão invalidada preserva objeto e reporta estado incerto |
| AnexoService, refresh após commit | não remove bytes de anexo já confirmado | preserva referência confirmada |
| DemandService.excluir, PedidoService.excluir e FKs | exclusão de pedido não concluído pode remover metadados de anexos em cascata | não remove bytes; cria candidatos para revisão, não autorização de limpeza |
| BaseRepository.delete / SQL administrativo / restauração | podem alterar/remover/recriar referências | precisam participar da janela global, mesmo sem chamar o SDK |
| scripts.reconcile_storage e cleanup_review | inventário SQL e ensaio de leitura | nenhuma mutação de Storage ou autorização de delete |
| PR15 já em HML/main | adiciona leitura/listagem/signed URL; mantém upload e delete por caminho | signed URL de leitura não cria objeto; não adiciona CAS de geração |
| SDK genérico, Dashboard, S3, jobs e credenciais externas | podem upload/substituir/mover/copiar/remover fora do FastAPI | não são enumeráveis somente pelo repositório; operação precisa inventariá-los |

Não foram encontrados consumidores de move/copy/update/empty/delete_bucket nos
caminhos de produção versionados examinados. O SDK disponibilizar métodos não
significa que a aplicação os use. O backend não substitui objetos por upsert.
O campo caminho_storage é protegido no repository; uma credencial SQL/Storage
privilegiada ou restore ainda pode reutilizar caminhos. Não há UNIQUE SQL do
caminho nem FK para os bytes do Storage.

## Backup separado dos arquivos

1. Aprovar responsável, janela, RPO/RTO, escopo, retenção, destino externo e chave
   de criptografia. Usar credencial de leitura quando disponível; service keys
   amplas não se tornam read-only por serem usadas em um job de backup. Se não
   houver credencial restrita, registrar o risco e obter autorização específica.
   Não criar policies ou rotacionar credenciais reais nesta tarefa.
2. Coordenar **todos** os escritores da tabela anterior. Drenar uploads, commits,
   retries, compensações e operações do provedor. Pausar só uma instância da API
   ou adquirir advisory lock só no script não basta. Se não for possível provar
   a drenagem, rotular a cópia como parcial/crash-consistent; não aprová-la como
   backup consistente nem usá-la como autorização de exclusão.
3. Capturar ponto PostgreSQL consistente e inventário completo de metadados,
   com a role enxergando todas as linhas. `reconcile_storage --dry-run` agora
   recusa RLS filtrando tabelas, falta de grants, bucket inexistente ou público.
   SQL REPEATABLE READ não congela o serviço de arquivos.
4. Exportar a configuração do bucket/policies/owners para evidência restrita.
   Criar manifesto com snapshot ID, bucket, storage ID, path lógico, timestamps,
   tamanho, tipo, checksum SHA-256 dos bytes e referência ao ponto do banco.
   Registrar versão/geração somente se o provedor realmente a fornecer; não
   promover timestamp/ETag/UUID de catálogo a garantia de delete condicional.
5. Copiar bytes com operações de leitura, por exemplo o download do SDK já
   instalado, mantendo a coordenação. Fazer verificação de identidade antes/depois
   e comparar o inventário final. Qualquer substituição, objeto ausente, página
   incompleta, erro ou timeout invalida a completude. Duas verificações sozinhas
   não eliminam a janela entre elas.
6. Guardar bytes em prefixo exclusivo por snapshot em destino independente e
   criptografado. Não usar sync com delete, espelhamento destrutivo ou sobrescrita
   da cópia anterior. Aplicar imutabilidade/WORM se o destino oferecer e houver
   aprovação. Nunca assumir que o bucket de origem tem versionamento.
7. Conferir hashes, tamanhos, contagens, duplicidades e relações banco↔manifesto.
   Preservar também arquivos ambíguos/legados em backup; eles não são candidatos
   automáticos a descarte. Chaves de descriptografia e configuração ficam em
   cofre separado; JWT, signed URLs, secrets e bytes não entram no Git/log público.
8. Assinar/aprovar o hash do manifesto final e registrar o ensaio de recuperação.
   Arquivo existente ou resposta HTTP de sucesso não prova recuperação.

## Ensaio de recuperação dos bytes

Usar projeto/bucket **novo, privado e isolado**, com autorização para escritas
somente nesse destino e credenciais que não alcancem o bucket compartilhado.
Não executar este fluxo no Storage real nesta sessão.

- Restaurar a aplicação/schema/dados no ambiente isolado e planejar separadamente
  os schemas geridos pelo Supabase. Um clone/dump pode ter metadados de Storage
  sem os bytes; não considerar essas linhas como arquivos restaurados.
- Preparar bucket privado vazio e configuração/policies revisadas no destino.
  Restaurar bytes pela API suportada, mantendo paths lógicos e upsert=false.
  Não inserir/apagar diretamente storage.objects para contornar colisões ou
  arquivos ausentes. Se o fluxo de restore do provedor já criou metadados que
  colidem, parar e usar procedimento suportado ou outro bucket/projeto vazio.
- IDs e timestamps do Storage de destino podem ser diferentes. Registrar mapa
  origem→destino e validar policies baseadas em owner. As referências da aplicação
  são por caminho/configuração de bucket, não por FK ao ID do catálogo Storage.
- Baixar novamente cada objeto restaurado e comparar SHA-256 dos bytes. Conferir
  vínculos, MIME, permissões e acesso horizontal com usuários sintéticos.
  Signed URLs e sua expiração exigem o artefato que contém esse contrato.
- Retomar falha parcial somente pelo manifesto aprovado: objeto já presente com
  identidade/hash esperado é no-op auditado; divergência ou timeout é estado
  incerto, não permissão para sobrescrever. Preservar a cópia anterior e o destino
  parcial para investigação. Não trocar tráfego sem reconciliação completa.

O dump/restore PostgreSQL ensaiado localmente não comprova este restore de bytes.
Sem destino/credenciais aprovados, essa parte permanece operacionalmente pendente.

## Alternativas à remoção destrutiva

**Alternativa imediata: quarentena lógica.** Recibo restrito e aprovado com IDs
dos candidatos, sem mover, renomear, revogar acesso ou apagar o objeto original.
Uma cópia para backup independente pode ser feita pelo procedimento acima.
Isso preserva dados, mas não recupera espaço nem conclui a limpeza.

**Quarentena física não foi implementada.** Move costuma incluir remoção da
origem e copy seguida de delete tem a mesma corrida de path reutilizado. Mesmo
alterar ACL/prefixo pode afetar arquivo que ganhou referência. Nenhuma dessas
operações é segura apenas porque se chama quarentena.

**Alternativa arquitetural: serviço controlado pelo provedor/operador.** Exige
identidade imutável/geração e exclusão condicional comprovadas, mais protocolo
obrigatório de reservas/fencing para API, commits, retries e compensações.
Outra possibilidade requer exclusividade real do namespace, eliminação de todos
os escritores externos e drenagem comprovada no servidor. É uma decisão de
arquitetura/infraestrutura, não uma flag booleana no cliente.

Antes de qualquer alteração futura, exigir intenção durável fora da transação
que possa falhar: aprovador, executor, snapshot/hash aprovado, ID/geração,
referência do backup, motivo, timestamps e request ID. Registrar resultado,
incluindo estado incerto, e recuperação testada. Repetir somente por identidade
e estado comprovado, nunca por path. Falha de auditoria ou da barreira interrompe
o lote. O ensaio atual retorna um registro sanitizado, mas não implementa esse
ledger nem um executor de exclusão.

**Situação:** preparação e testes locais disponíveis; SCRUM-87 permanece PARCIAL.
O bloqueio técnico é real: o contrato necessário de exclusão e a barreira global
não estão comprovados. Aprovação operacional sozinha não substitui essas garantias.
