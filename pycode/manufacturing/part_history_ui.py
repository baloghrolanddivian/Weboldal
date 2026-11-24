"""Shared long-press history UI for the worker and admin manufacturing pages."""

from pathlib import Path


def part_history_script():
    return Path(__file__).with_name("part_history.js").read_text(encoding="utf-8")
