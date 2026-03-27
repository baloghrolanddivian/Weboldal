from __future__ import annotations

import html
import hashlib
import io
import json
import mimetypes
import os
import sqlite3
import re
import subprocess
import sys
import time
import threading
import unicodedata
import urllib.parse
import urllib.request
import urllib.error
import uuid
import zipfile
import zlib
import csv
import calendar as month_calendar
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    import winreg
except Exception:  # pragma: no cover - Windows-only optional import
    winreg = None

from nettfront_module import (
    build_compare_artifacts,
    build_procurement_artifacts,
    create_bundle_archive,
    load_alkatresz_map,
    load_alkatresz_map_from_bytes,
)
from nettfront_order_module import (
    NettfrontOrderRow,
    build_order_suggestions,
    calc_total_m2_from_rows,
    rows_to_approved_workbook,
    rows_to_suggestion_workbook,
)
from manufacturing_module import (
    available_production_entries,
    available_production_numbers,
    latest_production_number,
    load_production_bundle,
    load_selection_state,
    production_folder as manufacturing_production_folder,
    save_selection_state,
)
from manufacturing_view import render_manufacturing_page
from procurement_helper import (
    get_procurement_helper_state,
    launch_procurement_helper,
    stop_procurement_helper,
)

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency handling
    OpenAI = None

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - optional dependency handling
    PdfReader = None

try:
    from openpyxl import load_workbook
except Exception:  # pragma: no cover - optional dependency handling
    load_workbook = None


HOST = "0.0.0.0"
PORT = int(os.getenv("DIVIAN_HUB_PORT", "5000"))
NO_DATA = "Nincs adat"
BASE_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = BASE_DIR / "runtime"
DEV_RELOAD_ROUTE = "/__dev__/events"
DEV_CHILD_ENV = "DIVIAN_HUB_DEV_CHILD"
DEV_RELOAD_TOKEN_ENV = "DIVIAN_HUB_RELOAD_TOKEN"
DEV_RELOAD_ENABLED = os.getenv("DIVIAN_HUB_DEV_RELOAD", "1") != "0"
DEV_WATCH_INTERVAL_SECONDS = 0.75
DEV_EVENT_HEARTBEAT_SECONDS = 10
WATCHED_EXTENSIONS = {".py", ".html", ".css", ".js", ".json", ".xlsx", ".xlsm", ".csv"}
WATCHED_FILES = {"requirements.txt"}
WATCH_IGNORED_DIRS = {".git", "__pycache__", "runtime", ".venv", "venv", "node_modules"}
APP_ROUTE = "/apps/szamla-magyarito"
GENERATE_ROUTE = f"{APP_ROUTE}/generate"
NETTFRONT_ROUTE = "/apps/nettfront-olvaso"
NETTFRONT_PROCESS_ROUTE = f"{NETTFRONT_ROUTE}/process"
NETTFRONT_DOWNLOAD_PREFIX = f"{NETTFRONT_ROUTE}/download"
NETTFRONT_LAUNCH_PREFIX = f"{NETTFRONT_ROUTE}/launch"
NETTFRONT_PROCUREMENT_ROUTE = "/apps/nettfront-beszerzes"
NETTFRONT_PROCUREMENT_PROCESS_ROUTE = f"{NETTFRONT_PROCUREMENT_ROUTE}/process"
NETTFRONT_PROCUREMENT_DOWNLOAD_PREFIX = f"{NETTFRONT_PROCUREMENT_ROUTE}/download"
NETTFRONT_PROCUREMENT_LAUNCH_PREFIX = f"{NETTFRONT_PROCUREMENT_ROUTE}/launch"
NETTFRONT_PROCUREMENT_STOP_PREFIX = f"{NETTFRONT_PROCUREMENT_ROUTE}/stop"
NETTFRONT_PROCUREMENT_PARTS_PREFIX = f"{NETTFRONT_PROCUREMENT_ROUTE}/alkatreszlista"
NETTFRONT_COMPARE_ROUTE = "/apps/nettfront-ellenorzes"
NETTFRONT_COMPARE_PROCESS_ROUTE = f"{NETTFRONT_COMPARE_ROUTE}/process"
NETTFRONT_COMPARE_DOWNLOAD_PREFIX = f"{NETTFRONT_COMPARE_ROUTE}/download"
NETTFRONT_ORDER_ROUTE = "/apps/nettfront-rendeles"
NETTFRONT_ORDER_PROCESS_ROUTE = f"{NETTFRONT_ORDER_ROUTE}/process"
NETTFRONT_ORDER_APPROVE_PREFIX = f"{NETTFRONT_ORDER_ROUTE}/approve"
NETTFRONT_ORDER_DOWNLOAD_PREFIX = f"{NETTFRONT_ORDER_ROUTE}/download"
NETTFRONT_ORDER_LAUNCH_PREFIX = f"{NETTFRONT_ORDER_ROUTE}/launch"
NETTFRONT_ORDER_STOP_PREFIX = f"{NETTFRONT_ORDER_ROUTE}/stop"
VACATION_CALENDAR_ROUTE = "/apps/szabadsag-naptar"
VACATION_CALENDAR_DEPARTMENT_SAVE_ROUTE = f"{VACATION_CALENDAR_ROUTE}/reszlegek/mentes"
VACATION_CALENDAR_DEPARTMENT_DELETE_ROUTE = f"{VACATION_CALENDAR_ROUTE}/reszlegek/torles"
VACATION_CALENDAR_EMPLOYEE_SAVE_ROUTE = f"{VACATION_CALENDAR_ROUTE}/kollegak/mentes"
VACATION_CALENDAR_EMPLOYEE_DELETE_ROUTE = f"{VACATION_CALENDAR_ROUTE}/kollegak/torles"
VACATION_CALENDAR_LEAVE_SAVE_ROUTE = f"{VACATION_CALENDAR_ROUTE}/szabadsagok/mentes"
VACATION_CALENDAR_LEAVE_DELETE_ROUTE = f"{VACATION_CALENDAR_ROUTE}/szabadsagok/torles"
MANUFACTURING_ROUTE = "/apps/gyartasi-papirok"
MANUFACTURING_STATE_ROUTE = f"{MANUFACTURING_ROUTE}/state"
DIVIAN_AI_KNOWLEDGE_ROUTE = "/apps/ai-tudasbazis"
DIVIAN_AI_KNOWLEDGE_PROCESS_ROUTE = f"{DIVIAN_AI_KNOWLEDGE_ROUTE}/upload"
DIVIAN_AI_KNOWLEDGE_FILE_PREFIX = f"{DIVIAN_AI_KNOWLEDGE_ROUTE}/file"
DIVIAN_AI_KNOWLEDGE_DELETE_PREFIX = f"{DIVIAN_AI_KNOWLEDGE_ROUTE}/delete"
DIVIAN_AI_STATUS_ROUTE = "/api/divian-ai/status"
DIVIAN_AI_CHAT_ROUTE = "/api/divian-ai/chat"
DIVIAN_AI_PROVIDER = os.getenv("DIVIAN_AI_PROVIDER", "").strip().lower()
DIVIAN_AI_MODEL = os.getenv("DIVIAN_AI_MODEL", "gpt-4.1-mini")
DIVIAN_AI_GEMINI_MODEL = os.getenv("DIVIAN_AI_GEMINI_MODEL", "gemini-2.5-flash-lite")
DIVIAN_AI_GROQ_MODEL = os.getenv("DIVIAN_AI_GROQ_MODEL", "llama-3.1-8b-instant")
DIVIAN_AI_REMOTE_ENABLED = os.getenv("DIVIAN_AI_REMOTE_ENABLED", "1") != "0"
DIVIAN_AI_KNOWLEDGE_ENV = "DIVIAN_AI_KNOWLEDGE_PDFS"
DIVIAN_AI_KNOWLEDGE_DIR = BASE_DIR / "data" / "divian-ai"
DIVIAN_AI_UPLOAD_DIR = DIVIAN_AI_KNOWLEDGE_DIR / "uploads"
DIVIAN_AI_RUNTIME_DIR = RUNTIME_DIR / "divian-ai"
DIVIAN_AI_UPLOAD_MANIFEST = DIVIAN_AI_RUNTIME_DIR / "uploads.json"
DIVIAN_AI_DB = DIVIAN_AI_RUNTIME_DIR / "knowledge.db"
DIVIAN_AI_RESPONSE_CACHE = DIVIAN_AI_RUNTIME_DIR / "response-cache.json"
DIVIAN_AI_PUBLIC_WEB_DIR = DIVIAN_AI_RUNTIME_DIR / "public-web"
DIVIAN_AI_PUBLIC_WEB_SOURCE_MANIFEST = DIVIAN_AI_PUBLIC_WEB_DIR / "_sources.json"
DIVIAN_AI_INDEXER_VERSION = 6
DIVIAN_AI_PUBLIC_WEB_VERSION = 6
DIVIAN_AI_PUBLIC_WEB_REFRESH_SECONDS = 30 * 24 * 60 * 60
DIVIAN_AI_PUBLIC_WEB_DISCOVERY_SECONDS = 30 * 24 * 60 * 60
DIVIAN_AI_PARTNER_PUBLIC_MAX_PAGES = 240
DIVIAN_AI_OPENAI_RETRY_SECONDS = 60
DIVIAN_AI_RESPONSE_CACHE_LIMIT = 160
DIVIAN_AI_MEMORY_CACHE_SECONDS = 5 * 60
DIVIAN_AI_PUBLIC_WEB_SOURCES = (
    {
        "slug": "divian-rolunk",
        "name": "Divian hivatalos - Rólunk",
        "url": "https://divian.hu/rolunk",
    },
    {
        "slug": "divian-adatkezeles",
        "name": "Divian hivatalos - Adatkezelés",
        "url": "https://divian.hu/adatkezeles",
    },
    {
        "slug": "divian-aszf",
        "name": "Divian hivatalos - ÁSZF",
        "url": "https://www.divian.hu/aszf",
    },
    {
        "slug": "divian-gyik",
        "name": "Divian hivatalos - GYIK",
        "url": "https://www.divian.hu/gyik",
    },
    {
        "slug": "divian-partner-fooldal",
        "name": "Divian partner - Főoldal",
        "url": "https://partner.divian.hu/",
    },
    {
        "slug": "divian-partner-akciok",
        "name": "Divian partner - Akciók",
        "url": "https://partner.divian.hu/akcios-termekek",
    },
    {
        "slug": "divian-partner-uj-termekek",
        "name": "Divian partner - Új termékek",
        "url": "https://partner.divian.hu/uj-termekek",
    },
    {
        "slug": "divian-partner-aszf",
        "name": "Divian partner - ÁSZF",
        "url": "https://partner.divian.hu/aszf",
    },
)
DIVIAN_AI_OCR_SCRIPT = BASE_DIR / "tools" / "windows_ocr.ps1"
VACATION_CALENDAR_RUNTIME_DIR = RUNTIME_DIR / "szabadsag-naptar"
VACATION_CALENDAR_DB = VACATION_CALENDAR_RUNTIME_DIR / "calendar.db"
MANUFACTURING_RUNTIME_DIR = RUNTIME_DIR / "gyartasi-papirok"
DIVIAN_AI_DEFAULT_KNOWLEDGE_FILES = [
    Path.home() / "Downloads" / "ceges_termekinformacios_kezikonyv.pdf",
]
DIVIAN_AI_CURATED_DOCUMENT_HINTS = (
    "katalogus",
    "katalógus",
    "kezikonyv",
    "kézikönyv",
    "elemjegyzek",
    "elemjegyzék",
)
DIVIAN_AI_MAX_QUESTION_CHARS = 1000
DIVIAN_AI_MAX_HISTORY_MESSAGES = 8
DIVIAN_AI_MAX_CONTEXT_CHARS = 12000
DIVIAN_AI_CHUNK_CHARS = 1400
DIVIAN_AI_CHUNK_OVERLAP = 220
DIVIAN_AI_MAX_TABLE_ROWS = 1200
DIVIAN_AI_TEXT_FILE_EXTENSIONS = {".txt", ".md", ".json"}
DIVIAN_AI_SPREADSHEET_EXTENSIONS = {".xlsx", ".xlsm", ".csv"}
DIVIAN_AI_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
DIVIAN_AI_WORD_EXTENSIONS = {".docx"}
DIVIAN_AI_SUPPORTED_EXTENSIONS = (
    {".pdf"}
    | DIVIAN_AI_TEXT_FILE_EXTENSIONS
    | DIVIAN_AI_SPREADSHEET_EXTENSIONS
    | DIVIAN_AI_IMAGE_EXTENSIONS
    | DIVIAN_AI_WORD_EXTENSIONS
)
DIVIAN_AI_TOKEN_SUFFIXES = (
    "jaink",
    "jeink",
    "aink",
    "eink",
    "unk",
    "ünk",
    "ink",
    "ok",
    "ek",
    "ak",
    "eket",
    "okat",
    "akat",
    "nek",
    "nak",
    "ban",
    "ben",
    "ból",
    "ből",
    "bol",
    "rol",
    "ről",
    "re",
    "ra",
    "hoz",
    "hez",
    "höz",
    "val",
    "vel",
)
DIVIAN_AI_COLOR_PHRASES = (
    "Szuper matt grafit",
    "Szuper matt fehér",
    "Szuper matt kasmír",
    "Szuper matt provance",
    "Szuper matt beige",
    "Antracit",
    "Beton fehér",
    "Beige fényes",
    "Fehér fényes",
    "Fehér tölgy",
    "Artizán tölgy",
    "Szürke tölgy",
    "Cappuccino fényes",
    "Agyagszürke",
    "Fjord zöld",
    "Sonoma",
    "Rusztikus sötét tölgy",
    "Kasmír",
    "Antracit fényes",
    "Cappuccino",
    "Fehér",
    "Beige",
    "San Remo",
    "Világos szürke",
    "Etna",
    "Ibiza",
    "Bianco",
    "Rusztik fehér",
    "Wotan tölgy",
    "Csíkos tölgy",
    "Canyon tölgy",
    "Petra tölgy",
    "Magasfényű fehér",
    "Lazac",
    "Sötét homok",
    "Iguazu márvány",
    "Világos homok",
    "Arany craft tölgy",
    "Sötét tölgy",
    "Krém Navona",
    "Porterhouse dió",
    "Sonoma Black",
    "Fekete-kvarc",
    "Ventura",
    "Matt fekete",
    "Króm",
    "Arany",
    "Rose gold",
    "Malibu",
    "Beige-kvarc",
    "Snow fehér",
)
DIVIAN_AI_PRODUCT_ALIASES = {
    "doroti": ("doroti", "doroit"),
    "antonia": ("antonia", "antónia"),
    "laura": ("laura",),
    "zille": ("zille",),
    "anna": ("anna",),
    "kira": ("kira",),
    "kata": ("kata",),
    "kinga": ("kinga",),
    "klio": ("klio", "klió"),
}
DIVIAN_AI_SUBJECT_ALIASES = {
    "butorlap": ("bútorlap", "butorlap"),
    "front": ("front", "frontok"),
    "korpusz": ("korpusz", "korpusz", "korpuszok", "látható korpusz", "nem látható korpusz"),
    "munkalap": ("munkalap", "munkalapok"),
    "falipanel": ("falipanel", "falipanelek"),
    "vilagitas": ("világítás", "vilagitas", "világítási", "vilagitasi", "led", "led profil", "led szett"),
    "fogantyu": ("fogantyú", "fogantyu", "fogantyúk", "fogantyuk"),
    "garancia": ("garancia",),
}
DIVIAN_AI_PARTNER_CATEGORY_ALIASES = {
    "szek": ("szek", "szék", "szekek", "székek", "etkezo szek", "étkező szék"),
    "asztal": ("asztal", "asztalok"),
    "garnitura": ("garnitura", "garnitúra", "garniturak", "garnitúrák", "etkezogarnitura", "étkezőgarnitúra"),
    "konyhagep": ("konyhagep", "konyhagép", "konyha gepek", "konyhagépek"),
    "kisgep": ("kisgep", "kisgép", "konyhai kisgep", "konyhai kisgép", "konyhai kisgepek", "konyhai kisgépek"),
    "mosogatotalca": ("mosogatotalca", "mosogatótálca", "mosogatotalcak", "mosogatótálcák"),
    "csaptelep": ("csaptelep", "csaptelepek"),
    "vasalat": ("vasalat", "vasalatok"),
    "kiegeszito": ("kiegeszito", "kiegészítő", "kiegeszitok", "kiegészítők"),
    "vilagitas": ("vilagitas", "világítás", "vilagitasi", "világítási", "led", "led profil", "led szett", "konyhai világítás", "konyhai vilagitas"),
    "blokk_konyha": ("blokk konyha", "blokk konyhak", "blokk konyhák"),
}
DIVIAN_AI_COMPANY_TERM_HINTS = (
    "divian",
    "ceg",
    "cég",
    "szekhely",
    "székhely",
    "telephely",
    "telephelyek",
    "cegjegyzek",
    "cégjegyzék",
    "adoszam",
    "adószám",
    "akcio",
    "akció",
    "uj termek",
    "új termék",
    "partner",
    "katalogus",
    "katalógus",
    "elemjegyzek",
    "elemjegyzék",
    "viszontelado",
    "viszonteladó",
)
DIVIAN_AI_COMPANY_PROFILE = {
    "groups": {
        "elemes": {
            "label": "Elemes konyhák",
            "summary": "Elemenként vásárolhatók meg az elérhető elemjegyzékből.",
            "members": ["doroti", "antonia", "laura", "zille"],
            "source": "Belső aktuális kínálat",
        },
        "blokk": {
            "label": "Blokk konyhák",
            "summary": "Előre összeállított konstrukciók, szűkített elemválasztékkal.",
            "members": ["kata", "kira", "kinga", "klio"],
            "source": "Belső aktuális kínálat",
        },
    },
    "worktops": {
        "source": "ceges_termekinformacios_kezikonyv.pdf · 17. oldal",
        "all_colors": [
            "Lazac",
            "Sötét homok",
            "Artizán tölgy",
            "Iguazu márvány",
            "Fehér tölgy",
            "Világos homok",
            "Arany Craft tölgy",
            "Beton fehér",
            "Sötét tölgy",
            "Krém Navona",
            "Rusztikus sötét tölgy",
            "Sonoma",
            "Porterhouse dió",
            "Szürke tölgy",
            "Sonoma Black",
            "Fekete-kvarc",
            "Ventura",
            "Fehér",
            "Beige-kvarc",
            "Malibu",
        ],
    },
    "legacy": {
        "anna": {
            "label": "Anna",
            "status": "A PDF-ben még szerepel, de a jelenlegi belső lista szerint nem része az aktuális 4 elemes konyhának.",
            "source": "ceges_termekinformacios_kezikonyv.pdf · 12-13. oldal",
        }
    },
    "kitchens": {
        "doroti": {
            "label": "Doroti",
            "group": "elemes",
            "current": True,
            "source": "ceges_termekinformacios_kezikonyv.pdf · 4-5. oldal + belső aktuális kínálat",
            "summary": "Prémium elemes konyha, elemenként rendelhető.",
            "front_materials": ["MDF fóliás", "bútorlap"],
            "front_colors": [
                "Szuper matt grafit",
                "Szuper matt fehér",
                "Szuper matt kasmír",
                "Szuper matt provance",
                "Antracit",
                "Beton fehér",
                "Beige fényes",
                "Fehér fényes",
                "Fehér tölgy",
                "Artizán tölgy",
                "Szürke tölgy",
                "Cappuccino fényes",
                "Agyagszürke",
                "Fjord zöld",
                "Sonoma",
                "Rusztikus sötét tölgy",
                "Kasmír",
                "Antracit fényes",
            ],
            "material_color_sets": {
                "mdf": ["Szuper matt grafit", "Szuper matt fehér", "Szuper matt kasmír", "Szuper matt provance"],
                "butorlap": [
                    "Antracit",
                    "Beton fehér",
                    "Beige fényes",
                    "Fehér fényes",
                    "Fehér tölgy",
                    "Artizán tölgy",
                    "Szürke tölgy",
                    "Cappuccino fényes",
                    "Agyagszürke",
                    "Fjord zöld",
                    "Sonoma",
                    "Rusztikus sötét tölgy",
                    "Kasmír",
                    "Antracit fényes",
                ],
            },
            "worktop_options": ["38 mm"],
            "warranty": "3 + 3 év regisztrációhoz kötve",
            "notes": [
                "A két fronttípus rendelésnél keverhető.",
                "A felső elemek push to open rendszerrel is kérhetők.",
            ],
        },
        "antonia": {
            "label": "Antónia",
            "group": "elemes",
            "current": True,
            "source": "ceges_termekinformacios_kezikonyv.pdf · 6-7. oldal + belső aktuális kínálat",
            "summary": "Népszerű elemes konyha, elemenként rendelhető.",
            "front_materials": ["MDF fóliás"],
            "front_colors": [
                "Szuper matt grafit",
                "Szuper matt kasmír",
                "Szuper matt fehér",
                "Szuper matt provance",
                "Artizán tölgy",
                "Antracit",
                "Cappuccino",
                "Fehér",
                "Beige",
            ],
            "material_color_sets": {
                "mdf": [
                    "Szuper matt grafit",
                    "Szuper matt kasmír",
                    "Szuper matt fehér",
                    "Szuper matt provance",
                    "Artizán tölgy",
                    "Antracit",
                    "Cappuccino",
                    "Fehér",
                    "Beige",
                ],
            },
            "worktop_options": ["38 mm"],
            "warranty": "3 + 2 év regisztrációhoz kötve",
            "notes": [
                "A matt és magasfényű színek keverhetők.",
            ],
        },
        "laura": {
            "label": "Laura",
            "group": "elemes",
            "current": True,
            "source": "ceges_termekinformacios_kezikonyv.pdf · 8-9. oldal + belső aktuális kínálat",
            "summary": "Klasszikus elemes konyha, elemenként rendelhető.",
            "front_materials": ["MDF fóliás", "mart front"],
            "front_colors": [
                "Szuper matt grafit",
                "Szuper matt kasmír",
                "Szuper matt provance",
                "Szuper matt fehér",
                "Szuper matt beige",
            ],
            "material_color_sets": {
                "mdf": [
                    "Szuper matt grafit",
                    "Szuper matt kasmír",
                    "Szuper matt provance",
                    "Szuper matt fehér",
                    "Szuper matt beige",
                ],
            },
            "worktop_options": ["38 mm"],
            "warranty": "3 + 2 év regisztrációhoz kötve",
        },
        "zille": {
            "label": "Zille",
            "group": "elemes",
            "current": True,
            "source": "ceges_termekinformacios_kezikonyv.pdf · 10-11. oldal + belső aktuális kínálat",
            "summary": "Rusztikus elemes konyha, elemenként rendelhető.",
            "front_materials": ["MDF fóliás", "mart front"],
            "front_colors": [
                "Szuper matt beige",
                "Sonoma",
                "Rusztik fehér",
                "Wotan tölgy",
            ],
            "material_color_sets": {
                "mdf": ["Szuper matt beige", "Sonoma", "Rusztik fehér", "Wotan tölgy"],
            },
            "worktop_options": ["28 mm", "38 mm"],
            "warranty": "3 + 2 év regisztrációhoz kötve",
            "notes": [
                "A PDF-ben blokk változat is szerepel, de a jelenlegi belső lista szerint a blokk kategóriát a Kata, Kira, Kinga és Klió viszi.",
            ],
        },
        "kira": {
            "label": "Kira",
            "group": "blokk",
            "current": True,
            "source": "ceges_termekinformacios_kezikonyv.pdf · 14. oldal + belső aktuális kínálat",
            "summary": "Előre összeállított blokk konyha szűkített elemválasztékkal.",
            "front_materials": ["bútorlap"],
            "front_colors": ["Antracit", "Fehér", "Sonoma", "Csíkos tölgy"],
            "material_color_sets": {
                "butorlap": ["Antracit", "Fehér", "Sonoma", "Csíkos tölgy"],
            },
            "worktop_options": ["28 mm"],
            "sizes": ["164 cm", "184 cm"],
            "warranty": "Értékhatárhoz kötötten 2 vagy 3 év",
        },
        "kata": {
            "label": "Kata",
            "group": "blokk",
            "current": True,
            "source": "ceges_termekinformacios_kezikonyv.pdf · 15. oldal + belső aktuális kínálat",
            "summary": "Előre összeállított blokk konyha szűkített elemválasztékkal.",
            "front_materials": ["bútorlap"],
            "front_colors": [
                "Magasfényű fehér",
                "Csíkos tölgy",
                "Antracit",
                "San Remo",
                "Fehér",
                "Bianco",
                "Sonoma",
                "Canyon tölgy",
            ],
            "material_color_sets": {
                "butorlap": [
                    "Magasfényű fehér",
                    "Csíkos tölgy",
                    "Antracit",
                    "San Remo",
                    "Fehér",
                    "Bianco",
                    "Sonoma",
                    "Canyon tölgy",
                ],
            },
            "worktop_options": ["28 mm"],
            "sizes": ["160 cm", "200 cm"],
            "warranty": "Értékhatárhoz kötötten 2 vagy 3 év",
        },
        "kinga": {
            "label": "Kinga",
            "group": "blokk",
            "current": True,
            "source": "ceges_termekinformacios_kezikonyv.pdf · 16. oldal + belső aktuális kínálat",
            "summary": "Előre összeállított blokk konyha szűkített elemválasztékkal.",
            "front_materials": ["bútorlap"],
            "front_colors": ["Antracit", "San Remo", "Fehér", "Bianco", "Sonoma", "Canyon tölgy"],
            "material_color_sets": {
                "butorlap": ["Antracit", "San Remo", "Fehér", "Bianco", "Sonoma", "Canyon tölgy"],
            },
            "worktop_options": ["28 mm"],
            "sizes": ["160 cm", "200 cm"],
            "warranty": "Értékhatárhoz kötötten 2 vagy 3 év",
        },
        "klio": {
            "label": "Klió",
            "group": "blokk",
            "current": True,
            "source": "Belső aktuális kínálat",
            "summary": "Új blokk konyha, előre összeállított konstrukció szűkített elemválasztékkal.",
            "front_materials": [],
            "front_colors": [],
            "worktop_options": [],
            "warranty": "",
            "notes": [
                "A részletes Klió specifikáció még nincs benne a feltöltött PDF tudástárban.",
            ],
        },
        "anna": {
            "label": "Anna",
            "group": "elemes",
            "current": False,
            "source": "ceges_termekinformacios_kezikonyv.pdf · 12-13. oldal",
            "summary": "A PDF-ben szereplő, jelenleg nem elsődleges elemes konyha.",
            "front_materials": ["bútorlap"],
            "front_colors": [
                "Antracit",
                "Kasmír",
                "Bianco",
                "Csíkos tölgy",
                "Fehér",
                "Sonoma",
                "San Remo",
                "Világos szürke",
                "Agyagszürke",
                "Ibiza",
                "Canyon tölgy",
                "Etna",
                "Petra tölgy",
            ],
            "material_color_sets": {
                "butorlap": [
                    "Antracit",
                    "Kasmír",
                    "Bianco",
                    "Csíkos tölgy",
                    "Fehér",
                    "Sonoma",
                    "San Remo",
                    "Világos szürke",
                    "Agyagszürke",
                    "Ibiza",
                    "Canyon tölgy",
                    "Etna",
                    "Petra tölgy",
                ],
            },
            "worktop_options": ["28 mm", "38 mm"],
            "warranty": "3 + 1 év regisztrációhoz kötve",
        },
    },
}
NETTFRONT_RUNTIME_DIR = RUNTIME_DIR / "nettfront"
NETTFRONT_PROCUREMENT_RUNTIME_DIR = NETTFRONT_RUNTIME_DIR / "procurement"
NETTFRONT_COMPARE_RUNTIME_DIR = NETTFRONT_RUNTIME_DIR / "compare"
NETTFRONT_ORDER_RUNTIME_DIR = NETTFRONT_RUNTIME_DIR / "order"
NETTFRONT_ORDER_DEFAULT_AVG_PATH = BASE_DIR / "data" / "nettfront-rendeles-atlag.xlsx"
STATIC_ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/script.js": ("script.js", "application/javascript; charset=utf-8"),
}
COMMON_SCRIPT_TAG = '<script src="/script.js"></script>'
DIVIAN_AI_STOPWORDS = {
    "hogy",
    "vagy",
    "van",
    "lesz",
    "mert",
    "amikor",
    "amely",
    "ezzel",
    "arra",
    "ezt",
    "azt",
    "itt",
    "ott",
    "egy",
    "ezt",
    "arra",
    "mint",
    "ami",
    "melyik",
    "milyen",
    "miért",
    "mit",
    "hogyan",
    "akkor",
    "ennek",
    "annak",
    "vannak",
    "lehet",
    "kell",
    "csak",
    "vagyis",
    "igen",
    "nem",
    "már",
    "még",
    "szerint",
    "alapján",
    "divian",
}
DIVIAN_AI_QUERY_META_TOKENS = {
    "sorold",
    "listaz",
    "listazd",
    "felsorolas",
    "mutasd",
    "mondd",
    "kerdes",
    "kerlek",
    "aktualis",
    "jelenleg",
    "kovetkezo",
    "adat",
    "adatok",
    "informacio",
    "informaciok",
    "fajl",
    "fajlban",
    "dokumentum",
    "dokumentumban",
    "excel",
    "pdf",
    "word",
    "tabla",
    "tablazat",
    "tablazatban",
    "lap",
    "oldal",
    "oldalak",
    "benne",
    "belole",
    "rola",
    "arrol",
    "ebben",
    "ebbol",
    "ezek",
    "ezeket",
    "ezeket",
    "mennyi",
    "hany",
    "mikor",
    "mi",
}
DIVIAN_AI_NAME_FIELD_HINTS = (
    "nev",
    "dolgozo",
    "munkatars",
    "szemely",
    "partner",
    "ugyfel",
    "megnevezes",
    "tema",
)
DIVIAN_AI_DESCRIPTION_FIELD_HINTS = (
    "megnevezes",
    "leiras",
    "tipus",
    "modell",
    "tema",
    "szin",
    "dekor",
    "anyag",
)
DIVIAN_AI_FILE_QUERY_HINTS = (
    "mi van",
    "mit tartalmaz",
    "mi talalhato",
    "milyen adatok",
    "milyen oszlopok",
    "milyen mezok",
    "fajl",
    "dokumentum",
    "excel",
    "pdf",
)
DIVIAN_AI_CORRECTION_MARKERS = (
    "nem jo",
    "nem ez",
    "rossz",
    "pontatlan",
    "javitsd",
    "javitani",
    "nem erre",
    "nem ezt",
    "nem igy",
    "masra gondoltam",
    "hanem",
)
DIVIAN_AI_REFERENCE_MARKERS = (
    "ez",
    "ezek",
    "az",
    "azok",
    "ebből",
    "ebbol",
    "ennek",
    "annak",
    "arra",
    "erre",
    "ugyanebbol",
    "ugyanennek",
)


@dataclass(frozen=True)
class DivianAIChunk:
    label: str
    source_name: str
    page_number: int
    text: str
    normalized: str
    tokens: frozenset[str]


@dataclass(frozen=True)
class DivianAIPage:
    label: str
    source_name: str
    page_number: int
    title: str
    text: str
    normalized: str
    folded: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class DivianAIRecord:
    label: str
    source_name: str
    row_number: int
    fields: tuple[tuple[str, str], ...]
    text: str
    normalized: str
    tokens: frozenset[str]


@dataclass
class DivianAIKnowledgeCache:
    signature: tuple[tuple[str, int, int], ...] = field(default_factory=tuple)
    loaded_at: float = 0.0
    sources: list[str] = field(default_factory=list)
    source_meta: dict[str, dict] = field(default_factory=dict)
    pages: list[DivianAIPage] = field(default_factory=list)
    chunks: list[DivianAIChunk] = field(default_factory=list)
    records: list[DivianAIRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class DivianAISourceExtractResult:
    source_name: str
    parser_name: str = ""
    study_mode: str = ""
    confidence: str = ""
    note: str = ""
    pages: list[DivianAIPage] = field(default_factory=list)
    chunks: list[DivianAIChunk] = field(default_factory=list)
    records: list[DivianAIRecord] = field(default_factory=list)
    error: str = ""


DIVIAN_AI_CACHE = DivianAIKnowledgeCache()
DIVIAN_AI_OPENAI_DISABLED_REASON = ""
DIVIAN_AI_OPENAI_DISABLED_UNTIL = 0.0
DIVIAN_AI_PRIME_LOCK = threading.Lock()
DIVIAN_AI_PRIME_STARTED = False
MANUFACTURING_BUNDLE_CACHE: dict[str, dict[str, object]] = {}
MANUFACTURING_BUNDLE_CACHE_LOCK = threading.Lock()


def _dev_reload_token() -> str:
    return os.getenv(DEV_RELOAD_TOKEN_ENV, "dev-static")


def _read_env_value(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value

    if os.name == "nt" and winreg is not None:
        registry_paths = (
            (winreg.HKEY_CURRENT_USER, r"Environment"),
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        )
        for root, subkey in registry_paths:
            try:
                with winreg.OpenKey(root, subkey) as key:
                    stored_value, _ = winreg.QueryValueEx(key, name)
                if stored_value:
                    return str(stored_value)
            except OSError:
                continue

    return default


def _divian_ai_read_response_cache() -> dict[str, dict]:
    if not DIVIAN_AI_RESPONSE_CACHE.exists():
        return {}
    try:
        payload = json.loads(DIVIAN_AI_RESPONSE_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): value for key, value in payload.items() if isinstance(value, dict)}


def _divian_ai_write_response_cache(entries: dict[str, dict]) -> None:
    DIVIAN_AI_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    ordered_items = sorted(
        entries.items(),
        key=lambda item: float(item[1].get("updated_at", 0.0)),
        reverse=True,
    )[:DIVIAN_AI_RESPONSE_CACHE_LIMIT]
    trimmed_entries = {key: value for key, value in ordered_items}
    DIVIAN_AI_RESPONSE_CACHE.write_text(
        json.dumps(trimmed_entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _divian_ai_response_cache_key(
    *,
    provider: str,
    model: str,
    question: str,
    effective_question: str,
    is_company_question: bool,
    history_items: list[dict[str, str]],
    context_text: str,
) -> str:
    payload = {
        "provider": provider,
        "model": model,
        "question": question,
        "effective_question": effective_question,
        "is_company_question": is_company_question,
        "history": history_items[-6:],
        "context_hash": hashlib.sha1(context_text.encode("utf-8")).hexdigest(),
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(serialized.encode("utf-8")).hexdigest()


def _divian_ai_cached_response(cache_key: str) -> dict | None:
    entry = _divian_ai_read_response_cache().get(cache_key)
    if not entry:
        return None

    answer = str(entry.get("answer", "")).strip()
    if not answer:
        return None

    sources = entry.get("sources", [])
    if not isinstance(sources, list):
        sources = []

    return {
        "ok": True,
        "answer": answer,
        "sources": [str(source) for source in sources if str(source).strip()],
        "cached": True,
    }


def _divian_ai_store_cached_response(cache_key: str, answer: str, sources: list[str]) -> None:
    entries = _divian_ai_read_response_cache()
    entries[cache_key] = {
        "answer": answer,
        "sources": sources,
        "updated_at": time.time(),
    }
    _divian_ai_write_response_cache(entries)


def _divian_ai_provider() -> str:
    provider = _read_env_value("DIVIAN_AI_PROVIDER", DIVIAN_AI_PROVIDER).strip().lower()
    if provider in {"openai", "gemini", "groq"}:
        return provider
    if _read_env_value("GROQ_API_KEY", "").strip():
        return "groq"
    if _read_env_value("GEMINI_API_KEY", "").strip():
        return "gemini"
    return "openai"


def _divian_ai_provider_model(provider: str) -> str:
    if provider == "groq":
        return _read_env_value("DIVIAN_AI_GROQ_MODEL", DIVIAN_AI_GROQ_MODEL).strip() or "llama-3.1-8b-instant"
    if provider == "gemini":
        return _read_env_value("DIVIAN_AI_GEMINI_MODEL", DIVIAN_AI_GEMINI_MODEL).strip() or "gemini-2.5-flash"
    return _read_env_value("DIVIAN_AI_MODEL", DIVIAN_AI_MODEL).strip() or "gpt-4.1-mini"


def _divian_ai_provider_api_key(provider: str) -> str:
    if provider == "groq":
        return _read_env_value("GROQ_API_KEY", "").strip()
    if provider == "gemini":
        return _read_env_value("GEMINI_API_KEY", "").strip()
    return _read_env_value("OPENAI_API_KEY", "").strip()


def _divian_ai_provider_base_url(provider: str) -> str | None:
    if provider == "groq":
        return "https://api.groq.com/openai/v1"
    return None


def _should_watch_path(path: Path) -> bool:
    if any(part in WATCH_IGNORED_DIRS for part in path.parts):
        return False
    return path.suffix.lower() in WATCHED_EXTENSIONS or path.name in WATCHED_FILES


def _build_watch_snapshot() -> dict[str, tuple[int, int]]:
    snapshot: dict[str, tuple[int, int]] = {}
    for file_path in BASE_DIR.rglob("*"):
        if not file_path.is_file():
            continue
        relative_path = file_path.relative_to(BASE_DIR)
        if not _should_watch_path(relative_path):
            continue
        stat = file_path.stat()
        snapshot[str(relative_path)] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def _spawn_dev_child(reload_token: str) -> subprocess.Popen:
    env = os.environ.copy()
    env[DEV_CHILD_ENV] = "1"
    env[DEV_RELOAD_TOKEN_ENV] = reload_token
    return subprocess.Popen([sys.executable, __file__], cwd=BASE_DIR, env=env)


def _run_dev_supervisor() -> None:
    reload_counter = 0
    snapshot = _build_watch_snapshot()
    child = _spawn_dev_child(f"reload-{reload_counter}")
    print(f"Dev reload supervisor active on http://localhost:{PORT}")

    try:
        while True:
            time.sleep(DEV_WATCH_INTERVAL_SECONDS)
            next_snapshot = _build_watch_snapshot()
            changed = next_snapshot != snapshot
            child_exited = child is not None and child.poll() is not None

            if not changed:
                if child is None:
                    continue
                if not child_exited:
                    continue
                print("A fejlesztoi szerver leallt. A kovetkezo modositasnal ujraindul.")
                child = None
                continue

            snapshot = next_snapshot
            reload_counter += 1
            print("Valtozas eszlelve, szerver ujrainditas...")

            if child and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)

            child = _spawn_dev_child(f"reload-{reload_counter}")
    except KeyboardInterrupt:
        print("\nFejlesztoi szerver leallitva.")
    finally:
        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)


VACATION_MONTH_NAMES = (
    "",
    "január",
    "február",
    "március",
    "április",
    "május",
    "június",
    "július",
    "augusztus",
    "szeptember",
    "október",
    "november",
    "december",
)
VACATION_WEEKDAY_LABELS = ("H", "K", "Sze", "Cs", "P", "Szo", "V")


def _vacation_db_connection() -> sqlite3.Connection:
    VACATION_CALENDAR_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(VACATION_CALENDAR_DB)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS vacation_departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            max_absent INTEGER NOT NULL DEFAULT 1 CHECK (max_absent >= 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS vacation_employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS vacation_employee_departments (
            employee_id INTEGER NOT NULL,
            department_id INTEGER NOT NULL,
            PRIMARY KEY (employee_id, department_id),
            FOREIGN KEY (employee_id) REFERENCES vacation_employees(id) ON DELETE CASCADE,
            FOREIGN KEY (department_id) REFERENCES vacation_departments(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS vacation_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (employee_id) REFERENCES vacation_employees(id) ON DELETE CASCADE
        );
        """
    )
    return connection


def _vacation_parse_month(month_value: str) -> date:
    clean_value = month_value.strip()
    if clean_value:
        try:
            parsed = datetime.strptime(clean_value, "%Y-%m")
            return date(parsed.year, parsed.month, 1)
        except ValueError:
            pass
    today = date.today()
    return date(today.year, today.month, 1)


def _vacation_month_value(month_start: date) -> str:
    return month_start.strftime("%Y-%m")


def _vacation_month_label(month_start: date) -> str:
    return f"{month_start.year}. {VACATION_MONTH_NAMES[month_start.month]}"


def _vacation_next_month(month_start: date, offset: int) -> date:
    year = month_start.year + ((month_start.month - 1 + offset) // 12)
    month = ((month_start.month - 1 + offset) % 12) + 1
    return date(year, month, 1)


def _vacation_month_bounds(month_start: date) -> tuple[date, date]:
    next_month = _vacation_next_month(month_start, 1)
    return month_start, next_month - timedelta(days=1)


def _vacation_parse_date(value: str) -> date | None:
    clean_value = value.strip()
    if not clean_value:
        return None
    for pattern in ("%Y-%m-%d", "%Y.%m.%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(clean_value, pattern).date()
        except ValueError:
            continue
    return None


def _vacation_date_value(day: date) -> str:
    return day.isoformat()


def _vacation_date_label(day: date) -> str:
    return day.strftime("%Y.%m.%d")


def _vacation_now_stamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _vacation_parse_int(value: str, default: int | None = None) -> int | None:
    try:
        return int(value.strip())
    except (TypeError, ValueError, AttributeError):
        return default


def _vacation_parse_form(raw_body: bytes) -> dict[str, list[str]]:
    parsed = urllib.parse.parse_qs(raw_body.decode("utf-8", errors="ignore"), keep_blank_values=True)
    return {key: value for key, value in parsed.items()}


def _vacation_form_value(form_data: dict[str, list[str]], name: str) -> str:
    values = form_data.get(name, [])
    return values[-1].strip() if values else ""


def _vacation_form_values(form_data: dict[str, list[str]], name: str) -> list[str]:
    return [value.strip() for value in form_data.get(name, []) if value.strip()]


def _vacation_fetch_departments(connection: sqlite3.Connection) -> list[dict]:
    rows = connection.execute(
        """
        SELECT
            d.id,
            d.name,
            d.max_absent,
            COUNT(ed.employee_id) AS employee_count
        FROM vacation_departments d
        LEFT JOIN vacation_employee_departments ed ON ed.department_id = d.id
        GROUP BY d.id
        ORDER BY d.name COLLATE NOCASE
        """
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "name": str(row["name"]),
            "max_absent": int(row["max_absent"]),
            "employee_count": int(row["employee_count"] or 0),
        }
        for row in rows
    ]


def _vacation_fetch_department(connection: sqlite3.Connection, department_id: int) -> dict | None:
    row = connection.execute(
        """
        SELECT id, name, max_absent
        FROM vacation_departments
        WHERE id = ?
        """,
        (department_id,),
    ).fetchone()
    if row is None:
        return None
    return {"id": int(row["id"]), "name": str(row["name"]), "max_absent": int(row["max_absent"])}


def _vacation_employee_department_map(connection: sqlite3.Connection) -> dict[int, list[dict]]:
    rows = connection.execute(
        """
        SELECT
            ed.employee_id,
            d.id AS department_id,
            d.name,
            d.max_absent
        FROM vacation_employee_departments ed
        JOIN vacation_departments d ON d.id = ed.department_id
        ORDER BY d.name COLLATE NOCASE
        """
    ).fetchall()
    mapping: dict[int, list[dict]] = {}
    for row in rows:
        mapping.setdefault(int(row["employee_id"]), []).append(
            {
                "id": int(row["department_id"]),
                "name": str(row["name"]),
                "max_absent": int(row["max_absent"]),
            }
        )
    return mapping


def _vacation_fetch_employees(connection: sqlite3.Connection) -> list[dict]:
    department_map = _vacation_employee_department_map(connection)
    rows = connection.execute(
        """
        SELECT
            e.id,
            e.name,
            COUNT(v.id) AS vacation_count
        FROM vacation_employees e
        LEFT JOIN vacation_entries v ON v.employee_id = e.id
        GROUP BY e.id
        ORDER BY e.name COLLATE NOCASE
        """
    ).fetchall()
    employees: list[dict] = []
    for row in rows:
        department_items = department_map.get(int(row["id"]), [])
        employees.append(
            {
                "id": int(row["id"]),
                "name": str(row["name"]),
                "vacation_count": int(row["vacation_count"] or 0),
                "departments": department_items,
                "department_ids": [int(item["id"]) for item in department_items],
                "department_names": [str(item["name"]) for item in department_items],
            }
        )
    return employees


def _vacation_fetch_employee(connection: sqlite3.Connection, employee_id: int) -> dict | None:
    row = connection.execute(
        """
        SELECT id, name
        FROM vacation_employees
        WHERE id = ?
        """,
        (employee_id,),
    ).fetchone()
    if row is None:
        return None

    department_rows = connection.execute(
        """
        SELECT d.id, d.name, d.max_absent
        FROM vacation_employee_departments ed
        JOIN vacation_departments d ON d.id = ed.department_id
        WHERE ed.employee_id = ?
        ORDER BY d.name COLLATE NOCASE
        """,
        (employee_id,),
    ).fetchall()
    departments = [
        {"id": int(item["id"]), "name": str(item["name"]), "max_absent": int(item["max_absent"])}
        for item in department_rows
    ]
    return {
        "id": int(row["id"]),
        "name": str(row["name"]),
        "departments": departments,
        "department_ids": [int(item["id"]) for item in departments],
        "department_names": [str(item["name"]) for item in departments],
    }


def _vacation_fetch_leave(connection: sqlite3.Connection, leave_id: int) -> dict | None:
    row = connection.execute(
        """
        SELECT
            v.id,
            v.employee_id,
            e.name AS employee_name,
            v.start_date,
            v.end_date,
            v.note
        FROM vacation_entries v
        JOIN vacation_employees e ON e.id = v.employee_id
        WHERE v.id = ?
        """,
        (leave_id,),
    ).fetchone()
    if row is None:
        return None

    employee = _vacation_fetch_employee(connection, int(row["employee_id"]))
    return {
        "id": int(row["id"]),
        "employee_id": int(row["employee_id"]),
        "employee_name": str(row["employee_name"]),
        "start_date": str(row["start_date"]),
        "end_date": str(row["end_date"]),
        "note": str(row["note"] or ""),
        "departments": employee["departments"] if employee else [],
    }


def _vacation_fetch_leaves_in_range(connection: sqlite3.Connection, start_day: date, end_day: date) -> list[dict]:
    employee_map = {item["id"]: item for item in _vacation_fetch_employees(connection)}
    rows = connection.execute(
        """
        SELECT
            v.id,
            v.employee_id,
            e.name AS employee_name,
            v.start_date,
            v.end_date,
            v.note
        FROM vacation_entries v
        JOIN vacation_employees e ON e.id = v.employee_id
        WHERE v.start_date <= ? AND v.end_date >= ?
        ORDER BY v.start_date, e.name COLLATE NOCASE
        """,
        (_vacation_date_value(end_day), _vacation_date_value(start_day)),
    ).fetchall()

    leaves: list[dict] = []
    for row in rows:
        employee = employee_map.get(int(row["employee_id"]), {})
        leaves.append(
            {
                "id": int(row["id"]),
                "employee_id": int(row["employee_id"]),
                "employee_name": str(row["employee_name"]),
                "start_date": str(row["start_date"]),
                "end_date": str(row["end_date"]),
                "note": str(row["note"] or ""),
                "departments": employee.get("departments", []),
                "department_names": employee.get("department_names", []),
            }
        )
    return leaves


def _vacation_overlaps_existing_leave(
    connection: sqlite3.Connection,
    employee_id: int,
    start_day: date,
    end_day: date,
    exclude_leave_id: int | None = None,
) -> bool:
    query = """
        SELECT 1
        FROM vacation_entries
        WHERE employee_id = ?
          AND start_date <= ?
          AND end_date >= ?
    """
    params: list[object] = [employee_id, _vacation_date_value(end_day), _vacation_date_value(start_day)]
    if exclude_leave_id is not None:
        query += " AND id <> ?"
        params.append(exclude_leave_id)
    row = connection.execute(query, params).fetchone()
    return row is not None


def _vacation_validate_department_limits(
    connection: sqlite3.Connection,
    employee_id: int,
    start_day: date,
    end_day: date,
    exclude_leave_id: int | None = None,
) -> tuple[bool, str]:
    employee = _vacation_fetch_employee(connection, employee_id)
    if employee is None:
        return False, "A kiválasztott kolléga nem található."
    if not employee["departments"]:
        return False, "A kollégához legalább egy részleget be kell állítani."

    current_day = start_day
    while current_day <= end_day:
        day_value = _vacation_date_value(current_day)
        for department in employee["departments"]:
            absent_row = connection.execute(
                """
                SELECT COUNT(DISTINCT v.employee_id) AS absent_count
                FROM vacation_entries v
                JOIN vacation_employee_departments ed ON ed.employee_id = v.employee_id
                WHERE ed.department_id = ?
                  AND v.start_date <= ?
                  AND v.end_date >= ?
                  AND (? IS NULL OR v.id <> ?)
                """,
                (department["id"], day_value, day_value, exclude_leave_id, exclude_leave_id),
            ).fetchone()
            absent_count = int(absent_row["absent_count"] or 0) if absent_row else 0
            if absent_count + 1 > int(department["max_absent"]):
                return (
                    False,
                    f"A(z) {department['name']} részlegen {_vacation_date_label(current_day)} napon már elértétek a szabadságlimitet.",
                )
        current_day += timedelta(days=1)
    return True, ""


def _vacation_save_department(form_data: dict[str, list[str]]) -> tuple[bool, str]:
    department_id = _vacation_parse_int(_vacation_form_value(form_data, "department_id"))
    name = _clean_spaces(_vacation_form_value(form_data, "name"))
    max_absent = _vacation_parse_int(_vacation_form_value(form_data, "max_absent"), default=1)

    if not name:
        return False, "A részleg neve kötelező."
    if max_absent is None or max_absent < 0:
        return False, "A részleg limitje 0 vagy nagyobb szám lehet."

    now_stamp = _vacation_now_stamp()
    try:
        with _vacation_db_connection() as connection:
            if department_id:
                exists = _vacation_fetch_department(connection, department_id)
                if exists is None:
                    return False, "A kiválasztott részleg nem található."
                connection.execute(
                    """
                    UPDATE vacation_departments
                    SET name = ?, max_absent = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (name, max_absent, now_stamp, department_id),
                )
                return True, f"Frissítve: {name}"

            connection.execute(
                """
                INSERT INTO vacation_departments (name, max_absent, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (name, max_absent, now_stamp, now_stamp),
            )
            return True, f"Létrehozva: {name}"
    except sqlite3.IntegrityError:
        return False, "Ilyen nevű részleg már létezik."


def _vacation_delete_department(form_data: dict[str, list[str]]) -> tuple[bool, str]:
    department_id = _vacation_parse_int(_vacation_form_value(form_data, "department_id"))
    if department_id is None:
        return False, "A törlendő részleg nem azonosítható."

    with _vacation_db_connection() as connection:
        department = _vacation_fetch_department(connection, department_id)
        if department is None:
            return False, "A törlendő részleg nem található."

        assigned_row = connection.execute(
            "SELECT COUNT(*) AS count FROM vacation_employee_departments WHERE department_id = ?",
            (department_id,),
        ).fetchone()
        if assigned_row and int(assigned_row["count"] or 0) > 0:
            return False, "A részleg még kollégákhoz van rendelve. Előbb vedd le onnan."

        connection.execute("DELETE FROM vacation_departments WHERE id = ?", (department_id,))
    return True, f"Törölve: {department['name']}"


def _vacation_save_employee(form_data: dict[str, list[str]]) -> tuple[bool, str]:
    employee_id = _vacation_parse_int(_vacation_form_value(form_data, "employee_id"))
    name = _clean_spaces(_vacation_form_value(form_data, "name"))
    department_ids = sorted(
        {
            department_id
            for raw_value in _vacation_form_values(form_data, "department_ids")
            for department_id in [_vacation_parse_int(raw_value)]
            if department_id is not None
        }
    )

    if not name:
        return False, "A kolléga neve kötelező."
    if not department_ids:
        return False, "A kollégához legalább egy részleget válassz ki."

    now_stamp = _vacation_now_stamp()
    try:
        with _vacation_db_connection() as connection:
            valid_departments = {
                int(row["id"])
                for row in connection.execute(
                    f"SELECT id FROM vacation_departments WHERE id IN ({','.join('?' for _ in department_ids)})",
                    department_ids,
                ).fetchall()
            }
            if len(valid_departments) != len(department_ids):
                return False, "A kiválasztott részlegek között van érvénytelen."

            if employee_id:
                employee = _vacation_fetch_employee(connection, employee_id)
                if employee is None:
                    return False, "A kiválasztott kolléga nem található."
                connection.execute(
                    """
                    UPDATE vacation_employees
                    SET name = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (name, now_stamp, employee_id),
                )
                connection.execute("DELETE FROM vacation_employee_departments WHERE employee_id = ?", (employee_id,))
                target_id = employee_id
                message = f"Frissítve: {name}"
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO vacation_employees (name, created_at, updated_at)
                    VALUES (?, ?, ?)
                    """,
                    (name, now_stamp, now_stamp),
                )
                target_id = int(cursor.lastrowid)
                message = f"Létrehozva: {name}"

            connection.executemany(
                """
                INSERT INTO vacation_employee_departments (employee_id, department_id)
                VALUES (?, ?)
                """,
                [(target_id, department_id) for department_id in department_ids],
            )
            return True, message
    except sqlite3.IntegrityError:
        return False, "Ilyen nevű kolléga már létezik."


def _vacation_delete_employee(form_data: dict[str, list[str]]) -> tuple[bool, str]:
    employee_id = _vacation_parse_int(_vacation_form_value(form_data, "employee_id"))
    if employee_id is None:
        return False, "A törlendő kolléga nem azonosítható."

    with _vacation_db_connection() as connection:
        employee = _vacation_fetch_employee(connection, employee_id)
        if employee is None:
            return False, "A törlendő kolléga nem található."
        connection.execute("DELETE FROM vacation_employees WHERE id = ?", (employee_id,))
    return True, f"Törölve: {employee['name']}"


def _vacation_save_leave(form_data: dict[str, list[str]]) -> tuple[bool, str]:
    leave_id = _vacation_parse_int(_vacation_form_value(form_data, "leave_id"))
    employee_id = _vacation_parse_int(_vacation_form_value(form_data, "employee_id"))
    start_day = _vacation_parse_date(_vacation_form_value(form_data, "start_date"))
    end_day = _vacation_parse_date(_vacation_form_value(form_data, "end_date"))
    note = _clean_spaces(_vacation_form_value(form_data, "note"))

    if employee_id is None:
        return False, "A szabadsághoz válassz ki egy kollégát."
    if start_day is None or end_day is None:
        return False, "A szabadság kezdete és vége kötelező."
    if end_day < start_day:
        return False, "A szabadság vége nem lehet korábbi, mint a kezdete."

    with _vacation_db_connection() as connection:
        employee = _vacation_fetch_employee(connection, employee_id)
        if employee is None:
            return False, "A kiválasztott kolléga nem található."
        if not employee["departments"]:
            return False, "A kollégához nincs részleg beállítva, ezért nem ellenőrizhető a limit."
        if _vacation_overlaps_existing_leave(connection, employee_id, start_day, end_day, exclude_leave_id=leave_id):
            return False, "Ehhez a kollégához már van átfedő szabadság felvéve."

        valid, message = _vacation_validate_department_limits(
            connection,
            employee_id,
            start_day,
            end_day,
            exclude_leave_id=leave_id,
        )
        if not valid:
            return False, message

        now_stamp = _vacation_now_stamp()
        if leave_id:
            existing = _vacation_fetch_leave(connection, leave_id)
            if existing is None:
                return False, "A kiválasztott szabadság nem található."
            connection.execute(
                """
                UPDATE vacation_entries
                SET employee_id = ?, start_date = ?, end_date = ?, note = ?, updated_at = ?
                WHERE id = ?
                """,
                (employee_id, _vacation_date_value(start_day), _vacation_date_value(end_day), note, now_stamp, leave_id),
            )
            return True, f"Frissítve: {employee['name']} szabadsága"

        connection.execute(
            """
            INSERT INTO vacation_entries (employee_id, start_date, end_date, note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (employee_id, _vacation_date_value(start_day), _vacation_date_value(end_day), note, now_stamp, now_stamp),
        )
        return True, f"Felvéve: {employee['name']} szabadsága"


def _vacation_delete_leave(form_data: dict[str, list[str]]) -> tuple[bool, str]:
    leave_id = _vacation_parse_int(_vacation_form_value(form_data, "leave_id"))
    if leave_id is None:
        return False, "A törlendő szabadság nem azonosítható."

    with _vacation_db_connection() as connection:
        leave_entry = _vacation_fetch_leave(connection, leave_id)
        if leave_entry is None:
            return False, "A törlendő szabadság nem található."
        connection.execute("DELETE FROM vacation_entries WHERE id = ?", (leave_id,))
    return True, f"Törölve: {leave_entry['employee_name']} szabadsága"


def _vacation_build_calendar(month_start: date, leaves: list[dict]) -> tuple[list[list[dict]], int]:
    month_end = _vacation_month_bounds(month_start)[1]
    day_map: dict[date, list[dict]] = {}
    limit_day_count = 0

    for leave_entry in leaves:
        leave_start = _vacation_parse_date(leave_entry["start_date"])
        leave_end = _vacation_parse_date(leave_entry["end_date"])
        if leave_start is None or leave_end is None:
            continue
        current_day = max(leave_start, month_start)
        final_day = min(leave_end, month_end)
        while current_day <= final_day:
            day_map.setdefault(current_day, []).append(leave_entry)
            current_day += timedelta(days=1)

    weeks: list[list[dict]] = []
    month_weeks = month_calendar.Calendar(firstweekday=0).monthdatescalendar(month_start.year, month_start.month)
    for week in month_weeks:
        week_cells: list[dict] = []
        for day in week:
            entries = sorted(day_map.get(day, []), key=lambda item: item["employee_name"].lower())
            department_loads: dict[int, dict] = {}
            for entry in entries:
                for department in entry["departments"]:
                    info = department_loads.setdefault(
                        int(department["id"]),
                        {
                            "id": int(department["id"]),
                            "name": str(department["name"]),
                            "count": 0,
                            "max_absent": int(department["max_absent"]),
                        },
                    )
                    info["count"] += 1
            loads = sorted(department_loads.values(), key=lambda item: item["name"].lower())
            if day.month == month_start.month and any(item["count"] >= item["max_absent"] for item in loads):
                limit_day_count += 1
            week_cells.append(
                {
                    "date": day,
                    "is_current_month": day.month == month_start.month,
                    "entries": entries,
                    "loads": loads,
                }
            )
        weeks.append(week_cells)
    return weeks, limit_day_count


def _vacation_query_params(raw_path: str) -> dict[str, str]:
    parsed = urllib.parse.urlparse(raw_path)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    return {key: values[-1].strip() for key, values in query.items() if values}


def _json_script_payload(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def _manufacturing_query_params(raw_path: str) -> dict[str, str]:
    parsed = urllib.parse.urlparse(raw_path)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    return {key: values[-1].strip() for key, values in query.items() if values}


def _manufacturing_normalize_number(value: object) -> str:
    return re.sub(r"[^0-9]", "", str(value or ""))


def _manufacturing_bundle_signature(production_number: str) -> tuple[str, tuple[tuple[str, int, int], ...]]:
    normalized = _manufacturing_normalize_number(production_number)
    if not normalized:
        return "", tuple()

    folder = manufacturing_production_folder(normalized)
    if not folder.exists():
        return normalized, tuple()

    signature_items: list[tuple[str, int, int]] = []
    for entry in sorted(folder.iterdir(), key=lambda item: item.name.lower()):
        if not entry.is_file():
            continue
        stat = entry.stat()
        signature_items.append((entry.name, stat.st_mtime_ns, stat.st_size))
    return normalized, tuple(signature_items)


def _load_manufacturing_bundle_cached(production_number: str) -> dict:
    normalized, signature = _manufacturing_bundle_signature(production_number)
    if not normalized:
        raise FileNotFoundError("Adj meg egy érvényes gyártási számot.")

    with MANUFACTURING_BUNDLE_CACHE_LOCK:
        cached = MANUFACTURING_BUNDLE_CACHE.get(normalized)
        if cached and cached.get("signature") == signature:
            return dict(cached.get("bundle", {}))

    bundle = load_production_bundle(normalized)
    with MANUFACTURING_BUNDLE_CACHE_LOCK:
        MANUFACTURING_BUNDLE_CACHE[normalized] = {
            "signature": signature,
            "bundle": bundle,
        }
    return dict(bundle)


ITEM_PATTERN_FULL = re.compile(
    r"^\s*(\d+)\s+([A-Z0-9\-/]+)\s+(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+([0-9][0-9.,]*)\s+([A-Z]{1,6})\s+([0-9][0-9.,]*)\s+([0-9][0-9.,]*)\s*$",
    re.IGNORECASE,
)
ITEM_PATTERN_SIMPLE = re.compile(
    r"^\s*(\d+)\s+([A-Z0-9\-/]+)\s+(.+?)\s+([0-9][0-9.,]*)\s+([A-Z]{1,6})\s+([0-9][0-9.,]*)\s+([0-9][0-9.,]*)\s*$",
    re.IGNORECASE,
)


@dataclass
class InvoiceItem:
    row_no: str = ""
    article_code: str = ""
    description: str = ""
    pallet_qty: str = ""
    package_qty: str = ""
    pcs_total: str = ""
    total_qty: str = ""
    unit: str = ""
    unit_price: str = ""
    net_value: str = ""


@dataclass
class InvoiceData:
    invoice_profile: str = ""
    supplier_name: str = ""
    invoice_number: str = ""
    invoice_date: str = ""
    due_date: str = ""
    payment_method: str = ""
    payment_term: str = ""
    delivery_term: str = ""
    transport_mode: str = ""
    order_confirmation_no: str = ""
    client_ref_no: str = ""
    delivery_note_no: str = ""
    truck_number: str = ""
    currency: str = ""
    supplier_lines: list[str] = field(default_factory=list)
    buyer_lines: list[str] = field(default_factory=list)
    items: list[InvoiceItem] = field(default_factory=list)
    total_net: str = ""
    vat_0: str = ""
    vat_19: str = ""
    discount_amount: str = ""
    discount_percent: str = ""
    total_gross: str = ""
    total_pcs: str = ""
    total_m2: str = ""
    total_m3: str = ""
    total_net_weight: str = ""
    total_gross_weight: str = ""
    origin_country: str = ""


@dataclass
class InvoiceChunk:
    invoice_hint: str
    text: str
    page_from: int
    page_to: int


def _clean_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _value_or_default(value: str) -> str:
    return _clean_spaces(value) if value else NO_DATA


def _parse_invoice_date(value: str) -> datetime | None:
    clean_value = _clean_spaces(value)
    if not clean_value:
        return None

    for pattern in (
        "%d.%m.%Y",
        "%d.%m.%y",
        "%d/%m/%Y",
        "%d/%m/%y",
        "%d-%m-%Y",
        "%d-%m-%y",
        "%Y.%m.%d",
        "%Y/%m/%d",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(clean_value, pattern)
        except ValueError:
            continue
    return None


def _format_invoice_date(value: str) -> str:
    parsed = _parse_invoice_date(value)
    if parsed is None:
        return _clean_spaces(value)
    return parsed.strftime("%Y.%m.%d")


def _item_value_or_default(value: str, placeholder: str = NO_DATA) -> str:
    cleaned = _clean_spaces(value)
    return cleaned if cleaned else placeholder


def _is_number_token(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9][0-9.,]*", value))


def _is_integer_token(value: str) -> bool:
    return bool(re.fullmatch(r"\d+", value))


def _parse_eu_number(value: str) -> float | None:
    cleaned = value.strip().replace(" ", "")
    if not cleaned:
        return None
    if not re.fullmatch(r"-?[0-9.,]+", cleaned):
        return None
    normalized = cleaned.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def _format_eu_number(value: float, decimals: int = 2) -> str:
    formatted = f"{value:,.{decimals}f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def _format_rounded_weight(raw_value: str) -> str:
    cleaned = _clean_spaces(raw_value)
    if not cleaned:
        return ""
    normalized = cleaned.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        rounded = Decimal(normalized).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return raw_value
    return f"{int(rounded):,}".replace(",", ".")


def _normalize_kronospan_weight(raw_value: str) -> str:
    value = _parse_eu_number(raw_value)
    if value is None:
        return raw_value
    # Kronospan totalsorban a gross/net weight tipikusan tonnában jelenik meg,
    # a felületen viszont kg-ban mutatjuk.
    if value < 1000:
        value *= 1000
    return _format_eu_number(value, 0)


def _fix_hungarian_mojibake(value: str) -> str:
    return value.translate(str.maketrans({"õ": "ő", "û": "ű", "Õ": "Ő", "Û": "Ű"}))


def _find_index(lines: list[str], pattern: str, start: int = 0) -> int:
    for idx in range(start, len(lines)):
        if re.search(pattern, lines[idx], re.IGNORECASE):
            return idx
    return -1


def _extract_block(lines: list[str], start_pattern: str, end_patterns: list[str]) -> list[str]:
    start_idx = _find_index(lines, start_pattern)
    if start_idx == -1:
        return []

    end_idx = len(lines)
    for end_pattern in end_patterns:
        match_idx = _find_index(lines, end_pattern, start_idx + 1)
        if match_idx != -1:
            end_idx = min(end_idx, match_idx)

    block = lines[start_idx + 1 : end_idx]
    return [line for line in block if line]


def _match_first(text: str, patterns: list[str], flags: int = re.IGNORECASE | re.MULTILINE) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return _clean_spaces(match.group(1))
    return ""


def _pdf_unescape(value: str) -> str:
    value = value.replace(r"\n", " ").replace(r"\r", " ").replace(r"\t", " ")
    value = value.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
    return value


def _looks_like_human_text(text: str) -> bool:
    if len(text.strip()) < 40:
        return False
    indicator_hits = sum(token in text for token in (" endobj", " stream", " xref", "/Type", "FlateDecode"))
    if indicator_hits >= 3 and text.count("\n") < 8:
        return False
    alpha_ratio = sum(ch.isalpha() for ch in text) / max(len(text), 1)
    return alpha_ratio > 0.15


def _fallback_extract_text_from_pdf(pdf_bytes: bytes) -> str:
    raw_text = pdf_bytes.decode("latin1", errors="ignore")
    chunks: list[str] = []

    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf_bytes, re.DOTALL):
        stream_data = match.group(1)
        candidates = [stream_data]
        for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
            try:
                candidates.append(zlib.decompress(stream_data, wbits))
            except Exception:
                pass

        for candidate in candidates:
            decoded = candidate.decode("latin1", errors="ignore")
            for grp in re.findall(r"\((.*?)\)\s*Tj", decoded, re.DOTALL):
                chunks.append(_pdf_unescape(grp))
            for arr in re.findall(r"\[(.*?)\]\s*TJ", decoded, re.DOTALL):
                chunks.extend(_pdf_unescape(part) for part in re.findall(r"\((.*?)\)", arr, re.DOTALL))
        for cand in candidates:
            text = cand.decode("latin1", errors="ignore")
            for grp in re.findall(r"\((.*?)\)\s*Tj", text, re.DOTALL):
                chunks.append(_pdf_unescape(grp))
            for arr in re.findall(r"\[(.*?)\]\s*TJ", text, re.DOTALL):
                parts = re.findall(r"\((.*?)\)", arr, re.DOTALL)
                chunks.extend(_pdf_unescape(p) for p in parts)

    extracted = " ".join(chunks).strip()
    if extracted:
        return re.sub(r"\s+", " ", extracted)

    rough = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-.,:/ ]{4,}", raw_text)
    return " ".join(rough[:800])


def _extract_text_pages_from_pdf(pdf_bytes: bytes) -> list[str]:
    if PdfReader is None:
        return []
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return [(page.extract_text() or "").strip() for page in reader.pages]
    except Exception:
        return []


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    page_text = _extract_text_pages_from_pdf(pdf_bytes)
    if page_text:
        joined = "\n".join(chunk for chunk in page_text if chunk).strip()
        if _looks_like_human_text(joined):
            return joined

    return _fallback_extract_text_from_pdf(pdf_bytes)


def _extract_invoice_number_hint(text: str) -> str:
    lines = [_clean_spaces(line) for line in text.splitlines() if _clean_spaces(line)]
    normalized = "\n".join(lines)

    for pattern in (
        r"DATE\s*:\s*[0-9./-]+\s*NO\s*:\s*([A-Z0-9/\-]+)",
        r"DELIVERY\s*NOTE\s*NO\.?\s*[:\-]?\s*([A-Z0-9/\-]+)",
        r"DOC\.?\s*NO\.?\s*[:\-]?\s*([A-Z0-9/\-]+)",
        r"INVOICE\s*(?:NO|NUMBER|#)\s*[:\-]?\s*([A-Z0-9/\-]+)",
        r"SZÁMLA\s*SZÁMA[\s\S]{0,120}?(\d{5,})",
    ):
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    idx = _find_index(lines, r"^Invoice number$")
    if idx != -1:
        for candidate in lines[idx + 1 : idx + 12]:
            if re.fullmatch(r"\d{4,}", candidate):
                return candidate

    return ""


def split_pdf_by_invoice(pdf_bytes: bytes) -> list[InvoiceChunk]:
    page_texts = _extract_text_pages_from_pdf(pdf_bytes)
    if not page_texts:
        text = extract_text_from_pdf(pdf_bytes)
        return [InvoiceChunk(invoice_hint=_extract_invoice_number_hint(text), text=text, page_from=1, page_to=1)]

    groups: list[InvoiceChunk] = []
    current_hint = ""
    current_pages: list[tuple[int, str]] = []

    for page_index, raw_text in enumerate(page_texts, start=1):
        page_text = raw_text.strip()
        hint = _extract_invoice_number_hint(page_text) if page_text else ""

        if not current_pages:
            current_pages = [(page_index, page_text)]
            current_hint = hint
            continue

        should_split = bool(hint and current_hint and hint != current_hint)
        if should_split:
            from_page = current_pages[0][0]
            to_page = current_pages[-1][0]
            joined_text = "\n".join(text for _, text in current_pages if text).strip()
            groups.append(InvoiceChunk(invoice_hint=current_hint, text=joined_text, page_from=from_page, page_to=to_page))
            current_pages = [(page_index, page_text)]
            current_hint = hint
            continue

        if hint and not current_hint:
            current_hint = hint
        current_pages.append((page_index, page_text))

    if current_pages:
        from_page = current_pages[0][0]
        to_page = current_pages[-1][0]
        joined_text = "\n".join(text for _, text in current_pages if text).strip()
        groups.append(InvoiceChunk(invoice_hint=current_hint, text=joined_text, page_from=from_page, page_to=to_page))

    # Ha nem sikerült jól szétbontani (pl. mind üres), maradjon egy blokk.
    valid_groups = [group for group in groups if group.text]
    return valid_groups or [InvoiceChunk(invoice_hint="", text=extract_text_from_pdf(pdf_bytes), page_from=1, page_to=len(page_texts))]


def _parse_items(lines: list[str]) -> list[InvoiceItem]:
    items: list[InvoiceItem] = []
    for line in lines:
        tokens = line.split()
        if len(tokens) < 7 or not _is_integer_token(tokens[0]):
            continue

        # A sor végétől bontunk, mert a leírás maga is tartalmazhat számokat.
        if (
            len(tokens) >= 10
            and _is_number_token(tokens[-1])
            and _is_number_token(tokens[-2])
            and _is_number_token(tokens[-4])
            and re.fullmatch(r"[A-Za-z0-9]{1,8}", tokens[-3])
        ):
            if len(tokens) >= 14 and all(_is_integer_token(tokens[idx]) for idx in (-5, -6, -7)):
                description = " ".join(tokens[2:-7]).strip()
                if not description:
                    continue
                items.append(
                    InvoiceItem(
                        row_no=tokens[0],
                        article_code=tokens[1],
                        description=description,
                        pallet_qty=tokens[-7],
                        package_qty=tokens[-6],
                        pcs_total=tokens[-5],
                        total_qty=tokens[-4],
                        unit=tokens[-3],
                        unit_price=tokens[-2],
                        net_value=tokens[-1],
                    )
                )
                continue

            description = " ".join(tokens[2:-5]).strip()
            if description:
                items.append(
                    InvoiceItem(
                        row_no=tokens[0],
                        article_code=tokens[1],
                        description=description,
                        total_qty=tokens[-4],
                        unit=tokens[-3],
                        unit_price=tokens[-2],
                        net_value=tokens[-1],
                    )
                )
                continue

        full_match = ITEM_PATTERN_FULL.match(line)
        if full_match:
            row_no, code, desc, pallet, package_qty, pcs, qty, unit, unit_price, net_value = full_match.groups()
            items.append(
                InvoiceItem(
                    row_no=row_no,
                    article_code=code,
                    description=_clean_spaces(desc),
                    pallet_qty=pallet,
                    package_qty=package_qty,
                    pcs_total=pcs,
                    total_qty=qty,
                    unit=unit,
                    unit_price=unit_price,
                    net_value=net_value,
                )
            )
            continue

        simple_match = ITEM_PATTERN_SIMPLE.match(line)
        if simple_match:
            row_no, code, desc, qty, unit, unit_price, net_value = simple_match.groups()
            items.append(
                InvoiceItem(
                    row_no=row_no,
                    article_code=code,
                    description=_clean_spaces(desc),
                    total_qty=qty,
                    unit=unit,
                    unit_price=unit_price,
                    net_value=net_value,
                )
            )

    return items


def _detect_invoice_profile(lines: list[str], text: str) -> str:
    upper_text = text.upper()
    if "KASTAMONU" in upper_text:
        return "kastamonu"

    krono_hits = 0
    for marker in ("KRONOSPAN", "DESPATCH ADDRESS", "SPLIT_PDF_MARK", "PAYMENT DUE", "DELIVERY NOTE NO."):
        if marker in upper_text:
            krono_hits += 1
    if krono_hits >= 2:
        return "kronospan"

    if ("DIVIAN-MEGA KFT" in upper_text or "/DIVI" in upper_text) and (
        "SZÁMLA SZÁMA" in upper_text or "ÁRUÉRTÉK" in upper_text or "TRAILER:" in upper_text
    ):
        return "divian"

    return "generic"


def _extract_decimal_from_token(token: str) -> str:
    match = re.search(r"-?\d{1,3}(?:\.\d{3})*,\d{2}", token)
    if match:
        return match.group(0)
    match = re.search(r"-?\d+,\d{2}", token)
    if match:
        return match.group(0)
    return ""


def _infer_unit_from_line(line: str) -> str:
    upper = line.upper()
    if "LFM" in upper:
        return "lfm"
    if "M2" in upper:
        return "m2"
    if "PCS" in upper:
        return "pcs"
    return ""


def _parse_kronospan_items(lines: list[str], total_net_fallback: str = "") -> list[InvoiceItem]:
    items: list[InvoiceItem] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        start_match = re.match(r"^(\d{3})\s+(.+)$", line)
        if not start_match:
            i += 1
            continue

        upper_line = line.upper()
        if not any(token in upper_line for token in ("P2EN", "WORKTOP", "SPLASHBACK", "MF PB", "VP P2")):
            i += 1
            continue

        kronospan_marker = ""
        if "SPLASHBACK" in upper_line:
            kronospan_marker = "SPLASHBACK"
        elif "WORKTOP" in upper_line or "WORK TOP" in upper_line or "KITCHEN TOP" in upper_line:
            kronospan_marker = "WORKTOP"
        elif "MF PB" in upper_line:
            kronospan_marker = "MF PB"
        elif "VP P2" in upper_line:
            kronospan_marker = "VP P2"
        elif "P2EN" in upper_line:
            kronospan_marker = "P2EN"

        item = InvoiceItem(row_no=str(len(items) + 1))
        position_code = start_match.group(1)
        payload = start_match.group(2)
        item.unit = _infer_unit_from_line(line)

        payload_tokens = payload.split()
        comma_tokens = [token for token in payload_tokens if "," in token]
        if comma_tokens:
            item.net_value = _extract_decimal_from_token(comma_tokens[0])
        if len(comma_tokens) > 1:
            item.unit_price = _extract_decimal_from_token(comma_tokens[1])

        code_match = re.search(r"\b([A-Z]{1,6}\d[A-Z0-9]{3,})\b", payload)
        if code_match:
            item.article_code = code_match.group(1)
        else:
            item.article_code = position_code

        description_lines: list[str] = []
        quantity_line = ""
        code_line = ""
        packs_line = ""
        pcs_line = ""

        j = i + 1
        while j < len(lines):
            next_line = lines[j]
            if re.match(r"^\d{3}\s+", next_line):
                break
            if re.match(r"^T\s*o\s*t\s*a\s*l:", next_line, re.IGNORECASE):
                break
            if re.fullmatch(r"\d+\s+\d+/", next_line):
                break
            if "SPLIT_PDF_MARK" in next_line.upper():
                j += 1
                continue
            if "C A R R Y" in next_line.upper() or "CARRY" in next_line.upper():
                break
            if next_line.upper().startswith("COUNTRY OF ORIGIN") or next_line.upper().startswith("CUSTOM TARIFF"):
                j += 1
                continue

            if "/" in next_line and "HTTP" not in next_line.upper():
                description_lines.append(next_line)
            elif re.fullmatch(r"-?[0-9][0-9.,]*", next_line):
                if not quantity_line:
                    quantity_line = next_line
            elif re.fullmatch(r"\d+\s+\d+", next_line):
                pcs_line = next_line
            elif re.search(r"PACK\(S\)", next_line, re.IGNORECASE):
                packs_line = next_line
            elif re.fullmatch(r"(?=.*[A-Z])[0-9A-Z ]{6,}", next_line):
                code_line = next_line

            j += 1

        if quantity_line:
            item.total_qty = quantity_line

        if code_line:
            refined_code_match = re.search(r"\b([A-Z]{1,6}\d[A-Z0-9]{2,}|\d{4})\b", code_line)
            if refined_code_match:
                item.article_code = refined_code_match.group(1)

        if description_lines:
            description_parts = description_lines + ([code_line] if code_line else [])
            description_text = " | ".join(description_parts)
            if kronospan_marker and kronospan_marker not in description_text.upper():
                description_text = f"{kronospan_marker} | {description_text}"
            item.description = description_text
        else:
            item.description = payload

        if packs_line:
            packs_match = re.search(r"(\d+)\s*Pack\(s\)", packs_line, re.IGNORECASE)
            if packs_match:
                item.package_qty = packs_match.group(1)

        if pcs_line:
            parts = pcs_line.split()
            if len(parts) == 2:
                if not item.package_qty:
                    item.package_qty = parts[0]
                item.pcs_total = parts[1]

        if not item.net_value and total_net_fallback and len(items) == 0:
            item.net_value = total_net_fallback

        if item.total_qty and item.net_value and not item.unit_price:
            quantity_value = _parse_eu_number(item.total_qty)
            net_value_num = _parse_eu_number(item.net_value)
            if quantity_value and net_value_num and quantity_value > 0:
                item.unit_price = _format_eu_number(net_value_num / quantity_value, 2)

        items.append(item)
        i = j

    return items


def _parse_kastamonu_or_generic_invoice_data(lines: list[str]) -> InvoiceData:
    normalized_text = "\n".join(lines)
    profile = "kastamonu" if "KASTAMONU" in normalized_text.upper() else "generic"
    data = InvoiceData(invoice_profile=profile)

    data.supplier_lines = _extract_block(lines, r"^(SELLER|SUPPLIER)\b", [r"^INVOICE\b", r"^DATE\b"])
    data.buyer_lines = _extract_block(
        lines,
        r"^(BUYER|CUSTOMER|BILL TO)\b",
        [r"^CONSIGNEE\b", r"^DELIVERY TERM\b", r"^NR\.?$", r"^ARTICLE\b"],
    )

    data.invoice_number = _match_first(
        normalized_text,
        [
            r"DATE\s*:\s*[0-9./-]+\s*NO\s*:\s*([A-Z0-9/\-]+)",
            r"INVOICE\s*(?:NO|NUMBER|#)\s*[:\-]?\s*([A-Z0-9/\-]+)",
            r"DOC\.?\s*NO\.?\s*[:\-]?\s*([A-Z0-9/\-]+)",
        ],
    )
    data.invoice_date = _match_first(
        normalized_text,
        [
            r"\bDATE\s*:\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
            r"INVOICE\s*DATE\s*[:\-]?\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
        ],
    )
    data.due_date = _match_first(normalized_text, [r"DUE\s*DATE\s*:\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})"])
    data.payment_method = _match_first(normalized_text, [r"PAYMENT\s*METHOD\s*:\s*(.+)"])
    data.payment_term = _match_first(normalized_text, [r"PAYMENT\s*TERM\s*:\s*(.+)"])
    data.delivery_term = _match_first(normalized_text, [r"DELIVERY\s*TERM\s*:\s*(.+)"])
    data.transport_mode = _match_first(normalized_text, [r"MEAN\s*OF\s*TRANSPORT\s*:\s*(.+)"])
    data.order_confirmation_no = _match_first(normalized_text, [r"ORDER\s*CONFIRMATION\s*NO\s*:\s*([A-Z0-9#/\-]+)"])
    data.client_ref_no = _match_first(normalized_text, [r"CLIENT'?S\s*REF\s*NO\s*:\s*(.+)"])
    data.delivery_note_no = _match_first(normalized_text, [r"DELIVERY\s*NOTE\s*NO\s*:\s*([A-Z0-9#/\-]+)"])
    data.truck_number = _match_first(normalized_text, [r"TRUCK\s*NUMBER\s*:\s*([A-Z0-9/\- ]+)"])
    data.currency = _match_first(
        normalized_text,
        [
            r"TOTAL\s*\(([A-Z]{3})\)",
            r"VALUE\s*\(([A-Z]{3})\)",
            r"PRICE/UM\s*\(([A-Z]{3})\)",
            r"CURRENCY\s*:\s*([A-Z]{3})",
        ],
    )

    data.total_net = _match_first(
        normalized_text,
        [
            r"^TOTAL\s+\d+\s+\d+\s+VALUE\s*\([A-Z]{3}\)\s*([0-9][0-9.,]*)\s*$",
            r"^TOTAL\s+VALUE\s*\([A-Z]{3}\)\s*([0-9][0-9.,]*)\s*$",
            r"NET\s*(?:VALUE|AMOUNT)\s*[:\-]?\s*([0-9][0-9.,]*)",
        ],
    )
    data.total_gross = _match_first(
        normalized_text,
        [
            r"^TOTAL\s*\([A-Z]{3}\)\s*([0-9][0-9.,]*)\s*$",
            r"GROSS\s*(?:VALUE|AMOUNT|TOTAL)\s*[:\-]?\s*([0-9][0-9.,]*)",
        ],
    )
    data.total_m2 = _match_first(normalized_text, [r"TOTAL\s*M2\s*:\s*([0-9][0-9.,]*)"])
    data.total_m3 = _match_first(normalized_text, [r"TOTAL\s*M3\s*:\s*([0-9][0-9.,]*)"])
    data.total_net_weight = _match_first(normalized_text, [r"TOTAL\s*NET\s*WEIGHT\s*:\s*([0-9][0-9.,]*)\s*KG"])
    data.total_gross_weight = _match_first(normalized_text, [r"TOTAL\s*GROSS\s*WEIGHT\s*:\s*([0-9][0-9.,]*)\s*KG"])
    data.origin_country = _match_first(
        normalized_text,
        [r"ORIGIN\s*OF\s*THE\s*GOODS\s*:\s*(.+)", r"COUNTRY\s*OF\s*ORIGIN\s*:\s*(.+)"],
    )

    for idx, line in enumerate(lines):
        vat_match = re.search(r"VAT\(([\d.,]+)%\)\s*([0-9][0-9.,]*)?$", line, re.IGNORECASE)
        if not vat_match:
            continue

        rate = vat_match.group(1).replace(",", ".").strip()
        amount = vat_match.group(2) or ""
        if not amount and idx + 1 < len(lines) and re.fullmatch(r"[0-9][0-9.,]*", lines[idx + 1]):
            amount = lines[idx + 1]
        if not amount:
            amount = "0,00"

        if rate == "0":
            data.vat_0 = amount
        elif rate == "19":
            data.vat_19 = amount

    if not data.vat_0:
        data.vat_0 = _match_first(normalized_text, [r"VAT\(?0%?\)?\s*[:\-]?\s*([0-9][0-9.,]*)"])
    if not data.vat_19:
        data.vat_19 = _match_first(normalized_text, [r"VAT\(?19%?\)?\s*[:\-]?\s*([0-9][0-9.,]*)"])

    data.items = _parse_items(lines)
    if data.supplier_lines:
        data.supplier_name = data.supplier_lines[0]
    return data


def _parse_kronospan_invoice_data(lines: list[str], text: str) -> InvoiceData:
    normalized_text = "\n".join(lines)
    data = InvoiceData(invoice_profile="kronospan", supplier_name="KRONOSPAN, s.r.o.")

    data.invoice_number = _match_first(normalized_text, [r"DELIVERY\s*NOTE\s*NO\.?\s*[:\-]?\s*([A-Z0-9/\-]+)"])
    if not data.invoice_number:
        idx = _find_index(lines, r"^Invoice number$")
        if idx != -1:
            for candidate in lines[idx + 1 : idx + 12]:
                if re.fullmatch(r"\d{4,}", candidate):
                    data.invoice_number = candidate
                    break

    data.invoice_date = _match_first(
        normalized_text,
        [
            r"DATE\s*OF\s*INVOICE\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
            r"\bDate\b[\s\S]{0,80}?([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
        ],
    )
    data.due_date = _match_first(
        normalized_text,
        [r"PAYMENT\s*DUE\s*:?\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})"],
    )

    payment_idx = _find_index(lines, r"^Payment Terms")
    if payment_idx != -1 and payment_idx + 1 < len(lines):
        data.payment_term = lines[payment_idx + 1]

    data.delivery_term = _match_first(
        normalized_text,
        [r"((?:DAP|CPT|EXW|FCA|CIF|FOB)\s+[A-Za-z0-9 .\-]+)", r"TERMS\s*OF\s*DEL\.?\s*[:\-]?\s*(.+)"],
    )
    data.payment_method = "Banki átutalás"
    data.truck_number = _match_first(normalized_text, [r"TRAILER\s*:\s*([A-Z0-9/\- ]+)"])
    data.delivery_note_no = _match_first(normalized_text, [r"DELIVERY\s*NOTE\s*NO\.?\s*([A-Z0-9/\-]+)"])

    order_idx = _find_index(lines, r"^Order Number$")
    if order_idx != -1:
        strict_match = ""
        for candidate in lines[order_idx + 1 : order_idx + 10]:
            if re.fullmatch(r"\d{5,}", candidate):
                strict_match = candidate
                break
        if strict_match:
            data.order_confirmation_no = strict_match
        else:
            for candidate in lines[order_idx + 1 : order_idx + 10]:
                if re.fullmatch(r"[A-Z0-9/\-]{4,}", candidate) and not re.fullmatch(
                    r"\d{1,2}\.\d{1,2}\.\d{2,4}",
                    candidate,
                ):
                    data.order_confirmation_no = candidate
                    break

    ref_idx = _find_index(lines, r"^Your Reference$")
    if ref_idx != -1:
        for candidate in lines[ref_idx + 1 : ref_idx + 8]:
            if "/" in candidate and "ORDER DATE" not in candidate.upper():
                data.client_ref_no = candidate
                break

    vat_no = _match_first(normalized_text, [r"VAT\s*-\s*NO\.?\s*([A-Z0-9]+?)(?:DELIVERY|\s|$)"])
    tax_idx = _find_index(lines, r"^Tax No\.")
    if tax_idx != -1:
        data.buyer_lines = [line for line in lines[max(0, tax_idx - 4) : tax_idx] if line]
    else:
        despatch_idx = _find_index(lines, r"^Despatch Address")
        if despatch_idx != -1 and despatch_idx + 1 < len(lines):
            data.buyer_lines = [lines[despatch_idx + 1]]
    if vat_no:
        data.buyer_lines.append(f"VAT NUMBER: {vat_no}")
    data.buyer_lines = list(dict.fromkeys(data.buyer_lines))

    data.supplier_lines = [data.supplier_name]
    for label in ("BANK:", "IBAN:", "SWIFT:"):
        idx = _find_index(lines, f"^{re.escape(label)}")
        if idx != -1:
            data.supplier_lines.append(lines[idx])

    data.currency = _match_first(
        normalized_text,
        [
            r"\b(EUR)\s*[-0-9.,]+\s*VALUE\s*OF\s*GOODS",
            r"\b(EUR)\s*[-0-9.,]+\s*TOTAL\s*AMOUNT",
            r"\b(EUR)\b",
        ],
    )
    data.total_net = _match_first(normalized_text, [r"EUR\s*([-0-9.,]+)\s*VALUE\s*OF\s*GOODS"])
    data.total_gross = _match_first(normalized_text, [r"EUR\s*([-0-9.,]+)\s*TOTAL\s*AMOUNT"])

    discount_match = re.search(r"EUR\s*([-0-9.,]+)\s*([0-9]+,[0-9]{2})?\s*DISCOUNT\s*%", normalized_text, re.IGNORECASE)
    if discount_match:
        discount_blob = (discount_match.group(1) or "").strip()
        percent = (discount_match.group(2) or "").strip()
        split_match = re.fullmatch(r"(-?[0-9.]+,[0-9]{2})([0-9]+,[0-9]{2})", discount_blob)
        if split_match and not percent:
            data.discount_amount = split_match.group(1)
            data.discount_percent = split_match.group(2)
        else:
            data.discount_amount = discount_blob
            data.discount_percent = percent

    totals_idx = _find_index(lines, r"^T\s*o\s*t\s*a\s*l:")
    if totals_idx != -1:
        totals_line = lines[totals_idx]
        m_pcs = re.search(r"pcs\.\s*:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        m_m2 = re.search(r"m2\s*:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        m_m3 = re.search(r"m3\s*:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        m_gross_weight = re.search(r"gross\s*to\s*:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        if m_pcs:
            data.total_pcs = m_pcs.group(1)
        if m_m2:
            data.total_m2 = m_m2.group(1)
        if m_m3:
            data.total_m3 = m_m3.group(1)
        if m_gross_weight:
            data.total_gross_weight = _normalize_kronospan_weight(m_gross_weight.group(1))

    if not data.total_m2:
        data.total_m2 = _match_first(normalized_text, [r"\bm2\s*:\s*([0-9][0-9.,]*)"])
    if not data.total_m3:
        data.total_m3 = _match_first(normalized_text, [r"\bm3\s*:\s*([0-9][0-9.,]*)"])
    data.origin_country = _match_first(normalized_text, [r"COUNTRY\s*OF\s*ORIGIN\s*:\s*([A-Z]{2,})"])

    if "VAT EXEMPT" in normalized_text.upper():
        data.vat_0 = "0,00"
        data.vat_19 = "0,00"

    data.items = _parse_kronospan_items(lines, total_net_fallback=data.total_net)
    if data.total_pcs and data.items:
        has_any_pcs = any(item.pcs_total for item in data.items)
        if not has_any_pcs and len(data.items) == 1:
            data.items[0].pcs_total = data.total_pcs

    return data


def _parse_divian_items(lines: list[str], total_net_fallback: str = "") -> list[InvoiceItem]:
    items: list[InvoiceItem] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        start_match = re.match(r"^(\d{3})\s+(.+)$", line)
        if not start_match:
            i += 1
            continue

        upper_line = line.upper()
        if "Á T V I T E L" in upper_line or "ÁT VITEL" in upper_line:
            i += 1
            continue
        if "STCK" not in upper_line and "M2" not in upper_line:
            i += 1
            continue

        item = InvoiceItem(row_no=str(len(items) + 1))
        payload = start_match.group(2)
        item.article_code = start_match.group(1)

        quantity_match = re.search(r"\d{1,3}(?:\.\d{3})*,\d{2}", line)
        if quantity_match:
            item.total_qty = quantity_match.group(0)
        if "M2" in upper_line:
            item.unit = "m2"
        elif "STCK" in upper_line:
            item.unit = "stck"

        description_parts: list[str] = []
        base_description = re.sub(r"\d{1,3}(?:\.\d{3})*,\d{2}.*$", "", payload).strip()
        if base_description:
            description_parts.append(base_description)

        j = i + 1
        while j < len(lines):
            next_line = lines[j]
            upper_next = next_line.upper()

            if re.match(r"^\d{3}\s+", next_line):
                break
            if re.search(r"nettó\s*to:", next_line, re.IGNORECASE):
                break
            if "Á T V I T E L" in upper_next or "ÁT VITEL" in upper_next:
                break
            if upper_next.startswith("MINDEN TÉTEL") or upper_next.startswith("A KITERJESZTETT GYÁRTÓI"):
                break

            if upper_next.startswith("EAN:") or upper_next.startswith("RÉSZSZ.:"):
                j += 1
                continue
            if upper_next.startswith("SZÁRMAZÁSI ORSZÁG") or upper_next.startswith("VÁMTARIFASZÁM"):
                j += 1
                continue

            if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})*,\d{2}", next_line):
                if not item.net_value:
                    item.net_value = next_line
                j += 1
                continue

            article_match = re.match(r"^(\d{4})\s+([A-Z0-9]{2,})$", next_line, re.IGNORECASE)
            if article_match:
                item.article_code = article_match.group(1)
                j += 1
                continue

            pcs_match = re.fullmatch(r"(\d+)\s+([0-9.]+)", next_line)
            if pcs_match:
                item.package_qty = pcs_match.group(1)
                item.pcs_total = pcs_match.group(2)
                j += 1
                continue

            package_match = re.search(
                r"(\d+)\s*csomag\(ok\)\s*a\s*([0-9.]+)\s*darab",
                next_line,
                re.IGNORECASE,
            )
            if package_match:
                item.package_qty = package_match.group(1)
                if not item.pcs_total:
                    try:
                        packages = int(package_match.group(1))
                        per_package = int(package_match.group(2).replace(".", ""))
                        item.pcs_total = str(packages * per_package)
                    except ValueError:
                        pass
                j += 1
                continue

            if "/" in next_line or re.search(r"[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű]{3,}", next_line):
                description_parts.append(next_line)

            j += 1

        unique_descriptions: list[str] = []
        for part in description_parts:
            cleaned_part = _fix_hungarian_mojibake(_clean_spaces(part))
            if cleaned_part and cleaned_part not in unique_descriptions:
                unique_descriptions.append(cleaned_part)

        if unique_descriptions:
            item.description = " | ".join(unique_descriptions[:3])
        else:
            item.description = _fix_hungarian_mojibake(_clean_spaces(payload))

        if not item.net_value and total_net_fallback and not items:
            item.net_value = total_net_fallback

        items.append(item)
        i = j

    return items


def _parse_divian_invoice_data(lines: list[str], text: str) -> InvoiceData:
    normalized_text = "\n".join(lines)
    data = InvoiceData(invoice_profile="divian")

    data.invoice_number = _match_first(
        normalized_text,
        [
            r"Számla\s*száma[\s\S]{0,120}?(\d{5,})",
            r"\b(\d{5,}/DIVI\d+)\b",
        ],
    )
    data.invoice_date = _match_first(
        normalized_text,
        [
            r"számla\s*dátuma\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
            r"Kiállítás\s*dátuma[\s\S]{0,80}?([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
        ],
    )
    data.order_confirmation_no = _match_first(
        normalized_text,
        [
            r"\b(WO\d{4,})\b",
            r"Rendelésszám[\s\S]{0,80}?([A-Z0-9/\-]{4,})",
        ],
    )
    data.delivery_note_no = _match_first(normalized_text, [r"Út\s*száma\s*([A-Z0-9/\-]+)"])
    data.truck_number = _match_first(normalized_text, [r"Trailer\s*:\s*([A-Z0-9/\- ]+)"])
    data.delivery_term = _match_first(
        normalized_text,
        [r"\b((?:DAP|CPT|EXW|FCA|CIF|FOB)\s+[A-Za-z0-9 .\-]+)\b"],
    )

    payment_idx = _find_index(lines, r"^Fizetési feltétel:?$")
    if payment_idx != -1 and payment_idx + 1 < len(lines):
        payment_value = _fix_hungarian_mojibake(lines[payment_idx + 1])
        data.payment_term = payment_value
        data.payment_method = payment_value

    data.currency = _match_first(
        normalized_text,
        [
            r"\b(EUR)\s*[0-9][0-9.,]*\s*Áruérték",
            r"\b(EUR)\b",
        ],
    )
    data.total_net = _match_first(normalized_text, [r"\bEUR\s*([0-9][0-9.]*,[0-9]{2})\s*Áruérték"])
    data.total_gross = _match_first(normalized_text, [r"\bEUR\s*([0-9][0-9.]*,[0-9]{2})\s*Végső\s*összeg"])

    vat_match = re.search(
        r"\bEUR\s*([0-9][0-9.]*,[0-9]{2})\s*([0-9]{1,2},[0-9]{2})\s*ÁFA",
        normalized_text,
        re.IGNORECASE,
    )
    if vat_match:
        vat_amount = vat_match.group(1)
        vat_rate = vat_match.group(2).replace(",", ".")
        if vat_rate.startswith("0"):
            data.vat_0 = vat_amount
        else:
            data.vat_19 = vat_amount

    totals_line = ""
    for line in lines:
        if re.search(r"nettó\s*to:", line, re.IGNORECASE) and re.search(r"bruttó\s*to:", line, re.IGNORECASE):
            totals_line = line
            break

    if totals_line:
        net_weight_match = re.search(r"nettó\s*to:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        gross_weight_match = re.search(r"bruttó\s*to:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        pcs_match = re.search(r"Stck:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        m2_match = re.search(r"m2:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        m3_match = re.search(r"m3:\s*([0-9][0-9.,]*)", totals_line, re.IGNORECASE)
        if net_weight_match:
            data.total_net_weight = net_weight_match.group(1)
        if gross_weight_match:
            data.total_gross_weight = gross_weight_match.group(1)
        if pcs_match:
            data.total_pcs = pcs_match.group(1)
        if m2_match:
            data.total_m2 = m2_match.group(1)
        if m3_match:
            data.total_m3 = m3_match.group(1)

    data.origin_country = _match_first(normalized_text, [r"Származási ország\s*:\s*([A-Z]{2,})"])

    company_blocks: list[list[str]] = []
    seller_candidates: list[tuple[int, list[str]]] = []
    for idx, line in enumerate(lines):
        if "DIVIAN-MEGA KFT" not in line.upper():
            continue

        buyer_block = [line]
        for candidate in lines[idx + 1 : idx + 6]:
            upper_candidate = candidate.upper()
            if upper_candidate.startswith("RENDELÉSI ADATOK") or upper_candidate.startswith("ADÓSZÁM"):
                break
            if upper_candidate.startswith("CÉGJEGYZÉKSZÁM") or upper_candidate.startswith("EUR "):
                break
            if upper_candidate.startswith("Á T V I T E L") or upper_candidate.startswith("MINDEN TÉTEL"):
                break
            if upper_candidate.startswith("FIZETÉSI FELTÉTEL"):
                break
            buyer_block.append(candidate)
            if len(buyer_block) >= 3:
                break
        if len(buyer_block) >= 2:
            fixed_buyer_block = [_fix_hungarian_mojibake(entry) for entry in buyer_block]
            company_blocks.append(list(dict.fromkeys(fixed_buyer_block)))

        seller_block = [line]
        seller_score = 0
        for candidate in lines[idx + 1 : idx + 9]:
            upper_candidate = candidate.upper()
            if upper_candidate.startswith("EUR ") or upper_candidate.startswith("FIZETÉSI FELTÉTEL"):
                break
            if upper_candidate.startswith("MNB ÁRFOLYAM") or upper_candidate.startswith("Ö S S Z E S E N"):
                break
            if upper_candidate.startswith("Á T V I T E L") or upper_candidate.startswith("MINDEN TÉTEL"):
                break
            if upper_candidate.startswith("SZÁMLA") or upper_candidate.startswith("OLDAL"):
                break
            seller_block.append(candidate)
            if upper_candidate.startswith("ADÓSZÁM"):
                seller_score += 3
            elif upper_candidate.startswith("CÉGJEGYZÉKSZÁM"):
                seller_score += 2
            elif re.search(r"\b\d{4}\s+[A-ZÁÉÍÓÖŐÚÜŰ]", upper_candidate):
                seller_score += 1

        fixed_seller_block = [_fix_hungarian_mojibake(entry) for entry in seller_block if _clean_spaces(entry)]
        if len(fixed_seller_block) >= 2:
            deduped_seller_block = list(dict.fromkeys(fixed_seller_block[:5]))
            seller_candidates.append((seller_score + len(deduped_seller_block), deduped_seller_block))

    if company_blocks:
        preferred_block = next((b for b in company_blocks if re.search(r"\b\d{4}\b", " ".join(b))), company_blocks[0])
        data.buyer_lines = preferred_block

    if seller_candidates:
        seller_candidates.sort(key=lambda x: x[0], reverse=True)
        data.supplier_lines = seller_candidates[0][1]
        data.supplier_name = data.supplier_lines[0]
    elif company_blocks:
        data.supplier_lines = company_blocks[0]
        data.supplier_name = data.supplier_lines[0]

    data.items = _parse_divian_items(lines, total_net_fallback=data.total_net)
    return data


def parse_invoice_data(text: str) -> InvoiceData:
    lines = [_clean_spaces(raw) for raw in text.splitlines() if _clean_spaces(raw)]
    profile = _detect_invoice_profile(lines, text)
    if profile == "kronospan":
        return _parse_kronospan_invoice_data(lines, text)
    if profile == "divian":
        return _parse_divian_invoice_data(lines, text)
    return _parse_kastamonu_or_generic_invoice_data(lines)


def parse_fields(text: str) -> dict[str, str]:
    data = parse_invoice_data(text)
    return {
        "invoice_number": data.invoice_number,
        "invoice_date": data.invoice_date,
        "supplier": " | ".join(data.supplier_lines),
        "customer": " | ".join(data.buyer_lines),
        "total_amount": data.total_gross or data.total_net,
        "vat_amount": data.vat_19 or data.vat_0,
    }


def _to_invoice_data(parsed: InvoiceData | dict[str, str]) -> InvoiceData:
    if isinstance(parsed, InvoiceData):
        return parsed

    data = InvoiceData()
    data.invoice_profile = parsed.get("invoice_profile", "")
    data.supplier_name = parsed.get("supplier_name", "")
    data.invoice_number = parsed.get("invoice_number", "")
    data.invoice_date = parsed.get("invoice_date", "")
    supplier = parsed.get("supplier", "")
    customer = parsed.get("customer", "")
    data.supplier_lines = [line.strip() for line in supplier.split("|") if line.strip()]
    data.buyer_lines = [line.strip() for line in customer.split("|") if line.strip()]
    data.total_gross = parsed.get("total_amount", "")
    data.vat_19 = parsed.get("vat_amount", "")
    return data


def _html_text(value: str) -> str:
    return html.escape(_value_or_default(value))


def _html_party(lines: list[str]) -> str:
    if not lines:
        return html.escape(NO_DATA)
    return "<br>".join(html.escape(_clean_spaces(line)) for line in lines if _clean_spaces(line))


def _html_table_rows(rows: list[tuple[str, str]]) -> str:
    return "".join(f"<tr><th>{html.escape(label)}</th><td>{_html_text(value)}</td></tr>" for label, value in rows)


def _non_empty_rows(rows: list[tuple[str, str]], keep_labels: set[str] | None = None) -> list[tuple[str, str]]:
    if keep_labels is None:
        keep_labels = set()
    filtered: list[tuple[str, str]] = []
    for label, value in rows:
        if label in keep_labels:
            filtered.append((label, value))
            continue
        if _clean_spaces(value):
            filtered.append((label, value))
    return filtered


def _split_vehicle_plates(raw_value: str) -> tuple[str, str]:
    cleaned = _clean_spaces(raw_value)
    if not cleaned:
        return "", ""

    direct_parts = [part.strip() for part in re.split(r"\s*/\s*|\s*;\s*|\s+\|\s+", cleaned) if part.strip()]
    if len(direct_parts) >= 2:
        return direct_parts[0], direct_parts[1]

    plate_like = re.findall(r"\b[A-Z]{1,4}\d{1,4}[A-Z]{0,3}\b", cleaned.upper())
    if len(plate_like) >= 2:
        return plate_like[0], plate_like[1]

    tokens = cleaned.split()
    if len(tokens) >= 2:
        return tokens[0], tokens[1]

    return cleaned, ""


def _is_takarotabla_item(description: str) -> bool:
    normalized = _fix_hungarian_mojibake(_clean_spaces(description)).upper()
    return normalized.startswith("PAL BRUT")


def _detect_product_type(description: str, article_code: str = "", invoice_profile: str = "") -> str:
    normalized_description = _fix_hungarian_mojibake(_clean_spaces(description)).upper()
    normalized_code = _fix_hungarian_mojibake(_clean_spaces(article_code)).upper()
    normalized_profile = _fix_hungarian_mojibake(_clean_spaces(invoice_profile)).lower()
    text = f"{normalized_description} {normalized_code}".upper()
    description_prefix = normalized_description.split(" ", 1)[0] if normalized_description else ""
    code_prefix = normalized_code.split(" ", 1)[0] if normalized_code else ""

    if _is_takarotabla_item(description):
        return "takarótábla"
    if normalized_profile == "kronospan":
        if "WORKTOP" in text or "WORK TOP" in text or "KITCHEN TOP" in text:
            return "munkalap"
        if "SPLASHBACK" in text:
            return "falipanel"
        if "MF PB" in text or "VP P2" in text or "P2EN" in text:
            return "bútorlap"
    if description_prefix.startswith("SP") or code_prefix.startswith("SP"):
        return "falipanel"
    if (
        description_prefix.startswith("WT")
        or description_prefix.startswith("NT")
        or code_prefix.startswith("WT")
        or code_prefix.startswith("NT")
    ):
        return "munkalap"
    if description_prefix.startswith("NFC") or code_prefix.startswith("NFC"):
        return "bútorlap"
    if "EVOGLOSS" in text or "EVGLS" in text:
        return "evogloss lap"
    if "MUNKALAP" in text or "WORKTOP" in text or "WORK TOP" in text or "KITCHEN TOP" in text:
        return "munkalap"
    if (
        "HÁTFAL" in text
        or "HATFAL" in text
        or "HDF THIN" in text
        or "THIN PLUS" in text
        or "BACKWALL" in text
        or "BACK WALL" in text
        or "BACKPANEL" in text
        or "BACK PANEL" in text
    ):
        return "hátfal"
    if "FALIPANEL" in text or ("WALL" in text and "PANEL" in text):
        return "falipanel"
    return "bútorlap"


def _render_invoice_item_row(item: InvoiceItem, invoice_profile: str = "") -> str:
    product_type = _detect_product_type(item.description, item.article_code, invoice_profile=invoice_profile)
    missing_placeholder = "-" if product_type == "takarótábla" else NO_DATA
    return (
        "<tr>"
        f"<td class='center'>{html.escape(_item_value_or_default(item.row_no, missing_placeholder))}</td>"
        f"<td class='center'>{html.escape(_item_value_or_default(item.article_code, missing_placeholder))}</td>"
        f"<td class='center'>{html.escape(product_type)}</td>"
        f"<td>{html.escape(_item_value_or_default(item.description, missing_placeholder))}</td>"
        f"<td class='center'>{html.escape(_item_value_or_default(item.package_qty, missing_placeholder))}</td>"
        f"<td class='center'>{html.escape(_item_value_or_default(item.pcs_total, missing_placeholder))}</td>"
        f"<td class='right'>{html.escape(_item_value_or_default(item.total_qty, missing_placeholder))}</td>"
        f"<td class='center'>{html.escape(_item_value_or_default(item.unit, missing_placeholder))}</td>"
        f"<td class='right'>{html.escape(_item_value_or_default(item.unit_price, missing_placeholder))}</td>"
        f"<td class='right'>{html.escape(_item_value_or_default(item.net_value, missing_placeholder))}</td>"
        "</tr>"
    )


def create_printable_html(parsed: InvoiceData | dict[str, str], source_filename: str = "") -> bytes:
    data = _to_invoice_data(parsed)
    truck_plate, trailer_plate = _split_vehicle_plates(data.truck_number)
    vehicle_plates = ""
    if truck_plate and trailer_plate:
        vehicle_plates = f"{truck_plate} - {trailer_plate}"
    elif truck_plate:
        vehicle_plates = truck_plate
    elif trailer_plate:
        vehicle_plates = trailer_plate

    rounded_net_weight = _format_rounded_weight(data.total_net_weight) if data.total_net_weight else ""
    rounded_gross_weight = _format_rounded_weight(data.total_gross_weight) if data.total_gross_weight else ""
    invoice_date_display = _format_invoice_date(data.invoice_date)
    due_date_display = _format_invoice_date(data.due_date)
    generated_at = datetime.now().strftime("%Y.%m.%d %H:%M")
    source_label = html.escape(source_filename) if source_filename else "feltöltött PDF"
    compact_mode = len(data.items) >= 10 or (len(data.supplier_lines) + len(data.buyer_lines)) >= 12
    body_class = "compact" if compact_mode else ""
    profile_label = {
        "kastamonu": "Kastamonu sablon",
        "kronospan": "Kronospan sablon",
        "divian": "DIVI sablon",
        "generic": "Általános sablon",
        "": "Általános sablon",
    }.get(data.invoice_profile, "Általános sablon")

    info_fields = _non_empty_rows(
        [
            ("Számlaszám", data.invoice_number),
            ("Számla dátuma", invoice_date_display),
            ("Fizetési határidő", due_date_display),
            ("Fizetési mód", data.payment_method),
            ("Szállítólevél száma", data.delivery_note_no),
            ("Gépjármű azonosító", vehicle_plates),
        ],
        keep_labels={"Számlaszám", "Számla dátuma", "Gépjármű azonosító"},
    )
    info_rows = _html_table_rows(info_fields)

    discount_label = "Engedmény"
    if data.discount_percent:
        discount_label = f"Engedmény ({data.discount_percent}%)"

    summary_fields_raw: list[tuple[str, str]] = [
        ("Pénznem", data.currency),
        ("Összeg", data.total_net),
        (discount_label, data.discount_amount),
        ("Kedvezményes összeg", data.total_gross),
    ]
    summary_fields_raw.extend(
        [
            ("Nettó tömeg (kg)", rounded_net_weight),
            ("Bruttó tömeg (kg)", rounded_gross_weight),
            ("Származási ország", data.origin_country),
        ]
    )
    summary_fields = _non_empty_rows(
        summary_fields_raw,
        keep_labels={"Pénznem", "Összeg", "Kedvezményes összeg"},
    )
    summary_rows = _html_table_rows(summary_fields)

    if data.items:
        item_rows = "".join(
            _render_invoice_item_row(item, data.invoice_profile)
            for item in data.items
        )
    else:
        item_rows = "<tr><td colspan='10'>Nem sikerült tételsorokat felismerni.</td></tr>"

    page = f"""<!doctype html>
<html lang="hu">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Divian-HUB | Nyomtatható számlakivonat</title>
  <style>
    :root {{
      --bg: #061018;
      --bg-soft: #0b1a26;
      --ink: #11202b;
      --ink-deep: #08131b;
      --muted: #58717c;
      --line: #cfdee2;
      --surface: #ffffff;
      --accent: #36d7c3;
      --accent-strong: #149c90;
      --accent-soft: #e3fff8;
      --accent-warm: #c7ff7a;
      --paper: #eff5f6;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 1rem 1rem 1.25rem;
      background:
        radial-gradient(900px 360px at 0% 0%, rgba(54, 215, 195, .18), transparent 60%),
        radial-gradient(760px 320px at 100% 0%, rgba(199, 255, 122, .12), transparent 55%),
        linear-gradient(180deg, var(--bg) 0%, var(--bg-soft) 100%);
      color: var(--ink);
      font-family: "Segoe UI", Arial, sans-serif;
      line-height: 1.32;
    }}
    a {{
      color: inherit;
      text-decoration: none;
    }}
    .toolbar {{
      max-width: 210mm;
      margin: 0 auto .65rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: .45rem;
      padding: 0 .15rem;
    }}
    .toolbar-group {{
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: .45rem;
    }}
    .toolbar-note {{
      color: rgba(237, 247, 247, .72);
      font-size: .76rem;
      letter-spacing: .08em;
      text-transform: uppercase;
    }}
    .toolbar button,
    .toolbar a {{
      border: 1px solid rgba(54, 215, 195, .22);
      background: rgba(7, 17, 26, .72);
      color: #edf7f7;
      padding: .55rem .86rem;
      border-radius: 999px;
      cursor: pointer;
      font-size: .84rem;
      font-weight: 700;
      transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease, background .16s ease;
      backdrop-filter: blur(12px);
    }}
    .toolbar a {{
      color: #edf7f7;
    }}
    .toolbar button {{
      background: linear-gradient(135deg, var(--accent-warm), var(--accent));
      border-color: transparent;
      color: #041017;
    }}
    .toolbar button:hover,
    .toolbar a:hover {{
      transform: translateY(-1px);
      box-shadow: 0 10px 22px rgba(0, 0, 0, .2);
      border-color: rgba(54, 215, 195, .4);
    }}
    .sheet {{
      width: 210mm;
      min-height: 297mm;
      margin: 0 auto .8rem;
      background: var(--surface);
      padding: 8.5mm 8.5mm 8mm;
      border: 1px solid #d6e7e8;
      border-top: 6px solid var(--accent-strong);
      border-radius: 18px;
      box-shadow: 0 24px 50px rgba(0, 0, 0, .28);
      position: relative;
      overflow: hidden;
    }}
    .sheet::before {{
      content: "";
      position: absolute;
      inset: 0;
      background:
        linear-gradient(135deg, rgba(54, 215, 195, .08), transparent 28%),
        linear-gradient(180deg, transparent, rgba(54, 215, 195, .03));
      pointer-events: none;
    }}
    .head {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 1.2rem;
      border-bottom: 1px solid #d9e7e8;
      padding-bottom: .55rem;
      margin-bottom: .75rem;
      position: relative;
      z-index: 1;
    }}
    .head-copy {{
      max-width: 62%;
    }}
    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: .38rem;
      padding: .24rem .5rem;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent-strong);
      letter-spacing: .12em;
      text-transform: uppercase;
      font-size: .64rem;
      font-weight: 800;
      margin-bottom: .45rem;
    }}
    .head h1 {{
      margin: 0;
      font-size: 1.14rem;
      letter-spacing: .12px;
      color: var(--ink-deep);
    }}
    .head-copy p {{
      margin: .3rem 0 0;
      color: var(--muted);
      font-size: .78rem;
    }}
    .meta {{
      min-width: 220px;
      display: grid;
      gap: .34rem;
    }}
    .meta div {{
      padding: .44rem .58rem;
      border: 1px solid #d9e7e8;
      border-radius: 10px;
      background: linear-gradient(180deg, #fcfefe 0%, #f5fbfb 100%);
      font-size: .73rem;
      color: var(--muted);
    }}
    .meta strong {{
      display: block;
      margin-top: .08rem;
      color: var(--ink-deep);
      font-size: .82rem;
    }}
    .parties {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: .6rem;
      margin-bottom: .62rem;
      position: relative;
      z-index: 1;
    }}
    .meta-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: .5rem;
      margin-bottom: .48rem;
      align-items: start;
      position: relative;
      z-index: 1;
    }}
    .meta-card {{
      min-width: 0;
    }}
    .panel {{
      border: 1px solid #d5e5e6;
      border-radius: 12px;
      padding: .46rem .54rem;
      background: linear-gradient(180deg, #fefefe 0%, #f4fbfb 100%);
    }}
    .panel h2 {{
      margin: 0 0 .24rem 0;
      font-size: .74rem;
      color: var(--accent-strong);
      text-transform: uppercase;
      letter-spacing: .14em;
    }}
    .panel p {{
      margin: 0;
      white-space: normal;
      font-size: .8rem;
    }}
    h3 {{
      margin: .58rem 0 .24rem 0;
      font-size: .76rem;
      text-transform: uppercase;
      letter-spacing: .14em;
      color: var(--accent-strong);
      border-left: 3px solid var(--accent);
      padding-left: .42rem;
      position: relative;
      z-index: 1;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: .74rem;
      margin-bottom: .42rem;
      position: relative;
      z-index: 1;
    }}
    th,
    td {{
      border: 1px solid var(--line);
      padding: .18rem .24rem;
      vertical-align: top;
    }}
    th {{
      background: linear-gradient(180deg, #f3fefb 0%, #e9faf6 100%);
      font-weight: 700;
      text-align: left;
    }}
    .kv {{
      table-layout: fixed;
      margin-bottom: 0;
    }}
    .meta-card .kv {{
      font-size: .79rem;
    }}
    .meta-card .kv th,
    .meta-card .kv td {{
      padding: 6px;
      line-height: 1.28;
    }}
    .meta-card .kv th {{
      width: 58%;
      white-space: nowrap;
    }}
    .meta-card .kv td {{
      font-weight: 600;
    }}
    .items td:nth-child(4) {{ line-height: 1.2; }}
    .items tbody tr:nth-child(even) {{
      background: #f8fcfb;
    }}
    .center {{ text-align: center; }}
    .right {{ text-align: right; }}
    .footnote {{
      margin-top: .38rem;
      border-top: 1px dashed #b7cfd0;
      padding-top: .32rem;
      font-size: .68rem;
      color: var(--muted);
      position: relative;
      z-index: 1;
    }}
    body.compact .sheet {{
      padding: 7.8mm 8mm 7.4mm;
    }}
    body.compact .head h1 {{
      font-size: 1.02rem;
    }}
    body.compact .meta {{
      gap: .3rem;
    }}
    body.compact .meta div {{
      font-size: .7rem;
      padding: .38rem .5rem;
    }}
    body.compact .panel p {{
      font-size: .76rem;
    }}
    body.compact h3 {{
      margin: .42rem 0 .2rem 0;
      font-size: .74rem;
    }}
    body.compact table {{
      font-size: .72rem;
      margin-bottom: .34rem;
    }}
    body.compact th,
    body.compact td {{
      padding: .14rem .18rem;
    }}
    body.compact .meta-card .kv {{
      font-size: .74rem;
    }}
    body.compact .meta-card .kv th,
    body.compact .meta-card .kv td {{
      padding: 5px;
      line-height: 1.22;
    }}
    body.compact .meta-card .kv th {{
      width: 55%;
    }}
    @media (max-width: 860px) {{
      body {{
        padding: .65rem;
      }}
      .toolbar {{
        justify-content: center;
      }}
      .toolbar-note {{
        width: 100%;
        text-align: center;
      }}
      .meta-grid {{
        grid-template-columns: 1fr;
      }}
      .parties {{
        grid-template-columns: 1fr;
      }}
      .head {{
        flex-direction: column;
      }}
      .head-copy {{
        max-width: none;
      }}
      .meta {{
        width: 100%;
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}
    @page {{
      size: A4 portrait;
      margin: 6mm;
    }}
    @media print {{
      body {{
        padding: 0;
        background: #fff;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }}
      .toolbar {{ display: none; }}
      .sheet {{
        margin: 0;
        width: 100%;
        min-height: auto;
        padding: 8.8mm 9mm 8.2mm;
        border: 1px solid #d6e7e8;
        border-top: 6px solid var(--accent-strong);
        border-radius: 0;
        box-shadow: none;
        transform: none;
      }}
      a {{ color: inherit; text-decoration: none; }}
    }}
  </style>
</head>
<body class="{body_class}">
  <div class="toolbar">
    <span class="toolbar-note">Divian-HUB // nyomtatható kivonat</span>
    <div class="toolbar-group">
      <a href="/">Főoldal</a>
      <a href="{APP_ROUTE}">Új számla</a>
      <button onclick="window.print()">Nyomtatás / Mentés PDF-be</button>
    </div>
  </div>
  <main class="sheet">
    <header class="head">
      <div class="head-copy">
        <div class="eyebrow">Divian-HUB kimenet</div>
        <h1>Külföldi számla magyar fordítása</h1>
        <p>Automatikusan generált, nyomtatható kivonat egységes vállalati megjelenéssel.</p>
      </div>
      <div class="meta">
        <div>Gyártó<strong>{html.escape(data.supplier_name or NO_DATA)}</strong></div>
        <div>Sablon<strong>{profile_label}</strong></div>
        <div>Forrás<strong>{source_label}</strong></div>
        <div>Generálás<strong>{generated_at}</strong></div>
      </div>
    </header>

    <section class="parties">
      <article class="panel">
        <h2>Eladó</h2>
        <p>{_html_party(data.supplier_lines)}</p>
      </article>
      <article class="panel">
        <h2>Vevő</h2>
        <p>{_html_party(data.buyer_lines)}</p>
      </article>
    </section>

    <section class="meta-grid">
      <article class="meta-card">
        <h3>Számla adatok</h3>
        <table class="kv">
          <tbody>{info_rows}</tbody>
        </table>
      </article>
      <article class="meta-card">
        <h3>Összesítés</h3>
        <table class="kv">
          <tbody>{summary_rows}</tbody>
        </table>
      </article>
    </section>

    <h3>Tételek</h3>
    <table class="items">
      <thead>
        <tr>
          <th class="center">Ssz.</th>
          <th class="center">Cikkszám</th>
          <th class="center">Termék típus</th>
          <th>Megnevezés</th>
          <th class="center">Rakat</th>
          <th class="center">Össz. db</th>
          <th class="right">Mennyiség</th>
          <th class="center">ME</th>
          <th class="right">Egységár</th>
          <th class="right">Nettó érték</th>
        </tr>
      </thead>
      <tbody>{item_rows}</tbody>
    </table>

    <div class="footnote">
      Ez egy automatikusan generált, nyomtatható fordítási kivonat.
    </div>
  </main>
  {COMMON_SCRIPT_TAG}
</body>
</html>"""
    return page.encode("utf-8")


def render_form(message: str = "") -> bytes:
    msg_html = f'<div class="alert">{html.escape(message)}</div>' if message else ""
    page = f"""<!doctype html>
<html lang="hu">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Divian-HUB | Számla magyarító</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link
    href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;700&display=swap"
    rel="stylesheet"
  />
  <style>
    :root {{
      --bg: #040b12;
      --bg-soft: #09131c;
      --panel: rgba(8, 18, 28, 0.84);
      --panel-strong: rgba(10, 22, 33, 0.94);
      --border: rgba(84, 191, 214, 0.18);
      --line: rgba(84, 191, 214, 0.12);
      --text: #f3fbff;
      --muted: #8ea8b8;
      --accent: #43decf;
      --accent-strong: #1197a2;
      --accent-warm: #ff8b64;
      --danger-bg: rgba(88, 27, 28, 0.78);
      --danger-line: rgba(255, 139, 100, 0.34);
      --shadow: 0 28px 80px rgba(0, 0, 0, 0.42);
      --radius-xl: 30px;
      --radius-lg: 22px;
      --radius-md: 16px;
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      min-width: 320px;
      font-family: "Manrope", sans-serif;
      background:
        radial-gradient(circle at 14% 16%, rgba(67, 222, 207, 0.2), transparent 24%),
        radial-gradient(circle at 82% 10%, rgba(255, 139, 100, 0.15), transparent 18%),
        linear-gradient(180deg, var(--bg) 0%, var(--bg-soft) 100%);
      color: var(--text);
      overflow-x: hidden;
    }}
    a {{
      color: inherit;
      text-decoration: none;
    }}
    button,
    input {{
      font: inherit;
    }}
    .site {{
      position: relative;
      min-height: 100vh;
      padding: 20px 24px 36px;
    }}
    .site::before {{
      content: "";
      position: fixed;
      inset: 0;
      background-image:
        linear-gradient(rgba(84, 191, 214, 0.04) 1px, transparent 1px),
        linear-gradient(90deg, rgba(84, 191, 214, 0.04) 1px, transparent 1px);
      background-size: 72px 72px;
      mask-image: radial-gradient(circle at center, black 35%, transparent 85%);
      pointer-events: none;
      z-index: -1;
    }}
    .topbar,
    .content {{
      width: min(1080px, calc(100vw - 48px));
      margin-inline: auto;
    }}
    .topbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      padding: 16px 20px;
      background: rgba(7, 16, 24, 0.76);
      border: 1px solid var(--border);
      backdrop-filter: blur(18px);
      border-radius: 999px;
      box-shadow: var(--shadow);
    }}
    .brand {{
      display: inline-flex;
      align-items: center;
      gap: 14px;
    }}
    .brand-mark {{
      width: 16px;
      height: 16px;
      border-radius: 50%;
      background:
        radial-gradient(circle at 35% 35%, #ffffff, transparent 28%),
        radial-gradient(circle, var(--accent-warm), var(--accent-strong));
      box-shadow:
        0 0 0 8px rgba(67, 222, 207, 0.08),
        0 0 28px rgba(67, 222, 207, 0.22);
    }}
    .brand-text {{
      display: grid;
      gap: 3px;
    }}
    .brand-text strong,
    h1,
    h2,
    .surface-title strong {{
      font-family: "Space Grotesk", sans-serif;
    }}
    .brand-text strong {{
      font-size: 0.98rem;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }}
    .brand-text small {{
      color: var(--muted);
      font-size: 0.72rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .nav {{
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      justify-content: center;
      gap: 18px;
      color: var(--muted);
      font-weight: 600;
    }}
    .nav a {{
      transition: color 180ms ease;
    }}
    .nav a:hover,
    .nav a:focus-visible {{
      color: var(--text);
    }}
    .ghost-link,
    .nav-cta,
    .button,
    .primary-button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 48px;
      padding: 0 20px;
      border-radius: 999px;
      font-weight: 700;
      transition:
        transform 180ms ease,
        border-color 180ms ease,
        background 180ms ease,
        color 180ms ease;
    }}
    .ghost-link {{
      border: 1px solid var(--border);
      color: var(--text);
      background: rgba(255, 255, 255, 0.06);
    }}
    .button,
    .primary-button {{
      border: 0;
      background: linear-gradient(135deg, var(--accent-warm), var(--accent));
      color: #041017;
      cursor: pointer;
      box-shadow: 0 12px 26px rgba(67, 222, 207, 0.2);
    }}
    .nav-cta {{
      border: 0;
      background: linear-gradient(135deg, var(--accent-warm), var(--accent));
      color: #041017;
      font-weight: 800;
      box-shadow: 0 12px 26px rgba(67, 222, 207, 0.2);
    }}
    .ghost-link:hover,
    .nav-cta:hover,
    .button:hover,
    .primary-button:hover,
    .nav-cta:focus-visible {{
      transform: translateY(-2px);
    }}
    .content {{
      display: grid;
      gap: 18px;
      padding-top: 28px;
      align-items: start;
    }}
    .hero-card,
    .upload-card {{
      position: relative;
      overflow: hidden;
      background: linear-gradient(180deg, var(--panel) 0%, var(--panel-strong) 100%);
      border: 1px solid var(--border);
      border-radius: var(--radius-xl);
      box-shadow: var(--shadow);
    }}
    .hero-card::before,
    .upload-card::before {{
      content: "";
      position: absolute;
      inset: 0;
      background:
        linear-gradient(120deg, rgba(67, 222, 207, 0.12), transparent 34%),
        linear-gradient(180deg, transparent, rgba(255, 139, 100, 0.06));
      pointer-events: none;
    }}
    .hero-card {{
      padding: 26px;
    }}
    .hero-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.05fr) 240px;
      gap: 20px;
      align-items: center;
    }}
    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 9px 13px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.06);
      color: var(--accent);
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-size: 0.72rem;
    }}
    .eyebrow::before {{
      content: "";
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--accent-warm);
      box-shadow: 0 0 16px rgba(255, 142, 110, 0.45);
    }}
    h1 {{
      margin: 18px 0 14px;
      font-size: clamp(2.6rem, 5vw, 4.5rem);
      line-height: 0.94;
      letter-spacing: -0.05em;
      max-width: 9ch;
    }}
    h1 span {{
      display: block;
      color: transparent;
      background: linear-gradient(135deg, var(--accent-strong) 0%, var(--accent) 48%, var(--accent-warm) 100%);
      -webkit-background-clip: text;
      background-clip: text;
    }}
    .lead,
    .surface-title p,
    .file-state small,
    .inline-note,
    .alert {{
      color: var(--muted);
    }}
    .lead {{
      max-width: 40ch;
      font-size: 1.02rem;
      line-height: 1.7;
      margin: 0;
    }}
    .hero-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }}
    .hero-visual {{
      position: relative;
      width: 250px;
      height: 200px;
      margin-left: auto;
    }}
    .visual-doc,
    .visual-arrow,
    .visual-lang {{
      position: absolute;
    }}
    .visual-doc {{
      width: 122px;
      height: 156px;
      border-radius: 24px;
      border: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.04));
      box-shadow: 0 18px 30px rgba(0, 0, 0, 0.24);
      backdrop-filter: blur(14px);
    }}
    .visual-doc::before {{
      content: "";
      position: absolute;
      left: 14px;
      right: 14px;
      top: 18px;
      height: 10px;
      border-radius: 999px;
      background: linear-gradient(90deg, rgba(67, 222, 207, 0.6), rgba(255, 139, 100, 0.45));
    }}
    .visual-doc::after {{
      content: "";
      position: absolute;
      left: 14px;
      right: 20px;
      top: 42px;
      height: 72px;
      border-radius: 18px;
      background:
        linear-gradient(rgba(255, 255, 255, 0.14) 0 0) 0 0 / 100% 1px no-repeat,
        linear-gradient(rgba(255, 255, 255, 0.1) 0 0) 0 18px / 86% 1px no-repeat,
        linear-gradient(rgba(255, 255, 255, 0.08) 0 0) 0 36px / 92% 1px no-repeat,
        linear-gradient(rgba(255, 255, 255, 0.08) 0 0) 0 54px / 70% 1px no-repeat;
    }}
    .doc-source {{
      left: 2px;
      top: 26px;
      transform: rotate(-6deg);
    }}
    .doc-target {{
      right: 0;
      top: 18px;
      transform: rotate(6deg);
      border-color: rgba(67, 222, 207, 0.26);
    }}
    .visual-arrow {{
      left: 99px;
      top: 84px;
      width: 52px;
      height: 20px;
      border-radius: 999px;
      border: 1px solid rgba(67, 222, 207, 0.16);
      background: linear-gradient(90deg, rgba(255, 139, 100, 0.12), rgba(67, 222, 207, 0.12));
      display: grid;
      place-items: center;
      color: var(--accent);
      font-size: 1rem;
      font-weight: 700;
      backdrop-filter: blur(8px);
    }}
    .visual-lang {{
      padding: 7px 10px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.06);
      font-size: 0.7rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--text);
    }}
    .lang-source {{
      left: 0;
      top: 0;
    }}
    .lang-target {{
      right: 0;
      bottom: 0;
      color: var(--accent);
    }}
    .upload-card {{
      padding: 22px;
    }}
    .alert {{
      padding: 14px 16px;
      border-radius: var(--radius-md);
      border: 1px solid var(--danger-line);
      background: var(--danger-bg);
      line-height: 1.55;
      margin-bottom: 14px;
    }}
    .surface-title {{
      margin-bottom: 14px;
    }}
    .surface-title strong {{
      display: block;
      font-size: 1.05rem;
      margin-bottom: 4px;
    }}
    .surface-title p {{
      margin: 0;
    }}
    .upload-shell {{
      display: grid;
      gap: 14px;
    }}
    .upload-shell.is-dragover {{
      box-shadow: 0 0 0 1px rgba(69, 224, 207, 0.22) inset;
    }}
    .file-input {{
      position: absolute;
      width: 1px;
      height: 1px;
      opacity: 0;
      pointer-events: none;
    }}
    .upload-surface {{
      display: grid;
      gap: 16px;
      min-height: 188px;
      padding: 22px;
      border-radius: var(--radius-lg);
      border: 1px solid var(--line);
      background:
        radial-gradient(circle at top left, rgba(67, 222, 207, 0.08), transparent 32%),
        rgba(255, 255, 255, 0.04);
      cursor: pointer;
    }}
    .upload-top {{
      display: grid;
      grid-template-columns: 70px 1fr;
      gap: 16px;
      align-items: center;
    }}
    .upload-badge {{
      width: 70px;
      height: 70px;
      border-radius: 22px;
      display: grid;
      place-items: center;
      font-family: "Space Grotesk", sans-serif;
      font-size: 1.05rem;
      color: #041017;
      background: linear-gradient(135deg, var(--accent), var(--accent-warm));
      box-shadow: 0 16px 34px rgba(67, 222, 207, 0.18);
    }}
    .upload-copy strong {{
      display: block;
      font-size: 1.16rem;
      margin-bottom: 4px;
    }}
    .upload-copy p {{
      margin: 0;
      line-height: 1.65;
      color: var(--muted);
    }}
    .upload-rail {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      color: var(--muted);
      font-size: 0.78rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .upload-rail span {{
      color: var(--text);
    }}
    .upload-rail i {{
      width: 22px;
      height: 1px;
      background: linear-gradient(90deg, var(--accent), var(--accent-warm));
      display: block;
    }}
    .file-state {{
      padding-top: 2px;
    }}
    .file-state strong {{
      display: block;
      font-size: 0.96rem;
      margin-bottom: 4px;
    }}
    .action-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
    }}
    .inline-note {{
      font-size: 0.88rem;
    }}
    .support-footer {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
      margin-top: 16px;
      padding-top: 14px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 0.8rem;
    }}
    .support-footer strong {{
      letter-spacing: 0.08em;
      text-transform: uppercase;
      font-size: 0.72rem;
      color: var(--muted);
    }}
    .support-pill {{
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.04);
      color: var(--text);
      font-size: 0.78rem;
    }}
    @media (max-width: 1100px) {{
      .hero-grid {{
        grid-template-columns: 1fr;
      }}
      .hero-visual {{
        margin-inline: auto;
      }}
    }}
    @media (max-width: 760px) {{
      .site {{
        padding: 14px 14px 28px;
      }}
      .topbar {{
        border-radius: 28px;
        justify-content: center;
        text-align: center;
        flex-wrap: wrap;
      }}
      .nav {{
        width: 100%;
      }}
      .content,
      .topbar {{
        width: min(100vw - 28px, 1080px);
      }}
      .hero-card,
      .upload-card {{
        padding: 22px;
      }}
      h1 {{
        max-width: none;
      }}
      .hero-visual {{
        width: 180px;
        height: 180px;
      }}
      .visual-core {{
        inset: 60px;
      }}
      .surface-title {{
        flex-direction: column;
        align-items: flex-start;
      }}
      .upload-top {{
        grid-template-columns: 1fr;
      }}
      .action-row {{
        align-items: stretch;
      }}
    }}
  </style>
</head>
<body>
  <div class="site">
    <header class="topbar">
      <a class="brand" href="/" aria-label="Divian-HUB főoldal">
        <span class="brand-mark"></span>
        <span class="brand-text">
          <strong>Divian-HUB</strong>
          <small>Számla magyarító</small>
        </span>
      </a>

      <nav class="nav">
        <a href="/">Főoldal</a>
        <a href="/#modules">Modulok</a>
      </nav>

      <a class="nav-cta" href="/#divian-ai">Divian-AI</a>
    </header>

    <main class="content">
      <section class="hero-card">
        <div class="hero-grid">
          <div class="hero-copy">
            <div class="eyebrow">Számla magyarító</div>
            <h1>PDF számla <span>kész fordítás</span></h1>
            <p class="lead">
              Tölts fel egy PDF számlát, és a rendszer elkészíti a fordított, nyomtatható változatot.
            </p>
            <div class="hero-actions">
              <a class="button" href="#feltoltes">Feltöltés</a>
              <a class="ghost-link" href="/">Modulok</a>
            </div>
          </div>

          <div class="hero-visual" aria-hidden="true">
            <div class="visual-lang lang-source">Forrás</div>
            <div class="visual-doc doc-source"></div>
            <div class="visual-arrow">→</div>
            <div class="visual-doc doc-target"></div>
            <div class="visual-lang lang-target">Magyar</div>
          </div>
        </div>
      </section>

      <section class="upload-card" id="feltoltes">
        <div class="surface-title">
          <strong>Feltöltés</strong>
          <p>Fájl kiválasztása, majd indítás.</p>
        </div>

        {msg_html}

        <form method="post" action="{GENERATE_ROUTE}" enctype="multipart/form-data" target="_blank" id="invoice-form">
          <div class="upload-shell" id="upload-shell">
            <input
              class="file-input"
              id="invoice_file"
              type="file"
              name="invoice_file"
              accept="application/pdf"
              required
            />

            <label class="upload-surface" for="invoice_file">
              <div class="upload-top">
                <div class="upload-badge">PDF</div>
                <div class="upload-copy">
                  <strong>Számla kiválasztása</strong>
                  <p>Kattints ide, vagy húzd be a fájlt.</p>
                </div>
              </div>

              <div class="upload-rail" aria-hidden="true">
                <span>PDF</span>
                <i></i>
                <span>Fordítás</span>
                <i></i>
                <span>Magyar nézet</span>
              </div>

              <div class="file-state">
                <strong id="file-name">Még nincs kiválasztott fájl</strong>
                <small id="file-meta">Támogatott formátum: .pdf</small>
              </div>
            </label>

            <div class="action-row">
              <button class="primary-button" type="submit" id="submit-button">Fordítás indítása</button>
              <span class="inline-note">Az eredmény külön lapon jelenik meg.</span>
            </div>
          </div>
        </form>

        <div class="support-footer">
          <strong>Működik jelenleg:</strong>
          <span class="support-pill">Kronospan</span>
          <span class="support-pill">Kastamonu</span>
        </div>
      </section>
    </main>
  </div>

  <script>
    const fileInput = document.getElementById("invoice_file");
    const fileName = document.getElementById("file-name");
    const fileMeta = document.getElementById("file-meta");
    const uploadShell = document.getElementById("upload-shell");
    const form = document.getElementById("invoice-form");
    const submitButton = document.getElementById("submit-button");

    const updateFileState = () => {{
      const file = fileInput.files && fileInput.files[0];
      if (!file) {{
        fileName.textContent = "Még nincs kiválasztott fájl";
        fileMeta.textContent = "Támogatott formátum: .pdf";
        return;
      }}

      fileName.textContent = file.name;
      fileMeta.textContent = `${{(file.size / 1024 / 1024).toFixed(2)}} MB`;
    }};

    ["dragenter", "dragover"].forEach((eventName) => {{
      uploadShell.addEventListener(eventName, (event) => {{
        event.preventDefault();
        uploadShell.classList.add("is-dragover");
      }});
    }});

    ["dragleave", "drop"].forEach((eventName) => {{
      uploadShell.addEventListener(eventName, (event) => {{
        event.preventDefault();
        uploadShell.classList.remove("is-dragover");
      }});
    }});

    fileInput.addEventListener("change", updateFileState);

    form.addEventListener("submit", () => {{
      submitButton.textContent = "Feldolgozás indul...";
      submitButton.disabled = true;
      window.setTimeout(() => {{
        submitButton.textContent = "Fordítás indítása";
        submitButton.disabled = false;
      }}, 2000);
    }});
  </script>
  {COMMON_SCRIPT_TAG}
</body>
</html>"""
    return page.encode("utf-8")


def _render_nettfront_layout(
    *,
    heading: str,
    lead: str,
    intro_label: str,
    content_html: str,
    side_html: str,
    notice_html: str = "",
    extra_script: str = "",
    single_column: bool = False,
    module_root_id: str = "",
) -> bytes:
    workflow_class = "workflow-grid is-single-column" if single_column else "workflow-grid"
    side_column_html = ""
    if side_html.strip() and not single_column:
        side_column_html = f"""
          <aside class="stack-column reveal is-visible">
            {side_html}
          </aside>
        """
    hero_html = ""
    module_root_open = f'<div id="{html.escape(module_root_id)}" class="module-root-shell">' if module_root_id else ""
    module_root_close = "</div>" if module_root_id else ""
    page = f"""<!doctype html>
<html lang="hu">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Divian-HUB | NettFront modul</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link
    href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;700&display=swap"
    rel="stylesheet"
  />
  <link rel="stylesheet" href="/styles.css" />
  <style>
    .module-shell {{
      padding-top: 42px;
      padding-bottom: 64px;
    }}
    .module-root-shell {{
      display: block;
      transition: opacity 180ms ease, transform 180ms ease;
    }}
    .module-root-shell.is-loading {{
      opacity: 0.66;
      transform: translateY(2px);
      pointer-events: none;
    }}
    .module-hero {{
      max-width: 760px;
      margin-bottom: 24px;
    }}
    .workflow-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.1fr) minmax(300px, 0.9fr);
      gap: 22px;
    }}
    .workflow-grid.is-single-column {{
      grid-template-columns: minmax(0, 1fr);
    }}
    .workflow-panel,
    .stack-card {{
      position: relative;
      overflow: hidden;
      background: linear-gradient(180deg, var(--panel) 0%, var(--panel-strong) 100%);
      border: 1px solid var(--border);
      border-radius: var(--radius-xl);
      box-shadow: var(--shadow);
    }}
    .workflow-panel::before,
    .stack-card::before {{
      content: "";
      position: absolute;
      inset: 0;
      background:
        linear-gradient(120deg, rgba(67, 222, 207, 0.12), transparent 34%),
        linear-gradient(180deg, transparent, rgba(255, 139, 100, 0.06));
      pointer-events: none;
    }}
    .workflow-panel {{
      padding: 24px;
    }}
    .stack-column {{
      display: grid;
      gap: 18px;
    }}
    .stack-card {{
      padding: 20px;
    }}
    .stack-card h3,
    .workflow-panel h2,
    .summary-card strong {{
      font-family: "Space Grotesk", sans-serif;
    }}
    .workflow-panel h2,
    .stack-card h3 {{
      margin: 0 0 12px;
      font-size: 1.3rem;
      line-height: 1.08;
    }}
    .muted-copy,
    .stack-card p,
    .stack-card li,
    .field-hint,
    .summary-card span,
    .download-card p,
    .notice-banner,
    .status-note {{
      color: var(--muted);
    }}
    .muted-copy,
    .stack-card p {{
      line-height: 1.65;
    }}
    .inline-note {{
      color: var(--muted);
      font-size: 0.88rem;
      line-height: 1.55;
    }}
    .notice-banner {{
      width: var(--content-width);
      margin: 0 auto 18px;
      padding: 16px 18px;
      border-radius: var(--radius-md);
      border: 1px solid rgba(255, 122, 122, 0.26);
      background: rgba(97, 34, 31, 0.42);
      line-height: 1.6;
    }}
    .notice-banner.success {{
      border-color: rgba(67, 222, 207, 0.22);
      background: rgba(16, 74, 63, 0.38);
    }}
    .upload-grid,
    .summary-grid,
    .download-grid,
    .route-grid {{
      display: grid;
      gap: 16px;
    }}
    .upload-grid {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
      margin-top: 20px;
    }}
    .upload-field {{
      display: grid;
      gap: 10px;
      padding: 18px;
      border-radius: var(--radius-lg);
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.04);
    }}
    .upload-field strong,
    .summary-card strong,
    .download-card strong {{
      display: block;
      margin-bottom: 6px;
      font-size: 1rem;
    }}
    .upload-field input[type="file"] {{
      width: 100%;
      padding: 14px 16px;
      border-radius: 16px;
      border: 1px dashed var(--line);
      background: rgba(255, 255, 255, 0.03);
      color: var(--text);
    }}
    .field-hint {{
      font-size: 0.9rem;
      line-height: 1.55;
    }}
    .action-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 18px;
    }}
    .summary-grid {{
      grid-template-columns: repeat(3, minmax(0, 1fr));
      margin-top: 18px;
    }}
    .summary-card,
    .download-card,
    .result-card {{
      padding: 18px;
      border-radius: var(--radius-lg);
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.04);
    }}
    .summary-card span {{
      display: block;
      margin-top: 8px;
      font-size: 0.9rem;
    }}
    .summary-card strong {{
      font-size: 1.9rem;
    }}
    .download-grid {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
      margin-top: 18px;
    }}
    .route-grid {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
      margin-top: 20px;
    }}
    .download-card {{
      display: grid;
      gap: 10px;
      align-content: start;
    }}
    .route-card {{
      display: grid;
      gap: 12px;
      padding: 22px;
      border-radius: var(--radius-lg);
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.04);
      color: inherit;
      text-decoration: none;
      transition:
        transform 180ms ease,
        border-color 180ms ease,
        box-shadow 180ms ease;
    }}
    .route-card:hover {{
      transform: translateY(-3px);
      border-color: rgba(67, 222, 207, 0.24);
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.24);
    }}
    .route-card p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.6;
    }}
    .download-card p {{
      margin: 0;
      line-height: 1.55;
    }}
    .tag {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      width: fit-content;
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: rgba(67, 222, 207, 0.08);
      color: var(--accent);
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-size: 0.7rem;
      font-weight: 700;
    }}
    .tag::before {{
      content: "";
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--accent-warm);
      box-shadow: 0 0 16px rgba(167, 255, 112, 0.8);
    }}
    .status-list {{
      margin: 14px 0 0;
      padding-left: 18px;
      display: grid;
      gap: 10px;
    }}
    .status-note {{
      margin-top: 10px;
      line-height: 1.6;
    }}
    .knowledge-shell {{
      display: grid;
      gap: 18px;
    }}
    .knowledge-hero {{
      position: relative;
      overflow: hidden;
      padding: 24px;
      border-radius: 30px;
      border: 1px solid rgba(67, 222, 207, 0.14);
      background:
        radial-gradient(circle at top right, rgba(67, 222, 207, 0.18), transparent 30%),
        radial-gradient(circle at bottom left, rgba(167, 255, 112, 0.1), transparent 24%),
        linear-gradient(180deg, rgba(255, 255, 255, 0.045), rgba(255, 255, 255, 0.02));
      box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.04),
        0 24px 48px rgba(0, 0, 0, 0.16);
    }}
    .knowledge-hero-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.15fr) 260px;
      gap: 24px;
      align-items: center;
    }}
    .knowledge-hero-copy h2 {{
      margin: 10px 0 8px;
      font-size: clamp(1.8rem, 2vw, 2.35rem);
      line-height: 1.08;
      letter-spacing: -0.04em;
    }}
    .knowledge-hero-copy p {{
      margin: 0;
      max-width: 560px;
      color: var(--muted);
      line-height: 1.6;
    }}
    .knowledge-stat-strip {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 16px;
    }}
    .knowledge-mini-stat {{
      min-width: 120px;
      padding: 10px 14px;
      border-radius: 18px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(255, 255, 255, 0.04);
      backdrop-filter: blur(10px);
      -webkit-backdrop-filter: blur(10px);
    }}
    .knowledge-mini-stat strong {{
      display: block;
      margin-bottom: 3px;
      font-family: "Space Grotesk", sans-serif;
      font-size: 1.14rem;
    }}
    .knowledge-mini-stat span {{
      color: var(--muted);
      font-size: 0.82rem;
      line-height: 1.4;
    }}
    .knowledge-visual {{
      position: relative;
      min-height: 220px;
      overflow: hidden;
      border-radius: 28px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background:
        radial-gradient(circle at 50% 48%, rgba(67, 222, 207, 0.18), transparent 28%),
        radial-gradient(circle at 50% 50%, rgba(167, 255, 112, 0.08), transparent 36%),
        linear-gradient(180deg, rgba(8, 16, 28, 0.96), rgba(5, 10, 18, 0.92));
      box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.04),
        0 18px 44px rgba(0, 0, 0, 0.22);
    }}
    .knowledge-visual-gridline {{
      position: absolute;
      inset: 16px;
      border-radius: 26px;
      background:
        radial-gradient(circle at center, rgba(67, 222, 207, 0.12), transparent 32%),
        radial-gradient(circle at center, rgba(255, 255, 255, 0.06) 0 1px, transparent 1px);
      background-size: auto, 24px 24px;
      opacity: 0.42;
    }}
    .knowledge-visual-core {{
      position: absolute;
      top: 50%;
      left: 50%;
      width: 186px;
      transform: translate(-50%, -50%);
      padding: 22px 20px 18px;
      display: grid;
      gap: 10px;
      justify-items: center;
      text-align: center;
      border-radius: 30px;
      border: 1px solid rgba(67, 222, 207, 0.24);
      background:
        radial-gradient(circle at top left, rgba(255, 255, 255, 0.16), transparent 40%),
        linear-gradient(180deg, rgba(21, 52, 66, 0.96), rgba(7, 22, 34, 0.98));
      box-shadow:
        0 22px 42px rgba(0, 0, 0, 0.28),
        0 0 42px rgba(67, 222, 207, 0.14),
        inset 0 1px 0 rgba(255, 255, 255, 0.08);
      animation: knowledgeCorePulse 6.2s ease-in-out infinite;
      z-index: 2;
    }}
    .knowledge-visual-core::before {{
      content: "";
      position: absolute;
      inset: -12px;
      border-radius: 40px;
      border: 1px solid rgba(67, 222, 207, 0.12);
      opacity: 0.85;
    }}
    .knowledge-visual-core::after {{
      content: "";
      position: absolute;
      inset: auto 28px -20px;
      height: 30px;
      border-radius: 50%;
      background: rgba(67, 222, 207, 0.18);
      filter: blur(20px);
      opacity: 0.8;
    }}
    .knowledge-visual-kicker {{
      position: relative;
      z-index: 1;
      color: rgba(228, 250, 255, 0.72);
      font-size: 0.74rem;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      font-weight: 700;
    }}
    .knowledge-visual-core strong {{
      position: relative;
      z-index: 1;
      font-family: "Space Grotesk", sans-serif;
      font-size: 1.28rem;
      line-height: 1;
      letter-spacing: -0.04em;
    }}
    .knowledge-visual-scan {{
      position: relative;
      z-index: 1;
      width: 82px;
      height: 4px;
      overflow: hidden;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.06);
    }}
    .knowledge-visual-scan::after {{
      content: "";
      position: absolute;
      inset: 0;
      background: linear-gradient(90deg, transparent, rgba(167, 255, 112, 0.96), transparent);
      transform: translateX(-100%);
      animation: knowledgeScanLine 2.8s ease-in-out infinite;
    }}
    .knowledge-visual-caption {{
      position: relative;
      z-index: 1;
      color: var(--muted);
      line-height: 1.35;
      font-size: 0.74rem;
      max-width: 128px;
    }}
    @keyframes knowledgeCorePulse {{
      0%, 100% {{
        transform: translate(-50%, -50%) scale(0.985);
      }}
      50% {{
        transform: translate(-50%, -50%) scale(1.015);
      }}
    }}
    @keyframes knowledgeScanLine {{
      0% {{
        transform: translateX(-100%);
      }}
      55%,
      100% {{
        transform: translateX(100%);
      }}
    }}
    .knowledge-upload {{
      display: grid;
      gap: 16px;
      padding: 18px;
      border-radius: 28px;
      border: 1px solid rgba(67, 222, 207, 0.14);
      background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.02)),
        rgba(7, 16, 27, 0.6);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
    }}
    .knowledge-upload-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }}
    .knowledge-upload-copy strong {{
      display: block;
      margin-bottom: 6px;
      font-size: 1rem;
    }}
    .knowledge-upload-copy p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
    }}
    .knowledge-upload {{
      position: relative;
    }}
    .knowledge-upload-badge {{
      flex: 0 0 auto;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 64px;
      padding: 9px 12px;
      border-radius: 999px;
      border: 1px solid rgba(67, 222, 207, 0.16);
      background: rgba(67, 222, 207, 0.1);
      color: var(--accent);
      font-size: 0.74rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-weight: 700;
    }}
    .knowledge-dropzone {{
      position: relative;
      overflow: hidden;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 16px;
      align-items: center;
      padding: 20px;
      border-radius: 24px;
      border: 1px dashed rgba(67, 222, 207, 0.18);
      background: rgba(7, 16, 27, 0.46);
      cursor: pointer;
      transition:
        border-color 180ms ease,
        background 180ms ease,
        transform 180ms ease;
    }}
    .knowledge-dropzone.is-dragover {{
      border-color: rgba(67, 222, 207, 0.34);
      background: rgba(10, 22, 35, 0.62);
      transform: translateY(-2px);
    }}
    .knowledge-dropzone:hover {{
      border-color: rgba(67, 222, 207, 0.3);
      background: rgba(10, 22, 35, 0.56);
      transform: translateY(-2px);
    }}
    .knowledge-dropzone:focus-within {{
      border-color: rgba(67, 222, 207, 0.34);
      background: rgba(10, 22, 35, 0.6);
    }}
    .knowledge-dropzone-copy strong {{
      display: block;
      margin-bottom: 4px;
      font-size: 1rem;
    }}
    .knowledge-dropzone-copy p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.55;
    }}
    .knowledge-dropzone-action {{
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .knowledge-dropzone-cta {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 42px;
      padding: 0 14px;
      border-radius: 999px;
      border: 1px solid rgba(67, 222, 207, 0.16);
      background: linear-gradient(180deg, rgba(67, 222, 207, 0.14), rgba(9, 47, 61, 0.5));
      color: var(--text);
      font-size: 0.84rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
    }}
    .knowledge-dropzone-note {{
      color: var(--muted);
      font-size: 0.84rem;
    }}
    .knowledge-dropzone input[type="file"] {{
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      opacity: 0;
      cursor: pointer;
    }}
    .knowledge-file-state {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      width: fit-content;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.05);
      color: var(--muted);
      font-size: 0.82rem;
    }}
    .knowledge-file-state::before {{
      content: "";
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: rgba(67, 222, 207, 0.7);
      box-shadow: 0 0 12px rgba(67, 222, 207, 0.5);
    }}
    .knowledge-chip-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    .knowledge-chip {{
      display: inline-flex;
      align-items: center;
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(255, 255, 255, 0.035);
      color: var(--muted);
      font-size: 0.82rem;
    }}
    .knowledge-footer {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      flex-wrap: wrap;
    }}
    .knowledge-bottom {{
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 14px;
    }}
    .knowledge-list-card {{
      padding: 18px;
      border-radius: 24px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(255, 255, 255, 0.035);
    }}
    .knowledge-section-head {{
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 14px;
    }}
    .knowledge-section-head h3 {{
      margin: 0;
      font-family: "Space Grotesk", sans-serif;
      font-size: 1.16rem;
    }}
    .knowledge-section-head p {{
      margin: 6px 0 0;
      color: var(--muted);
      line-height: 1.6;
    }}
    .knowledge-list {{
      display: grid;
      gap: 10px;
      margin: 0;
      padding: 0;
      list-style: none;
    }}
    .knowledge-list li {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 14px;
      border-radius: 16px;
      border: 1px solid rgba(255, 255, 255, 0.05);
      background: rgba(255, 255, 255, 0.03);
    }}
    .knowledge-list strong {{
      font-size: 0.96rem;
    }}
    .knowledge-list span {{
      color: var(--muted);
      font-size: 0.88rem;
      line-height: 1.5;
    }}
    .knowledge-list-side {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    .knowledge-list-meta {{
      text-align: right;
      white-space: nowrap;
    }}
    .knowledge-list-badge {{
      display: inline-flex;
      align-items: center;
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid rgba(67, 222, 207, 0.14);
      background: rgba(67, 222, 207, 0.08);
      color: var(--text);
      font-size: 0.76rem;
      white-space: nowrap;
    }}
    .knowledge-list-badge.is-pending {{
      border-color: rgba(255, 184, 76, 0.18);
      background: rgba(255, 184, 76, 0.1);
    }}
    .knowledge-list-actions {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .knowledge-list-actions form {{
      margin: 0;
    }}
    .knowledge-action {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 34px;
      padding: 0 12px;
      border-radius: 999px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(255, 255, 255, 0.04);
      color: var(--text);
      font-size: 0.78rem;
      text-decoration: none;
      cursor: pointer;
      transition: border-color 180ms ease, background 180ms ease, transform 180ms ease;
    }}
    .knowledge-action:hover {{
      border-color: rgba(67, 222, 207, 0.2);
      background: rgba(67, 222, 207, 0.08);
      transform: translateY(-1px);
    }}
    .knowledge-action.is-danger {{
      border-color: rgba(255, 107, 107, 0.18);
      background: rgba(255, 107, 107, 0.08);
    }}
    .knowledge-empty {{
      padding: 14px 16px;
      border-radius: 18px;
      border: 1px dashed rgba(255, 255, 255, 0.08);
      color: var(--muted);
      background: rgba(255, 255, 255, 0.02);
    }}
    .missing-list {{
      margin: 12px 0 0;
      padding-left: 18px;
      display: grid;
      gap: 8px;
      max-height: 220px;
      overflow: auto;
    }}
    .stack-card ul {{
      margin: 12px 0 0;
      padding-left: 18px;
      display: grid;
      gap: 8px;
    }}
    .launch-form {{
      margin-top: 18px;
    }}
    .launch-form .button-secondary {{
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.05);
      color: var(--text);
      box-shadow: none;
    }}
    .procurement-shell {{
      display: grid;
      gap: 18px;
    }}
    .procurement-hero-card,
    .procurement-upload-card {{
      position: relative;
      overflow: hidden;
      border-radius: 28px;
      border: 1px solid rgba(67, 222, 207, 0.14);
      background:
        radial-gradient(circle at top right, rgba(67, 222, 207, 0.12), transparent 34%),
        linear-gradient(180deg, rgba(255, 255, 255, 0.045), rgba(255, 255, 255, 0.028));
      box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.03),
        0 18px 42px rgba(0, 0, 0, 0.18);
    }}
    .procurement-hero-card {{
      padding: 24px;
    }}
    .procurement-hero-card::before,
    .procurement-upload-card::before {{
      content: "";
      position: absolute;
      inset: 0;
      background: linear-gradient(120deg, rgba(67, 222, 207, 0.08), transparent 42%);
      pointer-events: none;
    }}
    .procurement-hero-grid {{
      position: relative;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 240px;
      gap: 24px;
      align-items: center;
    }}
    .procurement-copy {{
      display: grid;
      gap: 14px;
    }}
    .procurement-copy strong {{
      display: block;
      max-width: 15ch;
      font-family: "Space Grotesk", sans-serif;
      font-size: clamp(2rem, 4.5vw, 3.15rem);
      line-height: 0.98;
      letter-spacing: -0.04em;
    }}
    .procurement-copy p {{
      margin: 0;
      max-width: 34ch;
      color: var(--muted);
      line-height: 1.65;
    }}
    .procurement-flow {{
      display: inline-flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
      width: fit-content;
      padding: 10px 14px;
      border-radius: 999px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(255, 255, 255, 0.04);
      color: var(--muted);
      font-size: 0.82rem;
      letter-spacing: 0.04em;
    }}
    .procurement-flow i {{
      width: 22px;
      height: 1px;
      background: linear-gradient(90deg, rgba(67, 222, 207, 0.2), rgba(167, 255, 112, 0.8));
      display: block;
    }}
    .procurement-visual {{
      position: relative;
      min-height: 220px;
      border-radius: 28px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background:
        radial-gradient(circle at 50% 18%, rgba(67, 222, 207, 0.18), transparent 34%),
        linear-gradient(180deg, rgba(7, 16, 27, 0.76), rgba(7, 16, 27, 0.42));
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
    }}
    .procurement-visual::before {{
      content: "";
      position: absolute;
      inset: 18px;
      border-radius: 22px;
      border: 1px solid rgba(67, 222, 207, 0.08);
      background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.02), transparent),
        repeating-linear-gradient(
          180deg,
          transparent 0,
          transparent 16px,
          rgba(255, 255, 255, 0.02) 16px,
          rgba(255, 255, 255, 0.02) 17px
        );
    }}
    .procurement-orbit {{
      position: absolute;
      inset: 36px;
      border-radius: 28px;
      border: 1px dashed rgba(67, 222, 207, 0.14);
    }}
    .procurement-doc {{
      position: absolute;
      width: 88px;
      height: 112px;
      padding: 14px 12px;
      border-radius: 22px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.03));
      box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.04),
        0 18px 24px rgba(0, 0, 0, 0.2);
      backdrop-filter: blur(12px);
    }}
    .procurement-doc.is-source {{
      left: 34px;
      top: 54px;
    }}
    .procurement-doc.is-target {{
      right: 34px;
      top: 54px;
      border-color: rgba(167, 255, 112, 0.14);
    }}
    .procurement-doc-label {{
      display: block;
      margin-bottom: 12px;
      color: var(--text);
      font-size: 0.8rem;
      font-weight: 700;
      letter-spacing: 0.04em;
    }}
    .procurement-doc-lines {{
      display: grid;
      gap: 8px;
    }}
    .procurement-doc-lines span {{
      display: block;
      height: 7px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.12);
    }}
    .procurement-doc-lines span:nth-child(2) {{
      width: 78%;
    }}
    .procurement-doc-lines span:nth-child(3) {{
      width: 62%;
    }}
    .procurement-transfer {{
      position: absolute;
      left: 50%;
      top: 50%;
      width: 82px;
      height: 82px;
      transform: translate(-50%, -50%);
      border-radius: 50%;
      border: 1px solid rgba(67, 222, 207, 0.18);
      background: radial-gradient(circle, rgba(67, 222, 207, 0.18), rgba(8, 22, 36, 0.12));
      box-shadow: 0 0 34px rgba(67, 222, 207, 0.18);
    }}
    .procurement-transfer::before {{
      content: "";
      position: absolute;
      left: 24px;
      right: 24px;
      top: 50%;
      height: 2px;
      transform: translateY(-50%);
      background: linear-gradient(90deg, rgba(67, 222, 207, 0.16), rgba(167, 255, 112, 0.9));
    }}
    .procurement-transfer::after {{
      content: "";
      position: absolute;
      right: 22px;
      top: 50%;
      width: 10px;
      height: 10px;
      transform: translateY(-50%) rotate(45deg);
      border-top: 2px solid rgba(167, 255, 112, 0.9);
      border-right: 2px solid rgba(167, 255, 112, 0.9);
    }}
    .procurement-upload-card {{
      padding: 22px;
    }}
    .procurement-surface-title {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 16px;
    }}
    .procurement-surface-title strong {{
      font-size: 1rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .procurement-surface-title p {{
      margin: 0;
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .procurement-upload-shell {{
      display: grid;
      gap: 16px;
    }}
    .procurement-upload-shell.is-dragover .procurement-upload-surface {{
      border-color: rgba(67, 222, 207, 0.34);
      background: rgba(10, 22, 35, 0.64);
      transform: translateY(-2px);
    }}
    .procurement-file-input {{
      position: absolute;
      inset: 0;
      opacity: 0;
      pointer-events: none;
    }}
    .procurement-upload-surface {{
      position: relative;
      overflow: hidden;
      display: grid;
      gap: 14px;
      padding: 24px;
      border-radius: 26px;
      border: 1px dashed rgba(67, 222, 207, 0.18);
      background: rgba(7, 16, 27, 0.48);
      cursor: pointer;
      transition:
        border-color 180ms ease,
        background 180ms ease,
        transform 180ms ease;
    }}
    .procurement-upload-surface:hover {{
      border-color: rgba(67, 222, 207, 0.28);
      background: rgba(10, 22, 35, 0.56);
      transform: translateY(-2px);
    }}
    .procurement-upload-top {{
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 14px;
      align-items: center;
    }}
    .procurement-upload-badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 54px;
      min-height: 54px;
      padding: 0 16px;
      border-radius: 18px;
      border: 1px solid rgba(67, 222, 207, 0.16);
      background: linear-gradient(180deg, rgba(67, 222, 207, 0.14), rgba(9, 47, 61, 0.44));
      color: var(--text);
      font-size: 0.84rem;
      font-weight: 700;
      letter-spacing: 0.08em;
    }}
    .procurement-upload-copy strong {{
      display: block;
      margin-bottom: 4px;
      font-size: 1rem;
    }}
    .procurement-upload-copy p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.6;
    }}
    .procurement-upload-rail {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      color: var(--muted);
      font-size: 0.82rem;
      letter-spacing: 0.04em;
    }}
    .procurement-upload-rail i {{
      width: 20px;
      height: 1px;
      background: linear-gradient(90deg, rgba(67, 222, 207, 0.18), rgba(167, 255, 112, 0.8));
      display: block;
    }}
    .procurement-file-state {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      width: fit-content;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.05);
      color: var(--muted);
      font-size: 0.86rem;
    }}
    .procurement-file-state::before {{
      content: "";
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: rgba(67, 222, 207, 0.72);
      box-shadow: 0 0 12px rgba(67, 222, 207, 0.5);
    }}
    .procurement-action-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      flex-wrap: wrap;
    }}
    .procurement-action-row .button {{
      min-width: 220px;
    }}
    .procurement-action-row .inline-note {{
      margin-left: auto;
      text-align: right;
    }}
    .procurement-output-footer {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      padding-top: 14px;
      margin-top: 4px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 0.8rem;
    }}
    .procurement-output-footer strong {{
      letter-spacing: 0.08em;
      text-transform: uppercase;
      font-size: 0.72rem;
      color: var(--muted);
    }}
    .procurement-pill {{
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(255, 255, 255, 0.04);
      color: var(--text);
      font-size: 0.78rem;
    }}
    .procurement-result-shell {{
      display: grid;
      gap: 18px;
    }}
    .procurement-result-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }}
    .procurement-result-card {{
      padding: 18px;
      border-radius: 24px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(255, 255, 255, 0.035);
    }}
    .procurement-result-card strong {{
      display: block;
      margin-bottom: 8px;
      font-size: 1.04rem;
    }}
    .procurement-result-copy {{
      margin: 12px 0 0;
      color: var(--muted);
      line-height: 1.6;
      font-size: 0.9rem;
    }}
    .procurement-warning-modal {{
      position: fixed;
      inset: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
      background: rgba(3, 8, 16, 0.74);
      backdrop-filter: blur(18px);
      -webkit-backdrop-filter: blur(18px);
      opacity: 0;
      visibility: hidden;
      pointer-events: none;
      transition: opacity 180ms ease, visibility 180ms ease;
      z-index: 40;
    }}
    .procurement-warning-modal.is-visible {{
      opacity: 1;
      visibility: visible;
      pointer-events: auto;
    }}
    .procurement-warning-card {{
      width: min(100%, 520px);
      padding: 24px;
      border-radius: 28px;
      border: 1px solid rgba(255, 184, 76, 0.18);
      background:
        radial-gradient(circle at top right, rgba(255, 184, 76, 0.14), transparent 34%),
        rgba(8, 16, 28, 0.96);
      box-shadow: 0 28px 80px rgba(0, 0, 0, 0.36);
    }}
    .procurement-warning-card strong {{
      display: block;
      margin-bottom: 10px;
      font-size: 1.14rem;
    }}
    .procurement-warning-card p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.65;
    }}
    .procurement-warning-actions {{
      display: flex;
      justify-content: flex-end;
      margin-top: 18px;
    }}
    .procurement-result-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      margin-top: 10px;
    }}
    .procurement-result-pill {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid rgba(67, 222, 207, 0.14);
      background: rgba(67, 222, 207, 0.08);
      color: var(--text);
      font-size: 0.82rem;
    }}
    .procurement-result-pill.is-alert {{
      border-color: rgba(255, 139, 100, 0.18);
      background: rgba(255, 139, 100, 0.08);
    }}
    .procurement-code-list {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }}
    .procurement-code-chip {{
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid rgba(255, 255, 255, 0.07);
      background: rgba(255, 255, 255, 0.04);
      color: var(--text);
      font-size: 0.78rem;
    }}
    .procurement-preview-card {{
      padding: 18px;
      border-radius: 24px;
      border: 1px solid rgba(67, 222, 207, 0.14);
      background:
        radial-gradient(circle at top right, rgba(67, 222, 207, 0.08), transparent 34%),
        rgba(7, 16, 27, 0.44);
    }}
    .procurement-preview-head {{
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }}
    .procurement-preview-head strong {{
      display: block;
      margin-bottom: 4px;
      font-size: 1rem;
    }}
    .procurement-preview-head p {{
      margin: 0;
      color: var(--muted);
      font-size: 0.88rem;
      line-height: 1.55;
    }}
    .procurement-preview-table-wrap {{
      overflow: auto;
      border-radius: 18px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(255, 255, 255, 0.03);
    }}
    .procurement-preview-table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 320px;
    }}
    .procurement-preview-table th,
    .procurement-preview-table td {{
      padding: 12px 14px;
      text-align: left;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
      font-size: 0.9rem;
    }}
    .procurement-preview-table th {{
      color: var(--muted);
      font-weight: 600;
      letter-spacing: 0.04em;
    }}
    .procurement-preview-table tbody tr:last-child td {{
      border-bottom: 0;
    }}
    .procurement-preview-empty {{
      padding: 16px;
      border-radius: 18px;
      border: 1px solid rgba(255, 255, 255, 0.05);
      background: rgba(255, 255, 255, 0.03);
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .procurement-launch-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
    }}
    .procurement-launch-row form {{
      margin: 0;
    }}
    .procurement-launch-row .button {{
      min-width: 240px;
    }}
    .procurement-remap-card {{
      padding: 18px;
      border-radius: 24px;
      border: 1px solid rgba(255, 139, 100, 0.16);
      background:
        radial-gradient(circle at top left, rgba(255, 139, 100, 0.08), transparent 32%),
        rgba(255, 255, 255, 0.035);
    }}
    .procurement-remap-card strong {{
      display: block;
      margin-bottom: 8px;
      font-size: 1.02rem;
    }}
    .procurement-remap-card p {{
      margin: 0 0 14px;
      color: var(--muted);
      line-height: 1.6;
    }}
    .procurement-remap-form {{
      display: grid;
      gap: 12px;
    }}
    .procurement-remap-input {{
      width: 100%;
      padding: 14px 16px;
      border-radius: 16px;
      border: 1px dashed rgba(255, 255, 255, 0.14);
      background: rgba(7, 16, 27, 0.54);
      color: var(--text);
    }}
    .procurement-remap-meta {{
      color: var(--muted);
      font-size: 0.84rem;
      line-height: 1.55;
    }}
    .procurement-side-card {{
      display: grid;
      gap: 12px;
    }}
    .procurement-side-card h3 {{
      margin: 0;
      font-size: 1.16rem;
    }}
    .procurement-side-card p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.6;
    }}
    .procurement-side-list {{
      display: grid;
      gap: 10px;
      margin: 0;
      padding: 0;
      list-style: none;
    }}
    .procurement-side-list li {{
      display: flex;
      align-items: center;
      gap: 10px;
      color: var(--text);
    }}
    .procurement-side-list li::before {{
      content: "";
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: linear-gradient(180deg, var(--accent), var(--accent-warm));
      box-shadow: 0 0 12px rgba(67, 222, 207, 0.36);
      flex: 0 0 auto;
    }}
    .vacation-shell {{
      display: grid;
      gap: 16px;
    }}
    .vacation-hero-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 248px;
      gap: 12px;
      align-items: stretch;
    }}
    .vacation-hero-card {{
      display: grid;
      gap: 12px;
      padding: 18px;
    }}
    .vacation-hero-copy {{
      display: grid;
      gap: 6px;
    }}
    .vacation-hero-copy h2 {{
      margin: 0;
      font-size: clamp(1.56rem, 1.8vw, 1.92rem);
      line-height: 1.04;
    }}
    .vacation-hero-copy p {{
      margin: 0;
      max-width: 56ch;
      font-size: 0.92rem;
      line-height: 1.45;
    }}
    .vacation-stat-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }}
    .vacation-stat {{
      padding: 10px 12px;
      border-radius: 16px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(255, 255, 255, 0.035);
    }}
    .vacation-stat strong {{
      display: block;
      margin: 0;
      font-family: "Space Grotesk", sans-serif;
      font-size: 1.14rem;
      line-height: 1;
    }}
    .vacation-stat span {{
      display: block;
      margin-top: 5px;
      color: var(--muted);
      font-size: 0.76rem;
      line-height: 1.35;
    }}
    .vacation-visual-card {{
      display: grid;
      align-content: stretch;
      padding: 14px;
    }}
    .vacation-visual {{
      position: relative;
      min-height: 100%;
      display: grid;
      gap: 10px;
      align-content: center;
    }}
    .vacation-visual::before {{
      content: "";
      position: absolute;
      inset: 18px 26px auto auto;
      width: 120px;
      height: 120px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(67, 222, 207, 0.24), transparent 72%);
      filter: blur(6px);
      pointer-events: none;
    }}
    .vacation-visual::after {{
      content: "";
      position: absolute;
      inset: auto auto 8px 18px;
      width: 110px;
      height: 110px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(255, 184, 76, 0.12), transparent 72%);
      filter: blur(10px);
      pointer-events: none;
    }}
    .vacation-visual-board {{
      position: relative;
      z-index: 1;
      display: grid;
      gap: 8px;
      padding: 12px;
      border-radius: 18px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background:
        linear-gradient(180deg, rgba(10, 22, 36, 0.92), rgba(7, 15, 27, 0.86)),
        radial-gradient(circle at top right, rgba(67, 222, 207, 0.12), transparent 38%);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
    }}
    .vacation-visual-topbar {{
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .vacation-visual-topbar span {{
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.18);
    }}
    .vacation-visual-topbar span:first-child {{
      background: rgba(255, 184, 76, 0.84);
    }}
    .vacation-visual-topbar span:nth-child(2) {{
      background: rgba(67, 222, 207, 0.84);
    }}
    .vacation-visual-week {{
      display: grid;
      grid-template-columns: repeat(7, minmax(0, 1fr));
      gap: 6px;
    }}
    .vacation-visual-week span {{
      height: 8px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.08);
    }}
    .vacation-visual-days {{
      display: grid;
      grid-template-columns: repeat(7, minmax(0, 1fr));
      gap: 5px;
    }}
    .vacation-visual-day {{
      height: 18px;
      border-radius: 9px;
      border: 1px solid rgba(255, 255, 255, 0.05);
      background: rgba(255, 255, 255, 0.04);
    }}
    .vacation-visual-day.is-accent {{
      background: linear-gradient(180deg, rgba(67, 222, 207, 0.34), rgba(67, 222, 207, 0.14));
      border-color: rgba(67, 222, 207, 0.28);
      box-shadow: 0 0 20px rgba(67, 222, 207, 0.16);
    }}
    .vacation-visual-day.is-warm {{
      background: linear-gradient(180deg, rgba(255, 184, 76, 0.3), rgba(255, 184, 76, 0.12));
      border-color: rgba(255, 184, 76, 0.28);
    }}
    .vacation-visual-roster {{
      display: grid;
      gap: 6px;
      padding-top: 1px;
    }}
    .vacation-visual-row {{
      display: grid;
      grid-template-columns: 9px minmax(0, 1fr) 42px;
      align-items: center;
      gap: 8px;
    }}
    .vacation-visual-avatar {{
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: linear-gradient(180deg, rgba(67, 222, 207, 0.92), rgba(255, 184, 76, 0.9));
      box-shadow: 0 0 12px rgba(67, 222, 207, 0.3);
    }}
    .vacation-visual-bar {{
      height: 8px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.08);
      overflow: hidden;
      position: relative;
    }}
    .vacation-visual-bar::after {{
      content: "";
      position: absolute;
      inset: 0 auto 0 0;
      width: 58%;
      border-radius: inherit;
      background: linear-gradient(90deg, rgba(67, 222, 207, 0.84), rgba(67, 222, 207, 0.36));
    }}
    .vacation-visual-bar.is-mid::after {{
      width: 74%;
    }}
    .vacation-visual-bar.is-warm::after {{
      width: 92%;
      background: linear-gradient(90deg, rgba(255, 184, 76, 0.92), rgba(255, 184, 76, 0.4));
    }}
    .vacation-visual-count {{
      justify-self: end;
      padding: 3px 7px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.05);
      color: var(--muted);
      font-size: 0.62rem;
    }}
    .vacation-visual-chip-row {{
      position: relative;
      z-index: 1;
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .vacation-visual-chip {{
      display: inline-flex;
      align-items: center;
      padding: 5px 8px;
      border-radius: 999px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(255, 255, 255, 0.04);
      color: var(--muted);
      font-size: 0.64rem;
      letter-spacing: 0.02em;
    }}
    .vacation-visual-chip::before {{
      content: "";
      width: 8px;
      height: 8px;
      margin-right: 8px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.24);
    }}
    .vacation-visual-chip.is-accent::before {{
      background: var(--accent);
      box-shadow: 0 0 12px rgba(67, 222, 207, 0.34);
    }}
    .vacation-visual-chip.is-warm::before {{
      background: var(--accent-warm);
      box-shadow: 0 0 12px rgba(255, 184, 76, 0.3);
    }}
    .vacation-toolbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
      padding: 11px 14px;
      border-radius: 18px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(255, 255, 255, 0.03);
    }}
    .vacation-month-nav {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .vacation-month-title {{
      min-width: 158px;
      font-family: "Space Grotesk", sans-serif;
      font-size: 0.92rem;
    }}
    .vacation-month-form {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .vacation-month-form input[type="month"] {{
      min-width: 170px;
      padding: 8px 11px;
      border-radius: 12px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(7, 16, 27, 0.54);
      color: var(--text);
    }}
    .vacation-toolbar .knowledge-action,
    .vacation-item-actions .knowledge-action,
    .vacation-form-actions .button {{
      min-width: 0;
      padding: 8px 12px;
      border-radius: 12px;
      font-size: 0.78rem;
      line-height: 1.1;
    }}
    .vacation-calendar-stage {{
      position: relative;
      display: grid;
      gap: 0;
      scroll-margin-top: 88px;
    }}
    .vacation-calendar-card {{
      display: grid;
      gap: 12px;
      padding: 16px;
    }}
    .vacation-calendar-wrap {{
      overflow: visible;
      min-width: 0;
      padding-bottom: 2px;
    }}
    .vacation-calendar-grid {{
      min-width: 0;
      width: 100%;
      display: grid;
      grid-template-columns: repeat(7, minmax(0, 1fr));
      gap: 6px;
    }}
    .vacation-weekday,
    .vacation-day {{
      border-radius: 20px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(255, 255, 255, 0.03);
    }}
    .vacation-weekday {{
      padding: 7px 8px;
      text-align: center;
      font-size: 0.7rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
    }}
    .vacation-day {{
      min-height: 88px;
      padding: 7px;
      display: grid;
      align-content: start;
      gap: 5px;
      position: relative;
      transition: transform 180ms ease, border-color 180ms ease, background 180ms ease, box-shadow 180ms ease;
    }}
    .vacation-day[data-vacation-day] {{
      cursor: pointer;
    }}
    .vacation-day[data-vacation-day]:hover {{
      transform: translateY(-1px);
      border-color: rgba(67, 222, 207, 0.18);
      box-shadow: 0 18px 34px rgba(2, 10, 18, 0.24);
    }}
    .vacation-day[data-vacation-day]:focus-visible {{
      outline: none;
      box-shadow: 0 0 0 1px rgba(67, 222, 207, 0.36), 0 16px 28px rgba(2, 10, 18, 0.2);
    }}
    .vacation-day.is-other-month {{
      opacity: 0.42;
    }}
    .vacation-day.is-busy {{
      border-color: rgba(67, 222, 207, 0.16);
      background: linear-gradient(180deg, rgba(67, 222, 207, 0.06), rgba(255, 255, 255, 0.03));
    }}
    .vacation-day.is-limited {{
      border-color: rgba(255, 184, 76, 0.22);
      background: linear-gradient(180deg, rgba(255, 184, 76, 0.08), rgba(255, 255, 255, 0.03));
    }}
    .vacation-day.is-today {{
      box-shadow: inset 0 0 0 1px rgba(67, 222, 207, 0.28);
    }}
    .vacation-day-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 6px;
    }}
    .vacation-day-number {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 26px;
      min-height: 26px;
      padding: 0 7px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.04);
      font-size: 0.76rem;
      font-weight: 700;
    }}
    .vacation-day.is-today .vacation-day-number {{
      background: rgba(67, 222, 207, 0.14);
      color: var(--text);
    }}
    .vacation-day-badge {{
      display: inline-flex;
      align-items: center;
      padding: 3px 7px;
      border-radius: 999px;
      font-size: 0.62rem;
      color: var(--muted);
      background: rgba(255, 255, 255, 0.04);
    }}
    .vacation-day-list {{
      display: grid;
      gap: 4px;
    }}
    .vacation-entry {{
      display: inline-flex;
      align-items: center;
      justify-content: flex-start;
      width: 100%;
      max-width: 100%;
      padding: 4px 7px;
      border-radius: 10px;
      border: 1px solid rgba(255, 255, 255, 0.05);
      background: rgba(255, 255, 255, 0.05);
      color: var(--text);
      font-size: 0.68rem;
      line-height: 1.25;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      font: inherit;
      text-align: left;
      cursor: pointer;
      transition: border-color 180ms ease, background 180ms ease, transform 180ms ease;
    }}
    .vacation-entry:hover {{
      border-color: rgba(67, 222, 207, 0.18);
      background: rgba(67, 222, 207, 0.08);
      transform: translateY(-1px);
    }}
    .vacation-entry:focus-visible {{
      outline: none;
      border-color: rgba(67, 222, 207, 0.28);
      background: rgba(67, 222, 207, 0.1);
    }}
    .vacation-entry-more {{
      color: var(--muted);
      font-size: 0.66rem;
    }}
    .vacation-load-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
    }}
    .vacation-load {{
      display: inline-flex;
      align-items: center;
      padding: 3px 6px;
      border-radius: 999px;
      background: rgba(67, 222, 207, 0.08);
      color: var(--text);
      font-size: 0.6rem;
    }}
    .vacation-load.is-limit {{
      background: rgba(255, 184, 76, 0.12);
    }}
    .vacation-insight-grid,
    .vacation-section-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      align-items: start;
    }}
    .vacation-list-card.is-wide {{
      grid-column: 1 / -1;
    }}
    .vacation-list-card {{
      display: grid;
      gap: 8px;
      padding: 16px;
    }}
    .vacation-list-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .vacation-list-head h3 {{
      margin: 0;
      font-size: 0.94rem;
    }}
    .vacation-list-head p {{
      margin: 2px 0 0;
      color: var(--muted);
      font-size: 0.74rem;
      line-height: 1.45;
    }}
    .vacation-list {{
      display: grid;
      gap: 7px;
      margin: 0;
      padding: 0;
      list-style: none;
    }}
    .vacation-item {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      padding: 10px 12px;
      border-radius: 14px;
      border: 1px solid rgba(255, 255, 255, 0.05);
      background: rgba(255, 255, 255, 0.03);
    }}
    .vacation-item-main {{
      display: grid;
      gap: 5px;
    }}
    .vacation-item-main strong {{
      font-size: 0.88rem;
    }}
    .vacation-item-main span {{
      color: var(--muted);
      font-size: 0.76rem;
      line-height: 1.45;
    }}
    .vacation-item-actions {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .vacation-item-actions form {{
      margin: 0;
    }}
    .vacation-mini-badge-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}
    .vacation-mini-badge {{
      display: inline-flex;
      align-items: center;
      padding: 3px 7px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.04);
      color: var(--muted);
      font-size: 0.64rem;
    }}
    .vacation-form-stack {{
      display: grid;
      gap: 12px;
    }}
    .vacation-form-card {{
      display: grid;
      gap: 10px;
      padding: 18px;
    }}
    .vacation-form-card h3 {{
      margin: 0;
      font-size: 0.94rem;
    }}
    .vacation-form-card p {{
      margin: 0;
      color: var(--muted);
      font-size: 0.78rem;
      line-height: 1.45;
    }}
    .vacation-form-grid {{
      display: grid;
      gap: 7px;
    }}
    .vacation-form-grid.is-split {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
    .vacation-field.is-full,
    .vacation-form-actions.is-full {{
      grid-column: 1 / -1;
    }}
    .vacation-field {{
      display: grid;
      gap: 6px;
    }}
    .vacation-field label,
    .vacation-field strong {{
      font-size: 0.78rem;
      font-weight: 700;
    }}
    .vacation-field input[type="text"],
    .vacation-field input[type="number"],
    .vacation-field input[type="date"],
    .vacation-field select,
    .vacation-field textarea {{
      width: 100%;
      padding: 8px 10px;
      border-radius: 12px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(7, 16, 27, 0.54);
      color: var(--text);
      font: inherit;
    }}
    .vacation-field textarea {{
      min-height: 56px;
      resize: vertical;
    }}
    .vacation-field-hint {{
      color: var(--muted);
      font-size: 0.7rem;
      line-height: 1.45;
    }}
    .vacation-checkbox-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 6px;
    }}
    .vacation-check {{
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 10px;
      border-radius: 12px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(255, 255, 255, 0.03);
      cursor: pointer;
    }}
    .vacation-check span {{
      font-size: 0.74rem;
      line-height: 1.35;
    }}
    .vacation-check input {{
      accent-color: var(--accent);
    }}
    .vacation-form-actions {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .vacation-card-divider {{
      height: 1px;
      background: linear-gradient(90deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.02));
      margin: 2px 0;
    }}
    .vacation-modal-backdrop {{
      position: absolute;
      inset: 8px;
      z-index: 12;
      display: none;
      align-items: flex-start;
      justify-content: center;
      padding: 14px;
      border-radius: 26px;
      background: rgba(3, 10, 18, 0.7);
      backdrop-filter: blur(10px);
      overflow-y: auto;
    }}
    .vacation-modal-backdrop.is-open {{
      display: flex;
    }}
    .vacation-modal-card {{
      position: relative;
      width: min(520px, calc(100% - 12px));
      max-height: min(720px, calc(100vh - 180px));
      overflow: auto;
      display: grid;
      align-content: start;
      gap: 10px;
      padding: 16px;
      border-radius: 20px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background:
        linear-gradient(180deg, rgba(11, 21, 35, 0.96), rgba(7, 15, 27, 0.94)),
        radial-gradient(circle at top right, rgba(67, 222, 207, 0.1), transparent 36%);
      box-shadow: 0 32px 80px rgba(0, 0, 0, 0.4);
    }}
    .vacation-modal-close {{
      position: absolute;
      top: 12px;
      right: 12px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 34px;
      height: 34px;
      border-radius: 999px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(255, 255, 255, 0.04);
      color: var(--text);
      font-size: 1.25rem;
      line-height: 1;
      cursor: pointer;
    }}
    .vacation-modal-head {{
      display: grid;
      gap: 6px;
      padding-right: 40px;
    }}
    .vacation-modal-head h3 {{
      margin: 0;
      font-size: 1.04rem;
    }}
    .vacation-modal-head p {{
      margin: 0;
      color: var(--muted);
      font-size: 0.78rem;
      line-height: 1.45;
    }}
    .vacation-modal-day-panel {{
      display: grid;
      gap: 8px;
      padding: 12px;
      border-radius: 18px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(255, 255, 255, 0.03);
    }}
    .vacation-modal-day-summary {{
      display: grid;
      gap: 3px;
    }}
    .vacation-modal-day-summary strong {{
      font-size: 0.92rem;
    }}
    .vacation-modal-day-summary span {{
      color: var(--muted);
      font-size: 0.72rem;
    }}
    .vacation-modal-day-list {{
      display: grid;
      gap: 7px;
    }}
    .vacation-modal-day-entry {{
      display: grid;
      gap: 3px;
      width: 100%;
      padding: 8px 10px;
      border-radius: 14px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(255, 255, 255, 0.04);
      color: var(--text);
      text-align: left;
      cursor: pointer;
      font: inherit;
      transition: border-color 180ms ease, background 180ms ease, transform 180ms ease;
    }}
    .vacation-modal-day-entry:hover {{
      border-color: rgba(67, 222, 207, 0.18);
      background: rgba(67, 222, 207, 0.08);
      transform: translateY(-1px);
    }}
    .vacation-modal-day-entry.is-active {{
      border-color: rgba(67, 222, 207, 0.24);
      background: rgba(67, 222, 207, 0.1);
      box-shadow: inset 0 0 0 1px rgba(67, 222, 207, 0.18);
    }}
    .vacation-modal-day-entry strong {{
      font-size: 0.82rem;
    }}
    .vacation-modal-day-entry span,
    .vacation-modal-day-entry small {{
      color: var(--muted);
      font-size: 0.72rem;
      line-height: 1.4;
    }}
    .vacation-modal-form {{
      margin: 0;
    }}
    .vacation-modal-actions {{
      justify-content: space-between;
    }}
    .vacation-modal-delete {{
      display: flex;
      justify-content: flex-end;
      margin: 0;
    }}
    .vacation-inline-link {{
      color: var(--muted);
      font-size: 0.74rem;
      text-decoration: none;
    }}
    .vacation-inline-link:hover {{
      color: var(--text);
    }}
    .vacation-empty {{
      padding: 10px 12px;
      border-radius: 14px;
      border: 1px dashed rgba(255, 255, 255, 0.08);
      background: rgba(255, 255, 255, 0.02);
      color: var(--muted);
      font-size: 0.78rem;
      line-height: 1.45;
    }}
    @media (max-width: 1020px) {{
      .workflow-grid,
      .upload-grid,
      .summary-grid,
      .download-grid,
      .route-grid,
      .knowledge-hero-grid,
      .procurement-result-grid {{
        grid-template-columns: 1fr;
      }}
      .procurement-hero-grid {{
        grid-template-columns: 1fr;
      }}
      .knowledge-upload-head,
      .knowledge-section-head {{
        grid-template-columns: 1fr;
        display: grid;
      }}
      .vacation-hero-grid,
      .vacation-checkbox-grid {{
        grid-template-columns: 1fr;
      }}
      .vacation-toolbar,
      .vacation-insight-grid,
      .vacation-section-grid {{
        align-items: flex-start;
      }}
      .vacation-form-grid.is-split {{
        grid-template-columns: 1fr;
      }}
    }}
    @media (max-width: 760px) {{
      .vacation-calendar-stage {{
        scroll-margin-top: 74px;
      }}
      .procurement-hero-card,
      .procurement-upload-card {{
        padding: 20px;
      }}
      .procurement-visual {{
        min-height: 200px;
      }}
      .procurement-doc {{
        width: 78px;
        height: 102px;
      }}
      .procurement-doc.is-source {{
        left: 24px;
      }}
      .procurement-doc.is-target {{
        right: 24px;
      }}
      .procurement-transfer {{
        width: 70px;
        height: 70px;
      }}
      .procurement-upload-surface {{
        padding: 20px;
      }}
      .procurement-action-row {{
        align-items: stretch;
      }}
      .procurement-action-row .button {{
        width: 100%;
        min-width: 0;
      }}
      .procurement-action-row .inline-note {{
        margin-left: 0;
        text-align: left;
      }}
      .procurement-launch-row .button {{
        width: 100%;
        min-width: 0;
      }}
      .procurement-preview-head {{
        flex-direction: column;
        align-items: flex-start;
      }}
      .procurement-upload-top {{
        grid-template-columns: 1fr;
        align-items: flex-start;
      }}
      .procurement-surface-title {{
        flex-direction: column;
        align-items: flex-start;
      }}
      .knowledge-hero,
      .knowledge-upload,
      .knowledge-list-card {{
        padding: 20px;
      }}
      .knowledge-visual {{
        min-height: 216px;
      }}
      .knowledge-visual-core {{
        width: 170px;
        padding: 20px 16px 16px;
      }}
      .knowledge-visual-caption {{
        max-width: 118px;
      }}
      .knowledge-dropzone {{
        grid-template-columns: 1fr;
        justify-items: flex-start;
      }}
      .knowledge-dropzone-action,
      .knowledge-footer,
      .knowledge-list li,
      .knowledge-list-side {{
        justify-content: flex-start;
      }}
      .knowledge-list li {{
        flex-direction: column;
        align-items: flex-start;
      }}
      .knowledge-list-meta {{
        text-align: left;
        white-space: normal;
      }}
      .vacation-calendar-card,
      .vacation-hero-card,
      .vacation-visual-card,
      .vacation-list-card,
      .vacation-form-card {{
        padding: 14px;
      }}
      .vacation-toolbar {{
        gap: 10px;
        padding: 10px 12px;
      }}
      .vacation-visual {{
        min-height: 160px;
      }}
      .vacation-stat-grid {{
        grid-template-columns: 1fr 1fr;
      }}
      .vacation-toolbar,
      .vacation-month-nav,
      .vacation-month-form,
      .vacation-form-actions,
      .vacation-modal-actions,
      .vacation-item,
      .vacation-item-actions {{
        align-items: flex-start;
      }}
      .vacation-month-nav,
      .vacation-month-form {{
        width: 100%;
        justify-content: space-between;
      }}
      .vacation-month-title {{
        min-width: 0;
        flex: 1 1 auto;
        text-align: center;
        font-size: 0.84rem;
      }}
      .vacation-month-form input[type="month"] {{
        min-width: 0;
        width: 100%;
      }}
      .vacation-month-form .knowledge-action {{
        width: 100%;
      }}
      .vacation-weekday {{
        padding: 5px 2px;
        font-size: 0.55rem;
        letter-spacing: 0.04em;
      }}
      .vacation-day {{
        min-height: 64px;
        padding: 4px;
        gap: 3px;
        border-radius: 14px;
      }}
      .vacation-day-number {{
        min-width: 22px;
        min-height: 22px;
        padding: 0 5px;
        font-size: 0.68rem;
      }}
      .vacation-day-badge,
      .vacation-load-row {{
        display: none;
      }}
      .vacation-day-list {{
        gap: 3px;
      }}
      .vacation-entry {{
        padding: 2px 4px;
        border-radius: 8px;
        font-size: 0.58rem;
      }}
      .vacation-entry-more {{
        font-size: 0.58rem;
      }}
      .vacation-insight-grid,
      .vacation-section-grid {{
        grid-template-columns: 1fr;
      }}
      .vacation-checkbox-grid {{
        grid-template-columns: 1fr;
      }}
      .vacation-modal-backdrop {{
        inset: 6px;
        padding: 8px;
        border-radius: 18px;
      }}
      .vacation-modal-card {{
        width: 100%;
        max-height: calc(100dvh - 28px);
        padding: 12px;
        border-radius: 18px;
      }}
      .vacation-modal-head {{
        gap: 4px;
        padding-right: 28px;
      }}
      .vacation-modal-head h3 {{
        font-size: 0.96rem;
      }}
      .vacation-modal-head p,
      .vacation-modal-day-summary span,
      .vacation-modal-day-entry span,
      .vacation-modal-day-entry small {{
        font-size: 0.7rem;
      }}
      .vacation-modal-day-panel {{
        padding: 10px;
        border-radius: 14px;
      }}
      .vacation-modal-day-entry {{
        padding: 7px 8px;
        border-radius: 12px;
      }}
      .vacation-modal-actions .button,
      .vacation-modal-actions .knowledge-action,
      .vacation-modal-delete .knowledge-action {{
        width: 100%;
        justify-content: center;
      }}
      .vacation-modal-close {{
        top: 10px;
        right: 10px;
        width: 30px;
        height: 30px;
      }}
    }}
  </style>
</head>
<body>
  <div class="site-shell">
    <div class="ambient ambient-one"></div>
    <div class="ambient ambient-two"></div>
    <div class="grid-overlay"></div>

    <header class="topbar">
      <a class="brand" href="/" aria-label="Divian-HUB főoldal">
        <span class="brand-mark"></span>
        <span class="brand-text">
          <strong>Divian-HUB</strong>
          <small>Céges modulplatform</small>
        </span>
      </a>

      <nav class="nav">
        <a href="/">Főoldal</a>
        <a href="/#modules">Modulok</a>
      </nav>

      <a class="nav-cta" href="/#divian-ai">Divian-AI</a>
    </header>

    {module_root_open}
      {notice_html}

      <main class="section module-shell">
        {hero_html}

        <div class="{workflow_class}">
          <section class="workflow-panel reveal is-visible">
            {content_html}
          </section>

          {side_column_html}
        </div>
      </main>
    {module_root_close}
  </div>
  {COMMON_SCRIPT_TAG}
  {extra_script}
</body>
</html>"""
    return page.encode("utf-8")


def render_nettfront_form(message: str = "") -> bytes:
    notice_html = ""
    if message:
        notice_html = f'<div class="notice-banner">{html.escape(message)}</div>'

    content_html = f"""
      <div class="tag">PDF -> fordítás -> procurement</div>
      <h2>NettFront számla beolvasó és beszerzési előkészítés</h2>
      <p class="muted-copy">
        Töltsd fel a NettFront számlát PDF-ben. Opcionálisan megadhatsz egy aktuális rendelési fájlt is,
        ekkor a rendszer összehasonlító Excel riportot is készít. A feldolgozás után letölthető lesz az
        invoice CSV, a beszerzési CSV és az összesített ZIP.
      </p>

      <form id="nettfront-upload-form" class="upload-grid" method="post" action="{NETTFRONT_PROCESS_ROUTE}" enctype="multipart/form-data">
        <label class="upload-field">
          <strong>Számla PDF</strong>
          <span class="field-hint">Kötelező bemenet. Ebből készül a fordított cikktörzs és a beszerzési CSV.</span>
          <input id="nettfront-invoice" type="file" name="invoice_pdf" accept=".pdf,application/pdf" required />
          <span class="field-hint" id="nettfront-invoice-state">Támogatott formátum: PDF</span>
        </label>

        <label class="upload-field">
          <strong>Aktuális rendelés</strong>
          <span class="field-hint">Nem kötelező. XLSX, XLSM vagy CSV esetén összehasonlító report is készül.</span>
          <input id="nettfront-order" type="file" name="order_file" accept=".xlsx,.xlsm,.csv" />
          <span class="field-hint" id="nettfront-order-state">Opcionális feltöltés</span>
        </label>
      </form>

      <div class="action-row">
        <button class="button button-primary" type="submit" form="nettfront-upload-form">Procurement csomag készítése</button>
      </div>
    """

    side_html = """
      <article class="stack-card">
        <h3>Mit gyárt a modul?</h3>
        <ul>
          <li>Fordított számla sorok `invoice-output.csv` formában.</li>
          <li>Kész Beszerzés lista a következő lépéshez.</li>
          <li>Opcionálisan összehasonlító `compare-output.xlsx` riport.</li>
          <li>Egyben letölthető ZIP csomag.</li>
        </ul>
      </article>

      <article class="stack-card">
        <h3>Launch workflow</h3>
        <p>
          A feldolgozás után egy külön gombbal elindítható az import-segéd. A beszerzési
          ablakban a `Shift + Space` billentyűkombináció indítja el a tényleges importot.
        </p>
      </article>

      <article class="stack-card">
        <h3>Megjegyzés</h3>
        <p>
          A module reuse-olja az eredeti repo fordítási tábláját és az alkatrész-mapet, így a procurement
          kimenet ugyanazon szabályok szerint készül, mint a meglévő projektben.
        </p>
      </article>
    """

    extra_script = """
<script>
  const bindFileState = (inputId, stateId, emptyText) => {
    const input = document.getElementById(inputId);
    const state = document.getElementById(stateId);
    if (!input || !state) return;

    input.addEventListener("change", () => {
      const file = input.files && input.files[0];
      if (!file) {
        state.textContent = emptyText;
        return;
      }
      state.textContent = `${file.name} • ${(file.size / 1024 / 1024).toFixed(2)} MB`;
    });
  };

  bindFileState("nettfront-invoice", "nettfront-invoice-state", "Támogatott formátum: PDF");
  bindFileState("nettfront-order", "nettfront-order-state", "Opcionális feltöltés");
</script>"""

    return _render_nettfront_layout(
        heading="NettFront számlaolvasó egy egységes platform alatt",
        lead="PDF-feldolgozás, fordítás, procurement CSV és opcionális összehasonlító Excel ugyanabban a Divian-HUB élményben.",
        intro_label="Második éles modul",
        content_html=content_html,
        side_html=side_html,
        notice_html=notice_html,
        extra_script=extra_script,
    )


def render_nettfront_result(job_id: str, metadata: dict, message: str = "", success: bool = False) -> bytes:
    notice_html = ""
    if message:
        extra_class = " success" if success else ""
        notice_html = f'<div class="notice-banner{extra_class}">{html.escape(message)}</div>'

    compare_button = ""
    if metadata.get("has_compare"):
        compare_button = f"""
          <a class="button button-secondary" href="{NETTFRONT_DOWNLOAD_PREFIX}/{job_id}/compare-xlsx">
            Compare Excel letöltése
          </a>
        """

    missing_html = "<p class='status-note'>Minden cikkkódhoz találtunk procurement mappinget.</p>"
    missing_codes = metadata.get("missing_codes") or []
    if missing_codes:
        missing_items = "".join(f"<li>{html.escape(code)}</li>" for code in missing_codes)
        missing_html = f"<ul class='missing-list'>{missing_items}</ul>"

    order_note = "Nem töltöttél fel rendelési fájlt, ezért most csak az invoice/procurement kimenetek készültek el."
    if metadata.get("has_compare"):
        order_note = "Az aktuális rendelés összehasonlító riportja is elkészült a csomagban."

    content_html = f"""
      <div class="tag">Feldolgozás kész</div>
      <h2>NettFront procurement csomag elkészült</h2>
      <p class="muted-copy">{html.escape(order_note)}</p>

      <div class="summary-grid">
        <article class="summary-card">
          <strong>{metadata.get("invoice_row_count", 0)}</strong>
          <span>felismert számlasor</span>
        </article>
        <article class="summary-card">
          <strong>{metadata.get("order_row_count", 0)}</strong>
          <span>beolvasott rendelési sor</span>
        </article>
        <article class="summary-card">
          <strong>{len(missing_codes)}</strong>
          <span>hiányzó procurement mapping</span>
        </article>
      </div>

      <div class="download-grid">
        <article class="download-card">
          <strong>Invoice CSV</strong>
          <p>Fordított és kódolt számlasorok a rendszerből.</p>
          <a class="button button-secondary" href="{NETTFRONT_DOWNLOAD_PREFIX}/{job_id}/invoice-csv">invoice-output.csv</a>
        </article>

        <article class="download-card">
          <strong>Beszerzési CSV</strong>
          <p>Az a kimenet, amivel az importfolyamat továbbvihető.</p>
          <a class="button button-secondary" href="{NETTFRONT_DOWNLOAD_PREFIX}/{job_id}/procurement-csv">rendeles_sima.csv</a>
        </article>

        <article class="download-card">
          <strong>Teljes csomag</strong>
          <p>Minden generált fájl egyetlen ZIP-ben.</p>
          <a class="button button-secondary" href="{NETTFRONT_DOWNLOAD_PREFIX}/{job_id}/bundle-zip">nettfront-output.zip</a>
        </article>

        <article class="download-card">
          <strong>Összehasonlító riport</strong>
          <p>Csak akkor érhető el, ha rendelési fájlt is feltöltöttél.</p>
          {compare_button or "<span class='status-note'>Ebben a futásban nem készült összehasonlító Excel.</span>"}
        </article>
      </div>

      <form class="launch-form" method="post" action="{NETTFRONT_LAUNCH_PREFIX}/{job_id}">
        <div class="action-row">
          <button class="button button-primary" type="submit">Beszerzési folyamat indítása</button>
          <a class="button button-secondary" href="{NETTFRONT_ROUTE}">Új feldolgozás</a>
        </div>
      </form>
    """

    side_html = f"""
      <article class="stack-card">
        <h3>Állapot</h3>
        <ul class="status-list">
          <li>Invoice sorok: {metadata.get("invoice_row_count", 0)}</li>
          <li>Rendelési sorok: {metadata.get("order_row_count", 0)}</li>
          <li>Összehasonlító riport: {"igen" if metadata.get("has_compare") else "nem"}</li>
        </ul>
      </article>

      <article class="stack-card">
        <h3>Hiányzó kódok</h3>
        {missing_html}
      </article>

      <article class="stack-card">
        <h3>Launch információ</h3>
        <p>
          A launch gomb egy import-segédet indít el. Nyisd meg a beszerzési ablakot,
          majd a `Shift + Space` billentyűkombinációval indítsd az importot.
        </p>
      </article>
    """

    return _render_nettfront_layout(
        heading="A NettFront feldolgozás elkészült",
        lead="Innen indítható az import-segéd, az import pedig Shift + Space-re indul.",
        intro_label="Procurement output ready",
        content_html=content_html,
        side_html=side_html,
        notice_html=notice_html,
    )


def _render_file_bind_script(bindings: list[tuple[str, str, str]]) -> str:
    lines = [
        "<script>",
        "  const bindFileState = (inputId, stateId, emptyText) => {",
        "    const input = document.getElementById(inputId);",
        "    const state = document.getElementById(stateId);",
        "    if (!input || !state) return;",
        "",
        "    input.addEventListener(\"change\", () => {",
        "      const file = input.files && input.files[0];",
        "      if (!file) {",
        "        state.textContent = emptyText;",
        "        return;",
        "      }",
        "      state.textContent = `${file.name} • ${(file.size / 1024 / 1024).toFixed(2)} MB`;",
        "    });",
        "  };",
        "",
    ]
    for input_id, state_id, empty_text in bindings:
        lines.append(f'  bindFileState("{input_id}", "{state_id}", "{empty_text}");')
    lines.extend(["</script>"])
    return "\n".join(lines)


def render_nettfront_hub(message: str = "") -> bytes:
    notice_html = ""
    if message:
        notice_html = f'<div class="notice-banner">{html.escape(message)}</div>'

    content_html = f"""
      <div class="tag">NettFront workflow split</div>
      <h2>Három külön felület a három külön feladatra</h2>
      <p class="muted-copy">
        A korábbi közös modult szétválasztottam. Az egyik nézet a számlából készít procurement kimenetet,
        a másik pedig a már meglévő beszerzést hasonlítja össze a számlával.
      </p>

      <div class="route-grid">
        <a class="route-card" href="{NETTFRONT_PROCUREMENT_ROUTE}">
          <div class="tag">Procurement</div>
          <strong>Számla -> beszerzés</strong>
          <p>Invoice CSV, Beszerzés lista, ZIP csomag és külön indítható import-segéd.</p>
        </a>

        <a class="route-card" href="{NETTFRONT_ORDER_ROUTE}">
          <div class="tag">Order suggestion</div>
          <strong>Excel -> rendelési javaslat</strong>
          <p>Raktár Excelből kész javaslat, szerkeszthető mennyiségekkel és jóváhagyható kész rendeléssel.</p>
        </a>

        <a class="route-card" href="{NETTFRONT_COMPARE_ROUTE}">
          <div class="tag">Compare</div>
          <strong>Számla vs. meglévő beszerzés</strong>
          <p>Számla és rendelési fájl összehasonlítása két munkalapos, színezett Excel riporttal.</p>
        </a>
      </div>
    """

    side_html = """
      <article class="stack-card">
        <h3>Mi változott?</h3>
        <ul>
          <li>A három külön workflow most külön felületet kapott.</li>
          <li>A rendelési javaslat most külön Excel-alapú modul.</li>
          <li>Az összehasonlítás továbbra is önálló, célzott belépési pont.</li>
        </ul>
      </article>

      <article class="stack-card">
        <h3>Mi maradt?</h3>
        <p>
          A fordítási tábla, az alkatrész-mapping és az alap PDF-feldolgozási logika változatlanul az eredeti
          projektből jön, csak az élmény és a folyamatok lettek rendezettebbek.
        </p>
      </article>
    """

    return _render_nettfront_layout(
        heading="NettFront modulok egységes, sötét kezelőfelületen",
        lead="Válaszd ki, hogy számlából beszerzést készítesz, raktár Excelből rendelési javaslatot kérsz, vagy egy meglévő rendelést ellenőrzöl.",
        intro_label="Split workflow",
        content_html=content_html,
        side_html=side_html,
        notice_html=notice_html,
    )


def _order_safe_number(value) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(" ", "")
    if not text:
        return 0.0
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _order_parse_quantity_input(value: str) -> tuple[float, bool]:
    text = str(value or "").strip()
    if not text:
        return 0.0, True
    sanitized = text.replace(" ", "")
    if "," in sanitized and "." in sanitized:
        if sanitized.rfind(",") > sanitized.rfind("."):
            sanitized = sanitized.replace(".", "").replace(",", ".")
        else:
            sanitized = sanitized.replace(",", "")
    elif "," in sanitized:
        sanitized = sanitized.replace(",", ".")
    try:
        return max(0.0, float(sanitized)), True
    except ValueError:
        return 0.0, False


def _format_order_metric(value) -> str:
    if value in (None, ""):
        return "—"
    raw = str(value).strip()
    if not raw:
        return "—"
    if not any(char.isdigit() for char in raw):
        return raw
    number = _order_safe_number(value)
    decimals = 0 if abs(number - round(number)) < 1e-9 else 2
    return _format_eu_number(number, decimals)


def _format_order_input_value(value) -> str:
    number = _order_safe_number(value)
    if abs(number - round(number)) < 1e-9:
        return str(int(round(number)))
    return f"{number:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _count_positive_order_rows(rows: list[NettfrontOrderRow]) -> int:
    return sum(1 for row in rows if _order_safe_number(row.order_qty) > 0)


def _nettfront_order_row_to_dict(row: NettfrontOrderRow) -> dict:
    return {
        "row_id": row.row_id,
        "part_number": row.part_number,
        "description": row.description,
        "stock_unit": row.stock_unit,
        "current_stock": row.current_stock,
        "confirmed_demand": row.confirmed_demand,
        "open_procurement": row.open_procurement,
        "safe_stock": row.safe_stock,
        "capacity": row.capacity,
        "order_qty": row.order_qty,
        "color": row.color,
        "length": row.length,
        "width": row.width,
        "is_super_matt": row.is_super_matt,
    }


def _nettfront_order_row_from_dict(payload: dict) -> NettfrontOrderRow:
    return NettfrontOrderRow(
        row_id=str(payload.get("row_id", "")).strip(),
        part_number=str(payload.get("part_number", "")).strip(),
        description=str(payload.get("description", "")).strip(),
        stock_unit=payload.get("stock_unit"),
        current_stock=payload.get("current_stock"),
        confirmed_demand=payload.get("confirmed_demand"),
        open_procurement=payload.get("open_procurement"),
        safe_stock=payload.get("safe_stock"),
        capacity=payload.get("capacity"),
        order_qty=_order_safe_number(payload.get("order_qty")),
        color=str(payload.get("color", "")).strip(),
        length=_order_safe_number(payload.get("length")),
        width=_order_safe_number(payload.get("width")),
        is_super_matt=bool(payload.get("is_super_matt")),
    )


def _read_nettfront_order_rows(job_dir: Path) -> list[NettfrontOrderRow]:
    rows_path = job_dir / "suggestions.json"
    if not rows_path.exists():
        return []
    try:
        payload = json.loads(rows_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [_nettfront_order_row_from_dict(item) for item in payload if isinstance(item, dict)]


def _write_nettfront_order_rows(job_dir: Path, rows: list[NettfrontOrderRow]) -> None:
    payload = [_nettfront_order_row_to_dict(row) for row in rows]
    (job_dir / "suggestions.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _nettfront_order_quantity_text(value: float) -> str:
    number = _order_safe_number(value)
    if abs(number - round(number)) < 1e-9:
        return str(int(round(number)))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _normalize_nettfront_part_number(value: object) -> str:
    text = str(value or "").strip().upper()
    return re.sub(r"\s+", "", text)


def _nettfront_parts_list_header_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", _normalize_nettfront_part_number(value))


def _nettfront_order_part_number_aliases(value: object) -> list[str]:
    normalized = _normalize_nettfront_part_number(value)
    if not normalized:
        return []

    aliases = [normalized]
    for base_tag, secondary_tag, merged_tag in (("KAF", "KAFS", "KAFU"), ("PRA", "PRAS", "PRAU")):
        match = re.match(rf"^(NFA[^_]*_ANT)_{merged_tag}_(.+)$", normalized)
        if not match:
            continue
        base = match.group(1)
        suffix = match.group(2)
        aliases.extend(
            [
                f"{base}_{base_tag}_{suffix}",
                f"{base}_{secondary_tag}_{suffix}",
            ]
        )
        break

    unique_aliases: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        if alias in seen:
            continue
        seen.add(alias)
        unique_aliases.append(alias)
    return unique_aliases


def _nettfront_order_display_part_number(value: object) -> str:
    aliases = _nettfront_order_part_number_aliases(value)
    if not aliases:
        return ""
    if len(aliases) >= 2 and aliases[0] != aliases[1]:
        return aliases[1]
    return aliases[0]


def _load_nettfront_parts_list_from_bytes(payload: bytes, file_name: str) -> list[str]:
    file_name = str(file_name or "").strip().lower()
    values: list[str] = []

    if file_name.endswith((".xlsx", ".xlsm")):
        if load_workbook is None:
            raise ValueError("Az Excel feldolgozáshoz hiányzik az openpyxl csomag.")
        workbook = load_workbook(io.BytesIO(payload), data_only=True, read_only=True)
        worksheet = workbook.active
        for row in worksheet.iter_rows(values_only=True):
            first_value = None
            for cell in row:
                if cell not in (None, ""):
                    first_value = cell
                    break
            normalized = _normalize_nettfront_part_number(first_value)
            if normalized:
                values.append(normalized)
    elif file_name.endswith(".csv"):
        decoded = None
        for encoding in ("utf-8-sig", "cp1250", "cp1252", "latin-1"):
            try:
                decoded = payload.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if decoded is None:
            raise ValueError("A CSV fájl kódolását nem tudtam beolvasni.")
        for row in csv.reader(io.StringIO(decoded)):
            first_value = next((cell for cell in row if str(cell).strip()), "")
            normalized = _normalize_nettfront_part_number(first_value)
            if normalized:
                values.append(normalized)
    else:
        raise ValueError("A friss alkatrészlista csak XLSX, XLSM vagy CSV lehet.")

    unique_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not unique_values and _nettfront_parts_list_header_key(value) in {
            "ALKATRESZ",
            "ALKATRESZSZAM",
            "ALKATRSZAM",
            "CIKKSZAM",
            "PARTNUMBER",
            "PARTNUM",
        }:
            continue
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def _build_nettfront_order_import_csv(rows: list[NettfrontOrderRow]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
    for row in rows:
        if _order_safe_number(row.order_qty) <= 0:
            continue
        part_number = _nettfront_order_display_part_number(row.part_number) or row.part_number.strip()
        if not part_number:
            continue
        writer.writerow([part_number, _nettfront_order_quantity_text(row.order_qty)])
    return buffer.getvalue().encode("utf-8-sig")


def _write_nettfront_order_bundle(job_dir: Path, metadata: dict) -> None:
    bundle_name = str(metadata.get("bundle_name", "nettfront-rendeles-output.zip")).strip() or "nettfront-rendeles-output.zip"
    bundle_files: list[str] = ["metadata.json", "suggestions.json", "rendelesi-javaslat.xlsx"]

    source_stock_file = str(metadata.get("source_stock_file", "")).strip()
    if source_stock_file:
        bundle_files.append(source_stock_file)

    source_parts_file = str(metadata.get("source_parts_file", "")).strip()
    if source_parts_file:
        bundle_files.append(source_parts_file)

    source_avg_file = str(metadata.get("source_average_file", "")).strip()
    if source_avg_file:
        bundle_files.append(source_avg_file)

    approved_file = str(metadata.get("approved_file", "")).strip()
    if approved_file:
        bundle_files.append(approved_file)

    import_file = str(metadata.get("import_file", "")).strip()
    if import_file:
        bundle_files.append(import_file)

    seen: set[str] = set()
    existing_files = []
    for file_name in bundle_files:
        if file_name in seen:
            continue
        seen.add(file_name)
        if (job_dir / file_name).exists():
            existing_files.append(file_name)

    (job_dir / bundle_name).write_bytes(create_bundle_archive(job_dir, existing_files))


def _write_nettfront_order_job(
    result,
    stock_name: str,
    stock_bytes: bytes,
    parts_name: str = "",
    parts_bytes: bytes | None = None,
    parts_count: int = 0,
) -> tuple[str, dict]:
    job_id = uuid.uuid4().hex[:12]
    job_dir = _job_runtime_dir("order") / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    stock_suffix = Path(stock_name).suffix.lower() or ".xlsx"
    source_stock_file = f"source-stock{stock_suffix}"
    (job_dir / source_stock_file).write_bytes(stock_bytes)
    (job_dir / "rendelesi-javaslat.xlsx").write_bytes(result.suggestion_workbook)
    _write_nettfront_order_rows(job_dir, result.rows)

    metadata = {
        "job_id": job_id,
        "job_type": "order",
        "bundle_name": "nettfront-rendeles-output.zip",
        "source_stock_name": stock_name,
        "source_stock_file": source_stock_file,
        "suggestion_row_count": len(result.rows),
        "merged_variant_count": result.merged_variant_count,
        "filtered_stock_count": result.filtered_stock_count,
        "added_super_matt_count": result.added_super_matt_count,
        "total_m2": result.total_m2,
        "avg_row_count": result.avg_row_count,
        "approved_row_count": 0,
        "approved_total_m2": 0.0,
        "approved_file": "",
        "approved_generated_at": "",
    }

    if parts_name and parts_bytes is not None:
        parts_suffix = Path(parts_name).suffix.lower() or ".xlsx"
        parts_file = f"source-parts{parts_suffix}"
        (job_dir / parts_file).write_bytes(parts_bytes)
        metadata["source_parts_name"] = parts_name
        metadata["source_parts_file"] = parts_file
        metadata["source_parts_count"] = max(0, int(parts_count))

    (job_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_nettfront_order_bundle(job_dir, metadata)
    return job_id, metadata


def _persist_nettfront_order_approval(job_dir: Path, metadata: dict, rows: list[NettfrontOrderRow]) -> dict:
    suggestion_workbook = rows_to_suggestion_workbook(rows)
    approved_title = f"Divian-Mega Kft. Rendelés {datetime.now().strftime('%Y.%m.%d.')}"
    approved_workbook = rows_to_approved_workbook(rows, approved_title)
    import_csv = _build_nettfront_order_import_csv(rows)

    (job_dir / "rendelesi-javaslat.xlsx").write_bytes(suggestion_workbook)
    (job_dir / "rendeles-jovahagyott.xlsx").write_bytes(approved_workbook)
    (job_dir / "rendeles_sima.csv").write_bytes(import_csv)
    _write_nettfront_order_rows(job_dir, rows)

    updated_metadata = {
        **metadata,
        "suggestion_row_count": len(rows),
        "total_m2": calc_total_m2_from_rows(rows),
        "approved_row_count": _count_positive_order_rows(rows),
        "approved_total_m2": calc_total_m2_from_rows(rows),
        "approved_file": "rendeles-jovahagyott.xlsx",
        "import_file": "rendeles_sima.csv",
        "approved_generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    (job_dir / "metadata.json").write_text(json.dumps(updated_metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_nettfront_order_bundle(job_dir, updated_metadata)
    return updated_metadata


def render_nettfront_order_form(message: str = "", success: bool = False) -> bytes:
    notice_html = ""
    if message:
        extra_class = " success" if success else ""
        notice_html = f'<div class="notice-banner{extra_class}">{html.escape(message)}</div>'

    content_html = f"""
      <div class="order-shell">
        <section class="order-hero-card">
          <div class="order-hero-grid">
            <div class="order-copy">
              <div class="tag">Excel -> rendelési javaslat</div>
              <strong>NettFront rendelési javaslat.</strong>
              <p>Feltöltöd a raktár Excelt, átnézed a javasolt darabszámokat, majd jóváhagyod a kész rendelést.</p>
              <div class="order-flow" aria-hidden="true">
                <span>Excel</span>
                <i></i>
                <span>Javaslat</span>
                <i></i>
                <span>Kész rendelés</span>
              </div>
            </div>

            <div class="order-visual" aria-hidden="true">
              <div class="order-visual-list">
                <div class="order-visual-row">
                  <span>Excel</span>
                  <i></i>
                  <strong>Beolvasás</strong>
                </div>
                <div class="order-visual-row">
                  <span>Javaslat</span>
                  <i></i>
                  <strong>Ellenőrzés</strong>
                </div>
                <div class="order-visual-row">
                  <span>Rendelés</span>
                  <i></i>
                  <strong>Jóváhagyás</strong>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="order-upload-card">
          <div class="order-upload-head">
            <strong>Feltöltés</strong>
            <p>Egy raktár Excel kell. A rendszer kiszámolja a rendelési javaslatot.</p>
          </div>

          <form id="nettfront-order-form" class="order-upload-form" method="post" action="{NETTFRONT_ORDER_PROCESS_ROUTE}" enctype="multipart/form-data">
            <div class="order-dropzone" id="nettfront-order-dropzone">
              <input
                id="nettfront-order-stock"
                class="order-file-input"
                type="file"
                name="stock_file"
                accept=".xlsx,.xlsm,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,text/csv"
                required
              />
              <label class="order-dropzone-surface" for="nettfront-order-stock">
                <div class="order-dropzone-copy">
                  <span class="order-dropzone-chip">Excel</span>
                  <strong>Raktárfájl kiválasztása</strong>
                  <p>Kattints ide, vagy húzd be a fájlt.</p>
                </div>
                <span class="order-file-state" id="nettfront-order-stock-state">Támogatott formátum: XLSX, XLSM, CSV</span>
              </label>
            </div>

            <div class="order-optional-upload">
              <div class="order-optional-copy">
                <strong>Friss alkatrészlista</strong>
                <p>Opcionális egyoszlopos lista. A jóváhagyásnál ebből ellenőrizzük a kiválasztott cikkszámokat, hogy a kész rendelés bevételezhető legyen.</p>
              </div>

              <div class="order-dropzone is-secondary" id="nettfront-order-parts-dropzone">
                <input
                  id="nettfront-order-parts"
                  class="order-file-input"
                  type="file"
                  name="parts_file"
                  accept=".xlsx,.xlsm,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,text/csv"
                />
                <label class="order-dropzone-surface" for="nettfront-order-parts">
                  <div class="order-dropzone-copy">
                    <span class="order-dropzone-chip">Opcionális</span>
                    <strong>Friss lista kiválasztása</strong>
                    <p>Kattints ide, vagy húzd be a fájlt.</p>
                  </div>
                  <span class="order-file-state" id="nettfront-order-parts-state">Támogatott formátum: XLSX, XLSM, CSV</span>
                </label>
              </div>
            </div>

            <div class="order-action-row">
              <button class="button button-primary" type="submit" id="nettfront-order-submit">Javaslat készítése</button>
              <span class="inline-note">A kész lista külön oldalon nyílik meg, ott tudod jóváhagyni.</span>
            </div>
          </form>
        </section>
      </div>
    """

    extra_script = """
<style>
  .order-shell {
    display: grid;
    gap: 16px;
  }
  .order-hero-card,
  .order-upload-card {
    position: relative;
    overflow: hidden;
    border-radius: 24px;
    border: 1px solid var(--border);
    background: linear-gradient(180deg, rgba(10, 16, 28, 0.94), rgba(8, 13, 22, 0.96));
    box-shadow: var(--shadow);
  }
  .order-hero-card::before,
  .order-upload-card::before {
    content: "";
    position: absolute;
    inset: 0;
    background: radial-gradient(circle at top left, rgba(67, 222, 207, 0.1), transparent 32%);
    pointer-events: none;
  }
  .order-hero-grid {
    position: relative;
    z-index: 1;
    display: grid;
    grid-template-columns: minmax(0, 1.15fr) minmax(260px, 0.85fr);
    gap: 16px;
    align-items: stretch;
    padding: 24px;
  }
  .order-copy {
    display: grid;
    gap: 12px;
    align-content: start;
  }
  .order-copy strong {
    font-family: "Space Grotesk", sans-serif;
    font-size: clamp(1.7rem, 3.8vw, 2.5rem);
    line-height: 1;
  }
  .order-copy p,
  .order-upload-head p {
    margin: 0;
    color: var(--muted);
    line-height: 1.6;
    max-width: 58ch;
  }
  .order-flow {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 2px;
    color: var(--muted);
    font-size: 0.84rem;
  }
  .order-flow span {
    display: inline-flex;
    align-items: center;
    min-height: 34px;
    padding: 0 12px;
    border-radius: 999px;
    border: 1px solid rgba(255, 255, 255, 0.07);
    background: rgba(255, 255, 255, 0.035);
  }
  .order-flow i {
    width: 18px;
    height: 1px;
    background: linear-gradient(90deg, rgba(67, 222, 207, 0.18), rgba(67, 222, 207, 0.62));
  }
  .order-visual {
    position: relative;
    z-index: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 212px;
    padding: 18px;
    border-radius: 22px;
    border: 1px solid rgba(255, 255, 255, 0.06);
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.02));
  }
  .order-visual-list {
    display: grid;
    gap: 12px;
    width: min(100%, 240px);
  }
  .order-visual-row {
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 12px;
    align-items: center;
    min-height: 56px;
    padding: 0 16px;
    border-radius: 18px;
    border: 1px solid rgba(255, 255, 255, 0.07);
    background: rgba(255, 255, 255, 0.03);
  }
  .order-visual-row span {
    color: var(--muted);
    font-size: 0.82rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .order-visual-row i {
    height: 1px;
    background: linear-gradient(90deg, rgba(67, 222, 207, 0.16), rgba(67, 222, 207, 0.56));
  }
  .order-visual-row strong {
    font-family: "Space Grotesk", sans-serif;
    font-size: 0.94rem;
    font-weight: 600;
  }
  .order-upload-card {
    padding: 22px;
  }
  .order-upload-head {
    display: grid;
    gap: 6px;
    margin-bottom: 14px;
  }
  .order-upload-head strong {
    font-family: "Space Grotesk", sans-serif;
  }
  .order-upload-form {
    display: grid;
    gap: 16px;
  }
  .order-optional-upload {
    display: grid;
    gap: 12px;
    padding: 16px;
    border-radius: 20px;
    border: 1px solid rgba(255, 255, 255, 0.06);
    background: rgba(255, 255, 255, 0.025);
  }
  .order-optional-copy {
    display: grid;
    gap: 6px;
  }
  .order-optional-copy strong {
    font-family: "Space Grotesk", sans-serif;
    font-size: 0.96rem;
  }
  .order-optional-copy p {
    margin: 0;
    color: var(--muted);
    line-height: 1.5;
  }
  .order-dropzone {
    position: relative;
  }
  .order-dropzone.is-secondary .order-dropzone-surface {
    min-height: 138px;
    padding: 18px 20px;
    border-radius: 20px;
    border-style: solid;
    border-color: rgba(255, 255, 255, 0.1);
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0.012));
  }
  .order-file-input {
    position: absolute;
    inset: 0;
    opacity: 0;
    pointer-events: none;
  }
  .order-dropzone-surface {
    display: grid;
    gap: 14px;
    min-height: 176px;
    padding: 22px;
    border-radius: 24px;
    border: 1px dashed rgba(67, 222, 207, 0.24);
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.028), rgba(255, 255, 255, 0.016));
    cursor: pointer;
    transition:
      border-color 180ms ease,
      transform 180ms ease,
      box-shadow 180ms ease;
  }
  .order-dropzone.is-dragover .order-dropzone-surface,
  .order-dropzone-surface:hover {
    border-color: rgba(67, 222, 207, 0.42);
    transform: translateY(-1px);
    box-shadow: 0 18px 42px rgba(0, 0, 0, 0.22);
  }
  .order-dropzone-copy {
    display: grid;
    gap: 8px;
    justify-items: start;
  }
  .order-dropzone-chip {
    display: inline-flex;
    align-items: center;
    min-height: 30px;
    padding: 0 12px;
    border-radius: 999px;
    border: 1px solid rgba(255, 255, 255, 0.07);
    background: rgba(255, 255, 255, 0.04);
    color: var(--muted);
    font-size: 0.78rem;
    white-space: nowrap;
  }
  .order-dropzone-copy strong {
    font-size: 1rem;
  }
  .order-file-state {
    font-size: 0.9rem;
    color: var(--muted);
  }
  .order-action-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
  }
  @media (max-width: 960px) {
    .order-hero-grid {
      grid-template-columns: minmax(0, 1fr);
    }
  }
  @media (max-width: 640px) {
    .order-hero-grid,
    .order-upload-card {
      padding: 18px;
    }
    .order-dropzone-surface {
      min-height: 156px;
      padding: 18px;
    }
    .order-action-row {
      align-items: stretch;
      flex-direction: column;
    }
    .order-action-row .button {
      width: 100%;
    }
  }
</style>
<script>
  (() => {
    const stockInput = document.getElementById("nettfront-order-stock");
    const stockState = document.getElementById("nettfront-order-stock-state");
    const stockDropzone = document.getElementById("nettfront-order-dropzone");
    const partsInput = document.getElementById("nettfront-order-parts");
    const partsState = document.getElementById("nettfront-order-parts-state");
    const partsDropzone = document.getElementById("nettfront-order-parts-dropzone");
    const form = document.getElementById("nettfront-order-form");
    const submitButton = document.getElementById("nettfront-order-submit");
    if (!stockInput || !stockState || !stockDropzone || !partsInput || !partsState || !partsDropzone || !form || !submitButton) return;

    const updateState = (input, state, emptyLabel) => {
      const file = input.files && input.files[0];
      if (!file) {
        state.textContent = emptyLabel;
        return;
      }
      state.textContent = `${file.name} • ${(file.size / 1024 / 1024).toFixed(2)} MB`;
    };

    const bindDropzone = (dropzone) => {
      ["dragenter", "dragover"].forEach((eventName) => {
        dropzone.addEventListener(eventName, (event) => {
          event.preventDefault();
          dropzone.classList.add("is-dragover");
        });
      });

      ["dragleave", "drop"].forEach((eventName) => {
        dropzone.addEventListener(eventName, (event) => {
          event.preventDefault();
          dropzone.classList.remove("is-dragover");
        });
      });
    };

    bindDropzone(stockDropzone);
    bindDropzone(partsDropzone);

    stockInput.addEventListener("change", () => updateState(stockInput, stockState, "Támogatott formátum: XLSX, XLSM, CSV"));
    partsInput.addEventListener("change", () => updateState(partsInput, partsState, "Támogatott formátum: XLSX, XLSM, CSV"));
    form.addEventListener("submit", () => {
      submitButton.textContent = "Javaslat készül...";
      submitButton.disabled = true;
    });
  })();
</script>
"""

    return _render_nettfront_layout(
        heading="",
        lead="",
        intro_label="",
        content_html=content_html,
        side_html="",
        notice_html=notice_html,
        extra_script=extra_script,
        single_column=True,
    )


def render_nettfront_order_result(job_id: str, metadata: dict, message: str = "", success: bool = False) -> bytes:
    notice_html = ""
    if message:
        extra_class = " success" if success else ""
        notice_html = f'<div class="notice-banner{extra_class}">{html.escape(message)}</div>'

    job_dir, _ = _read_nettfront_job("order", job_id)
    rows = _read_nettfront_order_rows(job_dir) if job_dir is not None else []
    suggestion_count = len(rows)
    positive_count = _count_positive_order_rows(rows)
    total_m2 = calc_total_m2_from_rows(rows)
    approved_file = str(metadata.get("approved_file", "")).strip()
    approved_ready = bool(approved_file and job_dir is not None and (job_dir / approved_file).exists())
    helper_state = get_procurement_helper_state(job_dir)
    helper_running = bool(helper_state.get("running"))
    import_file = str(metadata.get("import_file", "")).strip()
    import_ready = bool(import_file and job_dir is not None and (job_dir / import_file).exists())
    source_stock_name = str(metadata.get("source_stock_name", "")).strip() or "Feltöltött raktárfájl"
    source_parts_name = str(metadata.get("source_parts_name", "")).strip() or str(metadata.get("source_average_name", "")).strip()
    source_parts_count = int(metadata.get("source_parts_count", 0) or 0)

    table_html = """
      <div class="order-empty-state">
        <strong>Nincs rendelési javaslat.</strong>
        <p>A feltöltött fájl alapján most nem találtam rendelésre váró tételt.</p>
      </div>
    """
    if rows:
        row_html = []
        for row in rows:
            description = html.escape(row.description or "Megnevezés nélkül")
            display_part_number = _nettfront_order_display_part_number(row.part_number)
            part_number = html.escape(display_part_number or row.part_number or "Nincs cikkszám")
            color_value = html.escape(row.color.strip() or "Nincs színadat")
            current_stock = html.escape(_format_order_metric(row.current_stock))
            safe_stock = html.escape(_format_order_metric(row.safe_stock))
            capacity = html.escape(_format_order_metric(row.capacity))
            qty_value = html.escape(_format_order_input_value(row.order_qty))
            super_matt_html = '<span class="order-inline-badge">SM</span>' if row.is_super_matt else ""
            row_html.append(
                f"""
                <tr>
                  <td>
                    <div class="order-item-main">
                      <strong>{description}</strong>
                      <span>{part_number}</span>
                    </div>
                  </td>
                  <td>
                    <div class="order-color-stack">
                      <span class="order-color-text">{color_value}</span>
                      {super_matt_html}
                    </div>
                  </td>
                  <td class="is-metric">{current_stock}</td>
                  <td class="is-metric">{safe_stock}</td>
                  <td class="is-metric">{capacity}</td>
                  <td>
                    <input
                      class="order-qty-input"
                      type="text"
                      inputmode="decimal"
                      name="qty__{html.escape(row.row_id)}"
                      value="{qty_value}"
                    />
                  </td>
                </tr>
                """
            )
        table_html = f"""
          <form method="post" action="{NETTFRONT_ORDER_APPROVE_PREFIX}/{job_id}">
            <div class="order-table-wrap">
              <table class="order-table">
                <thead>
                  <tr>
                    <th>Tétel</th>
                    <th>Szín</th>
                    <th class="is-metric">Rend.áll</th>
                    <th class="is-metric">Biztonsági</th>
                    <th class="is-metric">Tárolható</th>
                    <th class="is-metric">Rendelés</th>
                  </tr>
                </thead>
                <tbody>
                  {''.join(row_html)}
                </tbody>
              </table>
            </div>

            <div class="order-approve-bar">
              <span class="inline-note">A 0 mennyiség azt jelenti, hogy az adott tétel nem kerül be a kész rendelésbe.</span>
              <button class="button button-primary" type="submit">Jóváhagyás és kész rendelés</button>
            </div>
          </form>
        """

    helper_action_html = ""
    helper_hint_html = ""
    if approved_ready and import_ready:
        if helper_running:
            helper_action_html = f"""
              <form method="post" action="{NETTFRONT_ORDER_STOP_PREFIX}/{job_id}">
                <button class="button button-primary" type="submit">Leállítás</button>
              </form>
            """
            helper_hint_html = '<p class="order-helper-copy">A bevételezési segéd fut. Nyisd meg a bevételezési ablakot, majd Shift + Space indítja az importot. Kilépés: ESC.</p>'
        else:
            helper_action_html = f"""
              <form method="post" action="{NETTFRONT_ORDER_LAUNCH_PREFIX}/{job_id}">
                <button class="button button-primary" type="submit">Bevételezés indítása</button>
              </form>
            """
            helper_hint_html = '<p class="order-helper-copy">A kész rendelés bevételezhető. Indítsd a segédet, majd a bevételezési ablakban Shift + Space indítja az importot. Kilépés: ESC.</p>'

    content_html = f"""
      <div class="order-result-shell">
        <section class="order-result-card">
          <div class="order-result-head">
            <div class="tag">Rendelési javaslat</div>
            <strong>Átnézés után egy gombbal kész rendelés lesz belőle.</strong>
            <p>{html.escape(source_stock_name)}</p>
          </div>

          <div class="order-summary-grid">
            <article class="order-summary-card">
              <strong>{suggestion_count}</strong>
              <span>javasolt tétel</span>
            </article>
            <article class="order-summary-card">
              <strong>{positive_count}</strong>
              <span>jóváhagyásra kész sor</span>
            </article>
            <article class="order-summary-card">
              <strong>{html.escape(_format_order_metric(total_m2))}</strong>
              <span>becsült összes m²</span>
            </article>
          </div>

          <div class="order-meta-strip">
            <span>Összevont variánsok: {metadata.get("merged_variant_count", 0)}</span>
            <span>Küszöb alatti tételek: {metadata.get("filtered_stock_count", 0)}</span>
            <span>SM sorok: {metadata.get("added_super_matt_count", 0)}</span>
            <span>Átlagolt alkatrészek: {metadata.get("avg_row_count", 0)}</span>
            {"<span>Friss alkatrészlista: " + html.escape(source_parts_name) + (f' • {source_parts_count} tétel' if source_parts_count else '') + "</span>" if source_parts_name else ""}
            {"<span>Bevételezési segéd fut</span>" if helper_running else ""}
          </div>

          <div class="order-toolbar">
            <button class="button button-secondary order-toggle-button" type="button" id="order-table-toggle">Javaslat megmutatása</button>
            <a class="button button-secondary" href="{NETTFRONT_ORDER_DOWNLOAD_PREFIX}/{job_id}/suggestion-xlsx">Javaslat letöltése</a>
            {f'<a class="button button-primary" href="{NETTFRONT_ORDER_DOWNLOAD_PREFIX}/{job_id}/approved-xlsx">Kész rendelés letöltése</a>' if approved_ready else ''}
            {f'<a class="button button-secondary" href="{NETTFRONT_ORDER_DOWNLOAD_PREFIX}/{job_id}/import-csv">Bevételezési lista</a>' if import_ready else ''}
            {helper_action_html}
            <a class="button button-secondary" href="{NETTFRONT_ORDER_ROUTE}">Új feltöltés</a>
          </div>
          {helper_hint_html}
        </section>

        <section class="order-table-card" id="order-table-card" hidden>
          <div class="order-result-head">
            <strong>Rendelési javaslat</strong>
            <p>Itt módosíthatod a mennyiségeket, majd jóváhagyhatod a kész rendelést.</p>
          </div>
          {table_html}
        </section>
      </div>
    """

    extra_script = """
<style>
  .order-result-card,
  .order-table-card {
    position: relative;
    overflow: hidden;
    padding: 22px;
    border-radius: 24px;
    border: 1px solid var(--border);
    background: linear-gradient(180deg, rgba(10, 16, 28, 0.94), rgba(8, 13, 22, 0.96));
    box-shadow: var(--shadow);
  }
  .order-result-shell {
    display: grid;
    gap: 16px;
  }
  .order-result-head,
  .order-item-main,
  .order-empty-state {
    display: grid;
    gap: 6px;
  }
  .order-result-head strong,
  .order-summary-card strong,
  .order-item-main strong,
  .order-empty-state strong {
    font-family: "Space Grotesk", sans-serif;
  }
  .order-result-head p,
  .order-summary-card span,
  .order-meta-strip span,
  .order-item-main span,
  .order-empty-state p {
    margin: 0;
    color: var(--muted);
  }
  .order-summary-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    margin-top: 6px;
  }
  .order-summary-card {
    padding: 16px 18px;
    border-radius: 18px;
    border: 1px solid rgba(255, 255, 255, 0.07);
    background: rgba(255, 255, 255, 0.03);
  }
  .order-summary-card strong {
    display: block;
    margin-bottom: 4px;
    font-size: 1.65rem;
    line-height: 1;
  }
  .order-meta-strip,
  .order-toolbar,
  .order-approve-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
  }
  .order-meta-strip {
    gap: 8px 14px;
    padding-top: 2px;
    color: var(--muted);
  }
  .order-meta-strip span {
    font-size: 0.88rem;
  }
  .order-toolbar {
    margin-top: 4px;
    padding-top: 6px;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
  }
  .order-helper-copy {
    margin: 10px 0 0;
    color: var(--muted);
    line-height: 1.55;
  }
  .order-toggle-button {
    min-width: 200px;
  }
  .order-table-wrap {
    overflow: auto;
    margin-top: 14px;
    border-radius: 18px;
    border: 1px solid rgba(255, 255, 255, 0.07);
    background: rgba(7, 12, 20, 0.84);
  }
  .order-table {
    width: 100%;
    min-width: 860px;
    border-collapse: collapse;
    background: transparent;
  }
  .order-table th,
  .order-table td {
    padding: 14px 16px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.045);
    text-align: left;
    vertical-align: middle;
  }
  .order-table th {
    background: rgba(255, 255, 255, 0.03);
    color: var(--text-soft);
    font-size: 0.76rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .order-table th.is-metric,
  .order-table td.is-metric {
    text-align: right;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .order-table tbody tr:nth-child(odd) td {
    background: rgba(255, 255, 255, 0.012);
  }
  .order-table tbody tr:nth-child(even) td {
    background: rgba(255, 255, 255, 0.022);
  }
  .order-table tbody tr:hover {
    background: transparent;
  }
  .order-table tbody tr:hover td {
    background: rgba(255, 255, 255, 0.05);
  }
  .order-item-main strong {
    font-size: 0.96rem;
    line-height: 1.35;
  }
  .order-item-main span {
    font-size: 0.82rem;
  }
  .order-color-stack {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .order-color-text {
    color: var(--text);
    line-height: 1.45;
  }
  .order-inline-badge {
    display: inline-flex;
    align-items: center;
    min-height: 24px;
    padding: 0 8px;
    border-radius: 999px;
    background: rgba(67, 222, 207, 0.1);
    color: var(--accent);
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.06em;
  }
  .order-qty-input {
    width: 96px;
    min-height: 42px;
    padding: 0 12px;
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    background: rgba(255, 255, 255, 0.03);
    color: var(--text);
    font: inherit;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  .order-qty-input:focus {
    outline: none;
    border-color: rgba(67, 222, 207, 0.48);
    box-shadow: 0 0 0 4px rgba(67, 222, 207, 0.12);
  }
  .order-empty-state {
    padding: 20px;
    border-radius: 18px;
    border: 1px dashed rgba(255, 255, 255, 0.08);
    background: rgba(255, 255, 255, 0.03);
  }
  .order-approve-bar {
    justify-content: space-between;
    margin-top: 14px;
    padding-top: 14px;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
  }
  @media (max-width: 960px) {
    .order-summary-grid {
      grid-template-columns: minmax(0, 1fr);
    }
  }
  @media (max-width: 640px) {
    .order-result-card,
    .order-table-card {
      padding: 18px;
    }
    .order-toolbar,
    .order-approve-bar {
      align-items: stretch;
      flex-direction: column;
    }
    .order-toolbar .button,
    .order-approve-bar .button,
    .order-toggle-button {
      width: 100%;
    }
  }
</style>
<script>
  (() => {
    const button = document.getElementById("order-table-toggle");
    const card = document.getElementById("order-table-card");
    if (!button || !card) return;

    const sync = () => {
      button.textContent = card.hidden ? "Javaslat megmutatása" : "Javaslat elrejtése";
    };

    button.addEventListener("click", () => {
      card.hidden = !card.hidden;
      sync();
      if (!card.hidden) {
        card.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });

    sync();
  })();
</script>
"""

    return _render_nettfront_layout(
        heading="",
        lead="",
        intro_label="",
        content_html=content_html,
        side_html="",
        notice_html=notice_html,
        extra_script=extra_script,
        single_column=True,
    )


def render_nettfront_procurement_form(message: str = "") -> bytes:
    notice_html = ""
    if message:
        notice_html = f'<div class="notice-banner">{html.escape(message)}</div>'

    content_html = f"""
      <div class="procurement-shell">
        <section class="procurement-hero-card">
          <div class="procurement-hero-grid">
            <div class="procurement-copy">
              <div class="tag">Invoice -> beszerzés</div>
              <strong>NettFront számlából beszerzés.</strong>
              <p>Egy feltöltés után elkészül minden fájl, ami kell a következő lépéshez.</p>
              <div class="procurement-flow" aria-hidden="true">
                <span>PDF</span>
                <i></i>
                <span>Fordítás</span>
                <i></i>
                <span>CSV</span>
              </div>
            </div>

            <div class="procurement-visual" aria-hidden="true">
              <div class="procurement-orbit"></div>
              <div class="procurement-doc is-source">
                <span class="procurement-doc-label">Számla</span>
                <div class="procurement-doc-lines">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
              <div class="procurement-transfer"></div>
              <div class="procurement-doc is-target">
                <span class="procurement-doc-label">Beszerzés</span>
                <div class="procurement-doc-lines">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="procurement-upload-card" id="feltoltes">
          <div class="procurement-surface-title">
            <strong>Feltöltés</strong>
            <p>Fájl kiválasztása, majd indítás.</p>
          </div>

          <form id="nettfront-procurement-form" method="post" action="{NETTFRONT_PROCUREMENT_PROCESS_ROUTE}" enctype="multipart/form-data">
            <div class="procurement-upload-shell" id="nettfront-procurement-shell">
              <input
                class="procurement-file-input"
                id="nettfront-procurement-invoice"
                type="file"
                name="invoice_pdf"
                accept=".pdf,application/pdf"
                required
              />

              <label class="procurement-upload-surface" for="nettfront-procurement-invoice">
                <div class="procurement-upload-top">
                  <div class="procurement-upload-badge">PDF</div>
                  <div class="procurement-upload-copy">
                    <strong>Számla kiválasztása</strong>
                    <p>Kattints ide, vagy húzd be a fájlt.</p>
                  </div>
                </div>

                <div class="procurement-upload-rail" aria-hidden="true">
                  <span>Számla</span>
                  <i></i>
                  <span>Feldolgozás</span>
                  <i></i>
                  <span>Beszerzési csomag</span>
                </div>

                <span class="procurement-file-state" id="nettfront-procurement-invoice-state">Támogatott formátum: PDF</span>
              </label>

              <input
                class="procurement-file-input"
                id="nettfront-procurement-parts"
                type="file"
                name="parts_file"
                accept=".xlsx,.xlsm,.csv,text/csv"
              />

              <label class="procurement-upload-surface" for="nettfront-procurement-parts">
                <div class="procurement-upload-top">
                  <div class="procurement-upload-badge">XLSX</div>
                  <div class="procurement-upload-copy">
                    <strong>Friss alkatrészlista</strong>
                    <p>Opcionális. Ha most feltöltöd, már ebből építjük a Beszerzést.</p>
                  </div>
                </div>

                <div class="procurement-upload-rail" aria-hidden="true">
                  <span>Alkatrészlista</span>
                  <i></i>
                  <span>Kódfrissítés</span>
                  <i></i>
                  <span>Pontosabb Beszerzés</span>
                </div>

                <span class="procurement-file-state" id="nettfront-procurement-parts-state">Támogatott formátum: XLSX, XLSM, CSV</span>
              </label>

              <div class="procurement-action-row">
                <button class="button button-primary" type="submit" id="nettfront-procurement-submit">Beszerzés készítése</button>
                <span class="inline-note">Az eredmény külön oldalon nyílik meg.</span>
              </div>
            </div>
          </form>

          <div class="procurement-output-footer">
            <strong>Elkészül</strong>
            <span class="procurement-pill">invoice-output.csv</span>
            <span class="procurement-pill">Beszerzés</span>
            <span class="procurement-pill">ZIP csomag</span>
          </div>
        </section>
      </div>
    """

    extra_script = """
<script>
  (() => {
    const invoiceInput = document.getElementById("nettfront-procurement-invoice");
    const invoiceState = document.getElementById("nettfront-procurement-invoice-state");
    const partsInput = document.getElementById("nettfront-procurement-parts");
    const partsState = document.getElementById("nettfront-procurement-parts-state");
    const shell = document.getElementById("nettfront-procurement-shell");
    const form = document.getElementById("nettfront-procurement-form");
    const submitButton = document.getElementById("nettfront-procurement-submit");
    if (!invoiceInput || !invoiceState || !partsInput || !partsState || !shell || !form || !submitButton) return;

    const updateState = (input, state, emptyText) => {
      const file = input.files && input.files[0];
      if (!file) {
        state.textContent = emptyText;
        return;
      }
      state.textContent = `${file.name} • ${(file.size / 1024 / 1024).toFixed(2)} MB`;
    };

    ["dragenter", "dragover"].forEach((eventName) => {
      shell.addEventListener(eventName, (event) => {
        event.preventDefault();
        shell.classList.add("is-dragover");
      });
    });

    ["dragleave", "drop"].forEach((eventName) => {
      shell.addEventListener(eventName, (event) => {
        event.preventDefault();
        shell.classList.remove("is-dragover");
      });
    });

    invoiceInput.addEventListener("change", () => updateState(invoiceInput, invoiceState, "Támogatott formátum: PDF"));
    partsInput.addEventListener("change", () => updateState(partsInput, partsState, "Támogatott formátum: XLSX, XLSM, CSV"));

    form.addEventListener("submit", () => {
      submitButton.textContent = "Beszerzés készül...";
      submitButton.disabled = true;
    });
  })();
</script>"""

    return _render_nettfront_layout(
        heading="",
        lead="",
        intro_label="",
        content_html=content_html,
        side_html="",
        notice_html=notice_html,
        extra_script=extra_script,
        single_column=True,
    )


def _read_procurement_preview_rows(job_id: str, limit: int | None = None) -> tuple[list[list[str]], int]:
    job_dir, _ = _read_nettfront_job("procurement", job_id)
    if job_dir is None:
        return [], 0

    csv_path = job_dir / "rendeles_sima.csv"
    if not csv_path.exists():
        return [], 0

    raw_bytes = csv_path.read_bytes()
    text = raw_bytes.decode("utf-8-sig", errors="ignore")
    reader = csv.reader(io.StringIO(text), delimiter=";")
    rows: list[list[str]] = []
    total_rows = 0
    for row in reader:
        clean_row = [str(value).strip() for value in row[:2]]
        if not any(clean_row):
            continue
        total_rows += 1
        if limit is None or len(rows) < limit:
            rows.append(clean_row)
    return rows, total_rows


def render_nettfront_procurement_result(job_id: str, metadata: dict, message: str = "", success: bool = False) -> bytes:
    notice_html = ""
    if message:
        lowered_message = message.casefold()
        helper_message = (
            "import-segéd" in lowered_message
            or "import-seged" in lowered_message
            or "shift + space" in lowered_message
            or "esc" in lowered_message
        )
        if not helper_message:
            extra_class = " success" if success else ""
            notice_html = f'<div class="notice-banner{extra_class}">{html.escape(message)}</div>'

    missing_codes = metadata.get("missing_codes") or []
    job_dir = _job_runtime_dir("procurement") / job_id
    helper_state = get_procurement_helper_state(job_dir)
    helper_running = bool(helper_state.get("running"))
    preview_rows, preview_total = _read_procurement_preview_rows(job_id)
    uploaded_parts_name = str(metadata.get("uploaded_parts_name", "")).strip()
    missing_html = '<div class="procurement-result-meta"><span class="procurement-result-pill">Nincs hiányzó kód</span></div>'
    if missing_codes:
        visible_codes = missing_codes[:10]
        more_count = len(missing_codes) - len(visible_codes)
        code_chips = "".join(f'<span class="procurement-code-chip">{html.escape(code)}</span>' for code in visible_codes)
        more_html = f'<span class="procurement-code-chip">+{more_count} további</span>' if more_count > 0 else ""
        missing_html = f"""
          <div class="procurement-result-meta">
            <span class="procurement-result-pill is-alert">{len(missing_codes)} hiányzó kód</span>
          </div>
          <div class="procurement-code-list">
            {code_chips}
            {more_html}
          </div>
        """

    preview_html = '<div class="procurement-preview-empty">A Beszerzés most nem elérhető.</div>'
    if preview_rows:
        preview_rows_html = "".join(
            f"<tr><td>{html.escape(row[0] if len(row) > 0 else '')}</td><td>{html.escape(row[1] if len(row) > 1 else '')}</td></tr>"
            for row in preview_rows
        )
        preview_html = f"""
          <div class="procurement-preview-table-wrap">
            <table class="procurement-preview-table">
              <thead>
                <tr>
                  <th>Cikkszám</th>
                  <th>Mennyiség</th>
                </tr>
              </thead>
              <tbody>
                {preview_rows_html}
              </tbody>
            </table>
          </div>
        """

    helper_status_pill = '<span class="procurement-result-pill">Import-segéd nincs elindítva</span>'
    helper_status_copy = "A Beszerzés elkészült. Indítsd a segédet, majd Shift + Space-re elindul az import."
    action_html = f"""
      <form class="launch-form" method="post" action="{NETTFRONT_PROCUREMENT_LAUNCH_PREFIX}/{job_id}">
        <div class="procurement-launch-row">
          <button class="button button-primary" type="submit">Beszerzés indítása</button>
          <a class="button button-secondary" href="{NETTFRONT_PROCUREMENT_ROUTE}">Új feldolgozás</a>
        </div>
      </form>
    """
    if missing_codes:
        uploaded_meta_html = ""
        if uploaded_parts_name:
            uploaded_meta_html = f'<div class="procurement-remap-meta">Utolsó feltöltött lista: {html.escape(uploaded_parts_name)}</div>'
        helper_status_pill = f'<span class="procurement-result-pill is-alert">{len(missing_codes)} hiányzó kód</span>'
        helper_status_copy = "Hiányzó kódokat találtunk. Tölts fel alkatrészlistát, és újraépítjük a Beszerzést."
        action_html = f"""
          <article class="procurement-remap-card">
            <strong>Alkatrészlista feltöltése</strong>
            <p>Hiányzó kódokat találtunk. Tölts fel egy friss alkatrészlistát, és újraépítjük a Beszerzést.</p>
            {uploaded_meta_html}
            <form class="procurement-remap-form" method="post" action="{NETTFRONT_PROCUREMENT_PARTS_PREFIX}/{job_id}" enctype="multipart/form-data">
              <input class="procurement-remap-input" type="file" name="parts_file" accept=".xlsx,.xlsm,.csv,text/csv" required />
              <div class="procurement-launch-row">
                <button class="button button-primary" type="submit">Alkatrészlista feltöltése</button>
                <a class="button button-secondary" href="{NETTFRONT_PROCUREMENT_ROUTE}">Új feldolgozás</a>
              </div>
            </form>
          </article>
        """
    elif helper_running:
        helper_status_pill = '<span class="procurement-result-pill">Import-segéd fut</span>'
        helper_status_copy = "A segéd fut. Shift + Space indítja az importot, a Leállítás gomb azonnal megszakítja."
        action_html = f"""
          <div class="procurement-launch-row">
            <form method="post" action="{NETTFRONT_PROCUREMENT_STOP_PREFIX}/{job_id}">
              <button class="button button-primary" type="submit">Leállítás</button>
            </form>
            <a class="button button-secondary" href="{NETTFRONT_PROCUREMENT_ROUTE}">Új feldolgozás</a>
          </div>
        """

    lead_copy = "A Beszerzés elkészült. Ha minden kód megvan, a segéd automatikusan elindul."
    if missing_codes:
        lead_copy = "Hiányzó kódokat találtunk. Tölts fel alkatrészlistát, és újraépítjük a Beszerzést."
    elif helper_running:
        lead_copy = "A segéd fut: Shift + Space indítja az importot, a Leállítás gomb azonnal megállítja."
    elif message and "automatikus indítása nem sikerült" in message:
        lead_copy = "Az automatikus indítás most nem sikerült. Nyomd meg a Beszerzés indítása gombot."

    warning_modal_html = ""
    extra_script = ""
    if not missing_codes:
        warning_modal_html = f"""
          <div class="procurement-warning-modal" id="procurement-warning-modal" aria-hidden="true">
            <div class="procurement-warning-card" role="dialog" aria-modal="true" aria-labelledby="procurement-warning-title">
              <strong id="procurement-warning-title">Figyelem</strong>
              <p>
                A beszerzést a gép billentyűkkel fogja kezelni az InSight-ban. Csak akkor indítsd el,
                ha biztosan tudod mit csinálsz. Nyiss egy üres beszerzést az InSight-ban, majd nyomd meg a
                <strong>Shift + Space</strong> billentyűkombinációt. Ha baj van, a <strong>Leállítás</strong>
                gomb azonnal megszakítja a segédet.
              </p>
              <div class="procurement-warning-actions">
                <button class="button button-primary" type="button" id="procurement-warning-close">Értem</button>
              </div>
            </div>
          </div>
        """
        extra_script = f"""
<script>
  (() => {{
    const modal = document.getElementById("procurement-warning-modal");
    const closeButton = document.getElementById("procurement-warning-close");
    if (!modal || !closeButton) return;

    const storageKey = "divian-procurement-warning:{job_id}";
    if (!window.sessionStorage.getItem(storageKey)) {{
      modal.classList.add("is-visible");
      modal.setAttribute("aria-hidden", "false");
    }}

    const closeModal = () => {{
      modal.classList.remove("is-visible");
      modal.setAttribute("aria-hidden", "true");
      window.sessionStorage.setItem(storageKey, "1");
    }};

    closeButton.addEventListener("click", closeModal);
    modal.addEventListener("click", (event) => {{
      if (event.target === modal) {{
        closeModal();
      }}
    }});
  }})();
</script>"""

    content_html = f"""
      <div class="procurement-result-shell">
        <div class="tag">Procurement ready</div>
        <h2>A beszerzés elő van készítve</h2>
        <p class="muted-copy">{lead_copy}</p>

        <div class="procurement-result-grid">
          <article class="procurement-result-card">
            <strong>Állapot</strong>
            <div class="procurement-result-meta">
              <span class="procurement-result-pill">{metadata.get("invoice_row_count", 0)} számlasor</span>
              <span class="procurement-result-pill">{preview_total} beszerzési sor</span>
              {helper_status_pill}
            </div>
            <p class="procurement-result-copy">{helper_status_copy}</p>
          </article>

          <article class="procurement-result-card">
            <strong>Hiányzó kódok</strong>
            {missing_html}
          </article>
        </div>

        <article class="procurement-preview-card">
          <div class="procurement-preview-head">
            <div>
              <strong>Beszerzés</strong>
              <p>Előnézet a kész beszerzési listából.</p>
            </div>
            <p>{preview_total} / {preview_total} sor látszik</p>
          </div>
          {preview_html}
        </article>

        {action_html}
      </div>
      {warning_modal_html}
    """

    layout_lead = "A kész Beszerzésnél a segéd automatikusan indul. Ha baj van, a Leállítás gombbal azonnal megállítható."
    if missing_codes:
        layout_lead = "Hiányzó kódoknál tölts fel alkatrészlistát, és a rendszer újraépíti a Beszerzést."
    elif helper_running:
        layout_lead = "A segéd fut. Shift + Space indítja az importot, a Leállítás gomb azonnal megállítja."

    return _render_nettfront_layout(
        heading="Beszerzés kész",
        lead=layout_lead,
        intro_label="Procurement ready",
        content_html=content_html,
        side_html="",
        notice_html=notice_html,
        extra_script=extra_script,
        single_column=True,
    )


def render_nettfront_compare_form(message: str = "") -> bytes:
    notice_html = ""
    if message:
        notice_html = f'<div class="notice-banner">{html.escape(message)}</div>'

    content_html = f"""
      <div class="tag">Invoice vs procurement</div>
      <h2>NettFront számla és meglévő beszerzés összehasonlítása</h2>
      <p class="muted-copy">
        Töltsd fel a számlát és a meglévő rendelési fájlt. A rendszer elkészít egy két munkalapos,
        színezett Excel riportot, amiből gyorsan látszik minden eltérés.
      </p>

      <form id="nettfront-compare-form" class="upload-grid" method="post" action="{NETTFRONT_COMPARE_PROCESS_ROUTE}" enctype="multipart/form-data">
        <label class="upload-field">
          <strong>Számla PDF</strong>
          <span class="field-hint">Kötelező. Ebből készül az invoice sorstruktúra.</span>
          <input id="nettfront-compare-invoice" type="file" name="invoice_pdf" accept=".pdf,application/pdf" required />
          <span class="field-hint" id="nettfront-compare-invoice-state">Támogatott formátum: PDF</span>
        </label>

        <label class="upload-field">
          <strong>Meglévő rendelés</strong>
          <span class="field-hint">Kötelező. XLSX, XLSM vagy CSV formátum.</span>
          <input id="nettfront-compare-order" type="file" name="order_file" accept=".xlsx,.xlsm,.csv" required />
          <span class="field-hint" id="nettfront-compare-order-state">Támogatott formátum: XLSX, XLSM, CSV</span>
        </label>
      </form>

      <div class="action-row">
        <button class="button button-primary" type="submit" form="nettfront-compare-form">Összehasonlító riport készítése</button>
      </div>
    """

    side_html = """
      <article class="stack-card">
        <h3>Kimenetek</h3>
        <ul>
          <li>`compare-output.xlsx` két munkalappal</li>
          <li>`invoice-output.csv` a visszakövetéshez</li>
          <li>egyben letölthető ZIP</li>
        </ul>
      </article>

      <article class="stack-card">
        <h3>Mire jó?</h3>
        <p>
          Akkor hasznos, ha a beszerzés már létezik, és a számlával akarod kontrollálni, hogy a kódok,
          mennyiségek és árak ténylegesen egyeznek-e.
        </p>
      </article>
    """

    return _render_nettfront_layout(
        heading="Meglévő beszerzés és számla összehasonlítása",
        lead="Külön felület csak az ellenőrzésre, hogy a már kész rendelés és az érkező számla pontosan összevethető legyen.",
        intro_label="Comparison module",
        content_html=content_html,
        side_html=side_html,
        notice_html=notice_html,
        extra_script=_render_file_bind_script(
            [
                ("nettfront-compare-invoice", "nettfront-compare-invoice-state", "Támogatott formátum: PDF"),
                ("nettfront-compare-order", "nettfront-compare-order-state", "Támogatott formátum: XLSX, XLSM, CSV"),
            ]
        ),
    )


def render_nettfront_compare_result(job_id: str, metadata: dict, message: str = "") -> bytes:
    notice_html = ""
    if message:
        notice_html = f'<div class="notice-banner">{html.escape(message)}</div>'

    content_html = f"""
      <div class="tag">Comparison output ready</div>
      <h2>Az összehasonlító riport elkészült</h2>
      <p class="muted-copy">
        Elkészült a számla és a meglévő beszerzés összevetése. Innen letölthető a színezett Excel riport és a kapcsolódó fájlok.
      </p>

      <div class="summary-grid">
        <article class="summary-card">
          <strong>{metadata.get("invoice_row_count", 0)}</strong>
          <span>felismert számlasor</span>
        </article>
        <article class="summary-card">
          <strong>{metadata.get("order_row_count", 0)}</strong>
          <span>beolvasott rendelési sor</span>
        </article>
        <article class="summary-card">
          <strong>Excel</strong>
          <span>két munkalapos riport</span>
        </article>
      </div>

      <div class="download-grid">
        <article class="download-card">
          <strong>Compare Excel</strong>
          <p>Színezett riport két összevetési nézettel.</p>
          <a class="button button-secondary" href="{NETTFRONT_COMPARE_DOWNLOAD_PREFIX}/{job_id}/compare-xlsx">compare-output.xlsx</a>
        </article>

        <article class="download-card">
          <strong>Invoice CSV</strong>
          <p>A feldolgozott számlasorok külön is letölthetők.</p>
          <a class="button button-secondary" href="{NETTFRONT_COMPARE_DOWNLOAD_PREFIX}/{job_id}/invoice-csv">invoice-output.csv</a>
        </article>

        <article class="download-card">
          <strong>Teljes csomag</strong>
          <p>Minden generált fájl egy ZIP-ben.</p>
          <a class="button button-secondary" href="{NETTFRONT_COMPARE_DOWNLOAD_PREFIX}/{job_id}/bundle-zip">compare-output.zip</a>
        </article>
      </div>

      <div class="action-row">
        <a class="button button-primary" href="{NETTFRONT_COMPARE_ROUTE}">Új összehasonlítás</a>
        <a class="button button-secondary" href="{NETTFRONT_ROUTE}">Vissza a NettFront modulokhoz</a>
      </div>
    """

    side_html = f"""
      <article class="stack-card">
        <h3>Állapot</h3>
        <ul class="status-list">
          <li>Invoice sorok: {metadata.get("invoice_row_count", 0)}</li>
          <li>Rendelési sorok: {metadata.get("order_row_count", 0)}</li>
          <li>Riport: elkészült</li>
        </ul>
      </article>

      <article class="stack-card">
        <h3>Mit kapsz?</h3>
        <p>
          A compare Excel külön munkalapokon mutatja az order->invoice és invoice->order nézetet, így gyorsan
          látszanak a hiányzó vagy eltérő sorok.
        </p>
      </article>
    """

    return _render_nettfront_layout(
        heading="Az összehasonlítás lefutott",
        lead="A meglévő rendelés és a számla közötti eltérések most már külön riportban átnézhetők.",
        intro_label="Compare ready",
        content_html=content_html,
        side_html=side_html,
        notice_html=notice_html,
    )


def _vacation_route(month_value: str, **params: object) -> str:
    query: dict[str, str] = {}
    if month_value:
        query["month"] = month_value
    for key, value in params.items():
        if value is None:
            continue
        clean_value = str(value).strip()
        if clean_value:
            query[key] = clean_value
    suffix = urllib.parse.urlencode(query)
    return f"{VACATION_CALENDAR_ROUTE}?{suffix}" if suffix else VACATION_CALENDAR_ROUTE


def _vacation_render_calendar_cell(cell: dict) -> str:
    classes = ["vacation-day"]
    if not cell["is_current_month"]:
        classes.append("is-other-month")
    if cell["entries"]:
        classes.append("is-busy")
    if any(load["count"] >= load["max_absent"] for load in cell["loads"]):
        classes.append("is-limited")
    if cell["date"] == date.today():
        classes.append("is-today")

    day_value = _vacation_date_value(cell["date"])
    interactive_attrs = (
        f' data-vacation-day="{html.escape(day_value)}" tabindex="0" role="button"'
        if cell["is_current_month"]
        else ""
    )
    day_badge = ""
    entry_html = "".join(
        f'<button class="vacation-entry" type="button" data-vacation-leave-id="{entry["id"]}" '
        f'data-vacation-day="{html.escape(day_value)}">{html.escape(entry["employee_name"])}</button>'
        for entry in cell["entries"][:3]
    )
    if len(cell["entries"]) > 3:
        entry_html += f'<span class="vacation-entry-more">+{len(cell["entries"]) - 3} további</span>'

    load_html = ""

    return f"""
      <div class="{' '.join(classes)}"{interactive_attrs}>
        <div class="vacation-day-head">
          <span class="vacation-day-number">{cell["date"].day}</span>
          {day_badge}
        </div>
        <div class="vacation-day-list">{entry_html}</div>
        {load_html}
      </div>
    """


def _vacation_render_leave_item(leave_entry: dict, month_value: str) -> str:
    start_day = _vacation_parse_date(leave_entry["start_date"])
    end_day = _vacation_parse_date(leave_entry["end_date"])
    if start_day and end_day:
        range_label = _vacation_date_label(start_day) if start_day == end_day else f"{_vacation_date_label(start_day)} - {_vacation_date_label(end_day)}"
    else:
        range_label = f"{leave_entry['start_date']} - {leave_entry['end_date']}"
    department_label = ", ".join(leave_entry["department_names"]) or "Nincs részleg"
    note_html = f"<span>{html.escape(leave_entry['note'])}</span>" if leave_entry["note"] else ""
    return f"""
      <li class="vacation-item">
        <div class="vacation-item-main">
          <strong>{html.escape(leave_entry["employee_name"])}</strong>
          <span>{html.escape(range_label)} · {html.escape(department_label)}</span>
          {note_html}
        </div>
      </li>
    """


def _vacation_render_employee_item(employee: dict, month_value: str) -> str:
    badges = "".join(
        f'<span class="vacation-mini-badge">{html.escape(name)}</span>'
        for name in employee["department_names"]
    )
    edit_href = _vacation_route(month_value, edit_employee=employee["id"]) + "#employee-form"
    return f"""
      <li class="vacation-item">
        <div class="vacation-item-main">
          <strong>{html.escape(employee["name"])}</strong>
          <span>{len(employee["department_names"])} részleg · {employee["vacation_count"]} rögzített szabadság</span>
          <div class="vacation-mini-badge-row">{badges}</div>
        </div>
        <div class="vacation-item-actions">
          <a class="knowledge-action" href="{edit_href}">Szerkesztés</a>
          <form method="post" action="{VACATION_CALENDAR_EMPLOYEE_DELETE_ROUTE}">
            <input type="hidden" name="employee_id" value="{employee["id"]}" />
            <input type="hidden" name="return_month" value="{html.escape(month_value)}" />
            <button class="knowledge-action is-danger" type="submit">Törlés</button>
          </form>
        </div>
      </li>
    """


def _vacation_render_department_item(department: dict, month_value: str) -> str:
    edit_href = _vacation_route(month_value, edit_department=department["id"]) + "#department-form"
    return f"""
      <li class="vacation-item">
        <div class="vacation-item-main">
          <strong>{html.escape(department["name"])}</strong>
          <span>{department["employee_count"]} kolléga · max. {department["max_absent"]} fő lehet egyszerre szabadságon</span>
        </div>
        <div class="vacation-item-actions">
          <a class="knowledge-action" href="{edit_href}">Szerkesztés</a>
          <form method="post" action="{VACATION_CALENDAR_DEPARTMENT_DELETE_ROUTE}">
            <input type="hidden" name="department_id" value="{department["id"]}" />
            <input type="hidden" name="return_month" value="{html.escape(month_value)}" />
            <button class="knowledge-action is-danger" type="submit">Törlés</button>
          </form>
        </div>
      </li>
    """


def render_vacation_calendar(
    *,
    month_value: str = "",
    message: str = "",
    success: bool = False,
    edit_department_id: int | None = None,
    edit_employee_id: int | None = None,
    edit_leave_id: int | None = None,
    department_draft: dict | None = None,
    employee_draft: dict | None = None,
    leave_draft: dict | None = None,
) -> bytes:
    notice_html = ""
    if message:
        notice_class = "notice-banner success" if success else "notice-banner"
        notice_html = f'<div class="{notice_class}">{html.escape(message)}</div>'

    month_start = _vacation_parse_month(month_value)
    month_value = _vacation_month_value(month_start)
    month_end = _vacation_month_bounds(month_start)[1]

    with _vacation_db_connection() as connection:
        departments = _vacation_fetch_departments(connection)
        employees = _vacation_fetch_employees(connection)
        leaves = _vacation_fetch_leaves_in_range(connection, month_start, month_end)
        edit_department = _vacation_fetch_department(connection, edit_department_id) if edit_department_id else None
        edit_employee = _vacation_fetch_employee(connection, edit_employee_id) if edit_employee_id else None
        edit_leave = _vacation_fetch_leave(connection, edit_leave_id) if edit_leave_id else None

    weeks, limit_day_count = _vacation_build_calendar(month_start, leaves)
    month_label = _vacation_month_label(month_start)
    prev_month_href = _vacation_route(_vacation_month_value(_vacation_next_month(month_start, -1)))
    next_month_href = _vacation_route(_vacation_month_value(_vacation_next_month(month_start, 1)))
    cancel_href = _vacation_route(month_value)
    current_view_url = _vacation_route(
        month_value,
        edit_department=edit_department_id,
        edit_employee=edit_employee_id,
    )

    department_state = {
        "id": str((department_draft or {}).get("id", edit_department["id"] if edit_department else "")),
        "name": str((department_draft or {}).get("name", edit_department["name"] if edit_department else "")),
        "max_absent": str((department_draft or {}).get("max_absent", edit_department["max_absent"] if edit_department else 1)),
    }
    employee_state = {
        "id": str((employee_draft or {}).get("id", edit_employee["id"] if edit_employee else "")),
        "name": str((employee_draft or {}).get("name", edit_employee["name"] if edit_employee else "")),
        "department_ids": [
            int(value)
            for value in (employee_draft or {}).get("department_ids", edit_employee["department_ids"] if edit_employee else [])
        ],
    }
    leave_state = {
        "id": str((leave_draft or {}).get("id", edit_leave["id"] if edit_leave else "")),
        "employee_id": str((leave_draft or {}).get("employee_id", edit_leave["employee_id"] if edit_leave else "")),
        "start_date": str((leave_draft or {}).get("start_date", edit_leave["start_date"] if edit_leave else _vacation_date_value(date.today()))),
        "end_date": str((leave_draft or {}).get("end_date", edit_leave["end_date"] if edit_leave else _vacation_date_value(date.today()))),
        "note": str((leave_draft or {}).get("note", edit_leave["note"] if edit_leave else "")),
    }
    leave_modal_should_open = edit_leave is not None or leave_draft is not None
    leave_modal_date = leave_state["start_date"] or _vacation_date_value(date.today())
    leave_modal_leave_id = leave_state["id"]

    weekday_html = "".join(f'<div class="vacation-weekday">{label}</div>' for label in VACATION_WEEKDAY_LABELS)
    calendar_html = weekday_html + "".join(_vacation_render_calendar_cell(cell) for week in weeks for cell in week)

    employee_list_html = "".join(_vacation_render_employee_item(item, month_value) for item in employees)
    employee_list_html = f'<ul class="vacation-list">{employee_list_html}</ul>' if employee_list_html else '<div class="vacation-empty">Először hozz létre legalább egy részleget, utána add fel a kollégákat.</div>'

    department_list_html = "".join(_vacation_render_department_item(item, month_value) for item in departments)
    department_list_html = f'<ul class="vacation-list">{department_list_html}</ul>' if department_list_html else '<div class="vacation-empty">Még nincs részleg felvéve.</div>'

    department_checks_html = "".join(
        f"""
        <label class="vacation-check">
          <input type="checkbox" name="department_ids" value="{department["id"]}"{" checked" if department["id"] in employee_state["department_ids"] else ""} />
          <span>{html.escape(department["name"])} · max. {department["max_absent"]} fő</span>
        </label>
        """
        for department in departments
    )
    if not department_checks_html:
        department_checks_html = '<div class="vacation-empty">Előbb hozz létre legalább egy részleget.</div>'

    employee_options_html = '<option value="">Válassz kollégát</option>' + "".join(
        f'<option value="{employee["id"]}"{" selected" if str(employee["id"]) == leave_state["employee_id"] else ""}>{html.escape(employee["name"])}</option>'
        for employee in employees
    )
    leave_payload_json = json.dumps(
        [
            {
                "id": item["id"],
                "employeeId": item["employee_id"],
                "employeeName": item["employee_name"],
                "startDate": item["start_date"],
                "endDate": item["end_date"],
                "note": item["note"],
                "departmentNames": item["department_names"],
            }
            for item in leaves
        ],
        ensure_ascii=False,
    ).replace("</", "<\\/")
    employee_cancel_html = f'<a class="vacation-inline-link" href="{cancel_href}#employee-form">Mégse</a>' if employee_state["id"] else ""
    department_cancel_html = f'<a class="vacation-inline-link" href="{cancel_href}#department-form">Mégse</a>' if department_state["id"] else ""
    leave_modal_html = f"""
        <div class="vacation-modal-backdrop" data-vacation-modal aria-hidden="true" hidden>
          <article class="vacation-modal-card" role="dialog" aria-modal="true" aria-labelledby="vacation-modal-title">
            <button class="vacation-modal-close" type="button" data-vacation-close aria-label="Bezárás">×</button>
            <div class="vacation-modal-head">
              <h3 id="vacation-modal-title" data-vacation-modal-title>Új szabadság</h3>
              <p data-vacation-modal-subtitle>Válaszd ki a kollégát és a dátumot.</p>
            </div>

            <div class="vacation-modal-day-panel">
              <div class="vacation-modal-day-summary">
                <strong data-vacation-modal-day-label></strong>
                <span data-vacation-modal-day-meta></span>
              </div>
              <div class="vacation-modal-day-list" data-vacation-day-list></div>
            </div>

            <form class="vacation-form-grid is-split vacation-modal-form" method="post" action="{VACATION_CALENDAR_LEAVE_SAVE_ROUTE}">
              <input type="hidden" name="leave_id" value="{html.escape(leave_state['id'])}" data-vacation-leave-id-field />
              <input type="hidden" name="return_month" value="{html.escape(month_value)}" />
              <div class="vacation-field">
                <label for="modal-leave-employee">Kolléga</label>
                <select id="modal-leave-employee" name="employee_id"{" disabled" if not employees else ""} required>{employee_options_html}</select>
              </div>
              <div class="vacation-field">
                <label for="modal-leave-start">Kezdete</label>
                <input id="modal-leave-start" type="date" name="start_date" value="{html.escape(leave_state['start_date'])}" required />
              </div>
              <div class="vacation-field">
                <label for="modal-leave-end">Vége</label>
                <input id="modal-leave-end" type="date" name="end_date" value="{html.escape(leave_state['end_date'])}" required />
              </div>
              <div class="vacation-field is-full">
                <label for="modal-leave-note">Megjegyzés</label>
                <textarea id="modal-leave-note" name="note" placeholder="Opcionális">{html.escape(leave_state['note'])}</textarea>
              </div>
              <div class="vacation-form-actions is-full vacation-modal-actions">
                <button class="button button-secondary" type="submit" data-vacation-save{" disabled" if not employees else ""}>{'Mentés' if leave_state['id'] else 'Felvétel'}</button>
                <button class="knowledge-action" type="button" data-vacation-new{" hidden" if not employees else ""}>Új szabadság</button>
              </div>
            </form>

            <form class="vacation-modal-delete" method="post" action="{VACATION_CALENDAR_LEAVE_DELETE_ROUTE}" data-vacation-delete-form{" hidden" if not leave_state['id'] else ""}>
              <input type="hidden" name="leave_id" value="{html.escape(leave_state['id'])}" data-vacation-delete-id />
              <input type="hidden" name="return_month" value="{html.escape(month_value)}" />
              <button class="knowledge-action is-danger" type="submit">Szabadság törlése</button>
            </form>
          </article>
        </div>
    """

    employee_panel_html = f"""
      <article class="stack-card vacation-list-card" id="employee-form">
        <div class="vacation-list-head">
          <div>
            <h3>Kollégák</h3>
            <p>Felvétel, szerkesztés, törlés.</p>
          </div>
        </div>
        {employee_list_html}
        <div class="vacation-card-divider"></div>
        <div>
          <h3>{'Kolléga szerkesztése' if employee_state['id'] else 'Új kolléga'}</h3>
          <p>{'Név és részlegek módosítása.' if employee_state['id'] else 'Név és részlegek megadása.'}</p>
        </div>
        <form class="vacation-form-grid" method="post" action="{VACATION_CALENDAR_EMPLOYEE_SAVE_ROUTE}">
          <input type="hidden" name="employee_id" value="{html.escape(employee_state['id'])}" />
          <input type="hidden" name="return_month" value="{html.escape(month_value)}" />
          <div class="vacation-field">
            <label for="employee-name">Név</label>
            <input id="employee-name" type="text" name="name" value="{html.escape(employee_state['name'])}" placeholder="Kiss Péter" required />
          </div>
          <div class="vacation-field">
            <strong>Részlegek</strong>
            <div class="vacation-checkbox-grid">{department_checks_html}</div>
            <span class="vacation-field-hint">Minden kijelölt részleg limitjét figyeli.</span>
          </div>
          <div class="vacation-form-actions">
            <button class="button button-secondary" type="submit">{'Mentés' if employee_state['id'] else 'Felvétel'}</button>
            {employee_cancel_html}
          </div>
        </form>
      </article>
    """
    department_panel_html = f"""
      <article class="stack-card vacation-list-card" id="department-form">
        <div class="vacation-list-head">
          <div>
            <h3>Részlegek</h3>
            <p>Felvétel, szerkesztés, törlés.</p>
          </div>
        </div>
        {department_list_html}
        <div class="vacation-card-divider"></div>
        <div>
          <h3>{'Részleg szerkesztése' if department_state['id'] else 'Új részleg'}</h3>
          <p>Írd be, egyszerre hány fő lehet távol.</p>
        </div>
        <form class="vacation-form-grid" method="post" action="{VACATION_CALENDAR_DEPARTMENT_SAVE_ROUTE}">
          <input type="hidden" name="department_id" value="{html.escape(department_state['id'])}" />
          <input type="hidden" name="return_month" value="{html.escape(month_value)}" />
          <div class="vacation-field">
            <label for="department-name">Részleg neve</label>
            <input id="department-name" type="text" name="name" value="{html.escape(department_state['name'])}" placeholder="Beszerzés" required />
          </div>
          <div class="vacation-field">
            <label for="department-max-absent">Max. szabadságon egyszerre</label>
            <input id="department-max-absent" type="number" min="0" name="max_absent" value="{html.escape(department_state['max_absent'])}" required />
          </div>
          <div class="vacation-form-actions">
            <button class="button button-secondary" type="submit">{'Mentés' if department_state['id'] else 'Felvétel'}</button>
            {department_cancel_html}
          </div>
        </form>
      </article>
    """

    content_html = f"""
      <div
        class="vacation-shell"
        data-current-url="{html.escape(current_view_url)}"
        data-leave-modal-open="{'true' if leave_modal_should_open else 'false'}"
        data-leave-modal-date="{html.escape(leave_modal_date)}"
        data-leave-modal-id="{html.escape(leave_modal_leave_id)}"
      >
        <div class="vacation-calendar-stage" data-vacation-calendar-stage>
          <article class="stack-card vacation-calendar-card">
            <div class="vacation-toolbar">
              <div class="vacation-month-nav">
                <a class="knowledge-action" href="{prev_month_href}">Előző</a>
                <div class="vacation-month-title">{html.escape(month_label)}</div>
                <a class="knowledge-action" href="{next_month_href}">Következő</a>
              </div>

              <form class="vacation-month-form" method="get" action="{VACATION_CALENDAR_ROUTE}">
                <input type="month" name="month" value="{html.escape(month_value)}" />
                <button class="knowledge-action" type="submit">Ugrás</button>
              </form>
            </div>

            <div class="vacation-calendar-wrap">
              <div class="vacation-calendar-grid">{calendar_html}</div>
            </div>
          </article>
          {leave_modal_html}
        </div>

        <div class="vacation-section-grid">
          {employee_panel_html}
          {department_panel_html}
        </div>

        <script type="application/json" data-vacation-leaves>{leave_payload_json}</script>
      </div>
    """

    combined_content_html = content_html
    extra_script = f"""
<script>
(() => {{
  if (window.__vacationCalendarAsyncBound) return;
  window.__vacationCalendarAsyncBound = true;

  const ROOT_ID = "vacation-module-root";
  const ROUTE_PREFIX = "{VACATION_CALENDAR_ROUTE}";
  let requestToken = 0;
  const longDateFormatter = new Intl.DateTimeFormat("hu-HU", {{
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "long",
  }});
  const shortDateFormatter = new Intl.DateTimeFormat("hu-HU", {{
    month: "short",
    day: "numeric",
  }});

  const getRoot = () => document.getElementById(ROOT_ID);
  const getShell = () => getRoot()?.querySelector(".vacation-shell") || null;
  const getStage = () => getRoot()?.querySelector("[data-vacation-calendar-stage]") || null;
  const getModal = () => getRoot()?.querySelector("[data-vacation-modal]") || null;
  const shouldHandleUrl = (url) => url.origin === window.location.origin && url.pathname.startsWith(ROUTE_PREFIX);
  const escapeHtml = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (char) => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }})[char] || char);
  const parseVacationDate = (value) => new Date(`${{value}}T12:00:00`);
  const formatLongDate = (value) => {{
    if (!value) return "";
    const parsed = parseVacationDate(value);
    return Number.isNaN(parsed.getTime()) ? value : longDateFormatter.format(parsed);
  }};
  const formatShortDate = (value) => {{
    if (!value) return "";
    const parsed = parseVacationDate(value);
    return Number.isNaN(parsed.getTime()) ? value : shortDateFormatter.format(parsed);
  }};
  const formatLeaveRange = (startDate, endDate) => {{
    if (!startDate || !endDate) return "";
    return startDate === endDate ? formatLongDate(startDate) : `${{formatShortDate(startDate)}} - ${{formatShortDate(endDate)}}`;
  }};
  const readVacationLeaves = () => {{
    const node = getRoot()?.querySelector("[data-vacation-leaves]");
    if (!node) return [];
    try {{
      const parsed = JSON.parse(node.textContent || "[]");
      return Array.isArray(parsed) ? parsed : [];
    }} catch (_error) {{
      return [];
    }}
  }};
  const getDayLeaves = (dayValue) =>
    readVacationLeaves()
      .filter((item) => item.startDate <= dayValue && item.endDate >= dayValue)
      .sort((left, right) => left.employeeName.localeCompare(right.employeeName, "hu"));
  const hasVacationEmployees = () => {{
    const select = getModal()?.querySelector('select[name="employee_id"]');
    if (!(select instanceof HTMLSelectElement)) return false;
    return Array.from(select.options).some((option) => option.value);
  }};
  const closeVacationModal = () => {{
    const modal = getModal();
    if (!modal) return;
    modal.setAttribute("aria-hidden", "true");
    modal.classList.remove("is-open");
    modal.hidden = true;
  }};
  const revealVacationStage = () => {{
    const stage = getStage();
    if (!stage) return;
    stage.scrollIntoView({{ behavior: "smooth", block: "start" }});
  }};
  const renderVacationDayEntries = (modal, dayValue, activeLeaveId) => {{
    const list = modal.querySelector("[data-vacation-day-list]");
    const dayLabel = modal.querySelector("[data-vacation-modal-day-label]");
    const dayMeta = modal.querySelector("[data-vacation-modal-day-meta]");
    if (!(list instanceof HTMLElement) || !(dayLabel instanceof HTMLElement) || !(dayMeta instanceof HTMLElement)) {{
      return;
    }}

    const entries = getDayLeaves(dayValue);
    dayLabel.textContent = formatLongDate(dayValue) || dayValue;
    dayMeta.textContent = entries.length
      ? `${{entries.length}} rögzített szabadság ezen a napon.`
      : "Erre a napra még nincs szabadság felvéve.";

    if (!entries.length) {{
      list.innerHTML = '<div class="vacation-empty">Erre a napra még nincs szabadság.</div>';
      return;
    }}

    list.innerHTML = entries
      .map((entry) => {{
        const departmentLabel = Array.isArray(entry.departmentNames) && entry.departmentNames.length
          ? entry.departmentNames.join(", ")
          : "Nincs részleg";
        const noteHtml = entry.note ? `<small>${{escapeHtml(entry.note)}}</small>` : "";
        return `
          <button
            class="vacation-modal-day-entry${{String(entry.id) === String(activeLeaveId) ? " is-active" : ""}}"
            type="button"
            data-vacation-leave-id="${{entry.id}}"
            data-vacation-day="${{dayValue}}"
          >
            <strong>${{escapeHtml(entry.employeeName)}}</strong>
            <span>${{escapeHtml(formatLeaveRange(entry.startDate, entry.endDate))}} · ${{escapeHtml(departmentLabel)}}</span>
            ${{noteHtml}}
          </button>
        `;
      }})
      .join("");
  }};
  const populateVacationModal = (options = {{}}) => {{
    const modal = getModal();
    if (!modal) return;

    const shell = getShell();
    const leaves = readVacationLeaves();
    const selectedLeave = options.leaveId ? leaves.find((item) => String(item.id) === String(options.leaveId)) || null : null;
    const dayValue = options.dayValue || selectedLeave?.startDate || shell?.dataset.leaveModalDate || "";
    const saveForm = modal.querySelector(".vacation-modal-form");
    const deleteForm = modal.querySelector("[data-vacation-delete-form]");
    const title = modal.querySelector("[data-vacation-modal-title]");
    const subtitle = modal.querySelector("[data-vacation-modal-subtitle]");
    const leaveIdField = modal.querySelector("[data-vacation-leave-id-field]");
    const deleteIdField = modal.querySelector("[data-vacation-delete-id]");
    const saveButton = modal.querySelector("[data-vacation-save]");
    const newButton = modal.querySelector("[data-vacation-new]");
    if (!(saveForm instanceof HTMLFormElement) || !(title instanceof HTMLElement) || !(subtitle instanceof HTMLElement)) {{
      return;
    }}

    modal.dataset.dayValue = dayValue;
    renderVacationDayEntries(modal, dayValue, selectedLeave?.id ?? "");

    const employeeField = saveForm.querySelector('select[name="employee_id"]');
    const startField = saveForm.querySelector('input[name="start_date"]');
    const endField = saveForm.querySelector('input[name="end_date"]');
    const noteField = saveForm.querySelector('textarea[name="note"]');
    if (leaveIdField instanceof HTMLInputElement) {{
      leaveIdField.value = selectedLeave ? String(selectedLeave.id) : "";
    }}
    if (deleteIdField instanceof HTMLInputElement) {{
      deleteIdField.value = selectedLeave ? String(selectedLeave.id) : "";
    }}
    if (employeeField instanceof HTMLSelectElement) {{
      employeeField.value = selectedLeave ? String(selectedLeave.employeeId) : "";
    }}
    if (startField instanceof HTMLInputElement) {{
      startField.value = selectedLeave ? selectedLeave.startDate : dayValue;
    }}
    if (endField instanceof HTMLInputElement) {{
      endField.value = selectedLeave ? selectedLeave.endDate : dayValue;
    }}
    if (noteField instanceof HTMLTextAreaElement) {{
      noteField.value = selectedLeave?.note || "";
    }}

    const canSave = hasVacationEmployees();
    if (saveButton instanceof HTMLButtonElement) {{
      saveButton.disabled = !canSave;
      saveButton.textContent = selectedLeave ? "Mentés" : "Felvétel";
    }}
    if (employeeField instanceof HTMLSelectElement) {{
      employeeField.disabled = !canSave;
    }}

    if (selectedLeave) {{
      title.textContent = "Szabadság szerkesztése";
      subtitle.textContent = `${{selectedLeave.employeeName}} szabadsága. Módosíthatod vagy törölheted is.`;
      if (deleteForm instanceof HTMLFormElement) {{
        deleteForm.hidden = false;
      }}
      if (newButton instanceof HTMLButtonElement) {{
        newButton.hidden = !canSave;
      }}
    }} else {{
      title.textContent = "Új szabadság";
      subtitle.textContent = canSave
        ? "Kattints egy napra, és innen rögtön felveheted a szabadságot."
        : "Előbb vegyél fel legalább egy kollégát, utána rögzíthető szabadság.";
      if (deleteForm instanceof HTMLFormElement) {{
        deleteForm.hidden = true;
      }}
      if (newButton instanceof HTMLButtonElement) {{
        newButton.hidden = true;
      }}
    }}

    modal.setAttribute("aria-hidden", "false");
    modal.classList.add("is-open");
    modal.hidden = false;
    revealVacationStage();
  }};
  const syncVacationModalFromRoot = () => {{
    const shell = getShell();
    if (!shell) return;
    if (shell.dataset.leaveModalOpen === "true") {{
      populateVacationModal({{
        dayValue: shell.dataset.leaveModalDate || "",
        leaveId: shell.dataset.leaveModalId || "",
      }});
      return;
    }}
    closeVacationModal();
  }};

  const serializeForm = (form, submitter) => {{
    const formData = new FormData(form);
    if (submitter?.name) {{
      formData.append(submitter.name, submitter.value);
    }}
    const body = new URLSearchParams();
    for (const [key, value] of formData.entries()) {{
      body.append(key, String(value));
    }}
    return body;
  }};

  const updateHistory = (mode, nextRoot, fallbackUrl) => {{
    if (mode === "none") return;
    const nextUrl = nextRoot.querySelector(".vacation-shell")?.dataset.currentUrl || fallbackUrl;
    if (!nextUrl) return;
    if (mode === "replace") {{
      window.history.replaceState({{ vacationCalendar: true }}, "", nextUrl);
      return;
    }}
    window.history.pushState({{ vacationCalendar: true }}, "", nextUrl);
  }};

  const swapRoot = (htmlText, fallbackUrl, historyMode, hash) => {{
    const parser = new DOMParser();
    const documentNode = parser.parseFromString(htmlText, "text/html");
    const nextRoot = documentNode.getElementById(ROOT_ID);
    const currentRoot = getRoot();
    if (!nextRoot || !currentRoot) {{
      throw new Error("A szabadságnaptár nézet nem frissíthető részlegesen.");
    }}
    currentRoot.replaceWith(nextRoot);
    if (documentNode.title) {{
      document.title = documentNode.title;
    }}
    updateHistory(historyMode, nextRoot, fallbackUrl);
    syncVacationModalFromRoot();
    if (hash) {{
      window.requestAnimationFrame(() => {{
        const target = document.querySelector(hash);
        if (target) {{
          target.scrollIntoView({{ behavior: "smooth", block: "start" }});
        }}
      }});
    }}
  }};

  const fetchAndSwap = async (url, options = {{}}, historyMode = "push", hash = "") => {{
    const root = getRoot();
    if (!root) return;

    const requestId = ++requestToken;
    root.classList.add("is-loading");
    root.setAttribute("aria-busy", "true");

    try {{
      const response = await fetch(url, {{
        ...options,
        headers: {{
          Accept: "text/html",
          ...(options.headers || {{}}),
        }},
      }});
      const htmlText = await response.text();
      if (requestId !== requestToken) return;
      swapRoot(htmlText, typeof url === "string" ? url : url.toString(), historyMode, hash);
    }} catch (_error) {{
      window.location.assign(typeof url === "string" ? url : url.toString());
    }} finally {{
      const nextRoot = getRoot();
      if (nextRoot) {{
        nextRoot.classList.remove("is-loading");
        nextRoot.removeAttribute("aria-busy");
      }}
    }}
  }};

  document.addEventListener("click", (event) => {{
    const root = getRoot();
    const target = event.target instanceof Element ? event.target : null;
    if (!root || !target || !root.contains(target)) {{
      return;
    }}

    if (target === getModal()) {{
      event.preventDefault();
      closeVacationModal();
      return;
    }}

    const closeButton = target.closest("[data-vacation-close]");
    if (closeButton) {{
      event.preventDefault();
      closeVacationModal();
      return;
    }}

    const newButton = target.closest("[data-vacation-new]");
    if (newButton) {{
      event.preventDefault();
      populateVacationModal({{ dayValue: getModal()?.dataset.dayValue || getShell()?.dataset.leaveModalDate || "" }});
      return;
    }}

    const leaveButton = target.closest("[data-vacation-leave-id]");
    if (leaveButton) {{
      event.preventDefault();
      populateVacationModal({{
        leaveId: leaveButton.getAttribute("data-vacation-leave-id") || "",
        dayValue:
          leaveButton.getAttribute("data-vacation-day") ||
          leaveButton.closest("[data-vacation-day]")?.getAttribute("data-vacation-day") ||
          "",
      }});
      return;
    }}

    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {{
      return;
    }}

    const dayCell = target.closest("[data-vacation-day]");
    if (dayCell) {{
      event.preventDefault();
      populateVacationModal({{ dayValue: dayCell.getAttribute("data-vacation-day") || "" }});
      return;
    }}

    const link = target.closest("a");
    if (!link || !root.contains(link)) {{
      return;
    }}
    if (link.target && link.target !== "_self") {{
      return;
    }}
    const url = new URL(link.href, window.location.href);
    if (!shouldHandleUrl(url)) {{
      return;
    }}
    event.preventDefault();
    const requestUrl = new URL(url.toString());
    requestUrl.hash = "";
    fetchAndSwap(requestUrl.toString(), {{ method: "GET" }}, "push", url.hash);
  }});

  document.addEventListener("keydown", (event) => {{
    const modal = getModal();
    if (event.key === "Escape" && modal?.classList.contains("is-open")) {{
      event.preventDefault();
      closeVacationModal();
      return;
    }}

    const target = event.target instanceof Element ? event.target : null;
    const dayCell = target?.closest("[data-vacation-day]");
    if (!dayCell || !getRoot()?.contains(dayCell)) {{
      return;
    }}
    if (event.key === "Enter" || event.key === " ") {{
      event.preventDefault();
      populateVacationModal({{ dayValue: dayCell.getAttribute("data-vacation-day") || "" }});
    }}
  }});

  document.addEventListener("submit", (event) => {{
    const root = getRoot();
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !root || !root.contains(form)) {{
      return;
    }}
    const actionUrl = new URL(form.action || window.location.href, window.location.href);
    if (!shouldHandleUrl(actionUrl)) {{
      return;
    }}

    event.preventDefault();
    const method = (form.method || "get").toUpperCase();
    const body = serializeForm(form, event.submitter);

    if (method === "GET") {{
      actionUrl.search = body.toString();
      fetchAndSwap(actionUrl.toString(), {{ method: "GET" }}, "push", actionUrl.hash);
      return;
    }}

    fetchAndSwap(actionUrl.toString(), {{ method: "POST", body }}, "replace");
  }});

  window.addEventListener("popstate", () => {{
    const root = getRoot();
    const currentUrl = new URL(window.location.href);
    if (!root || !shouldHandleUrl(currentUrl)) {{
      return;
    }}
    fetchAndSwap(currentUrl.toString(), {{ method: "GET" }}, "none", currentUrl.hash);
  }});

  syncVacationModalFromRoot();
}})();
</script>"""

    return _render_nettfront_layout(
        heading="Szabadságnaptár",
        lead="Részlegenként követhető szabadságkezelés egy helyen.",
        intro_label="Calendar",
        content_html=combined_content_html,
        side_html="",
        notice_html=notice_html,
        extra_script=extra_script,
        single_column=True,
        module_root_id="vacation-module-root",
    )


def render_manufacturing_module(production_number: str = "", message: str = "", success: bool = False) -> bytes:
    requested_number = _manufacturing_normalize_number(production_number)
    recent_numbers = available_production_numbers(limit=80, ready_only=True)
    recent_productions = available_production_entries(limit=80, ready_only=True)
    selected_number = requested_number if requested_number in recent_numbers else (recent_numbers[0] if recent_numbers else "")
    if requested_number and requested_number not in recent_numbers:
        combined_prefix = f"A {requested_number} gyártásban nem található meg mindkét szükséges PDF, ezért a legfrissebb használható gyártást nyitottam meg."
        message = f"{combined_prefix} {message}".strip() if message else combined_prefix
        success = False

    bundle: dict | None = None
    selection_state: dict[str, str] = {}
    combined_message = message
    combined_success = success

    if not selected_number:
        combined_message = "Nem találok használható gyártási mappát a beállított gyártási útvonalon."
        combined_success = False
    else:
        try:
            bundle = _load_manufacturing_bundle_cached(selected_number)
            selection_state = load_selection_state(MANUFACTURING_RUNTIME_DIR, selected_number)
        except Exception as exc:
            combined_message = f"A gyártási papírok betöltése nem sikerült: {exc}"
            combined_success = False

    if bundle is None:
        bundle = {
            "production_number": selected_number,
            "folder": str(manufacturing_production_folder(selected_number)) if selected_number else "",
            "documents": [],
        }

    return render_manufacturing_page(
        route=MANUFACTURING_ROUTE,
        state_route=MANUFACTURING_STATE_ROUTE,
        selected_number=selected_number,
        recent_productions=recent_productions,
        bundle=bundle,
        selection_state=selection_state,
        message=combined_message,
        success=combined_success,
    )


def _divian_ai_format_file_size(size_bytes: int) -> str:
    size = max(0, int(size_bytes))
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    unit = units[0]
    for next_unit in units:
        unit = next_unit
        if value < 1024 or next_unit == units[-1]:
            break
        value /= 1024
    return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"


def _divian_ai_db_connection() -> sqlite3.Connection:
    DIVIAN_AI_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DIVIAN_AI_DB, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS knowledge_documents (
            id TEXT PRIMARY KEY,
            source_key TEXT NOT NULL UNIQUE,
            source_name TEXT NOT NULL,
            path TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            kind TEXT NOT NULL,
            parser_name TEXT NOT NULL DEFAULT '',
            study_mode TEXT NOT NULL DEFAULT '',
            confidence TEXT NOT NULL DEFAULT '',
            is_uploaded INTEGER NOT NULL DEFAULT 0,
            uploaded_at TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            note TEXT NOT NULL DEFAULT '',
            size_bytes INTEGER NOT NULL DEFAULT 0,
            modified_ns INTEGER NOT NULL DEFAULT 0,
            page_count INTEGER NOT NULL DEFAULT 0,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            record_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS knowledge_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT NOT NULL,
            label TEXT NOT NULL,
            page_number INTEGER NOT NULL,
            title TEXT NOT NULL,
            text TEXT NOT NULL,
            normalized TEXT NOT NULL,
            folded TEXT NOT NULL,
            lines_json TEXT NOT NULL,
            FOREIGN KEY (document_id) REFERENCES knowledge_documents(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT NOT NULL,
            label TEXT NOT NULL,
            page_number INTEGER NOT NULL,
            text TEXT NOT NULL,
            normalized TEXT NOT NULL,
            tokens_json TEXT NOT NULL,
            FOREIGN KEY (document_id) REFERENCES knowledge_documents(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS knowledge_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT NOT NULL,
            label TEXT NOT NULL,
            row_number INTEGER NOT NULL,
            fields_json TEXT NOT NULL,
            text TEXT NOT NULL,
            normalized TEXT NOT NULL,
            tokens_json TEXT NOT NULL,
            FOREIGN KEY (document_id) REFERENCES knowledge_documents(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS knowledge_corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            correction TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_hint TEXT NOT NULL DEFAULT ''
        );
        """
    )
    document_columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(knowledge_documents)").fetchall()}
    if "parser_name" not in document_columns:
        connection.execute("ALTER TABLE knowledge_documents ADD COLUMN parser_name TEXT NOT NULL DEFAULT ''")
    if "study_mode" not in document_columns:
        connection.execute("ALTER TABLE knowledge_documents ADD COLUMN study_mode TEXT NOT NULL DEFAULT ''")
    if "confidence" not in document_columns:
        connection.execute("ALTER TABLE knowledge_documents ADD COLUMN confidence TEXT NOT NULL DEFAULT ''")
    return connection


class _DivianAIHTMLToTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._current_tag_stack: list[str] = []
        self._title_parts: list[str] = []
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag_name = tag.lower()
        self._current_tag_stack.append(tag_name)
        if tag_name in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
            return
        if tag_name in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "section", "article", "li", "ul", "ol", "br", "tr"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.lower()
        if tag_name in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if self._current_tag_stack:
            self._current_tag_stack.pop()
        if tag_name in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "section", "article", "li", "ul", "ol", "tr"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = _clean_spaces(data)
        if not text:
            return
        if self._current_tag_stack and self._current_tag_stack[-1] == "title":
            self._title_parts.append(text)
        if self._parts:
            previous = self._parts[-1]
            if previous and not previous.endswith(("\n", " ", "\t")):
                if previous[-1].isalnum() and text[:1].isalnum():
                    self._parts.append(" ")
        self._parts.append(text)

    def text(self) -> str:
        raw = "".join(self._parts)
        normalized = re.sub(r"\n{3,}", "\n\n", raw)
        return "\n".join(line.strip() for line in normalized.splitlines() if line.strip()).strip()

    def title(self) -> str:
        return _clean_spaces(" ".join(self._title_parts))


class _DivianAILinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._current_link: dict | None = None
        self._links: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return
        attr_map = dict(attrs)
        href = _clean_spaces(attr_map.get("href", ""))
        if not href:
            return
        self._current_link = {
            "href": href,
            "title": _clean_spaces(attr_map.get("title", "")),
            "class": _clean_spaces(attr_map.get("class", "")),
            "text": "",
        }

    def handle_data(self, data: str) -> None:
        if self._current_link is None:
            return
        text = _clean_spaces(data)
        if not text:
            return
        if self._current_link["text"]:
            self._current_link["text"] += f" {text}"
        else:
            self._current_link["text"] = text

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._current_link is None:
            return
        self._current_link["text"] = _clean_spaces(self._current_link["text"])
        self._links.append(self._current_link)
        self._current_link = None

    def links(self) -> list[dict[str, str]]:
        return list(self._links)


def _divian_ai_fetch_public_web_html(url: str) -> tuple[str, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="ignore"), ""
    except Exception as exc:
        return "", str(exc)


def _divian_ai_collect_html_links(base_url: str, html_text: str) -> list[dict[str, str]]:
    parser = _DivianAILinkCollector()
    parser.feed(html_text)
    parser.close()
    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for item in parser.links():
        full_url = urllib.parse.urljoin(base_url, item.get("href", ""))
        normalized_url = full_url.split("#", 1)[0].strip()
        if not normalized_url or normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        results.append(
            {
                "url": normalized_url,
                "title": _clean_spaces(item.get("title", "")),
                "text": _clean_spaces(item.get("text", "")),
                "class": _clean_spaces(item.get("class", "")),
            }
        )
    return results


def _divian_ai_public_web_slug_for_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    host_part = re.sub(r"[^a-z0-9]+", "-", parsed.netloc.lower()).strip("-")
    path_part = re.sub(r"[^a-z0-9]+", "-", parsed.path.strip("/").lower()).strip("-") or "root"
    query_part = re.sub(r"[^a-z0-9]+", "-", parsed.query.lower()).strip("-")
    parts = [part for part in (host_part, path_part, query_part) if part]
    return re.sub(r"-{2,}", "-", "-".join(parts)).strip("-")


def _divian_ai_normalize_partner_public_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query_pairs: list[tuple[str, str]] = []
    if path in {"/akcios-termekek", "/uj-termekek"}:
        query_values = urllib.parse.parse_qs(parsed.query)
        page_value = query_values.get("page", [""])
        if page_value and page_value[0]:
            query_pairs.append(("page", page_value[0]))
    query = urllib.parse.urlencode(query_pairs)
    return urllib.parse.urlunparse(("https", parsed.netloc.lower(), path, "", query, ""))


def _divian_ai_partner_page_type(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    path = parsed.path or "/"
    if path.startswith("/kategoria/"):
        return "product"
    if path in {"/akcios-termekek", "/uj-termekek"} or parsed.query:
        return "listing"
    return "page"


def _divian_ai_partner_should_crawl_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc.lower() != "partner.divian.hu":
        return False
    path = parsed.path or "/"
    if path.startswith("/image/"):
        return False
    if path in {"/belepes", "/regisztracio"}:
        return False
    if path.startswith("/kategoria/"):
        return True
    return path in {
        "/",
        "/akcios-termekek",
        "/uj-termekek",
        "/kapcsolat",
        "/garanciabejelento",
        "/aszf",
        "/adatvedelmi-nyilatkozat",
        "/szemelyes-adatok-kezelese",
    }


def _divian_ai_partner_entry_name(url: str, page_title: str, sections: set[str]) -> str:
    parsed = urllib.parse.urlparse(url)
    path = parsed.path or "/"
    page_type = _divian_ai_partner_page_type(url)
    clean_title = _clean_spaces(page_title)

    if page_type == "product":
        if "akcio" in sections and "uj" not in sections:
            prefix = "Divian partner - Akciós termék"
        elif "uj" in sections and "akcio" not in sections:
            prefix = "Divian partner - Új termék"
        else:
            prefix = "Divian partner - Termék"
    elif path == "/akcios-termekek":
        prefix = "Divian partner - Akciók"
    elif path == "/uj-termekek":
        prefix = "Divian partner - Új termékek"
    elif path == "/kapcsolat":
        prefix = "Divian partner - Kapcsolat"
    elif path == "/garanciabejelento":
        prefix = "Divian partner - Garancia bejelentő"
    else:
        prefix = "Divian partner - Oldal"

    page_value = urllib.parse.parse_qs(parsed.query).get("page", [""])
    if page_value and page_value[0] and prefix in {"Divian partner - Akciók", "Divian partner - Új termékek"}:
        return f"{prefix} - {page_value[0]}. oldal"

    if clean_title and _divian_ai_fold_text(clean_title) != _divian_ai_fold_text(prefix):
        return f"{prefix} - {clean_title}"
    return clean_title or prefix


def _divian_ai_load_public_web_source_manifest() -> list[dict] | None:
    if not DIVIAN_AI_PUBLIC_WEB_SOURCE_MANIFEST.exists():
        return None
    try:
        payload = json.loads(DIVIAN_AI_PUBLIC_WEB_SOURCE_MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return None
    if int(payload.get("version", 0)) != DIVIAN_AI_PUBLIC_WEB_VERSION:
        return None
    generated_at = float(payload.get("generated_at", 0))
    if generated_at and time.time() - generated_at > DIVIAN_AI_PUBLIC_WEB_DISCOVERY_SECONDS:
        return None
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return None
    valid_entries: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        slug = _clean_spaces(str(entry.get("slug", "")))
        name = _clean_spaces(str(entry.get("name", "")))
        url = _clean_spaces(str(entry.get("url", "")))
        if not slug or not name or not url:
            continue
        valid_entries.append(entry)
    return valid_entries or None


def _divian_ai_write_public_web_source_manifest(entries: list[dict]) -> None:
    DIVIAN_AI_PUBLIC_WEB_SOURCE_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": DIVIAN_AI_PUBLIC_WEB_VERSION,
        "generated_at": time.time(),
        "entries": entries,
    }
    DIVIAN_AI_PUBLIC_WEB_SOURCE_MANIFEST.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _divian_ai_discover_partner_public_sources() -> list[dict]:
    cached_entries = _divian_ai_load_public_web_source_manifest()
    if cached_entries is not None:
        return cached_entries

    seed_items = [
        {"url": "https://partner.divian.hu/", "sections": {"partner"}},
        {"url": "https://partner.divian.hu/kapcsolat", "sections": {"partner"}},
        {"url": "https://partner.divian.hu/akcios-termekek", "sections": {"partner", "akcio"}},
        {"url": "https://partner.divian.hu/uj-termekek", "sections": {"partner", "uj"}},
    ]
    queued_urls = {item["url"] for item in seed_items}
    visited_urls: set[str] = set()
    discovered: dict[str, dict] = {}
    static_urls = {
        _divian_ai_normalize_partner_public_url(str(entry.get("url", "")).strip())
        for entry in DIVIAN_AI_PUBLIC_WEB_SOURCES
        if "partner.divian.hu" in str(entry.get("url", ""))
    }
    queue = list(seed_items)

    while queue and len(visited_urls) < DIVIAN_AI_PARTNER_PUBLIC_MAX_PAGES:
        item = queue.pop(0)
        current_url = _divian_ai_normalize_partner_public_url(str(item.get("url", "")).strip())
        if not current_url or current_url in visited_urls:
            continue

        current_sections = set(item.get("sections", set()))
        page_meta = discovered.setdefault(
            current_url,
            {
                "sections": set(),
                "title": "",
                "page_type": _divian_ai_partner_page_type(current_url),
            },
        )
        page_meta["sections"].update(current_sections)

        html_text, error = _divian_ai_fetch_public_web_html(current_url)
        if error:
            visited_urls.add(current_url)
            continue

        parser = _DivianAIHTMLToTextParser()
        parser.feed(html_text)
        parser.close()
        page_title = parser.title()
        if page_title:
            page_meta["title"] = page_title
        if _divian_ai_fold_text(page_title) == "belepes":
            page_meta["skip"] = True
            visited_urls.add(current_url)
            continue

        sku_present = bool(re.search(r"\bSKU\s*:\s*[A-Z0-9_\-]+\b", parser.text(), re.IGNORECASE))
        if page_meta["page_type"] == "product" and not sku_present:
            if _divian_ai_partner_product_titles_from_html(current_url, html_text):
                page_meta["page_type"] = "listing"

        visited_urls.add(current_url)

        for link in _divian_ai_collect_html_links(current_url, html_text):
            next_url = _divian_ai_normalize_partner_public_url(link.get("url", ""))
            if not next_url or not _divian_ai_partner_should_crawl_url(next_url):
                continue

            next_sections = set(current_sections)
            next_path = urllib.parse.urlparse(next_url).path or "/"
            if page_meta["page_type"] == "product" and next_path.startswith("/kategoria/"):
                continue
            folded_link_text = _divian_ai_fold_text(f"{link.get('text', '')} {link.get('title', '')}")
            if next_path == "/akcios-termekek" or "akcio" in folded_link_text:
                next_sections.add("akcio")
            if next_path == "/uj-termekek" or "uj termek" in folded_link_text:
                next_sections.add("uj")

            next_meta = discovered.setdefault(
                next_url,
                {
                    "sections": set(),
                    "title": "",
                    "page_type": _divian_ai_partner_page_type(next_url),
                },
            )
            next_meta["sections"].update(next_sections)
            if not next_meta["title"]:
                next_meta["title"] = link.get("text", "") or link.get("title", "")

            if next_url not in visited_urls and next_url not in queued_urls:
                queue.append({"url": next_url, "sections": next_sections})
                queued_urls.add(next_url)

    dynamic_entries: list[dict] = []
    for url in sorted(visited_urls):
        meta = discovered.get(url, {})
        if url in static_urls:
            continue
        if meta.get("skip"):
            continue
        sections = set(meta.get("sections", set()))
        page_title = _clean_spaces(str(meta.get("title", "")))
        entry = {
            "slug": _divian_ai_public_web_slug_for_url(url),
            "name": _divian_ai_partner_entry_name(url, page_title, sections),
            "url": url,
            "section": "|".join(sorted(sections)),
            "page_type": str(meta.get("page_type") or _divian_ai_partner_page_type(url)),
        }
        dynamic_entries.append(entry)

    _divian_ai_write_public_web_source_manifest(dynamic_entries)
    return dynamic_entries


def _divian_ai_public_web_sources() -> tuple[dict, ...]:
    dynamic_entries = _divian_ai_discover_partner_public_sources()
    return tuple(DIVIAN_AI_PUBLIC_WEB_SOURCES) + tuple(dynamic_entries)


def _divian_ai_public_web_entry(path: Path) -> dict | None:
    file_name = path.name.lower()
    for entry in _divian_ai_public_web_sources():
        slug = str(entry.get("slug", "")).strip().lower()
        if file_name == f"{slug}.txt":
            return entry
    return None


def _divian_ai_public_web_source_path(entry: dict) -> Path:
    slug = str(entry.get("slug", "")).strip().lower()
    return DIVIAN_AI_PUBLIC_WEB_DIR / f"{slug}.txt"


def _divian_ai_cleanup_public_web_text(text: str) -> str:
    cleaned = text
    cleaned = re.sub(
        r"(?<=[a-záéíóöőúüű])(?=[A-ZÁÉÍÓÖŐÚÜŰ])",
        " ",
        cleaned,
    )
    cleaned = re.sub(r"(?<=\S)(https?://)", r" \1", cleaned)
    cleaned = re.sub(r"(?<=[a-záéíóöőúüű])(?=\d)", " ", cleaned)
    cleaned = re.sub(r"(?<=\d)(?=[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű])", " ", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _divian_ai_partner_product_titles_from_html(base_url: str, html_text: str) -> list[str]:
    generic_category_slugs = {
        "szekek",
        "asztal",
        "garniturak",
        "konyha-gepek",
        "konyhai-kisgepek",
        "mosogatotalcak",
        "csaptelepek",
        "vasalatok",
        "kiegeszitok",
        "kisopres",
        "blokk-konyha",
        "blokk-konyha-keszlett",
    }
    titles: list[str] = []
    seen_titles: set[str] = set()
    for link in _divian_ai_collect_html_links(base_url, html_text):
        link_url = _divian_ai_normalize_partner_public_url(link.get("url", ""))
        parsed = urllib.parse.urlparse(link_url)
        if parsed.netloc.lower() != "partner.divian.hu" or not parsed.path.startswith("/kategoria/"):
            continue
        path_slug = parsed.path.rsplit("/", 1)[-1].strip().lower()
        if path_slug in generic_category_slugs:
            continue
        if "list-group-item" in _divian_ai_fold_text(link.get("class", "")):
            continue
        title = _clean_spaces(link.get("text", "") or link.get("title", ""))
        if not title:
            continue
        folded_title = _divian_ai_fold_text(title)
        if folded_title in seen_titles:
            continue
        seen_titles.add(folded_title)
        titles.append(title)
    return titles


def _divian_ai_partner_stock_label(plain_text: str) -> str:
    folded_text = _divian_ai_fold_text(plain_text)
    if "raktaron" in folded_text:
        return "Raktáron"
    if any(term in folded_text for term in ("nincs raktaron", "elfogyott", "nem rendelheto", "nem rendelhető")):
        return "Nem elérhető"
    return ""


def _divian_ai_partner_public_document_text(entry: dict, url: str, page_title: str, plain_text: str, html_text: str) -> str:
    page_type = str(entry.get("page_type", "")).strip() or _divian_ai_partner_page_type(url)
    section_tags = [value for value in str(entry.get("section", "")).split("|") if value]
    section_labels: list[str] = []
    if "akcio" in section_tags:
        section_labels.append("Akciók")
    if "uj" in section_tags:
        section_labels.append("Új termékek")
    if not section_labels and "partner" in section_tags:
        section_labels.append("Partner katalógus")

    header_lines: list[str] = []
    if page_type == "product":
        header_lines.append("Oldal típus: Partner termékoldal")
        header_lines.append(f"Termék neve: {page_title}")
        sku_match = re.search(r"\bSKU\s*:\s*([A-Z0-9_\-]+)\b", plain_text, re.IGNORECASE)
        if sku_match:
            header_lines.append(f"SKU: {sku_match.group(1).strip()}")
        stock_label = _divian_ai_partner_stock_label(plain_text)
        if stock_label:
            header_lines.append(f"Készletállapot: {stock_label}")
    elif page_type == "listing":
        if "akcio" in section_tags:
            header_lines.append("Oldal típus: Partner akciós lista")
        elif "uj" in section_tags:
            header_lines.append("Oldal típus: Partner új termék lista")
        else:
            header_lines.append("Oldal típus: Partner listaoldal")
    else:
        header_lines.append("Oldal típus: Partner információs oldal")

    if section_labels:
        header_lines.append(f"Partner szekció: {', '.join(section_labels)}")

    product_titles = _divian_ai_partner_product_titles_from_html(url, html_text)
    if product_titles and page_type == "listing":
        header_lines.append(f"Talált termékek száma: {len(product_titles)}")
        for title in product_titles[:160]:
            if "akcio" in section_tags:
                header_lines.append(f"Akciós termék: {title}")
            elif "uj" in section_tags:
                header_lines.append(f"Új termék: {title}")
            else:
                header_lines.append(f"Termék: {title}")

    merged_lines = "\n".join(line for line in header_lines if line.strip()).strip()
    if not merged_lines:
        return plain_text
    return "\n\n".join(part for part in (merged_lines, plain_text) if part.strip()).strip()


def _divian_ai_fetch_public_web_source(entry: dict) -> tuple[Path | None, str]:
    url = str(entry.get("url", "")).strip()
    if not url:
        return None, "A nyilvános Divian webforrás URL-je hiányzik."

    target_path = _divian_ai_public_web_source_path(entry)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if target_path.exists():
        age_seconds = time.time() - target_path.stat().st_mtime
        if age_seconds < DIVIAN_AI_PUBLIC_WEB_REFRESH_SECONDS:
            return target_path, ""

    html_text, fetch_error = _divian_ai_fetch_public_web_html(url)
    if fetch_error:
        if target_path.exists():
            return target_path, f"A nyilvános webforrás frissítése most nem sikerült: {entry.get('name', url)} ({fetch_error})"
        return None, f"A nyilvános webforrás nem érhető el: {entry.get('name', url)} ({fetch_error})"

    parser = _DivianAIHTMLToTextParser()
    parser.feed(html_text)
    parser.close()
    plain_text = _divian_ai_cleanup_public_web_text(parser.text())
    page_title = parser.title() or str(entry.get("name", "")).strip() or url
    if "partner.divian.hu" in urllib.parse.urlparse(url).netloc.lower():
        plain_text = _divian_ai_partner_public_document_text(entry, url, page_title, plain_text, html_text)

    if not plain_text:
        if target_path.exists():
            return target_path, f"A nyilvános webforrásból most nem sikerült szöveget kinyerni: {entry.get('name', url)}"
        return None, f"A nyilvános webforrásból nem sikerült olvasható szöveget kinyerni: {entry.get('name', url)}"

    document_text = "\n".join(
        [
            f"Divian nyilvános webforrás: {str(entry.get('name', '')).strip() or page_title}",
            f"Web extract version: {DIVIAN_AI_PUBLIC_WEB_VERSION}",
            f"Forrás URL: {url}",
            f"Oldal címe: {page_title}",
            f"Frissítve: {datetime.now().isoformat(timespec='seconds')}",
            "",
            plain_text,
        ]
    ).strip()
    target_path.write_text(document_text, encoding="utf-8")
    return target_path, ""


def _divian_ai_public_web_source_paths() -> tuple[list[Path], list[str]]:
    paths: list[Path] = []
    errors: list[str] = []
    for entry in _divian_ai_public_web_sources():
        path, error = _divian_ai_fetch_public_web_source(entry)
        if path is not None and path.exists():
            paths.append(path)
        if error:
            errors.append(error)
    return paths, errors


def _divian_ai_source_key(path: Path) -> str:
    try:
        return str(path.resolve()).lower()
    except Exception:
        return str(path).lower()


def _divian_ai_document_rows() -> list[sqlite3.Row]:
    with _divian_ai_db_connection() as connection:
        return connection.execute(
            """
            SELECT
                id,
                source_name,
                path,
                stored_name,
                kind,
                parser_name,
                study_mode,
                confidence,
                is_uploaded,
                uploaded_at,
                status,
                note,
                size_bytes,
                page_count,
                chunk_count,
                record_count,
                updated_at
            FROM knowledge_documents
            ORDER BY
                CASE WHEN uploaded_at = '' THEN 1 ELSE 0 END,
                uploaded_at DESC,
                updated_at DESC,
                source_name COLLATE NOCASE
            """
        ).fetchall()


def _divian_ai_registry_totals() -> dict[str, int]:
    with _divian_ai_db_connection() as connection:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS document_count,
                SUM(CASE WHEN status IN ('indexed', 'indexed_with_warning') THEN 1 ELSE 0 END) AS indexed_count,
                SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS error_count,
                SUM(CASE WHEN study_mode = 'strukturált' THEN 1 ELSE 0 END) AS structured_count,
                COALESCE(SUM(chunk_count), 0) AS chunk_count,
                COALESCE(SUM(record_count), 0) AS record_count
            FROM knowledge_documents
            """
        ).fetchone()
    return {
        "document_count": int(row["document_count"] or 0),
        "indexed_count": int(row["indexed_count"] or 0),
        "error_count": int(row["error_count"] or 0),
        "structured_count": int(row["structured_count"] or 0),
        "chunk_count": int(row["chunk_count"] or 0),
        "record_count": int(row["record_count"] or 0),
    }


def _divian_ai_catalog_entries() -> list[dict]:
    knowledge = _load_divian_ai_knowledge()
    entries: list[dict] = []

    for row in _divian_ai_document_rows():
        file_path = Path(row["path"])
        display_name = str(row["source_name"]).strip() or file_path.name
        is_public_web = _divian_ai_public_web_entry(file_path) is not None
        try:
            size_bytes = int(row["size_bytes"] or 0)
        except Exception:
            size_bytes = 0

        entries.append(
            {
                "id": str(row["id"]),
                "display_name": display_name,
                "stored_name": str(row["stored_name"]).strip() or file_path.name,
                "kind": str(row["kind"]).strip() or _divian_ai_doc_kind(file_path),
                "parser_name": str(row["parser_name"]).strip(),
                "study_mode": str(row["study_mode"]).strip(),
                "confidence": str(row["confidence"]).strip(),
                "size_label": _divian_ai_format_file_size(size_bytes),
                "uploaded_at": str(row["uploaded_at"]).strip(),
                "is_uploaded": bool(row["is_uploaded"]),
                "is_indexed": str(row["status"]).strip() in {"indexed", "indexed_with_warning"},
                "status": str(row["status"]).strip(),
                "note": str(row["note"]).strip(),
                "previewable": file_path.exists() and _divian_ai_previewable(file_path),
                "downloadable": file_path.exists(),
                "deletable": file_path.exists() and not is_public_web,
                "page_count": int(row["page_count"] or 0),
                "chunk_count": int(row["chunk_count"] or 0),
                "record_count": int(row["record_count"] or 0),
            }
        )

    entries.sort(
        key=lambda item: (
            item["uploaded_at"] or "",
            item["display_name"].lower(),
        ),
        reverse=True,
    )
    return entries


def render_divian_ai_knowledge_form(message: str = "", success: bool = False) -> bytes:
    notice_html = ""
    if message:
        notice_class = "notice-banner success" if success else "notice-banner"
        notice_html = f'<div class="{notice_class}">{html.escape(message)}</div>'

    knowledge = _load_divian_ai_knowledge()
    registry_totals = _divian_ai_registry_totals()
    catalog_entries = _divian_ai_catalog_entries()
    indexed_entries = [entry for entry in catalog_entries if entry["is_indexed"]]
    ready_value = "Kész" if knowledge.chunks else "Üres"
    ready_note = "A chat már tud keresni benne." if knowledge.chunks else "Tölts fel fájlokat a kezdéshez."
    recent_entries = catalog_entries[:8]
    recent_list = "".join(
        f"""
        <li>
          <div>
            <strong>{html.escape(entry['display_name'])}</strong>
            <span>{html.escape(entry['kind'])} · {html.escape(entry['size_label'])} · {entry['chunk_count']} blokk · {entry['record_count']} rekord</span>
            {f'<span>{html.escape(entry["parser_name"])} · {html.escape(entry["study_mode"])} · biztonság: {html.escape(entry["confidence"])}</span>' if entry['parser_name'] else ''}
          </div>
          <div class="knowledge-list-side">
            <span class="knowledge-list-badge">{'Feltöltött' if entry['is_uploaded'] else 'Rendszerforrás'}</span>
            <span class="knowledge-list-badge{' is-pending' if not entry['is_indexed'] else ''}">{'Kereshető' if entry['is_indexed'] else 'Feldolgozás'}</span>
            <div class="knowledge-list-actions">
              {f'<a class="knowledge-action" href="{DIVIAN_AI_KNOWLEDGE_FILE_PREFIX}/{entry["id"]}" target="_blank" rel="noreferrer">Megnézés</a>' if entry['previewable'] else ''}
              {f'<a class="knowledge-action" href="{DIVIAN_AI_KNOWLEDGE_FILE_PREFIX}/{entry["id"]}/download">Letöltés</a>' if entry['downloadable'] else ''}
              {f'<form method="post" action="{DIVIAN_AI_KNOWLEDGE_DELETE_PREFIX}/{entry["id"]}"><button class="knowledge-action is-danger" type="submit">Törlés</button></form>' if entry['deletable'] else ''}
            </div>
          </div>
        </li>
        """
        for entry in recent_entries
    )
    recent_list_html = f"<ul class=\"knowledge-list\">{recent_list}</ul>"
    if not recent_list:
        recent_list_html = '<div class="knowledge-empty">Még nincs feltöltött forrás.</div>'

    error_note = ""
    if knowledge.errors:
        error_note = f'<p class="status-note">Megjegyzés: {html.escape(knowledge.errors[0])}</p>'

    content_html = f"""
      <div class="knowledge-shell">
        <section class="knowledge-hero">
          <div class="knowledge-hero-grid">
            <div class="knowledge-hero-copy">
              <div class="tag">AI tudástár</div>
              <h2>Tölts fel fájlokat, és a Divian-AI már ezekből is dolgozik.</h2>
              <p>PDF, Excel, Word, kép vagy export. A rendszer elmenti, beolvassa, és kérdezhetővé teszi. A hivatalos Divian webes források automatikusan bekerülnek.</p>
              <div class="knowledge-stat-strip">
                <div class="knowledge-mini-stat">
                  <strong>{registry_totals["document_count"]}</strong>
                  <span>forrásregiszter</span>
                </div>
                <div class="knowledge-mini-stat">
                  <strong>{registry_totals["chunk_count"]}</strong>
                  <span>kereshető blokk</span>
                </div>
                <div class="knowledge-mini-stat">
                  <strong>{ready_value}</strong>
                  <span>{ready_note}</span>
                </div>
              </div>
            </div>

            <div class="knowledge-visual" aria-hidden="true">
              <div class="knowledge-visual-gridline"></div>
              <div class="knowledge-visual-core">
                <span class="knowledge-visual-kicker">Divian-AI</span>
                <strong>Tudástár</strong>
                <div class="knowledge-visual-scan"></div>
                <span class="knowledge-visual-caption">Minden adat, egy helyen.</span>
              </div>
            </div>
          </div>
        </section>

        <div class="summary-grid">
          <article class="summary-card">
            <strong>{registry_totals["document_count"]}</strong>
            <span>forrás a regiszterben</span>
          </article>
          <article class="summary-card">
            <strong>{registry_totals["record_count"]}</strong>
            <span>strukturált rekord</span>
          </article>
          <article class="summary-card">
            <strong>{len(indexed_entries)}</strong>
            <span>indexelt, kérdezhető forrás</span>
          </article>
        </div>

        <div class="download-grid">
          <article class="download-card">
            <strong>Forrásregiszter</strong>
            <p>Minden fájl külön forrásként kerül be névvel, típussal, állapottal és dátummal.</p>
          </article>
          <article class="download-card">
            <strong>Feldolgozott tudás</strong>
            <p>A rendszer dokumentumokra, rekordokra és kereshető blokkokra bontja a feltöltéseket.</p>
          </article>
        </div>

        <form id="divian-ai-knowledge-form" class="knowledge-upload" method="post" action="{DIVIAN_AI_KNOWLEDGE_PROCESS_ROUTE}" enctype="multipart/form-data">
          <div class="knowledge-upload-head">
            <div class="knowledge-upload-copy">
              <strong>Feltöltés a tudástárba</strong>
              <p>Több fájlt is adhatsz egyszerre.</p>
            </div>
            <div class="knowledge-upload-badge">AI ready</div>
          </div>

          <label class="knowledge-dropzone" id="divian-ai-knowledge-dropzone" for="divian-ai-knowledge-files">
            <div class="knowledge-dropzone-copy">
              <strong>Húzd ide a fájlokat</strong>
              <p>Vagy kattints, és válaszd ki őket.</p>
            </div>
            <div class="knowledge-dropzone-action" aria-hidden="true">
              <span class="knowledge-dropzone-cta">Fájlok kiválasztása</span>
              <span class="knowledge-dropzone-note">Bármilyen céges fájl</span>
            </div>
            <input
              id="divian-ai-knowledge-files"
              type="file"
              name="knowledge_files"
              accept=".pdf,.xlsx,.xlsm,.csv,.txt,.json,.md,.docx,.png,.jpg,.jpeg,.webp,.bmp"
              multiple
              required
            />
          </label>

          <div class="knowledge-footer">
            <div>
              <span class="knowledge-file-state" id="divian-ai-knowledge-state">Még nincs kiválasztott fájl</span>
            </div>
            <div class="knowledge-chip-row" aria-label="Támogatott formátumok">
              <span class="knowledge-chip">Dokumentum</span>
              <span class="knowledge-chip">Lista</span>
              <span class="knowledge-chip">Kép</span>
              <span class="knowledge-chip">Export</span>
            </div>
            <div class="action-row">
              <button class="button button-primary" type="submit" id="divian-ai-knowledge-submit">Feltöltés</button>
              <a class="button button-secondary" href="/#divian-ai">Vissza a chathez</a>
            </div>
          </div>
        </form>

        <section class="knowledge-bottom">
          <article class="knowledge-list-card">
            <div class="knowledge-section-head">
              <div>
                <h3>Feltöltött fájlok</h3>
                <p>Itt látod a forrásregisztert és az indexelés állapotát.</p>
              </div>
            </div>
            {recent_list_html}
            {error_note}
          </article>
        </section>
      </div>
    """

    return _render_nettfront_layout(
        heading="AI-tudásbázis",
        lead="Központi hely a Divian-AI számára feltöltött dokumentumoknak, táblázatoknak és képeknek.",
        intro_label="Knowledge base",
        content_html=content_html,
        side_html="",
        notice_html=notice_html,
        extra_script=f"""
  <script>
    (() => {{
      const fileInput = document.getElementById("divian-ai-knowledge-files");
      const fileState = document.getElementById("divian-ai-knowledge-state");
      const form = document.getElementById("divian-ai-knowledge-form");
      const dropzone = document.getElementById("divian-ai-knowledge-dropzone");
      const submitButton = document.getElementById("divian-ai-knowledge-submit");
      if (!fileInput || !fileState || !form || !dropzone || !submitButton) {{
        return;
      }}

      const formatSize = (size) => {{
        const sizeInMb = size / 1024 / 1024;
        if (sizeInMb >= 1) {{
          return `${{sizeInMb.toFixed(1)}} MB`;
        }}
        return `${{Math.round(size / 1024)}} KB`;
      }};

      const updateState = () => {{
        const files = Array.from(fileInput.files || []);
        if (!files.length) {{
          fileState.textContent = "Még nincs kiválasztott fájl";
          return;
        }}

        const totalSize = files.reduce((sum, file) => sum + file.size, 0);
        fileState.textContent = `${{files.length}} fájl kiválasztva · ${{formatSize(totalSize)}}`;
      }};

      ["dragenter", "dragover"].forEach((eventName) => {{
        dropzone.addEventListener(eventName, (event) => {{
          event.preventDefault();
          dropzone.classList.add("is-dragover");
        }});
      }});

      ["dragleave", "drop"].forEach((eventName) => {{
        dropzone.addEventListener(eventName, (event) => {{
          event.preventDefault();
          dropzone.classList.remove("is-dragover");
        }});
      }});

      fileInput.addEventListener("change", updateState);
      form.addEventListener("submit", () => {{
        fileState.textContent = "Feldolgozás indul...";
        submitButton.disabled = true;
        submitButton.textContent = "Feltöltés...";
      }});
    }})();
  </script>
        """,
        single_column=True,
    )


def _divian_ai_normalize_text(text: str) -> str:
    fixed = (
        text.replace("õ", "ő")
        .replace("û", "ű")
        .replace("Õ", "Ő")
        .replace("Û", "Ű")
    )
    fixed = re.sub(r"([a-záéíóöőúüű])([A-ZÁÉÍÓÖŐÚÜŰ])", r"\1 \2", fixed)
    return re.sub(r"\s+", " ", fixed).strip()


def _divian_ai_fold_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", _divian_ai_normalize_text(text).lower())
    return "".join(character for character in normalized if not unicodedata.combining(character))


def _divian_ai_read_upload_manifest() -> list[dict]:
    if not DIVIAN_AI_UPLOAD_MANIFEST.exists():
        return []

    try:
        payload = json.loads(DIVIAN_AI_UPLOAD_MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return []

    if not isinstance(payload, list):
        return []

    entries: list[dict] = []
    for item in payload:
        if isinstance(item, dict):
            entries.append(item)
    return entries


def _divian_ai_write_upload_manifest(entries: list[dict]) -> None:
    DIVIAN_AI_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    DIVIAN_AI_UPLOAD_MANIFEST.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _divian_ai_upload_display_map() -> dict[str, dict]:
    mapping: dict[str, dict] = {}
    for entry in _divian_ai_read_upload_manifest():
        stored_name = str(entry.get("stored_name", "")).strip()
        if stored_name:
            mapping[stored_name] = entry
    return mapping


def _divian_ai_source_entry_id(path: Path, upload_entry: dict | None = None) -> str:
    existing_id = str((upload_entry or {}).get("id", "")).strip().lower()
    if re.fullmatch(r"[a-f0-9]{12}", existing_id):
        return existing_id

    try:
        source_key = str(path.resolve()).lower()
    except Exception:
        source_key = str(path).lower()
    return uuid.uuid5(uuid.NAMESPACE_URL, source_key).hex[:12]


def _divian_ai_source_entry(entry_id: str) -> tuple[Path, dict | None] | None:
    normalized_id = entry_id.strip().lower()
    if not re.fullmatch(r"[a-f0-9]{12}", normalized_id):
        return None

    manifest_map = _divian_ai_upload_display_map()
    for path in _divian_ai_source_paths():
        upload_entry = manifest_map.get(path.name)
        if _divian_ai_source_entry_id(path, upload_entry) == normalized_id:
            return path, upload_entry
    return None


def _divian_ai_upload_entry(entry_id: str) -> dict | None:
    normalized_id = entry_id.strip().lower()
    if not re.fullmatch(r"[a-f0-9]{12}", normalized_id):
        return None

    for entry in _divian_ai_read_upload_manifest():
        current_id = str(entry.get("id", "")).strip().lower()
        if current_id == normalized_id:
            return entry
    return None


def _divian_ai_upload_path(stored_name: str) -> Path | None:
    clean_name = Path(stored_name).name.strip()
    if not clean_name:
        return None

    try:
        upload_root = DIVIAN_AI_UPLOAD_DIR.resolve()
        file_path = (DIVIAN_AI_UPLOAD_DIR / clean_name).resolve()
    except Exception:
        return None

    if file_path.parent != upload_root:
        return None
    return file_path


def _divian_ai_previewable(path: Path) -> bool:
    suffix = path.suffix.lower()
    return suffix in {".pdf", ".csv", ".txt", ".md", ".json"} or suffix in DIVIAN_AI_IMAGE_EXTENSIONS


def _divian_ai_content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix in {".txt", ".md"}:
        return "text/plain; charset=utf-8"
    if suffix == ".json":
        return "application/json; charset=utf-8"
    if suffix == ".csv":
        return "text/csv; charset=utf-8"
    guessed_type, _ = mimetypes.guess_type(path.name)
    return guessed_type or "application/octet-stream"


def _divian_ai_upload_payload(entry_id: str, download: bool = False) -> tuple[bytes, str, str, str] | None:
    resolved_entry = _divian_ai_source_entry(entry_id)
    if resolved_entry is None:
        return None

    file_path, upload_entry = resolved_entry
    if not file_path.exists():
        return None

    original_name = str((upload_entry or {}).get("original_name", "")).strip() or file_path.name
    disposition = "attachment" if download or not _divian_ai_previewable(file_path) else "inline"
    return file_path.read_bytes(), _divian_ai_content_type(file_path), original_name, disposition


def _delete_divian_ai_upload(entry_id: str) -> tuple[bool, str]:
    resolved_entry = _divian_ai_source_entry(entry_id)
    if resolved_entry is None:
        return False, "A fájl nem található."

    file_path, upload_entry = resolved_entry
    entries = _divian_ai_read_upload_manifest()
    remaining_entries: list[dict] = []
    removed_manifest_entry: dict | None = None

    for entry in entries:
        current_id = str(entry.get("id", "")).strip().lower()
        current_stored_name = str(entry.get("stored_name", "")).strip()
        if (
            current_id == entry_id.strip().lower()
            or current_stored_name == file_path.name
        ) and removed_manifest_entry is None:
            removed_manifest_entry = entry
            continue
        remaining_entries.append(entry)

    try:
        if file_path.exists():
            file_path.unlink()
    except Exception as exc:
        return False, f"Nem sikerült törölni: {file_path.name} ({exc})"

    if len(remaining_entries) != len(entries):
        _divian_ai_write_upload_manifest(remaining_entries)
    global DIVIAN_AI_CACHE
    DIVIAN_AI_CACHE = DivianAIKnowledgeCache()
    _load_divian_ai_knowledge()

    original_name = str((upload_entry or removed_manifest_entry or {}).get("original_name", "")).strip() or file_path.name
    return True, f"Törölve: {original_name}"


def _divian_ai_source_display_name(path: Path) -> str:
    public_web_entry = _divian_ai_public_web_entry(path)
    if public_web_entry:
        display_name = str(public_web_entry.get("name", "")).strip()
        if display_name:
            return display_name

    entry = _divian_ai_upload_display_map().get(path.name)
    original_name = str(entry.get("original_name", "")).strip() if entry else ""
    return original_name or path.name


def _divian_ai_uploaded_source_names() -> set[str]:
    names: set[str] = set()
    for entry in _divian_ai_read_upload_manifest():
        original_name = str(entry.get("original_name", "")).strip()
        if original_name:
            names.add(original_name)

    if DIVIAN_AI_UPLOAD_DIR.exists():
        for source_path in DIVIAN_AI_UPLOAD_DIR.glob("*"):
            if not source_path.is_file() or source_path.suffix.lower() not in DIVIAN_AI_SUPPORTED_EXTENSIONS:
                continue
            names.add(_divian_ai_source_display_name(source_path))
    return names


def _divian_ai_filter_knowledge_sources(
    knowledge: DivianAIKnowledgeCache,
    allowed_sources: set[str],
) -> DivianAIKnowledgeCache:
    if not allowed_sources:
        return DivianAIKnowledgeCache()

    pages = [page for page in knowledge.pages if page.source_name in allowed_sources]
    chunks = [chunk for chunk in knowledge.chunks if chunk.source_name in allowed_sources]
    records = [record for record in knowledge.records if record.source_name in allowed_sources]
    sources = [source for source in knowledge.sources if source in allowed_sources]
    return DivianAIKnowledgeCache(
        signature=knowledge.signature,
        sources=sources,
        source_meta={source: dict(knowledge.source_meta.get(source, {})) for source in sources},
        pages=pages,
        chunks=chunks,
        records=records,
        errors=[],
    )


def _divian_ai_source_meta_value(
    knowledge: DivianAIKnowledgeCache,
    source_name: str,
    key: str,
) -> str:
    return str((knowledge.source_meta.get(source_name) or {}).get(key, "")).strip()


def _divian_ai_confidence_rank(value: str) -> int:
    folded_value = _divian_ai_fold_text(value)
    if folded_value == "magas":
        return 3
    if folded_value == "kozepes":
        return 2
    if folded_value == "alacsony":
        return 1
    return 0


def _divian_ai_study_mode_rank(value: str) -> int:
    folded_value = _divian_ai_fold_text(value)
    if folded_value == "strukturalt":
        return 3
    if folded_value == "web":
        return 2
    if folded_value == "szoveges":
        return 1
    return 0


def _divian_ai_iso_sort_value(value: str) -> str:
    clean_value = str(value or "").strip()
    try:
        return datetime.fromisoformat(clean_value).isoformat(timespec="seconds")
    except Exception:
        return ""


def _divian_ai_source_quality_key(
    knowledge: DivianAIKnowledgeCache,
    source_name: str,
) -> tuple[int, int, int, str, str, int, str]:
    meta = knowledge.source_meta.get(source_name) or {}
    study_mode = _divian_ai_study_mode_rank(str(meta.get("study_mode", "")))
    confidence = _divian_ai_confidence_rank(str(meta.get("confidence", "")))
    is_uploaded = 1 if str(meta.get("is_uploaded", "")).strip() in {"1", "true", "True"} else 0
    uploaded_at = _divian_ai_iso_sort_value(str(meta.get("uploaded_at", "")))
    updated_at = _divian_ai_iso_sort_value(str(meta.get("updated_at", "")))
    parser_bonus = 1 if "parser" in _divian_ai_fold_text(str(meta.get("parser_name", ""))) else 0
    return (study_mode, confidence, is_uploaded, uploaded_at, updated_at, parser_bonus, _divian_ai_fold_text(source_name))


def _divian_ai_ranked_sources(
    knowledge: DivianAIKnowledgeCache,
    predicate=None,
) -> list[str]:
    sources = [source for source in knowledge.sources if predicate is None or predicate(source)]
    return sorted(
        sources,
        key=lambda source: _divian_ai_source_quality_key(knowledge, source),
        reverse=True,
    )


def _divian_ai_preferred_structured_sources(
    knowledge: DivianAIKnowledgeCache,
    *,
    source_type: str = "",
    limit: int = 3,
) -> list[str]:
    normalized_type = _divian_ai_fold_text(source_type)

    def predicate(source_name: str) -> bool:
        meta = knowledge.source_meta.get(source_name) or {}
        if _divian_ai_fold_text(str(meta.get("study_mode", ""))) != "strukturalt":
            return False
        if _divian_ai_confidence_rank(str(meta.get("confidence", ""))) < 2:
            return False
        if normalized_type == "catalog" and not _divian_ai_source_is_catalog(source_name):
            return False
        if normalized_type == "elemjegyzek" and not _divian_ai_source_is_elemjegyzek(source_name):
            return False
        return True

    ranked = _divian_ai_ranked_sources(knowledge, predicate)
    return ranked[:limit] if limit > 0 else ranked


def _divian_ai_preferred_handbook_sources(
    knowledge: DivianAIKnowledgeCache,
    *,
    limit: int = 2,
) -> list[str]:
    handbook_hints = ("kezikonyv", "kézikönyv", "termekinformacios", "termékinformációs")
    handbook_sources = _divian_ai_ranked_sources(
        knowledge,
        lambda source_name: (
            source_name in _divian_ai_preferred_structured_sources(knowledge, source_type="catalog", limit=0)
            and any(hint in _divian_ai_fold_text(source_name) for hint in handbook_hints)
        ),
    )
    if handbook_sources:
        return handbook_sources[:limit] if limit > 0 else handbook_sources
    return _divian_ai_preferred_structured_sources(knowledge, source_type="catalog", limit=limit)


def _divian_ai_cleanup_material_colors(colors: list[str], material_key: str) -> list[str]:
    cleaned: list[str] = []
    seen_colors: set[str] = set()
    blocked_terms = {"krom", "króm", "arany", "rose gold"}
    front_only_terms = {"fenyes", "fényes", "szuper matt"}

    for color in colors:
        folded_color = _divian_ai_fold_text(color)
        if not folded_color:
            continue
        if any(term in folded_color for term in blocked_terms):
            continue
        if material_key == "butorlap" and any(term in folded_color for term in front_only_terms):
            continue
        if folded_color in seen_colors:
            continue
        seen_colors.add(folded_color)
        cleaned.append(color)
    return cleaned


def _divian_ai_known_colors_from_folded_text(folded_text: str) -> list[str]:
    if not folded_text:
        return []

    matches: list[tuple[int, int, str]] = []
    for phrase in sorted(DIVIAN_AI_COLOR_PHRASES, key=len, reverse=True):
        folded_phrase = _divian_ai_fold_text(phrase)
        if not folded_phrase:
            continue
        start = 0
        while True:
            position = folded_text.find(folded_phrase, start)
            if position == -1:
                break
            matches.append((position, len(folded_phrase), phrase))
            start = position + len(folded_phrase)

    matches.sort(key=lambda item: (item[0], -item[1], item[2]))
    colors: list[str] = []
    last_end = -1
    for position, length, phrase in matches:
        if position < last_end:
            continue
        colors.append(phrase)
        last_end = position + length
    return colors


def _divian_ai_folded_section_colors(
    folded_text: str,
    *,
    start_marker: str,
    end_markers: tuple[str, ...] = (),
) -> list[str]:
    normalized_start = _divian_ai_fold_text(start_marker)
    if not normalized_start:
        return []

    start_position = folded_text.find(normalized_start)
    if start_position == -1:
        return []

    content_start = start_position + len(normalized_start)
    content_end = len(folded_text)
    for marker in end_markers:
        normalized_end = _divian_ai_fold_text(marker)
        if not normalized_end:
            continue
        marker_position = folded_text.find(normalized_end, content_start)
        if marker_position != -1:
            content_end = min(content_end, marker_position)

    section_text = folded_text[content_start:content_end]
    return _divian_ai_known_colors_from_folded_text(section_text)


def _divian_ai_unique_values(values: list[str]) -> list[str]:
    unique_values: list[str] = []
    seen_values: set[str] = set()
    for value in values:
        normalized_value = _divian_ai_fold_text(value)
        if not normalized_value or normalized_value in seen_values:
            continue
        seen_values.add(normalized_value)
        unique_values.append(value)
    return unique_values


def _divian_ai_handbook_kitchen_page_data(page: DivianAIPage) -> dict | None:
    title_folded = _divian_ai_fold_text(page.title)
    if "konyha" not in title_folded:
        return None

    kitchen_key = ""
    for candidate_key in DIVIAN_AI_PRODUCT_ALIASES:
        if candidate_key in {"doroti", "antonia", "laura", "zille", "anna", "kira", "kata", "kinga", "klio"}:
            if any(_divian_ai_fold_text(alias) in title_folded for alias in DIVIAN_AI_PRODUCT_ALIASES[candidate_key]):
                kitchen_key = candidate_key
                break
    if not kitchen_key:
        return None

    page_folded = page.folded
    front_colors: list[str] = []
    butorlap_colors: list[str] = []

    if kitchen_key == "doroti":
        grouped_colors = _divian_ai_folded_section_colors(
            page_folded,
            start_marker="MDF fóliás frontok Látható korpusz színek Nem látható korpusz színek Bútorlap frontok",
            end_markers=("ÚJ!",),
        )
        if grouped_colors:
            front_colors = _divian_ai_unique_values(grouped_colors[0::4] + grouped_colors[3::4])
            butorlap_colors = _divian_ai_unique_values(grouped_colors[1::4] + grouped_colors[2::4])
    elif kitchen_key == "antonia":
        front_section = _divian_ai_folded_section_colors(
            page_folded,
            start_marker="Matt frontok Magasfényû frontok",
            end_markers=("Látható és nem látható korpusz színek",),
        )
        if front_section:
            front_colors = _divian_ai_unique_values(front_section)
        board_section = _divian_ai_folded_section_colors(
            page_folded,
            start_marker="Látható korpusz színek Nem látható korpusz színek",
            end_markers=("A Szuper matt frontok fõ elõnyei", "ÚJ!"),
        )
        if board_section:
            butorlap_colors = _divian_ai_unique_values(board_section)
    elif kitchen_key in {"laura", "zille"}:
        front_section = _divian_ai_folded_section_colors(
            page_folded,
            start_marker="Front színek",
            end_markers=("Látható és nem látható korpusz színek",),
        )
        if front_section:
            front_colors = _divian_ai_unique_values(front_section)
        board_section = _divian_ai_folded_section_colors(
            page_folded,
            start_marker="Látható korpusz színek Nem látható korpusz színek",
            end_markers=("A Szuper matt frontok fõ elõnyei", "ÚJ!", "Fogantyú"),
        )
        if board_section:
            butorlap_colors = _divian_ai_unique_values(board_section)
    else:
        board_section = _divian_ai_folded_section_colors(
            page_folded,
            start_marker="Látható korpusz színek Nem látható korpusz színek",
            end_markers=("Munkalap", "Garancia", "Fogantyú", "ÚJ!"),
        )
        if board_section:
            butorlap_colors = _divian_ai_unique_values(board_section)
        front_section = _divian_ai_folded_section_colors(
            page_folded,
            start_marker="Front színek",
            end_markers=("Látható és nem látható korpusz színek", "Munkalap", "Garancia"),
        )
        if front_section:
            front_colors = _divian_ai_unique_values(front_section)

    if not front_colors and not butorlap_colors:
        return None

    return {
        "kitchen_key": kitchen_key,
        "kitchen_label": _divian_ai_product_label(kitchen_key) or kitchen_key.title(),
        "front_colors": front_colors,
        "butorlap_colors": butorlap_colors,
        "source": page.label,
    }


def _divian_ai_structured_catalog_material_answer(
    question: str,
    knowledge: DivianAIKnowledgeCache,
    evidence_label: str = "A Divian források alapján",
) -> dict | None:
    if not _divian_ai_is_color_question(question):
        return None

    subject_keys = set(_divian_ai_detect_subject_keys(question))
    material_subjects = {"butorlap", "front"} & subject_keys
    if not material_subjects:
        return None

    preferred_sources = set(_divian_ai_preferred_handbook_sources(knowledge, limit=2))
    if not preferred_sources:
        return None

    kitchen_filter = set(_divian_ai_detect_product_keys(question))
    page_materials: list[dict] = []
    for page in knowledge.pages:
        if page.source_name not in preferred_sources:
            continue
        page_data = _divian_ai_handbook_kitchen_page_data(page)
        if page_data is None:
            continue
        if kitchen_filter and page_data["kitchen_key"] not in kitchen_filter:
            continue
        page_materials.append(page_data)

    if not page_materials:
        return None

    color_bucket_key = "butorlap_colors" if "butorlap" in material_subjects else "front_colors"
    material_key = "butorlap" if color_bucket_key == "butorlap_colors" else "front"
    material_label = "bútorlap színei" if color_bucket_key == "butorlap_colors" else "front színei"
    source_labels: list[str] = []
    seen_sources: set[str] = set()

    if kitchen_filter:
        page_data = page_materials[0]
        colors = _divian_ai_cleanup_material_colors(
            _divian_ai_unique_values(page_data.get(color_bucket_key, [])),
            material_key,
        )
        if not colors:
            return None
        if page_data["source"] not in seen_sources:
            seen_sources.add(page_data["source"])
            source_labels.append(page_data["source"])
        return {
            "ok": True,
            "answer": f"{page_data['kitchen_label']} {material_label}:\n- " + "\n- ".join(colors),
            "sources": source_labels,
        }

    merged_colors: list[str] = []
    for page_data in page_materials:
        merged_colors.extend(page_data.get(color_bucket_key, []))
        if page_data["source"] not in seen_sources:
            seen_sources.add(page_data["source"])
            source_labels.append(page_data["source"])

    merged_colors = _divian_ai_cleanup_material_colors(_divian_ai_unique_values(merged_colors), material_key)
    if not merged_colors:
        return None

    noun = "bútorlap színek/dekorok" if color_bucket_key == "butorlap_colors" else "front színek"
    return {
        "ok": True,
        "answer": f"{evidence_label} ezek a fő {noun} érhetők el:\n- " + "\n- ".join(merged_colors),
        "sources": source_labels[:4],
    }


def _divian_ai_best_chunk_evidence(question: str, chunks: list[DivianAIChunk]) -> tuple[int, int, int, bool, int]:
    question_normalized = _divian_ai_fold_text(question)
    question_tokens = _divian_ai_focus_tokens(question) or _divian_ai_tokens(question)
    best_score = 0
    best_overlap = 0
    longest_overlap = 0
    phrase_match = False
    best_source_affinity = 0

    for chunk in chunks:
        overlap = question_tokens & chunk.tokens
        score = len(overlap) * 6
        for token in overlap:
            score += min(chunk.normalized.count(token), 3)

        current_phrase_match = bool(question_normalized and question_normalized in chunk.normalized)
        if current_phrase_match:
            score += 10

        source_affinity = _divian_ai_source_affinity_score(question, chunk.source_name, chunk.label)
        score += source_affinity

        best_score = max(best_score, score)
        best_overlap = max(best_overlap, len(overlap))
        if overlap:
            longest_overlap = max(longest_overlap, max(len(token) for token in overlap))
        phrase_match = phrase_match or current_phrase_match
        best_source_affinity = max(best_source_affinity, source_affinity)

    return best_score, best_overlap, longest_overlap, phrase_match, best_source_affinity


def _divian_ai_has_confident_evidence(question: str, chunks: list[DivianAIChunk]) -> bool:
    if not chunks:
        return False

    best_score, best_overlap, longest_overlap, phrase_match, best_source_affinity = _divian_ai_best_chunk_evidence(question, chunks)
    focus_tokens = _divian_ai_focus_tokens(question)
    if phrase_match:
        return True

    if len(focus_tokens) >= 2:
        if best_overlap >= 2 and best_score >= 12:
            return True
        return best_source_affinity >= 10 and best_score >= 10

    if _divian_ai_detect_product_keys(question) and best_overlap >= 1 and best_score >= 6:
        return True

    if best_source_affinity >= 10 and best_score >= 8:
        return True

    if best_overlap >= 2 and best_score >= 10:
        return True

    return longest_overlap >= 7 and best_score >= 6


def _divian_ai_no_confident_answer(question: str = "", prefer_uploaded_sources: bool = False) -> dict:
    guidance = _divian_ai_upload_guidance(question, prefer_uploaded_sources=prefer_uploaded_sources)
    if prefer_uploaded_sources:
        return {
            "ok": True,
            "answer": (
                "A jelenlegi Divian forrásokban ehhez nem találtam elég biztos információt. "
                "Nem szeretnék találgatni.\n\n"
                f"{guidance}"
            ),
            "sources": [],
        }

    return {
        "ok": True,
        "answer": (
            "Ehhez most nem találtam elég biztos információt a jelenlegi Divian forrásokban. "
            "Nem szeretnék találgatni.\n\n"
            f"{guidance}"
        ),
        "sources": [],
    }


def _divian_ai_parse_date(value: str) -> datetime | None:
    raw_value = _divian_ai_normalize_text(value)
    patterns = (
        "%Y-%m-%d",
        "%Y.%m.%d",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y.%m.%d.",
        "%d.%m.%Y.",
    )
    for pattern in patterns:
        try:
            return datetime.strptime(raw_value, pattern)
        except ValueError:
            continue
    return None


def _divian_ai_format_date(value: str) -> str:
    parsed_date = _divian_ai_parse_date(value)
    if parsed_date is None:
        return value
    return parsed_date.strftime("%Y-%m-%d")


def _divian_ai_question_month_filter(question: str) -> tuple[int, int] | None:
    folded_question = _divian_ai_fold_text(question)
    now = datetime.now()
    month_map = {
        "januar": 1,
        "februar": 2,
        "marcius": 3,
        "aprilis": 4,
        "majus": 5,
        "junius": 6,
        "julius": 7,
        "augusztus": 8,
        "szeptember": 9,
        "oktober": 10,
        "november": 11,
        "december": 12,
    }

    if "ebben a honapban" in folded_question or "a honapban" in folded_question:
        return now.year, now.month

    year_match = re.search(r"\b(20\d{2})\b", folded_question)
    target_year = int(year_match.group(1)) if year_match else now.year
    for month_name, month_number in month_map.items():
        if month_name in folded_question:
            return target_year, month_number

    return None


def _divian_ai_select_records(question: str, records: list[DivianAIRecord], limit: int = 8) -> list[tuple[int, DivianAIRecord]]:
    question_normalized = _divian_ai_fold_text(question)
    focus_tokens = _divian_ai_focus_tokens(question)
    question_tokens = focus_tokens or _divian_ai_tokens(question)
    if not question_tokens:
        return []

    asks_when = any(term in question_normalized for term in ("mikor", "datum", "esedekes", "hatarido", "honap"))
    asks_list = any(term in question_normalized for term in ("kik", "sorold", "listaz", "melyek"))
    scored_records: list[tuple[int, DivianAIRecord]] = []
    for record in records:
        overlap = question_tokens & record.tokens
        source_affinity = _divian_ai_source_affinity_score(question, record.source_name, record.label)
        if not overlap and not source_affinity:
            continue

        if len(focus_tokens) >= 2 and not overlap and source_affinity < 10:
            continue

        score = len(overlap) * 7 + source_affinity
        for token in overlap:
            score += min(record.normalized.count(token), 3)

        for key, value in record.fields:
            field_key_tokens = _divian_ai_tokens(key)
            field_value_tokens = _divian_ai_tokens(value)
            field_overlap = question_tokens & field_key_tokens
            value_overlap = question_tokens & field_value_tokens
            score += len(field_overlap) * 8
            score += len(value_overlap) * 5
            if asks_when and _divian_ai_parse_date(value):
                score += 4
            if asks_list and any(name_token in _divian_ai_fold_text(key) for name_token in ("nev", "dolgozo", "munkatars", "szemely")):
                score += 3

        if question_normalized and question_normalized in record.normalized:
            score += 12

        unique_key_count = _divian_ai_record_unique_key_count(record)
        if unique_key_count >= 2:
            score += 3
        if _divian_ai_record_has_descriptive_field(record):
            score += 5
        if asks_list and unique_key_count == 1 and not _divian_ai_record_has_descriptive_field(record):
            score -= 12

        scored_records.append((score, record))

    scored_records.sort(key=lambda item: (item[0], len(item[1].fields), len(item[1].text)), reverse=True)
    return scored_records[:limit]


def _divian_ai_record_name_field(record: DivianAIRecord) -> str:
    name_priority = ("nev", "dolgozo", "munkatars", "szemely", "partner", "ugyfel", "megnevezes", "tema")
    for key, value in record.fields:
        folded_key = _divian_ai_fold_text(key)
        if any(token in folded_key for token in name_priority):
            return value
    return record.fields[0][1]


def _divian_ai_record_best_field(record: DivianAIRecord, question: str) -> tuple[str, str] | None:
    best_field = _divian_ai_record_display_field(record, question)
    return best_field if best_field is not None else record.fields[0]


def _divian_ai_record_answer(question: str, knowledge: DivianAIKnowledgeCache) -> dict | None:
    if not knowledge.records:
        return None

    selected_records = _divian_ai_select_records(question, knowledge.records)
    if not selected_records:
        return None

    top_score = selected_records[0][0]
    if top_score < 6:
        return None

    month_filter = _divian_ai_question_month_filter(question)
    if month_filter is not None:
        filtered_records: list[tuple[int, DivianAIRecord]] = []
        for score, record in selected_records:
            for _, value in record.fields:
                parsed_date = _divian_ai_parse_date(value)
                if parsed_date and (parsed_date.year, parsed_date.month) == month_filter:
                    filtered_records.append((score + 6, record))
                    break
        if filtered_records:
            selected_records = sorted(
                filtered_records,
                key=lambda item: min(
                    (
                        _divian_ai_parse_date(value)
                        for _, value in item[1].fields
                        if _divian_ai_parse_date(value) is not None
                    ),
                    default=datetime.max,
                ),
            )

    question_folded = _divian_ai_fold_text(question)
    asks_list = any(term in question_folded for term in ("sorold", "listaz", "kik", "melyek"))
    asks_count = any(term in question_folded for term in ("hany", "mennyi"))
    asks_when = any(term in question_folded for term in ("mikor", "hatarido", "datum", "esedekes"))
    preferred_source = _divian_ai_preferred_record_source(question, selected_records)
    if preferred_source:
        preferred_records = [item for item in selected_records if item[1].source_name == preferred_source]
        if preferred_records:
            selected_records = preferred_records

    source_labels: list[str] = []
    seen_sources: set[str] = set()
    for _, record in selected_records:
        if record.label not in seen_sources:
            seen_sources.add(record.label)
            source_labels.append(record.label)

    if asks_count:
        answer = f"A Divian források alapján {len(selected_records)} releváns találatot találtam."
        return {"ok": True, "answer": answer, "sources": source_labels[:4]}

    if asks_list:
        items: list[str] = []
        seen_items: set[str] = set()
        for _, record in selected_records:
            display_field = _divian_ai_record_display_field(record, question)
            item_value = display_field[1] if display_field is not None else _divian_ai_record_name_field(record)
            if not item_value or _divian_ai_is_code_like(item_value):
                continue
            normalized_item = _divian_ai_fold_text(item_value)
            if normalized_item in seen_items:
                continue
            seen_items.add(normalized_item)
            items.append(item_value)
            if len(items) == 8:
                break
        if items:
            if len(items) == 1:
                answer = f"A Divian források alapján ezt találtam: {items[0]}."
            else:
                answer = "A Divian források alapján ezeket találtam:\n- " + "\n- ".join(items)
            return {"ok": True, "answer": answer, "sources": source_labels[:4]}

    top_record = selected_records[0][1]
    best_field = _divian_ai_record_best_field(top_record, question)
    subject_name = _divian_ai_record_name_field(top_record)
    top_record_sources = [top_record.label]
    if asks_when and best_field is not None:
        if _divian_ai_parse_date(best_field[1]) is not None:
            folded_key = _divian_ai_fold_text(best_field[0])
            if "esedekes" in folded_key:
                answer = f"A Divian források alapján {subject_name} esetén {best_field[0].lower()}: {_divian_ai_format_date(best_field[1])}."
            else:
                answer = f"A Divian források alapján {subject_name} esetén a releváns dátum: {_divian_ai_format_date(best_field[1])}."
        else:
            answer = f"A Divian források alapján {subject_name} esetén {best_field[0].lower()}: {best_field[1]}."
        return {"ok": True, "answer": answer, "sources": top_record_sources}

    if best_field is not None:
        answer = f"A Divian források alapján {subject_name} esetén {best_field[0].lower()}: {best_field[1]}."
        return {"ok": True, "answer": answer, "sources": top_record_sources}

    compact_fields = ", ".join(f"{key}: {value}" for key, value in top_record.fields[:3])
    answer = f"A Divian források alapján ezt találtam: {compact_fields}."
    return {"ok": True, "answer": answer, "sources": top_record_sources}


def _divian_ai_safe_filename(name: str) -> str:
    source_name = Path(name).name.strip() or "feltoltes"
    stem = unicodedata.normalize("NFKD", Path(source_name).stem)
    stem = "".join(character for character in stem if not unicodedata.combining(character))
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._") or "dokumentum"
    suffix = re.sub(r"[^A-Za-z0-9.]+", "", Path(source_name).suffix.lower())[:12]
    if suffix not in DIVIAN_AI_SUPPORTED_EXTENSIONS:
        suffix = ""
    return f"{stem}{suffix}"


def _divian_ai_doc_kind(path: Path) -> str:
    if _divian_ai_public_web_entry(path):
        return "Nyilvános web"

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "PDF"
    if suffix in {".xlsx", ".xlsm"}:
        return "Excel"
    if suffix == ".csv":
        return "CSV"
    if suffix == ".docx":
        return "DOCX"
    if suffix in DIVIAN_AI_IMAGE_EXTENSIONS:
        return "Kép"
    if suffix == ".json":
        return "JSON"
    if suffix in {".txt", ".md"}:
        return "Szöveg"
    return suffix.lstrip(".").upper() or "Dokumentum"


def _divian_ai_source_study_profile(path: Path, source_name: str) -> tuple[str, str, str, str]:
    folded_name = _divian_ai_fold_text(source_name or path.name)
    if _divian_ai_public_web_entry(path) is not None:
        return ("Nyilvános web parser", "web", "magas", "Hivatalos nyilvános webforrásként feltérképezve.")
    if _divian_ai_is_elemjegyzek_source(source_name or path.name):
        return ("Elemjegyzék parser", "strukturált", "magas", "Az elemjegyzék külön szerkezeti parserrel kerül feldolgozásra.")
    if any(term in folded_name for term in ("katalogus", "katalógus", "kezikonyv", "kézikönyv")):
        return ("Katalógus parser", "strukturált", "kozepes", "A katalógusból célzott oldaltípus-parser próbál strukturált adatot kinyerni.")
    if path.suffix.lower() in DIVIAN_AI_SPREADSHEET_EXTENSIONS:
        return ("Táblázat parser", "strukturált", "magas", "A táblázat soronként és oszloponként kerül beolvasásra.")
    if path.suffix.lower() in DIVIAN_AI_WORD_EXTENSIONS:
        return ("Dokumentum parser", "szöveges", "kozepes", "A dokumentum szöveges és kulcs-érték alapú feldolgozást kap.")
    if path.suffix.lower() in DIVIAN_AI_IMAGE_EXTENSIONS:
        return ("OCR parser", "szöveges", "alacsony", "A kép OCR-rel kerül beolvasásra, ezért kézi ellenőrzés javasolt.")
    if path.suffix.lower() == ".pdf":
        return ("Általános PDF parser", "szöveges", "kozepes", "A PDF nyers szövegkinyeréssel kerül feldolgozásra.")
    return ("Általános parser", "szöveges", "alacsony", "A forrás általános szövegkinyeréssel kerül beolvasásra.")


def _divian_ai_source_paths() -> list[Path]:
    candidates: list[Path] = []
    env_value = os.getenv(DIVIAN_AI_KNOWLEDGE_ENV, "").strip()
    if env_value:
        for raw_path in re.split(r"[;\r\n]+", env_value):
            raw_path = raw_path.strip()
            if raw_path:
                candidates.append(Path(raw_path).expanduser())

    candidates.extend(DIVIAN_AI_DEFAULT_KNOWLEDGE_FILES)
    if DIVIAN_AI_KNOWLEDGE_DIR.exists():
        candidates.extend(sorted(path for path in DIVIAN_AI_KNOWLEDGE_DIR.rglob("*") if path.is_file()))

    unique_paths: list[Path] = []
    seen_paths: set[str] = set()
    for path in candidates:
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path

        key = str(resolved).lower()
        if key in seen_paths:
            continue
        seen_paths.add(key)

        if resolved.exists() and resolved.is_file() and resolved.suffix.lower() in DIVIAN_AI_SUPPORTED_EXTENSIONS:
            unique_paths.append(resolved)

    return unique_paths


def _divian_ai_curated_document_paths() -> list[Path]:
    curated_paths: list[Path] = []
    seen_paths: set[str] = set()
    for path in _divian_ai_source_paths():
        if path.suffix.lower() != ".pdf":
            continue

        folded_name = _divian_ai_fold_text(path.name)
        if not any(hint in folded_name for hint in DIVIAN_AI_CURATED_DOCUMENT_HINTS):
            continue

        path_key = _divian_ai_source_key(path)
        if path_key in seen_paths:
            continue
        seen_paths.add(path_key)
        curated_paths.append(path)
    return curated_paths


def _divian_ai_tokens(text: str) -> frozenset[str]:
    raw_tokens = re.findall(r"[0-9a-z-]{3,}", _divian_ai_fold_text(text))
    tokens: set[str] = set()
    folded_stopwords = {_divian_ai_fold_text(word) for word in DIVIAN_AI_STOPWORDS}

    for token in raw_tokens:
        if token in folded_stopwords:
            continue

        tokens.add(token)
        if "-" in token:
            for part in token.split("-"):
                if len(part) >= 3 and part not in folded_stopwords:
                    tokens.add(part)
        for suffix in DIVIAN_AI_TOKEN_SUFFIXES:
            if token.endswith(suffix):
                stem = token[: -len(suffix)]
                if len(stem) >= 3 and stem not in folded_stopwords:
                    tokens.add(stem)

    return frozenset(tokens)


def _divian_ai_focus_tokens(text: str) -> frozenset[str]:
    folded_meta_tokens = {_divian_ai_fold_text(value) for value in DIVIAN_AI_QUERY_META_TOKENS}
    return frozenset(token for token in _divian_ai_tokens(text) if token not in folded_meta_tokens)


def _divian_ai_source_affinity_score(question: str, *source_values: str) -> int:
    focus_tokens = _divian_ai_focus_tokens(question)
    if not focus_tokens:
        return 0

    source_text = " ".join(value for value in source_values if value)
    if not source_text:
        return 0

    source_tokens = _divian_ai_tokens(source_text)
    overlap = focus_tokens & source_tokens
    if not overlap:
        return 0

    score = len(overlap) * 10
    folded_source_text = _divian_ai_fold_text(source_text)
    for token in overlap:
        if len(token) >= 5 and token in folded_source_text:
            score += 2
    return score


def _divian_ai_record_unique_key_count(record: DivianAIRecord) -> int:
    return len({_divian_ai_fold_text(key) for key, _ in record.fields if key.strip()})


def _divian_ai_record_has_descriptive_field(record: DivianAIRecord) -> bool:
    hints = DIVIAN_AI_NAME_FIELD_HINTS + DIVIAN_AI_DESCRIPTION_FIELD_HINTS
    for key, _ in record.fields:
        folded_key = _divian_ai_fold_text(key)
        if any(hint in folded_key for hint in hints):
            return True
    return False


def _divian_ai_is_code_like(value: str) -> bool:
    stripped_value = value.strip()
    if not stripped_value:
        return False

    if re.fullmatch(r"[A-Z0-9._/-]{3,}", stripped_value):
        return True

    digit_count = sum(character.isdigit() for character in stripped_value)
    alpha_count = sum(character.isalpha() for character in stripped_value)
    return digit_count >= 3 and alpha_count <= 4 and len(stripped_value) <= 24


def _divian_ai_record_display_field(record: DivianAIRecord, question: str) -> tuple[str, str] | None:
    focus_tokens = _divian_ai_focus_tokens(question) or _divian_ai_tokens(question)
    asks_when = any(term in _divian_ai_fold_text(question) for term in ("mikor", "datum", "esedekes", "hatarido", "honap"))
    best_field: tuple[str, str] | None = None
    best_score = -10**9

    for key, value in record.fields:
        folded_key = _divian_ai_fold_text(key)
        key_tokens = _divian_ai_tokens(key)
        value_tokens = _divian_ai_tokens(value)
        score = len(focus_tokens & key_tokens) * 8
        score += len(focus_tokens & value_tokens) * 6

        if any(hint in folded_key for hint in DIVIAN_AI_NAME_FIELD_HINTS):
            score += 10
        if any(hint in folded_key for hint in DIVIAN_AI_DESCRIPTION_FIELD_HINTS):
            score += 8
        if asks_when and _divian_ai_parse_date(value):
            score += 12
        if _divian_ai_is_code_like(value):
            score -= 10
        if len(value.strip()) < 3:
            score -= 8

        if score > best_score:
            best_score = score
            best_field = (key, value)

    return best_field


def _divian_ai_preferred_record_source(
    question: str,
    selected_records: list[tuple[int, DivianAIRecord]],
) -> str | None:
    if not selected_records:
        return None

    scored_sources: dict[str, int] = {}
    for score, record in selected_records:
        source_score = score + _divian_ai_source_affinity_score(question, record.source_name, record.label)
        if _divian_ai_record_has_descriptive_field(record):
            source_score += 4
        if _divian_ai_record_unique_key_count(record) >= 2:
            source_score += 2
        scored_sources[record.source_name] = scored_sources.get(record.source_name, 0) + source_score

    if not scored_sources:
        return None

    ranked_sources = sorted(scored_sources.items(), key=lambda item: item[1], reverse=True)
    best_source, best_score = ranked_sources[0]
    next_score = ranked_sources[1][1] if len(ranked_sources) > 1 else 0
    best_affinity = _divian_ai_source_affinity_score(question, best_source)

    if best_affinity >= 10 or best_score >= next_score + 10:
        return best_source
    return None


def _divian_ai_build_record(
    label: str,
    source_name: str,
    row_number: int,
    fields: list[tuple[str, str]],
) -> DivianAIRecord | None:
    clean_fields: list[tuple[str, str]] = []
    for key, value in fields:
        clean_key = _divian_ai_normalize_text(key)
        clean_value = _divian_ai_normalize_text(value)
        if clean_key and clean_value:
            clean_fields.append((clean_key, clean_value))

    if not clean_fields:
        return None

    text = "\n".join(f"{key}: {value}" for key, value in clean_fields)
    normalized = _divian_ai_fold_text(text)
    tokens = _divian_ai_tokens(text)
    if not tokens:
        return None

    return DivianAIRecord(
        label=label,
        source_name=source_name,
        row_number=row_number,
        fields=tuple(clean_fields),
        text=text,
        normalized=normalized,
        tokens=tokens,
    )


def _divian_ai_looks_like_header_row(values: list[str]) -> bool:
    if len(values) < 2:
        return False

    meaningful_values = [value for value in values if value]
    if len(meaningful_values) < 2:
        return False

    unique_ratio = len({value.lower() for value in meaningful_values}) / max(1, len(meaningful_values))
    numeric_ratio = sum(bool(re.search(r"\d", value)) for value in meaningful_values) / len(meaningful_values)
    average_length = sum(len(value) for value in meaningful_values) / len(meaningful_values)

    return unique_ratio >= 0.8 and numeric_ratio <= 0.35 and average_length <= 30


def _divian_ai_extract_table_records(
    rows: list[list[str]],
    source_name: str,
    section_label: str,
) -> list[DivianAIRecord]:
    clean_rows = [[_divian_ai_normalize_text(value) for value in row if _divian_ai_normalize_text(value)] for row in rows]
    clean_rows = [row for row in clean_rows if row]
    if not clean_rows:
        return []

    header_row = clean_rows[0] if _divian_ai_looks_like_header_row(clean_rows[0]) else []
    data_rows = clean_rows[1:] if header_row else clean_rows
    records: list[DivianAIRecord] = []

    for row_index, row in enumerate(data_rows, start=2 if header_row else 1):
        if header_row:
            fields = [
                (header_row[column_index], value)
                for column_index, value in enumerate(row)
                if column_index < len(header_row) and value
            ]
        else:
            fields = [(f"Oszlop {column_index + 1}", value) for column_index, value in enumerate(row) if value]

        record = _divian_ai_build_record(
            label=f"{source_name} · {section_label} · {row_index}. sor",
            source_name=source_name,
            row_number=row_index,
            fields=fields,
        )
        if record is not None:
            records.append(record)

    return records


def _divian_ai_extract_key_value_records(
    raw_text: str,
    source_name: str,
    section_label: str,
) -> list[DivianAIRecord]:
    blocks = re.split(r"\n\s*\n", raw_text)
    records: list[DivianAIRecord] = []
    record_index = 0

    for block in blocks:
        lines = [line.strip(" -\t") for line in block.splitlines() if line.strip()]
        fields: list[tuple[str, str]] = []
        for line in lines:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            if key.strip() and value.strip():
                fields.append((key, value))

        if len(fields) >= 2:
            record_index += 1
            record = _divian_ai_build_record(
                label=f"{source_name} · {section_label} · blokk {record_index}",
                source_name=source_name,
                row_number=record_index,
                fields=fields,
            )
            if record is not None:
                records.append(record)

    if records:
        return records

    consecutive_fields: list[tuple[str, str]] = []
    record_index = 0
    for raw_line in raw_text.splitlines():
        line = raw_line.strip(" -\t")
        if not line:
            if len(consecutive_fields) >= 2:
                record_index += 1
                record = _divian_ai_build_record(
                    label=f"{source_name} · {section_label} · blokk {record_index}",
                    source_name=source_name,
                    row_number=record_index,
                    fields=consecutive_fields,
                )
                if record is not None:
                    records.append(record)
            consecutive_fields = []
            continue

        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        if key.strip() and value.strip():
            consecutive_fields.append((key, value))

    if len(consecutive_fields) >= 2:
        record_index += 1
        record = _divian_ai_build_record(
            label=f"{source_name} · {section_label} · blokk {record_index}",
            source_name=source_name,
            row_number=record_index,
            fields=consecutive_fields,
        )
        if record is not None:
            records.append(record)

    return records


def _divian_ai_is_elemjegyzek_source(source_name: str) -> bool:
    return "elemjegyz" in _divian_ai_fold_text(source_name)


def _divian_ai_elemjegyzek_section(page_number: int, page_title: str, raw_page_text: str) -> str:
    title_context = _divian_ai_fold_text(page_title)
    lead_context = _divian_ai_fold_text(raw_page_text[:400])
    full_context = _divian_ai_fold_text(f"{page_title}\n{raw_page_text[:1500]}")
    if "blokk konyhakhoz rendelheto elemek" in full_context:
        return "Blokk konyhákhoz rendelhető elemek"
    if "oldaltakaro" in title_context or "oldaltakaro" in lead_context:
        return "Oldaltakarók"
    if "fogantyu" in title_context or "fogantyu" in lead_context:
        return "Fogantyúk"
    if "falipanel" in title_context or title_context.startswith("kiegeszitok falipanel"):
        return "Falipanelek"
    if "munkalap" in title_context or title_context.startswith("28-as munkalapok") or title_context.startswith("38-as 900 mely munkalapok"):
        return "Munkalapok"
    if "konyhasziget" in title_context or "konyhasziget" in lead_context:
        return "Konyhasziget elemek"
    if "kiegeszit" in title_context or "kiegeszit" in lead_context:
        return "Kiegészítők"
    if 2 <= page_number <= 6:
        return "Alsó elemek"
    if 7 <= page_number <= 11:
        return "Felső elemek"
    return "Elemjegyzék"


def _divian_ai_elemjegyzek_scope(page_number: int, raw_page_text: str, section_label: str) -> tuple[str, str]:
    context = _divian_ai_fold_text(f"{section_label}\n{raw_page_text[:1500]}")
    if "kinga" in context and "kata" in context and "kira" in context and "blokk" in context:
        return "Blokk konyhák", "Kinga, Kata, Kira"
    if 2 <= page_number <= 11:
        return "Elemes konyhák", ""
    return "", ""


def _divian_ai_clean_elemjegyzek_description(raw_description: str, code: str) -> tuple[str, str]:
    description = _divian_ai_normalize_text(raw_description)
    if not description:
        return f"Nem egyértelmű megnevezés ({code})", ""

    description = re.sub(r"^\d+\s+(?=\S)", "", description).strip(" ,-:;")
    if len(description) > 90 and "!" in description:
        description = description.split("!")[-1].strip()

    markers = (
        "BLOKK KONYHÁKHOZ RENDELHETŐ ELEMEK",
        "RENDELHETŐ ELEMEK",
        "ALSÓ ELEMEK",
        "FELSŐ ELEMEK",
        "KONYHASZIGET ELEMEK",
        "KIEGÉSZÍTŐK",
    )
    upper_description = description.upper()
    for marker in markers:
        marker_position = upper_description.rfind(marker)
        if marker_position != -1:
            description = description[marker_position + len(marker) :].strip(" ,-:;")
            upper_description = description.upper()

    note = ""
    note_match = re.search(r"\b(Csak [^!?.]+[!?]?|Tartalmazza [^.]+)$", description, flags=re.IGNORECASE)
    if note_match:
        note = _divian_ai_normalize_text(note_match.group(1))
        description = _divian_ai_normalize_text(description[: note_match.start()]).strip(" ,-:;")

    if not description:
        description = f"Nem egyértelmű megnevezés ({code})"
    return description, note


def _divian_ai_extract_elemjegyzek_dimension_records(
    raw_page_text: str,
    source_name: str,
    page_number: int,
    section_label: str,
    kitchen_group: str,
    kitchens_label: str,
) -> list[DivianAIRecord]:
    code_dimension_pattern = re.compile(
        r"(?P<code>[A-ZÁÉÍÓÖŐÚÜŰ]{1,8}[A-ZÁÉÍÓÖŐÚÜŰ0-9_x]{1,})\s+"
        r"(?P<dims>\d{1,4}(?:,\d+)?\s*x\s*\d{1,4}(?:,\d+)?(?:\s*x\s*\d{1,4}(?:,\d+)?)?)"
    )
    records: list[DivianAIRecord] = []
    last_end = 0
    row_number = 0
    matches = list(code_dimension_pattern.finditer(raw_page_text))
    for match in matches:
        code = _divian_ai_normalize_text(match.group("code"))
        dimensions = _divian_ai_normalize_text(match.group("dims"))
        description, note = _divian_ai_clean_elemjegyzek_description(raw_page_text[last_end : match.start()], code)
        last_end = match.end()

        if not code or not dimensions:
            continue

        dimension_parts = [part.strip() for part in re.split(r"\s*x\s*", dimensions) if part.strip()]
        fields: list[tuple[str, str]] = [
            ("Megnevezés", description),
            ("Kód", code),
            ("Méretek", dimensions),
            ("Elemcsoport", section_label),
        ]
        for dimension_index, part in enumerate(dimension_parts, start=1):
            fields.append((f"Méret {dimension_index}", part))
        if kitchen_group:
            fields.append(("Konyhacsoport", kitchen_group))
        if kitchens_label:
            fields.append(("Konyhák", kitchens_label))
        if note:
            fields.append(("Megjegyzés", note))

        row_number += 1
        record = _divian_ai_build_record(
            label=f"{source_name} · {page_number}. oldal · elem {row_number}",
            source_name=source_name,
            row_number=row_number,
            fields=fields,
        )
        if record is not None:
            records.append(record)
    return records


def _divian_ai_extract_elemjegyzek_code_only_records(
    raw_page_text: str,
    source_name: str,
    page_number: int,
    section_label: str,
    kitchen_group: str,
    kitchens_label: str,
) -> list[DivianAIRecord]:
    if "blokk konyhakhoz rendelheto elemek" not in _divian_ai_fold_text(raw_page_text):
        return []

    working_text = raw_page_text
    anchor_match = re.search(r"ELEMEK", working_text, flags=re.IGNORECASE)
    if anchor_match:
        working_text = working_text[anchor_match.end() :]

    price_match = re.search(r"\d{1,3}(?:\.\d{3})?\s*Ft", working_text, flags=re.IGNORECASE)
    if price_match:
        working_text = working_text[: price_match.start()]

    code_pattern = re.compile(r"(?P<code>[A-ZÁÉÍÓÖŐÚÜŰ]{1,8}[A-ZÁÉÍÓÖŐÚÜŰ0-9_x]{1,})")
    records: list[DivianAIRecord] = []
    last_end = 0
    row_number = 0
    for match in code_pattern.finditer(working_text):
        code = _divian_ai_normalize_text(match.group("code"))
        description, note = _divian_ai_clean_elemjegyzek_description(working_text[last_end : match.start()], code)
        last_end = match.end()
        if not code:
            continue

        row_number += 1
        fields: list[tuple[str, str]] = [
            ("Megnevezés", description),
            ("Kód", code),
            ("Elemcsoport", section_label),
        ]
        if kitchen_group:
            fields.append(("Konyhacsoport", kitchen_group))
        if kitchens_label:
            fields.append(("Konyhák", kitchens_label))
        if note:
            fields.append(("Megjegyzés", note))

        record = _divian_ai_build_record(
            label=f"{source_name} · {page_number}. oldal · elem {row_number}",
            source_name=source_name,
            row_number=row_number,
            fields=fields,
        )
        if record is not None:
            records.append(record)
    return records


def _divian_ai_extract_elemjegyzek_records(
    raw_page_text: str,
    source_name: str,
    page_number: int,
    page_title: str,
) -> list[DivianAIRecord]:
    if not _divian_ai_is_elemjegyzek_source(source_name):
        return []

    section_label = _divian_ai_elemjegyzek_section(page_number, page_title, raw_page_text)
    kitchen_group, kitchens_label = _divian_ai_elemjegyzek_scope(page_number, raw_page_text, section_label)
    records = _divian_ai_extract_elemjegyzek_dimension_records(
        raw_page_text,
        source_name,
        page_number,
        section_label,
        kitchen_group,
        kitchens_label,
    )
    if records:
        return records
    return _divian_ai_extract_elemjegyzek_code_only_records(
        raw_page_text,
        source_name,
        page_number,
        section_label,
        kitchen_group,
        kitchens_label,
    )


def _divian_ai_catalog_lines(raw_text: str) -> list[str]:
    fixed_text = (
        raw_text.replace("õ", "ő")
        .replace("û", "ű")
        .replace("Õ", "Ő")
        .replace("Û", "Ű")
    )
    fixed_text = re.sub(r"([a-záéíóöőúüű])([A-ZÁÉÍÓÖŐÚÜŰ])", r"\1 \2", fixed_text)
    lines = [_clean_spaces(line) for line in fixed_text.splitlines()]
    return [
        line
        for line in lines
        if line
        and not re.fullmatch(r"\d+", line)
        and "copyright" not in _divian_ai_fold_text(line)
    ]


def _divian_ai_catalog_subject_label(page_title: str, raw_page_text: str) -> str:
    context = f"{page_title}\n{raw_page_text[:2000]}"
    product_keys = _divian_ai_detect_product_keys(context)
    if product_keys:
        return _divian_ai_product_label(product_keys[0]) or product_keys[0].capitalize()

    folded_context = _divian_ai_fold_text(context)
    if "munkalapok es falipanelek" in folded_context:
        return "Munkalapok és falipanelek"
    if "blokk konyhak" in folded_context:
        return "Blokk konyhák"
    if "inspiraciok" in folded_context:
        return "Inspirációk"
    if "fogantyu" in folded_context and "munkalap" in folded_context:
        return "Konyhai kiegészítők"
    clean_title = _clean_spaces(page_title)
    return clean_title if clean_title else "Divian katalógus"


def _divian_ai_catalog_kind(subject_label: str, raw_page_text: str) -> str:
    folded_subject = _divian_ai_fold_text(subject_label)
    folded_text = _divian_ai_fold_text(raw_page_text[:2000])
    if subject_label == "Munkalapok és falipanelek":
        return "Anyagválaszték"
    if any(name in folded_subject for name in ("kata", "kira", "kinga", "klio")) or "blokk konyha" in folded_text:
        return "Blokk konyha"
    if any(name in folded_subject for name in ("doroti", "antonia", "laura", "zille", "anna")):
        return "Elemes konyha"
    return "Katalógus oldal"


def _divian_ai_catalog_color_values(raw_page_text: str) -> list[str]:
    folded_text = _divian_ai_fold_text(raw_page_text)
    colors: list[str] = []
    seen_colors: set[str] = set()
    for color in DIVIAN_AI_COLOR_PHRASES:
        folded_color = _divian_ai_fold_text(color)
        if folded_color in folded_text and folded_color not in seen_colors:
            seen_colors.add(folded_color)
            colors.append(color)
    return colors


def _divian_ai_catalog_short_values(lines: list[str], *, max_length: int = 42, max_words: int = 6) -> list[str]:
    values: list[str] = []
    seen_values: set[str] = set()
    for line in lines:
        folded_line = _divian_ai_fold_text(line)
        if not line or len(line) > max_length:
            continue
        if len(line.split()) > max_words:
            continue
        if any(token in folded_line for token in ("ft", "garancia", "kedvezmeny", "regisztracio", "oldal tipus", "partner szekcio")):
            continue
        if re.search(r"\d{2,4}\s*x\s*\d{2,4}", line):
            continue
        if _divian_ai_is_code_like(line):
            continue
        if folded_line in seen_values:
            continue
        seen_values.add(folded_line)
        values.append(line)
    return values


def _divian_ai_catalog_feature_values(lines: list[str]) -> list[str]:
    features = _divian_ai_catalog_short_values(lines, max_length=48, max_words=7)
    return [value for value in features if len(value) >= 6][:12]


def _divian_ai_catalog_inline_material_values(raw_page_text: str, material_label: str) -> list[str]:
    fixed_text = (
        raw_page_text.replace("õ", "ő")
        .replace("û", "ű")
        .replace("Õ", "Ő")
        .replace("Û", "Ű")
    )
    fixed_text = re.sub(r"([a-záéíóöőúüű])([A-ZÁÉÍÓÖŐÚÜŰ])", r"\1 \2", fixed_text)
    flat_text = re.sub(r"\s+", " ", fixed_text)
    pattern = re.compile(
        rf"([A-ZÁÉÍÓÖŐÚÜŰa-záéíóöőúüű][A-ZÁÉÍÓÖŐÚÜŰa-záéíóöőúüű0-9\-/ ]{{2,42}}?)\s+{re.escape(material_label)}\*?",
        flags=re.IGNORECASE,
    )
    values: list[str] = []
    seen: set[str] = set()
    for match in pattern.finditer(flat_text):
        value = _clean_spaces(match.group(1)).strip(" -*,")
        folded_value = _divian_ai_fold_text(value)
        if not value or folded_value in seen:
            continue
        if any(term in folded_value for term in ("28-as", "38-as", "minden", "feltuntetett", "tovabbi", "vizzaro", "konyhasziget")):
            continue
        if len(value) > 32 or re.search(r"\d", value):
            continue
        seen.add(folded_value)
        values.append(value)
    return values


def _divian_ai_catalog_page_color_values(
    raw_page_text: str,
    *,
    start_markers: tuple[str, ...] = (),
    end_markers: tuple[str, ...] = (),
    excluded: tuple[str, ...] = (),
) -> list[str]:
    fixed_text = (
        raw_page_text.replace("õ", "ő")
        .replace("û", "ű")
        .replace("Õ", "Ő")
        .replace("Û", "Ű")
    )
    fixed_text = re.sub(r"([a-záéíóöőúüű])([A-ZÁÉÍÓÖŐÚÜŰ])", r"\1 \2", fixed_text)
    lines = [_clean_spaces(line) for line in fixed_text.splitlines() if _clean_spaces(line)]
    folded_lines = [_divian_ai_fold_text(line) for line in lines]

    start_index = 0
    if start_markers:
        for index, folded_line in enumerate(folded_lines):
            if any(marker in folded_line for marker in start_markers):
                start_index = index
                break
        else:
            return []

    collected: list[str] = []
    excluded_folded = {_divian_ai_fold_text(value) for value in excluded}
    for line, folded_line in zip(lines[start_index:], folded_lines[start_index:]):
        if end_markers and any(marker in folded_line for marker in end_markers):
            break
        collected.append(line)

    block_text = " ".join(collected)
    values: list[str] = []
    seen: set[str] = set()
    for color in DIVIAN_AI_COLOR_PHRASES:
        folded_color = _divian_ai_fold_text(color)
        if folded_color in excluded_folded or folded_color in seen:
            continue
        if folded_color in _divian_ai_fold_text(block_text):
            seen.add(folded_color)
            values.append(color)
    return values


def _divian_ai_catalog_surface_colors(
    knowledge: DivianAIKnowledgeCache,
    subject_key: str,
) -> tuple[list[str], list[str]]:
    colors: list[str] = []
    sources: list[str] = []
    seen_colors: set[str] = set()
    seen_sources: set[str] = set()

    preferred_sources = set(_divian_ai_preferred_structured_sources(knowledge, source_type="catalog", limit=3))
    for page in knowledge.pages:
        if page.source_name not in preferred_sources:
            continue
        page_folded = page.folded
        page_colors: list[str] = []
        if subject_key == "munkalap":
            if not any(
                marker in page_folded
                for marker in ("28-as munkalapok", "38-as munkalapok", "munkalapok es falipanelek")
            ):
                continue
            page_colors = _divian_ai_catalog_inline_material_values(page.text, "munkalap")
        elif subject_key == "falipanel":
            if not any(marker in page_folded for marker in ("falipanel szinek", "munkalapok es falipanelek")):
                continue
            page_colors = _divian_ai_catalog_page_color_values(
                page.text,
                start_markers=("falipanel szinek", "munkalapok es falipanelek"),
                excluded=("Króm", "Matt fekete", "Arany", "Rose gold"),
            )
            if not page_colors:
                page_colors = _divian_ai_catalog_page_color_values(
                    page.text,
                    start_markers=("38-as munkalapok es vizzarok",),
                    excluded=("Króm", "Matt fekete", "Arany", "Rose gold"),
                )
        else:
            continue

        for color in page_colors:
            folded_color = _divian_ai_fold_text(color)
            if not folded_color or folded_color in seen_colors:
                continue
            seen_colors.add(folded_color)
            colors.append(color)

        if page_colors and page.label not in seen_sources:
            seen_sources.add(page.label)
            sources.append(page.label)

    return colors, sources


def _divian_ai_catalog_summary(lines: list[str], subject_label: str) -> str:
    summary_parts: list[str] = []
    folded_subject = _divian_ai_fold_text(subject_label)
    for line in lines:
        folded_line = _divian_ai_fold_text(line)
        if folded_subject and folded_subject in folded_line:
            continue
        if len(line) < 40 or len(line.split()) < 7:
            continue
        if any(term in folded_line for term in ("az akcioban", "idotartama", "regisztraciohoz", "garancia van ra", "copyright")):
            continue
        if "ft" in folded_line:
            continue
        summary_parts.append(line)
        if len(" ".join(summary_parts)) >= 420 or len(summary_parts) >= 3:
            break
    return " ".join(summary_parts).strip()


def _divian_ai_catalog_extract_records(
    page_data: DivianAIPage,
    raw_page_text: str,
    source_name: str,
    page_number: int,
) -> list[DivianAIRecord]:
    if not _divian_ai_source_is_catalog(source_name):
        return []

    detected_product_keys = list(dict.fromkeys(_divian_ai_detect_product_keys(f"{page_data.title}\n{raw_page_text[:2000]}")))
    folded_text = _divian_ai_fold_text(raw_page_text)
    if len(detected_product_keys) >= 3 and not any(
        marker in folded_text
        for marker in (
            "front szinek",
            "munkalap",
            "falipanel",
            "garancia",
            "blokk konyha",
            "fogantyu",
            "elony",
            "előny",
            "front es korpusz",
        )
    ):
        return []

    subject_label = _divian_ai_catalog_subject_label(page_data.title, raw_page_text)
    kind_label = _divian_ai_catalog_kind(subject_label, raw_page_text)
    lines = _divian_ai_catalog_lines(raw_page_text)
    summary = _divian_ai_catalog_summary(lines, subject_label)
    colors = _divian_ai_catalog_color_values(raw_page_text)
    features = _divian_ai_catalog_feature_values(lines)

    front_materials: list[str] = []
    if "mdf folias" in folded_text:
        front_materials.append("MDF fóliás")
    if "butorlap" in folded_text:
        front_materials.append("Bútorlap")

    price_matches = re.findall(r"\d[\d.\s]*\s*Ft(?:-tól)?", raw_page_text, flags=re.IGNORECASE)
    prices = [_clean_spaces(price) for price in price_matches]
    unique_prices: list[str] = []
    seen_prices: set[str] = set()
    for price in prices:
        folded_price = _divian_ai_fold_text(price)
        if folded_price in seen_prices:
            continue
        seen_prices.add(folded_price)
        unique_prices.append(price)

    size_matches = re.findall(r"\b\d+\s*cm(?:-es)?(?:\s*vagy\s*\d+\s*cm)?(?:,\s*\d+\s*cm)?", raw_page_text, flags=re.IGNORECASE)
    sizes = []
    seen_sizes: set[str] = set()
    for size in size_matches:
        clean_size = _clean_spaces(size)
        folded_size = _divian_ai_fold_text(clean_size)
        if folded_size in seen_sizes:
            continue
        seen_sizes.add(folded_size)
        sizes.append(clean_size)

    warranty_matches = re.findall(r"(?:Akár\s*)?\d+\s*(?:\+\s*\d+\s*)?év\*?", raw_page_text, flags=re.IGNORECASE)
    warranties = []
    seen_warranties: set[str] = set()
    for warranty in warranty_matches:
        clean_warranty = _clean_spaces(warranty)
        folded_warranty = _divian_ai_fold_text(clean_warranty)
        if folded_warranty in seen_warranties:
            continue
        seen_warranties.add(folded_warranty)
        warranties.append(clean_warranty)

    fields: list[tuple[str, str]] = [
        ("Megnevezés", subject_label),
        ("Típus", kind_label),
    ]
    if summary:
        fields.append(("Leírás", summary))
    if front_materials:
        fields.append(("Front anyag", ", ".join(front_materials)))
    if colors:
        fields.append(("Színek", ", ".join(colors[:18])))
    worktop_colors = _divian_ai_catalog_inline_material_values(raw_page_text, "munkalap")
    if worktop_colors:
        fields.append(("Munkalap színek", ", ".join(worktop_colors[:24])))
    if "falipanel" in folded_text:
        panel_colors = _divian_ai_catalog_page_color_values(
            raw_page_text,
            start_markers=("falipanel szinek",),
            excluded=("Króm", "Matt fekete", "Arany", "Rose gold"),
        )
        if panel_colors:
            fields.append(("Falipanel színek", ", ".join(panel_colors[:24])))
    if features:
        fields.append(("Jellemzők", ", ".join(features[:12])))
    if unique_prices:
        fields.append(("Ár", ", ".join(unique_prices[:4])))
    if sizes:
        fields.append(("Méret", ", ".join(sizes[:6])))
    if warranties:
        fields.append(("Garancia", ", ".join(warranties[:4])))

    records: list[DivianAIRecord] = []
    summary_record = _divian_ai_build_record(
        label=f"{source_name} · {page_number}. oldal · összefoglaló",
        source_name=source_name,
        row_number=page_number * 1000 + 1,
        fields=fields,
    )
    if summary_record is not None:
        records.append(summary_record)

    for item_index, color in enumerate(colors[:24], start=1):
        color_record = _divian_ai_build_record(
            label=f"{source_name} · {page_number}. oldal · szín {item_index}",
            source_name=source_name,
            row_number=page_number * 1000 + 20 + item_index,
            fields=[
                ("Megnevezés", color),
                ("Típus", "Szín"),
                ("Kapcsolódó modell", subject_label),
            ],
        )
        if color_record is not None:
            records.append(color_record)

    for item_index, feature in enumerate(features[:16], start=1):
        feature_record = _divian_ai_build_record(
            label=f"{source_name} · {page_number}. oldal · jellemző {item_index}",
            source_name=source_name,
            row_number=page_number * 1000 + 100 + item_index,
            fields=[
                ("Megnevezés", feature),
                ("Típus", "Jellemző"),
                ("Kapcsolódó modell", subject_label),
            ],
        )
        if feature_record is not None:
            records.append(feature_record)

    return records


def _divian_ai_partner_category_key_from_text(*values: str) -> str:
    combined = " ".join(value for value in values if value)
    folded_text = _divian_ai_fold_text(combined)
    for category_key, aliases in DIVIAN_AI_PARTNER_CATEGORY_ALIASES.items():
        if any(_divian_ai_fold_text(alias) in folded_text for alias in aliases):
            return category_key
    return ""


def _divian_ai_partner_category_label(category_key: str) -> str:
    return {
        "szek": "Szék",
        "asztal": "Asztal",
        "garnitura": "Étkezőgarnitúra",
        "konyhagep": "Konyhagép",
        "kisgep": "Konyhai kisgép",
        "mosogatotalca": "Mosogatótálca",
        "csaptelep": "Csaptelep",
        "vasalat": "Vasalat",
        "kiegeszito": "Kiegészítő",
        "vilagitas": "Világítás",
        "blokk_konyha": "Blokk konyha",
    }.get(category_key, category_key.replace("_", " ").strip().title())


def _divian_ai_extract_public_web_records(
    raw_text: str,
    source_name: str,
    source_path: Path,
) -> list[DivianAIRecord]:
    entry = _divian_ai_public_web_entry(source_path)
    if entry is None:
        return []

    page_type = str(entry.get("page_type", "")).strip() or "info"
    source_url = str(entry.get("url", "")).strip()
    category_key = _divian_ai_partner_category_key_from_text(source_name, raw_text, source_url)
    category_label = _divian_ai_partner_category_label(category_key) if category_key else ""

    key_value_lines: list[tuple[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for raw_line in raw_text.splitlines():
        line = _clean_spaces(raw_line)
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        clean_key = _clean_spaces(key)
        clean_value = _clean_spaces(value)
        if not clean_key or not clean_value:
            continue
        folded_key = _divian_ai_fold_text(clean_key)
        if folded_key in {"forras url", "frissitve", "oldal cime", "web extract version"}:
            continue
        pair = (clean_key, clean_value)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        key_value_lines.append(pair)

    name_value = ""
    for key, value in key_value_lines:
        if _divian_ai_fold_text(key) in {"termek neve", "megnevezes"}:
            name_value = value
            break
    if not name_value:
        name_value = _clean_spaces(str(entry.get("name", "")).strip() or source_name)

    base_fields: list[tuple[str, str]] = [
        ("Megnevezés", name_value),
        ("Oldal típus", page_type),
    ]
    if category_label:
        base_fields.append(("Kategória", category_label))
    for key, value in key_value_lines[:14]:
        if (key, value) not in base_fields:
            base_fields.append((key, value))

    records: list[DivianAIRecord] = []
    main_record = _divian_ai_build_record(
        label=f"{source_name} · web összefoglaló",
        source_name=source_name,
        row_number=1,
        fields=base_fields,
    )
    if main_record is not None:
        records.append(main_record)

    item_patterns = (
        ("Akciós termék", "Akció"),
        ("Új termék", "Új termék"),
        ("Termék", "Partner termék"),
    )
    item_index = 0
    for key, item_type in item_patterns:
        regex = re.compile(rf"^{re.escape(key)}\s*:\s*(.+)$", re.IGNORECASE)
        for raw_line in raw_text.splitlines():
            line = _clean_spaces(raw_line)
            match = regex.match(line)
            if not match:
                continue
            item_name = _clean_spaces(match.group(1))
            if not item_name:
                continue
            item_index += 1
            item_fields = [("Megnevezés", item_name), ("Típus", item_type)]
            if category_label:
                item_fields.append(("Kategória", category_label))
            item_record = _divian_ai_build_record(
                label=f"{source_name} · web tétel {item_index}",
                source_name=source_name,
                row_number=50 + item_index,
                fields=item_fields,
            )
            if item_record is not None:
                records.append(item_record)

    return records


def _divian_ai_chunk_text(label: str, source_name: str, page_number: int, text: str) -> list[DivianAIChunk]:
    clean_text = _divian_ai_normalize_text(text)
    if not clean_text:
        return []

    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    if not paragraphs:
        paragraphs = [line.strip() for line in text.splitlines() if line.strip()]
    if not paragraphs:
        paragraphs = [clean_text]

    chunks: list[str] = []
    current_parts: list[str] = []
    current_length = 0

    for paragraph in paragraphs:
        if len(paragraph) > DIVIAN_AI_CHUNK_CHARS:
            if current_parts:
                chunks.append("\n\n".join(current_parts).strip())
                current_parts = []
                current_length = 0

            step = max(1, DIVIAN_AI_CHUNK_CHARS - DIVIAN_AI_CHUNK_OVERLAP)
            for start in range(0, len(paragraph), step):
                piece = paragraph[start : start + DIVIAN_AI_CHUNK_CHARS].strip()
                if piece:
                    chunks.append(piece)
            continue

        projected_length = current_length + len(paragraph) + (2 if current_parts else 0)
        if projected_length > DIVIAN_AI_CHUNK_CHARS and current_parts:
            chunks.append("\n\n".join(current_parts).strip())
            current_parts = [paragraph]
            current_length = len(paragraph)
            continue

        current_parts.append(paragraph)
        current_length = projected_length

    if current_parts:
        chunks.append("\n\n".join(current_parts).strip())

    results: list[DivianAIChunk] = []
    for chunk in chunks:
        normalized = _divian_ai_normalize_text(chunk)
        if len(normalized) < 20:
            continue
        results.append(
            DivianAIChunk(
                label=label,
                source_name=source_name,
                page_number=page_number,
                text=normalized,
                normalized=_divian_ai_fold_text(normalized),
                tokens=_divian_ai_tokens(normalized),
            )
        )
    return results


def _divian_ai_build_page(label: str, source_name: str, page_number: int, title: str, raw_text: str) -> DivianAIPage | None:
    page_text = _divian_ai_normalize_text(raw_text)
    if not page_text:
        return None

    page_text_lines = (
        raw_text.replace("õ", "ő")
        .replace("û", "ű")
        .replace("Õ", "Ő")
        .replace("Û", "Ű")
    )
    page_text_lines = re.sub(r"([a-záéíóöőúüű])([A-ZÁÉÍÓÖŐÚÜŰ])", r"\1\n\2", page_text_lines)
    page_lines = [re.sub(r"\s+", " ", line).strip() for line in page_text_lines.splitlines() if line.strip()]
    page_title = title.strip() if title.strip() else (page_lines[0] if page_lines else label)
    return DivianAIPage(
        label=label,
        source_name=source_name,
        page_number=page_number,
        title=page_title,
        text=page_text,
        normalized=page_text.lower(),
        folded=_divian_ai_fold_text(page_text),
        lines=tuple(page_lines),
    )


def _divian_ai_read_text_file(source_path: Path) -> str:
    raw_bytes = source_path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1250", "latin1"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="ignore")


def _divian_ai_flatten_json(value, prefix: str = "") -> list[str]:
    lines: list[str] = []
    if isinstance(value, dict):
        for key, nested_value in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            lines.extend(_divian_ai_flatten_json(nested_value, next_prefix))
        return lines

    if isinstance(value, list):
        for index, nested_value in enumerate(value, start=1):
            next_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
            lines.extend(_divian_ai_flatten_json(nested_value, next_prefix))
        return lines

    clean_value = _divian_ai_normalize_text(str(value))
    if clean_value:
        if prefix:
            lines.append(f"{prefix}: {clean_value}")
        else:
            lines.append(clean_value)
    return lines


def _divian_ai_extract_pdf_source(source_path: Path, source_name: str) -> DivianAISourceExtractResult:
    if PdfReader is None:
        return DivianAISourceExtractResult(source_name=source_name, error="A PDF források olvasásához a pypdf csomag szükséges.")

    try:
        reader = PdfReader(str(source_path))
    except Exception as exc:
        return DivianAISourceExtractResult(source_name=source_name, error=f"Nem sikerült megnyitni: {source_name} ({exc})")

    result = DivianAISourceExtractResult(source_name=source_name)
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            raw_page_text = page.extract_text() or ""
        except Exception:
            raw_page_text = ""

        label = f"{source_name} · {page_number}. oldal"
        page_title = next(
            (
                line
                for line in re.split(r"[\r\n]+", raw_page_text)
                if "KONYHA" in line.upper() or "MUNKALAPOK" in line.upper() or "OLDALTAKARÓK" in line.upper()
            ),
            label,
        )
        page_data = _divian_ai_build_page(label, source_name, page_number, page_title, raw_page_text)
        if page_data is None:
            continue

        result.pages.append(page_data)
        result.chunks.extend(_divian_ai_chunk_text(label, source_name, page_number, raw_page_text))
        elemjegyzek_records = _divian_ai_extract_elemjegyzek_records(raw_page_text, source_name, page_number, page_title)
        if elemjegyzek_records:
            result.records.extend(elemjegyzek_records)
        catalog_records = _divian_ai_catalog_extract_records(page_data, raw_page_text, source_name, page_number)
        if catalog_records:
            result.records.extend(catalog_records)
        result.records.extend(_divian_ai_extract_key_value_records(raw_page_text, source_name, f"{page_number}. oldal"))

    if not result.pages and not result.error:
        result.error = f"A PDF-ből nem sikerült olvasható szöveget kinyerni: {source_name}"
    return result


def _divian_ai_extract_text_source(source_path: Path, source_name: str) -> DivianAISourceExtractResult:
    try:
        raw_text = _divian_ai_read_text_file(source_path)
    except Exception as exc:
        return DivianAISourceExtractResult(source_name=source_name, error=f"Nem sikerült beolvasni: {source_name} ({exc})")

    if source_path.suffix.lower() == ".json":
        try:
            flattened = _divian_ai_flatten_json(json.loads(raw_text))
            raw_text = "\n".join(flattened)
        except Exception:
            pass

    label = f"{source_name} · szöveg"
    page_data = _divian_ai_build_page(label, source_name, 1, source_name, raw_text)
    if page_data is None:
        return DivianAISourceExtractResult(source_name=source_name, error=f"A fájl üres vagy nem olvasható: {source_name}")

    records = _divian_ai_extract_key_value_records(raw_text, source_name, "szöveg")
    public_web_records = _divian_ai_extract_public_web_records(raw_text, source_name, source_path)
    if public_web_records:
        records.extend(public_web_records)

    return DivianAISourceExtractResult(
        source_name=source_name,
        pages=[page_data],
        chunks=_divian_ai_chunk_text(label, source_name, 1, raw_text),
        records=records,
    )


def _divian_ai_extract_csv_source(source_path: Path, source_name: str) -> DivianAISourceExtractResult:
    try:
        raw_text = _divian_ai_read_text_file(source_path)
    except Exception as exc:
        return DivianAISourceExtractResult(source_name=source_name, error=f"Nem sikerült beolvasni: {source_name} ({exc})")

    sample = raw_text[:2000]
    delimiter = ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,|\t,")
        delimiter = dialect.delimiter
    except Exception:
        if ";" in sample:
            delimiter = ";"

    reader = csv.reader(io.StringIO(raw_text), delimiter=delimiter)
    lines: list[str] = []
    row_values: list[list[str]] = []
    for row_index, row in enumerate(reader, start=1):
        if row_index > DIVIAN_AI_MAX_TABLE_ROWS:
            break
        values = [_divian_ai_normalize_text(str(value)) for value in row if _divian_ai_normalize_text(str(value))]
        if values:
            lines.append(" | ".join(values))
            row_values.append(values)

    joined_text = "\n".join(lines)
    label = f"{source_name} · táblázat"
    page_data = _divian_ai_build_page(label, source_name, 1, f"{source_name} táblázat", joined_text)
    if page_data is None:
        return DivianAISourceExtractResult(source_name=source_name, error=f"A CSV-ből nem sikerült használható sort kinyerni: {source_name}")

    return DivianAISourceExtractResult(
        source_name=source_name,
        pages=[page_data],
        chunks=_divian_ai_chunk_text(label, source_name, 1, joined_text),
        records=_divian_ai_extract_table_records(row_values, source_name, "táblázat"),
    )


def _divian_ai_extract_workbook_source(source_path: Path, source_name: str) -> DivianAISourceExtractResult:
    if load_workbook is None:
        return DivianAISourceExtractResult(source_name=source_name, error="Az Excel fájlok olvasásához az openpyxl csomag szükséges.")

    try:
        workbook = load_workbook(filename=str(source_path), read_only=True, data_only=True)
    except Exception as exc:
        return DivianAISourceExtractResult(source_name=source_name, error=f"Nem sikerült megnyitni: {source_name} ({exc})")

    result = DivianAISourceExtractResult(source_name=source_name)
    for page_number, sheet_name in enumerate(workbook.sheetnames, start=1):
        worksheet = workbook[sheet_name]
        rows: list[str] = []
        row_values: list[list[str]] = []
        for row_index, row in enumerate(worksheet.iter_rows(values_only=True), start=1):
            if row_index > DIVIAN_AI_MAX_TABLE_ROWS:
                break
            values = [_divian_ai_normalize_text(str(value)) for value in row if value not in (None, "")]
            values = [value for value in values if value]
            if values:
                rows.append(" | ".join(values))
                row_values.append(values)

        joined_text = "\n".join(rows)
        label = f"{source_name} · {sheet_name}"
        page_data = _divian_ai_build_page(label, source_name, page_number, sheet_name, joined_text)
        if page_data is None:
            continue

        result.pages.append(page_data)
        result.chunks.extend(_divian_ai_chunk_text(label, source_name, page_number, joined_text))
        result.records.extend(_divian_ai_extract_table_records(row_values, source_name, sheet_name))

    try:
        workbook.close()
    except Exception:
        pass

    if not result.pages and not result.error:
        result.error = f"Az Excel fájlból nem sikerült használható adatot kinyerni: {source_name}"
    return result


def _divian_ai_extract_docx_source(source_path: Path, source_name: str) -> DivianAISourceExtractResult:
    try:
        with zipfile.ZipFile(source_path) as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
    except Exception as exc:
        return DivianAISourceExtractResult(source_name=source_name, error=f"Nem sikerült kiolvasni a DOCX-et: {source_name} ({exc})")

    document_xml = document_xml.replace("</w:p>", "\n").replace("<w:tab/>", " ")
    document_xml = re.sub(r"</w:tr>", "\n", document_xml)
    plain_text = html.unescape(re.sub(r"<[^>]+>", " ", document_xml))
    label = f"{source_name} · dokumentum"
    page_data = _divian_ai_build_page(label, source_name, 1, source_name, plain_text)
    if page_data is None:
        return DivianAISourceExtractResult(source_name=source_name, error=f"A DOCX-ből nem sikerült olvasható szöveget kinyerni: {source_name}")

    return DivianAISourceExtractResult(
        source_name=source_name,
        pages=[page_data],
        chunks=_divian_ai_chunk_text(label, source_name, 1, plain_text),
        records=_divian_ai_extract_key_value_records(plain_text, source_name, "dokumentum"),
    )


def _divian_ai_extract_image_text(source_path: Path) -> str:
    if os.name != "nt" or not DIVIAN_AI_OCR_SCRIPT.exists():
        return ""

    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(DIVIAN_AI_OCR_SCRIPT),
                "-Path",
                str(source_path),
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            encoding="utf-8",
            errors="ignore",
        )
    except Exception:
        return ""

    if completed.returncode != 0:
        return ""

    return _divian_ai_normalize_text(completed.stdout)


def _divian_ai_extract_image_source(source_path: Path, source_name: str) -> DivianAISourceExtractResult:
    ocr_text = _divian_ai_extract_image_text(source_path)
    if not ocr_text:
        return DivianAISourceExtractResult(source_name=source_name, error=f"A képből nem sikerült szöveget kiolvasni: {source_name}")

    label = f"{source_name} · OCR"
    page_data = _divian_ai_build_page(label, source_name, 1, f"{source_name} OCR", ocr_text)
    if page_data is None:
        return DivianAISourceExtractResult(source_name=source_name, error=f"A képből nem sikerült olvasható szöveget kinyerni: {source_name}")

    return DivianAISourceExtractResult(
        source_name=source_name,
        pages=[page_data],
        chunks=_divian_ai_chunk_text(label, source_name, 1, ocr_text),
        records=_divian_ai_extract_key_value_records(ocr_text, source_name, "OCR"),
    )


def _divian_ai_extract_source(source_path: Path, source_name: str | None = None) -> DivianAISourceExtractResult:
    source_name = source_name or _divian_ai_source_display_name(source_path)
    suffix = source_path.suffix.lower()
    parser_name, study_mode, confidence, note = _divian_ai_source_study_profile(source_path, source_name)

    if suffix == ".pdf":
        result = _divian_ai_extract_pdf_source(source_path, source_name)
    elif suffix in {".txt", ".md", ".json"}:
        result = _divian_ai_extract_text_source(source_path, source_name)
    elif suffix == ".csv":
        result = _divian_ai_extract_csv_source(source_path, source_name)
    elif suffix in {".xlsx", ".xlsm"}:
        result = _divian_ai_extract_workbook_source(source_path, source_name)
    elif suffix == ".docx":
        result = _divian_ai_extract_docx_source(source_path, source_name)
    elif suffix in DIVIAN_AI_IMAGE_EXTENSIONS:
        result = _divian_ai_extract_image_source(source_path, source_name)
    else:
        result = DivianAISourceExtractResult(source_name=source_name, error=f"Nem támogatott forrásformátum: {source_name}")

    result.parser_name = parser_name
    result.study_mode = study_mode
    result.confidence = confidence
    if note and not result.note:
        result.note = note
    return result


def _divian_ai_sync_knowledge_registry(source_paths: list[Path]) -> list[str]:
    manifest_map = _divian_ai_upload_display_map()
    active_keys = {_divian_ai_source_key(path) for path in source_paths}
    sync_errors: list[str] = []
    now_iso = datetime.now().isoformat(timespec="seconds")

    with _divian_ai_db_connection() as connection:
        for source_path in source_paths:
            source_key = _divian_ai_source_key(source_path)
            display_name = _divian_ai_source_display_name(source_path)
            parser_name, study_mode, confidence, profile_note = _divian_ai_source_study_profile(source_path, display_name)
            upload_entry = manifest_map.get(source_path.name)
            document_id = _divian_ai_source_entry_id(source_path, upload_entry)
            stat = source_path.stat()
            size_bytes = int(stat.st_size)
            modified_ns = int(stat.st_mtime_ns) + DIVIAN_AI_INDEXER_VERSION
            row = connection.execute(
                """
                SELECT id, source_name, modified_ns, size_bytes, status, parser_name, study_mode, confidence
                FROM knowledge_documents
                WHERE source_key = ?
                """,
                (source_key,),
            ).fetchone()
            should_reindex = (
                row is None
                or int(row["modified_ns"] or 0) != modified_ns
                or int(row["size_bytes"] or 0) != size_bytes
                or str(row["source_name"] or "") != display_name
                or not str(row["parser_name"] or "").strip()
                or not str(row["study_mode"] or "").strip()
                or not str(row["confidence"] or "").strip()
            )

            connection.execute(
                """
                INSERT INTO knowledge_documents (
                    id, source_key, source_name, path, stored_name, kind, is_uploaded, uploaded_at,
                    parser_name, study_mode, confidence, status, note, size_bytes, modified_ns, page_count, chunk_count, record_count, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_key) DO UPDATE SET
                    id = excluded.id,
                    source_name = excluded.source_name,
                    path = excluded.path,
                    stored_name = excluded.stored_name,
                    kind = excluded.kind,
                    is_uploaded = excluded.is_uploaded,
                    uploaded_at = excluded.uploaded_at,
                    parser_name = excluded.parser_name,
                    study_mode = excluded.study_mode,
                    confidence = excluded.confidence,
                    size_bytes = excluded.size_bytes,
                    modified_ns = excluded.modified_ns,
                    updated_at = excluded.updated_at
                """,
                (
                    document_id,
                    source_key,
                    display_name,
                    str(source_path),
                    source_path.name,
                    _divian_ai_doc_kind(source_path),
                    1 if upload_entry else 0,
                    str((upload_entry or {}).get("uploaded_at", "")).strip(),
                    parser_name,
                    study_mode,
                    confidence,
                    "pending",
                    profile_note,
                    size_bytes,
                    modified_ns,
                    0,
                    0,
                    0,
                    now_iso,
                ),
            )

            if not should_reindex:
                continue

            extracted = _divian_ai_extract_source(source_path, display_name)
            try:
                connection.execute("DELETE FROM knowledge_pages WHERE document_id = ?", (document_id,))
                connection.execute("DELETE FROM knowledge_chunks WHERE document_id = ?", (document_id,))
                connection.execute("DELETE FROM knowledge_records WHERE document_id = ?", (document_id,))

                if extracted.pages:
                    connection.executemany(
                        """
                        INSERT INTO knowledge_pages (
                            document_id, label, page_number, title, text, normalized, folded, lines_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            (
                                document_id,
                                page.label,
                                page.page_number,
                                page.title,
                                page.text,
                                page.normalized,
                                page.folded,
                                json.dumps(list(page.lines), ensure_ascii=False),
                            )
                            for page in extracted.pages
                        ],
                    )

                if extracted.chunks:
                    connection.executemany(
                        """
                        INSERT INTO knowledge_chunks (
                            document_id, label, page_number, text, normalized, tokens_json
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        [
                            (
                                document_id,
                                chunk.label,
                                chunk.page_number,
                                chunk.text,
                                chunk.normalized,
                                json.dumps(sorted(chunk.tokens), ensure_ascii=False),
                            )
                            for chunk in extracted.chunks
                        ],
                    )

                if extracted.records:
                    connection.executemany(
                        """
                        INSERT INTO knowledge_records (
                            document_id, label, row_number, fields_json, text, normalized, tokens_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            (
                                document_id,
                                record.label,
                                record.row_number,
                                json.dumps(list(record.fields), ensure_ascii=False),
                                record.text,
                                record.normalized,
                                json.dumps(sorted(record.tokens), ensure_ascii=False),
                            )
                            for record in extracted.records
                        ],
                    )

                if extracted.error:
                    sync_errors.append(extracted.error)

                if extracted.error and not (extracted.pages or extracted.chunks or extracted.records):
                    status = "error"
                elif extracted.error:
                    status = "indexed_with_warning"
                elif extracted.chunks or extracted.records or extracted.pages:
                    status = "indexed"
                else:
                    status = "stored"

                final_note = " ".join(part for part in (extracted.note, extracted.error) if part).strip()

                connection.execute(
                    """
                    UPDATE knowledge_documents
                    SET parser_name = ?, study_mode = ?, confidence = ?, status = ?, note = ?, page_count = ?, chunk_count = ?, record_count = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        extracted.parser_name,
                        extracted.study_mode,
                        extracted.confidence,
                        status,
                        final_note,
                        len(extracted.pages),
                        len(extracted.chunks),
                        len(extracted.records),
                        now_iso,
                        document_id,
                    ),
                )
            except Exception as exc:
                message = f"Nem sikerült indexelni: {display_name} ({exc})"
                sync_errors.append(message)
                connection.execute(
                    """
                    UPDATE knowledge_documents
                    SET status = 'error', note = ?, page_count = 0, chunk_count = 0, record_count = 0, updated_at = ?
                    WHERE id = ?
                    """,
                    (message, now_iso, document_id),
                )

        if active_keys:
            placeholders = ", ".join("?" for _ in active_keys)
            stale_rows = connection.execute(
                f"SELECT id FROM knowledge_documents WHERE source_key NOT IN ({placeholders})",
                tuple(active_keys),
            ).fetchall()
        else:
            stale_rows = connection.execute("SELECT id FROM knowledge_documents").fetchall()

        for stale_row in stale_rows:
            document_id = str(stale_row["id"])
            connection.execute("DELETE FROM knowledge_pages WHERE document_id = ?", (document_id,))
            connection.execute("DELETE FROM knowledge_chunks WHERE document_id = ?", (document_id,))
            connection.execute("DELETE FROM knowledge_records WHERE document_id = ?", (document_id,))
            connection.execute("DELETE FROM knowledge_documents WHERE id = ?", (document_id,))

    return sync_errors


def _divian_ai_cache_from_db(signature: tuple[tuple[str, int, int], ...]) -> DivianAIKnowledgeCache:
    cache = DivianAIKnowledgeCache(signature=signature, loaded_at=time.time())
    with _divian_ai_db_connection() as connection:
        documents = connection.execute(
            """
            SELECT id, source_name, status, note, parser_name, study_mode, confidence, kind, is_uploaded, uploaded_at, updated_at
            FROM knowledge_documents
            ORDER BY source_name COLLATE NOCASE
            """
        ).fetchall()
        cache.sources = [str(row["source_name"]) for row in documents]
        cache.source_meta = {
            str(row["source_name"]): {
                "parser_name": str(row["parser_name"] or "").strip(),
                "study_mode": str(row["study_mode"] or "").strip(),
                "confidence": str(row["confidence"] or "").strip(),
                "status": str(row["status"] or "").strip(),
                "note": str(row["note"] or "").strip(),
                "kind": str(row["kind"] or "").strip(),
                "is_uploaded": str(row["is_uploaded"] or "").strip(),
                "uploaded_at": str(row["uploaded_at"] or "").strip(),
                "updated_at": str(row["updated_at"] or "").strip(),
            }
            for row in documents
        }

        page_rows = connection.execute(
            """
            SELECT d.source_name, p.label, p.page_number, p.title, p.text, p.normalized, p.folded, p.lines_json
            FROM knowledge_pages p
            JOIN knowledge_documents d ON d.id = p.document_id
            ORDER BY d.source_name COLLATE NOCASE, p.page_number, p.id
            """
        ).fetchall()
        for row in page_rows:
            try:
                lines = tuple(json.loads(row["lines_json"]))
            except Exception:
                lines = tuple(line for line in str(row["text"]).splitlines() if line.strip())
            cache.pages.append(
                DivianAIPage(
                    label=str(row["label"]),
                    source_name=str(row["source_name"]),
                    page_number=int(row["page_number"]),
                    title=str(row["title"]),
                    text=str(row["text"]),
                    normalized=str(row["normalized"]),
                    folded=str(row["folded"]),
                    lines=lines,
                )
            )

        chunk_rows = connection.execute(
            """
            SELECT d.source_name, c.label, c.page_number, c.text, c.normalized, c.tokens_json
            FROM knowledge_chunks c
            JOIN knowledge_documents d ON d.id = c.document_id
            ORDER BY d.source_name COLLATE NOCASE, c.page_number, c.id
            """
        ).fetchall()
        for row in chunk_rows:
            try:
                tokens = frozenset(json.loads(row["tokens_json"]))
            except Exception:
                tokens = frozenset(_divian_ai_tokens(str(row["text"])))
            cache.chunks.append(
                DivianAIChunk(
                    label=str(row["label"]),
                    source_name=str(row["source_name"]),
                    page_number=int(row["page_number"]),
                    text=str(row["text"]),
                    normalized=str(row["normalized"]),
                    tokens=tokens,
                )
            )

        record_rows = connection.execute(
            """
            SELECT d.source_name, r.label, r.row_number, r.fields_json, r.text, r.normalized, r.tokens_json
            FROM knowledge_records r
            JOIN knowledge_documents d ON d.id = r.document_id
            ORDER BY d.source_name COLLATE NOCASE, r.row_number, r.id
            """
        ).fetchall()
        for row in record_rows:
            try:
                fields = tuple((str(key), str(value)) for key, value in json.loads(row["fields_json"]))
            except Exception:
                fields = tuple()
            try:
                tokens = frozenset(json.loads(row["tokens_json"]))
            except Exception:
                tokens = frozenset(_divian_ai_tokens(str(row["text"])))
            cache.records.append(
                DivianAIRecord(
                    label=str(row["label"]),
                    source_name=str(row["source_name"]),
                    row_number=int(row["row_number"]),
                    fields=fields,
                    text=str(row["text"]),
                    normalized=str(row["normalized"]),
                    tokens=tokens,
                )
            )

        for row in documents:
            if str(row["status"]).strip() == "error" and str(row["note"]).strip():
                cache.errors.append(str(row["note"]).strip())

    return cache


def _load_divian_ai_knowledge() -> DivianAIKnowledgeCache:
    global DIVIAN_AI_CACHE
    now = time.time()

    if DIVIAN_AI_CACHE.signature and (now - DIVIAN_AI_CACHE.loaded_at) < DIVIAN_AI_MEMORY_CACHE_SECONDS:
        return DIVIAN_AI_CACHE

    public_web_paths, public_web_errors = _divian_ai_public_web_source_paths()
    curated_document_paths = _divian_ai_curated_document_paths()
    source_paths = list(public_web_paths) + list(curated_document_paths)
    unique_paths: list[Path] = []
    seen_path_keys: set[str] = set()
    for path in source_paths:
        try:
            path_key = str(path.resolve()).lower()
        except Exception:
            path_key = str(path).lower()
        if path_key in seen_path_keys:
            continue
        seen_path_keys.add(path_key)
        unique_paths.append(path)
    source_paths = unique_paths
    signature = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size, DIVIAN_AI_INDEXER_VERSION) for path in source_paths)
    if signature == DIVIAN_AI_CACHE.signature:
        DIVIAN_AI_CACHE.loaded_at = now
        for error in public_web_errors:
            if error not in DIVIAN_AI_CACHE.errors:
                DIVIAN_AI_CACHE.errors.append(error)
        return DIVIAN_AI_CACHE

    if not source_paths:
        with _divian_ai_db_connection() as connection:
            connection.execute("DELETE FROM knowledge_pages")
            connection.execute("DELETE FROM knowledge_chunks")
            connection.execute("DELETE FROM knowledge_records")
            connection.execute("DELETE FROM knowledge_documents")
        cache = DivianAIKnowledgeCache(signature=signature, loaded_at=now)
        cache.errors.append("Még nincs elérhető Divian forrás a Divian-AI számára.")
        DIVIAN_AI_CACHE = cache
        return cache

    sync_errors = _divian_ai_sync_knowledge_registry(source_paths)
    sync_errors.extend(error for error in public_web_errors if error not in sync_errors)
    cache = _divian_ai_cache_from_db(signature)
    cache.errors.extend(error for error in sync_errors if error not in cache.errors)
    if not cache.chunks and not cache.errors:
        cache.errors.append("A Divian forrásokból nem sikerült használható szöveget kinyerni.")

    cache.loaded_at = now
    DIVIAN_AI_CACHE = cache
    return cache


def _divian_ai_select_chunks(question: str, chunks: list[DivianAIChunk], limit: int = 6) -> list[DivianAIChunk]:
    question_normalized = _divian_ai_fold_text(question)
    focus_tokens = _divian_ai_focus_tokens(question)
    question_tokens = focus_tokens or _divian_ai_tokens(question)
    if not question_tokens:
        return []

    scored_chunks: list[tuple[int, int, DivianAIChunk]] = []
    for chunk in chunks:
        overlap = question_tokens & chunk.tokens
        source_affinity = _divian_ai_source_affinity_score(question, chunk.source_name, chunk.label)
        if not overlap and not source_affinity:
            continue

        if len(focus_tokens) >= 2 and len(overlap) < 2 and source_affinity < 10:
            longest_overlap = max((len(token) for token in overlap), default=0)
            if longest_overlap < 7:
                continue

        score = len(overlap) * 7 + source_affinity
        for token in overlap:
            score += min(chunk.normalized.count(token), 3)
        if question_normalized and question_normalized in chunk.normalized:
            score += 10

        scored_chunks.append((score, len(overlap), chunk))

    scored_chunks.sort(key=lambda item: (item[0], item[1], len(item[2].text)), reverse=True)
    return [chunk for _, _, chunk in scored_chunks[:limit]]


def _divian_ai_detect_product_keys(question: str) -> list[str]:
    question_tokens = _divian_ai_tokens(question)
    matches: list[str] = []
    for product_key, aliases in DIVIAN_AI_PRODUCT_ALIASES.items():
        alias_tokens = {_divian_ai_fold_text(alias) for alias in aliases}
        if question_tokens & alias_tokens:
            matches.append(product_key)
    return matches


def _divian_ai_detect_subject_keys(question: str) -> list[str]:
    question_folded = _divian_ai_fold_text(question)
    question_tokens = _divian_ai_tokens(question)
    matches: list[str] = []
    for subject_key, aliases in DIVIAN_AI_SUBJECT_ALIASES.items():
        folded_aliases = [_divian_ai_fold_text(alias) for alias in aliases]
        if any(alias in question_folded for alias in folded_aliases) or question_tokens & set(folded_aliases):
            matches.append(subject_key)
    return matches


def _divian_ai_sanitize_history(history: object) -> list[dict[str, str]]:
    if not isinstance(history, list):
        return []

    clean_history: list[dict[str, str]] = []
    for item in history[-DIVIAN_AI_MAX_HISTORY_MESSAGES:]:
        if not isinstance(item, dict):
            continue

        role = str(item.get("role", "")).strip().lower()
        if role not in {"user", "assistant"}:
            continue

        content = str(item.get("content", "")).strip()
        if not content:
            continue

        clean_history.append(
            {
                "role": role,
                "content": _divian_ai_normalize_text(content)[:DIVIAN_AI_MAX_QUESTION_CHARS],
            }
        )

    return clean_history


def _divian_ai_last_history_content(history: list[dict[str, str]], role: str) -> str | None:
    for item in reversed(history):
        if item.get("role") == role:
            return item.get("content")
    return None


def _divian_ai_last_history_user_question(history: list[dict[str, str]]) -> str | None:
    return _divian_ai_last_history_content(history, "user")


def _divian_ai_is_correction_message(question: str) -> bool:
    folded_question = _divian_ai_fold_text(question)
    return any(marker in folded_question for marker in DIVIAN_AI_CORRECTION_MARKERS)


def _divian_ai_is_reference_followup(question: str) -> bool:
    folded_question = _divian_ai_fold_text(question)
    if re.match(r"^(es|akkor|es akkor|es meg)\b", folded_question):
        return True
    return any(marker in folded_question.split()[:4] for marker in {_divian_ai_fold_text(value) for value in DIVIAN_AI_REFERENCE_MARKERS})


def _divian_ai_extract_correction_focus(question: str) -> str | None:
    cleaned_question = _divian_ai_normalize_text(question)
    folded_question = _divian_ai_fold_text(cleaned_question)
    if "hanem" in folded_question:
        parts = re.split(r"\bhanem\b", cleaned_question, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) == 2 and parts[1].strip():
            return parts[1].strip(" .")

    if ":" in cleaned_question:
        _, value = cleaned_question.split(":", 1)
        if value.strip():
            return value.strip(" .")

    return None


def _divian_ai_canonical_focus_label(text: str) -> str | None:
    product_keys = _divian_ai_detect_product_keys(text)
    if product_keys:
        return _divian_ai_product_label(product_keys[0]) or text

    subject_keys = _divian_ai_detect_subject_keys(text)
    if not subject_keys:
        return None

    subject_labels = {
        "butorlap": "bútorlapok",
        "front": "frontok",
        "munkalap": "munkalapok",
        "falipanel": "falipanelek",
        "fogantyu": "fogantyúk",
        "korpusz": "korpuszok",
        "garancia": "garancia",
    }
    return subject_labels.get(subject_keys[0], text)


def _divian_ai_rewrite_question_from_correction(last_question: str, correction_focus: str) -> str:
    focus_label = _divian_ai_canonical_focus_label(correction_focus) or correction_focus
    folded_last_question = _divian_ai_fold_text(last_question)

    if _divian_ai_is_color_question(last_question):
        return f"Milyen színű {focus_label} vannak?"
    if any(term in folded_last_question for term in ("anyag", "anyagok", "mibol", "tipus")):
        return f"Milyen anyagú {focus_label} vannak?"
    if any(term in folded_last_question for term in ("mikor", "datum", "esedekes", "hatarido")):
        return f"Mi a releváns dátum {focus_label} esetén?"
    if "milyen" in folded_last_question:
        return f"Milyen {focus_label} érhetők el?"
    return f"{last_question}\nPontosítás: csak erre fókuszálj: {focus_label}."


def _divian_ai_upload_guidance(question: str, prefer_uploaded_sources: bool = False) -> str:
    return (
        "Jelenleg a Divian webes és katalógus forrásokból dolgozom. "
        "Ha valamire nincs biztos válasz, akkor azt jelzem, és nem találgatok."
    )


def _divian_ai_feedback_response(question: str, history: list[dict[str, str]]) -> dict | None:
    if not _divian_ai_is_correction_message(question):
        return None

    correction_focus = _divian_ai_extract_correction_focus(question)
    last_user_question = _divian_ai_last_history_user_question(history)
    if correction_focus and last_user_question:
        return None

    guidance = _divian_ai_upload_guidance(last_user_question or question, prefer_uploaded_sources=True)
    return {
        "ok": True,
        "answer": (
            "Rendben, akkor pontosítsuk a kérdést. "
            "Írd meg röviden, mire gondoltál pontosan, például: "
            "\"nem a frontokra, hanem a bútorlapokra gondoltam\" vagy "
            "\"csak a Kastamonu színeket mutasd\".\n\n"
            f"{guidance}"
        ),
        "sources": [],
    }


def _divian_ai_product_label(product_key: str) -> str | None:
    kitchen = DIVIAN_AI_COMPANY_PROFILE["kitchens"].get(product_key)
    if kitchen and kitchen.get("label"):
        return str(kitchen["label"])

    legacy = DIVIAN_AI_COMPANY_PROFILE["legacy"].get(product_key)
    if legacy and legacy.get("label"):
        return str(legacy["label"])

    return None


def _divian_ai_needs_product_context(question: str) -> bool:
    if _divian_ai_detect_product_keys(question):
        return False

    folded_question = _divian_ai_fold_text(question)
    contextual_markers = (
        "ebbol",
        "ennek",
        "ehhez",
        "errol",
        "rola",
        "abbol",
        "annak",
        "ahhoz",
        "belole",
        "hozza",
        "ugyanebbol",
        "ugyanennek",
    )

    if re.match(r"^(es|es akkor|es ilyenkor|es meg)\b", folded_question):
        return True

    if any(re.search(rf"\b{re.escape(marker)}\b", folded_question) for marker in contextual_markers):
        return True

    return False


def _divian_ai_last_history_product_label(history: list[dict[str, str]]) -> str | None:
    for item in reversed(history):
        if item.get("role") != "user":
            continue

        product_keys = _divian_ai_detect_product_keys(item.get("content", ""))
        if not product_keys:
            continue

        product_label = _divian_ai_product_label(product_keys[0])
        if product_label:
            return product_label

    return None


def _divian_ai_contextualize_question(question: str, history: list[dict[str, str]]) -> str:
    clean_question = question.strip()
    if not clean_question or not history:
        return clean_question

    last_user_question = _divian_ai_last_history_user_question(history)
    correction_focus = _divian_ai_extract_correction_focus(clean_question) if _divian_ai_is_correction_message(clean_question) else None
    if correction_focus and last_user_question:
        return _divian_ai_rewrite_question_from_correction(last_user_question, correction_focus)

    if last_user_question and last_user_question != clean_question and _divian_ai_is_reference_followup(clean_question):
        return f"{last_user_question}\nKiegészítő kérdés: {clean_question}"

    return clean_question


def _divian_ai_is_color_question(question: str) -> bool:
    folded_question = _divian_ai_fold_text(question)
    return any(term in folded_question for term in ("szin", "szinek", "szinu", "dekor", "sorold", "listazd"))


def _divian_ai_profile_kitchen(key: str) -> dict | None:
    return DIVIAN_AI_COMPANY_PROFILE["kitchens"].get(key)


def _divian_ai_current_kitchen_keys(group_key: str | None = None) -> list[str]:
    kitchens = DIVIAN_AI_COMPANY_PROFILE["kitchens"]
    return [
        key
        for key, value in kitchens.items()
        if value.get("current") and (group_key is None or value.get("group") == group_key)
    ]


def _divian_ai_collect_profile_colors(kitchen_keys: list[str], material_filter: str | None = None) -> tuple[list[str], list[str]]:
    kitchens = DIVIAN_AI_COMPANY_PROFILE["kitchens"]
    colors: list[str] = []
    sources: list[str] = []
    seen_colors: set[str] = set()
    seen_sources: set[str] = set()

    for kitchen_key in kitchen_keys:
        kitchen = kitchens.get(kitchen_key)
        if not kitchen:
            continue

        color_values = kitchen.get("front_colors", [])
        if material_filter:
            material_sets = kitchen.get("material_color_sets", {})
            matched_sets = [
                values
                for set_key, values in material_sets.items()
                if material_filter in _divian_ai_fold_text(set_key)
            ]
            if matched_sets:
                color_values = [color for values in matched_sets for color in values]
            elif any(material_filter in _divian_ai_fold_text(material) for material in kitchen.get("front_materials", [])):
                color_values = kitchen.get("front_colors", [])
            else:
                continue

            color_values = _divian_ai_refine_material_colors(color_values, material_filter)

        for color in color_values:
            color_key = _divian_ai_fold_text(color)
            if color_key in seen_colors:
                continue
            seen_colors.add(color_key)
            colors.append(color)

        source = kitchen.get("source")
        if source and source not in seen_sources:
            seen_sources.add(source)
            sources.append(source)

    return colors, sources


def _divian_ai_match_material_color_set(kitchen: dict, material_filter: str) -> list[str]:
    material_sets = kitchen.get("material_color_sets", {})
    matched_sets = [
        values
        for set_key, values in material_sets.items()
        if material_filter in _divian_ai_fold_text(set_key)
    ]
    if matched_sets:
        merged: list[str] = []
        seen: set[str] = set()
        for values in matched_sets:
            for color in values:
                color_key = _divian_ai_fold_text(color)
                if not color_key or color_key in seen:
                    continue
                seen.add(color_key)
                merged.append(color)
        return _divian_ai_refine_material_colors(merged, material_filter)
    return []


def _divian_ai_refine_material_colors(colors: list[str], material_filter: str, question: str = "") -> list[str]:
    if material_filter != "butorlap":
        return colors

    folded_question = _divian_ai_fold_text(question)
    asks_finish = any(term in folded_question for term in ("fenyes", "fényes", "matt", "magasfenyu", "magasfényű"))
    if asks_finish:
        return colors

    refined: list[str] = []
    seen: set[str] = set()
    for color in colors:
        folded_color = _divian_ai_fold_text(color)
        if any(term in folded_color for term in ("fenyes", "fényes", "matt", "magasfenyu", "magasfényű")):
            continue
        if folded_color in seen:
            continue
        seen.add(folded_color)
        refined.append(color)
    return refined or colors


def _divian_ai_format_source_list(values: list[str]) -> list[str]:
    unique_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values[:5]


def _divian_ai_profile_lineup_answer(question: str) -> dict | None:
    folded_question = _divian_ai_fold_text(question)
    question_tokens = _divian_ai_tokens(question)
    if _divian_ai_detect_product_keys(question):
        return None
    mentions_kitchens = "konyh" in folded_question or any(token.startswith("konyh") for token in question_tokens)
    asks_current_lineup = (
        (
            mentions_kitchens
            and any(
                term in folded_question
                for term in ("milyen", "jelenleg", "hany", "fajta", "felsorol", "listaz", "aktualis", "most")
            )
        )
        or ("elemes" in folded_question and "blokk" in folded_question and "kulonbseg" in folded_question)
    )
    if not asks_current_lineup:
        return None

    elemes_members = [
        DIVIAN_AI_COMPANY_PROFILE["kitchens"][key]["label"]
        for key in DIVIAN_AI_COMPANY_PROFILE["groups"]["elemes"]["members"]
    ]
    blokk_members = [
        DIVIAN_AI_COMPANY_PROFILE["kitchens"][key]["label"]
        for key in DIVIAN_AI_COMPANY_PROFILE["groups"]["blokk"]["members"]
    ]

    if "kulonbseg" in folded_question:
        answer = (
            "A jelenlegi belső tudás alapján:\n"
            f"- Elemes konyhák: {', '.join(elemes_members)}. Ezek elemenként vásárolhatók meg az elérhető elemjegyzékből.\n"
            f"- Blokk konyhák: {', '.join(blokk_members)}. Ezek előre összeállított konstrukciók, szűkített elemválasztékkal."
        )
        return {
            "ok": True,
            "answer": answer,
            "sources": ["Belső aktuális kínálat"],
        }

    answer = (
        "A jelenlegi belső tudás alapján összesen 8 fő konyhatípus fut:\n"
        f"- Elemes: {', '.join(elemes_members)}\n"
        f"- Blokk: {', '.join(blokk_members)}"
    )
    return {
        "ok": True,
        "answer": answer,
        "sources": ["Belső aktuális kínálat"],
    }


def _divian_ai_profile_material_answer(question: str) -> dict | None:
    folded_question = _divian_ai_fold_text(question)
    subject_keys = _divian_ai_detect_subject_keys(question)
    question_tokens = _divian_ai_tokens(question)
    if _divian_ai_detect_product_keys(question):
        return None

    if "munkalap" in subject_keys and not _divian_ai_detect_product_keys(question):
        colors = DIVIAN_AI_COMPANY_PROFILE["worktops"]["all_colors"]
        answer = "A feltöltött tudástár alapján ezek a munkalap színek/dekorok érhetők el:\n- " + "\n- ".join(colors)
        return {
            "ok": True,
            "answer": answer,
            "sources": [DIVIAN_AI_COMPANY_PROFILE["worktops"]["source"]],
        }

    if ("butorlap" in subject_keys or "butorlap" in question_tokens or "butorlap" in folded_question) and _divian_ai_is_color_question(question):
        kitchen_keys = [key for key in ("doroti", "anna", "kira", "kata", "kinga", "klio") if _divian_ai_profile_kitchen(key)]
        colors, sources = _divian_ai_collect_profile_colors(kitchen_keys, material_filter="butorlap")
        if colors:
            answer = "A jelenlegi kínálat és a kézikönyv alapján ezek a fő bútorlap színek/dekorok érhetők el:\n- " + "\n- ".join(colors)
            return {
                "ok": True,
                "answer": answer,
                "sources": ["Belső aktuális kínálat"] + _divian_ai_format_source_list(sources),
            }

    if "front" in subject_keys and _divian_ai_is_color_question(question):
        kitchen_keys = [key for key in _divian_ai_current_kitchen_keys() if key in {"doroti", "antonia", "laura", "zille", "anna", "kira", "kata", "kinga"}]
        colors, sources = _divian_ai_collect_profile_colors(kitchen_keys)
        if colors:
            answer = "A jelenlegi kínálat és a kézikönyv alapján ezek a fő front színek érhetők el:\n- " + "\n- ".join(colors)
            return {
                "ok": True,
                "answer": answer,
                "sources": ["Belső aktuális kínálat"] + _divian_ai_format_source_list(sources),
            }

    if "mdf" in folded_question and _divian_ai_is_color_question(question):
        kitchen_keys = [key for key in _divian_ai_current_kitchen_keys() if key in {"doroti", "antonia", "laura", "zille"}]
        colors, sources = _divian_ai_collect_profile_colors(kitchen_keys, material_filter="mdf")
        if colors:
            answer = "A jelenlegi kínálat és a kézikönyv alapján ezek a fő MDF front színek szerepelnek:\n- " + "\n- ".join(colors)
            return {
                "ok": True,
                "answer": answer,
                "sources": ["Belső aktuális kínálat"] + _divian_ai_format_source_list(sources),
            }

    return None


def _divian_ai_profile_kitchen_answer(question: str) -> dict | None:
    product_keys = _divian_ai_detect_product_keys(question)
    if not product_keys:
        return None

    kitchen_key = product_keys[0]
    kitchen = _divian_ai_profile_kitchen(kitchen_key)
    if kitchen is None:
        return None

    subject_keys = _divian_ai_detect_subject_keys(question)
    folded_question = _divian_ai_fold_text(question)
    asks_material = any(term in folded_question for term in ("anyag", "anyagok", "mibol", "miből", "tipus"))
    sources = _divian_ai_format_source_list([kitchen.get("source", "")] + (["Belső aktuális kínálat"] if kitchen.get("current") else []))
    sources = [source for source in sources if source]

    if not kitchen.get("current") and "jelenleg" in _divian_ai_fold_text(question):
        legacy = DIVIAN_AI_COMPANY_PROFILE["legacy"].get(kitchen_key)
        if legacy:
            return {
                "ok": True,
                "answer": f"{legacy['label']} szerepel a PDF-ben, de a jelenlegi belső lista szerint nem része az aktuális kínálatnak.",
                "sources": [legacy["source"], "Belső aktuális kínálat"],
            }

    if "garancia" in subject_keys and kitchen.get("warranty"):
        return {
            "ok": True,
            "answer": f"{kitchen['label']} garanciája: {kitchen['warranty']}.",
            "sources": sources,
        }

    if "munkalap" in subject_keys and kitchen.get("worktop_options"):
        return {
            "ok": True,
            "answer": f"{kitchen['label']} munkalap opciói: {', '.join(kitchen['worktop_options'])}.",
            "sources": sources,
        }

    if asks_material and kitchen.get("front_materials"):
        return {
            "ok": True,
            "answer": f"{kitchen['label']} front anyagai: {', '.join(kitchen['front_materials'])}.",
            "sources": sources,
        }

    if ("front" in subject_keys or "butorlap" in subject_keys or _divian_ai_is_color_question(question)) and kitchen.get("front_colors"):
        if "butorlap" in subject_keys:
            butorlap_colors = _divian_ai_match_material_color_set(kitchen, "butorlap")
            if butorlap_colors:
                return {
                    "ok": True,
                    "answer": f"{kitchen['label']} bútorlap színei:\n- " + "\n- ".join(butorlap_colors),
                    "sources": sources,
                }
        if "front" in subject_keys:
            label = "front színei"
        else:
            label = "színei"
        return {
            "ok": True,
            "answer": f"{kitchen['label']} {label}:\n- " + "\n- ".join(kitchen["front_colors"]),
            "sources": sources,
        }

    summary_lines = [
        f"- Típus: {DIVIAN_AI_COMPANY_PROFILE['groups'][kitchen['group']]['label']}",
        f"- Röviden: {kitchen['summary']}",
    ]
    if kitchen.get("front_materials"):
        summary_lines.append(f"- Front anyagok: {', '.join(kitchen['front_materials'])}")
    if kitchen.get("worktop_options"):
        summary_lines.append(f"- Munkalap: {', '.join(kitchen['worktop_options'])}")
    if kitchen.get("warranty"):
        summary_lines.append(f"- Garancia: {kitchen['warranty']}")
    if kitchen.get("sizes"):
        summary_lines.append(f"- Elérhető méretek: {', '.join(kitchen['sizes'])}")
    if kitchen.get("notes"):
        summary_lines.extend(f"- {note}" for note in kitchen["notes"][:2])

    return {
        "ok": True,
        "answer": f"{kitchen['label']} összefoglaló:\n" + "\n".join(summary_lines),
        "sources": sources,
    }


def _divian_ai_catalog_surface_answer(
    question: str,
    knowledge: DivianAIKnowledgeCache,
    evidence_label: str = "A Divian források alapján",
) -> dict | None:
    if not _divian_ai_is_color_question(question):
        return None

    subject_keys = _divian_ai_detect_subject_keys(question)
    if not any(subject in subject_keys for subject in ("munkalap", "falipanel")):
        return None

    sections: list[tuple[str, list[str], list[str]]] = []
    if "munkalap" in subject_keys:
        colors, sources = _divian_ai_catalog_surface_colors(knowledge, "munkalap")
        if colors:
            sections.append(("Munkalap színek", colors, sources))
    if "falipanel" in subject_keys:
        colors, sources = _divian_ai_catalog_surface_colors(knowledge, "falipanel")
        if colors:
            sections.append(("Falipanel színek", colors, sources))

    if not sections:
        return None

    answer_lines: list[str] = []
    source_labels: list[str] = []
    seen_sources: set[str] = set()
    for label, colors, sources in sections:
        answer_lines.append(f"- {label}: " + ", ".join(colors))
        for source in sources:
            if source not in seen_sources:
                seen_sources.add(source)
                source_labels.append(source)

    return {
        "ok": True,
        "answer": "A Divian katalógus alapján:\n" + "\n".join(answer_lines),
        "sources": source_labels[:4],
    }


def _divian_ai_filter_pages(question: str, knowledge: DivianAIKnowledgeCache) -> list[DivianAIPage]:
    product_keys = _divian_ai_detect_product_keys(question)
    subject_keys = _divian_ai_detect_subject_keys(question)
    filtered_pages = knowledge.pages

    if product_keys:
        product_terms = {
            _divian_ai_fold_text(alias)
            for product_key in product_keys
            for alias in DIVIAN_AI_PRODUCT_ALIASES[product_key]
        }
        filtered_pages = [
            page
            for page in filtered_pages
            if any(term in page.folded for term in product_terms)
        ]
        title_matched_pages = [
            page
            for page in filtered_pages
            if any(term in _divian_ai_fold_text(page.title) for term in product_terms)
        ]
        if title_matched_pages:
            filtered_pages = title_matched_pages

    if subject_keys:
        subject_filtered: list[DivianAIPage] = []
        for page in filtered_pages:
            if "butorlap" in subject_keys:
                title_folded = _divian_ai_fold_text(page.title)
                allowed_butorlap_titles = ("anna konyha", "kira konyha", "kata konyha", "kinga konyha", "doroti konyha")
                if (
                    (
                        any(name in title_folded for name in allowed_butorlap_titles)
                        and (
                            "front szin" in page.folded
                            or "front es korpusz szinek" in page.folded
                            or "korpusz szinek" in page.folded
                            or "butorlap frontok" in page.folded
                        )
                    )
                    or "oldaltakarok" in title_folded
                ):
                    subject_filtered.append(page)
                continue

            if "falipanel" in subject_keys and "falipanel" in page.folded:
                subject_filtered.append(page)
                continue

            if "munkalap" in subject_keys and ("munkalapok" in page.folded or "munkalap" in page.folded):
                subject_filtered.append(page)
                continue

            if any(_divian_ai_fold_text(alias) in page.folded for subject_key in subject_keys for alias in DIVIAN_AI_SUBJECT_ALIASES[subject_key]):
                subject_filtered.append(page)

        if subject_filtered:
            filtered_pages = subject_filtered

    return filtered_pages or knowledge.pages


def _divian_ai_extract_color_list(question: str, knowledge: DivianAIKnowledgeCache) -> tuple[list[str], list[str]]:
    relevant_pages = _divian_ai_filter_pages(question, knowledge)
    subject_keys = _divian_ai_detect_subject_keys(question)
    found_phrases: list[tuple[int, str, str]] = []
    seen_phrases: set[str] = set()
    excluded_phrases = set()

    if any(subject in subject_keys for subject in ("butorlap", "front", "korpusz", "munkalap", "falipanel")):
        excluded_phrases.update({"Króm", "Arany", "Rose gold", "Matt fekete"})

    for page in relevant_pages:
        for phrase in DIVIAN_AI_COLOR_PHRASES:
            if phrase in excluded_phrases:
                continue
            folded_phrase = _divian_ai_fold_text(phrase)
            position = page.folded.find(folded_phrase)
            if position == -1:
                continue
            if folded_phrase in seen_phrases:
                continue
            seen_phrases.add(folded_phrase)
            found_phrases.append((position, phrase, page.label))

    found_phrases.sort(key=lambda item: (item[2], item[0], item[1]))
    colors = [phrase for _, phrase, _ in found_phrases]
    source_labels = []
    seen_sources: set[str] = set()
    for _, _, label in found_phrases:
        if label in seen_sources:
            continue
        seen_sources.add(label)
        source_labels.append(label)
    return colors, source_labels


def _divian_ai_best_matching_source(question: str, sources: list[str]) -> str | None:
    best_source = ""
    best_score = 0
    for source_name in sources:
        score = _divian_ai_source_affinity_score(question, source_name)
        if score > best_score:
            best_score = score
            best_source = source_name
    return best_source if best_score >= 10 else None


def _divian_ai_source_summary_answer(
    question: str,
    knowledge: DivianAIKnowledgeCache,
    evidence_label: str = "A Divian források alapján",
) -> dict | None:
    folded_question = _divian_ai_fold_text(question)
    if not any(hint in folded_question for hint in DIVIAN_AI_FILE_QUERY_HINTS):
        return None

    best_source = _divian_ai_best_matching_source(question, knowledge.sources)
    if not best_source:
        return None

    source_records = [record for record in knowledge.records if record.source_name == best_source]
    if source_records:
        field_names: list[str] = []
        seen_field_names: set[str] = set()
        for record in source_records[:12]:
            for key, _ in record.fields:
                folded_key = _divian_ai_fold_text(key)
                if folded_key in seen_field_names:
                    continue
                seen_field_names.add(folded_key)
                field_names.append(key)
                if len(field_names) == 5:
                    break
            if len(field_names) == 5:
                break

        answer = f"{evidence_label} a(z) {best_source} fájlban {len(source_records)} beolvasott sor van."
        if field_names:
            answer += f" A fő mezők: {', '.join(field_names)}."
        return {
            "ok": True,
            "answer": answer,
            "sources": [best_source],
        }

    source_pages = [page for page in knowledge.pages if page.source_name == best_source]
    if source_pages:
        answer = f"{evidence_label} a(z) {best_source} dokumentumból {len(source_pages)} oldal került beolvasásra."
        return {
            "ok": True,
            "answer": answer,
            "sources": [best_source],
        }

    return None


def _divian_ai_company_founding_answer(
    question: str,
    knowledge: DivianAIKnowledgeCache,
    evidence_label: str = "A Divian források alapján",
) -> dict | None:
    folded_question = _divian_ai_fold_text(question)
    if not any(term in folded_question for term in ("mikor alakult", "alapitas", "alapit", "alapított")):
        return None

    preferred_pages = [
        page
        for page in knowledge.pages
        if any(
            hint in _divian_ai_fold_text(page.source_name)
            for hint in ("divian hivatalos - rolunk", "divian partner - fooldal")
        )
    ]
    candidate_pages = preferred_pages or knowledge.pages
    for page in candidate_pages:
        match = re.search(r"\b((?:19|20)\d{2})-?ben\s+alakult", _divian_ai_fold_text(page.text))
        if not match:
            continue
        year = match.group(1)
        return {
            "ok": True,
            "answer": f"{evidence_label} a Divian-Mega Kft. {year}-ben alakult.",
            "sources": [page.label],
        }
    return None


def _divian_ai_is_company_info_question(question: str) -> bool:
    folded_question = _divian_ai_fold_text(question)
    company_terms = (
        "divian",
        "ceg",
        "cegjegyzek",
        "cegjegyzek",
        "adoszam",
        "szekhely",
        "telephely",
        "fotevekenyseg",
        "főtevékenys",
        "mivel foglalkozik",
        "mivel foglalkoznak",
        "partner felulet",
        "partner oldal",
        "akcio",
        "akcioink",
        "uj termek",
        "uj termekek",
        "viszontelado",
        "beepito",
        "beépítő",
        "mikor alakult",
        "alapit",
        "alapított",
    )
    return any(term in folded_question for term in company_terms)


def _divian_ai_is_partner_offer_question(question: str) -> bool:
    folded_question = _divian_ai_fold_text(question)
    return any(
        term in folded_question
        for term in (
            "akcio",
            "akcioink",
            "akcios",
            "uj termek",
            "uj termekeink",
            "ujdonsag",
            "ujdonsagok",
        )
    )


def _divian_ai_official_web_pages(knowledge: DivianAIKnowledgeCache) -> list[DivianAIPage]:
    return [
        page
        for page in knowledge.pages
        if any(
            hint in _divian_ai_fold_text(page.source_name)
            for hint in ("divian hivatalos", "divian partner")
        )
    ]


def _divian_ai_extract_web_field_value(page: DivianAIPage, labels: tuple[str, ...]) -> str:
    folded_labels = tuple(_divian_ai_fold_text(label) for label in labels)
    for index, line in enumerate(page.lines):
        folded_line = _divian_ai_fold_text(line)
        if not any(label in folded_line for label in folded_labels):
            continue
        if ":" in line:
            value = line.split(":", 1)[1].strip()
            if value:
                return value
        for next_line in page.lines[index + 1 : index + 6]:
            next_folded = _divian_ai_fold_text(next_line)
            if ":" in next_line and not re.search(r"\d", next_line):
                break
            if any(label in next_folded for label in folded_labels):
                continue
            if next_line.strip():
                return next_line.strip()
    return ""


def _divian_ai_extract_web_field_list(page: DivianAIPage, labels: tuple[str, ...]) -> list[str]:
    folded_labels = tuple(_divian_ai_fold_text(label) for label in labels)
    for index, line in enumerate(page.lines):
        folded_line = _divian_ai_fold_text(line)
        if not any(label in folded_line for label in folded_labels):
            continue
        values: list[str] = []
        if ":" in line:
            value = line.split(":", 1)[1].strip()
            if value:
                values.append(value)
        for next_line in page.lines[index + 1 : index + 8]:
            next_folded = _divian_ai_fold_text(next_line)
            if ":" in next_line and values:
                break
            if any(label in next_folded for label in folded_labels):
                continue
            if not next_line.strip():
                continue
            if re.search(r"\d{4}", next_line):
                values.append(next_line.strip())
            elif values:
                break
        return values
    return []


def _divian_ai_partner_product_name(page: DivianAIPage) -> str:
    explicit_name = _divian_ai_extract_web_field_value(page, ("Termék neve",))
    if explicit_name:
        return explicit_name
    source_name = _clean_spaces(page.source_name)
    source_parts = [part.strip() for part in source_name.split(" - ") if part.strip()]
    if source_parts:
        return source_parts[-1]
    return source_name


def _divian_ai_detect_partner_category_keys(question: str) -> list[str]:
    folded_question = _divian_ai_fold_text(question)
    detected: list[str] = []
    for category_key, aliases in DIVIAN_AI_PARTNER_CATEGORY_ALIASES.items():
        if any(_divian_ai_fold_text(alias) in folded_question for alias in aliases):
            detected.append(category_key)
    return detected


def _divian_ai_partner_product_titles(pages: list[DivianAIPage]) -> list[str]:
    titles: list[str] = []
    seen_titles: set[str] = set()
    rejected_titles = {
        "belepes",
        "akciok",
        "uj termekek",
        "divian partner - uj termek",
        "divian partner - akcios termek",
        "divian partner - termek",
    }
    for page in pages:
        title = _clean_spaces(_divian_ai_partner_product_name(page))
        if not title:
            continue
        folded_title = _divian_ai_fold_text(title)
        if folded_title in rejected_titles or re.fullmatch(r"\d+\. oldal", folded_title):
            continue
        if folded_title in seen_titles:
            continue
        seen_titles.add(folded_title)
        titles.append(title)
    return titles


def _divian_ai_is_partner_catalog_question(question: str) -> bool:
    folded_question = _divian_ai_fold_text(question)
    if not _divian_ai_detect_partner_category_keys(question):
        return False
    return any(
        term in folded_question
        for term in (
            "milyen",
            "fajta",
            "sorold",
            "listaz",
            "listáz",
            "miket",
            "mik vannak",
            "milyen van",
            "milyen vannak",
        )
    )


def _divian_ai_partner_alias_match(text: str, alias: str) -> bool:
    folded_text = _divian_ai_fold_text(text)
    folded_alias = _divian_ai_fold_text(alias)
    if " " in folded_alias:
        return folded_alias in folded_text
    return folded_alias in _divian_ai_tokens(folded_text)


def _divian_ai_partner_catalog_answer(
    question: str,
    knowledge: DivianAIKnowledgeCache,
    evidence_label: str = "A Divian források alapján",
) -> dict | None:
    category_keys = _divian_ai_detect_partner_category_keys(question)
    if not category_keys:
        return None

    partner_pages = [
        page
        for page in knowledge.pages
        if "divian partner" in _divian_ai_fold_text(page.source_name)
        and "szoveg" in _divian_ai_fold_text(page.label)
    ]
    if not partner_pages:
        return None

    matching_pages: list[DivianAIPage] = []
    generic_titles = {
        "akciok",
        "uj termekek",
        "fooldal",
        "kapcsolat",
        "aszf",
        "adatvedelmi nyilatkozat",
        "garancia bejelento",
        "szekek",
        "asztalok",
        "etkezogarniturak",
        "etkezőgarnitúrák",
        "vasalatok",
        "kiegeszitok",
        "kiegészítők",
        "blokk konyha",
    }
    for page in partner_pages:
        source_folded = _divian_ai_fold_text(page.source_name)
        title_folded = _divian_ai_fold_text(_divian_ai_partner_product_name(page))
        if title_folded in generic_titles or re.fullmatch(r"\d+\. oldal", title_folded):
            continue
        if any(
            any(
                _divian_ai_partner_alias_match(title_folded, alias)
                or _divian_ai_partner_alias_match(source_folded, alias)
                for alias in DIVIAN_AI_PARTNER_CATEGORY_ALIASES.get(category_key, ())
            )
            for category_key in category_keys
        ):
            matching_pages.append(page)

    titles = _divian_ai_partner_product_titles(matching_pages)
    if not titles:
        return None

    visible_titles = titles[:18]
    category_label = category_keys[0].replace("_", " ")
    category_label = {
        "szek": "széket",
        "asztal": "asztalt",
        "garnitura": "garnitúrát",
        "konyhagep": "konyhagépet",
        "kisgep": "konyhai kisgépet",
        "mosogatotalca": "mosogatótálcát",
        "csaptelep": "csaptelepet",
        "vasalat": "vasalatot",
        "kiegeszito": "kiegészítőt",
        "blokk konyha": "blokk konyhát",
    }.get(category_label, category_label)
    answer = (
        f"{evidence_label} jelenleg {len(titles)} partneres {category_label} látok a publikus katalógusban:\n- "
        + "\n- ".join(visible_titles)
    )
    if len(titles) > len(visible_titles):
        answer += f"\n- ... és még {len(titles) - len(visible_titles)} további tételt."
    return {
        "ok": True,
        "answer": answer,
        "sources": [page.label for page in matching_pages[:8]],
    }


def _divian_ai_partner_offer_answer(
    question: str,
    knowledge: DivianAIKnowledgeCache,
    evidence_label: str = "A Divian források alapján",
) -> dict | None:
    folded_question = _divian_ai_fold_text(question)
    if "akcio" in folded_question:
        offer_key = "akcio"
        intro = "akciós terméket"
    elif "uj termek" in folded_question or "ujdonsag" in folded_question:
        offer_key = "uj termek"
        intro = "új terméket"
    else:
        return None

    partner_pages = [
        page
        for page in knowledge.pages
        if "divian partner" in _divian_ai_fold_text(page.source_name)
        and "szoveg" in _divian_ai_fold_text(page.label)
        and offer_key in _divian_ai_fold_text(page.source_name)
    ]
    if not partner_pages:
        return None

    titles = _divian_ai_partner_product_titles(partner_pages)
    if not titles:
        return None

    visible_titles = titles[:18]
    answer = (
        f"{evidence_label} jelenleg {len(titles)} {intro} látok a publikus partneres oldalon:\n- "
        + "\n- ".join(visible_titles)
    )
    if len(titles) > len(visible_titles):
        answer += f"\n- ... és még {len(titles) - len(visible_titles)} további tételt."

    return {
        "ok": True,
        "answer": answer,
        "sources": [page.label for page in partner_pages[:8]],
    }


def _divian_ai_lighting_answer(
    question: str,
    knowledge: DivianAIKnowledgeCache,
    evidence_label: str = "A Divian források alapján",
) -> dict | None:
    folded_question = _divian_ai_fold_text(question)
    subject_keys = _divian_ai_detect_subject_keys(question)
    if "vilagitas" not in subject_keys and "led" not in folded_question and "vilagitas" not in folded_question:
        return None

    items: list[str] = []
    seen_items: set[str] = set()
    sources: list[str] = []
    seen_sources: set[str] = set()

    def add_item(value: str) -> None:
        clean_value = _clean_spaces(value).strip(" .,-")
        if not clean_value:
            return
        folded_value = _divian_ai_fold_text(clean_value)
        if folded_value in seen_items:
            return
        seen_items.add(folded_value)
        items.append(clean_value)

    def add_source(value: str) -> None:
        if not value or value in seen_sources:
            return
        seen_sources.add(value)
        sources.append(value)

    for page in knowledge.pages:
        folded_source = _divian_ai_fold_text(page.source_name)
        folded_text = _divian_ai_fold_text(page.text)
        if not any(token in folded_text or token in folded_source for token in ("led", "vilagitas", "paraelszivo", "páraelszívó")):
            continue

        if "divian partner - termek - kiegeszitok" in folded_source or "divian partner - akcios termek - kiegeszitok" in folded_source:
            if "konyhai vilagitas" in folded_text:
                add_item("Konyhai világítás kategória")
                add_source(page.label)

            for match in re.finditer(r"Divian kiegészítő LED profil 2 m [^\n,]+", page.text, flags=re.IGNORECASE):
                add_item(match.group(0))
                add_source(page.label)

        if "divian_katalogus" in folded_source:
            for phrase in (
                "Divian konyhai LED szett",
                "Divian kiegészítő LED profil 2 m Eloxált",
                "Divian kiegészítő LED profil 2 m Fehér",
                "Divian kiegészítő LED profil 2 m Fekete",
            ):
                if _divian_ai_fold_text(phrase) in folded_text:
                    add_item(phrase)
                    add_source(page.label)

            if "vilagitas:" in folded_text and "led" in folded_text and "paraelszivo" in folded_text:
                add_item("Beépített LED világítású páraelszívók")
                add_source(page.label)

        if "elemjegyzek" in folded_source:
            for phrase in ("Vonalas led", "Kocka led", "Karos led", "Távirányítós színváltós"):
                if _divian_ai_fold_text(phrase) in folded_text:
                    add_item(phrase)
                    add_source(page.label)

    if not items:
        return None

    answer_lines = "\n- ".join(items[:8])
    answer = f"{evidence_label} ezek a világítási megoldások látszanak a jelenlegi Divian-forrásokban:\n- {answer_lines}"
    return {
        "ok": True,
        "answer": answer,
        "sources": sources[:6],
    }


def _divian_ai_company_web_answer(
    question: str,
    knowledge: DivianAIKnowledgeCache,
    evidence_label: str = "A Divian források alapján",
) -> dict | None:
    if not _divian_ai_is_company_info_question(question):
        return None

    official_pages = _divian_ai_official_web_pages(knowledge)
    if not official_pages:
        return None

    folded_question = _divian_ai_fold_text(question)
    about_pages = [page for page in official_pages if "rolunk" in _divian_ai_fold_text(page.source_name)]
    partner_pages = [page for page in official_pages if "partner - fooldal" in _divian_ai_fold_text(page.source_name)]
    partner_action_pages = [page for page in official_pages if "partner - akciok" in _divian_ai_fold_text(page.source_name)]
    partner_new_pages = [page for page in official_pages if "partner - uj termekek" in _divian_ai_fold_text(page.source_name)]
    partner_action_product_pages = [page for page in official_pages if "partner - akcios termek" in _divian_ai_fold_text(page.source_name)]
    partner_new_product_pages = [page for page in official_pages if "partner - uj termek" in _divian_ai_fold_text(page.source_name)]
    legal_pages = [
        page
        for page in official_pages
        if any(term in _divian_ai_fold_text(page.source_name) for term in ("adatkezeles", "aszf"))
    ]

    if "szekhely" in folded_question:
        for page in legal_pages:
            value = _divian_ai_extract_web_field_value(page, ("SZÉKHELY",))
            if value:
                return {
                    "ok": True,
                    "answer": f"{evidence_label} a cég székhelye: {value}.",
                    "sources": [page.label],
                }

    if "cegjegyzek" in folded_question or "cegjegyzek" in folded_question:
        for page in legal_pages:
            value = _divian_ai_extract_web_field_value(page, ("CÉGJEGYZÉKSZÁM", "CÉGJEGYZÉK SZÁM"))
            if value:
                return {
                    "ok": True,
                    "answer": f"{evidence_label} a cég cégjegyzékszáma: {value}.",
                    "sources": [page.label],
                }

    if "adoszam" in folded_question:
        for page in legal_pages:
            value = _divian_ai_extract_web_field_value(page, ("ADÓSZÁM",))
            if value:
                return {
                    "ok": True,
                    "answer": f"{evidence_label} a cég adószáma: {value}.",
                    "sources": [page.label],
                }

    if "telephely" in folded_question:
        for page in legal_pages:
            values = _divian_ai_extract_web_field_list(page, ("A CÉG TELEPHELYEI", "TELEPHELYEI"))
            if values:
                return {
                    "ok": True,
                    "answer": f"{evidence_label} a jelenleg beolvasott telephelyek:\n- " + "\n- ".join(values),
                    "sources": [page.label],
                }

    if "fotevekenyseg" in folded_question or "főtevékenys" in folded_question or "mivel foglalkozik" in folded_question or "mivel foglalkoznak" in folded_question:
        for page in legal_pages:
            value = _divian_ai_extract_web_field_value(page, ("FŐTEVÉKENYSÉGE", "FŐ TEVÉKENYSÉGE"))
            if value:
                extra = ""
                for about_page in about_pages:
                    sentence_match = re.search(r"A Divian-Mega Kft\.\s+\d{4}-ben alakult\s+([^.]*)\.", about_page.text, flags=re.IGNORECASE)
                    if sentence_match:
                        extra = _divian_ai_normalize_text(sentence_match.group(1))
                        break
                answer = f"{evidence_label} a cég főtevékenysége: {value}."
                if extra:
                    answer += f" A hivatalos bemutatkozás szerint {extra}."
                return {
                    "ok": True,
                    "answer": answer,
                    "sources": [page.label] + ([about_pages[0].label] if about_pages else []),
                }

    if "akcio" in folded_question:
        action_titles = _divian_ai_partner_product_titles(partner_action_product_pages)
        if action_titles:
            visible_titles = action_titles[:18]
            answer = (
                f"{evidence_label} jelenleg {len(action_titles)} akciós terméket látok a partnerfelület publikus katalógusából:\n- "
                + "\n- ".join(visible_titles)
            )
            if len(action_titles) > len(visible_titles):
                answer += f"\n- ... és még {len(action_titles) - len(visible_titles)} további tételt."
            source_labels = [page.label for page in partner_action_product_pages[:6]]
            if partner_action_pages:
                source_labels = [partner_action_pages[0].label] + source_labels
            return {
                "ok": True,
                "answer": answer,
                "sources": source_labels,
            }
        return {
            "ok": True,
            "answer": "A partneres akcióoldal be van kötve, de most még nem jött ki belőle használható akciós terméklista.",
            "sources": ["Divian partner - Akciók"],
        }

    if "uj termek" in folded_question:
        new_titles = _divian_ai_partner_product_titles(partner_new_product_pages)
        if new_titles:
            visible_titles = new_titles[:18]
            answer = (
                f"{evidence_label} jelenleg {len(new_titles)} új terméket látok a partnerfelület publikus katalógusából:\n- "
                + "\n- ".join(visible_titles)
            )
            if len(new_titles) > len(visible_titles):
                answer += f"\n- ... és még {len(new_titles) - len(visible_titles)} további tételt."
            source_labels = [page.label for page in partner_new_product_pages[:6]]
            if partner_new_pages:
                source_labels = [partner_new_pages[0].label] + source_labels
            return {
                "ok": True,
                "answer": answer,
                "sources": source_labels,
            }
        return {
            "ok": True,
            "answer": "A partneres új termékek oldal be van kötve, de most még nem jött ki belőle használható terméklista.",
            "sources": ["Divian partner - Új termékek"],
        }

    if "partner felulet" in folded_question or "partner oldal" in folded_question or "viszontelado" in folded_question:
        for page in partner_pages:
            lines = [line.strip() for line in page.lines if line.strip()]
            summary_lines = [
                line
                for line in lines
                if any(term in _divian_ai_fold_text(line) for term in ("viszontelado", "akcio", "garancia", "kapcsolat", "uj termekek"))
            ]
            if summary_lines:
                answer = (
                    f"{evidence_label} a partner.divian.hu a viszonteladói partnerfelület. "
                    + "A beolvasott tartalom alapján itt ilyen fő részek érhetők el: "
                    + ", ".join(summary_lines[:4])
                    + "."
                )
                return {
                    "ok": True,
                    "answer": answer,
                    "sources": [page.label],
                }

    return _divian_ai_company_founding_answer(question, knowledge, evidence_label=evidence_label)


def _divian_ai_element_catalog_answer(
    question: str,
    knowledge: DivianAIKnowledgeCache,
    evidence_label: str = "A Divian források alapján",
) -> dict | None:
    folded_question = _divian_ai_fold_text(question)
    product_keys = _divian_ai_detect_product_keys(question)
    asks_element_catalog = (
        "elemjegyz" in folded_question
        or "elemkinal" in folded_question
        or "elemvalasz" in folded_question
        or "elemei" in folded_question
        or ("elemek" in folded_question and any(term in folded_question for term in ("milyen", "sorold", "listaz", "teljes", "elerheto")))
        or (bool(product_keys) and "elem" in folded_question and "konyha" in folded_question)
    )
    if not asks_element_catalog:
        return None

    source_records = [
        record
        for record in knowledge.records
        if _divian_ai_is_elemjegyzek_source(record.source_name)
        and any(_divian_ai_fold_text(key) == "kod" for key, _ in record.fields)
    ]
    if not source_records:
        return None

    if product_keys:
        product_key = product_keys[0]
        product_label = _divian_ai_product_label(product_key) or product_key.capitalize()
        product_label_folded = _divian_ai_fold_text(product_label)
        filtered = [
            record
            for record in source_records
            if any(
                _divian_ai_fold_text(key) == "konyhak" and product_label_folded in _divian_ai_fold_text(value)
                for key, value in record.fields
            )
        ]
        if filtered:
            source_records = filtered
        elif product_key in {"kinga", "kata", "kira"}:
            filtered = [
                record
                for record in source_records
                if any(
                    _divian_ai_fold_text(key) == "konyhak" and product_label_folded in _divian_ai_fold_text(value)
                    for key, value in record.fields
                )
            ]
            if filtered:
                source_records = filtered
        elif product_key in {"doroti", "antonia", "laura", "zille", "anna"}:
            filtered = [
                record
                for record in source_records
                if any(
                    _divian_ai_fold_text(key) == "konyhacsoport" and "elemes konyh" in _divian_ai_fold_text(value)
                    for key, value in record.fields
                )
            ]
            if filtered:
                source_records = filtered

    if "also" in folded_question:
        filtered = [
            record
            for record in source_records
            if any(
                _divian_ai_fold_text(key) == "elemcsoport" and "also" in _divian_ai_fold_text(value)
                for key, value in record.fields
            )
        ]
        if filtered:
            source_records = filtered
    elif "felso" in folded_question:
        filtered = [
            record
            for record in source_records
            if any(
                _divian_ai_fold_text(key) == "elemcsoport" and "felso" in _divian_ai_fold_text(value)
                for key, value in record.fields
            )
        ]
        if filtered:
            source_records = filtered
    elif "oldaltakaro" in folded_question:
        filtered = [
            record
            for record in source_records
            if any(
                _divian_ai_fold_text(key) == "elemcsoport" and "oldaltakaro" in _divian_ai_fold_text(value)
                for key, value in record.fields
            )
        ]
        if filtered:
            source_records = filtered

    if not source_records:
        return None

    def field_value(record: DivianAIRecord, field_name: str) -> str:
        target = _divian_ai_fold_text(field_name)
        for key, value in record.fields:
            if _divian_ai_fold_text(key) == target:
                return value
        return ""

    unique_records: list[DivianAIRecord] = []
    seen_codes: set[tuple[str, str]] = set()
    for record in source_records:
        code = field_value(record, "Kód")
        group_name = field_value(record, "Elemcsoport") or "Elemek"
        code_key = (_divian_ai_fold_text(group_name), _divian_ai_fold_text(code))
        if code_key[1] and code_key in seen_codes:
            continue
        if code_key[1]:
            seen_codes.add(code_key)
        unique_records.append(record)

    grouped_records: dict[str, list[DivianAIRecord]] = {}
    for record in unique_records:
        group_name = field_value(record, "Elemcsoport") or "Elemek"
        grouped_records.setdefault(group_name, []).append(record)

    asks_list = any(term in folded_question for term in ("sorold", "listaz", "melyek", "milyen"))
    asks_count = any(term in folded_question for term in ("hany", "mennyi", "darab"))
    summary_parts = [f"{group_name} ({len(records)} db)" for group_name, records in grouped_records.items()]
    summary_text = ", ".join(summary_parts)
    subject_prefix = "az elemjegyzékből"
    if product_keys:
        product_label = _divian_ai_product_label(product_keys[0]) or product_keys[0].capitalize()
        subject_prefix = f"{product_label} konyhához az elemjegyzék alapján"

    if asks_count and not asks_list:
        answer = f"{evidence_label} {subject_prefix} {len(unique_records)} beolvasható tételt látok. Fő csoportok: {summary_text}."
        return {
            "ok": True,
            "answer": answer,
            "sources": ["elemjegyzek.pdf"],
        }

    if asks_list:
        group_lines: list[str] = []
        include_all_items = len(unique_records) <= 24
        for group_name, records in grouped_records.items():
            items: list[str] = []
            for record in records:
                name = field_value(record, "Megnevezés")
                code = field_value(record, "Kód")
                dimensions = field_value(record, "Méretek")
                item = name
                if code:
                    item += f" ({code}"
                    if dimensions:
                        item += f", {dimensions}"
                    item += ")"
                elif dimensions:
                    item += f" ({dimensions})"
                items.append(item)
                if not include_all_items and len(items) == 6:
                    break
            suffix = ""
            if not include_all_items and len(records) > len(items):
                suffix = f" + még {len(records) - len(items)} tétel"
            group_lines.append(f"- {group_name}: " + ", ".join(items) + suffix)

        answer = f"{evidence_label} {subject_prefix} {len(unique_records)} tételt látok. Fő csoportok: {summary_text}.\n" + "\n".join(group_lines)
        return {
            "ok": True,
            "answer": answer,
            "sources": ["elemjegyzek.pdf"],
        }

    answer = f"{evidence_label} {subject_prefix} {len(unique_records)} beolvasható tételt látok. Fő csoportok: {summary_text}."
    return {
        "ok": True,
        "answer": answer,
        "sources": ["elemjegyzek.pdf"],
    }


def _divian_ai_record_color_answer(
    question: str,
    knowledge: DivianAIKnowledgeCache,
    evidence_label: str = "A Divian források alapján",
) -> dict | None:
    if not _divian_ai_is_color_question(question):
        return None

    selected_records = _divian_ai_select_records(question, knowledge.records, limit=40)
    if not selected_records:
        return None

    preferred_source = _divian_ai_preferred_record_source(question, selected_records)
    if preferred_source:
        selected_records = [item for item in selected_records if item[1].source_name == preferred_source]

    subject_keys = _divian_ai_detect_subject_keys(question)
    material_subjects = {"butorlap", "front", "munkalap", "falipanel"} & set(subject_keys)
    colors: list[str] = []
    seen_colors: set[str] = set()
    sources: list[str] = []
    seen_sources: set[str] = set()

    for _, record in selected_records:
        display_field = _divian_ai_record_display_field(record, question)
        if display_field is None:
            continue

        key, value = display_field
        folded_key = _divian_ai_fold_text(key)
        candidate_values: list[str] = []
        if "butorlap" in subject_keys and "front" in folded_key and "butorlap" not in folded_key:
            continue
        if "front" in subject_keys and "butorlap" in folded_key and "front" not in folded_key:
            continue
        if "munkalap" in subject_keys and "munkalap" not in folded_key and "dekor" not in folded_key:
            continue

        if any(term in folded_key for term in ("szin", "dekor")):
            candidate_values.append(value)

        parts = [part.strip() for part in _divian_ai_normalize_text(value).split(" - ") if part.strip()]
        if len(parts) >= 2 and any(term in _divian_ai_fold_text(parts[0]) for term in ("butorlap", "munkalap", "front")):
            part_subject = _divian_ai_fold_text(parts[0])
            if "butorlap" in subject_keys and "butorlap" not in part_subject:
                continue
            if "front" in subject_keys and "front" not in part_subject:
                continue
            if "munkalap" in subject_keys and "munkalap" not in part_subject:
                continue
            candidate_values.append(parts[1])
        elif not material_subjects and any(term in folded_key for term in ("megnevezes", "leiras")):
            candidate_values.append(value)

        for candidate in candidate_values:
            normalized_candidate = _divian_ai_fold_text(candidate)
            if normalized_candidate in seen_colors or len(candidate) < 3:
                continue
            seen_colors.add(normalized_candidate)
            colors.append(candidate)
            if record.label not in seen_sources:
                seen_sources.add(record.label)
                sources.append(record.label)
            if len(colors) == 12:
                break
        if len(colors) == 12:
            break

    if not colors:
        return None

    return {
        "ok": True,
        "answer": f"{evidence_label} ezeket a színeket/dekorokat találtam:\n- " + "\n- ".join(colors),
        "sources": sources[:4],
    }


def _divian_ai_structured_answer(
    question: str,
    knowledge: DivianAIKnowledgeCache,
    evidence_label: str = "A Divian források alapján",
) -> dict | None:
    subject_keys = _divian_ai_detect_subject_keys(question)
    if not subject_keys:
        return None

    relevant_pages = _divian_ai_filter_pages(question, knowledge)
    source_labels: list[str] = []
    seen_sources: set[str] = set()

    if "garancia" in subject_keys:
        matches: list[str] = []
        for page in relevant_pages:
            page_matches: list[str] = []
            for index, line in enumerate(page.lines):
                folded_line = _divian_ai_fold_text(line)
                if "garancia" in folded_line:
                    for next_line in page.lines[index + 1 : index + 5]:
                        next_folded = _divian_ai_fold_text(next_line)
                        if "ev" in next_folded or "regisztracio" in next_folded or "ertekhatar" in next_folded:
                            page_matches.append(next_line.strip())
                elif "ev" in folded_line and ("regisztracio" in folded_line or "garancia" in folded_line):
                    page_matches.append(line.strip())

            for match in page_matches:
                if match not in matches:
                    matches.append(match)
            if page_matches and page.label not in seen_sources:
                seen_sources.add(page.label)
                source_labels.append(page.label)

        if matches:
            return {
                "ok": True,
                "answer": f"{evidence_label} a garancia:\n- " + "\n- ".join(matches[:3]),
                "sources": source_labels,
            }

    return None


def _divian_ai_sentence_answer(
    question: str,
    knowledge: DivianAIKnowledgeCache,
    selected_chunks: list[DivianAIChunk],
    evidence_label: str = "A Divian források alapján",
) -> tuple[str, list[str]] | None:
    focus_tokens = _divian_ai_focus_tokens(question)
    question_tokens = focus_tokens or _divian_ai_tokens(question)
    if not question_tokens:
        return None

    relevant_pages = _divian_ai_filter_pages(question, knowledge)
    scored_sentences: list[tuple[int, str, str]] = []
    product_keys = _divian_ai_detect_product_keys(question)
    subject_keys = _divian_ai_detect_subject_keys(question)
    minimum_overlap = 1 if product_keys else 2 if subject_keys else 1

    for page in relevant_pages:
        for line in page.lines:
            line = line.strip(" -")
            if len(line) < 6 or len(line) > 180:
                continue
            sentence_tokens = _divian_ai_tokens(line)
            overlap = question_tokens & sentence_tokens
            if not overlap:
                continue
            if len(overlap) < minimum_overlap and max((len(token) for token in overlap), default=0) < 7:
                continue

            score = len(overlap) * 5 + _divian_ai_source_affinity_score(question, page.source_name, page.title, page.label)
            if any(char.isdigit() for char in line):
                score += 2
            if "garancia" in _divian_ai_fold_text(question) and "garancia" in _divian_ai_fold_text(line):
                score += 4
            scored_sentences.append((score, line, page.label))

    if not scored_sentences:
        for chunk in selected_chunks:
            sentences = re.split(r"(?<=[.!?])\s+|\s{2,}", chunk.text)
            for sentence in sentences:
                sentence = sentence.strip(" -")
                if len(sentence) < 24 or len(sentence) > 220:
                    continue
                sentence_tokens = _divian_ai_tokens(sentence)
                overlap = question_tokens & sentence_tokens
                if not overlap:
                    continue
                if len(overlap) < minimum_overlap and max((len(token) for token in overlap), default=0) < 7:
                    continue

                score = len(overlap) * 5 + _divian_ai_source_affinity_score(question, chunk.source_name, chunk.label)
                for token in overlap:
                    score += min(sentence.lower().count(token), 2)
                scored_sentences.append((score, sentence, chunk.label))

    if not scored_sentences:
        return None

    scored_sentences.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
    answer_lines: list[str] = []
    source_labels: list[str] = []
    seen_sentences: set[str] = set()
    seen_sources: set[str] = set()

    for _, sentence, label in scored_sentences:
        normalized_sentence = sentence.strip()
        if normalized_sentence in seen_sentences:
            continue
        seen_sentences.add(normalized_sentence)
        answer_lines.append(f"- {normalized_sentence}")
        if label not in seen_sources:
            seen_sources.add(label)
            source_labels.append(label)
        if len(answer_lines) == 3:
            break

    if not answer_lines:
        return None

    strongest_score = scored_sentences[0][0]
    minimum_score = 10 if len(focus_tokens) >= 2 else 6
    if strongest_score < minimum_score:
        return None

    answer = f"{evidence_label}:\n" + "\n".join(answer_lines)
    return answer, source_labels


def _build_local_divian_ai_answer(
    question: str,
    knowledge: DivianAIKnowledgeCache,
    selected_chunks: list[DivianAIChunk],
    *,
    allow_profile_answers: bool = False,
    evidence_label: str = "A Divian források alapján",
    no_answer_message: str | None = None,
) -> dict:
    if allow_profile_answers:
        lineup_answer = _divian_ai_profile_lineup_answer(question)
        if lineup_answer is not None:
            return lineup_answer

        catalog_surface_answer = _divian_ai_catalog_surface_answer(question, knowledge, evidence_label=evidence_label)
        if catalog_surface_answer is not None:
            return catalog_surface_answer

        structured_catalog_material_answer = _divian_ai_structured_catalog_material_answer(question, knowledge, evidence_label=evidence_label)
        if structured_catalog_material_answer is not None:
            return structured_catalog_material_answer

        material_answer = _divian_ai_profile_material_answer(question)
        if material_answer is not None:
            return material_answer

        kitchen_answer = _divian_ai_profile_kitchen_answer(question)
        if kitchen_answer is not None:
            return kitchen_answer

    lighting_answer = _divian_ai_lighting_answer(question, knowledge, evidence_label=evidence_label)
    if lighting_answer is not None:
        return lighting_answer

    partner_catalog_answer = _divian_ai_partner_catalog_answer(question, knowledge, evidence_label=evidence_label)
    if partner_catalog_answer is not None:
        return partner_catalog_answer

    element_catalog_answer = _divian_ai_element_catalog_answer(question, knowledge, evidence_label=evidence_label)
    if element_catalog_answer is not None:
        return element_catalog_answer

    source_summary_answer = _divian_ai_source_summary_answer(question, knowledge, evidence_label=evidence_label)
    if source_summary_answer is not None:
        return source_summary_answer

    record_color_answer = _divian_ai_record_color_answer(question, knowledge, evidence_label=evidence_label)
    if record_color_answer is not None:
        return record_color_answer

    record_answer = _divian_ai_record_answer(question, knowledge)
    if record_answer is not None:
        return record_answer

    structured_answer = _divian_ai_structured_answer(question, knowledge, evidence_label=evidence_label)
    if structured_answer is not None:
        return structured_answer

    if _divian_ai_is_color_question(question):
        colors, sources = _divian_ai_extract_color_list(question, knowledge)
        if colors:
            answer = f"{evidence_label} ezek a színek szerepelnek:\n- " + "\n- ".join(colors)
            return {
                "ok": True,
                "answer": answer,
                "sources": sources,
            }

    sentence_answer = _divian_ai_sentence_answer(question, knowledge, selected_chunks, evidence_label=evidence_label)
    if sentence_answer:
        answer, sources = sentence_answer
        return {
            "ok": True,
            "answer": answer,
            "sources": sources,
        }

    if no_answer_message is None:
        return _divian_ai_no_confident_answer(question)

    return {
        "ok": True,
        "answer": no_answer_message,
        "sources": [],
    }


def _build_high_confidence_divian_ai_fallback(
    question: str,
    knowledge: DivianAIKnowledgeCache,
    selected_chunks: list[DivianAIChunk],
) -> dict | None:
    structured_catalog_material_answer = _divian_ai_structured_catalog_material_answer(
        question,
        knowledge,
        evidence_label="A Divian források alapján",
    )
    if structured_catalog_material_answer is not None:
        return structured_catalog_material_answer

    partner_offer_answer = _divian_ai_partner_offer_answer(question, knowledge)
    if partner_offer_answer is not None:
        return partner_offer_answer

    lighting_answer = _divian_ai_lighting_answer(question, knowledge)
    if lighting_answer is not None:
        return lighting_answer

    company_web_answer = _divian_ai_company_web_answer(question, knowledge)
    if company_web_answer is not None:
        return company_web_answer

    partner_catalog_answer = _divian_ai_partner_catalog_answer(question, knowledge, evidence_label="A Divian források alapján")
    if partner_catalog_answer is not None:
        return partner_catalog_answer

    element_catalog_answer = _divian_ai_element_catalog_answer(question, knowledge, evidence_label="A Divian források alapján")
    if element_catalog_answer is not None:
        return element_catalog_answer

    sentence_answer = _divian_ai_sentence_answer(question, knowledge, selected_chunks, evidence_label="A Divian források alapján")
    if sentence_answer:
        answer, sources = sentence_answer
        return {
            "ok": True,
            "answer": answer,
            "sources": sources,
        }

    return None


def _divian_ai_smalltalk_response(question: str) -> dict | None:
    folded_question = _divian_ai_fold_text(question).strip(" .!?")
    if not folded_question:
        return None

    if folded_question in {"szia", "hello", "hali", "helo", "jó reggelt", "jo reggelt", "jó napot", "jo napot", "jó estét", "jo estet"}:
        return {
            "ok": True,
            "answer": "Szia! Miben segíthetek?",
            "sources": [],
        }

    if folded_question in {"koszi", "köszi", "koszonom", "köszönöm"}:
        return {
            "ok": True,
            "answer": "Szívesen.",
            "sources": [],
        }

    if folded_question in {"viszlát", "viszlat", "szia!", "bye", "viszlatasra"}:
        return {
            "ok": True,
            "answer": "Rendben, ha kellek még, írj nyugodtan.",
            "sources": [],
        }

    return None


def _divian_ai_status_payload() -> dict:
    knowledge = _load_divian_ai_knowledge()
    registry_totals = _divian_ai_registry_totals()
    provider = _divian_ai_provider()
    provider_key = _divian_ai_provider_api_key(provider)
    provider_model = _divian_ai_provider_model(provider)
    openai_temporarily_blocked = DIVIAN_AI_OPENAI_DISABLED_UNTIL > time.time()
    openai_ready = (
        DIVIAN_AI_REMOTE_ENABLED
        and not openai_temporarily_blocked
        and ((provider in {"openai", "groq"} and OpenAI is not None) or provider == "gemini")
        and bool(provider_key)
    )
    knowledge_ready = bool(knowledge.chunks)

    blocked_reason = DIVIAN_AI_OPENAI_DISABLED_REASON.lower()

    if knowledge_ready and openai_ready:
        message = f"{len(knowledge.sources)} nyilvános webforrás betöltve, a Divian-AI {provider} modellen válaszol."
    elif knowledge_ready and not DIVIAN_AI_REMOTE_ENABLED:
        message = "A nyilvános webes források be vannak töltve, de a GPT válaszmotor ki van kapcsolva."
    elif knowledge_ready and openai_temporarily_blocked:
        if "quota" in blocked_reason:
            message = f"A nyilvános webes források be vannak töltve, de a {provider} free kerete most elfogyott."
        else:
            message = f"A nyilvános webes források be vannak töltve, de a {provider} válaszmotor jelenleg nem elérhető."
    elif knowledge_ready:
        message = f"A nyilvános webes források be vannak töltve, de a {provider} API még nincs készen."
    else:
        message = knowledge.errors[0] if knowledge.errors else "A nyilvános webes források még nem állnak készen."

    return {
        "ok": True,
        "knowledge_ready": knowledge_ready,
        "openai_ready": openai_ready,
        "provider": provider,
        "model": provider_model,
        "source_count": len(knowledge.sources),
        "uploaded_file_count": 0,
        "sources": knowledge.sources,
        "chunk_count": registry_totals["chunk_count"],
        "record_count": registry_totals["record_count"],
        "message": message,
    }


def _divian_ai_response_text(response) -> str:
    output_text = getattr(response, "output_text", "")
    if output_text:
        return str(output_text).strip()

    parts: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", "") or getattr(content, "value", "")
            if text:
                parts.append(str(text).strip())
    return "\n\n".join(part for part in parts if part).strip()


def _divian_ai_chat_completion_text(response) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    first_choice = choices[0]
    message = getattr(first_choice, "message", None)
    if message is None:
        return ""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            text = getattr(item, "text", None)
            if text:
                parts.append(str(text).strip())
            elif isinstance(item, dict) and item.get("text"):
                parts.append(str(item.get("text")).strip())
        return "\n\n".join(part for part in parts if part).strip()
    return str(content).strip()


def _divian_ai_gemini_response_text(payload: dict) -> str:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        return ""

    parts: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        content_parts = content.get("parts")
        if not isinstance(content_parts, list):
            continue
        for part in content_parts:
            if not isinstance(part, dict):
                continue
            text = str(part.get("text", "")).strip()
            if text:
                parts.append(text)
    return "\n\n".join(part for part in parts if part).strip()


def _divian_ai_call_gemini(
    *,
    api_key: str,
    model: str,
    instructions: str,
    history_items: list[dict[str, str]],
    prompt: str,
) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(model, safe='')}:generateContent"
    contents: list[dict[str, object]] = []
    for item in history_items[-6:]:
        role = "user" if item.get("role") == "user" else "model"
        contents.append(
            {
                "role": role,
                "parts": [{"text": str(item.get("content", ""))}],
            }
        )
    contents.append({"role": "user", "parts": [{"text": prompt}]})

    payload = {
        "system_instruction": {
            "parts": [{"text": instructions}],
        },
        "contents": contents,
        "generationConfig": {
            "temperature": 0.2,
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="ignore")
        try:
            error_payload = json.loads(response_body)
            error_message = str(error_payload.get("error", {}).get("message", "")).strip()
        except Exception:
            error_message = response_body.strip()
        raise RuntimeError(error_message or str(exc)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc.reason or exc)) from exc

    return _divian_ai_gemini_response_text(result)


def _divian_ai_is_company_question(question: str) -> bool:
    folded_question = _divian_ai_fold_text(question)
    return (
        _divian_ai_is_company_info_question(question)
        or _divian_ai_is_partner_offer_question(question)
        or bool(_divian_ai_detect_product_keys(question))
        or _divian_ai_is_partner_catalog_question(question)
        or bool(_divian_ai_detect_partner_category_keys(question))
        or bool(_divian_ai_detect_subject_keys(question))
        or any(term in folded_question for term in DIVIAN_AI_COMPANY_TERM_HINTS)
    )


def _divian_ai_source_is_official(source_name: str) -> bool:
    folded_source = _divian_ai_fold_text(source_name)
    return "divian hivatalos" in folded_source or "divian partner" in folded_source


def _divian_ai_source_is_catalog(source_name: str) -> bool:
    folded_source = _divian_ai_fold_text(source_name)
    return any(term in folded_source for term in ("katalogus", "katalógus", "kezikonyv", "kézikönyv"))


def _divian_ai_source_is_elemjegyzek(source_name: str) -> bool:
    return _divian_ai_is_elemjegyzek_source(source_name)


def _divian_ai_expand_search_query(question: str) -> str:
    parts: list[str] = [question]
    folded_question = _divian_ai_fold_text(question)

    for product_key in _divian_ai_detect_product_keys(question):
        parts.extend(DIVIAN_AI_PRODUCT_ALIASES.get(product_key, ()))
        product_label = _divian_ai_product_label(product_key)
        if product_label:
            parts.append(product_label)

    for subject_key in _divian_ai_detect_subject_keys(question):
        parts.extend(DIVIAN_AI_SUBJECT_ALIASES.get(subject_key, ()))

    for category_key in _divian_ai_detect_partner_category_keys(question):
        parts.extend(DIVIAN_AI_PARTNER_CATEGORY_ALIASES.get(category_key, ()))

    if "akcio" in folded_question or "akció" in question.lower():
        parts.extend(("akciók", "akciós termékek"))
    if "uj termek" in folded_question or "új termék" in question.lower():
        parts.extend(("új termékek", "új termék"))
    if "vilagit" in folded_question or "led" in folded_question:
        parts.extend(("konyhai világítás", "led", "led profil", "led szett"))
    if "elemjegy" in folded_question or "elem" in folded_question:
        parts.extend(("elemjegyzék", "elemkínálat", "elemek"))

    unique_parts: list[str] = []
    seen: set[str] = set()
    for part in parts:
        clean_part = _divian_ai_normalize_text(part)
        folded_part = _divian_ai_fold_text(clean_part)
        if not clean_part or not folded_part or folded_part in seen:
            continue
        seen.add(folded_part)
        unique_parts.append(clean_part)

    return "\n".join(unique_parts)


def _divian_ai_company_allowed_sources(question: str, knowledge: DivianAIKnowledgeCache) -> set[str]:
    folded_question = _divian_ai_fold_text(question)
    category_keys = _divian_ai_detect_partner_category_keys(question)
    product_keys = _divian_ai_detect_product_keys(question)
    subject_keys = set(_divian_ai_detect_subject_keys(question))
    allowed_sources: set[str] = set()

    if _divian_ai_is_partner_offer_question(question):
        for source_name in knowledge.sources:
            folded_source = _divian_ai_fold_text(source_name)
            if "divian partner" not in folded_source:
                continue
            if "akcio" in folded_question and "akcio" in folded_source:
                allowed_sources.add(source_name)
            if ("uj termek" in folded_question or "ujdonsag" in folded_question) and "uj termek" in folded_source:
                allowed_sources.add(source_name)
        if allowed_sources:
            return allowed_sources

    if _divian_ai_is_company_info_question(question):
        for source_name in knowledge.sources:
            if _divian_ai_source_is_official(source_name):
                allowed_sources.add(source_name)
        return allowed_sources

    asks_element_catalog = (
        "elemjegyz" in folded_question
        or "elemkinal" in folded_question
        or "elemvalasz" in folded_question
        or "elemei" in folded_question
        or ("elem" in folded_question and "konyha" in folded_question)
    )

    material_subjects = {"butorlap", "front", "munkalap", "falipanel"} & subject_keys
    if material_subjects:
        structured_catalog_sources = _divian_ai_preferred_structured_sources(knowledge, source_type="catalog", limit=3)
        if structured_catalog_sources:
            allowed_sources.update(structured_catalog_sources)
            return allowed_sources

    if asks_element_catalog:
        structured_elemjegyzek_sources = _divian_ai_preferred_structured_sources(knowledge, source_type="elemjegyzek", limit=2)
        if structured_elemjegyzek_sources:
            allowed_sources.update(structured_elemjegyzek_sources)
            if product_keys:
                allowed_sources.update(_divian_ai_preferred_structured_sources(knowledge, source_type="catalog", limit=2))
            return allowed_sources

    if product_keys:
        allowed_sources.update(_divian_ai_preferred_structured_sources(knowledge, source_type="catalog", limit=3))
        if asks_element_catalog:
            allowed_sources.update(_divian_ai_preferred_structured_sources(knowledge, source_type="elemjegyzek", limit=2))
        if allowed_sources:
            return allowed_sources

    if category_keys:
        for source_name in knowledge.sources:
            folded_source = _divian_ai_fold_text(source_name)
            if "divian partner" not in folded_source:
                continue

            matches_category = any(
                any(_divian_ai_partner_alias_match(folded_source, alias) for alias in DIVIAN_AI_PARTNER_CATEGORY_ALIASES.get(category_key, ()))
                for category_key in category_keys
            )

            if not matches_category and "vilagitas" in category_keys:
                matches_category = any(
                    term in folded_source
                    for term in ("led", "vilagitas", "kiegeszito", "kiegészítő", "paraelszivo", "páraelszívó")
                )

            if matches_category:
                allowed_sources.add(source_name)

        if allowed_sources:
            return allowed_sources

    for source_name in knowledge.sources:
        if _divian_ai_source_is_official(source_name) or _divian_ai_source_is_catalog(source_name):
            allowed_sources.add(source_name)

    if _divian_ai_source_affinity_score(question, "elemjegyzek") >= 10 or "elemjegy" in folded_question or "elem " in f"{folded_question} ":
        for source_name in knowledge.sources:
            if _divian_ai_source_is_elemjegyzek(source_name):
                allowed_sources.add(source_name)

    for source_name in knowledge.sources:
        if _divian_ai_source_affinity_score(question, source_name) >= 10:
            allowed_sources.add(source_name)

    return allowed_sources


def _divian_ai_record_context_block(record: DivianAIRecord) -> str:
    lines = [f"{key}: {value}" for key, value in record.fields if key.strip() and value.strip()]
    if not lines:
        return ""
    return f"[{record.label}]\n" + "\n".join(lines)


def _divian_ai_build_openai_context(
    question: str,
    knowledge: DivianAIKnowledgeCache,
) -> tuple[str, list[str]]:
    search_query = _divian_ai_expand_search_query(question)
    working_knowledge = knowledge
    if _divian_ai_is_company_question(question):
        allowed_sources = _divian_ai_company_allowed_sources(search_query, knowledge)
        filtered_knowledge = _divian_ai_filter_knowledge_sources(knowledge, allowed_sources)
        if filtered_knowledge.chunks:
            working_knowledge = filtered_knowledge

    selected_records = _divian_ai_select_records(search_query, working_knowledge.records, limit=10)
    selected_chunks = _divian_ai_select_chunks(search_query, working_knowledge.chunks, limit=12)

    source_labels: list[str] = []
    seen_labels: set[str] = set()
    context_blocks: list[str] = []
    remaining_chars = DIVIAN_AI_MAX_CONTEXT_CHARS

    for _, record in selected_records:
        block = _divian_ai_record_context_block(record)
        if not block or len(block) > remaining_chars:
            continue
        context_blocks.append(block)
        remaining_chars -= len(block)
        if record.label not in seen_labels:
            seen_labels.add(record.label)
            source_labels.append(record.label)

    for chunk in selected_chunks:
        block = f"[{chunk.label}]\n{chunk.text}"
        if len(block) > remaining_chars:
            continue
        context_blocks.append(block)
        remaining_chars -= len(block)
        if chunk.label not in seen_labels:
            seen_labels.add(chunk.label)
            source_labels.append(chunk.label)

    return "\n\n".join(context_blocks).strip(), source_labels


def _ask_divian_ai(question: str, history: object = None) -> dict:
    global DIVIAN_AI_OPENAI_DISABLED_REASON, DIVIAN_AI_OPENAI_DISABLED_UNTIL

    question = question.strip()
    if not question:
        return {"ok": False, "error": "Adj meg egy kérdést a Divian-AI számára."}

    if len(question) > DIVIAN_AI_MAX_QUESTION_CHARS:
        return {"ok": False, "error": f"A kérdés legfeljebb {DIVIAN_AI_MAX_QUESTION_CHARS} karakter lehet."}

    history_items = _divian_ai_sanitize_history(history)
    effective_question = _divian_ai_contextualize_question(question, history_items)
    is_company_question = _divian_ai_is_company_question(effective_question)

    if not is_company_question:
        smalltalk_response = _divian_ai_smalltalk_response(effective_question)
        if smalltalk_response is not None:
            return smalltalk_response

    knowledge: DivianAIKnowledgeCache | None = None
    context_text = ""
    source_labels: list[str] = []
    selected_chunks: list[DivianAIChunk] = []

    if is_company_question:
        knowledge = _load_divian_ai_knowledge()
        if not knowledge.chunks:
            message = knowledge.errors[0] if knowledge.errors else "Még nincs elérhető nyilvános webforrás."
            return {"ok": False, "error": message}
        context_text, source_labels = _divian_ai_build_openai_context(effective_question, knowledge)
        selected_chunks = _divian_ai_select_chunks(effective_question, knowledge.chunks)

        direct_company_answer = _divian_ai_company_web_answer(effective_question, knowledge)
        if direct_company_answer is not None:
            return direct_company_answer

        direct_profile_lineup = _divian_ai_profile_lineup_answer(effective_question)
        if direct_profile_lineup is not None:
            return direct_profile_lineup

        direct_catalog_surface_answer = _divian_ai_catalog_surface_answer(effective_question, knowledge, evidence_label="A Divian források alapján")
        if direct_catalog_surface_answer is not None:
            return direct_catalog_surface_answer

        direct_structured_catalog_material = _divian_ai_structured_catalog_material_answer(
            effective_question,
            knowledge,
            evidence_label="A Divian források alapján",
        )
        if direct_structured_catalog_material is not None:
            return direct_structured_catalog_material

        direct_profile_material = _divian_ai_profile_material_answer(effective_question)
        if direct_profile_material is not None:
            return direct_profile_material

        direct_profile_kitchen = _divian_ai_profile_kitchen_answer(effective_question)
        if direct_profile_kitchen is not None:
            return direct_profile_kitchen

        direct_offer_answer = _divian_ai_partner_offer_answer(effective_question, knowledge, evidence_label="A Divian források alapján")
        if direct_offer_answer is not None:
            return direct_offer_answer

        direct_lighting_answer = _divian_ai_lighting_answer(effective_question, knowledge, evidence_label="A Divian források alapján")
        if direct_lighting_answer is not None:
            return direct_lighting_answer

        direct_element_answer = _divian_ai_element_catalog_answer(effective_question, knowledge, evidence_label="A Divian források alapján")
        if direct_element_answer is not None:
            return direct_element_answer

        if _divian_ai_is_partner_catalog_question(effective_question):
            direct_catalog_answer = _divian_ai_partner_catalog_answer(effective_question, knowledge, evidence_label="A Divian források alapján")
            if direct_catalog_answer is not None:
                return direct_catalog_answer

    if is_company_question and not context_text:
        return {
            "ok": True,
            "answer": (
                "Erre most nincs elég biztos nyilvános céges forrásom a weben. "
                "Inkább nem találgatok."
            ),
            "sources": [],
        }

    if not DIVIAN_AI_REMOTE_ENABLED:
        return {
            "ok": False,
            "error": "A Divian-AI GPT válaszmotor jelenleg ki van kapcsolva.",
        }

    provider = _divian_ai_provider()
    model_name = _divian_ai_provider_model(provider)
    api_key = _divian_ai_provider_api_key(provider)
    if not api_key:
        return {
            "ok": False,
            "error": f"Hiányzik a {provider.upper()} API kulcs, ezért a Divian-AI nem tud ezen a provideren válaszolni.",
        }

    cache_key = _divian_ai_response_cache_key(
        provider=provider,
        model=model_name,
        question=question,
        effective_question=effective_question,
        is_company_question=is_company_question,
        history_items=history_items,
        context_text=context_text,
    )
    cached_response = _divian_ai_cached_response(cache_key)
    if cached_response is not None:
        if is_company_question and source_labels:
            cached_response["sources"] = source_labels
        return cached_response

    if DIVIAN_AI_OPENAI_DISABLED_UNTIL > time.time():
        if is_company_question:
            fallback = _build_high_confidence_divian_ai_fallback(effective_question, knowledge, selected_chunks)
            if fallback is not None:
                fallback["answer"] += f"\n\nMegjegyzés: a {provider} most átmenetileg nem elérhető, ezért ezt a választ a nyilvános webes forrásokból állítottam össze."
                return fallback
        return {
            "ok": False,
            "error": f"A {provider} válaszmotor jelenleg nem elérhető. Ellenőrizni kell a kvótát vagy a billinget.",
        }
    if DIVIAN_AI_OPENAI_DISABLED_REASON:
        DIVIAN_AI_OPENAI_DISABLED_REASON = ""
        DIVIAN_AI_OPENAI_DISABLED_UNTIL = 0.0

    instructions = (
        "Te vagy Divian-AI, a Divian belső céges asszisztense. "
        "Általános kérdéseknél természetesen, intelligensen és röviden válaszolj magyarul, mint egy modern chat asszisztens. "
        "Ha a kérdés céges vagy Divian-specifikus, akkor csak a megadott céges forrásokra támaszkodhatsz. "
        "Céges kérdésnél ha a forrás nem elég biztos, ezt mondd ki egyértelműen, és ne találj ki adatot. "
        "Ne ismételd meg automatikusan az előző válasz témáját, ha az új kérdés önálló. "
        "A forrásokat nem kell a válasz végére kiírnod, azt a felület külön kezeli."
    )
    history_text = ""
    if history_items:
        history_lines = [
            f"{'Felhasználó' if item['role'] == 'user' else 'Divian-AI'}: {item['content']}"
            for item in history_items[-6:]
        ]
        history_text = "Aktuális beszélgetés:\n" + "\n".join(history_lines) + "\n\n"

    company_mode = "igen" if is_company_question else "nem"
    context_section = context_text if context_text else "Nincs céges kontextus megadva ehhez a kérdéshez."
    prompt = (
        f"{history_text}"
        f"Aktuális kérdés:\n{question}\n\n"
        f"Értelmezett kérdés:\n{effective_question}\n\n"
        f"Céges kérdés:\n{company_mode}\n\n"
        f"Céges webes forrásrészletek:\n{context_section}\n\n"
        "Válaszolj közvetlenül a kérdésre. "
        "Ha céges kérdésre nincs elég biztos adat, ezt mondd ki egyértelműen."
    )

    try:
        if provider == "gemini":
            answer = _divian_ai_call_gemini(
                api_key=api_key,
                model=model_name,
                instructions=instructions,
                history_items=history_items,
                prompt=prompt,
            )
        else:
            if OpenAI is None:
                return {
                    "ok": False,
                    "error": f"Az OpenAI kompatibilis kliens nincs telepítve, ezért a Divian-AI nem tud {provider} alapon válaszolni.",
                }
            base_url = _divian_ai_provider_base_url(provider)
            client = OpenAI(api_key=api_key, timeout=8.0, base_url=base_url)
            if provider == "groq":
                messages = [{"role": "system", "content": instructions}]
                for item in history_items[-6:]:
                    role = "user" if item.get("role") == "user" else "assistant"
                    messages.append({"role": role, "content": str(item.get("content", ""))})
                messages.append({"role": "user", "content": prompt})
                response = client.chat.completions.create(
                    model=model_name,
                    temperature=0.2,
                    messages=messages,
                )
                answer = _divian_ai_chat_completion_text(response)
            else:
                response = client.responses.create(
                    model=model_name,
                    instructions=instructions,
                    input=prompt,
                )
                answer = _divian_ai_response_text(response)
    except Exception as exc:
        error_message = str(exc)
        lowered_message = error_message.lower()
        if "insufficient_quota" in lowered_message or "429" in lowered_message or "quota" in lowered_message:
            DIVIAN_AI_OPENAI_DISABLED_REASON = error_message
            DIVIAN_AI_OPENAI_DISABLED_UNTIL = time.time() + DIVIAN_AI_OPENAI_RETRY_SECONDS
            if is_company_question:
                fallback = _build_high_confidence_divian_ai_fallback(effective_question, knowledge, selected_chunks)
                if fallback is not None:
                    fallback["answer"] += f"\n\nMegjegyzés: a {provider} free kerete most elfogyott, ezért ezt a választ a nyilvános webes forrásokból állítottam össze."
                    return fallback
        if is_company_question:
            fallback = _build_high_confidence_divian_ai_fallback(effective_question, knowledge, selected_chunks)
            if fallback is not None:
                fallback["answer"] += f"\n\nMegjegyzés: a {provider} most átmenetileg nem válaszolt, ezért ezt a választ a nyilvános webes forrásokból állítottam össze."
                return fallback
        return {
            "ok": False,
            "error": f"A Divian-AI hívás nem sikerült: {error_message}",
        }

    if not answer:
        return {
            "ok": False,
            "error": "A GPT válaszmotor üres választ adott vissza.",
        }

    result = {
        "ok": True,
        "answer": answer,
        "sources": source_labels if is_company_question else [],
    }
    _divian_ai_store_cached_response(cache_key, answer, result["sources"])
    return result


def _normalize_path(raw_path: str) -> str:
    path = urllib.parse.urlparse(raw_path).path or "/"
    if path != "/" and path.endswith("/"):
        return path.rstrip("/")
    return path


def _load_static_asset(path: str) -> tuple[bytes, str] | None:
    asset = STATIC_ASSETS.get(path)
    if asset is None:
        return None

    file_name, content_type = asset
    file_path = BASE_DIR / file_name
    if not file_path.exists():
        return None

    return file_path.read_bytes(), content_type


def _extract_uploaded_file_parts(headers, body: bytes) -> list[tuple[str, str, bytes]]:
    content_type = headers.get("Content-Type", "")
    boundary_match = re.search(r'boundary="?([^";]+)"?', content_type)
    if "multipart/form-data" not in content_type or not boundary_match:
        return []

    boundary = boundary_match.group(1).encode()
    parts: list[tuple[str, str, bytes]] = []
    for part in body.split(b"--" + boundary):
        header, _, payload = part.partition(b"\r\n\r\n")
        if not payload:
            continue

        payload = payload.rsplit(b"\r\n", 1)[0]
        field_match = re.search(br'name="([^"]+)"', header)
        if not field_match:
            continue

        field_name = field_match.group(1).decode(errors="ignore")
        name_match = re.search(br'filename="([^"]+)"', header)
        file_name = name_match.group(1).decode(errors="ignore") if name_match else ""
        if file_name and payload:
            parts.append((field_name, file_name, payload))

    return parts


def _extract_uploaded_files(headers, body: bytes) -> dict[str, tuple[str, bytes]]:
    files: dict[str, tuple[str, bytes]] = {}
    for field_name, file_name, payload in _extract_uploaded_file_parts(headers, body):
        if field_name not in files:
            files[field_name] = (file_name, payload)
    return files


def _parse_urlencoded_body(body: bytes) -> dict[str, str]:
    try:
        payload = urllib.parse.parse_qs(body.decode("utf-8"), keep_blank_values=True)
    except UnicodeDecodeError:
        payload = urllib.parse.parse_qs(body.decode("latin1"), keep_blank_values=True)
    return {key: values[0] for key, values in payload.items() if values}


def _store_divian_ai_uploads(uploaded_files: list[tuple[str, bytes]]) -> tuple[list[dict], list[str]]:
    DIVIAN_AI_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    manifest_entries = _divian_ai_read_upload_manifest()
    accepted_entries: list[dict] = []
    warnings: list[str] = []

    for file_name, payload in uploaded_files:
        original_name = Path(file_name).name.strip()
        if not original_name:
            warnings.append("Egy feltöltött fájl neve hiányzott, ezért kimaradt.")
            continue

        suffix = Path(original_name).suffix.lower()
        if suffix not in DIVIAN_AI_SUPPORTED_EXTENSIONS:
            warnings.append(f"{original_name}: ez a formátum még nem támogatott.")
            continue

        safe_name = _divian_ai_safe_filename(original_name)
        stored_name = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}-{safe_name}"
        stored_path = DIVIAN_AI_UPLOAD_DIR / stored_name
        stored_path.write_bytes(payload)

        entry = {
            "id": uuid.uuid4().hex[:12],
            "stored_name": stored_name,
            "original_name": original_name,
            "uploaded_at": datetime.now().isoformat(timespec="seconds"),
            "size_bytes": len(payload),
            "kind": _divian_ai_doc_kind(stored_path),
            "status": "pending",
            "note": "",
        }
        manifest_entries.append(entry)
        accepted_entries.append(entry)

    _divian_ai_write_upload_manifest(manifest_entries)
    global DIVIAN_AI_CACHE
    DIVIAN_AI_CACHE = DivianAIKnowledgeCache()
    knowledge = _load_divian_ai_knowledge()
    warnings.extend(knowledge.errors[:3])
    return accepted_entries, warnings


def _extract_uploaded_pdf(headers, body: bytes) -> tuple[str | None, bytes | None]:
    files = _extract_uploaded_files(headers, body)
    invoice_file = files.get("invoice_file")
    if invoice_file is None:
        return None, None

    return invoice_file


def _is_valid_job_id(job_id: str) -> bool:
    return bool(re.fullmatch(r"[a-f0-9]{10,32}", job_id))


def _nettfront_job_dir(job_id: str) -> Path | None:
    if not _is_valid_job_id(job_id):
        return None
    return NETTFRONT_RUNTIME_DIR / job_id


def _write_nettfront_job(artifacts) -> tuple[str, dict]:
    job_id = uuid.uuid4().hex[:12]
    job_dir = NETTFRONT_RUNTIME_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    (job_dir / "invoice-output.csv").write_bytes(artifacts.invoice_csv)
    (job_dir / "rendeles_sima.csv").write_bytes(artifacts.procurement_csv)
    if artifacts.compare_workbook is not None:
        (job_dir / "compare-output.xlsx").write_bytes(artifacts.compare_workbook)

    metadata = {
        "job_id": job_id,
        "invoice_row_count": len(artifacts.invoice_rows),
        "order_row_count": artifacts.order_row_count,
        "has_compare": artifacts.compare_workbook is not None,
        "missing_codes": artifacts.missing_codes,
    }
    (job_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    (job_dir / "nettfront-output.zip").write_bytes(create_bundle_zip(job_dir, include_compare=metadata["has_compare"]))
    return job_id, metadata


def _read_nettfront_metadata(job_id: str) -> tuple[Path | None, dict | None]:
    job_dir = _nettfront_job_dir(job_id)
    if job_dir is None or not job_dir.exists():
        return None, None

    metadata_path = job_dir / "metadata.json"
    if not metadata_path.exists():
        return None, None

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return job_dir, metadata


def _nettfront_download_payload(job_id: str, artifact: str) -> tuple[bytes, str, str] | None:
    job_dir, metadata = _read_nettfront_metadata(job_id)
    if job_dir is None or metadata is None:
        return None

    artifact_map = {
        "invoice-csv": ("invoice-output.csv", "text/csv; charset=utf-8", "invoice-output.csv"),
        "procurement-csv": ("rendeles_sima.csv", "text/csv; charset=utf-8", "rendeles_sima.csv"),
        "bundle-zip": ("nettfront-output.zip", "application/zip", "nettfront-output.zip"),
    }

    if artifact == "compare-xlsx":
        if not metadata.get("has_compare"):
            return None
        file_path = job_dir / "compare-output.xlsx"
        if not file_path.exists():
            return None
        return (
            file_path.read_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "compare-output.xlsx",
        )

    config = artifact_map.get(artifact)
    if config is None:
        return None

    file_name, content_type, download_name = config
    file_path = job_dir / file_name
    if not file_path.exists():
        return None
    return file_path.read_bytes(), content_type, download_name


def _job_runtime_dir(kind: str) -> Path:
    if kind == "procurement":
        return NETTFRONT_PROCUREMENT_RUNTIME_DIR
    if kind == "compare":
        return NETTFRONT_COMPARE_RUNTIME_DIR
    if kind == "order":
        return NETTFRONT_ORDER_RUNTIME_DIR
    raise ValueError(f"Ismeretlen NettFront job típus: {kind}")


def _write_nettfront_job_files(kind: str, files: dict[str, bytes], metadata: dict, bundle_name: str) -> tuple[str, dict]:
    job_id = uuid.uuid4().hex[:12]
    job_dir = _job_runtime_dir(kind) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        **metadata,
        "job_id": job_id,
        "job_type": kind,
        "bundle_name": bundle_name,
    }

    for file_name, payload in files.items():
        (job_dir / file_name).write_bytes(payload)

    (job_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    bundle_files = list(files.keys()) + ["metadata.json"]
    (job_dir / bundle_name).write_bytes(create_bundle_archive(job_dir, bundle_files))
    return job_id, metadata


def _persist_procurement_job(job_dir: Path, metadata: dict, artifacts, uploaded_parts_name: str = "", uploaded_parts_bytes: bytes | None = None) -> dict:
    (job_dir / "invoice-output.csv").write_bytes(artifacts.invoice_csv)
    (job_dir / "rendeles_sima.csv").write_bytes(artifacts.procurement_csv)

    updated_metadata = {
        **metadata,
        "invoice_row_count": len(artifacts.invoice_rows),
        "missing_codes": artifacts.missing_codes,
    }

    if uploaded_parts_name and uploaded_parts_bytes is not None:
        suffix = Path(uploaded_parts_name).suffix.lower() or ".xlsx"
        stored_name = f"alkatreszlista{suffix}"
        (job_dir / stored_name).write_bytes(uploaded_parts_bytes)
        updated_metadata["uploaded_parts_name"] = uploaded_parts_name
        updated_metadata["uploaded_parts_file"] = stored_name

    metadata_path = job_dir / "metadata.json"
    metadata_path.write_text(json.dumps(updated_metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    bundle_name = updated_metadata.get("bundle_name", "procurement-output.zip")
    bundle_files = ["invoice-output.csv", "rendeles_sima.csv", "metadata.json"]
    (job_dir / bundle_name).write_bytes(create_bundle_archive(job_dir, bundle_files))
    return updated_metadata


def _write_procurement_job(
    artifacts,
    source_invoice_name: str,
    source_invoice_bytes: bytes,
    uploaded_parts_name: str = "",
    uploaded_parts_bytes: bytes | None = None,
) -> tuple[str, dict]:
    job_id = uuid.uuid4().hex[:12]
    job_dir = _job_runtime_dir("procurement") / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    source_invoice_file = "source-invoice.pdf"
    (job_dir / source_invoice_file).write_bytes(source_invoice_bytes)

    metadata = {
        "job_id": job_id,
        "job_type": "procurement",
        "bundle_name": "procurement-output.zip",
        "source_invoice_name": source_invoice_name,
        "source_invoice_file": source_invoice_file,
    }
    metadata = _persist_procurement_job(
        job_dir,
        metadata,
        artifacts,
        uploaded_parts_name=uploaded_parts_name,
        uploaded_parts_bytes=uploaded_parts_bytes,
    )
    return job_id, metadata


def _write_compare_job(artifacts) -> tuple[str, dict]:
    return _write_nettfront_job_files(
        "compare",
        {
            "invoice-output.csv": artifacts.invoice_csv,
            "compare-output.xlsx": artifacts.compare_workbook,
        },
        {
            "invoice_row_count": len(artifacts.invoice_rows),
            "order_row_count": artifacts.order_row_count,
        },
        "compare-output.zip",
    )


def _read_nettfront_job(kind: str, job_id: str) -> tuple[Path | None, dict | None]:
    if not _is_valid_job_id(job_id):
        return None, None

    job_dir = _job_runtime_dir(kind) / job_id
    if not job_dir.exists():
        return None, None

    metadata_path = job_dir / "metadata.json"
    if not metadata_path.exists():
        return None, None

    return job_dir, json.loads(metadata_path.read_text(encoding="utf-8"))


def _download_payload_for_kind(kind: str, job_id: str, artifact: str) -> tuple[bytes, str, str] | None:
    job_dir, metadata = _read_nettfront_job(kind, job_id)
    if job_dir is None or metadata is None:
        return None

    if kind == "procurement":
        artifact_map = {
            "invoice-csv": ("invoice-output.csv", "text/csv; charset=utf-8", "invoice-output.csv"),
            "procurement-csv": ("rendeles_sima.csv", "text/csv; charset=utf-8", "rendeles_sima.csv"),
            "bundle-zip": (metadata.get("bundle_name", "procurement-output.zip"), "application/zip", metadata.get("bundle_name", "procurement-output.zip")),
        }
    elif kind == "compare":
        artifact_map = {
            "invoice-csv": ("invoice-output.csv", "text/csv; charset=utf-8", "invoice-output.csv"),
            "compare-xlsx": ("compare-output.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "compare-output.xlsx"),
            "bundle-zip": (metadata.get("bundle_name", "compare-output.zip"), "application/zip", metadata.get("bundle_name", "compare-output.zip")),
        }
    else:
        source_stock_file = str(metadata.get("source_stock_file", "")).strip()
        source_stock_name = str(metadata.get("source_stock_name", source_stock_file)).strip() or source_stock_file
        guessed_stock_type = mimetypes.guess_type(source_stock_name)[0] or "application/octet-stream"
        artifact_map = {
            "suggestion-xlsx": (
                "rendelesi-javaslat.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "rendelesi-javaslat.xlsx",
            ),
            "approved-xlsx": (
                metadata.get("approved_file", "rendeles-jovahagyott.xlsx"),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                metadata.get("approved_file", "rendeles-jovahagyott.xlsx"),
            ),
            "import-csv": (
                metadata.get("import_file", "rendeles_sima.csv"),
                "text/csv; charset=utf-8",
                metadata.get("import_file", "rendeles_sima.csv"),
            ),
            "source-stock": (
                source_stock_file,
                guessed_stock_type,
                source_stock_name,
            ),
            "bundle-zip": (
                metadata.get("bundle_name", "nettfront-rendeles-output.zip"),
                "application/zip",
                metadata.get("bundle_name", "nettfront-rendeles-output.zip"),
            ),
        }

    config = artifact_map.get(artifact)
    if config is None:
        return None

    file_name, content_type, download_name = config
    file_path = job_dir / file_name
    if not file_path.exists():
        return None
    return file_path.read_bytes(), content_type, download_name


def _build_invoice_response(file_name: str, file_data: bytes) -> tuple[int, bytes, str, dict[str, str]]:
    chunks = split_pdf_by_invoice(file_data)
    if len(chunks) <= 1:
        chunk = chunks[0]
        parsed = parse_invoice_data(chunk.text)
        source_label = file_name
        if chunk.page_from != chunk.page_to:
            source_label = f"{file_name} (oldalak: {chunk.page_from}-{chunk.page_to})"
        printable_html = create_printable_html(parsed, source_filename=source_label)
        return 200, printable_html, "text/html; charset=utf-8", {"Cache-Control": "no-store"}

    zip_buffer = io.BytesIO()
    summary_lines = [
        f"Forrás PDF: {file_name}",
        f"Felismert számlák: {len(chunks)}",
        "",
    ]

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for idx, chunk in enumerate(chunks, start=1):
            parsed = parse_invoice_data(chunk.text)
            invoice_no = parsed.invoice_number or chunk.invoice_hint or f"invoice_{idx:02d}"
            safe_no = re.sub(r"[^A-Za-z0-9._-]+", "_", invoice_no).strip("._-")
            if not safe_no:
                safe_no = f"invoice_{idx:02d}"

            page_span = f"{chunk.page_from}" if chunk.page_from == chunk.page_to else f"{chunk.page_from}-{chunk.page_to}"
            source_label = f"{file_name} (oldalak: {page_span})"
            html_bytes = create_printable_html(parsed, source_filename=source_label)
            html_name = f"{idx:02d}_{safe_no}_nyomtathato.html"
            archive.writestr(html_name, html_bytes)
            summary_lines.append(f"{idx}. számla: {invoice_no} (oldalak: {page_span}) -> {html_name}")

        archive.writestr("00_lista.txt", "\n".join(summary_lines))

    payload = zip_buffer.getvalue()
    zip_name = f"{re.sub(r'[^A-Za-z0-9._-]+', '_', file_name.rsplit('.', 1)[0])}_szamlak.zip"
    quoted_name = urllib.parse.quote(zip_name)
    return 200, payload, "application/zip", {
        "Cache-Control": "no-store",
        "Content-Disposition": f"attachment; filename*=UTF-8''{quoted_name}",
    }


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


class InvoiceHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = _normalize_path(self.path)
        if path == DEV_RELOAD_ROUTE:
            self.respond_dev_reload_stream()
            return

        if path == DIVIAN_AI_STATUS_ROUTE:
            self.respond_json(200, _divian_ai_status_payload())
            return

        if path == APP_ROUTE:
            body = render_form()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == NETTFRONT_ROUTE:
            body = render_nettfront_hub()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == NETTFRONT_PROCUREMENT_ROUTE:
            body = render_nettfront_procurement_form()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == NETTFRONT_COMPARE_ROUTE:
            body = render_nettfront_compare_form()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == NETTFRONT_ORDER_ROUTE:
            body = render_nettfront_order_form()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == MANUFACTURING_ROUTE:
            query = _manufacturing_query_params(self.path)
            body = render_manufacturing_module(production_number=query.get("production", ""))
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == VACATION_CALENDAR_ROUTE:
            query = _vacation_query_params(self.path)
            body = render_vacation_calendar(
                month_value=query.get("month", ""),
                edit_department_id=_vacation_parse_int(query.get("edit_department", "")),
                edit_employee_id=_vacation_parse_int(query.get("edit_employee", "")),
                edit_leave_id=_vacation_parse_int(query.get("edit_leave", "")),
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == DIVIAN_AI_KNOWLEDGE_ROUTE or path.startswith(DIVIAN_AI_KNOWLEDGE_FILE_PREFIX + "/"):
            self.send_error(404)
            return

        if path.startswith(NETTFRONT_PROCUREMENT_DOWNLOAD_PREFIX + "/"):
            tail = path[len(NETTFRONT_PROCUREMENT_DOWNLOAD_PREFIX) + 1 :]
            job_id, _, artifact = tail.partition("/")
            payload = _download_payload_for_kind("procurement", job_id, artifact)
            if not payload:
                self.send_error(404)
                return

            body, content_type, download_name = payload
            quoted_name = urllib.parse.quote(download_name)
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quoted_name}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith(NETTFRONT_COMPARE_DOWNLOAD_PREFIX + "/"):
            tail = path[len(NETTFRONT_COMPARE_DOWNLOAD_PREFIX) + 1 :]
            job_id, _, artifact = tail.partition("/")
            payload = _download_payload_for_kind("compare", job_id, artifact)
            if not payload:
                self.send_error(404)
                return

            body, content_type, download_name = payload
            quoted_name = urllib.parse.quote(download_name)
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quoted_name}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith(NETTFRONT_ORDER_DOWNLOAD_PREFIX + "/"):
            tail = path[len(NETTFRONT_ORDER_DOWNLOAD_PREFIX) + 1 :]
            job_id, _, artifact = tail.partition("/")
            payload = _download_payload_for_kind("order", job_id, artifact)
            if not payload:
                self.send_error(404)
                return

            body, content_type, download_name = payload
            quoted_name = urllib.parse.quote(download_name)
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quoted_name}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        asset = _load_static_asset(path)
        if asset is None:
            self.send_error(404)
            return

        body, content_type = asset
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_dev_reload_stream(self):
        payload = json.dumps({"token": _dev_reload_token()}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            self.wfile.write(b"retry: 1000\n")
            self.wfile.write(b"event: reload\n")
            self.wfile.write(b"data: ")
            self.wfile.write(payload)
            self.wfile.write(b"\n\n")
            self.wfile.flush()

            while True:
                time.sleep(DEV_EVENT_HEARTBEAT_SECONDS)
                self.wfile.write(b": keep-alive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_POST(self):
        path = _normalize_path(self.path)
        if path == MANUFACTURING_STATE_ROUTE:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            try:
                payload = json.loads(raw_body.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self.respond_json(400, {"ok": False, "error": "Hibás JSON kérés."})
                return

            production_number = _manufacturing_normalize_number(payload.get("production_number", ""))
            row_id = str(payload.get("row_id", "")).strip()
            state = str(payload.get("state", "")).strip().lower()

            if not production_number:
                self.respond_json(400, {"ok": False, "error": "Hiányzik a gyártási szám."})
                return
            if not row_id:
                self.respond_json(400, {"ok": False, "error": "Hiányzik a sorazonosító."})
                return
            if state not in {"green", "red", "clear", "none", ""}:
                self.respond_json(400, {"ok": False, "error": "Érvénytelen sorállapot."})
                return

            try:
                current_state = save_selection_state(MANUFACTURING_RUNTIME_DIR, production_number, row_id, state)
            except Exception as exc:
                self.respond_json(500, {"ok": False, "error": f"A mentés nem sikerült: {exc}"})
                return

            self.respond_json(
                200,
                {
                    "ok": True,
                    "production_number": production_number,
                    "row_id": row_id,
                    "state": current_state.get(row_id, ""),
                },
            )
            return

        if path == DIVIAN_AI_CHAT_ROUTE:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            try:
                payload = json.loads(raw_body.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self.respond_json(400, {"ok": False, "error": "Hibás JSON kérés."})
                return

            question = str(payload.get("question", "")).strip()
            result = _ask_divian_ai(question, payload.get("history"))
            status_code = 200 if result.get("ok") else 400
            self.respond_json(status_code, result)
            return

        if path == DIVIAN_AI_KNOWLEDGE_PROCESS_ROUTE or path.startswith(DIVIAN_AI_KNOWLEDGE_DELETE_PREFIX + "/"):
            self.send_error(404)
            return

        if path == VACATION_CALENDAR_DEPARTMENT_SAVE_ROUTE:
            raw_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            form_data = _vacation_parse_form(raw_body)
            success, message = _vacation_save_department(form_data)
            body = render_vacation_calendar(
                month_value=_vacation_form_value(form_data, "return_month"),
                message=message,
                success=success,
                edit_department_id=None if success else _vacation_parse_int(_vacation_form_value(form_data, "department_id")),
                department_draft=None
                if success
                else {
                    "id": _vacation_form_value(form_data, "department_id"),
                    "name": _vacation_form_value(form_data, "name"),
                    "max_absent": _vacation_form_value(form_data, "max_absent") or "1",
                },
            )
            self.send_response(200 if success else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == VACATION_CALENDAR_DEPARTMENT_DELETE_ROUTE:
            raw_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            form_data = _vacation_parse_form(raw_body)
            success, message = _vacation_delete_department(form_data)
            body = render_vacation_calendar(
                month_value=_vacation_form_value(form_data, "return_month"),
                message=message,
                success=success,
            )
            self.send_response(200 if success else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == VACATION_CALENDAR_EMPLOYEE_SAVE_ROUTE:
            raw_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            form_data = _vacation_parse_form(raw_body)
            success, message = _vacation_save_employee(form_data)
            body = render_vacation_calendar(
                month_value=_vacation_form_value(form_data, "return_month"),
                message=message,
                success=success,
                edit_employee_id=None if success else _vacation_parse_int(_vacation_form_value(form_data, "employee_id")),
                employee_draft=None
                if success
                else {
                    "id": _vacation_form_value(form_data, "employee_id"),
                    "name": _vacation_form_value(form_data, "name"),
                    "department_ids": [
                        department_id
                        for raw_value in _vacation_form_values(form_data, "department_ids")
                        for department_id in [_vacation_parse_int(raw_value)]
                        if department_id is not None
                    ],
                },
            )
            self.send_response(200 if success else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == VACATION_CALENDAR_EMPLOYEE_DELETE_ROUTE:
            raw_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            form_data = _vacation_parse_form(raw_body)
            success, message = _vacation_delete_employee(form_data)
            body = render_vacation_calendar(
                month_value=_vacation_form_value(form_data, "return_month"),
                message=message,
                success=success,
            )
            self.send_response(200 if success else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == VACATION_CALENDAR_LEAVE_SAVE_ROUTE:
            raw_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            form_data = _vacation_parse_form(raw_body)
            success, message = _vacation_save_leave(form_data)
            body = render_vacation_calendar(
                month_value=_vacation_form_value(form_data, "return_month"),
                message=message,
                success=success,
                edit_leave_id=None if success else _vacation_parse_int(_vacation_form_value(form_data, "leave_id")),
                leave_draft=None
                if success
                else {
                    "id": _vacation_form_value(form_data, "leave_id"),
                    "employee_id": _vacation_form_value(form_data, "employee_id"),
                    "start_date": _vacation_form_value(form_data, "start_date"),
                    "end_date": _vacation_form_value(form_data, "end_date"),
                    "note": _vacation_form_value(form_data, "note"),
                },
            )
            self.send_response(200 if success else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == VACATION_CALENDAR_LEAVE_DELETE_ROUTE:
            raw_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            form_data = _vacation_parse_form(raw_body)
            success, message = _vacation_delete_leave(form_data)
            body = render_vacation_calendar(
                month_value=_vacation_form_value(form_data, "return_month"),
                message=message,
                success=success,
            )
            self.send_response(200 if success else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith(DIVIAN_AI_KNOWLEDGE_DELETE_PREFIX + "/"):
            entry_id = path[len(DIVIAN_AI_KNOWLEDGE_DELETE_PREFIX) + 1 :]
            success, message = _delete_divian_ai_upload(entry_id)
            body = render_divian_ai_knowledge_form(message, success=success)
            status_code = 200 if success else 404
            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == NETTFRONT_ORDER_PROCESS_ROUTE:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            files = _extract_uploaded_files(self.headers, raw_body)
            stock_file = files.get("stock_file")
            parts_file = files.get("parts_file")

            if stock_file is None:
                self.respond_nettfront_order_form("A raktár Excel feltöltése kötelező.")
                return

            stock_name, stock_bytes = stock_file
            if not stock_name.lower().endswith((".xlsx", ".xlsm", ".csv")):
                self.respond_nettfront_order_form("A raktárfájl csak XLSX, XLSM vagy CSV lehet.")
                return

            uploaded_parts_name = ""
            uploaded_parts_bytes: bytes | None = None
            uploaded_parts_count = 0
            if parts_file is not None:
                uploaded_parts_name, uploaded_parts_bytes = parts_file
                if uploaded_parts_name and not uploaded_parts_name.lower().endswith((".xlsx", ".xlsm", ".csv")):
                    self.respond_nettfront_order_form("A friss alkatrészlista csak XLSX, XLSM vagy CSV lehet.")
                    return
                try:
                    uploaded_parts_count = len(_load_nettfront_parts_list_from_bytes(uploaded_parts_bytes or b"", uploaded_parts_name))
                except Exception as exc:
                    self.respond_nettfront_order_form(f"A friss alkatrészlista feldolgozása nem sikerült: {exc}")
                    return
                if uploaded_parts_count == 0:
                    self.respond_nettfront_order_form("A friss alkatrészlista üres, így nem tudom felhasználni a jóváhagyásnál.")
                    return

            try:
                result = build_order_suggestions(
                    stock_bytes,
                    default_avg_path=NETTFRONT_ORDER_DEFAULT_AVG_PATH,
                )
                job_id, metadata = _write_nettfront_order_job(
                    result,
                    stock_name,
                    stock_bytes,
                    uploaded_parts_name,
                    uploaded_parts_bytes,
                    uploaded_parts_count,
                )
            except Exception as exc:
                self.respond_nettfront_order_form(f"Hiba a rendelési javaslat készítése közben: {exc}")
                return

            body = render_nettfront_order_result(
                job_id,
                metadata,
                message="A rendelési javaslat elkészült.",
                success=True,
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith(NETTFRONT_ORDER_APPROVE_PREFIX + "/"):
            job_id = path[len(NETTFRONT_ORDER_APPROVE_PREFIX) + 1 :]
            job_dir, metadata = _read_nettfront_job("order", job_id)
            if job_dir is None or metadata is None:
                self.send_error(404)
                return

            rows = _read_nettfront_order_rows(job_dir)
            if not rows:
                body = render_nettfront_order_result(
                    job_id,
                    metadata,
                    message="Ehhez a futáshoz nem találok szerkeszthető rendelési javaslatot.",
                )
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            form_data = _parse_urlencoded_body(raw_body)

            invalid_rows: list[str] = []
            for row in rows:
                field_name = f"qty__{row.row_id}"
                raw_value = form_data.get(field_name, "")
                parsed_value, ok = _order_parse_quantity_input(raw_value)
                if not ok:
                    invalid_rows.append(row.description or row.part_number or row.row_id)
                    continue
                row.order_qty = parsed_value

            if invalid_rows:
                invalid_preview = ", ".join(invalid_rows[:3])
                if len(invalid_rows) > 3:
                    invalid_preview += f" és még {len(invalid_rows) - 3} tétel"
                body = render_nettfront_order_result(
                    job_id,
                    metadata,
                    message=f"Hibás mennyiséget kaptam ezeknél a tételeknél: {invalid_preview}.",
                )
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            source_parts_file = str(metadata.get("source_parts_file", "")).strip() or str(metadata.get("source_average_file", "")).strip()
            if source_parts_file:
                parts_path = job_dir / source_parts_file
                if not parts_path.exists():
                    body = render_nettfront_order_result(
                        job_id,
                        metadata,
                        message="A feltöltött friss alkatrészlistát nem találom, ezért a jóváhagyást most nem tudom ellenőrizni.",
                    )
                    self.send_response(400)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

                try:
                    allowed_parts = {
                        _normalize_nettfront_part_number(item)
                        for item in _load_nettfront_parts_list_from_bytes(parts_path.read_bytes(), parts_path.name)
                    }
                except Exception as exc:
                    body = render_nettfront_order_result(
                        job_id,
                        metadata,
                        message=f"A friss alkatrészlista ellenőrzése nem sikerült: {exc}",
                    )
                    self.send_response(400)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

                missing_parts: list[str] = []
                seen_missing: set[str] = set()
                for row in rows:
                    if _order_safe_number(row.order_qty) <= 0:
                        continue
                    aliases = _nettfront_order_part_number_aliases(row.part_number)
                    if not aliases:
                        continue
                    if any(alias in allowed_parts for alias in aliases):
                        continue
                    display_part = _nettfront_order_display_part_number(row.part_number) or row.part_number or row.description or row.row_id
                    normalized_display = _normalize_nettfront_part_number(display_part)
                    if normalized_display in seen_missing:
                        continue
                    seen_missing.add(normalized_display)
                    missing_parts.append(display_part)

                if missing_parts:
                    missing_preview = ", ".join(missing_parts[:4])
                    if len(missing_parts) > 4:
                        missing_preview += f" és még {len(missing_parts) - 4} tétel"
                    body = render_nettfront_order_result(
                        job_id,
                        metadata,
                        message=(
                            "A jóváhagyás most nem ment végig, mert ezek a cikkszámok nem szerepelnek a friss alkatrészlistában: "
                            f"{missing_preview}."
                        ),
                    )
                    self.send_response(400)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

            try:
                metadata = _persist_nettfront_order_approval(job_dir, metadata, rows)
            except Exception as exc:
                body = render_nettfront_order_result(
                    job_id,
                    metadata,
                    message=f"A kész rendelés mentése nem sikerült: {exc}",
                )
                self.send_response(500)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            body = render_nettfront_order_result(
                job_id,
                metadata,
                message="A kész rendelés elkészült.",
                success=True,
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == NETTFRONT_PROCUREMENT_PROCESS_ROUTE:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            files = _extract_uploaded_files(self.headers, raw_body)
            invoice_file = files.get("invoice_pdf")
            parts_file = files.get("parts_file")

            if invoice_file is None:
                self.respond_nettfront_procurement_form("A NettFront számla PDF feltöltése kötelező.")
                return

            invoice_name, invoice_bytes = invoice_file
            if not invoice_name.lower().endswith(".pdf"):
                self.respond_nettfront_procurement_form("Csak PDF számla tölthető fel.")
                return

            uploaded_parts_name = ""
            uploaded_parts_bytes: bytes | None = None
            merged_map = None
            if parts_file is not None:
                uploaded_parts_name, uploaded_parts_bytes = parts_file
                if not uploaded_parts_name.lower().endswith((".xlsx", ".xlsm", ".csv")):
                    self.respond_nettfront_procurement_form("Az alkatrészlista csak XLSX, XLSM vagy CSV fájl lehet.")
                    return
                try:
                    merged_map = load_alkatresz_map()
                    merged_map.update(load_alkatresz_map_from_bytes(uploaded_parts_bytes, uploaded_parts_name))
                except Exception as exc:
                    self.respond_nettfront_procurement_form(f"Az alkatrészlista feldolgozása nem sikerült: {exc}")
                    return

            try:
                artifacts = build_procurement_artifacts(invoice_bytes, alkatresz_map=merged_map)
                job_id, metadata = _write_procurement_job(
                    artifacts,
                    invoice_name,
                    invoice_bytes,
                    uploaded_parts_name=uploaded_parts_name,
                    uploaded_parts_bytes=uploaded_parts_bytes,
                )
            except Exception as exc:
                self.respond_nettfront_procurement_form(f"Hiba a feldolgozás során: {exc}")
                return

            message = ""
            success = False
            if not metadata.get("missing_codes"):
                job_dir = _job_runtime_dir("procurement") / job_id
                try:
                    success, messages = launch_procurement_helper(job_dir)
                    message = " ".join(messages)
                except Exception as exc:
                    message = f"Az import-segéd automatikus indítása nem sikerült: {exc}"
                    success = False

            body = render_nettfront_procurement_result(job_id, metadata, message=message, success=success)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith(NETTFRONT_ORDER_LAUNCH_PREFIX + "/"):
            job_id = path[len(NETTFRONT_ORDER_LAUNCH_PREFIX) + 1 :]
            job_dir, metadata = _read_nettfront_job("order", job_id)
            if job_dir is None or metadata is None:
                self.send_error(404)
                return

            if not str(metadata.get("approved_file", "")).strip():
                body = render_nettfront_order_result(
                    job_id,
                    metadata,
                    message="Előbb jóvá kell hagynod a rendelést, és csak utána indítható a bevételezés.",
                )
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            try:
                success, messages = launch_procurement_helper(job_dir)
                message = " ".join(messages) if messages else "A bevételezési segéd elindult."
                body = render_nettfront_order_result(job_id, metadata, message=message, success=success)
            except Exception as exc:
                body = render_nettfront_order_result(
                    job_id,
                    metadata,
                    message=f"A bevételezési segéd indítása nem sikerült: {exc}",
                )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith(NETTFRONT_ORDER_STOP_PREFIX + "/"):
            job_id = path[len(NETTFRONT_ORDER_STOP_PREFIX) + 1 :]
            job_dir, metadata = _read_nettfront_job("order", job_id)
            if job_dir is None or metadata is None:
                self.send_error(404)
                return

            try:
                success, messages = stop_procurement_helper(job_dir)
                message = " ".join(messages) if messages else "A bevételezési segéd leállt."
                body = render_nettfront_order_result(job_id, metadata, message=message, success=success)
            except Exception as exc:
                body = render_nettfront_order_result(
                    job_id,
                    metadata,
                    message=f"A leállítás nem sikerült: {exc}",
                )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith(NETTFRONT_PROCUREMENT_PARTS_PREFIX + "/"):
            job_id = path[len(NETTFRONT_PROCUREMENT_PARTS_PREFIX) + 1 :]
            job_dir, metadata = _read_nettfront_job("procurement", job_id)
            if job_dir is None or metadata is None:
                self.send_error(404)
                return

            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            files = _extract_uploaded_files(self.headers, raw_body)
            parts_file = files.get("parts_file")

            if parts_file is None:
                body = render_nettfront_procurement_result(job_id, metadata, message="Az alkatrészlista feltöltése kötelező.")
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            parts_name, parts_bytes = parts_file
            if not parts_name.lower().endswith((".xlsx", ".xlsm", ".csv")):
                body = render_nettfront_procurement_result(job_id, metadata, message="Az alkatrészlista csak XLSX, XLSM vagy CSV fájl lehet.")
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            source_invoice_file = str(metadata.get("source_invoice_file", "source-invoice.pdf")).strip() or "source-invoice.pdf"
            source_invoice_path = job_dir / source_invoice_file
            if not source_invoice_path.exists():
                body = render_nettfront_procurement_result(
                    job_id,
                    metadata,
                    message="Ehhez a korábbi futáshoz nem találom a forrásszámlát. Töltsd fel újra a számlát.",
                )
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            try:
                merged_map = load_alkatresz_map()
                merged_map.update(load_alkatresz_map_from_bytes(parts_bytes, parts_name))
                artifacts = build_procurement_artifacts(source_invoice_path.read_bytes(), alkatresz_map=merged_map)
                metadata = _persist_procurement_job(job_dir, metadata, artifacts, uploaded_parts_name=parts_name, uploaded_parts_bytes=parts_bytes)
            except Exception as exc:
                body = render_nettfront_procurement_result(job_id, metadata, message=f"Az alkatrészlista feldolgozása nem sikerült: {exc}")
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if metadata.get("missing_codes"):
                message = f"Az alkatrészlista bekerült. Még {len(metadata.get('missing_codes', []))} hiányzó kód maradt."
                success = False
            else:
                try:
                    success, messages = launch_procurement_helper(job_dir)
                    message = "Az alkatrészlista bekerült. " + " ".join(messages)
                except Exception as exc:
                    message = f"Az alkatrészlista bekerült, de az import-segéd automatikus indítása nem sikerült: {exc}"
                    success = False

            body = render_nettfront_procurement_result(job_id, metadata, message=message, success=success)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == NETTFRONT_COMPARE_PROCESS_ROUTE:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            files = _extract_uploaded_files(self.headers, raw_body)
            invoice_file = files.get("invoice_pdf")
            order_file = files.get("order_file")

            if invoice_file is None or order_file is None:
                self.respond_nettfront_compare_form("A számla PDF és a meglévő rendelési fájl feltöltése is kötelező.")
                return

            invoice_name, invoice_bytes = invoice_file
            if not invoice_name.lower().endswith(".pdf"):
                self.respond_nettfront_compare_form("Csak PDF számla tölthető fel.")
                return

            order_name, order_bytes = order_file
            allowed_order_extensions = (".xlsx", ".xlsm", ".csv")
            if not order_name.lower().endswith(allowed_order_extensions):
                self.respond_nettfront_compare_form("A meglévő rendelés csak XLSX, XLSM vagy CSV fájl lehet.")
                return

            try:
                artifacts = build_compare_artifacts(invoice_bytes, order_bytes)
                job_id, metadata = _write_compare_job(artifacts)
            except Exception as exc:
                self.respond_nettfront_compare_form(f"Hiba az összehasonlítás során: {exc}")
                return

            body = render_nettfront_compare_result(job_id, metadata)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith(NETTFRONT_PROCUREMENT_LAUNCH_PREFIX + "/"):
            job_id = path[len(NETTFRONT_PROCUREMENT_LAUNCH_PREFIX) + 1 :]
            job_dir, metadata = _read_nettfront_job("procurement", job_id)
            if job_dir is None or metadata is None:
                self.send_error(404)
                return

            if metadata.get("missing_codes"):
                body = render_nettfront_procurement_result(
                    job_id,
                    metadata,
                    message="Hiányzó kódok vannak. Előbb tölts fel alkatrészlistát a Beszerzés újraépítéséhez.",
                )
                status_code = 400
            else:
                try:
                    success, messages = launch_procurement_helper(job_dir)
                    body = render_nettfront_procurement_result(job_id, metadata, message=" ".join(messages), success=success)
                    status_code = 200
                except Exception as exc:
                    body = render_nettfront_procurement_result(job_id, metadata, message=f"A launch nem sikerült: {exc}")
                    status_code = 500

            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith(NETTFRONT_PROCUREMENT_STOP_PREFIX + "/"):
            job_id = path[len(NETTFRONT_PROCUREMENT_STOP_PREFIX) + 1 :]
            job_dir, metadata = _read_nettfront_job("procurement", job_id)
            if job_dir is None or metadata is None:
                self.send_error(404)
                return

            try:
                success, messages = stop_procurement_helper(job_dir)
                body = render_nettfront_procurement_result(job_id, metadata, message=" ".join(messages), success=success)
                status_code = 200 if success else 400
            except Exception as exc:
                body = render_nettfront_procurement_result(job_id, metadata, message=f"A leállítás nem sikerült: {exc}")
                status_code = 500

            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path != GENERATE_ROUTE:
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        file_name, file_data = _extract_uploaded_pdf(self.headers, raw_body)

        if not file_data or not file_name:
            self.respond_form("Hibás kérés: hiányzó feltöltési adatok.")
            return

        if not file_name.lower().endswith(".pdf"):
            self.respond_form("Csak PDF fájl tölthető fel.")
            return

        status, payload, content_type, headers = _build_invoice_response(file_name, file_data)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        for header_name, header_value in headers.items():
            self.send_header(header_name, header_value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def respond_form(self, message: str):
        body = render_form(message)
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_nettfront_procurement_form(self, message: str):
        body = render_nettfront_procurement_form(message)
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_nettfront_order_form(self, message: str):
        body = render_nettfront_order_form(message)
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_nettfront_compare_form(self, message: str):
        body = render_nettfront_compare_form(message)
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_vacation_calendar(self, message: str, month_value: str = ""):
        body = render_vacation_calendar(month_value=month_value, message=message)
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_divian_ai_knowledge_form(self, message: str):
        body = render_divian_ai_knowledge_form(message)
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def respond_json(self, status_code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _prime_divian_ai_cache_worker() -> None:
    try:
        _load_divian_ai_knowledge()
    except Exception:
        pass


def _prime_divian_ai_cache_async() -> None:
    global DIVIAN_AI_PRIME_STARTED
    with DIVIAN_AI_PRIME_LOCK:
        if DIVIAN_AI_PRIME_STARTED:
            return
        DIVIAN_AI_PRIME_STARTED = True
    threading.Thread(target=_prime_divian_ai_cache_worker, name="divian-ai-prime", daemon=True).start()


if __name__ == "__main__":
    if DEV_RELOAD_ENABLED and os.getenv(DEV_CHILD_ENV) != "1":
        _run_dev_supervisor()
    else:
        _prime_divian_ai_cache_async()
        server = ReusableThreadingHTTPServer((HOST, PORT), InvoiceHandler)
        print(f"Server running on http://localhost:{PORT} (bind: {HOST}:{PORT})")
        server.serve_forever()
