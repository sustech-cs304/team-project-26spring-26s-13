"""
Frontend Relevant/components/materials_widget.py
左侧教材列表组件：展示已上传文件，支持上传和删除操作。
"""

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from frontend.api.client import APIError, api_client

ALLOWED_EXTENSIONS = (".pdf", ".pptx", ".ppt", ".md", ".txt")


class MaterialsWidget(QWidget):
    """
    左侧教材列表，提供上传/删除功能。
    上传完成后 emit material_uploaded，供 DashboardPage 更新状态。
    """

    material_uploaded = pyqtSignal(dict)  # 上传完成的 MaterialInfo dict
    material_deleted = pyqtSignal(str)  # 被删除的 file_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """
        布局：
          QVBoxLayout
          ├── QListWidget（文件列表，显示 file_name 和 vectorized 状态）
          └── QHBoxLayout
              ├── QPushButton "Upload"
              └── QPushButton "Delete"
        """
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self._list = QListWidget(self)
        layout.addWidget(self._list, 1)

        button_row = QHBoxLayout()
        upload_button = QPushButton("Upload", self)
        upload_button.clicked.connect(self._on_upload)
        delete_button = QPushButton("Delete", self)
        delete_button.clicked.connect(self._on_delete)
        button_row.addWidget(upload_button)
        button_row.addWidget(delete_button)
        layout.addLayout(button_row)

    def load_materials(self, materials: list[dict]) -> None:
        """
        批量加载材料列表（bootstrap 时调用）。

        Args:
            materials: MaterialInfo list，每项包含 file_id, file_name, vectorized
        """
        self._list.clear()
        for material in materials:
            file_id = str(material.get("file_id", "")).strip()
            file_name = str(material.get("file_name", "")).strip() or file_id
            if not file_id and not file_name:
                continue
            status = "Ready" if material.get("vectorized") else "Processing"
            item = QListWidgetItem(f"{file_name} · {status}")
            item.setData(Qt.ItemDataRole.UserRole, file_id)
            self._list.addItem(item)

    def _on_upload(self) -> None:
        """
        点击 Upload：
        1. 打开 QFileDialog 选择文件（过滤 ALLOWED_EXTENSIONS）
        2. 在 QThread 中调用 api_client.upload_material()（避免卡 UI）
        3. 成功后将新文件加入列表，emit material_uploaded
        4. 失败显示 QMessageBox 错误
        """
        filters = (
            "Materials (" + " ".join(f"*{ext}" for ext in ALLOWED_EXTENSIONS) + ")"
        )
        paths, _ = QFileDialog.getOpenFileNames(self, "Upload material", "", filters)
        for path in paths:
            if Path(path).suffix.lower() not in ALLOWED_EXTENSIONS:
                QMessageBox.warning(self, "Upload failed", "Unsupported file type.")
                continue
            try:
                material = api_client.upload_material(path)
            except APIError as exc:
                QMessageBox.warning(self, "Upload failed", exc.detail)
                continue
            self.load_materials([*self._current_materials(), material])
            self.material_uploaded.emit(material)

    def _on_delete(self) -> None:
        """
        点击 Delete：
        1. 获取当前选中的 file_id
        2. QMessageBox 确认
        3. 调用 api_client.delete_material(file_id)
        4. 从列表移除，emit material_deleted
        """
        item = self._list.currentItem()
        if item is None:
            return
        file_id = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
        if not file_id:
            return
        if (
            QMessageBox.question(
                self,
                "Delete material",
                "Delete the selected material?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            api_client.delete_material(file_id)
        except APIError as exc:
            QMessageBox.warning(self, "Delete failed", exc.detail)
            return
        row = self._list.row(item)
        self._list.takeItem(row)
        self.material_deleted.emit(file_id)

    def _current_materials(self) -> list[dict]:
        materials: list[dict] = []
        for row in range(self._list.count()):
            item = self._list.item(row)
            file_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
            file_name = item.text().split(" · ", 1)[0]
            materials.append(
                {"file_id": file_id, "file_name": file_name, "vectorized": True}
            )
        return materials
