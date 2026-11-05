"""Content identification for the attachment formats supported by Automatize.

No client MIME is trusted and no archive is extracted. Identification is not
antivirus scanning or a guarantee that an otherwise valid document is harmless.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path, PurePosixPath
import os
import re
import subprocess
import sys
import zlib
from xml.etree import ElementTree
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile

import olefile


class ArquivoInvalidoError(ValueError):
    pass


MIME_POR_EXTENSAO = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
TAMANHO_MAXIMO_BYTES = 10 * 1024 * 1024
_MAX_XML_BYTES = 2 * 1024 * 1024
PARSER_TIMEOUT_SECONDS = 8


def _documento_valido(conteudo: bytes, formato: str) -> bool:
    # Pass bytes over stdin, not a filename or command assembled from input.
    # The worker has no application secrets in its environment and never
    # imports Settings, opens a database connection or executes PDF actions.
    environment = {key: value for key, value in os.environ.items() if key.upper() in {
        "SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "LANG", "LC_ALL",
    }}
    try:
        result = subprocess.run(
            [sys.executable, "-I", str(Path(__file__).with_name("_document_worker.py")), formato],
            input=conteudo, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=PARSER_TIMEOUT_SECONDS, env=environment,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and result.stdout == b"ok"


def extensao_segura(nome_arquivo: str) -> str:
    if (
        not nome_arquivo or len(nome_arquivo) > 255
        or nome_arquivo != nome_arquivo.strip()
        or any(c in nome_arquivo for c in '/\\:')
        or any(ord(c) < 32 or ord(c) == 127 for c in nome_arquivo)
    ):
        raise ArquivoInvalidoError("Nome de arquivo inválido.")
    extensao = PurePosixPath(nome_arquivo).suffix.lower()
    if extensao not in MIME_POR_EXTENSAO:
        raise ArquivoInvalidoError(f"Extensão '{extensao}' não permitida.")
    return extensao


def _xml(arquivo: ZipFile, nome: str) -> ElementTree.Element:
    with arquivo.open(nome) as stream:
        data = stream.read(_MAX_XML_BYTES + 1)
    if len(data) > _MAX_XML_BYTES or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("XML não permitido")
    # OOXML XML is UTF-8. Reject UTF-16/32 as well to avoid bypassing the
    # declaration checks through null-interleaved bytes.
    if b"\x00" in data:
        raise ValueError("XML não permitido")
    return ElementTree.fromstring(data)


def _docx_valido(conteudo: bytes) -> bool:
    if not conteudo.startswith(b"PK\x03\x04"):
        return False
    with ZipFile(BytesIO(conteudo)) as arquivo:
        entries = arquivo.infolist()
        nomes = {entry.filename for entry in entries}
        if len(entries) > 2048 or len(nomes) != len(entries):
            return False
        if sum(entry.file_size for entry in entries) > 50 * 1024 * 1024:
            return False
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if (
                path.is_absolute() or ".." in path.parts
                or entry.orig_filename != entry.filename
                or "\\" in entry.filename or ":" in entry.filename
                or entry.flag_bits & 1
                or entry.compress_type not in {ZIP_STORED, ZIP_DEFLATED}
                or entry.filename.lower().endswith("vbaproject.bin")
            ):
                return False
        if not {"[Content_Types].xml", "_rels/.rels", "word/document.xml"} <= nomes:
            return False
        tipos = _xml(arquivo, "[Content_Types].xml")
        ns_tipos = "{http://schemas.openxmlformats.org/package/2006/content-types}"
        tipo_word = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
        if tipos.tag != ns_tipos + "Types" or not any(
            item.get("PartName") == "/word/document.xml" and item.get("ContentType") == tipo_word
            for item in tipos.findall(ns_tipos + "Override")
        ):
            return False
        rels = _xml(arquivo, "_rels/.rels")
        ns_rels = "{http://schemas.openxmlformats.org/package/2006/relationships}"
        if rels.tag != ns_rels + "Relationships" or not any(
            item.get("Type") in {
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
                "http://purl.oclc.org/ooxml/officeDocument/relationships/officeDocument",
            }
            and item.get("Target") in {"word/document.xml", "/word/document.xml"}
            and item.get("TargetMode", "Internal") == "Internal"
            for item in rels.findall(ns_rels + "Relationship")
        ):
            return False
        documento = _xml(arquivo, "word/document.xml")
        return documento.tag in {
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}document",
            "{http://purl.oclc.org/ooxml/wordprocessingml/main}document",
        }


def _doc_valido(conteudo: bytes) -> bool:
    if not conteudo.startswith(olefile.MAGIC):
        return False
    with olefile.OleFileIO(BytesIO(conteudo), raise_defects=olefile.DEFECT_INCORRECT) as arquivo:
        if not arquivo.exists("WordDocument"):
            return False
        fib = arquivo.openstream("WordDocument").read(32)
        if len(fib) != 32 or fib[:2] != b"\xec\xa5":
            return False
        flags = int.from_bytes(fib[10:12], "little")
        tabela = "1Table" if flags & 0x200 else "0Table"
        return not flags & 0x100 and arquivo.exists(tabela)


def validar_arquivo(nome_arquivo: str, conteudo: bytes, content_type: str | None = None) -> tuple[str, str]:
    extensao = extensao_segura(nome_arquivo)
    if not conteudo:
        raise ArquivoInvalidoError("O arquivo está vazio.")
    if len(conteudo) > TAMANHO_MAXIMO_BYTES:
        raise ArquivoInvalidoError("O arquivo excede o limite de 10 MB.")
    # A supplied specific MIME must match; generic upload MIME remains valid.
    # This is only a consistency check, never evidence of the actual format.
    mime = content_type.split(";", 1)[0].strip().lower() if content_type else None
    if mime not in {None, "application/octet-stream", MIME_POR_EXTENSAO[extensao]}:
        raise ArquivoInvalidoError("MIME informado incompatível com o arquivo.")
    try:
        if extensao == ".pdf":
            valido = (
                bool(re.match(rb"%PDF-[12]\.\d[\r\n]", conteudo))
                and conteudo.rstrip().endswith(b"%%EOF")
                and _documento_valido(conteudo, "PDF")
            )
        elif extensao == ".png":
            valido = (
                conteudo.startswith(b"\x89PNG\r\n\x1a\n")
                and _documento_valido(conteudo, "PNG")
            )
        elif extensao in {".jpg", ".jpeg"}:
            valido = (
                conteudo.startswith(b"\xff\xd8\xff") and conteudo.endswith(b"\xff\xd9")
                and _documento_valido(conteudo, "JPEG")
            )
        elif extensao == ".doc":
            valido = _doc_valido(conteudo)
        else:
            valido = _docx_valido(conteudo)
    except (OSError, EOFError, ValueError, KeyError, RuntimeError, BadZipFile, ElementTree.ParseError, zlib.error):
        valido = False
    if not valido:
        raise ArquivoInvalidoError("Conteúdo incompatível com a extensão ou arquivo inválido.")
    return extensao, MIME_POR_EXTENSAO[extensao]
