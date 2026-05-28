"""
Frontend Relevant/components/encyclopedia_widget.py
校园百科结果展示组件：答案（Markdown 渲染）+ 引用列表。
"""

from PyQt6.QtWidgets import QLabel, QListWidget, QTextBrowser, QVBoxLayout, QWidget


class EncyclopediaWidget(QWidget):
    """
    百科页面，展示 RAG 检索结果。
    回答内容为 Markdown 格式，建议使用 QTextBrowser 渲染（支持富文本）。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """
        布局：
          QVBoxLayout
          ├── QLabel "Query: {query}"
          ├── QTextBrowser（answer_markdown 渲染区）
          └── QListWidget（citations 列表）
        """
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self._query_label = QLabel("Query")
        self._query_label.setObjectName("SectionTitle")
        self._answer_browser = QTextBrowser(self)
        self._answer_browser.setOpenExternalLinks(True)
        self._citations_list = QListWidget(self)

        layout.addWidget(self._query_label)
        layout.addWidget(self._answer_browser, 1)
        layout.addWidget(QLabel("Citations"))
        layout.addWidget(self._citations_list)
        self.clear()

    def show_result(self, encyclopedia_data: dict) -> None:
        """
        展示 encyclopedia 查询结果。

        Args:
            encyclopedia_data: ui_payload.encyclopedia dict，包含：
                               query, answer_markdown, citations
        """
        query = str(encyclopedia_data.get("query", "")).strip()
        answer = str(encyclopedia_data.get("answer_markdown", "")).strip()
        citations = encyclopedia_data.get("citations", [])

        self._query_label.setText(f"Query: {query}" if query else "Campus Encyclopedia")
        self._answer_browser.setMarkdown(answer or "No answer returned.")
        self._citations_list.clear()
        if isinstance(citations, list):
            for citation in citations:
                self._citations_list.addItem(str(citation))

    def clear(self) -> None:
        """清空展示内容。"""
        self._query_label.setText("Campus Encyclopedia")
        self._answer_browser.clear()
        self._citations_list.clear()
