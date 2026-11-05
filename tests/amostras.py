"""Arquivos mínimos válidos de cada formato aceito, para os testes."""
import io
import struct
import zlib

from tests import attachment_samples


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
    return attachment_samples.jpeg()


def pdf(corpo: bytes = b"") -> bytes:
    if not corpo:
        return attachment_samples.pdf()
    # A valid stream carries the raw PDF tokens used by the active-content
    # rejection tests, without breaking object offsets or the xref table.
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject
    buffer = io.BytesIO()
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    stream = DecodedStreamObject()
    stream.set_data(corpo)
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(buffer)
    return buffer.getvalue()


def docx(*, com_macro: bool = False) -> bytes:
    extra = {"word/vbaProject.bin": b"\x00" * 16} if com_macro else None
    return attachment_samples.docx(extra)
