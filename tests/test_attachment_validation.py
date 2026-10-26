from io import BytesIO
from zipfile import ZipFile

import pytest

from app.infrastructure.storage.file_validation import (
    ArquivoInvalidoError, TAMANHO_MAXIMO_BYTES, validar_arquivo,
)
from tests.attachment_samples import docx, jpeg, pdf, png, word_ole


@pytest.mark.parametrize("name,data,mime", [
    ("real.pdf", pdf(), "application/pdf"),
    ("real.PNG", png(), "image/png"),
    ("real.jpg", jpeg(), "image/jpeg"),
    ("real.jpeg", jpeg(), "image/jpeg"),
    ("real.docx", docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ("word.doc", word_ole(), "application/msword"),
], ids=lambda value: value if isinstance(value, str) else "content")
def test_valid_content_identifies_canonical_mime(name, data, mime):
    assert validar_arquivo(name, data) == ("." + name.rsplit(".", 1)[1].lower(), mime)


@pytest.mark.parametrize("name,data", [
    ("fake.pdf", b"<!DOCTYPE html><html><script>alert(1)</script></html>"),
    ("wrong.pdf", png()), ("wrong.png", pdf()), ("wrong.docx", pdf()),
    ("empty.pdf", b""), ("program.exe", pdf()),
    ("broken.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 512),
    ("fake.doc", b"<html>Word document</html>"),
    ("broken.pdf", b"%PDF-1.4\ntruncated"),
    ("broken.png", b"\x89PNG\r\n\x1a\n"),
    ("broken.jpg", b"\xff\xd8\xff"),
    ("fake.docx", b"PK\x03\x04broken"),
    ("excel.doc", word_ole("Workbook")),
], ids=lambda value: value if isinstance(value, str) else "content")
def test_invalid_content_is_rejected(name, data):
    with pytest.raises(ArquivoInvalidoError):
        validar_arquivo(name, data)


@pytest.mark.parametrize("name", [
    "../file.pdf", "..\\file.pdf", "/tmp/file.pdf", "C:\\file.pdf",
    "file.pdf:stream", "file\x00.pdf", "file\n.pdf", "file.pdf ", "x" * 256 + ".pdf",
])
def test_filename_traversal_and_unsafe_names_rejected(name):
    with pytest.raises(ArquivoInvalidoError):
        validar_arquivo(name, pdf())


def test_exact_size_limit_and_one_byte_above():
    base = pdf()
    # Valid padding precedes the objects; offsets/startxref are rebuilt.
    padding = TAMANHO_MAXIMO_BYTES - len(base)
    exact = pdf(padding)
    exact = pdf(padding - (len(exact) - TAMANHO_MAXIMO_BYTES))
    assert len(exact) == TAMANHO_MAXIMO_BYTES
    assert validar_arquivo("limit.pdf", exact)[1] == "application/pdf"
    with pytest.raises(ArquivoInvalidoError, match="10 MB"):
        validar_arquivo("limit.pdf", exact + b"\n")


def test_generic_zip_is_not_a_word_document():
    data = BytesIO()
    with ZipFile(data, "w") as archive:
        archive.writestr("payload.html", "<html>fake</html>")
    with pytest.raises(ArquivoInvalidoError):
        validar_arquivo("fake.docx", data.getvalue())


@pytest.mark.parametrize("extra", [
    {"../payload": b"x"}, {"word/vbaProject.bin": b"macro"},
    {"/outside": b"x"}, {"word\\payload": b"x"},
    {"huge": b"x" * (50 * 1024 * 1024 + 1)},
])
def test_unsafe_docx_container_is_rejected(extra):
    with pytest.raises(ArquivoInvalidoError):
        validar_arquivo("bad.docx", docx(extra))


@pytest.mark.parametrize("name,data", [
    ("forged.pdf", b"%PDF-1.4\n<html>not a PDF</html>\n%%EOF"),
    ("forged.jpg", b"\xff\xd8\xff<html>not a JPEG</html>\xff\xd9"),
    ("forged.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01<html>fake</html>\x00\x00\x00\x00IEND\xaeB`\x82"),
    ("truncated.pdf", pdf()[:-20]),
    ("truncated.png", png()[:-15]),
    ("truncated.jpg", jpeg()[:40] + b"\xff\xd9"),
    ("wrong.pdf", jpeg()), ("wrong.jpg", png()), ("wrong.png", jpeg()),
    ("corrupt.png", png()[:29] + b"\0\0\0\0" + png()[33:]),
], ids=lambda value: value if isinstance(value, str) else "content")
def test_structural_parser_rejects_forged_truncated_and_corrupt_files(name, data):
    with pytest.raises(ArquivoInvalidoError):
        validar_arquivo(name, data)


@pytest.mark.parametrize("name,data,mime", [
    ("real.pdf", pdf(), "image/png"), ("real.png", png(), "image/jpeg"),
    ("real.jpg", jpeg(), "text/html"),
], ids=lambda value: value if isinstance(value, str) else "content")
def test_specific_mime_incompatible_with_verified_format_is_rejected(name, data, mime):
    with pytest.raises(ArquivoInvalidoError, match="MIME"):
        validar_arquivo(name, data, mime)


def test_generic_upload_mime_uses_verified_format():
    assert validar_arquivo("real.jpg", jpeg(), "application/octet-stream") == (".jpg", "image/jpeg")


def test_pdf_page_budget_rejects_otherwise_valid_large_document():
    from pypdf import PdfWriter
    data = BytesIO()
    writer = PdfWriter()
    for _ in range(201):
        writer.add_blank_page(width=100, height=100)
    writer.write(data)
    with pytest.raises(ArquivoInvalidoError):
        validar_arquivo("many-pages.pdf", data.getvalue())


def test_pdf_decompression_budget_rejects_compressed_stream_bomb():
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject
    data = BytesIO()
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    stream = DecodedStreamObject()
    stream.set_data(b"q\n" * (11 * 1024 * 1024))
    page[NameObject("/Contents")] = writer._add_object(stream.flate_encode())
    writer.write(data)
    assert len(data.getvalue()) < 10 * 1024 * 1024
    with pytest.raises(ArquivoInvalidoError):
        validar_arquivo("compressed.pdf", data.getvalue())


def test_image_pixel_budget_rejects_tiny_compressed_large_image():
    from PIL import Image
    data = BytesIO()
    with Image.new("1", (4096, 4096)) as image:
        image.save(data, format="PNG")
    with pytest.raises(ArquivoInvalidoError):
        validar_arquivo("large.png", data.getvalue())


def test_parser_timeout_fails_closed_without_returning_parser_details(monkeypatch):
    from app.infrastructure.storage import file_validation
    monkeypatch.setattr(file_validation, "PARSER_TIMEOUT_SECONDS", 0.0001)
    with pytest.raises(ArquivoInvalidoError, match="Conteúdo incompatível"):
        validar_arquivo("real.pdf", pdf())
