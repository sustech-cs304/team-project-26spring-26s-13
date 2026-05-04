from datetime import datetime

BLACKBOARD_BASE = "https://bb.sustech.edu.cn"
ACADEMIC_SYSTEM_BASE = "https://tis.sustech.edu.cn"

TIS_WEEK1_MONDAY = datetime(2026, 2, 23)
SUSTECH_CLASS_PERIODS: dict[int, tuple[str, str]] = {
    1: ("08:00", "08:50"),
    2: ("09:00", "09:50"),
    3: ("10:20", "11:10"),
    4: ("11:20", "12:10"),
    5: ("14:00", "14:50"),
    6: ("15:00", "15:50"),
    7: ("16:20", "17:10"),
    8: ("17:20", "18:10"),
    9: ("19:00", "19:50"),
    10: ("20:00", "20:50"),
}

# Backward-compatible aliases for older private-style names.
_TIS_WEEK1_MONDAY = TIS_WEEK1_MONDAY
_SUSTECH_CLASS_PERIODS = SUSTECH_CLASS_PERIODS
