"""Small allow-list HTML sanitizer for Mojang patch notes."""
from __future__ import annotations

from html import escape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

ALLOWED_TAGS = {
    "p", "div", "span", "strong", "b", "em", "i", "u", "s", "del",
    "ul", "ol", "li", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "code", "pre", "table", "thead", "tbody", "tfoot",
    "tr", "th", "td", "img",
}
VOID_TAGS = {"br", "hr", "img"}
SKIP_TAGS = {"script", "style", "iframe", "object", "embed", "template", "svg", "math"}


def _safe_image_url(value: str, base_url: str) -> str | None:
    absolute = urljoin(base_url.rstrip("/") + "/", value)
    parsed = urlparse(absolute)
    allowed_host = (urlparse(base_url).hostname or "").lower()
    if parsed.scheme != "https" or parsed.username or parsed.password:
        return None
    if (parsed.hostname or "").lower() != allowed_host:
        return None
    return absolute


class _Sanitizer(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.out: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self.skip_depth:
            if tag in SKIP_TAGS:
                self.skip_depth += 1
            return
        if tag in SKIP_TAGS:
            self.skip_depth = 1
            return
        if tag not in ALLOWED_TAGS:
            return
        if tag == "img":
            src = dict(attrs).get("src", "")
            safe = _safe_image_url(src, self.base_url) if src else None
            if safe:
                self.out.append(
                    f'<img src="{escape(safe, quote=True)}" loading="lazy" referrerpolicy="no-referrer">'
                )
            return
        self.out.append(f"<{tag}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.skip_depth:
            if tag in SKIP_TAGS:
                self.skip_depth -= 1
            return
        if tag in ALLOWED_TAGS and tag not in VOID_TAGS:
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.skip_depth:
            self.out.append(escape(data))


def sanitize_patch_html(html: str, base_url: str) -> str:
    parser = _Sanitizer(base_url)
    parser.feed(str(html))
    parser.close()
    return "".join(parser.out)
