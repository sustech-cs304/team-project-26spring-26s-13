"""
Frontend Relevant/components/library_widget.py
图书馆讨论间查询结果展示组件。
"""

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class LibraryWidget(QWidget):
    """展示图书馆讨论间可预约时间查询结果。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()
        self.clear()

    def _setup_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        self._title = QLabel("图书馆讨论间")
        self._title.setObjectName("SectionTitle")
        self._summary = QLabel()
        self._summary.setObjectName("BadgeLabel")
        self._summary.setWordWrap(True)

        card = QFrame()
        card.setObjectName("PanelCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setSpacing(10)

        self._rooms_list = QListWidget()
        self._rooms_list.setObjectName("LibraryRoomList")
        self._rooms_list.setUniformItemSizes(False)
        self._rooms_list.setAlternatingRowColors(True)
        self._rooms_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self._rooms_list.setMinimumHeight(360)

        card_layout.addWidget(self._rooms_list)
        layout.addWidget(self._title)
        layout.addWidget(self._summary)
        layout.addWidget(card, 1)
        scroll.setWidget(content)
        outer_layout.addWidget(scroll, 1)

    def update_rooms(self, library_data: dict[str, Any]) -> None:
        if not isinstance(library_data, dict):
            self.clear()
            return

        query_location = str(library_data.get("query_location") or "不限地点")
        query_time = str(library_data.get("query_time") or "不限时间")
        query_capacity = library_data.get("query_capacity")
        rooms = library_data.get("rooms")
        room_list = rooms if isinstance(rooms, list) else []

        capacity_label = f"{query_capacity} 人及以上" if query_capacity else "不限容量"
        self._summary.setText(
            f"查询：{query_time} · {query_location or '不限地点'} · {capacity_label}；"
            f"找到 {len(room_list)} 个有空闲时段的讨论间。"
        )

        self._rooms_list.clear()
        if not room_list:
            self._rooms_list.addItem("没有查询到符合条件的空闲讨论间。")
            return

        for room in room_list:
            if not isinstance(room, dict):
                continue
            room_name = str(
                room.get("room_name") or room.get("room_id") or "未命名讨论间"
            )
            location = str(room.get("location") or "位置未知")
            capacity = room.get("capacity")
            time_slots = room.get("time_slots") or []
            slot_label = "、".join(str(slot) for slot in time_slots) or "无空闲时段"
            capacity_text = f"{capacity} 人" if capacity else "容量未知"
            item = QListWidgetItem(
                f"{room_name}\n位置：{location} · 容量：{capacity_text}\n可预约：{slot_label}"
            )
            item.setData(Qt.ItemDataRole.UserRole, room)
            self._rooms_list.addItem(item)

    def clear(self) -> None:
        self._summary.setText("还没有讨论间查询结果。")
        self._rooms_list.clear()
