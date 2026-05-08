"""
Backward-compatible Blackboard exports.

The concrete implementations now live in smaller modules:
- `bb_auth.py`
- `bb_common.py`
- `bb_materials.py`
- `bb_deadlines.py`
"""

from .bb_deadlines import fetch_blackboard
from .bb_materials import (
    BlackboardMaterial,
    _extract_content_file_urls,
    _filename_from_response,
    _is_content_file_view_url,
    _parse_blackboard_material_page,
    fetch_blackboard_course_materials,
)

__all__ = [
    "BlackboardMaterial",
    "_extract_content_file_urls",
    "_filename_from_response",
    "_is_content_file_view_url",
    "_parse_blackboard_material_page",
    "fetch_blackboard",
    "fetch_blackboard_course_materials",
]
