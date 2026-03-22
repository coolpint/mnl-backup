from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from .social_status import (
    build_article_status_path,
    build_batch_status_path,
    build_status_contract,
)


PLATFORM_TARGETS = {
    "youtube_shorts": {
        "builder": "youtube_shorts_builder",
        "publisher": "youtube_publisher",
        "content_kind": "vertical_video",
        "delivery_mode": "private_review",
        "review_required": True,
    },
    "instagram": {
        "builder": "instagram_builder",
        "publisher": "instagram_publisher",
        "content_kind": "platform_specific",
        "delivery_mode": "review_required",
        "review_required": True,
    },
    "facebook": {
        "builder": "facebook_builder",
        "publisher": "facebook_publisher",
        "content_kind": "platform_specific",
        "delivery_mode": "review_required",
        "review_required": True,
    },
    "threads": {
        "builder": "threads_builder",
        "publisher": "threads_publisher",
        "content_kind": "text_first",
        "delivery_mode": "review_required",
        "review_required": True,
    },
}


@dataclass
class SocialPackageResult:
    article_idxno: int
    headline: str
    package_dir: Path
    package_path: Path
    article_json_path: Path
    rights_path: Path
    asset_count: int
    change_type: str


@dataclass
class SocialExportResult:
    run_id: int
    exported_at: str
    batch_dir: Path
    relative_dir: str
    batch_manifest_path: Path
    notification_path: Path
    article_count: int
    packages: List[SocialPackageResult] = field(default_factory=list)


def create_social_export_batch(
    data_dir: Path,
    output_root: Path,
    run_row,
    article_payloads: Sequence[Dict[str, object]],
    timestamp: Optional[datetime] = None,
) -> SocialExportResult:
    exported_dt = timestamp or datetime.now(timezone.utc)
    exported_at = isoformat_seconds(exported_dt)
    batch_dir = (
        Path(output_root)
        / exported_dt.strftime("%Y")
        / exported_dt.strftime("%m")
        / exported_dt.strftime("%d")
        / f"run-{int(run_row['id']):06d}"
    )
    batch_dir.mkdir(parents=True, exist_ok=True)
    relative_dir = batch_dir.relative_to(output_root).as_posix()

    packages: List[SocialPackageResult] = []
    for article_payload in article_payloads:
        packages.append(
            _write_social_package(
                data_dir=Path(data_dir),
                batch_dir=batch_dir,
                relative_dir=relative_dir,
                run_row=run_row,
                article_payload=article_payload,
                exported_at=exported_at,
            )
        )

    batch_manifest_path = batch_dir / "batch.json"
    notification_path = batch_dir / "notification.json"
    write_json(
        batch_manifest_path,
        {
            "schema_version": 1,
            "export_kind": "mnl/social-export-batch",
            "exported_at": exported_at,
            "relative_dir": relative_dir,
            "status_contract": build_status_contract(relative_dir),
            "run": {
                "id": int(run_row["id"]),
                "mode": run_row["mode"] or "",
                "started_at": run_row["started_at"] or "",
                "finished_at": run_row["finished_at"] or "",
                "discovered_count": int(run_row["discovered_count"] or 0),
                "fetched_count": int(run_row["fetched_count"] or 0),
                "updated_count": int(run_row["updated_count"] or 0),
            },
            "article_count": len(packages),
            "packages": [
                {
                    "article_idxno": item.article_idxno,
                    "headline": item.headline,
                    "change_type": item.change_type,
                    "package_dir": relative_to(batch_dir, item.package_dir),
                    "package_path": relative_to(batch_dir, item.package_path),
                    "article_json_path": relative_to(batch_dir, item.article_json_path),
                    "rights_path": relative_to(batch_dir, item.rights_path),
                    "asset_count": item.asset_count,
                }
                for item in packages
            ],
        },
    )
    write_json(
        notification_path,
        {
            "schema_version": 1,
            "event_kind": "mnl/social-export-notification",
            "exported_at": exported_at,
            "relative_dir": relative_dir,
            "batch_manifest": "batch.json",
            "status_contract": build_status_contract(relative_dir),
            "article_count": len(packages),
            "review_required": True,
            "run": {
                "id": int(run_row["id"]),
                "mode": run_row["mode"] or "",
                "updated_count": int(run_row["updated_count"] or 0),
            },
            "publisher_targets": sorted(PLATFORM_TARGETS.keys()),
            "packages": [
                {
                    "article_idxno": item.article_idxno,
                    "headline": item.headline,
                    "change_type": item.change_type,
                    "package_dir": relative_to(batch_dir, item.package_dir),
                }
                for item in packages
            ],
        },
    )
    return SocialExportResult(
        run_id=int(run_row["id"]),
        exported_at=exported_at,
        batch_dir=batch_dir,
        relative_dir=relative_dir,
        batch_manifest_path=batch_manifest_path,
        notification_path=notification_path,
        article_count=len(packages),
        packages=packages,
    )


