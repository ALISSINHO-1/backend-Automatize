# Proposta de PR para HML — não publicado

Título: **Integra segurança de persistência, imagens privadas e validação final de Henrique**

Base: `HML`. Head: `integracao/henrique-apresentacao-20261110`.

## Descrição pronta para revisão

Escopo: SCRUM-82 (integridade de aceites e auditoria), SCRUM-87 (integridade de
anexos e inventário dry-run), SCRUM-103 (RLS e privilégios), melhorias de
imagens/anexos, hardening do chat e demonstração reproduzível.

Um aceite inserido por SQL podia apontar para cliente diferente do dono da
demanda. A migration d1f6a8c20391 vincula o aceite ao par pedido/cliente e recusa
conteúdo vazio, preservando a proteção de evidências e abortando em legado
incompatível sem apagar dados. Reutiliza as migrations publicadas de RLS/grants.

O acesso a imagens reutiliza anexos: confirma bucket privado, valida PNG/JPEG
e tamanho, limita metadados, autoriza por demanda e assina URLs por 300 segundos.
Preserva PDFs/documentos, compensação e tratamento de commit incerto. O chat
publicado mantém rotas/participantes e passa a recusar campos forjados/caractere
nulo e recarregar o vínculo persistido sob lock.

## Validação executada

- 932 passed, 0 failed/errors/skipped, 2 warnings; 331 testes PostgreSQL 17.
- Inclui os 18 casos SCRUM-71, segurança SQL, imagens/HTTP controlado e chat.
- Upgrade do zero e de snapshot sintético antigo com grants/RLS antigos;
  backup/restore de schema/dados/ACLs/owners e três triggers, com comparação.
- Alembic com head/current d1f6a8c20391 e check sem divergências.
- Demo local executável e roteiro de três minutos, com PostgreSQL real e
  Storage simulado; auditoria de segredos e diff sem erros.

Os resultados são da execução final registrada no JUnit da integração. Na
organização dos quatro commits locais, confirmou-se a igualdade com o diff
validado; apenas documentação foi atualizada, sem reexecutar a suíte.

## Escopo e integração

A base é origin/HML em ae327b5. Não altera as treze migrations publicadas nem
recria chat/anexos. A migration local alternativa c7a1e9b4d602 e seu contrato
`/mensagens` permanecem preservados na árvore original e ficam fora deste PR.
Não remove regras administrativas, fila, visualizações ou requisitos de etapas
já integrados por outros membros. Os artefatos do PR22 são reutilizados; se ele
for integrado antes, conferir esses arquivos sem duplicar a funcionalidade.

Não incluir dumps, patches de transporte, caches, cópias frontend/backend ou
resultados históricos como evidência da suíte atual. A lista exata está em
`docs/integracao-final-henrique-20261110-files.txt`.

## Limites operacionais

Sem alteração no Supabase principal/HML e sem teste do Storage real. Snapshot
sintético não prova equivalência com o principal. Confirmar roles SQL do Render
e do Alembic, restaurar snapshot fiel e testar Storage em destino autorizado.
SCRUM-87 mantém --apply desabilitado; não há executor de limpeza real.

A migration exige revisão do legado e janela para constraints/locks. Não usar
stamp, downgrade automático ou grants públicos para contornar falhas.

## Revisão e apresentação

Ver `docs/apresentacao-tecnica-henrique-2026-11-10.md` e
`docs/integracao-final-henrique-2026-11-10.md`. Esta descrição é um arquivo local;
nenhum PR foi aberto ou modificado por esta entrega.
Os quatro commits estão apenas na branch local; publicação aguarda autorização.
