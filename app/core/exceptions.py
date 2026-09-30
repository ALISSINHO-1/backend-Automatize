class RegraNegocioException(Exception):
    """Excecao base para infracoes de regras de negocio."""
    def __init__(self, mensagem: str):
        self.mensagem = mensagem
        super().__init__(self.mensagem)

# Alias para compatibilidade com o router
BusinessRuleException = RegraNegocioException

class TransicaoEstadoInvalidaException(RegraNegocioException):
    """Lancada quando se tenta uma mudanca invalida no ciclo de vida do pedido."""
    pass

class AprovacaoNaoAutorizadaException(RegraNegocioException):
    """Lancada quando a aprovacao formal nao cumpre os requisitos."""
    pass
