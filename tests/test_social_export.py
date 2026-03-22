from pathlib import Path
from tempfile import TemporaryDirectory
import json
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


class SocialExportTests(unittest.TestCase):
    def test_social_export_creates_self_contained_packages_for_all_run_articles(self) -> None:
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
                result = service.export_social_packages(
                    run_id=summary.run_id,
                    output_root=Path(temp_dir) / "exports" / "social",
                )

                self.assertEqual(result.article_count, 2)
                self.assertTrue(result.batch_manifest_path.exists())
                self.assertTrue(result.notification_path.exists())
                self.assertTrue(result.relative_dir.endswith("run-000001"))

                batch_payload = json.loads(result.batch_manifest_path.read_text(encoding="utf-8"))
                self.assertEqual(batch_payload["run"]["id"], summary.run_id)
                self.assertEqual(batch_payload["article_count"], 2)
                self.assertEqual(batch_payload["relative_dir"], result.relative_dir)
                self.assertIn("status_contract", batch_payload)
                self.assertIn("{platform}", batch_payload["status_contract"]["batch_path_template"])

                notification_payload = json.loads(result.notification_path.read_text(encoding="utf-8"))
                self.assertEqual(notification_payload["run"]["id"], summary.run_id)
                self.assertEqual(notification_payload["article_count"], 2)
                self.assertEqual(notification_payload["batch_manifest"], "batch.json")
                self.assertEqual(notification_payload["status_contract"]["relative_dir"], result.relative_dir)

                package_dir_143 = result.batch_dir / "article-000143"
                package_dir_94 = result.batch_dir / "article-000094"
                self.assertTrue((package_dir_143 / "package.json").exists())
                self.assertTrue((package_dir_143 / "article.json").exists())
                self.assertTrue((package_dir_143 / "rights.json").exists())
                self.assertTrue((package_dir_143 / "article.xml").exists())
                self.assertTrue((package_dir_143 / "source.html").exists())
                self.assertTrue((package_dir_143 / "body.txt").exists())
                self.assertTrue((package_dir_143 / "assets" / "source-media" / "01.jpg").exists())

                package_143 = json.loads((package_dir_143 / "package.json").read_text(encoding="utf-8"))
                self.assertEqual(package_143["article"]["idxno"], 143)
                self.assertEqual(package_143["assets"]["count"], 1)
                self.assertEqual(package_143["platforms"]["youtube_shorts"]["status"], "pending")
                self.assertEqual(
                    package_143["platforms"]["youtube_shorts"]["status_paths"]["article"],
                    f"social/status/youtube_shorts/{result.relative_dir}/article-000143.json",
                )

                article_143_payload = json.loads((package_dir_143 / "article.json").read_text(encoding="utf-8"))
                self.assertEqual(article_143_payload["article"]["change_type"], "created")
                self.assertEqual(len(article_143_payload["assets"]), 1)
                self.assertEqual(article_143_payload["assets"][0]["packaged_path"], "assets/source-media/01.jpg")

                rights_143 = json.loads((package_dir_143 / "rights.json").read_text(encoding="utf-8"))
                self.assertFalse(rights_143["media"][0]["social_use_allowed"])

                package_94 = json.loads((package_dir_94 / "package.json").read_text(encoding="utf-8"))
                self.assertEqual(package_94["assets"]["count"], 0)
                self.assertEqual(package_94["files"]["article_json"], "article.json")
            finally:
                service.close()


if __name__ == "__main__":
    unittest.main()
