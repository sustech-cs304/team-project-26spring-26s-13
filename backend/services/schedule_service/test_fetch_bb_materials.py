import unittest

import httpx

from backend.services.schedule_service import bb_materials
from unittest.mock import patch
from backend.services.schedule_service.fetch_bb import (
    _bbcswebdav_courses_url_from_cms_url,
    _extract_cms_course_file_urls,
    _extract_content_file_urls,
    _filename_from_response,
    _is_cms_course_file_url,
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

    def test_is_cms_course_file_url_accepts_details_action(self) -> None:
        self.assertTrue(
            _is_cms_course_file_url(
                "https://bb.sustech.edu.cn/webapps/cmsmain/webui/courses/CS304-30018694-2026SP/lecture1-introduction.pdf?action=details&subaction=generateFileMenuItem&uniq=gpifn4&course_id=_8012_1&ctxMenuXythosId=19081314_1"
            )
        )
        self.assertFalse(
            _is_cms_course_file_url(
                "https://bb.sustech.edu.cn/webapps/cmsmain/webui/courses/CS304-30018694-2026SP/lecture1-introduction.pdf?action=download&course_id=_8012_1"
            )
        )
        self.assertFalse(
            _is_cms_course_file_url(
                "https://bb.sustech.edu.cn/webapps/cmsmain/webui/courses/CS304-30018694-2026SP/lecture1-introduction.pdf?action=details"
            )
        )

    def test_extract_cms_course_file_urls_finds_lecture_details(self) -> None:
        html = """
        <html><body>
          <a data-href="/webapps/cmsmain/webui/courses/CS304-30018694-2026SP/lecture1-introduction.pdf?action=details&subaction=generateFileMenuItem&course_id=_8012_1&ctxMenuXythosId=19081314_1">Menu</a>
        </body></html>
        """
        urls = _extract_cms_course_file_urls(
            html,
            "https://bb.sustech.edu.cn/webapps/blackboard/content/listContent.jsp?course_id=_8012_1&content_id=_588340_1&mode=reset",
        )
        self.assertEqual(
            urls,
            [
                "https://bb.sustech.edu.cn/webapps/cmsmain/webui/courses/CS304-30018694-2026SP/lecture1-introduction.pdf?action=details&subaction=generateFileMenuItem&course_id=_8012_1&ctxMenuXythosId=19081314_1"
            ],
        )

    def test_bbcswebdav_courses_url_from_cms_url(self) -> None:
        self.assertEqual(
            _bbcswebdav_courses_url_from_cms_url(
                "https://bb.sustech.edu.cn/webapps/cmsmain/webui/courses/CS304-30018694-2026SP/lecture1-introduction.pdf?action=details&subaction=generateFileMenuItem&course_id=_8012_1&ctxMenuXythosId=19081314_1"
            ),
            "https://bb.sustech.edu.cn/bbcswebdav/courses/CS304-30018694-2026SP/lecture1-introduction.pdf",
        )


if __name__ == "__main__":
    unittest.main()


class TestFetchCmsCourseFileStrict(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_cms_course_file_strict_raises_on_menu_no_bbcswebdav(
        self,
    ) -> None:
        cms_url = (
            "https://bb.sustech.edu.cn/webapps/cmsmain/webui/courses/"
            "CS304-30018694-2026SP/lecture1-introduction.pdf"
            "?action=details&subaction=generateFileMenuItem&course_id=_8012_1&ctxMenuXythosId=19081314_1"
        )
        list_url = (
            "https://bb.sustech.edu.cn/webapps/blackboard/content/listContent.jsp"
            "?course_id=_8012_1&mode=reset"
        )

        async def stub_request_with_retry(
            _client: httpx.AsyncClient,
            method: str,
            url: str,
            headers: dict[str, str] | None = None,
            content: str | bytes | None = None,
            label: str = "",
        ) -> httpx.Response:
            if (
                method == "GET"
                and "action=download" in url
                and "/webapps/cmsmain/webui/courses/" in url
            ):
                return httpx.Response(
                    404,
                    request=httpx.Request(method, url),
                    headers={"Content-Type": "text/plain"},
                    content=b"Not Found",
                )
            if method == "GET" and url == list_url:
                return httpx.Response(
                    200,
                    request=httpx.Request(method, url),
                    headers={"Content-Type": "text/html"},
                    content=b"<html></html>",
                )
            if method == "POST" and url == cms_url:
                return httpx.Response(
                    200,
                    request=httpx.Request(method, url),
                    headers={"Content-Type": "text/x-json"},
                    content=b'{"ok": true}',
                )
            raise AssertionError(f"Unexpected request: {method} {url} label={label}")

        async with httpx.AsyncClient() as client:
            with patch.object(
                bb_materials, "_bbcswebdav_courses_url_from_cms_url", return_value=""
            ), patch.object(
                bb_materials, "_request_with_retry", stub_request_with_retry
            ):
                with self.assertRaises(
                    bb_materials.BlackboardMaterialFetchError
                ) as ctx:
                    await bb_materials._fetch_cms_course_file_material(
                        client,
                        cms_url,
                        "https://bb.sustech.edu.cn/webapps/portal/execute/defaultTab",
                        {},
                        strict=True,
                    )

        self.assertEqual(ctx.exception.step, "menu_no_bbcswebdav")

    async def test_fetch_cms_course_file_strict_raises_on_menu_403(self) -> None:
        cms_url = (
            "https://bb.sustech.edu.cn/webapps/cmsmain/webui/courses/"
            "CS304-30018694-2026SP/lecture1-introduction.pdf"
            "?action=details&subaction=generateFileMenuItem&course_id=_8012_1&ctxMenuXythosId=19081314_1"
        )
        list_url = (
            "https://bb.sustech.edu.cn/webapps/blackboard/content/listContent.jsp"
            "?course_id=_8012_1&mode=reset"
        )

        async def stub_request_with_retry(
            _client: httpx.AsyncClient,
            method: str,
            url: str,
            headers: dict[str, str] | None = None,
            content: str | bytes | None = None,
            label: str = "",
        ) -> httpx.Response:
            if (
                method == "GET"
                and "action=download" in url
                and "/webapps/cmsmain/webui/courses/" in url
            ):
                return httpx.Response(
                    404,
                    request=httpx.Request(method, url),
                    headers={"Content-Type": "text/plain"},
                    content=b"Not Found",
                )
            if method == "GET" and url == list_url:
                return httpx.Response(
                    200,
                    request=httpx.Request(method, url),
                    headers={"Content-Type": "text/html"},
                    content=b"<html></html>",
                )
            if method == "POST" and url == cms_url:
                return httpx.Response(
                    403,
                    request=httpx.Request(method, url),
                    headers={"Content-Type": "text/plain"},
                    content=b"Forbidden",
                )
            raise AssertionError(f"Unexpected request: {method} {url} label={label}")

        async with httpx.AsyncClient() as client:
            with patch.object(
                bb_materials, "_bbcswebdav_courses_url_from_cms_url", return_value=""
            ), patch.object(
                bb_materials, "_request_with_retry", stub_request_with_retry
            ):
                with self.assertRaises(
                    bb_materials.BlackboardMaterialFetchError
                ) as ctx:
                    await bb_materials._fetch_cms_course_file_material(
                        client,
                        cms_url,
                        "https://bb.sustech.edu.cn/webapps/portal/execute/defaultTab",
                        {},
                        strict=True,
                    )

        self.assertEqual(ctx.exception.step, "menu_http_status")
