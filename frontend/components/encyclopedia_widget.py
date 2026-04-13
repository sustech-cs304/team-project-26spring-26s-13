"""
Frontend Relevant/components/encyclopedia_widget.py
校园百科结果展示组件：答案（Markdown 渲染）+ 引用列表。
"""

from PyQt6.QtWidgets import QLabel, QListWidget, QVBoxLayout, QWidget


class EncyclopediaWidget(QWidget):
    """
    百科页面，展示 RAG 检索结果。
    回答内容为 Markdown 格式，建议使用 QTextBrowser 渲染（支持富文本）。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # TODO: self._setup_ui()

    def _setup_ui(self) -> None:
        """
        布局：
          QVBoxLayout
          ├── QLabel "Query: {query}"
          ├── QTextBrowser（answer_markdown 渲染区）
          └── QListWidget（citations 列表）
        """
        # TODO
        raise NotImplementedError

    def show_result(self, encyclopedia_data: dict) -> None:
        """
        展示 encyclopedia 查询结果。

        Args:
            encyclopedia_data: ui_payload.encyclopedia dict，包含：
                               query, answer_markdown, citations
        """
        # TODO:
        # self._query_label.setText(f"Query: {encyclopedia_data['query']}")
        # self._answer_browser.setMarkdown(encyclopedia_data["answer_markdown"])
        # self._citations_list.clear()
        # for cite in encyclopedia_data.get("citations", []):
        #     self._citations_list.addItem(cite)
        raise NotImplementedError

    def clear(self) -> None:
        """清空展示内容。"""
        # TODO
        raise NotImplementedError
