"""Bounded, standalone parser process. Never imports application credentials.

Invoked by absolute path with Python isolated mode. PDF actions/attachments are
not executed and images are decoded without rendering or launching programs.
"""
from __future__ import annotations

from io import BytesIO
import logging
import os
import sys
import warnings

MAX_INPUT = 10 * 1024 * 1024
MAX_MEMORY = 512 * 1024 * 1024
MAX_CPU_SECONDS = 5
MAX_PIXELS = 16_000_000
MAX_DIMENSION = 16_384
MAX_PAGES = 200
MAX_STREAM = 20 * 1024 * 1024
MAX_DECODED = 50 * 1024 * 1024
_windows_job = None


def _resource_limits() -> None:
    global _windows_job
    if os.name != "nt":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (MAX_MEMORY, MAX_MEMORY))
        resource.setrlimit(resource.RLIMIT_CPU, (MAX_CPU_SECONDS, MAX_CPU_SECONDS))
        return

    import ctypes
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
            ("flags", wintypes.DWORD), ("min_working_set", ctypes.c_size_t),
            ("max_working_set", ctypes.c_size_t), ("active_processes", wintypes.DWORD),
            ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD),
        ]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("basic", BasicLimits), ("io", ctypes.c_ulonglong * 6),
            ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
            ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    _windows_job = kernel.CreateJobObjectW(None, None)
    limits = ExtendedLimits()
    limits.basic.flags = 0x100 | 0x2  # PROCESS_MEMORY | PROCESS_TIME
    limits.basic.process_time = MAX_CPU_SECONDS * 10_000_000
    limits.process_memory = MAX_MEMORY
    if (
        not _windows_job
        or not kernel.SetInformationJobObject(_windows_job, 9, ctypes.byref(limits), ctypes.sizeof(limits))
        or not kernel.AssignProcessToJobObject(_windows_job, kernel.GetCurrentProcess())
    ):
        raise RuntimeError("Cannot enforce parser resource limits")


def _image(data: bytes, expected: str) -> None:
    from PIL import Image, ImageFile

    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    warnings.simplefilter("error", Image.DecompressionBombWarning)
    with Image.open(BytesIO(data), formats=[expected]) as image:
        width, height = image.size
        if (
            image.format != expected or width < 1 or height < 1
            or max(width, height) > MAX_DIMENSION or width * height > MAX_PIXELS
        ):
            raise ValueError("Image limits")
        image.verify()
    # verify() alone does not fully decode JPEG pixel data.
    with Image.open(BytesIO(data), formats=[expected]) as image:
        frames = getattr(image, "n_frames", 1)
        if frames > 10 or image.width * image.height * frames > MAX_PIXELS:
            raise ValueError("Image frame limit")
        for frame in range(frames):
            image.seek(frame)
            image.load()


def _pdf(data: bytes) -> None:
    from pypdf import PdfReader, apply_configuration
    from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, StreamObject

    with apply_configuration(
        maximum_declared_stream_length=MAX_STREAM,
        zlib_maximum_output_length=MAX_STREAM,
        lzw_maximum_output_length=MAX_STREAM,
        run_length_maximum_output_length=MAX_STREAM,
        array_based_stream_maximum_output_length=MAX_STREAM,
        stream_decoding_work_maximum_length=MAX_DECODED,
        stream_parsing_work_maximum_count=50_000,
        dictionary_maximum_element_count=10_000,
        array_maximum_element_count=10_000,
        page_tree_maximum_entries=MAX_PAGES * 2,
        page_tree_maximum_depth=32,
        jbig2dec_binary=None,
    ):
        reader = PdfReader(BytesIO(data), strict=True, root_object_recovery_limit=500)
        if reader.is_encrypted or reader.trailer["/Root"].get("/Type") != "/Catalog":
            raise ValueError("PDF catalog")
        if sum(len(entries) for entries in reader.xref.values()) + len(reader.xref_objStm) > 10_000:
            raise ValueError("PDF object limit")
        pages_root = reader.trailer["/Root"]["/Pages"]
        if pages_root.get("/Type") != "/Pages" or not 1 <= pages_root.get("/Count", 0) <= MAX_PAGES:
            raise ValueError("PDF page limit")
        pages = reader.pages
        if not 1 <= len(pages) <= MAX_PAGES or len(pages) != pages_root["/Count"]:
            raise ValueError("PDF page tree")
        operators = 0
        for page in pages:
            if page.get("/Type") != "/Page" or len(page.mediabox) != 4:
                raise ValueError("PDF page")
            parts = page.get("/Contents")
            if parts is not None:
                parts = parts.get_object()
                parts = parts if isinstance(parts, ArrayObject) else [parts]
                for part in parts:
                    part = part.get_object()
                    filters = part.get("/Filter", [])
                    filters = [filters] if isinstance(filters, str) else filters
                    if any(f not in {"/FlateDecode", "/ASCIIHexDecode", "/ASCII85Decode", "/LZWDecode", "/RunLengthDecode"} for f in filters):
                        raise ValueError("Unsupported page content filter")
            content = page.get_contents()
            if content is not None:
                operators += len(content.operations)
                if operators > 100_000:
                    raise ValueError("PDF content limit")

        # Resolve reachable references and check streams, with bounded work.
        # Encoded image streams remain opaque; no external image decoder is run.
        safe_filters = {"/FlateDecode", "/ASCIIHexDecode", "/ASCII85Decode", "/LZWDecode", "/RunLengthDecode"}
        opaque_filters = {"/DCTDecode", "/JPXDecode", "/JBIG2Decode", "/CCITTFaxDecode"}
        stack = [(reader.trailer, 0)]
        seen = set()
        nodes = decoded = 0
        while stack:
            value, depth = stack.pop()
            nodes += 1
            if nodes > 50_000 or depth > 64:
                raise ValueError("PDF graph limit")
            if isinstance(value, IndirectObject):
                identity = (value.idnum, value.generation)
                if identity in seen:
                    continue
                seen.add(identity)
                value = value.get_object()
            if isinstance(value, StreamObject):
                filters = value.get("/Filter", [])
                filters = [filters] if isinstance(filters, str) else filters
                if any(f not in safe_filters | opaque_filters for f in filters):
                    raise ValueError("Unsupported PDF filter")
                if all(f in safe_filters for f in filters):
                    decoded += len(value.get_data())
                    if decoded > MAX_DECODED:
                        raise ValueError("PDF stream budget")
            if isinstance(value, DictionaryObject):
                stack.extend((child, depth + 1) for child in value.values())
            elif isinstance(value, ArrayObject):
                stack.extend((child, depth + 1) for child in value)


def main() -> int:
    logging.disable(logging.CRITICAL)
    try:
        _resource_limits()
        data = sys.stdin.buffer.read(MAX_INPUT + 1)
        if not data or len(data) > MAX_INPUT:
            return 1
        kind = sys.argv[1]
        if kind == "PDF":
            _pdf(data)
        elif kind in {"PNG", "JPEG"}:
            _image(data, kind)
        else:
            return 1
    except Exception:
        return 1
    sys.stdout.buffer.write(b"ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
