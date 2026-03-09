from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ArticleImage:
    source_url: str
    role: str = "inline"
    alt_text: str = ""
    caption: str = ""
    width: Optional[int] = None
    height: Optional[int] = None
    local_path: Optional[str] = None
    mime_type: Optional[str] = None
    sha256: Optional[str] = None


@dataclass
class ArticleRecord:
    idxno: int
    source_url: str
    canonical_url: str
    site_name: str
    language: str
    headline: str
    browser_title: str = ""
    summary: str = ""
    section: str = ""
    subsection: str = ""
    author_name: str = ""
    author_email: str = ""
    author_profile_url: str = ""
    published_at: str = ""
    updated_at: str = ""
    body_html: str = ""
    body_text: str = ""
    copyright_notice: str = ""
    status: str = "published"
    html_sha256: str = ""
    body_sha256: str = ""
    fetched_at: str = ""
    first_seen_at: str = ""
    last_seen_at: str = ""
    images: List[ArticleImage] = field(default_factory=list)


@dataclass
class ListArticleRef:
    idxno: int
    url: str
    title: str = ""
    section: str = ""
    author_name: str = ""
    listed_at: str = ""
    source_page: int = 1


@dataclass
class ListPage:
    page_number: int
    total_count: int
    list_per_page: int
    items: List[ListArticleRef]
