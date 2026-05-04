import unittest

from backend.services.schedule_service.fetch_bb import (
    _extract_content_file_urls,
    _filename_from_response,
    _is_content_file_view_url,
    _parse_blackboard_material_page,
)


class TestFetchBlackboardMaterials(unittest.TestCase):
    def test_is_content_file_view_url_requires_course_and_content(self) -> None:
        self.assertTrue(
            _is_content_file_view_url(
                "https://bb.sustech.edu.cn/webapps/blackboard/execute/content/file?cmd=view&content_id=_613494_1&course_id=_8205_1"
            )
        )
        self.assertFalse(
            _is_content_file_view_url(
                "https://bb.sustech.edu.cn/webapps/blackboard/execute/content/file?cmd=edit&content_id=_613494_1&course_id=_8205_1"
            )
        )
        self.assertFalse(
            _is_content_file_view_url(
                "https://bb.sustech.edu.cn/webapps/blackboard/execute/content/file?cmd=view&content_id=_613494_1"
            )
        )

    def test_extract_content_file_urls_finds_file_views(self) -> None:
        html = """
        <html><body>
          <a href="/webapps/blackboard/execute/content/file?cmd=view&content_id=_613494_1&course_id=_8205_1">Lecture</a>
          <a href="/webapps/blackboard/content/listContent.jsp?course_id=_8205_1&content_id=_613493_1&mode=reset">Folder</a>
        </body></html>
        """
        urls = _extract_content_file_urls(
            html,
            "https://bb.sustech.edu.cn/webapps/blackboard/content/listContent.jsp?course_id=_8205_1&content_id=_613493_1&mode=reset",
        )
        self.assertEqual(
            urls,
            [
                "https://bb.sustech.edu.cn/webapps/blackboard/execute/content/file?cmd=view&content_id=_613494_1&course_id=_8205_1"
            ],
        )

    def test_parse_blackboard_material_page_extracts_download_url(self) -> None:
        html = """
        <html>
          <head><title>L01 course intro</title></head>
          <body>
            <li id="crumb_1">CS302 Operating Systems</li>
            <h1 id="pageTitleText">L01 course intro</h1>
            <iframe src="/bbcswebdav/pid-613494-dt-content-rid-19121934_1/courses/CS302-30015313-2026SP/L01%20course%20intro%281%29.pdf"></iframe>
          </body>
        </html>
        """
        title, content_id, course_name, download_url = _parse_blackboard_material_page(
            html,
            "https://bb.sustech.edu.cn/webapps/blackboard/execute/content/file?cmd=view&content_id=_613494_1&course_id=_8205_1",
        )
        self.assertEqual(title, "L01 course intro")
        self.assertEqual(content_id, "_613494_1")
        self.assertEqual(course_name, "CS302 Operating Systems")
        self.assertEqual(
            download_url,
            "https://bb.sustech.edu.cn/bbcswebdav/pid-613494-dt-content-rid-19121934_1/courses/CS302-30015313-2026SP/L01%20course%20intro%281%29.pdf",
        )

    def test_filename_from_response_uses_final_redirect_url(self) -> None:
        import httpx

        response = httpx.Response(
            200,
            headers={"Content-Type": "application/pdf"},
            request=httpx.Request(
                "GET", "https://bb.sustech.edu.cn/bbcswebdav/pid-613494/xid-19121934_1"
            ),
        )
        response._request.url = httpx.URL(
            "https://bb.sustech.edu.cn/bbcswebdav/pid-613494-dt-content-rid-19121934_1/courses/CS302-30015313-2026SP/L01%20course%20intro%281%29.pdf"
        )
        self.assertEqual(
            _filename_from_response(response, "fallback"), "L01 course intro(1).pdf"
        )


if __name__ == "__main__":
    unittest.main()
