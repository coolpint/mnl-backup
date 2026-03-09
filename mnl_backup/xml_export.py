from __future__ import annotations

from pathlib import Path
from typing import Iterable
from xml.dom.minidom import Document

from .models import ArticleRecord


def build_article_xml(article: ArticleRecord, source_html_path: str) -> bytes:
    doc = Document()
    root = doc.createElement("articleArchive")
    root.setAttribute("version", "1")
    root.setAttribute("idxno", str(article.idxno))
    root.setAttribute("source", article.site_name)
    doc.appendChild(root)

    identity = append_element(doc, root, "identity")
    append_text(doc, identity, "sourceUrl", article.source_url)
    append_text(doc, identity, "canonicalUrl", article.canonical_url)
    append_text(doc, identity, "status", article.status)
    append_text(doc, identity, "language", article.language)

    titles = append_element(doc, root, "titles")
    append_text(doc, titles, "headline", article.headline)
    append_text(doc, titles, "browserTitle", article.browser_title)
    append_text(doc, titles, "summary", article.summary)

    classification = append_element(doc, root, "classification")
    append_text(doc, classification, "section", article.section)
    append_text(doc, classification, "subsection", article.subsection)

    byline = append_element(doc, root, "byline")
    append_text(doc, byline, "authorName", article.author_name)
    append_text(doc, byline, "authorEmail", article.author_email)
    append_text(doc, byline, "authorProfileUrl", article.author_profile_url)

    timestamps = append_element(doc, root, "timestamps")
    append_text(doc, timestamps, "publishedAt", article.published_at)
    append_text(doc, timestamps, "updatedAt", article.updated_at)
    append_text(doc, timestamps, "fetchedAt", article.fetched_at)
    append_text(doc, timestamps, "firstSeenAt", article.first_seen_at)
    append_text(doc, timestamps, "lastSeenAt", article.last_seen_at)

    content = append_element(doc, root, "content")
    append_cdata(doc, content, "bodyHtml", article.body_html)
    append_text(doc, content, "bodyText", article.body_text)

    media = append_element(doc, root, "media")
    for image in article.images:
        image_node = append_element(doc, media, "image")
        image_node.setAttribute("role", image.role)
        append_text(doc, image_node, "sourceUrl", image.source_url)
        append_text(doc, image_node, "localPath", image.local_path or "")
        append_text(doc, image_node, "mimeType", image.mime_type or "")
        append_text(doc, image_node, "width", "" if image.width is None else str(image.width))
        append_text(doc, image_node, "height", "" if image.height is None else str(image.height))
        append_text(doc, image_node, "altText", image.alt_text)
        append_text(doc, image_node, "caption", image.caption)
        append_text(doc, image_node, "sha256", image.sha256 or "")

    rights = append_element(doc, root, "rights")
    append_text(doc, rights, "copyrightNotice", article.copyright_notice)

    artifacts = append_element(doc, root, "artifacts")
    append_text(doc, artifacts, "sourceHtmlPath", source_html_path)
    append_text(doc, artifacts, "htmlSha256", article.html_sha256)
    append_text(doc, artifacts, "bodySha256", article.body_sha256)

    return doc.toprettyxml(indent="  ", encoding="utf-8")


def build_manifest_xml(rows: Iterable) -> bytes:
    doc = Document()
    root = doc.createElement("articleArchiveManifest")
    root.setAttribute("version", "1")
    doc.appendChild(root)

    for row in rows:
        article = append_element(doc, root, "article")
        article.setAttribute("idxno", str(row["idxno"]))
        append_text(doc, article, "headline", row["headline"])
        append_text(doc, article, "canonicalUrl", row["canonical_url"])
        append_text(doc, article, "section", row["section_name"] or "")
        append_text(doc, article, "subsection", row["subsection_name"] or "")
        append_text(doc, article, "authorName", row["author_name"] or "")
        append_text(doc, article, "publishedAt", row["published_at"] or "")
        append_text(doc, article, "updatedAt", row["updated_at"] or "")
        append_text(doc, article, "xmlPath", row["xml_path"])
        append_text(doc, article, "sourceHtmlPath", row["source_html_path"])
        append_text(doc, article, "fetchedAt", row["fetched_at"] or "")
        append_text(doc, article, "firstSeenAt", row["first_seen_at"] or "")
        append_text(doc, article, "lastSeenAt", row["last_seen_at"] or "")
        append_text(doc, article, "htmlSha256", row["html_sha256"] or "")
        append_text(doc, article, "bodySha256", row["body_sha256"] or "")

    return doc.toprettyxml(indent="  ", encoding="utf-8")


def write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def append_element(doc: Document, parent, name: str):
    element = doc.createElement(name)
    parent.appendChild(element)
    return element


def append_text(doc: Document, parent, name: str, value: str):
    element = append_element(doc, parent, name)
    element.appendChild(doc.createTextNode(value or ""))
    return element


def append_cdata(doc: Document, parent, name: str, value: str):
    element = append_element(doc, parent, name)
    parts = (value or "").split("]]>")
    for index, part in enumerate(parts):
        element.appendChild(doc.createCDATASection(part))
        if index != len(parts) - 1:
            element.appendChild(doc.createTextNode("]]>"))
    return element
