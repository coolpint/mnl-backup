from __future__ import annotations

import hashlib
import html
import json
import re
from html.parser import HTMLParser
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from .models import ArticleImage, ArticleRecord, ListArticleRef, ListPage


META_TAG_RE = re.compile(r"<meta\b(?P<attrs>[^>]+?)>", re.IGNORECASE | re.DOTALL)
ATTR_RE = re.compile(r'([:\w-]+)\s*=\s*(".*?"|\'.*?\'|[^\s>]+)', re.DOTALL)
BODY_RE = re.compile(
    r'<article\s+id="article-view-content-div"[^>]*>(?P<body>.*?)</article>',
    re.IGNORECASE | re.DOTALL,
)
SCRIPT_RE = re.compile(r"<script\b.*?</script>", re.IGNORECASE | re.DOTALL)
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
TITLE_RE = re.compile(r"<title>(?P<value>.*?)</title>", re.IGNORECASE | re.DOTALL)
JSON_LD_RE = re.compile(
    r'<script[^>]+type="application/ld\+json"[^>]*>(?P<value>.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
LIST_TOTAL_RE = re.compile(r"총\s*<strong>(?P<count>[\d,]+)</strong>건")
LIST_PER_PAGE_RE = re.compile(r"params\['list_per_page'\]\s*=\s*\"(?P<count>\d+)\";")
LIST_ITEM_RE = re.compile(
    r'<li\b[^>]*class="[^"]*\baltlist-(?:webzine|text)-item\b[^"]*"[^>]*>(?P<item>.*?)</li>',
    re.IGNORECASE | re.DOTALL,
)
LIST_LINK_RE = re.compile(
    r'href="(?P<url>https://www\.moneynlaw\.co\.kr/news/articleView\.html\?idxno=(?P<idxno>\d+))"',
    re.IGNORECASE,
)
LIST_TITLE_RE = re.compile(
    r'<H2 class="altlist-subject">\s*<a [^>]+>\s*(?P<title>.*?)\s*</a>',
    re.IGNORECASE | re.DOTALL,
)
LIST_INFO_RE = re.compile(
    r'<div class="altlist-info-item">\s*(?P<value>.*?)\s*</div>',
    re.IGNORECASE | re.DOTALL,
)
AUTHOR_RE = re.compile(
    r'<li class="info-name"[^>]*>\s*(?P<value>.*?)\s*</li>',
    re.IGNORECASE | re.DOTALL,
)
WRITER_NAME_RE = re.compile(
    r'<a [^>]*class="article-writer-name"[^>]*>\s*(?P<value>.*?)\s*</a>',
    re.IGNORECASE | re.DOTALL,
)
WRITER_MAIL_RE = re.compile(
    r'<a href="mailto:(?P<email>[^"]+)" class="article-writer-mail">',
    re.IGNORECASE,
)
WRITER_PROFILE_RE = re.compile(
    r'<a href="(?P<url>[^"]+)" class="article-writer-name">',
    re.IGNORECASE,
)
COPYRIGHT_RE = re.compile(
    r'<article class="article-copyright">\s*(?P<value>.*?)\s*</article>',
    re.IGNORECASE | re.DOTALL,
)


def parse_list_page(html_text: str, page_number: int) -> ListPage:
    total_match = LIST_TOTAL_RE.search(html_text)
    total_count = int(total_match.group("count").replace(",", "")) if total_match else 0
    per_page_match = LIST_PER_PAGE_RE.search(html_text)
    list_per_page = int(per_page_match.group("count")) if per_page_match else 20

    items: List[ListArticleRef] = []
    seen_idxnos = set()
    for item_match in LIST_ITEM_RE.finditer(html_text):
        item_html = item_match.group("item")
        link_match = LIST_LINK_RE.search(item_html)
        if not link_match:
            continue
        idxno = int(link_match.group("idxno"))
        if idxno in seen_idxnos:
            continue
        title_match = LIST_TITLE_RE.search(item_html)
        info_values = [strip_tags(value) for value in LIST_INFO_RE.findall(item_html)]
        section = info_values[0] if len(info_values) > 0 else ""
        author_name = info_values[1] if len(info_values) > 1 else ""
        listed_at = info_values[2] if len(info_values) > 2 else ""
        items.append(
            ListArticleRef(
                idxno=idxno,
                url=link_match.group("url"),
                title=clean_text(title_match.group("title")) if title_match else "",
                section=section,
                author_name=author_name,
                listed_at=listed_at,
                source_page=page_number,
            )
        )
        seen_idxnos.add(idxno)

    return ListPage(
        page_number=page_number,
        total_count=total_count,
        list_per_page=list_per_page,
        items=items,
    )


def parse_article_html(html_text: str, source_url: str) -> ArticleRecord:
    meta_map = extract_meta_map(html_text)
    json_ld = extract_news_article_schema(html_text)
    body_match = BODY_RE.search(html_text)
    if not body_match:
        raise ValueError("Could not locate article body")
    raw_body_html = body_match.group("body")
    body_html = clean_body_html(raw_body_html)
    images = extract_images(body_html)

    og_image = meta_map.get("og:image", "")
    if not images and is_article_image_url(og_image):
        images.append(ArticleImage(source_url=og_image, role="primary"))

    author_name = clean_text(first_match(AUTHOR_RE, html_text))
    if not author_name:
        author_name = clean_text(first_match(WRITER_NAME_RE, html_text))

    author_email = clean_text(first_match(WRITER_MAIL_RE, html_text, "email"))
    author_profile_url = clean_text(first_match(WRITER_PROFILE_RE, html_text, "url"))
    browser_title = clean_text(first_match(TITLE_RE, html_text))
    summary = clean_text(meta_map.get("description", ""))
    canonical_url = clean_text(meta_map.get("og:url", source_url))
    idxno = extract_idxno(canonical_url or source_url)
    published_at = clean_text(meta_map.get("article:published_time", "")) or clean_text(
        json_ld.get("datePublished", "")
    )
    updated_at = clean_text(json_ld.get("dateModified", "")) or published_at

    record = ArticleRecord(
        idxno=idxno,
        source_url=source_url,
        canonical_url=canonical_url or source_url,
        site_name=clean_text(meta_map.get("og:site_name", "머니앤로")) or "머니앤로",
        language="ko",
        headline=clean_text(meta_map.get("og:title", "")).replace(" - 머니앤로", "")
        or clean_text(json_ld.get("headline", "")),
        browser_title=browser_title,
        summary=summary,
        section=clean_text(meta_map.get("article:section", "")),
        subsection=clean_text(meta_map.get("article:section2", "")),
        author_name=author_name,
        author_email=author_email,
        author_profile_url=author_profile_url,
        published_at=published_at,
        updated_at=updated_at,
        body_html=body_html,
        body_text=html_to_text(body_html),
        copyright_notice=clean_text(first_match(COPYRIGHT_RE, html_text)),
        html_sha256=sha256_text(html_text),
        body_sha256=sha256_text(body_html),
        images=images,
    )
    if not record.headline:
        record.headline = clean_text(json_ld.get("headline", "")) or browser_title.split("<", 1)[0].strip()
    return record


def extract_idxno(url: str) -> int:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    value = query.get("idxno", ["0"])[0]
    return int(value)


def extract_meta_map(html_text: str) -> Dict[str, str]:
    meta_map: Dict[str, str] = {}
    for match in META_TAG_RE.finditer(html_text):
        attrs = parse_attrs(match.group("attrs"))
        key = attrs.get("property") or attrs.get("name")
        content = attrs.get("content")
        if key and content and key not in meta_map:
            meta_map[key] = clean_text(content)
    return meta_map


def extract_news_article_schema(html_text: str) -> Dict[str, str]:
    for match in JSON_LD_RE.finditer(html_text):
        candidate = match.group("value").strip()
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("@type") == "NewsArticle":
            return payload
    return {}


def clean_body_html(body_html: str) -> str:
    without_comments = COMMENT_RE.sub("", body_html)
    without_scripts = SCRIPT_RE.sub("", without_comments)
    return without_scripts.strip()


def extract_images(body_html: str) -> List[ArticleImage]:
    parser = _ImageParser()
    parser.feed(body_html)
    parser.close()
    images = parser.images
    if images and not any(image.role == "primary" for image in images):
        images[0].role = "primary"
    return images


def html_to_text(body_html: str) -> str:
    parser = _TextParser()
    parser.feed(body_html)
    parser.close()
    return parser.to_text()


def parse_attrs(raw_attrs: str) -> Dict[str, str]:
    attrs: Dict[str, str] = {}
    for key, raw_value in ATTR_RE.findall(raw_attrs):
        value = raw_value[1:-1] if raw_value[:1] in {"'", '"'} else raw_value
        attrs[key.lower()] = html.unescape(value)
    return attrs


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = strip_tags(value)
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value or "")


