from __future__ import annotations

import hashlib
import math
import mimetypes
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from .http import HttpClient
from .models import ArticleImage, ArticleRecord, ListArticleRef
from .packages import (
    PackageResult,
    create_full_package,
    create_incremental_package,
    create_state_snapshot as create_state_package,
)
from .parsers import parse_article_html, parse_list_page
from .social_export import SocialExportResult, create_social_export_batch
from .snapshot import restore_snapshot
from .storage import ArchiveStore
from .xml_export import build_article_xml, build_manifest_xml, build_run_manifest_xml, write_bytes


LIST_URL_TEMPLATE = "https://www.moneynlaw.co.kr/news/articleList.html?page={page}&view_type=sm"


@dataclass
class SyncSummary:
    run_id: int
    mode: str
    discovered_count: int
    fetched_count: int
    updated_count: int
    manifest_path: str
    run_manifest_path: str
    errors: List[str] = field(default_factory=list)


class BackupService:
    def __init__(self, data_dir: Path, client: Optional[HttpClient] = None) -> None:
        self.data_dir = Path(data_dir)
        self.client = client or HttpClient()
        self.store = ArchiveStore(self.data_dir)
        self.store.ensure_schema()

    def close(self) -> None:
        self.store.close()

    def sync(
        self,
        full: bool = False,
        max_pages: Optional[int] = None,
        refresh_pages: int = 2,
        delay_seconds: float = 0.2,
        limit: Optional[int] = None,
    ) -> SyncSummary:
        started_at = utc_now()
        mode = "full" if full or self.store.article_count() == 0 else "incremental"
        run_id = self.store.begin_sync(mode=mode, started_at=started_at)
        errors: List[str] = []
        updated_count = 0
        fetched_count = 0

        discovered_refs = self._discover_article_refs(
            full=(mode == "full"),
            max_pages=max_pages,
            refresh_pages=refresh_pages,
            delay_seconds=delay_seconds,
        )
        refs_to_fetch = self._select_refs_to_fetch(
            discovered_refs,
            full=(mode == "full"),
            refresh_pages=refresh_pages,
            limit=limit,
        )

        for ref in refs_to_fetch:
            try:
                change_type = self._fetch_and_store_article(ref)
                fetched_count += 1
                if change_type:
                    updated_count += 1
                    self.store.record_run_article(run_id, ref.idxno, change_type)
                if delay_seconds:
                    time.sleep(delay_seconds)
            except Exception as exc:  # pragma: no cover - exercised by real runs
                errors.append(f"{ref.idxno}: {exc}")

        manifest_path = self.export_manifest()
        finished_at = utc_now()
        notes = ""
        if errors:
            notes = "\n".join(errors[:20])
        self.store.finish_sync(
            run_id=run_id,
            finished_at=finished_at,
            discovered_count=len(discovered_refs),
            fetched_count=fetched_count,
            updated_count=updated_count,
            notes=notes,
        )
        run_manifest_path = self.export_run_manifest(run_id)
        return SyncSummary(
            run_id=run_id,
            mode=mode,
            discovered_count=len(discovered_refs),
            fetched_count=fetched_count,
            updated_count=updated_count,
            manifest_path=manifest_path,
            run_manifest_path=run_manifest_path,
            errors=errors,
        )

    def export_manifest(self) -> str:
        rows = self.store.fetch_manifest_rows()
        manifest_rel = Path("archive") / "manifests" / "articles.xml"
        write_bytes(self.data_dir / manifest_rel, build_manifest_xml(rows))
        return manifest_rel.as_posix()

    def export_run_manifest(self, run_id: int) -> str:
        run_row = self.store.fetch_sync_run(run_id)
        rows = self.store.fetch_run_manifest_rows(run_id)
        manifest_rel = Path("archive") / "manifests" / "runs" / f"run-{run_id:06d}.xml"
        write_bytes(self.data_dir / manifest_rel, build_run_manifest_xml(run_row, rows))
        return manifest_rel.as_posix()

    def create_incremental_package(
        self,
        run_id: int,
        output_root: Path,
        timestamp: Optional[datetime] = None,
    ) -> PackageResult:
        run_manifest_path = self.export_run_manifest(run_id)
        rel_paths = self.store.fetch_run_package_paths(run_id)
        rel_paths.extend(
            [
                "archive/manifests/articles.xml",
                run_manifest_path,
            ]
        )
        run_row = self.store.fetch_sync_run(run_id)
        return create_incremental_package(
            data_dir=self.data_dir,
            output_root=Path(output_root),
            run_id=run_id,
            rel_paths=rel_paths,
            article_count=int(run_row["updated_count"] or 0),
            timestamp=timestamp,
        )

    def create_full_package(
        self,
        output_root: Path,
        timestamp: Optional[datetime] = None,
    ) -> PackageResult:
        return create_full_package(
            data_dir=self.data_dir,
            output_root=Path(output_root),
            timestamp=timestamp,
            article_count=self.store.article_count(),
        )

    def create_state_snapshot(self, output_root: Path) -> Path:
        return create_state_package(data_dir=self.data_dir, output_root=Path(output_root))

    def export_social_packages(
        self,
        run_id: int,
        output_root: Path,
        timestamp: Optional[datetime] = None,
    ) -> SocialExportResult:
        run_row = self.store.fetch_sync_run(run_id)
        run_articles = self.store.fetch_run_manifest_rows(run_id)
        article_payloads = []
        for row in run_articles:
            article_row = self.store.fetch_article_row(int(row["idxno"]))
            asset_rows = self.store.fetch_asset_rows(int(row["idxno"]))
            article_payloads.append(
                {
                    "idxno": int(article_row["idxno"]),
                    "source_url": article_row["source_url"],
                    "canonical_url": article_row["canonical_url"],
                    "site_name": article_row["site_name"],
                    "language": article_row["language"],
                    "headline": article_row["headline"],
                    "browser_title": article_row["browser_title"] or "",
                    "summary": article_row["summary"] or "",
                    "section_name": article_row["section_name"] or "",
                    "subsection_name": article_row["subsection_name"] or "",
                    "author_name": article_row["author_name"] or "",
                    "author_email": article_row["author_email"] or "",
                    "author_profile_url": article_row["author_profile_url"] or "",
                    "published_at": article_row["published_at"] or "",
                    "updated_at": article_row["updated_at"] or "",
                    "status": article_row["status"] or "",
                    "body_html": article_row["body_html"] or "",
                    "body_text": article_row["body_text"] or "",
                    "source_html_path": article_row["source_html_path"],
                    "xml_path": article_row["xml_path"],
                    "html_sha256": article_row["html_sha256"] or "",
                    "body_sha256": article_row["body_sha256"] or "",
                    "first_seen_at": article_row["first_seen_at"] or "",
                    "last_seen_at": article_row["last_seen_at"] or "",
                    "fetched_at": article_row["fetched_at"] or "",
                    "copyright_notice": article_row["copyright_notice"] or "",
                    "change_type": row["change_type"] or "",
                    "assets": [
                        {
                            "ordinal": int(asset["ordinal"]),
                            "role": asset["role"],
                            "source_url": asset["source_url"],
                            "local_path": asset["local_path"],
                            "mime_type": asset["mime_type"] or "",
                            "width": asset["width"],
                            "height": asset["height"],
                            "alt_text": asset["alt_text"] or "",
                            "caption": asset["caption"] or "",
                            "sha256": asset["sha256"] or "",
                        }
                        for asset in asset_rows
                    ],
                }
            )
        return create_social_export_batch(
            data_dir=self.data_dir,
            output_root=Path(output_root),
            run_row=run_row,
            article_payloads=article_payloads,
            timestamp=timestamp,
        )

    def restore_state(self, snapshot_path: Path, destination_root: Path) -> None:
        restore_snapshot(Path(snapshot_path), Path(destination_root))

    def stats(self) -> Dict[str, object]:
        stats_row = self.store.fetch_stats()
        recent_rows = self.store.fetch_recent_articles(limit=5)
        return {
            "article_count": int(stats_row["article_count"]),
            "section_count": int(stats_row["section_count"]),
            "latest_published_at": stats_row["latest_published_at"],
            "recent_articles": [
                {
                    "idxno": int(row["idxno"]),
                    "headline": row["headline"],
                    "published_at": row["published_at"],
                    "section_name": row["section_name"],
                    "xml_path": row["xml_path"],
                }
                for row in recent_rows
            ],
        }

    def _discover_article_refs(
        self,
        full: bool,
        max_pages: Optional[int],
        refresh_pages: int,
        delay_seconds: float,
    ) -> List[ListArticleRef]:
        first_page = self._fetch_list_page(page_number=1)
        total_pages = max(1, math.ceil(first_page.total_count / max(first_page.list_per_page, 1)))
        page_limit = total_pages if max_pages is None else min(total_pages, max_pages)

        ordered_refs: Dict[int, ListArticleRef] = {}
        known_article_ids = set()
        if not full:
            known_article_ids = self.store.get_known_article_ids(item.idxno for item in first_page.items)

        for item in first_page.items:
            ordered_refs.setdefault(item.idxno, item)

        for page_number in range(2, page_limit + 1):
            page = self._fetch_list_page(page_number=page_number)
            if not page.items:
                break
            page_known_ids = set()
            if not full:
                page_known_ids = self.store.get_known_article_ids(item.idxno for item in page.items)
            for item in page.items:
                ordered_refs.setdefault(item.idxno, item)
            if not full and page_number >= max(1, refresh_pages) and len(page_known_ids) == len(page.items):
                break
            if delay_seconds:
                time.sleep(delay_seconds)

        return list(ordered_refs.values())

    def _select_refs_to_fetch(
        self,
        refs: Sequence[ListArticleRef],
        full: bool,
        refresh_pages: int,
        limit: Optional[int],
    ) -> List[ListArticleRef]:
        known_ids = set()
        if not full:
            known_ids = self.store.get_known_article_ids(ref.idxno for ref in refs)

        selected = []
        for ref in refs:
            if full or ref.idxno not in known_ids or ref.source_page <= max(1, refresh_pages):
                selected.append(ref)
            if limit is not None and len(selected) >= limit:
                break
        return selected

    def _fetch_list_page(self, page_number: int):
        response = self.client.fetch(LIST_URL_TEMPLATE.format(page=page_number))
        if response.status_code >= 400:
            raise RuntimeError(f"List page fetch failed: {page_number} ({response.status_code})")
        return parse_list_page(response.text(), page_number=page_number)

    def _fetch_and_store_article(self, ref: ListArticleRef) -> str | None:
        response = self.client.fetch(ref.url)
        if response.status_code >= 400:
            raise RuntimeError(f"Article fetch failed: HTTP {response.status_code}")

        fetched_at = utc_now()
        raw_html = response.text()
        article = parse_article_html(raw_html, ref.url)
        article.fetched_at = fetched_at
        article.first_seen_at = fetched_at
        article.last_seen_at = fetched_at
        if not article.section:
            article.section = ref.section
        if not article.author_name:
            article.author_name = ref.author_name

        period_dir = self._period_directory(article)
        source_html_rel = period_dir / "html" / "{:06d}.html".format(article.idxno)
        write_text(self.data_dir / source_html_rel, raw_html)

        existing_assets = self.store.fetch_asset_rows(article.idxno)
        article.images = self._download_images(article, period_dir, fetched_at)
        xml_rel = period_dir / "xml" / "{:06d}.xml".format(article.idxno)
        write_bytes(self.data_dir / xml_rel, build_article_xml(article, source_html_rel.as_posix()))

        change_type = self.store.upsert_article(
            record=article,
            source_html_path=source_html_rel.as_posix(),
            xml_path=xml_rel.as_posix(),
        )
        if change_type is None and asset_signature(existing_assets) != asset_signature(article.images):
            change_type = "updated"
        self.store.replace_assets(article.idxno, article.images, downloaded_at=fetched_at)
        return change_type

    def _download_images(
        self,
        article: ArticleRecord,
        period_dir: Path,
        downloaded_at: str,
    ) -> List[ArticleImage]:
        downloaded: List[ArticleImage] = []
        for ordinal, image in enumerate(article.images, start=1):
            if not image.source_url:
                continue
            response = self.client.fetch(image.source_url)
            if response.status_code >= 400:
                continue
            extension = guess_extension(image.source_url, response.headers.get("content-type", ""))
            rel_path = (
                period_dir
                / "media"
                / "{:06d}".format(article.idxno)
                / "{:02d}{}".format(ordinal, extension)
            )
            write_bytes(self.data_dir / rel_path, response.content)
            downloaded.append(
                ArticleImage(
                    source_url=image.source_url,
                    role=image.role,
                    alt_text=image.alt_text,
                    caption=image.caption,
                    width=image.width,
                    height=image.height,
                    local_path=rel_path.as_posix(),
                    mime_type=response.headers.get("content-type", ""),
                    sha256=hashlib.sha256(response.content).hexdigest(),
                )
            )
        return downloaded

    def _period_directory(self, article: ArticleRecord) -> Path:
        published_at = article.published_at or utc_now()
        try:
            published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        except ValueError:
            published = datetime.now(timezone.utc)
        return Path("archive") / "{:04d}".format(published.year) / "{:02d}".format(published.month)


def guess_extension(source_url: str, content_type: str) -> str:
    suffix = Path(urlparse(source_url).path).suffix.lower()
    if suffix:
        if suffix == ".jpe":
            return ".jpg"
        return suffix
    guessed = mimetypes.guess_extension((content_type or "").split(";", 1)[0].strip()) or ".bin"
    if guessed == ".jpe":
        return ".jpg"
    return guessed


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def asset_signature(images: Iterable[ArticleImage | Dict[str, object]]) -> Tuple[Tuple[object, ...], ...]:
    normalized = []
    for image in images:
        if isinstance(image, dict) or hasattr(image, "keys"):
            normalized.append(
                (
                    image["ordinal"] if "ordinal" in image.keys() else None,
                    image["role"],
                    image["source_url"],
                    image["local_path"],
                    image["mime_type"],
                    image["width"],
                    image["height"],
                    image["alt_text"],
                    image["caption"],
                    image["sha256"],
                )
            )
            continue

        normalized.append(
            (
                None,
                image.role,
                image.source_url,
                image.local_path,
                image.mime_type,
                image.width,
                image.height,
                image.alt_text,
                image.caption,
                image.sha256,
            )
        )
    return tuple(normalized)
