"""
Frontend Relevant/components/schedule_widget.py
日程展示组件：日历 + 每日安排 + 冲突提醒。
"""

from datetime import date
from typing import Any

from PyQt6.QtCore import QDate, QSize, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QTextCharFormat
from PyQt6.QtWidgets import (
    QCalendarWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from frontend.api.client import api_client
from frontend.schedule_utils import (
    event_sort_key,
    events_by_date,
    format_event_time,
    next_event_date,
)


class ScheduleRefreshWorker(QThread):
    schedule_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def run(self) -> None:
        try:
            self.schedule_ready.emit(api_client.refresh_schedule())
        except Exception as exc:  # noqa: BLE001
            self.error_occurred.emit(str(exc))


class ScheduleWidget(QWidget):
    """
    日程页面，展示日历、每日 events 列表和 conflicts 冲突提醒。
    提供"刷新"按钮，手动触发 /api/schedule/refresh。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._schedule_data: dict[str, Any] = {"events": [], "conflicts": []}
        self._selected_day: date | None = None
        self._highlighted_dates: set[date] = set()
        self._refresh_worker: ScheduleRefreshWorker | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """
        布局：
          QVBoxLayout
          ├── QCalendarWidget（日历，高亮有安排的日期）
          └── QListWidget（选中日期的每日安排）
        """
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        schedule_scroll = QScrollArea()
        schedule_scroll.setObjectName("SchedulePageScroll")
        schedule_scroll.setWidgetResizable(True)
        schedule_scroll.setFrameShape(QFrame.Shape.NoFrame)

        schedule_content = QWidget()
        schedule_content.setObjectName("SchedulePageContent")
        layout = QVBoxLayout(schedule_content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("日程日历")
        title.setObjectName("SectionTitle")
        self._summary_label = QLabel()
        self._summary_label.setObjectName("BadgeLabel")
        header.addWidget(title)
        header.addWidget(self._summary_label)
        header.addStretch(1)

        body = QVBoxLayout()
        body.setSpacing(12)

        calendar_card = QFrame()
        calendar_card.setObjectName("PanelCard")
        calendar_card.setMinimumHeight(500)
        calendar_layout = QVBoxLayout(calendar_card)
        calendar_layout.setContentsMargins(14, 14, 14, 14)
        self._calendar = QCalendarWidget()
        self._calendar.setObjectName("ScheduleCalendar")
        self._calendar.setGridVisible(True)
        self._calendar.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        self._calendar.setVerticalHeaderFormat(
            QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader
        )
        self._calendar.setMinimumHeight(420)
        self._calendar.selectionChanged.connect(self._on_date_selected)
        calendar_layout.addWidget(self._calendar)

        detail_card = QFrame()
        detail_card.setObjectName("PanelCard")
        detail_card.setMinimumHeight(240)
        detail_layout = QVBoxLayout(detail_card)
        detail_layout.setContentsMargins(14, 14, 14, 14)
        detail_layout.setSpacing(0)

        detail_scroll = QScrollArea()
        detail_scroll.setObjectName("ScheduleDetailScroll")
        detail_scroll.setWidgetResizable(True)
        detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        detail_content = QWidget()
        detail_content.setObjectName("ScheduleDetailContent")
        detail_content_layout = QVBoxLayout(detail_content)
        detail_content_layout.setContentsMargins(0, 0, 0, 0)
        detail_content_layout.setSpacing(14)

        self._day_label = QLabel()
        self._day_label.setObjectName("SectionTitle")
        self._events_list = QListWidget()
        self._events_list.setObjectName("DailyScheduleList")
        self._configure_schedule_list(self._events_list)
        self._conflicts_label = QLabel("冲突提醒")
        self._conflicts_label.setObjectName("CardTitle")
        self._conflicts_list = QListWidget()
        self._conflicts_list.setObjectName("ScheduleConflictList")
        self._configure_schedule_list(self._conflicts_list)

        events_section = QFrame()
        events_section.setObjectName("ScheduleSection")
        events_layout = QVBoxLayout(events_section)
        events_layout.setContentsMargins(0, 0, 0, 0)
        events_layout.setSpacing(8)
        events_layout.addWidget(self._day_label)
        events_layout.addWidget(self._events_list)

        conflicts_section = QFrame()
        conflicts_section.setObjectName("ScheduleSection")
        conflicts_layout = QVBoxLayout(conflicts_section)
        conflicts_layout.setContentsMargins(0, 0, 0, 0)
        conflicts_layout.setSpacing(8)
        conflicts_layout.addWidget(self._conflicts_label)
        conflicts_layout.addWidget(self._conflicts_list)

        detail_content_layout.addWidget(events_section)
        detail_content_layout.addWidget(conflicts_section)
        detail_content_layout.addStretch(1)
        detail_scroll.setWidget(detail_content)
        detail_layout.addWidget(detail_scroll, 1)

        body.addWidget(calendar_card)
        body.addWidget(detail_card, 1)

        layout.addLayout(header)
        layout.addLayout(body, 1)
        schedule_scroll.setWidget(schedule_content)
        outer_layout.addWidget(schedule_scroll, 1)
        self.update_schedule(self._schedule_data)

    def update_schedule(self, schedule_data: dict) -> None:
        """
        用新的日程数据刷新显示。

        Args:
            schedule_data: ScheduleData dict，包含 events 和 conflicts 列表
        """
        if not isinstance(schedule_data, dict):
            schedule_data = {"events": [], "conflicts": []}
        events = schedule_data.get("events", [])
        conflicts = schedule_data.get("conflicts", [])
        self._schedule_data = {
            "events": events if isinstance(events, list) else [],
            "conflicts": conflicts if isinstance(conflicts, list) else [],
        }
        self._refresh_calendar()

    def _on_refresh(self) -> None:
        """
        点击刷新按钮：
        1. 调用 api_client.refresh_schedule()（应在 QThread 中执行，避免卡 UI）
        2. 用返回数据调用 update_schedule()
        """
        if self._refresh_worker and self._refresh_worker.isRunning():
            return
        self._refresh_worker = ScheduleRefreshWorker(self)
        self._refresh_worker.schedule_ready.connect(self.update_schedule)
        self._refresh_worker.error_occurred.connect(self._show_refresh_error)
        self._refresh_worker.start()

    def _refresh_calendar(self) -> None:
        events = self._events()
        grouped = events_by_date(events)
        self._summary_label.setText(
            f"{len(grouped)} 天有安排 · 共 {len(events)} 个事件"
        )
        self._mark_calendar_dates(grouped)

        if self._selected_day is None:
            self._selected_day = next_event_date(events) or date.today()
        selected_qdate = self._qdate_from_day(self._selected_day)
        if self._calendar.selectedDate() != selected_qdate:
            self._calendar.setSelectedDate(selected_qdate)
        self._render_selected_day(grouped)
        self._render_conflicts()

    def _mark_calendar_dates(self, grouped: dict[date, list[dict[str, Any]]]) -> None:
        empty_format = QTextCharFormat()
        for old_day in self._highlighted_dates:
            self._calendar.setDateTextFormat(
                self._qdate_from_day(old_day), empty_format
            )

        event_format = QTextCharFormat()
        event_format.setBackground(QColor(59, 130, 246, 100))
        event_format.setForeground(QColor("#f0f4ff"))
        event_format.setFontWeight(QFont.Weight.Bold)
        for day_value in grouped:
            self._calendar.setDateTextFormat(
                self._qdate_from_day(day_value), event_format
            )
        self._highlighted_dates = set(grouped)

    def _on_date_selected(self) -> None:
        self._selected_day = self._day_from_qdate(self._calendar.selectedDate())
        self._render_selected_day(events_by_date(self._events()))

    def _render_selected_day(self, grouped: dict[date, list[dict[str, Any]]]) -> None:
        selected = self._selected_day or date.today()
        self._day_label.setText(
            f"选中日期：{self._qdate_from_day(selected).toString('yyyy-MM-dd ddd')}"
        )
        self._events_list.clear()
        day_events = grouped.get(selected, [])
        if not day_events:
            self._add_placeholder(self._events_list, "当天暂无安排。")
            self._fit_schedule_list_to_contents(
                self._events_list, min_height=74, max_height=150
            )
            return
        for event in sorted(day_events, key=event_sort_key):
            self._add_schedule_item(
                self._events_list, self._format_event(event, selected)
            )
        self._fit_schedule_list_to_contents(
            self._events_list, min_height=120, max_height=240
        )

    def _render_conflicts(self) -> None:
        self._conflicts_list.clear()
        conflicts = self._schedule_data.get("conflicts", [])
        if not conflicts:
            self._add_placeholder(self._conflicts_list, "暂无冲突提醒。")
            self._fit_schedule_list_to_contents(
                self._conflicts_list, min_height=74, max_height=150
            )
            return
        for conflict in conflicts[:5]:
            title = str(conflict.get("title", "冲突提醒")).strip()
            detail = str(conflict.get("detail", "")).strip()
            text = f"{title}\n{detail}" if detail else title
            self._add_schedule_item(self._conflicts_list, text)
        self._fit_schedule_list_to_contents(
            self._conflicts_list, min_height=96, max_height=180
        )

    def _events(self) -> list[dict[str, Any]]:
        return [
            event
            for event in self._schedule_data.get("events", [])
            if isinstance(event, dict)
        ]

    @staticmethod
    def _format_event(event: dict[str, Any], selected: date) -> str:
        title = str(event.get("title", "日程")).strip()
        time_text = format_event_time(event, selected)
        source = str(event.get("source", "")).strip()
        detail = str(event.get("detail", "")).strip()
        meta = " | ".join(part for part in [time_text, source] if part)
        return "\n".join(part for part in [title, meta, detail] if part)

    @staticmethod
    def _add_placeholder(list_widget: QListWidget, text: str) -> None:
        item = ScheduleWidget._add_schedule_item(list_widget, text)
        item.setFlags(Qt.ItemFlag.NoItemFlags)

    @staticmethod
    def _add_schedule_item(list_widget: QListWidget, text: str) -> QListWidgetItem:
        item = QListWidgetItem(text, list_widget)
        item.setSizeHint(QSize(0, ScheduleWidget._schedule_item_height(text)))
        return item

    @staticmethod
    def _configure_schedule_list(list_widget: QListWidget) -> None:
        list_widget.setWordWrap(True)
        list_widget.setUniformItemSizes(False)
        list_widget.setTextElideMode(Qt.TextElideMode.ElideNone)
        list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        list_widget.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)

    @staticmethod
    def _fit_schedule_list_to_contents(
        list_widget: QListWidget,
        *,
        min_height: int,
        max_height: int,
    ) -> None:
        content_height = 18
        for index in range(list_widget.count()):
            content_height += list_widget.item(index).sizeHint().height() + 6
        height = max(min_height, min(max_height, content_height))
        list_widget.setMinimumHeight(height)
        list_widget.setMaximumHeight(height)

    @staticmethod
    def _schedule_item_height(text: str) -> int:
        explicit_lines = text.count("\n") + 1
        wrapped_lines = sum(
            max(1, (len(line) + 42) // 43) for line in text.splitlines() or [""]
        )
        line_count = max(explicit_lines, wrapped_lines)
        return max(46, min(150, 24 + line_count * 22))

    def _show_refresh_error(self, message: str) -> None:
        QMessageBox.warning(self, "刷新日程失败", message)

    @staticmethod
    def _qdate_from_day(day_value: date) -> QDate:
        return QDate(day_value.year, day_value.month, day_value.day)

    @staticmethod
    def _day_from_qdate(qdate: QDate) -> date:
        return date(qdate.year(), qdate.month(), qdate.day())
