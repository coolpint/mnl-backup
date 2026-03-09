from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from mnl_backup.http import HttpResponse
from mnl_backup.service import BackupService


FIXTURE_DIR = Path(__file__).parent / "fixtures"


class FakeHttpClient:
    def __init__(self, responses):
        self.responses = responses

    def fetch(self, url: str) -> HttpResponse:
        if url not in self.responses:
            raise AssertionError(f"Unexpected URL requested: {url}")
        status_code, headers, content = self.responses[url]
        return HttpResponse(
            requested_url=url,
            final_url=url,
            status_code=status_code,
            headers=headers,
            content=content,
        )


class ServiceTests(unittest.TestCase):
    def test_sync_writes_db_xml_and_manifest(self) -> None:
        synthetic_list = """
        <div id="sections" class="altlist">
          <header class="altlist-header">
            <H1 class="altlist-title">전체기사 <small class="altlist-count">총 <strong>2</strong>건의 기사가 있습니다.</small></H1>
          </header>
          <article id="section-list" class="altlist-body">
            <ul class="altlist-webzine">
              <li class="altlist-webzine-item">
                <div class="altlist-webzine-content">
                  <H2 class="altlist-subject"><a href="https://www.moneynlaw.co.kr/news/articleView.html?idxno=143">기사 143</a></H2>
                  <div class="altlist-info">
                    <div class="altlist-info-item">경제</div>
                    <div class="altlist-info-item">머니앤로</div>
                    <div class="altlist-info-item">03-07 16:50</div>
                  </div>
                </div>
              </li>
              <li class="altlist-webzine-item">
                <div class="altlist-webzine-content">
                  <H2 class="altlist-subject"><a href="https://www.moneynlaw.co.kr/news/articleView.html?idxno=94">기사 94</a></H2>
                  <div class="altlist-info">
                    <div class="altlist-info-item">사회</div>
                    <div class="altlist-info-item">머니앤로</div>
                    <div class="altlist-info-item">02-22 07:47</div>
                  </div>
                </div>
              </li>
            </ul>
            <script>
            params['list_per_page'] = "20";
            </script>
          </article>
        </div>
        """
        article_143 = (FIXTURE_DIR / "article_143.html").read_bytes()
        article_94 = (FIXTURE_DIR / "article_94.html").read_bytes()
        image_bytes = b"\xff\xd8\xff\xdbfakejpeg"

        client = FakeHttpClient(
            {
                "https://www.moneynlaw.co.kr/news/articleList.html?page=1&view_type=sm": (
                    200,
                    {"content-type": "text/html; charset=utf-8"},
                    synthetic_list.encode("utf-8"),
                ),
                "https://www.moneynlaw.co.kr/news/articleView.html?idxno=143": (
                    200,
                    {"content-type": "text/html; charset=utf-8"},
                    article_143,
                ),
                "https://www.moneynlaw.co.kr/news/articleView.html?idxno=94": (
                    200,
                    {"content-type": "text/html; charset=utf-8"},
                    article_94,
                ),
                "https://cdn.moneynlaw.co.kr/news/photo/202603/143_106_2019.jpg": (
                    200,
                    {"content-type": "image/jpeg"},
                    image_bytes,
                ),
            }
        )

        with TemporaryDirectory() as temp_dir:
            service = BackupService(Path(temp_dir), client=client)
            try:
                summary = service.sync(max_pages=1, limit=2, delay_seconds=0)
                self.assertEqual(summary.errors, [])
                self.assertEqual(summary.fetched_count, 2)

                stats = service.stats()
                self.assertEqual(stats["article_count"], 2)

                xml_path = Path(temp_dir) / "archive" / "2026" / "03" / "xml" / "000143.xml"
                html_path = Path(temp_dir) / "archive" / "2026" / "03" / "html" / "000143.html"
                image_path = Path(temp_dir) / "archive" / "2026" / "03" / "media" / "000143" / "01.jpg"
                manifest_path = Path(temp_dir) / "archive" / "manifests" / "articles.xml"

                self.assertTrue(xml_path.exists())
                self.assertTrue(html_path.exists())
                self.assertTrue(image_path.exists())
                self.assertTrue(manifest_path.exists())
                self.assertIn("articleArchive", xml_path.read_text(encoding="utf-8"))
            finally:
                service.close()


if __name__ == "__main__":
    unittest.main()
