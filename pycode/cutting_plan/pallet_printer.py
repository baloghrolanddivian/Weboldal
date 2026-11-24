"""Send the verified pallet label directly to the Windows printer, once."""

import ctypes
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .pallet_print import render_page
from .store import _connect, validate_day


DEFAULT_PRINTER = "Kyocera ECOSYS P2040dn"


def _browser():
    for name in ("msedge", "chrome", "chromium", "google-chrome"):
        if found := shutil.which(name):
            return found
    for folder in (os.getenv("PROGRAMFILES(X86)"), os.getenv("PROGRAMFILES")):
        if folder:
            for relative in ("Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe"):
                path = Path(folder) / relative
                if path.is_file():
                    return str(path)
    raise RuntimeError("A címke nyomtatásához Edge vagy Chrome szükséges a szerveren.")


def _render_pdf(root, day, pallet_id, folder):
    path, pdf = folder / "label.html", folder / "label.pdf"
    label_format = os.getenv("CUTTING_PALLET_PRINT_FORMAT", "label")
    path.write_bytes(render_page(root, day, pallet_id, paper="a4", label_format=label_format))
    result = subprocess.run([_browser(), "--headless", "--disable-gpu", "--disable-background-networking",
        "--no-first-run", "--no-default-browser-check", f"--user-data-dir={folder / 'profile'}",
        "--virtual-time-budget=1500", "--no-pdf-header-footer", f"--print-to-pdf={pdf}", path.as_uri()],
        capture_output=True, timeout=45, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    if result.returncode or not pdf.is_file():
        raise RuntimeError("Nem sikerült előállítani a nyomtatható címkét.")
    return pdf


def _windows_device(printer):
    """Open the named printer's GDI device in A4 portrait, one-sided, 100%."""
    if os.name != "nt":
        raise RuntimeError("A közvetlen nyomtatáshoz Windows szerver szükséges.")
    from ctypes import wintypes as w

    class PrinterFields(ctypes.Structure):
        _fields_ = [(name, w.SHORT) for name in ("orientation", "paper_size", "paper_length", "paper_width", "scale", "copies", "source", "quality")]

    class DeviceMode(ctypes.Structure):
        _fields_ = [("device_name", w.WCHAR * 32), ("spec_version", w.WORD), ("driver_version", w.WORD),
            ("size", w.WORD), ("driver_extra", w.WORD), ("fields", w.DWORD), ("printer", PrinterFields),
            ("color", w.SHORT), ("duplex", w.SHORT), ("y_resolution", w.SHORT), ("tt_option", w.SHORT),
            ("collate", w.SHORT), ("form_name", w.WCHAR * 32), ("log_pixels", w.WORD),
            *[(name, w.DWORD) for name in ("bits", "width", "height", "display_flags", "frequency", "icm_method", "icm_intent", "media_type", "dither_type", "reserved1", "reserved2", "panning_width", "panning_height")]]

    spool = ctypes.WinDLL("winspool.drv", use_last_error=True)
    gdi = ctypes.WinDLL("gdi32", use_last_error=True)
    spool.OpenPrinterW.argtypes = [w.LPWSTR, ctypes.POINTER(w.HANDLE), ctypes.c_void_p]
    spool.OpenPrinterW.restype = w.BOOL
    spool.ClosePrinter.argtypes = [w.HANDLE]
    spool.DocumentPropertiesW.argtypes = [w.HWND, w.HANDLE, w.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, w.DWORD]
    spool.DocumentPropertiesW.restype = w.LONG
    gdi.CreateDCW.argtypes = [w.LPCWSTR, w.LPCWSTR, w.LPCWSTR, ctypes.c_void_p]
    gdi.CreateDCW.restype = w.HDC
    gdi.DeleteDC.argtypes = [w.HDC]
    gdi.GetDeviceCaps.argtypes = [w.HDC, ctypes.c_int]
    gdi.GetDeviceCaps.restype = ctypes.c_int
    handle = w.HANDLE()
    if not spool.OpenPrinterW(printer, ctypes.byref(handle), None):
        raise RuntimeError(f"A(z) {printer} nyomtató nem érhető el.")
    try:
        size = spool.DocumentPropertiesW(None, handle, printer, None, None, 0)
        if size < ctypes.sizeof(DeviceMode):
            raise RuntimeError("Nem sikerült lekérni a nyomtató papírbeállításait.")
        buffer = ctypes.create_string_buffer(size)
        if spool.DocumentPropertiesW(None, handle, printer, buffer, None, 2) < 0:
            raise RuntimeError("Nem sikerült lekérni a nyomtató beállításait.")
        mode = ctypes.cast(buffer, ctypes.POINTER(DeviceMode)).contents
        mode.fields |= 0x1 | 0x2 | 0x10 | 0x100 | 0x1000
        mode.fields &= ~(0x4 | 0x8 | 0x10000)  # Driver's custom paper dimensions/form name must not override A4.
        mode.printer.orientation, mode.printer.paper_size = 1, 9
        mode.printer.scale, mode.printer.copies, mode.duplex = 100, 1, 1
        if spool.DocumentPropertiesW(None, handle, printer, buffer, buffer, 10) < 0:
            raise RuntimeError("A nyomtató nem fogadta el az A4-es beállítást.")
        dc = gdi.CreateDCW("WINSPOOL", printer, None, buffer)
        if not dc:
            raise RuntimeError("Nem sikerült megnyitni a nyomtatót.")
        return gdi, dc
    finally:
        spool.ClosePrinter(handle)


def _spool_pdf(pdf, printer, title):
    import fitz
    from ctypes import wintypes as w

    class DocInfo(ctypes.Structure):
        _fields_ = [("size", ctypes.c_int), ("name", w.LPCWSTR), ("output", w.LPCWSTR), ("datatype", w.LPCWSTR), ("flags", w.DWORD)]

    class BitmapInfo(ctypes.Structure):
        _fields_ = [("size", w.DWORD), ("width", w.LONG), ("height", w.LONG), ("planes", w.WORD),
            ("bits", w.WORD), ("compression", w.DWORD), ("image_size", w.DWORD), ("x_resolution", w.LONG),
            ("y_resolution", w.LONG), ("colors", w.DWORD), ("important_colors", w.DWORD)]

    gdi, dc = _windows_device(printer)
    gdi.StartDocW.argtypes = [w.HDC, ctypes.POINTER(DocInfo)]
    gdi.StartDocW.restype = ctypes.c_int
    for name in ("StartPage", "EndPage", "EndDoc", "AbortDoc"):
        getattr(gdi, name).argtypes = [w.HDC]
        getattr(gdi, name).restype = ctypes.c_int
    gdi.StretchDIBits.argtypes = [w.HDC, *([ctypes.c_int] * 8), ctypes.c_void_p, ctypes.POINTER(BitmapInfo), w.UINT, w.DWORD]
    gdi.StretchDIBits.restype = ctypes.c_int
    started = False
    try:
        info = DocInfo(ctypes.sizeof(DocInfo), title, None, None, 0)
        job_id = gdi.StartDocW(dc, ctypes.byref(info))
        if job_id <= 0:
            raise RuntimeError("A nyomtató nem fogadta a nyomtatási feladatot.")
        started = True
        with fitz.open(pdf) as document:
            for page in document:
                if gdi.StartPage(dc) <= 0:
                    raise RuntimeError("Nem sikerült elkezdeni a nyomtatási oldalt.")
                pixmap = page.get_pixmap(dpi=300, colorspace=fitz.csRGB, alpha=False)
                rgb = pixmap.samples
                pixels = bytearray(pixmap.width * pixmap.height * 4)
                pixels[0::4], pixels[1::4], pixels[2::4] = rgb[2::3], rgb[1::3], rgb[0::3]
                bitmap = BitmapInfo(ctypes.sizeof(BitmapInfo), pixmap.width, -pixmap.height, 1, 32, 0, len(pixels), 0, 0, 0, 0)
                data = (ctypes.c_ubyte * len(pixels)).from_buffer(pixels)
                dpi_x, dpi_y = gdi.GetDeviceCaps(dc, 88), gdi.GetDeviceCaps(dc, 90)
                result = gdi.StretchDIBits(dc, -gdi.GetDeviceCaps(dc, 112), -gdi.GetDeviceCaps(dc, 113),
                    round(page.rect.width * dpi_x / 72), round(page.rect.height * dpi_y / 72),
                    0, 0, pixmap.width, pixmap.height, data, ctypes.byref(bitmap), 0, 0x00CC0020)
                if result <= 0 or gdi.EndPage(dc) <= 0:
                    raise RuntimeError("A címke nyomtatása megszakadt.")
        if gdi.EndDoc(dc) <= 0:
            raise RuntimeError("Nem sikerült átadni a címkét a nyomtatónak.")
        started = False
        return job_id
    finally:
        if started:
            gdi.AbortDoc(dc)
        gdi.DeleteDC(dc)


def print_pallet(root, day, pallet_id, retry=False):
    validate_day(day)
    printer = os.getenv("CUTTING_PALLET_PRINTER", DEFAULT_PRINTER)
    now = datetime.now(timezone.utc).isoformat()
    with _connect(root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        pallet = conn.execute("SELECT * FROM pallets WHERE id=? AND day=?", (pallet_id, day)).fetchone()
        if pallet is None or pallet["status"] != "ready":
            raise ValueError("Csak lezárt raklap nyomtatható automatikusan.")
        revision = pallet["revision"]
        previous = conn.execute("SELECT * FROM pallet_print_jobs WHERE pallet_id=? AND pallet_revision=?", (pallet_id, revision)).fetchone()
        if previous and (previous["status"] != "error" or not retry):
            return {"ok": previous["status"] == "sent", "status": previous["status"], "job_id": previous["job_id"], "error": previous["error"], "printer": printer}
        conn.execute("INSERT INTO pallet_print_jobs VALUES (?,?,'printing',NULL,'',?) ON CONFLICT(pallet_id,pallet_revision) DO UPDATE SET status='printing',error='',updated_at=excluded.updated_at", (pallet_id, revision, now))
        title = f'Divian-HUB - {pallet["name"]}'
    try:
        with tempfile.TemporaryDirectory(prefix="divian-pallet-print-", ignore_cleanup_errors=True) as folder:
            pdf = _render_pdf(root, day, pallet_id, Path(folder))
            job_id = _spool_pdf(pdf, printer, title)
        status, error = "sent", ""
    except Exception as exc:
        job_id, status, error = None, "error", str(exc) or "A nyomtatás nem sikerült."
    with _connect(root) as conn:
        conn.execute("UPDATE pallet_print_jobs SET status=?,job_id=?,error=?,updated_at=? WHERE pallet_id=? AND pallet_revision=?",
            (status, job_id, error, datetime.now(timezone.utc).isoformat(), pallet_id, revision))
    return {"ok": status == "sent", "status": status, "job_id": job_id, "error": error, "printer": printer}
