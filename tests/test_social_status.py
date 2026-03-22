from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from mnl_backup.http import HttpResponse
from mnl_backup.service import BackupService
from mnl_backup.social_status import (
    build_article_status_path,
    build_article_status_payload,
    build_batch_status_path,
    build_batch_status_payload,
)


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


class SocialStatusTests(unittest.TestCase):
    def test_publisher_simulation_can_consume_notification_and_write_status_files(self) -> None:
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
            base = Path(temp_dir)
            service = BackupService(base / "data", client=client)
            try:
                summary = service.sync(max_pages=1, limit=2, delay_seconds=0)
                result = service.export_social_packages(
                    run_id=summary.run_id,
                    output_root=base / "exports" / "social",
                )

                notification = json.loads(result.notification_path.read_text(encoding="utf-8"))
                batch = json.loads(result.batch_manifest_path.read_text(encoding="utf-8"))
                platform = "youtube_shorts"

                batch_status_path = base / build_batch_status_path(platform, result.relative_dir)
                batch_status_path.parent.mkdir(parents=True, exist_ok=True)
                batch_status = build_batch_status_payload(
                    platform=platform,
                    relative_dir=result.relative_dir,
                    run_id=summary.run_id,
                    state="building",
                    article_count=notification["article_count"],
                    processed_count=0,
                )
                batch_status_path.write_text(json.dumps(batch_status, ensure_ascii=False, indent=2), encoding="utf-8")

                processed_count = 0
                for package_info in batch["packages"]:
                    package_dir = result.batch_dir / package_info["package_dir"]
                    package_payload = json.loads((package_dir / "package.json").read_text(encoding="utf-8"))
                    article_idxno = package_payload["article"]["idxno"]

                    article_status_path = base / build_article_status_path(platform, result.relative_dir, article_idxno)
                    article_status_path.parent.mkdir(parents=True, exist_ok=True)
                    article_status = build_article_status_payload(
                        platform=platform,
                        relative_dir=result.relative_dir,
                        run_id=summary.run_id,
                        article_idxno=article_idxno,
                        state="review_required",
                        package_dir=package_info["package_dir"],
                        package_path=package_info["package_path"],
                        detail="Rendered preview and queued for human review.",
                        output_path=f"review/article-{article_idxno:06d}/preview.mp4",
                    )
                    article_status_path.write_text(
                        json.dumps(article_status, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    processed_count += 1

                completed_batch_status = build_batch_status_payload(
                    platform=platform,
                    relative_dir=result.relative_dir,
                    run_id=summary.run_id,
                    state="review_required",
                    article_count=notification["article_count"],
                    processed_count=processed_count,
                )
                batch_status_path.write_text(
                    json.dumps(completed_batch_status, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

                self.assertTrue(batch_status_path.exists())
                final_batch_status = json.loads(batch_status_path.read_text(encoding="utf-8"))
                self.assertEqual(final_batch_status["processed_count"], 2)
                self.assertEqual(final_batch_status["state"], "review_required")

                article_status_143 = base / build_article_status_path(platform, result.relative_dir, 143)
                self.assertTrue(article_status_143.exists())
                article_payload_143 = json.loads(article_status_143.read_text(encoding="utf-8"))
                self.assertEqual(article_payload_143["state"], "review_required")
                self.assertEqual(article_payload_143["package_path"], "article-000143/package.json")
            finally:
                service.close()


if __name__ == "__main__":
    unittest.main()
