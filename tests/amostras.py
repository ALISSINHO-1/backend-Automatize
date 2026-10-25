"""Arquivos mínimos válidos de cada formato aceito, para os testes."""
import io
import struct
import zipfile
import zlib


def png() -> bytes:
    def chunk(tipo: bytes, dados: bytes) -> bytes:
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados))

    cabecalho = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", cabecalho)
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
        + chunk(b"IEND", b"")
    )


def jpeg() -> bytes:
    return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"


def pdf(corpo: bytes = b"") -> bytes:
    return (
        b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [] /Count 0 >> endobj\n"
        + corpo
        + b"\ntrailer << /Root 1 0 R >>\n%%EOF\n"
    )


def docx(*, com_macro: bool = False) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as pacote:
        pacote.writestr("[Content_Types].xml", "<Types/>")
        pacote.writestr("word/document.xml", "<document/>")
        if com_macro:
            pacote.writestr("word/vbaProject.bin", b"\x00" * 16)
    return buffer.getvalue()
