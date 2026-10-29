"""Metadados públicos da documentação; sem alteração dos contratos em execução."""

ERROR_RESPONSES = {
    code: {
        "description": description,
        "content": {"application/json": {"example": {"detail": example}}},
    }
    for code, description, example in [
        (
            401,
            "Token ausente, inválido, expirado ou conta inativa.",
            "Não foi possível autenticar.",
        ),
        (403, "Perfil sem permissão para a operação.", "Acesso negado."),
        (
            404,
            "Recurso inexistente ou fora do escopo do usuário.",
            "Demanda não encontrada.",
        ),
        (
            409,
            "Estado incompatível ou recurso imutável.",
            "Demanda concluída é somente leitura.",
        ),
    ]
}
TAGS = [
    {"name": name, "description": description}
    for name, description in [
        (
            "Autenticação",
            "Login JSON com email e senha. Copie access_token para Authorize (Bearer).",
        ),
        (
            "Demandas",
            "Cadastro, consulta, filtros e edição. ADMIN: todas; CLIENTE: próprias; TECNICO: atribuídas.",
        ),
        ("Etapas", "Atividades operacionais e progresso calculado pelo backend."),
        (
            "Homologação",
            "Avanço de estado pela equipe; aceite e rejeição exclusivos do cliente proprietário.",
        ),
        (
            "Ocorrências",
            "Registro de problemas e correções, sempre vinculado a uma demanda autorizada.",
        ),
        ("Anexos", "Evidências privadas, metadados e links temporários de acesso."),
        ("Auditoria", "Eventos persistidos com autor e data. Somente leitura."),
        ("Sistema", "Identificação da API e verificação de disponibilidade."),
    ]
]
DESCRIPTION = """
## Comece aqui
1. Faça login em **Autenticação** com `email` e `senha`.
2. Copie `access_token` e clique em **Authorize**. Informe somente o token.
3. Consulte suas demandas e use os UUIDs retornados nas demais operações.

## Perfis e fluxo
**ADMIN** gerencia a plataforma; **TECNICO** é o desenvolvedor responsável;
**CLIENTE** acompanha e homologa suas próprias demandas. A API sempre verifica o vínculo.

`PLANEAMENTO → EXECUCAO → HOMOLOGACAO → CONCLUIDO`

Homologação exige ao menos uma etapa e todas concluídas. O cliente pode rejeitar
com justificativa e retornar à execução. A conclusão exige aceite formal e torna a demanda imutável.

## Contratos
UUIDs e datas ISO 8601; progresso como string decimal. Listas usam `offset` e `limit`.
401: autenticação; 403: permissão; 404: inexistente/fora do escopo; 409: conflito de regra;
422: entrada inválida. Rotas documentadas correspondem às operações implementadas.
"""
