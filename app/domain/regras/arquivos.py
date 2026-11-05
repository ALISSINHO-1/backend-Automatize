"""Validacao do conteudo real de evidencias e anexos.

Extensao e content-type sao informados pelo cliente e nao bastam: o conteudo
precisa ter a assinatura binaria do formato declarado. Arquivos com conteudo
ativo (JavaScript/acoes em PDF, macros em DOCX) sao recusados.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

from app.core.exceptions import ArquivoInvalidoException


TAMANHO_MAXIMO_BYTES = 10 * 1024 * 1024  # 10 MB
TAMANHO_MAXIMO_NOME = 255

CONTENT_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
EXTENSOES_PERMITIDAS = frozenset(CONTENT_TYPES)

# Limites contra "zip bomb" no DOCX: o arquivo enviado e pequeno, mas o
# conteudo descompactado pode ser enorme.
_DOCX_MAX_ENTRADAS = 1000
_DOCX_MAX_DESCOMPACTADO = 100 * 1024 * 1024

_PDF_ACOES_PROIBIDAS = re.compile(rb"/(JavaScript|JS|Launch|EmbeddedFile|RichMedia|XFA)(?![A-Za-z0-9])")
_PDF_NOME_HEX = re.compile(rb"#([0-9A-Fa-f]{2})")


@dataclass(frozen=True)
class ArquivoValidado:
    nome_arquivo: str
    extensao: str
    content_type: str
    tamanho_bytes: int


def validar_arquivo(nome_arquivo: str, conteudo: bytes) -> ArquivoValidado:
    """Valida nome, extensao, tamanho e conteudo; devolve o content-type real."""
    nome = _normalizar_nome(nome_arquivo)
    extensao = PurePosixPath(nome).suffix.lstrip(".").lower()
    if extensao not in EXTENSOES_PERMITIDAS:
        permitidas = ", ".join(sorted(EXTENSOES_PERMITIDAS))
        raise ArquivoInvalidoException(f"Extensão de arquivo não permitida. Permitidas: {permitidas}.")

    if not conteudo:
        raise ArquivoInvalidoException("O arquivo está vazio.")
    if len(conteudo) > TAMANHO_MAXIMO_BYTES:
        limite_mb = TAMANHO_MAXIMO_BYTES // (1024 * 1024)
        raise ArquivoInvalidoException(f"O arquivo excede o limite de {limite_mb} MB.")

    _VALIDADORES[extensao](conteudo)
    return ArquivoValidado(
        nome_arquivo=nome,
        extensao=extensao,
        content_type=CONTENT_TYPES[extensao],
        tamanho_bytes=len(conteudo),
    )


def _normalizar_nome(nome_arquivo: str) -> str:
    # Descarta diretorios enviados pelo cliente (C:\..., ../../) e mantem so o nome.
    nome = PurePosixPath((nome_arquivo or "").replace("\\", "/")).name.strip()
    if not nome or nome.startswith("."):
        raise ArquivoInvalidoException("Nome de arquivo inválido.")
    if len(nome) > TAMANHO_MAXIMO_NOME:
        raise ArquivoInvalidoException(f"O nome do arquivo deve ter no máximo {TAMANHO_MAXIMO_NOME} caracteres.")
    if any(ord(caractere) < 32 for caractere in nome):
        raise ArquivoInvalidoException("Nome de arquivo inválido.")
    return nome


def _conteudo_divergente(formato: str) -> ArquivoInvalidoException:
    return ArquivoInvalidoException(
        f"O conteúdo do arquivo não corresponde a um {formato} válido."
    )


def _validar_png(conteudo: bytes) -> None:
    if (
        not conteudo.startswith(b"\x89PNG\r\n\x1a\n")
        or conteudo[12:16] != b"IHDR"
        or b"IEND" not in conteudo[-16:]
    ):
        raise _conteudo_divergente("PNG")


def _validar_jpeg(conteudo: bytes) -> None:
    if len(conteudo) < 4 or not conteudo.startswith(b"\xff\xd8\xff"):
        raise _conteudo_divergente("JPEG")


def _validar_pdf(conteudo: bytes) -> None:
    if not re.match(rb"%PDF-[12]\.\d", conteudo) or b"%%EOF" not in conteudo[-1024:]:
        raise _conteudo_divergente("PDF")

    # Nomes PDF aceitam escape hexadecimal (/J#61vaScript); normaliza antes de buscar.
    normalizado = _PDF_NOME_HEX.sub(lambda m: bytes([int(m.group(1), 16)]), conteudo)
    if _PDF_ACOES_PROIBIDAS.search(normalizado):
        raise ArquivoInvalidoException(
            "PDF com conteúdo ativo (JavaScript, ações ou arquivos embutidos) não é permitido."
        )


def _validar_docx(conteudo: bytes) -> None:
    if not conteudo.startswith(b"PK\x03\x04"):
        raise _conteudo_divergente("DOCX")
    try:
        with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
            entradas = pacote.infolist()
    except (zipfile.BadZipFile, ValueError):
        raise _conteudo_divergente("DOCX") from None

    nomes = {entrada.filename for entrada in entradas}
    if "[Content_Types].xml" not in nomes or "word/document.xml" not in nomes:
        raise _conteudo_divergente("DOCX")
    if any(nome.lower().endswith("vbaproject.bin") for nome in nomes):
        raise ArquivoInvalidoException("Documentos com macros não são permitidos.")
    if (
        len(entradas) > _DOCX_MAX_ENTRADAS
        or sum(entrada.file_size for entrada in entradas) > _DOCX_MAX_DESCOMPACTADO
    ):
        raise ArquivoInvalidoException("O documento excede o limite de conteúdo descompactado.")


_VALIDADORES = {
    "png": _validar_png,
    "jpg": _validar_jpeg,
    "jpeg": _validar_jpeg,
    "pdf": _validar_pdf,
    "docx": _validar_docx,
}
