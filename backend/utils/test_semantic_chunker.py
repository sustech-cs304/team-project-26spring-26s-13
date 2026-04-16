import unittest

from backend.utils.semantic_chunker import semantic_chunk_text


class TestSemanticChunker(unittest.TestCase):
    def test_semantic_chunker_splits_by_headings_and_size(self) -> None:
        text = (
            "第一章 总则\n\n"
            "1.1 适用范围\n\n"
            + ("本手册适用于全体学生。请遵守相关规定。为了保证学习秩序，学校将采取必要措施。 " * 80)
            + "\n\n"
            "第二章 学籍管理\n\n"
            + ("学生应按时注册。未注册将影响选课与成绩。请及时关注通知。 " * 60)
        )
        chunks = semantic_chunk_text(text, target_size=300, hard_max_size=400, overlap=50)
        self.assertGreaterEqual(len(chunks), 3)
        for c in chunks:
            self.assertLessEqual(len(c.text), 400)

        self.assertTrue(any("第一章" in " ".join(c.section_path) for c in chunks))
        self.assertTrue(any("第二章" in " ".join(c.section_path) for c in chunks))

    def test_semantic_chunker_returns_empty_for_empty_text(self) -> None:
        self.assertEqual(semantic_chunk_text("", target_size=200, hard_max_size=300, overlap=50), [])


if __name__ == "__main__":
    unittest.main()

