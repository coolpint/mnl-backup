from pathlib import Path
import unittest

from mnl_backup.parsers import parse_article_html, parse_list_page


FIXTURE_DIR = Path(__file__).parent / "fixtures"


class ParserTests(unittest.TestCase):
    def test_parse_list_page_extracts_total_and_first_article(self) -> None:
        html_text = (FIXTURE_DIR / "list_page1.html").read_text(encoding="utf-8")
        page = parse_list_page(html_text, page_number=1)

        self.assertEqual(page.total_count, 73)
        self.assertEqual(page.list_per_page, 20)
        self.assertGreaterEqual(len(page.items), 10)
        self.assertEqual(page.items[0].idxno, 132)
        self.assertEqual(page.items[0].section, "경제")
        self.assertEqual(page.items[0].author_name, "최보람 기자")

    def test_parse_article_with_primary_image(self) -> None:
        html_text = (FIXTURE_DIR / "article_143.html").read_text(encoding="utf-8")
        article = parse_article_html(
            html_text,
            "https://www.moneynlaw.co.kr/news/articleView.html?idxno=143",
        )

        self.assertEqual(article.idxno, 143)
        self.assertEqual(article.section, "경제")
        self.assertEqual(article.subsection, "인사이트")
        self.assertEqual(article.author_name, "머니앤로")
        self.assertEqual(article.published_at, "2026-03-07T16:50:00+09:00")
        self.assertTrue(article.images)
        self.assertEqual(article.images[0].role, "primary")
        self.assertIn("속도전", article.body_text)

    def test_parse_article_without_inline_image_does_not_keep_site_logo(self) -> None:
        html_text = (FIXTURE_DIR / "article_94.html").read_text(encoding="utf-8")
        article = parse_article_html(
            html_text,
            "https://www.moneynlaw.co.kr/news/articleView.html?idxno=94",
        )

        self.assertEqual(article.idxno, 94)
        self.assertEqual(article.images, [])
        self.assertIn("캐나다 브리티시컬럼비아주", article.body_text)


if __name__ == "__main__":
    unittest.main()