def _write_social_package(
    data_dir: Path,
    batch_dir: Path,
    relative_dir: str,
    run_row,
    article_payload: Dict[str, object],
    exported_at: str,
) -> SocialPackageResult:
    idxno = int(article_payload["idxno"])
    package_dir = batch_dir / f"article-{idxno:06d}"
    package_dir.mkdir(parents=True, exist_ok=True)

    copied_files = _copy_source_files(
        data_dir=data_dir,
        package_dir=package_dir,
        article_payload=article_payload,
    )

    body_text_path = package_dir / "body.txt"
    body_text_path.write_text(str(article_payload.get("body_text") or ""), encoding="utf-8")

    article_json_path = package_dir / "article.json"
    write_json(
        article_json_path,
        {
            "schema_version": 1,
            "article": _article_payload(article_payload),
            "assets": _asset_payloads(article_payload.get("assets", [])),
            "source_files": copied_files,
            "editorial_signals": {
                "body_character_count": len(str(article_payload.get("body_text") or "")),
                "summary_present": bool(article_payload.get("summary")),
                "image_count": len(list(article_payload.get("assets", []))),
                "needs_human_editorial_review": True,
                "default_publish_policy": "manual_approval_only",
            },
        },
    )

    rights_path = package_dir / "rights.json"
    write_json(
        rights_path,
        {
            "schema_version": 1,
            "status": "needs_review",
            "article_idxno": idxno,
            "article_text": {
                "source": "moneynlaw_canonical_archive",
                "copyright_notice": article_payload.get("copyright_notice") or "",
                "transformation_required": True,
                "notes": [
                    "Publishers must transform article content for each platform instead of reposting the article verbatim."
                ],
            },
            "media": [
                {
                    "ordinal": asset["ordinal"],
                    "role": asset["role"],
                    "source_url": asset["source_url"],
                    "packaged_path": asset["packaged_path"],
                    "license_type": "unknown",
                    "social_use_allowed": False,
                    "credit_text": "",
                    "review_required": True,
                }
                for asset in _asset_payloads(article_payload.get("assets", []))
            ],
            "music": {
                "status": "not_attached",
                "license_required": True,
                "review_required": True,
            },
        },
    )

    package_path = package_dir / "package.json"
    write_json(
        package_path,
        {
            "schema_version": 1,
            "export_kind": "mnl/social-package",
            "exported_at": exported_at,
            "run": {
                "id": int(run_row["id"]),
                "mode": run_row["mode"] or "",
                "change_type": article_payload["change_type"],
            },
            "article": {
                "idxno": idxno,
                "headline": article_payload.get("headline") or "",
                "section_name": article_payload.get("section_name") or "",
                "subsection_name": article_payload.get("subsection_name") or "",
                "author_name": article_payload.get("author_name") or "",
                "published_at": article_payload.get("published_at") or "",
                "canonical_url": article_payload.get("canonical_url") or "",
            },
            "files": {
                "article_json": "article.json",
                "article_xml": copied_files["article_xml"],
                "source_html": copied_files["source_html"],
                "body_text": "body.txt",
                "rights": "rights.json",
            },
            "assets": {
                "count": len(list(article_payload.get("assets", []))),
                "has_local_media": bool(article_payload.get("assets")),
                "directory": copied_files["assets_dir"],
            },
            "status_contract": build_status_contract(relative_dir),
            "platforms": {
                name: {
                    **config,
                    "status": "pending",
                    "status_paths": {
                        "batch": build_batch_status_path(name, relative_dir),
                        "article": build_article_status_path(name, relative_dir, idxno),
                    },
                }
                for name, config in PLATFORM_TARGETS.items()
            },
        },
    )

    return SocialPackageResult(
        article_idxno=idxno,
        headline=str(article_payload.get("headline") or ""),
        package_dir=package_dir,
        package_path=package_path,
        article_json_path=article_json_path,
        rights_path=rights_path,
        asset_count=len(list(article_payload.get("assets", []))),
        change_type=str(article_payload.get("change_type") or ""),
    )


