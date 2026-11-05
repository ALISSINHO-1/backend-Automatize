# Mapeamento Flutter → FastAPI → persistência

Referência executável consolidada: raiz Git da branch Henrique-Silva, com as
regras oficiais da HML `f4f89e787cde2333f4b99696e7c9d15a61fdfabb` (PR #12).
A cópia `backend-Automatize-HML/` foi comparada por conteúdo e preservada como
evidência da reprodução. Nenhuma versão inteira foi substituída.

| Fluxo Flutter | Endpoint FastAPI | Schema | Service → repository/model/tabela | Resultado |
| --- | --- | --- | --- | --- |
| LoginScreen: POST JSON email/senha | POST `/auth/login` | LoginRequest → TokenResponse | AuthService → UserRepository → User/users | Compatível; token access_token, bearer, 401 genérico, 422 sem entrada sensível |
| DemandService.buscarDemandas | GET `/demandas?offset=N&limit=100` | list[DemandaResponse] | DemandaQueryService → PedidoRepository → Pedido/pedidos | Compatível; filtro de acesso antes da paginação; UUID, Decimal como string, datas ISO e nullable aceitos pelo model Flutter |
| NovaDemanda/DemandaStore | POST `/demandas` | DemandaCreateRequest → DemandaResponse | DemandService.criar → PedidoRepository/Pedido + AuditoriaLog | Compatível para CLIENTE; Flutter não fornece seleção de cliente exigida para ADMIN |
| DemandDetailsPage | GET `/demandas/{id}` existe | DemandaResponse | DemandaQueryService → PedidoRepository/Pedido | Tela usa objeto da lista; abertura só por ID não busca detalhes no estado atual |
| Filtro e dashboard | Reutilizam GET `/demandas` | Mesmo schema | Mesma consulta com escopo | Sem backend scheduler; polling controlado a cada 30 s nas duas listas e no painel |
| Editar demanda (sem integração Flutter completa) | PATCH `/demandas/{id}` | DemandaUpdateRequest | DemandService.editar → Pedido/pedidos + auditoria | Backend implementado e testado |
| Etapas (sem operações Flutter completas) | GET/POST `/demandas/{id}/etapas`, POST `.../{etapa_id}/conclusao` | EtapaCreateRequest/EtapaResponse | DemandService → EtapaOperacionalRepository → etapas_operacionais | Model/migration/repository existentes, bug de created_at corrigido |
| Avanço de estado (sem operação Flutter completa) | POST `/demandas/{id}/status` | StatusUpdateRequest → DemandaResponse | DemandService → Pedido/etapas/histórico/auditoria | Backend usa autorização e máquina de estados; aprovação é caminho separado |
| Homologação Flutter | POST `/demandas/{id}/aceite`, `/rejeicao` existem | AprovacaoSolicitacaoSchema/AprovacaoRespostaSchema ou RejeicaoRequest | DemandService/AprovacaoService → AceiteFormal/Pedido/HistoricoStatusPedido/AuditoriaLog | Flutter ainda demonstrativo; não envia versão/declaração/motivo à API |
| Seleção de anexos Flutter | POST `/demandas/{id}/evidencias` existe | multipart arquivo + ocorrencia_id opcional → AnexoResponse | DemandService → AnexoService/AnexoRepository → Anexo/anexos; SupabaseStorage | Flutter seleciona localmente; não faz upload. MIME HTTP agora chega ao validador existente |
| Histórico Flutter | GET `/demandas/{id}/historico` | list[AuditoriaResponse] | DemandService.listar_auditoria → AuditoriaLogRepository/auditoria_logs | Contrato difere de HistoricoEstadoModel; exemplos fixos foram removidos da tela |
| Consultas administrativas novas | GET `/usuarios/tecnicos`, `/usuarios/clientes`, `/usuarios/clientes/{UUID}` | UserSummary | UserQueryService → UserRepository → users com vínculo via pedidos | ADMIN só lista técnicos; TÉCNICO só clientes relacionados; CLIENTE recebe 403; sem e-mail/senha/hash |
| Responsável (sem integração Flutter completa) | PUT `/demandas/{id}/responsavel` | ResponsavelRequest → DemandaResponse | DemandService → users/pedidos/auditoria_logs | Somente ADMIN; valida técnico ativo; sem FK ADMIN → TECNICO inventada |

## Contratos e autenticação

`AppConfig` usa API_BASE_URL configurável, padrão localhost:8000. O router não
acrescenta `/api/v1` às URLs. APIs usam `PLANEAMENTO`, não traduzir o enum
persistido para `PLANEJAMENTO`; o filtro existente reconhece ambas as grafias.
UUID não é substituído por nome. percentuais são validados entre 0 e 100; campos
opcionais nulos são tratados explicitamente. Respostas de escrita usam 201 onde
declarado; 401 invalida apenas a sessão que emitiu a requisição, 403 não apaga JWT.

JWT fica em memória no Flutter, sem persistência em shared_preferences; reabrir
a página exige login. Bearer é acrescentado pelo interceptor usado pelo serviço.
O interceptor legado duplicado em api_cliente.dart não tem consumidores nas
fontes recebidas. O guard de navegação não substitui autorização: backend
recarrega usuário ativo e perfil do banco em cada requisição. Logout Flutter
remove a sessão local; não há revogação central de JWT por logout.

`PedidoService.atualizar` não é consumidor de endpoint atual; seus consumidores
encontrados são testes. A assinatura foi preservada, mas agora atualização exige
usuario_id de ator ativo, valida escopo/perfil, usa recarga FOR UPDATE após a
corrida reproduzida, compartilha a validação de transição e audita a operação.
Edição direta de progresso sem transição é recusada. Um caller interno continua
responsável por fornecer ID do ator autenticado, nunca um ID arbitrário do body.

## Consolidação da HML e da SCRUM-71

A regra oficial exige ao menos uma etapa operacional e todas concluídas antes de
entrar em HOMOLOGACAO. Ela foi reconciliada na regra pura, no validador central
compartilhado pelos services e no helper legado validar_e_transitar. Contagem e
pendências vêm das etapas persistidas. Locks, escopo, auditoria e transações da
raiz foram preservados; testes de homologação agora preparam etapas válidas.

`DemandService.listar_estados` foi preservado do PR #12 na raiz consolidada.
Ele já monta o contrato de linha do tempo esperado pelo Flutter; não foi
encontrada rota na HML expondo esse método, e o contrato de `/historico` não foi
trocado durante a consolidação.

O backend raiz retorna auditoria em `/historico`, com `acao/detalhes/created_at`,
enquanto o Flutter espera `estado_anterior/novo_estado/usuario_responsavel/timestamp`.
Não mapear auditoria genérica cegamente para mudanças de estado. A integração
HTTP da linha do tempo permanece pendente; a regra de etapas está definida e
implementada, sem decisão de negócio pendente sobre homologação sem etapas.

## Limites da comprovação

Testes Flutter usam transporte HTTP simulado com contratos reais e interceptor.
Testes FastAPI usam TestClient, JWT real e PostgreSQL local real, com Storage
simulado. Foi comprovada conexão PostgreSQL e leitura de metadados de bucket real
somente em modo leitura. Não foi feito teste E2E em navegador/aparelho com upload
real. Logo compatibilidade de login/listagem/criação não significa fluxo completo
de homologação, histórico e anexos integrado no produto.
