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
