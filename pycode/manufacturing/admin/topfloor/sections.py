"""Admin-view import surface for the shared Topfloor builders."""

# Admin adapter for the shared Topfloor builders.
from manufacturing.base.topfloor_sections import (
    _manufacturing_topfloor_document,
    _manufacturing_topfloor_document_from_bundles,
)

__all__ = ["_manufacturing_topfloor_document", "_manufacturing_topfloor_document_from_bundles"]
