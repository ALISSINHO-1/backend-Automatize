# Onboarding e escopo DEV/SAAS: primeira etapa

Este PR e somente codigo. Nenhuma migration foi executada em Supabase.

## Identidades e autorizacao
- `users` permanece identidade global; `perfil=ADMIN` e exclusivo da equipe.
- Novos registros publicos sao `PENDENTE`, `CLIENTE` e sem contrato. O token de uma conta PENDENTE so pode consultar `GET /auth/contexto`; as APIs operacionais e `/auth/me` recusam.
- `organizacoes` armazenam empresas; `organizacao_usuarios` armazena `GESTOR` e `COLABORADOR` locais. Gestor nunca vira ADMIN global.
- `contratacoes` separam DEV pessoal de SAAS empresarial e estado de vigencia.
- `GET /auth/contexto` devolve apenas contratos pessoais ativos e empresas onde a pessoa e membro ativo e existe contrato SAAS ativo. O contexto nao e selecionado livremente pelo frontend.
- Dados DEV existentes e usuarios anteriores preservados por default `situacao_cadastro=ATIVO`.

## Bloqueios obrigatorios
- `PUBLIC_SIGNUP_ENABLED=false` por padrao; nao ligar em ambiente publico ate adicionar verificacao real de e-mail e protecao contra abuso (rate limiting/Turnstile na borda).
- O cadastro PENDENTE nao pode ser promovido por `/usuarios/{id}/ativo` ou troca de perfil. Criar fluxo futuro com verificacao de titularidade e aprovacao auditada.
- Ainda nao existem consultas/mutacoes SaaS empresariais: `pedidos.cliente_id` continua pessoal. Nao ativar dashboard de empresa ate incluir escopo por `organizacao_id`, validar tenancy em todas as rotas e fazer regressao cross-tenant.
- A UI de cadastro/boas-vindas e os convites tambem fazem parte da proxima etapa; nao publicar cadastro ainda.

## Implantacao
1. Revisar a chain Alembic e executar primeiro em PostgreSQL 16 de teste descartavel, com `alembic check` e testes.
2. Revisar roles SQL runtime/migration, backup e impactos. HML so apos aprovacao; principal exige validacao especifica.
3. Revalidar RLS/ACLs para novas tabelas e impedir grants `anon`/`authenticated`.
4. Implementar verificacao de e-mail, convite e vinculo comercial antes de habilitar o cadastro.

## Gestao comercial por ADMIN
- `POST /comercial/organizacoes`: registra empresa com trilha de auditoria.
- `POST /comercial/organizacoes/{id}/membros`: vincula apenas usuarios CLIENTE ja ativos, com papel empresarial GESTOR ou COLABORADOR.
- `POST /comercial/contratos/dev`, `/contratos/saas`: cria contratos PENDENTE e registra autor.
- `PATCH /comercial/contratos/{id}/ativar`: ativa exclusivamente DEV; contrato SAAS continua bloqueado ate as APIs empresariais validarem empresa_id em cada consulta/mutacao.
- Apenas ADMIN global pode operar esse modulo; cliente nunca escolhe seu proprio contrato, perfil ou empresa.
- A criacao/ativacao de contratos representa decisao comercial manual, nao integra pagamento. Nenhum contrato gera faturamento automatico.

## Aprovacao publica DEV
- `POST /comercial/contas/{id}/aprovar-dev`: ADMIN global aprova somente conta PUBLICO que confirmou email; cria ou ativa contrato DEV + transforma PENDENTE em ATIVO na mesma transacao auditada.
- APIs legadas `get_current_user` exigem contrato DEV ATIVA para qualquer cliente PUBLICO. Usuario SAAS sem DEV nao entra nas demandas DEV, mesmo que tenha estado ATIVO.
- LEGADO conserva acesso via escopo `cliente_id` atual. Migracao para contratos estritos deve ser feita depois, com dados e testes.

## Recuperacao de conta e aprovacao DEV adicionadas
- Migration `de24ab6719c0`: `users.origem_cadastro`, `email_verificado_em`, `token_version`, tabela `tokens_conta` com RLS e acesso bloqueado a `anon`/`authenticated`/`service_role`.
- `POST /auth/cadastro` exige `PUBLIC_SIGNUP_ENABLED=true`, SMTP TLS e Cloudflare Turnstile com hostname esperado. Contas novas sao `PUBLICO/CLIENTE/PENDENTE`.
- `POST /auth/verificacao/reenviar`, `POST /auth/verificar-email`, `POST /auth/senha/solicitar`, `POST /auth/senha/redefinir`: token de uso unico, salvo apenas como hash, com expiracao, cooldown de 5 minutos no envio e bloqueio de replay.
- Alterar senha incrementa `users.token_version`; sessao JWT emitida antes e recusada automaticamente.
- `POST /comercial/contas/{id}/aprovar-dev` e exclusivamente ADMIN, exige email confirmado, cria contrato DEV ATIVO e ativa conta em transacao auditada.
- APIs de demandas negam contas PUBLICO sem email verificado + contrato DEV ATIVO e o ADMIN nao consegue cadastrar demandas para clientes PENDENTE.
- Contas preexistentes mantem origem LEGADO e acesso ao seu escopo pessoal; SaaS multiempresa permanece bloqueado.
- `GET /auth/contexto` retorna `situacao_cadastro`, `origem_cadastro`, `email_verificado`, `acesso_dev` e apenas ambientes autorizados.

## Variaveis necessarias, segredos apenas no Render
```text
PUBLIC_SIGNUP_ENABLED=false
PASSWORD_RECOVERY_ENABLED=false
SMTP_HOST=<host>
SMTP_PORT=587
SMTP_USERNAME=<usuario>
SMTP_PASSWORD=<segredo>
SMTP_FROM_EMAIL=<remetente_verificado>
PUBLIC_APP_BASE_URL=https://<dominio-pages-hml>
TURNSTILE_SECRET_KEY=<segredo>
TURNSTILE_EXPECTED_HOSTNAME=<dominio-pages-hml-sem-esquema>
```

## Criticos antes da implantacao
- Banco HML precisa estar na revisao anterior `d1f6a8c20391` e com backup verificado; o backend nao pode ser implantado ANTES de suas migrations incrementais. Main exige plano separado.
- Confirmar as roles SQL e endpoint de email, Turnstile, limites de requisicao na borda WAF e dominio Pages/Render em CORS.
- Testar no navegador login ADMIN/TECNICO/CLIENTE legado, contas PUBLICO pendentes, verificacao, recuperacao, aprovacao DEV, isolamento e regresso de senha.
- **Nao ligar `PUBLIC_SIGNUP_ENABLED` ou `PASSWORD_RECOVERY_ENABLED` apenas porque o CI passou**; sao obrigatorios SMTP real, CAPTCHA real, WAF e restauracao testada.