def _copy_source_files(
    data_dir: Path,
    package_dir: Path,
    article_payload: Dict[str, object],
) -> Dict[str, str]:
    article_xml_source = data_dir / str(article_payload["xml_path"])
    article_html_source = data_dir / str(article_payload["source_html_path"])
    article_xml_target = package_dir / "article.xml"
    source_html_target = package_dir / "source.html"
    shutil.copy2(article_xml_source, article_xml_target)
    shutil.copy2(article_html_source, source_html_target)

    assets_dir = package_dir / "assets" / "source-media"
    assets_dir.mkdir(parents=True, exist_ok=True)
    copied_assets = []
    for asset in article_payload.get("assets", []):
        asset_source = data_dir / str(asset["local_path"])
        target_name = asset_source.name
        asset_target = assets_dir / target_name
        shutil.copy2(asset_source, asset_target)
        copied_assets.append(
            {
                "ordinal": int(asset["ordinal"]),
                "source_path": str(asset["local_path"]),
                "packaged_path": relative_to(package_dir, asset_target),
            }
        )

    for asset in article_payload.get("assets", []):
        matching = next(
            (item for item in copied_assets if item["ordinal"] == int(asset["ordinal"])),
            None,
        )
        asset["packaged_path"] = "" if matching is None else matching["packaged_path"]

    return {
        "article_xml": relative_to(package_dir, article_xml_target),
        "source_html": relative_to(package_dir, source_html_target),
        "assets_dir": relative_to(package_dir, assets_dir),
    }


def _article_payload(article_payload: Dict[str, object]) -> Dict[str, object]:
    return {
        "idxno": int(article_payload["idxno"]),
        "source_url": article_payload.get("source_url") or "",
        "canonical_url": article_payload.get("canonical_url") or "",
        "site_name": article_payload.get("site_name") or "",
        "language": article_payload.get("language") or "",
        "headline": article_payload.get("headline") or "",
        "browser_title": article_payload.get("browser_title") or "",
        "summary": article_payload.get("summary") or "",
        "section_name": article_payload.get("section_name") or "",
        "subsection_name": article_payload.get("subsection_name") or "",
        "author_name": article_payload.get("author_name") or "",
        "author_email": article_payload.get("author_email") or "",
        "author_profile_url": article_payload.get("author_profile_url") or "",
        "published_at": article_payload.get("published_at") or "",
        "updated_at": article_payload.get("updated_at") or "",
        "status": article_payload.get("status") or "",
        "body_html": article_payload.get("body_html") or "",
        "body_text": article_payload.get("body_text") or "",
        "copyright_notice": article_payload.get("copyright_notice") or "",
        "html_sha256": article_payload.get("html_sha256") or "",
        "body_sha256": article_payload.get("body_sha256") or "",
        "fetched_at": article_payload.get("fetched_at") or "",
        "first_seen_at": article_payload.get("first_seen_at") or "",
        "last_seen_at": article_payload.get("last_seen_at") or "",
        "change_type": article_payload.get("change_type") or "",
        "archive_paths": {
            "xml_path": article_payload.get("xml_path") or "",
            "source_html_path": article_payload.get("source_html_path") or "",
        },
    }


def _asset_payloads(assets: Iterable[Dict[str, object]]) -> List[Dict[str, object]]:
    payloads = []
    for asset in assets:
        payloads.append(
            {
                "ordinal": int(asset["ordinal"]),
                "role": asset.get("role") or "",
                "source_url": asset.get("source_url") or "",
                "local_path": asset.get("local_path") or "",
                "packaged_path": asset.get("packaged_path") or "",
                "mime_type": asset.get("mime_type") or "",
                "width": asset.get("width"),
                "height": asset.get("height"),
                "alt_text": asset.get("alt_text") or "",
                "caption": asset.get("caption") or "",
                "sha256": asset.get("sha256") or "",
            }
        )
    return payloads


def isoformat_seconds(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def relative_to(base: Path, target: Path) -> str:
    return target.relative_to(base).as_posix()


def write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
