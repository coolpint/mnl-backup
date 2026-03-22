from pathlib import Path
from tempfile import TemporaryDirectory
import tarfile
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
                self.assertEqual(summary.run_id, 1)

                stats = service.stats()
                self.assertEqual(stats["article_count"], 2)

                xml_path = Path(temp_dir) / "archive" / "2026" / "03" / "xml" / "000143.xml"
                html_path = Path(temp_dir) / "archive" / "2026" / "03" / "html" / "000143.html"
                image_path = Path(temp_dir) / "archive" / "2026" / "03" / "media" / "000143" / "01.jpg"
                manifest_path = Path(temp_dir) / "archive" / "manifests" / "articles.xml"
                run_manifest_path = Path(temp_dir) / "archive" / "manifests" / "runs" / "run-000001.xml"

                self.assertTrue(xml_path.exists())
                self.assertTrue(html_path.exists())
                self.assertTrue(image_path.exists())
                self.assertTrue(manifest_path.exists())
                self.assertTrue(run_manifest_path.exists())
                self.assertIn("articleArchive", xml_path.read_text(encoding="utf-8"))
                self.assertIn('changeType="created"', run_manifest_path.read_text(encoding="utf-8"))

                incremental = service.create_incremental_package(
                    run_id=summary.run_id,
                    output_root=Path(temp_dir) / "exports",
                )
                self.assertTrue(incremental.package_path.exists())
                with tarfile.open(incremental.package_path, "r:gz") as archive:
                    names = set(archive.getnames())
                archive_root = Path(temp_dir).name
                self.assertIn(f"{archive_root}/archive/manifests/articles.xml", names)
                self.assertIn(f"{archive_root}/archive/manifests/runs/run-000001.xml", names)
                self.assertIn(f"{archive_root}/archive/2026/03/xml/000143.xml", names)
                self.assertIn(f"{archive_root}/archive/2026/03/html/000143.html", names)
                self.assertIn(f"{archive_root}/archive/2026/03/media/000143/01.jpg", names)

                full_package = service.create_full_package(output_root=Path(temp_dir) / "exports")
                self.assertTrue(full_package.package_path.exists())
                with tarfile.open(full_package.package_path, "r:gz") as archive:
                    names = set(archive.getnames())
                self.assertIn(f"{archive_root}/db/backup.sqlite3", names)

                state_snapshot = service.create_state_snapshot(output_root=Path(temp_dir) / "runtime")
                self.assertTrue(state_snapshot.exists())
            finally:
                service.close()

    def test_incremental_sync_catches_up_articles_after_missed_day(self) -> None:
        initial_client = FakeHttpClient(
            {
                "https://www.moneynlaw.co.kr/news/articleList.html?page=1&view_type=sm": (
                    200,
                    {"content-type": "text/html; charset=utf-8"},
                    build_list_page_html(
                        [
                            (104, "경제", "03-18 09:00"),
                            (103, "경제", "03-18 08:00"),
                        ],
                        total_count=4,
                        list_per_page=2,
                    ).encode("utf-8"),
                ),
                "https://www.moneynlaw.co.kr/news/articleList.html?page=2&view_type=sm": (
                    200,
                    {"content-type": "text/html; charset=utf-8"},
                    build_list_page_html(
                        [
                            (102, "사회", "03-17 18:00"),
                            (101, "사회", "03-17 17:00"),
                        ],
                        total_count=4,
                        list_per_page=2,
                    ).encode("utf-8"),
                ),
                **article_response_map([101, 102, 103, 104]),
            }
        )

        catchup_client = FakeHttpClient(
            {
                "https://www.moneynlaw.co.kr/news/articleList.html?page=1&view_type=sm": (
                    200,
                    {"content-type": "text/html; charset=utf-8"},
                    build_list_page_html(
                        [
                            (108, "경제", "03-20 09:30"),
                            (107, "경제", "03-20 09:00"),
                        ],
                        total_count=8,
                        list_per_page=2,
                    ).encode("utf-8"),
                ),
                "https://www.moneynlaw.co.kr/news/articleList.html?page=2&view_type=sm": (
                    200,
                    {"content-type": "text/html; charset=utf-8"},
                    build_list_page_html(
                        [
                            (106, "경제", "03-19 18:00"),
                            (105, "경제", "03-19 17:00"),
                        ],
                        total_count=8,
                        list_per_page=2,
                    ).encode("utf-8"),
                ),
                "https://www.moneynlaw.co.kr/news/articleList.html?page=3&view_type=sm": (
                    200,
                    {"content-type": "text/html; charset=utf-8"},
                    build_list_page_html(
                        [
                            (104, "경제", "03-18 09:00"),
                            (103, "경제", "03-18 08:00"),
                        ],
                        total_count=8,
                        list_per_page=2,
                    ).encode("utf-8"),
                ),
                "https://www.moneynlaw.co.kr/news/articleList.html?page=4&view_type=sm": (
                    200,
                    {"content-type": "text/html; charset=utf-8"},
                    build_list_page_html(
                        [
                            (102, "사회", "03-17 18:00"),
                            (101, "사회", "03-17 17:00"),
                        ],
                        total_count=8,
                        list_per_page=2,
                    ).encode("utf-8"),
                ),
                **article_response_map([105, 106, 107, 108]),
            }
        )

        with TemporaryDirectory() as temp_dir:
            service = BackupService(Path(temp_dir), client=initial_client)
            try:
                first_summary = service.sync(full=True, max_pages=2, delay_seconds=0)
                self.assertEqual(first_summary.errors, [])
                self.assertEqual(first_summary.updated_count, 4)
            finally:
                service.close()

            catchup_service = BackupService(Path(temp_dir), client=catchup_client)
            try:
                second_summary = catchup_service.sync(refresh_pages=2, delay_seconds=0)
                self.assertEqual(second_summary.errors, [])
                self.assertEqual(second_summary.mode, "incremental")
                self.assertEqual(second_summary.fetched_count, 4)
                self.assertEqual(second_summary.updated_count, 4)
                self.assertEqual(second_summary.discovered_count, 6)

                stats = catchup_service.stats()
                self.assertEqual(stats["article_count"], 8)

                for idxno in (105, 106, 107, 108):
                    xml_path = Path(temp_dir) / "archive" / "2026" / "03" / "xml" / f"{idxno:06d}.xml"
                    self.assertTrue(xml_path.exists(), f"missing xml for {idxno}")

                run_manifest = (
                    Path(temp_dir) / "archive" / "manifests" / "runs" / "run-000002.xml"
                ).read_text(encoding="utf-8")
                for idxno in (105, 106, 107, 108):
                    self.assertIn(f'idxno="{idxno}"', run_manifest)
                self.assertNotIn('idxno="104"', run_manifest)
                self.assertNotIn('idxno="103"', run_manifest)

                incremental = catchup_service.create_incremental_package(
                    run_id=second_summary.run_id,
                    output_root=Path(temp_dir) / "exports",
                )
                with tarfile.open(incremental.package_path, "r:gz") as archive:
                    names = set(archive.getnames())
                archive_root = Path(temp_dir).name
                for idxno in (105, 106, 107, 108):
                    self.assertIn(
                        f"{archive_root}/archive/2026/03/xml/{idxno:06d}.xml",
                        names,
                    )
                self.assertNotIn(f"{archive_root}/archive/2026/03/xml/000104.xml", names)
            finally:
                catchup_service.close()


