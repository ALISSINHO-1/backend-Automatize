"""Small real-format documents generated locally; no external service needed."""
from io import BytesIO
import struct
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
import zlib


def pdf(padding_bytes: int = 0) -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] >>",
    ]
    data = b"%PDF-1.4\n"
    if padding_bytes:
        data += b"%" + b"x" * (padding_bytes - 2) + b"\n"
    offsets = []
    for number, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += str(number).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
    start = len(data)
    data += b"xref\n0 4\n0000000000 65535 f \n"
    data += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    return data + f"trailer\n<< /Root 1 0 R /Size 4 >>\nstartxref\n{start}\n%%EOF\n".encode()


def png() -> bytes:
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b"")
    )


def jpeg() -> bytes:
    from PIL import Image
    data = BytesIO()
    with Image.new("RGB", (2, 2), "red") as image:
        image.save(data, format="JPEG")
    return data.getvalue()


def docx(extra: dict[str, bytes] | None = None) -> bytes:
    data = BytesIO()
    with ZipFile(data, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", (
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>'
        ))
        archive.writestr("_rels/.rels", (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="word/document.xml" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"/>'
            '</Relationships>'
        ))
        archive.writestr("word/document.xml", (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>Evidência</w:t></w:r></w:p></w:body></w:document>'
        ))
        for name, value in (extra or {}).items():
            info = ZipInfo(name)
            info.filename = name  # Preserve adversarial backslashes on Windows.
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, value)
    return data.getvalue()


def word_ole(stream_name: str = "WordDocument") -> bytes:
    """Minimal CFB fixture with Word FIB and table streams; not a rendered doc."""
    free, end, fat_sector = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD
    header = bytearray(512)
    header[:8] = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    struct.pack_into("<HHHHH", header, 24, 0x3E, 3, 0xFFFE, 9, 6)
    struct.pack_into("<9I", header, 40, 0, 1, 0, 0, 4096, end, 0, end, 0)
    struct.pack_into("<109I", header, 76, 17, *([free] * 108))

    def directory_entry(name, kind, start, size, child=free, right=free):
        entry = bytearray(128)
        name_bytes = (name + "\x00").encode("utf-16-le")
        entry[:len(name_bytes)] = name_bytes
        struct.pack_into("<HBBIII", entry, 64, len(name_bytes), kind, 1, free, right, child)
        struct.pack_into("<IQ", entry, 116, start, size)
        return entry

    directory = (
        directory_entry("Root Entry", 5, end, 0, child=1)
        + directory_entry(stream_name, 2, 1, 4096, right=2)
        + directory_entry("0Table", 2, 9, 4096) + bytes(128)
    )
    word = bytearray(4096)
    struct.pack_into("<HH", word, 0, 0xA5EC, 0x00C1)
    fat = [end] + list(range(2, 9)) + [end] + list(range(10, 17)) + [end, fat_sector]
    fat += [free] * (128 - len(fat))
    return bytes(header + directory + word + bytes(4096) + struct.pack("<128I", *fat))