def first_match(pattern: re.Pattern, text: str, group: str = "value") -> str:
    match = pattern.search(text)
    if not match:
        return ""
    return match.group(group)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def is_article_image_url(url: str) -> bool:
    return "/news/photo/" in (url or "")


def parse_int(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


class _TextParser(HTMLParser):
    _BLOCK_TAGS = {
        "article",
        "div",
        "p",
        "br",
        "figure",
        "figcaption",
        "li",
        "ul",
        "ol",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style"}:
            self._skip_depth += 1
            return
        if self._skip_depth == 0 and tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if self._skip_depth == 0 and tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self.parts.append(data)

    def to_text(self) -> str:
        text = "".join(self.parts).replace("\xa0", " ")
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()


class _ImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.images: List[ArticleImage] = []
        self._figure_attrs: Optional[Dict[str, str]] = None
        self._figure_images: List[ArticleImage] = []
        self._caption_parts: List[str] = []
        self._in_figcaption = False

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs_map = dict(attrs)
        if tag == "figure":
            self._figure_attrs = {key: value for key, value in attrs if value is not None}
            self._figure_images = []
            self._caption_parts = []
            self._in_figcaption = False
            return
        if tag == "figcaption" and self._figure_attrs is not None:
            self._in_figcaption = True
            return
        if tag != "img":
            return

        image = ArticleImage(
            source_url=attrs_map.get("src", ""),
            alt_text=attrs_map.get("alt", "") or "",
            width=parse_int(attrs_map.get("width")),
            height=parse_int(attrs_map.get("height")),
        )
        if self._figure_attrs is not None:
            self._figure_images.append(image)
        else:
            self.images.append(image)

    def handle_endtag(self, tag: str) -> None:
        if tag == "figcaption":
            self._in_figcaption = False
            return
        if tag != "figure" or self._figure_attrs is None:
            return

        caption = clean_text("".join(self._caption_parts))
        figure_classes = self._figure_attrs.get("class", "")
        for image in self._figure_images:
            image.caption = caption
            if "photo-layout" in figure_classes and not self.images:
                image.role = "primary"
            self.images.append(image)

        self._figure_attrs = None
        self._figure_images = []
        self._caption_parts = []
        self._in_figcaption = False

    def handle_data(self, data: str) -> None:
        if self._in_figcaption:
            self._caption_parts.append(data)
