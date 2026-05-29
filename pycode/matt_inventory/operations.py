"""Request-level operations for the Matt inventory value workflow."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .config import alert_workbook_path, price_meta_path, report_path, runtime_dir, stock_meta_path
from .engine import (
    build_matt_inventory_alert_workbook,
    build_matt_inventory_report,
    file_name_allowed,
    save_report_to_path,
    write_runtime_upload,
)
from .jobs import _matt_inventory_saved_price_payload, write_meta
from .page import render_matt_inventory_form


def process_matt_inventory_upload(files: dict[str, tuple[str, bytes]]) -> tuple[int, bytes]:
    price_file = files.get("price_file")
    stock_file = files.get("stock_file")

    if stock_file is None:
        return 400, render_matt_inventory_form("A napi k?szletf?jl felt?lt?se k?telez?.")

    stock_name, stock_bytes = stock_file
    if not file_name_allowed(stock_name):
        return 400, render_matt_inventory_form("A napi k?szletf?jl csak XLSX, XLSM vagy CSV lehet.")

    price_name = ""
    price_bytes: bytes | None = None
    if price_file is not None:
        price_name, price_bytes = price_file
        if not file_name_allowed(price_name):
            return 400, render_matt_inventory_form("A fix ?rt?bla csak XLSX, XLSM vagy CSV lehet.")
    else:
        saved_price_payload = _matt_inventory_saved_price_payload()
        if saved_price_payload is None:
            return 400, render_matt_inventory_form("Els? alkalommal a fix ?rt?bl?t is fel kell t?lteni.")
        price_name, price_bytes = saved_price_payload

    assert price_bytes is not None

    try:
        report = build_matt_inventory_report(
            price_name=price_name,
            price_bytes=price_bytes,
            stock_name=stock_name,
            stock_bytes=stock_bytes,
        )
        alert_workbook = build_matt_inventory_alert_workbook(
            price_name=price_name,
            price_bytes=price_bytes,
            stock_name=stock_name,
            stock_bytes=stock_bytes,
        )
    except Exception as exc:
        return 400, render_matt_inventory_form(f"A matt k?szlet?rt?k sz?mol?sa nem siker?lt: {exc}")

    runtime_dir().mkdir(parents=True, exist_ok=True)

    if price_file is not None:
        stored_price_path = write_runtime_upload(
            runtime_dir() / "latest-price",
            price_name,
            price_bytes,
        )
        write_meta(
            price_meta_path(),
            {
                "original_name": Path(price_name).name,
                "stored_name": stored_price_path.name,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            },
        )

    stored_stock_path = write_runtime_upload(
        runtime_dir() / "latest-stock",
        stock_name,
        stock_bytes,
    )
    write_meta(
        stock_meta_path(),
        {
            "original_name": Path(stock_name).name,
            "stored_name": stored_stock_path.name,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    save_report_to_path(report_path(), report)
    alert_workbook_path().write_bytes(alert_workbook)

    body = render_matt_inventory_form(
        message="A napi matt front k?szlet?rt?k elk?sz?lt.",
        success=True,
    )
    return 200, body


def matt_inventory_alert_download_payload() -> tuple[bytes, str, str] | None:
    path = alert_workbook_path()
    if not path.exists():
        return None
    return (
        path.read_bytes(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "matt-keszlet-kuszobriport.xlsx",
    )
