import pytest

from app.core.exceptions import ArquivoInvalidoException
from app.domain.regras.arquivos import TAMANHO_MAXIMO_BYTES, validar_arquivo
from tests import amostras


@pytest.mark.parametrize("nome, conteudo, content_type", [
    ("tela.png", amostras.png(), "image/png"),
    ("foto.JPG", amostras.jpeg(), "image/jpeg"),
    ("foto.jpeg", amostras.jpeg(), "image/jpeg"),
    ("laudo.pdf", amostras.pdf(), "application/pdf"),
    ("relatorio.docx", amostras.docx(),
     "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
])
def test_formatos_aceitos_devolvem_tipo_detectado(nome, conteudo, content_type):
    arquivo = validar_arquivo(nome, conteudo)
    assert arquivo.content_type == content_type
    assert arquivo.extensao == nome.rsplit(".", 1)[1].lower()
    assert arquivo.tamanho_bytes == len(conteudo)


@pytest.mark.parametrize("nome", ["script.exe", "sem_extensao", "planilha.xlsx", "antigo.doc"])
def test_extensao_nao_permitida(nome):
    with pytest.raises(ArquivoInvalidoException, match="não permitida"):
        validar_arquivo(nome, amostras.pdf())


@pytest.mark.parametrize("nome, conteudo", [
    ("virus.png", b"MZ\x90\x00" + b"\x00" * 64),       # executavel renomeado
    ("foto.jpg", amostras.png()),                      # PNG declarado como JPEG
    ("laudo.pdf", b"<html><script>alert(1)</script>"),
    ("laudo.pdf", b"%PDF-1.4\nsem marcador de fim"),
    ("imagem.png", amostras.png()[:-12]),               # PNG truncado
    ("relatorio.docx", b"PK\x03\x04 nao e um zip"),
    ("relatorio.docx", amostras.docx()[:40]),
])
def test_conteudo_divergente_da_extensao(nome, conteudo):
    with pytest.raises(ArquivoInvalidoException, match="não corresponde"):
        validar_arquivo(nome, conteudo)


@pytest.mark.parametrize("acao", [b"/JavaScript", b"/JS", b"/Launch", b"/EmbeddedFile", b"/J#61vaScript"])
def test_pdf_com_conteudo_ativo_recusado(acao):
    with pytest.raises(ArquivoInvalidoException, match="conteúdo ativo"):
        validar_arquivo("laudo.pdf", amostras.pdf(b"3 0 obj << /S " + acao + b" >> endobj"))


def test_docx_com_macro_recusado():
    with pytest.raises(ArquivoInvalidoException, match="macros"):
        validar_arquivo("relatorio.docx", amostras.docx(com_macro=True))


def test_arquivo_vazio_e_acima_do_limite():
    with pytest.raises(ArquivoInvalidoException, match="vazio"):
        validar_arquivo("foto.png", b"")
    with pytest.raises(ArquivoInvalidoException, match="10 MB"):
        validar_arquivo("foto.png", amostras.png() + b"\x00" * TAMANHO_MAXIMO_BYTES)


@pytest.mark.parametrize("nome, esperado", [
    ("C:\\Users\\cliente\\tela.png", "tela.png"),
    ("../../etc/tela.png", "tela.png"),
    ("  tela.png  ", "tela.png"),
])
def test_nome_descarta_diretorios(nome, esperado):
    assert validar_arquivo(nome, amostras.png()).nome_arquivo == esperado


@pytest.mark.parametrize("nome", ["", "   ", ".png", "pasta/", "tela\x00.png", "a" * 252 + ".png"])
def test_nome_invalido(nome):
    with pytest.raises(ArquivoInvalidoException):
        validar_arquivo(nome, amostras.png())
