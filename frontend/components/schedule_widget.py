"""
God Xun-Frontend/components/schedule_widget.py
日程展示组件：事件列表 + 冲突提醒卡片。
"""

from PyQt6.QtWidgets import (
    QGroupBox, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)

from frontend.api.client import api_client


class ScheduleWidget(QWidget):
    """
    日程页面，展示 events 列表和 conflicts 冲突提醒。
    提供"刷新"按钮，手动触发 /api/schedule/refresh。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # TODO: self._setup_ui()

    def _setup_ui(self) -> None:
        """
        布局：
          QVBoxLayout
          ├── QPushButton "Refresh Schedule"
          ├── QGroupBox "Events"
          │   └── QListWidget（事件列表）
          └── QGroupBox "Conflicts"
              └── QListWidget（冲突列表，警告色）
        """
        # TODO
        raise NotImplementedError

    def update_schedule(self, schedule_data: dict) -> None:
        """
        用新的日程数据刷新显示。

        Args:
            schedule_data: ScheduleData dict，包含 events 和 conflicts 列表
        """
        # TODO:
        # self._events_list.clear()
        # for event in schedule_data.get("events", []):
        #     self._events_list.addItem(f"{event['time']} | {event['title']} [{event['source']}]")
        # self._conflicts_list.clear()
        # for conflict in schedule_data.get("conflicts", []):
        #     self._conflicts_list.addItem(f"⚠ {conflict['title']}")
        raise NotImplementedError

    def _on_refresh(self) -> None:
        """
        点击刷新按钮：
        1. 调用 api_client.refresh_schedule()（应在 QThread 中执行，避免卡 UI）
        2. 用返回数据调用 update_schedule()
        """
        # TODO: 使用 QThread worker 执行，参考 AgentWorker 模式
        raise NotImplementedError