def build_list_page_html(items, total_count: int, list_per_page: int) -> str:
    item_html = []
    for idxno, section, published_label in items:
        item_html.append(
            f"""
              <li class="altlist-webzine-item">
                <div class="altlist-webzine-content">
                  <H2 class="altlist-subject"><a href="https://www.moneynlaw.co.kr/news/articleView.html?idxno={idxno}">기사 {idxno}</a></H2>
                  <div class="altlist-info">
                    <div class="altlist-info-item">{section}</div>
                    <div class="altlist-info-item">머니앤로</div>
                    <div class="altlist-info-item">{published_label}</div>
                  </div>
                </div>
              </li>
            """
        )

    return f"""
        <div id="sections" class="altlist">
          <header class="altlist-header">
            <H1 class="altlist-title">전체기사 <small class="altlist-count">총 <strong>{total_count}</strong>건의 기사가 있습니다.</small></H1>
          </header>
          <article id="section-list" class="altlist-body">
            <ul class="altlist-webzine">
              {''.join(item_html)}
            </ul>
            <script>
            params['list_per_page'] = "{list_per_page}";
            </script>
          </article>
        </div>
    """


def article_response_map(idxnos) -> dict:
    return {
        f"https://www.moneynlaw.co.kr/news/articleView.html?idxno={idxno}": (
            200,
            {"content-type": "text/html; charset=utf-8"},
            build_article_html(idxno).encode("utf-8"),
        )
        for idxno in idxnos
    }


def build_article_html(idxno: int) -> str:
    return f"""
        <!doctype html>
        <html lang="ko">
        <head>
        <meta property="og:site_name" content="머니앤로" />
        <meta property="og:url" content="https://www.moneynlaw.co.kr/news/articleView.html?idxno={idxno}" />
        <meta property="og:title" content="기사 {idxno} - 머니앤로" />
        <meta property="description" content="기사 {idxno} 요약" />
        <meta property="article:section" content="경제" />
        <meta property="article:published_time" content="2026-03-20T09:00:00+09:00" />
        <title>기사 {idxno} - 머니앤로</title>
        </head>
        <body>
          <article id="article-view-content-div">
            <p>기사 {idxno} 본문</p>
          </article>
          <article class="article-copyright">머니앤로</article>
        </body>
        </html>
    """


if __name__ == "__main__":
    unittest.main()
