from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional


STATUS_ROOT = "social/status"
STATUS_STATES = (
    "received",
    "building",
    "built",
    "review_required",
    "approved",
    "publishing",
    "published",
    "blocked",
    "failed",
    "skipped",
)
TERMINAL_STATUS_STATES = ("published", "blocked", "failed", "skipped")


def build_status_contract(relative_dir: str) -> Dict[str, object]:
    return {
        "root_dir": STATUS_ROOT,
        "relative_dir": relative_dir,
        "batch_path_template": f"{STATUS_ROOT}/{{platform}}/{relative_dir}/batch.json",
        "article_path_template": f"{STATUS_ROOT}/{{platform}}/{relative_dir}/article-{{idxno:06d}}.json",
        "allowed_states": list(STATUS_STATES),
        "terminal_states": list(TERMINAL_STATUS_STATES),
    }


def build_status_base_dir(platform: str, relative_dir: str) -> str:
    return f"{STATUS_ROOT}/{platform}/{relative_dir}"


def build_batch_status_path(platform: str, relative_dir: str) -> str:
    return f"{build_status_base_dir(platform, relative_dir)}/batch.json"


def build_article_status_path(platform: str, relative_dir: str, article_idxno: int) -> str:
    return f"{build_status_base_dir(platform, relative_dir)}/article-{int(article_idxno):06d}.json"


def build_batch_status_payload(
    *,
    platform: str,
    relative_dir: str,
    run_id: int,
    state: str,
    article_count: int,
    processed_count: int,
    failed_count: int = 0,
    detail: str = "",
    updated_at: Optional[str] = None,
) -> Dict[str, object]:
    return {
        "schema_version": 1,
        "status_kind": "mnl/social-batch-status",
        "platform": platform,
        "relative_dir": relative_dir,
        "run_id": int(run_id),
        "state": state,
        "article_count": int(article_count),
        "processed_count": int(processed_count),
        "failed_count": int(failed_count),
        "detail": detail,
        "updated_at": updated_at or utc_now(),
    }


def build_article_status_payload(
    *,
    platform: str,
    relative_dir: str,
    run_id: int,
    article_idxno: int,
    state: str,
    package_dir: str,
    package_path: str,
    detail: str = "",
    output_path: str = "",
    review_url: str = "",
    updated_at: Optional[str] = None,
) -> Dict[str, object]:
    return {
        "schema_version": 1,
        "status_kind": "mnl/social-article-status",
        "platform": platform,
        "relative_dir": relative_dir,
        "run_id": int(run_id),
        "article_idxno": int(article_idxno),
        "state": state,
        "package_dir": package_dir,
        "package_path": package_path,
        "detail": detail,
        "output_path": output_path,
        "review_url": review_url,
        "updated_at": updated_at or utc_now(),
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
