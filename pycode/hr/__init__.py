"""HR onboarding document generation module."""

from .page import APP_ROUTE, CONFIRM_ROUTE, render_form, render_review
from .generating import build_hr_documents
from .reading import HR_COLUMNS, read_people

HR_ACCESS_USER_IDS = frozenset({"hriroda"})

__all__ = [
    "APP_ROUTE", "CONFIRM_ROUTE", "HR_ACCESS_USER_IDS", "HR_COLUMNS",
    "build_hr_documents", "read_people", "render_form", "render_review",
]
