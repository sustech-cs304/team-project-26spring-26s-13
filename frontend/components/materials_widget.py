"""
Frontend Relevant/components/materials_widget.py
左侧教材列表组件：展示已上传文件，支持上传和删除操作。
"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog, QHBoxLayout, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

from frontend.api.client import APIError, api_client


ALLOWED_EXTENSIONS = (".pdf", ".pptx", ".ppt", ".md", ".txt")


class MaterialsWidget(QWidget):
    """
    左侧教材列表，提供上传/删除功能。
    上传完成后 emit material_uploaded，供 DashboardPage 更新状态。
    """

    material_uploaded = pyqtSignal(dict)   # 上传完成的 MaterialInfo dict
    material_deleted = pyqtSignal(str)     # 被删除的 file_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # TODO: self._setup_ui()

    def _setup_ui(self) -> None:
        """
        布局：
          QVBoxLayout
          ├── QListWidget（文件列表，显示 file_name 和 vectorized 状态）
          └── QHBoxLayout
              ├── QPushButton "Upload"
              └── QPushButton "Delete"
        """
        # TODO
        raise NotImplementedError

    def load_materials(self, materials: list[dict]) -> None:
        """
        批量加载材料列表（bootstrap 时调用）。

        Args:
            materials: MaterialInfo list，每项包含 file_id, file_name, vectorized
        """
        # TODO:
        # self._list.clear()
        # for m in materials:
        #     status = "✓" if m["vectorized"] else "⏳"
        #     item = QListWidgetItem(f"{status} {m['file_name']}")
        #     item.setData(Qt.ItemDataRole.UserRole, m["file_id"])
        #     self._list.addItem(item)
        raise NotImplementedError

    def _on_upload(self) -> None:
        """
        点击 Upload：
        1. 打开 QFileDialog 选择文件（过滤 ALLOWED_EXTENSIONS）
        2. 在 QThread 中调用 api_client.upload_material()（避免卡 UI）
        3. 成功后将新文件加入列表，emit material_uploaded
        4. 失败显示 QMessageBox 错误
        """
        # TODO
        raise NotImplementedError

    def _on_delete(self) -> None:
        """
        点击 Delete：
        1. 获取当前选中的 file_id
        2. QMessageBox 确认
        3. 调用 api_client.delete_material(file_id)
        4. 从列表移除，emit material_deleted
        """
        # TODO
        raise NotImplementedError
