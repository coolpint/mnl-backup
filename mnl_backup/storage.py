from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, List

from .models import ArticleImage, ArticleRecord


class ArchiveStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.db_path = self.data_dir / "db" / "backup.sqlite3"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        self._conn.close()

    def ensure_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS articles (
                idxno INTEGER PRIMARY KEY,
                source_url TEXT NOT NULL,
                canonical_url TEXT NOT NULL,
                site_name TEXT NOT NULL,
                language TEXT NOT NULL,
                headline TEXT NOT NULL,
                browser_title TEXT,
                summary TEXT,
                section_name TEXT,
                subsection_name TEXT,
                author_name TEXT,
                author_email TEXT,
                author_profile_url TEXT,
                published_at TEXT,
                updated_at TEXT,
                status TEXT NOT NULL DEFAULT 'published',
                body_html TEXT NOT NULL,
                body_text TEXT NOT NULL,
                source_html_path TEXT NOT NULL,
                xml_path TEXT NOT NULL,
                html_sha256 TEXT NOT NULL,
                body_sha256 TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                copyright_notice TEXT
            );

            CREATE TABLE IF NOT EXISTS article_assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_idxno INTEGER NOT NULL REFERENCES articles(idxno) ON DELETE CASCADE,
                ordinal INTEGER NOT NULL,
                role TEXT NOT NULL,
                source_url TEXT NOT NULL,
                local_path TEXT NOT NULL,
                mime_type TEXT,
                width INTEGER,
                height INTEGER,
                alt_text TEXT,
                caption TEXT,
                sha256 TEXT,
                downloaded_at TEXT NOT NULL,
                UNIQUE(article_idxno, ordinal)
            );

            CREATE TABLE IF NOT EXISTS sync_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mode TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                discovered_count INTEGER NOT NULL DEFAULT 0,
                fetched_count INTEGER NOT NULL DEFAULT 0,
                updated_count INTEGER NOT NULL DEFAULT 0,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS sync_run_articles (
                sync_run_id INTEGER NOT NULL REFERENCES sync_runs(id) ON DELETE CASCADE,
                article_idxno INTEGER NOT NULL REFERENCES articles(idxno) ON DELETE CASCADE,
                change_type TEXT NOT NULL,
                PRIMARY KEY (sync_run_id, article_idxno)
            );

            CREATE INDEX IF NOT EXISTS idx_sync_run_articles_article
            ON sync_run_articles(article_idxno);
            """
        )
        self._conn.commit()

    def begin_sync(self, mode: str, started_at: str) -> int:
        cursor = self._conn.execute(
            "INSERT INTO sync_runs (mode, started_at) VALUES (?, ?)",
            (mode, started_at),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def finish_sync(
        self,
        run_id: int,
        finished_at: str,
        discovered_count: int,
        fetched_count: int,
        updated_count: int,
        notes: str = "",
    ) -> None:
        self._conn.execute(
            """
            UPDATE sync_runs
            SET finished_at = ?, discovered_count = ?, fetched_count = ?, updated_count = ?, notes = ?
            WHERE id = ?
            """,
            (finished_at, discovered_count, fetched_count, updated_count, notes, run_id),
        )
        self._conn.commit()

    def get_known_article_ids(self, idxnos: Iterable[int]) -> set:
        idxno_list = list(dict.fromkeys(int(value) for value in idxnos))
        if not idxno_list:
            return set()
        placeholders = ",".join("?" for _ in idxno_list)
        rows = self._conn.execute(
            f"SELECT idxno FROM articles WHERE idxno IN ({placeholders})",
            idxno_list,
        ).fetchall()
        return {int(row["idxno"]) for row in rows}

    def article_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS count FROM articles").fetchone()
        return int(row["count"])

    def upsert_article(
        self,
        record: ArticleRecord,
        source_html_path: str,
        xml_path: str,
    ) -> str | None:
        existing = self._conn.execute(
            "SELECT first_seen_at, html_sha256, body_sha256, updated_at FROM articles WHERE idxno = ?",
            (record.idxno,),
        ).fetchone()
        first_seen_at = existing["first_seen_at"] if existing else record.first_seen_at
        changed = (
            existing is None
            or existing["html_sha256"] != record.html_sha256
            or existing["body_sha256"] != record.body_sha256
            or (existing["updated_at"] or "") != record.updated_at
        )

        self._conn.execute(
            """
            INSERT INTO articles (
                idxno, source_url, canonical_url, site_name, language, headline,
                browser_title, summary, section_name, subsection_name, author_name,
                author_email, author_profile_url, published_at, updated_at, status,
                body_html, body_text, source_html_path, xml_path, html_sha256,
                body_sha256, first_seen_at, last_seen_at, fetched_at, copyright_notice
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(idxno) DO UPDATE SET
                source_url = excluded.source_url,
                canonical_url = excluded.canonical_url,
                site_name = excluded.site_name,
                language = excluded.language,
                headline = excluded.headline,
                browser_title = excluded.browser_title,
                summary = excluded.summary,
                section_name = excluded.section_name,
                subsection_name = excluded.subsection_name,
                author_name = excluded.author_name,
                author_email = excluded.author_email,
                author_profile_url = excluded.author_profile_url,
                published_at = excluded.published_at,
                updated_at = excluded.updated_at,
                status = excluded.status,
                body_html = excluded.body_html,
                body_text = excluded.body_text,
                source_html_path = excluded.source_html_path,
                xml_path = excluded.xml_path,
                html_sha256 = excluded.html_sha256,
                body_sha256 = excluded.body_sha256,
                last_seen_at = excluded.last_seen_at,
                fetched_at = excluded.fetched_at,
                copyright_notice = excluded.copyright_notice
            """,
            (
                record.idxno,
                record.source_url,
                record.canonical_url,
                record.site_name,
                record.language,
                record.headline,
                record.browser_title,
                record.summary,
                record.section,
                record.subsection,
                record.author_name,
                record.author_email,
                record.author_profile_url,
                record.published_at,
                record.updated_at,
                record.status,
                record.body_html,
                record.body_text,
                source_html_path,
                xml_path,
                record.html_sha256,
                record.body_sha256,
                first_seen_at,
                record.last_seen_at,
                record.fetched_at,
                record.copyright_notice,
            ),
        )
        self._conn.commit()
        if existing is None:
            return "created"
        if changed:
            return "updated"
        return None

    def record_run_article(self, run_id: int, article_idxno: int, change_type: str) -> None:
        self._conn.execute(
            """
            INSERT INTO sync_run_articles (sync_run_id, article_idxno, change_type)
            VALUES (?, ?, ?)
            ON CONFLICT(sync_run_id, article_idxno) DO UPDATE SET
                change_type = excluded.change_type
            """,
            (run_id, article_idxno, change_type),
        )
        self._conn.commit()

    def replace_assets(self, article_idxno: int, images: List[ArticleImage], downloaded_at: str) -> None:
        self._conn.execute("DELETE FROM article_assets WHERE article_idxno = ?", (article_idxno,))
        for ordinal, image in enumerate(images, start=1):
            self._conn.execute(
                """
                INSERT INTO article_assets (
                    article_idxno, ordinal, role, source_url, local_path,
                    mime_type, width, height, alt_text, caption, sha256, downloaded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article_idxno,
                    ordinal,
                    image.role,
                    image.source_url,
                    image.local_path or "",
                    image.mime_type,
                    image.width,
                    image.height,
                    image.alt_text,
                    image.caption,
                    image.sha256,
                    downloaded_at,
                ),
        )
        self._conn.commit()

    def fetch_asset_rows(self, article_idxno: int) -> List[sqlite3.Row]:
        return self._conn.execute(
            """
            SELECT
                ordinal, role, source_url, local_path, mime_type, width, height,
                alt_text, caption, sha256
            FROM article_assets
            WHERE article_idxno = ?
            ORDER BY ordinal
            """,
            (article_idxno,),
        ).fetchall()

    def fetch_manifest_rows(self) -> List[sqlite3.Row]:
        return self._conn.execute(
            """
            SELECT
                idxno, canonical_url, headline, section_name, subsection_name,
                author_name, published_at, updated_at, xml_path, source_html_path,
                fetched_at, first_seen_at, last_seen_at, html_sha256, body_sha256
            FROM articles
            ORDER BY COALESCE(published_at, '') DESC, idxno DESC
            """
        ).fetchall()

    def fetch_article_row(self, article_idxno: int) -> sqlite3.Row:
        row = self._conn.execute(
            """
            SELECT
                idxno, source_url, canonical_url, site_name, language, headline,
                browser_title, summary, section_name, subsection_name, author_name,
                author_email, author_profile_url, published_at, updated_at, status,
                body_html, body_text, source_html_path, xml_path, html_sha256,
                body_sha256, first_seen_at, last_seen_at, fetched_at, copyright_notice
            FROM articles
            WHERE idxno = ?
            """,
            (article_idxno,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown article: {article_idxno}")
        return row

    def fetch_sync_run(self, run_id: int) -> sqlite3.Row:
        row = self._conn.execute(
            """
            SELECT
                id, mode, started_at, finished_at, discovered_count,
                fetched_count, updated_count, notes
            FROM sync_runs
            WHERE id = ?
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown sync run: {run_id}")
        return row

    def fetch_run_manifest_rows(self, run_id: int) -> List[sqlite3.Row]:
        return self._conn.execute(
            """
            SELECT
                sra.change_type,
                a.idxno,
                a.canonical_url,
                a.headline,
                a.section_name,
                a.subsection_name,
                a.author_name,
                a.published_at,
                a.updated_at,
                a.xml_path,
                a.source_html_path,
                a.fetched_at,
                a.first_seen_at,
                a.last_seen_at,
                a.html_sha256,
                a.body_sha256
            FROM sync_run_articles AS sra
            JOIN articles AS a
                ON a.idxno = sra.article_idxno
            WHERE sra.sync_run_id = ?
            ORDER BY COALESCE(a.published_at, '') DESC, a.idxno DESC
            """,
            (run_id,),
        ).fetchall()

    def fetch_run_package_paths(self, run_id: int) -> List[str]:
        rows = self._conn.execute(
            """
            SELECT a.xml_path AS path
            FROM sync_run_articles AS sra
            JOIN articles AS a
                ON a.idxno = sra.article_idxno
            WHERE sra.sync_run_id = ?
            UNION
            SELECT a.source_html_path AS path
            FROM sync_run_articles AS sra
            JOIN articles AS a
                ON a.idxno = sra.article_idxno
            WHERE sra.sync_run_id = ?
            UNION
            SELECT aa.local_path AS path
            FROM sync_run_articles AS sra
            JOIN article_assets AS aa
                ON aa.article_idxno = sra.article_idxno
            WHERE sra.sync_run_id = ?
            """,
            (run_id, run_id, run_id),
        ).fetchall()
        return [row["path"] for row in rows if row["path"]]

    def fetch_stats(self) -> sqlite3.Row:
        return self._conn.execute(
            """
            SELECT
                COUNT(*) AS article_count,
                COUNT(DISTINCT section_name) AS section_count,
                MAX(published_at) AS latest_published_at
            FROM articles
            """
        ).fetchone()

    def fetch_recent_articles(self, limit: int = 5) -> List[sqlite3.Row]:
        return self._conn.execute(
            """
            SELECT idxno, headline, published_at, section_name, xml_path
            FROM articles
            ORDER BY COALESCE(published_at, '') DESC, idxno DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
