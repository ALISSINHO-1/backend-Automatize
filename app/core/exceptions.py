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

class RegistroImutavelException(RegraNegocioException):
    """Lancada ao tentar alterar um aceite formal ou uma demanda ja concluida."""
    pass

class AcessoNegadoException(RegraNegocioException):
    """Lancada quando o usuario autenticado nao pode executar a operacao."""
    pass

class RecursoNaoEncontradoException(RegraNegocioException):
    """Lancada quando a demanda, etapa ou usuario referenciado nao existe."""
    pass

class ArquivoInvalidoException(RegraNegocioException):
    """Lancada quando o conteudo enviado nao corresponde a um formato aceito."""
    pass
