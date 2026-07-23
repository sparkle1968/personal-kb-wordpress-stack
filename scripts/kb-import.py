#!/usr/bin/env python3
"""Import URLs or local notes into the personal WordPress knowledge base."""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
from html.parser import HTMLParser
from http import cookiejar
import ipaddress
import json
import mimetypes
import os
import re
import socket
import sys
from pathlib import Path
from urllib import error, parse, request


MAX_HTML_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_IMAGES = 30
DEFAULT_MAX_IMAGE_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_VIDEO_BYTES = 128 * 1024 * 1024
USER_AGENT = "PersonalKBImporter/1.0 (+https://kb.example.com)"
X_API_BEARER = os.environ.get("X_API_BEARER", "")
X_TWEET_RESULT_QUERY_ID = "SgZWKwvBiOKrSC0QeOGvXw"
X_WEB_API_CONFIG: dict[str, str] | None = None
X_TWEET_RESULT_FEATURES = {
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "premium_content_api_read_enabled": True,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": True,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "rweb_cashtags_composer_attachment_enabled": True,
    "responsive_web_jetfuel_frame": True,
    "responsive_web_grok_share_attachment_enabled": True,
    "responsive_web_grok_annotations_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "rweb_conversational_replies_downvote_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "content_disclosure_indicator_enabled": True,
    "content_disclosure_ai_generated_indicator_enabled": True,
    "responsive_web_grok_show_grok_translated_post": True,
    "responsive_web_grok_analysis_button_from_backend": True,
    "post_ctas_fetch_enabled": True,
    "rweb_cashtags_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "responsive_web_profile_redirect_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "verified_phone_label_enabled": True,
    "responsive_web_grok_image_annotation_enabled": True,
    "responsive_web_grok_imagine_annotation_enabled": True,
    "responsive_web_grok_community_note_auto_translation_is_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
}
X_TWEET_RESULT_FIELD_TOGGLES = {
    "withArticleRichContentState": True,
    "withArticlePlainText": True,
    "withArticleSummaryText": True,
    "withArticleVoiceOver": True,
    "withGrokAnalyze": True,
    "withDisallowedReplyControls": True,
    "withPayments": True,
    "withAuxiliaryUserLabels": True,
}
URL_TEXT_PATTERN = r"(https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+)"

VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
DROP_WITH_CONTENT = {
    "script",
    "style",
    "noscript",
    "svg",
    "iframe",
    "form",
    "nav",
    "header",
    "footer",
    "aside",
    "button",
    "input",
    "select",
    "textarea",
}
ALLOWED_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "em",
    "figcaption",
    "figure",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "i",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}
ALLOWED_IMAGE_MIME = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/avif",
}
ALLOWED_VIDEO_MIME = {
    "video/mp4",
}
PROXY_FAKE_IP_NETWORKS = (
    ipaddress.ip_network("198.18.0.0/15"),
)


class Node:
    def __init__(self, tag: str, attrs: list[tuple[str, str | None]] | None = None, parent: "Node | None" = None):
        self.tag = tag
        self.attrs = attrs or []
        self.parent = parent
        self.children: list[Node | str] = []


class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self.current = self.root

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        node = Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in VOID_TAGS:
            self.current = node

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.current.children.append(Node(tag.lower(), attrs, self.current))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        cursor = self.current
        while cursor.parent is not None:
            if cursor.tag == tag:
                self.current = cursor.parent
                return
            cursor = cursor.parent

    def handle_data(self, data: str) -> None:
        self.current.children.append(data)


class MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.title_parts: list[str] = []
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr_map = {name.lower(): value for name, value in attrs if value is not None}
        if tag == "title":
            self.in_title = True
        if tag != "meta":
            return

        key = attr_map.get("property") or attr_map.get("name") or attr_map.get("itemprop")
        content = clean_text(attr_map.get("content", ""))
        if key and content:
            self.meta.setdefault(key.lower(), content)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)

    def title(self) -> str:
        return clean_text(" ".join(self.title_parts))


class ScriptTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.current: list[str] | None = None
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "script":
            self.current = []

    def handle_data(self, data: str) -> None:
        if self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self.current is not None:
            self.scripts.append("".join(self.current))
            self.current = None


class ImageRefParser(HTMLParser):
    def __init__(self, base_url: str | None = None):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.refs: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr_map = {name.lower(): value for name, value in attrs if value is not None}
        raw_values: list[tuple[str, str]] = []
        if tag == "img":
            raw_values.append(((attr_map.get("src") or "").strip(), "image"))
        elif tag == "video":
            raw_values.extend(
                [
                    ((attr_map.get("src") or "").strip(), "video"),
                    ((attr_map.get("poster") or "").strip(), "poster"),
                ]
            )
        elif tag == "source":
            raw_values.append(((attr_map.get("src") or "").strip(), "video"))
        else:
            return

        for raw, kind in raw_values:
            if not raw:
                continue
            absolute = parse.urljoin(self.base_url, raw) if self.base_url else raw
            self.refs.append({"raw": raw, "absolute": absolute, "kind": kind})


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key, value)


def site_config(site: str, base_url: str | None = None) -> tuple[str, str, str]:
    if site == "kb":
        url = base_url or os.environ.get("KB_LOCAL_URL") or os.environ.get("KB_PUBLIC_URL")
        if not url:
            url = "https://" + os.environ.get("DOMAIN_KB", "kb.example.com")
        return url, os.environ.get("WP_KB_API_USER", ""), os.environ.get("WP_KB_APP_PASSWORD", "")
    if site == "family":
        url = base_url or "https://" + os.environ.get("DOMAIN_FAMILY", "family.example.com")
        return url, os.environ.get("WP_FAMILY_API_USER", ""), os.environ.get("WP_FAMILY_APP_PASSWORD", "")
    raise ValueError(f"Unknown site: {site}")


def auth_header(user: str, password: str) -> str:
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def api_call(base_url: str, auth: str, method: str, path: str, payload: dict | None = None, headers: dict | None = None) -> dict:
    data = None
    req_headers = {
        "Authorization": auth,
        "Accept": "application/json",
        "User-Agent": "HomeKnowledgeBaseImporter/1.0",
    }
    if headers:
        req_headers.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/json; charset=utf-8"
    req = request.Request(base_url.rstrip("/") + path, data=data, headers=req_headers, method=method)
    with request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def upload_media_bytes(base_url: str, auth: str, filename: str, mime: str, data: bytes) -> dict:
    headers = {
        "Authorization": auth,
        "Accept": "application/json",
        "User-Agent": "HomeKnowledgeBaseImporter/1.0",
        "Content-Type": mime,
        "Content-Disposition": f"attachment; filename={filename}",
    }
    req = request.Request(
        base_url.rstrip("/") + "/wp-json/wp/v2/media",
        data=data,
        headers=headers,
        method="POST",
    )
    with request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def upload_media_file(base_url: str, auth: str, file_path: Path) -> dict:
    mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    return upload_media_bytes(base_url, auth, file_path.name, mime, file_path.read_bytes())


def ensure_term(base_url: str, auth: str, taxonomy: str, name: str) -> int:
    path = f"/wp-json/wp/v2/{taxonomy}?search={parse.quote(name)}"
    found = api_call(base_url, auth, "GET", path)
    for item in found:
        if item.get("name") == name:
            return int(item["id"])
    created = api_call(base_url, auth, "POST", f"/wp-json/wp/v2/{taxonomy}", {"name": name})
    return int(created["id"])


def is_privateish_ip(ip: str) -> bool:
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(
        [
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        ]
    )


def is_proxy_fake_ip(ip: str) -> bool:
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(address in network for network in PROXY_FAKE_IP_NETWORKS)


def host_is_privateish(host: str) -> bool:
    host = host.strip("[]").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return True
    if is_privateish_ip(host):
        return True
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    for info in infos:
        ip = info[4][0]
        if is_privateish_ip(ip) and not is_proxy_fake_ip(ip):
            return True
    return False


def check_fetch_url(url: str, allow_private: bool = False) -> tuple[bool, str]:
    parsed = parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False, "only http/https URLs are supported"
    if not parsed.hostname:
        return False, "missing URL host"
    if not allow_private and host_is_privateish(parsed.hostname):
        return False, "private/local URL is blocked"
    return True, "ok"


def read_limited(resp, max_bytes: int) -> bytes:
    data = resp.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"response is larger than {max_bytes} bytes")
    return data


def html_charset(data: bytes) -> str | None:
    match = re.search(br"<meta[^>]+charset=[\"']?([A-Za-z0-9._-]+)", data[:4096], re.I)
    if not match:
        return None
    try:
        return match.group(1).decode("ascii", "ignore")
    except UnicodeDecodeError:
        return None


def fetch_html(url: str, allow_private: bool = False) -> tuple[str, str]:
    ok, reason = check_fetch_url(url, allow_private)
    if not ok:
        raise ValueError(f"Refusing to fetch {url}: {reason}")
    req = request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
    with request.urlopen(req, timeout=30) as resp:
        content_type = resp.headers.get_content_type()
        if content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
            raise ValueError(f"URL returned unsupported content type: {content_type}")
        data = read_limited(resp, MAX_HTML_BYTES)
        charset = resp.headers.get_content_charset() or html_charset(data) or "utf-8"
        return data.decode(charset, "replace"), resp.geturl()


def fetch_json(url: str, allow_private: bool = False, max_bytes: int = 1024 * 1024) -> dict:
    ok, reason = check_fetch_url(url, allow_private)
    if not ok:
        raise ValueError(f"Refusing to fetch {url}: {reason}")
    req = request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
    with request.urlopen(req, timeout=30) as resp:
        content_type = resp.headers.get_content_type()
        if content_type not in {"application/json", "text/javascript"}:
            raise ValueError(f"URL returned unsupported JSON content type: {content_type}")
        data = read_limited(resp, max_bytes)
        charset = resp.headers.get_content_charset() or "utf-8"
        parsed = json.loads(data.decode(charset, "replace"))
        if not isinstance(parsed, dict):
            raise ValueError("JSON response is not an object")
        return parsed


def fetch_remote_media(
    url: str,
    max_image_bytes: int,
    max_video_bytes: int,
    allow_private: bool = False,
) -> tuple[bytes, str]:
    ok, reason = check_fetch_url(url, allow_private)
    if not ok:
        raise ValueError(reason)
    req = request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
    with request.urlopen(req, timeout=45) as resp:
        mime = resp.headers.get_content_type()
        if mime in ALLOWED_IMAGE_MIME:
            max_bytes = max_image_bytes
            media_label = "image"
        elif mime in ALLOWED_VIDEO_MIME:
            max_bytes = max_video_bytes
            media_label = "video"
        else:
            raise ValueError(f"unsupported media type: {mime}")
        length = resp.headers.get("Content-Length")
        if length and int(length) > max_bytes:
            raise ValueError(f"{media_label} is larger than {max_bytes} bytes")
        data = read_limited(resp, max_bytes)
        return data, mime


def fetch_image(url: str, max_bytes: int, allow_private: bool = False) -> tuple[bytes, str]:
    return fetch_remote_media(url, max_bytes, 0, allow_private)


def parse_metadata(source: str) -> MetadataParser:
    parser = MetadataParser()
    parser.feed(source)
    return parser


def build_tree(source: str) -> Node:
    parser = TreeBuilder()
    parser.feed(source)
    return parser.root


def attr_map(node: Node) -> dict[str, str]:
    return {name.lower(): value for name, value in node.attrs if value is not None}


def node_text(node: Node | str) -> str:
    if isinstance(node, str):
        return node
    if node.tag in DROP_WITH_CONTENT:
        return ""
    return "".join(node_text(child) for child in node.children)


def find_nodes(node: Node, tags: set[str]) -> list[Node]:
    found = [node] if node.tag in tags else []
    for child in node.children:
        if isinstance(child, Node):
            found.extend(find_nodes(child, tags))
    return found


def select_content_node(root: Node) -> Node:
    candidates = find_nodes(root, {"article", "main"})
    scored = [(len(clean_text(node_text(node))), node) for node in candidates]
    scored = [(score, node) for score, node in scored if score >= 200]
    if scored:
        return max(scored, key=lambda item: item[0])[1]
    body_nodes = find_nodes(root, {"body"})
    return body_nodes[0] if body_nodes else root


def safe_href(url: str, base_url: str | None) -> str:
    href = parse.urljoin(base_url, url.strip()) if base_url else url.strip()
    scheme = parse.urlparse(href).scheme.lower()
    if scheme and scheme not in {"http", "https", "mailto", "tel"}:
        return ""
    return href


def serialize_node(node: Node | str, base_url: str | None = None) -> str:
    if isinstance(node, str):
        return html.escape(node)
    if node.tag in DROP_WITH_CONTENT:
        return ""
    if node.tag in {"document", "body", "article", "main", "div", "section", "span"}:
        return "".join(serialize_node(child, base_url) for child in node.children)
    if node.tag not in ALLOWED_TAGS:
        return "".join(serialize_node(child, base_url) for child in node.children)

    tag = "h2" if node.tag == "h1" else node.tag
    attrs = attr_map(node)
    rendered_attrs: list[str] = []
    if tag == "a":
        href = safe_href(attrs.get("href", ""), base_url)
        if href:
            rendered_attrs.append(f'href="{html.escape(href, quote=True)}"')
            rendered_attrs.append('target="_blank"')
            rendered_attrs.append('rel="noopener noreferrer"')
    elif tag == "img":
        src = safe_href(attrs.get("src", ""), base_url)
        if not src:
            return ""
        rendered_attrs.append(f'src="{html.escape(src, quote=True)}"')
        for key in ("alt", "title"):
            if attrs.get(key):
                rendered_attrs.append(f'{key}="{html.escape(clean_text(attrs[key]), quote=True)}"')

    open_tag = f"<{tag}{(' ' + ' '.join(rendered_attrs)) if rendered_attrs else ''}>"
    if tag in VOID_TAGS:
        return open_tag
    return open_tag + "".join(serialize_node(child, base_url) for child in node.children) + f"</{tag}>"


def collapse_empty_blocks(markup: str) -> str:
    markup = re.sub(r"<(p|li|blockquote|figcaption)>\s*</\1>", "", markup)
    markup = re.sub(r"\n{3,}", "\n\n", markup)
    return markup.strip()


def summarize(text: str, limit: int = 220) -> str:
    text = clean_text(text)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def meta_first(meta: MetadataParser, keys: list[str]) -> str:
    for key in keys:
        value = meta.meta.get(key.lower())
        if value:
            return value
    return ""


def site_from_url(url: str) -> str:
    host = parse.urlparse(url).hostname or ""
    host = host.removeprefix("www.")
    return host


def is_medisearch_share_url(url: str) -> bool:
    parsed = parse.urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    return host == "medisearch.io" and parsed.path.startswith("/share/")


def next_flight_text(source: str) -> str:
    parts: list[str] = []
    pattern = re.compile(r"self\.__next_f\.push\((\[.*?\])\)</script>", re.S)
    for match in pattern.finditer(source):
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, list) and len(payload) >= 2 and isinstance(payload[1], str):
            parts.append(payload[1])
    return "".join(parts)


def json_string_value(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value


def react_flight_t_value(text: str, key: str) -> str:
    marker = f"{key}:T"
    start = text.find(marker)
    if start == -1:
        return ""
    cursor = start + len(marker)
    comma = text.find(",", cursor)
    if comma == -1:
        return ""
    try:
        byte_count = int(text[cursor:comma], 16)
    except ValueError:
        return ""

    body_start = comma + 1
    consumed = 0
    chars: list[str] = []
    for char in text[body_start:]:
        char_size = len(char.encode("utf-8"))
        if consumed + char_size > byte_count:
            break
        chars.append(char)
        consumed += char_size
        if consumed == byte_count:
            break
    return "".join(chars).strip()


def markdownish_inline_html(value: str) -> str:
    escaped = html.escape(value.strip())
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def medisearch_text_to_html(text: str) -> str:
    text = re.sub(r"([。！？])\s*(\*\*[^*]+\*\*)", r"\1\n\n\2", text.strip())
    text = re.sub(r"\s+-\s+", "\n- ", text)
    html_parts: list[str] = []
    list_items: list[str] = []
    paragraph_lines: list[str] = []

    def flush_list() -> None:
        if not list_items:
            return
        html_parts.append("<ul>" + "".join(f"<li>{item}</li>" for item in list_items) + "</ul>")
        list_items.clear()

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        paragraph = " ".join(paragraph_lines)
        if re.fullmatch(r"\*\*[^*]+\*\*", paragraph):
            html_parts.append(f"<h3>{markdownish_inline_html(paragraph.strip('*'))}</h3>")
        else:
            html_parts.append(f"<p>{markdownish_inline_html(paragraph)}</p>")
        paragraph_lines.clear()

    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        for line in lines:
            if line.startswith(("- ", "* ")):
                flush_paragraph()
                list_items.append(markdownish_inline_html(line[2:]))
                continue
            flush_list()
            paragraph_lines.append(line)
        flush_paragraph()

    flush_list()
    return "\n".join(html_parts)


def medisearch_title(report_title: str, questions: list[str]) -> str:
    joined = " ".join([report_title, *questions])
    if "乳腺癌" in joined and "肝转移" in joined and "2024年7月30日" in joined:
        return "乳腺癌肝转移两次 MRI 影像对比：化疗后病灶变化"
    if "乳腺癌" in joined and "肝转移" in joined and "MRI" in joined.upper():
        return "乳腺癌肝转移 MRI 报告解读"
    if "MRI" in joined.upper():
        return "MRI 报告解读与随访要点"
    return "MediSearch 医学资料整理"


def content_from_medisearch(url: str, args: argparse.Namespace) -> dict:
    source, final_url = fetch_html(url, args.allow_private_url)
    meta = parse_metadata(source)
    report_title = meta_first(meta, ["og:title", "twitter:title"]) or meta.title()
    first_answer = meta_first(meta, ["og:description", "twitter:description", "description"])
    flight = next_flight_text(source)

    qa_items: list[tuple[str, str]] = []
    seen_questions: set[str] = set()
    for match in re.finditer(r'"question":"((?:\\.|[^"\\])*)","answer":"\$(\w+)"', flight):
        question = clean_text(json_string_value(match.group(1)))
        answer = react_flight_t_value(flight, match.group(2))
        if question and answer and len(answer) >= 120 and question not in seen_questions:
            qa_items.append((question, answer))
            seen_questions.add(question)

    body_parts = [
        "<p><strong>医学提醒：</strong>以下内容是对 MediSearch 分享页的资料整理，不能替代医生诊断或 MDT 治疗决策。</p>",
    ]
    if first_answer:
        body_parts.append("<h2>2026年5月28日 MRI 报告解读</h2>")
        body_parts.append(medisearch_text_to_html(first_answer))

    for question, answer in qa_items:
        if "2026年5月28日" in question and "2024年7月30日" in question:
            section_title = "两次 MRI 影像对比：2024-07-30 vs 2026-05-28"
        else:
            section_title = question
        body_parts.append(f"<h2>{html.escape(section_title)}</h2>")
        body_parts.append(f"<blockquote><p><strong>原始追问：</strong>{html.escape(question)}</p></blockquote>")
        body_parts.append(medisearch_text_to_html(answer))

    if report_title:
        body_parts.append("<h2>原始影像报告</h2>")
        body_parts.append(f"<blockquote><p>{html.escape(report_title)}</p></blockquote>")
    body_parts.append("<p>参考文献编号沿用 MediSearch 原文；完整文献链接请查看来源页面。</p>")

    excerpt_source = " ".join([first_answer, *[answer for _, answer in qa_items]])
    return {
        "title": args.title or medisearch_title(report_title, [question for question, _ in qa_items]),
        "content": "\n\n".join(part for part in body_parts if part),
        "excerpt": args.excerpt or summarize(excerpt_source),
        "source_url": args.source_url or final_url,
        "source_site": args.source_site or "MediSearch",
        "source_author": args.source_author or "MediSearch",
        "base_url": final_url,
    }


def is_x_status_url(url: str) -> bool:
    parsed = parse.urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if host not in {"x.com", "twitter.com", "mobile.twitter.com"}:
        return False
    return bool(re.search(r"/(?:i/)?status(?:es)?/\d+", parsed.path))


def x_status_id(url: str) -> str:
    match = re.search(r"/(?:i/)?status(?:es)?/(\d+)", parse.urlparse(url).path)
    return match.group(1) if match else ""


def json_object_after_marker(source: str, marker: str) -> dict:
    decoder = json.JSONDecoder()
    start = source.find(marker)
    while start != -1:
        cursor = start + len(marker)
        while cursor < len(source) and source[cursor].isspace():
            cursor += 1
        if cursor < len(source) and source[cursor] == "{":
            try:
                obj, _ = decoder.raw_decode(source[cursor:])
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(obj, dict):
                    return obj
        start = source.find(marker, start + 1)
    return {}


def extract_x_tweet(source: str, tweet_id: str) -> dict:
    marker = f'"{tweet_id}":'
    cursor = source.find(marker)
    while cursor != -1:
        obj = json_object_after_marker(source[cursor:], marker)
        if obj.get("id_str") == tweet_id and obj.get("full_text"):
            return obj
        cursor = source.find(marker, cursor + 1)
    return {}


def extract_x_user(source: str, user_id: str) -> dict:
    if not user_id:
        return {}
    return json_object_after_marker(source, f'"{user_id}":')


def x_media_items(tweet: dict) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for container in (tweet.get("extended_entities") or {}, tweet.get("entities") or {}):
        for media in container.get("media") or []:
            if not isinstance(media, dict):
                continue
            media_url = media.get("media_url_https") or media.get("media_url")
            if not media_url or media_url in seen:
                continue
            seen.add(media_url)
            items.append(media)
    return items


def x_display_text(tweet: dict, media_items: list[dict]) -> str:
    text = str(tweet.get("full_text") or "")
    display_range = tweet.get("display_text_range")
    if (
        isinstance(display_range, list)
        and len(display_range) == 2
        and all(isinstance(item, int) for item in display_range)
    ):
        text = text[display_range[0] : display_range[1]]
    for media in media_items:
        short_url = str(media.get("url") or "")
        if short_url:
            text = text.replace(short_url, "")
    return clean_text_preserve_breaks(text)


def clean_text_preserve_breaks(value: str) -> str:
    value = html.unescape(value or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.split("\n")]
    return "\n".join(lines).strip()


def text_is_url_only(value: str) -> bool:
    text = clean_text_preserve_breaks(value)
    if not text:
        return True
    without_urls = re.sub(URL_TEXT_PATTERN, "", text)
    without_urls = re.sub(r"[\s\W_]+", "", without_urls, flags=re.U)
    return not without_urls.strip()


def title_should_use_remote(value: str) -> bool:
    title = clean_text(value)
    if not title:
        return True
    return text_is_url_only(title) or bool(re.search(r"\bon\s+X:\s*https?://", title, re.I))


def text_with_links_to_html(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(
        URL_TEXT_PATTERN,
        lambda match: (
            f'<a href="{html.escape(match.group(1), quote=True)}" '
            f'target="_blank" rel="noopener noreferrer">{html.escape(match.group(1))}</a>'
        ),
        escaped,
    )
    blocks = [block.strip() for block in re.split(r"\n\s*\n", escaped) if block.strip()]
    return "\n".join(f"<p>{block.replace(chr(10), '<br>')}</p>" for block in blocks)


def linkify_escaped_text(escaped: str) -> str:
    return re.sub(
        URL_TEXT_PATTERN,
        lambda match: (
            f'<a href="{html.escape(match.group(1), quote=True)}" '
            f'target="_blank" rel="noopener noreferrer">{html.escape(match.group(1))}</a>'
        ),
        escaped,
    )


def x_article_heading(line: str) -> str:
    line = line.strip()
    if re.match(r"^(目录|文章导读|附录|结论|总结)$", line):
        return "h2"
    if re.match(r"^[一二三四五六七八九十]+[、.．]\s*\S", line):
        return "h2"
    if re.match(r"^第[一二三四五六七八九十\d]+[章节步部分][：:、\s]\S*", line):
        return "h2"
    if re.match(r"^\d+\s*[.．、]\s*(有顺序|无序|步骤|选项|项目)", line):
        return ""
    if re.match(r"^拓展[一二三四五六七八九十]+[：:]", line):
        return "h2"
    return ""


def x_article_visual_cue(text: str) -> bool:
    return bool(re.search(r"(如下|截图|页面|界面|效果|长这样|预览|设置页|下载页面|安装页面)", text))


def x_article_text_to_html(text: str, media_items: list[dict]) -> str:
    figures = [figure_html_for_media(media) for media in media_items]
    figures = [figure for figure in figures if figure]
    figure_index = 0
    output: list[str] = []
    paragraph_lines: list[str] = []
    paragraph_count = 0

    def ordered_item(line: str) -> str:
        match = re.match(r"^\d+\s*[.．、]\s*(\S.*)$", line)
        return match.group(1).strip() if match else ""

    def unordered_item(line: str) -> str:
        match = re.match(r"^[\-*•]\s*(\S.*)$", line)
        return match.group(1).strip() if match else ""

    def strip_order_marker(line: str) -> str:
        return re.sub(r"^\d+\s*[.．、]\s*", "", line).strip()

    def list_intro(line: str) -> bool:
        return bool(re.search(r"(比如|包括|如下|这些|分别是)[：:]$", line))

    def short_list_line(line: str, max_len: int = 32) -> bool:
        if not line or x_article_heading(line) or ordered_item(line) or unordered_item(line):
            return False
        if re.search(r"[。！？；]$", line):
            return False
        return len(line) <= max_len

    def take_figure() -> str:
        nonlocal figure_index
        if figure_index >= len(figures):
            return ""
        figure = figures[figure_index]
        figure_index += 1
        return figure

    def flush_paragraph(force_figure: bool = False) -> None:
        nonlocal paragraph_count
        if not paragraph_lines:
            return
        paragraph_text = "\n".join(paragraph_lines).strip()
        paragraph_lines.clear()
        if not paragraph_text:
            return
        escaped = linkify_escaped_text(html.escape(paragraph_text)).replace("\n", "<br>")
        output.append(f"<p>{escaped}</p>")
        paragraph_count += 1
        if force_figure or (paragraph_count == 1 and figures) or x_article_visual_cue(paragraph_text):
            figure = take_figure()
            if figure:
                output.append(figure)

    def append_list(tag: str, items: list[str]) -> None:
        if not items:
            return
        rendered = "".join(
            f"<li>{linkify_escaped_text(html.escape(item))}</li>" for item in items if item
        )
        if rendered:
            output.append(f"<{tag}>{rendered}</{tag}>")

    lines = [raw_line.strip() for raw_line in text.splitlines()]
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line:
            flush_paragraph()
            index += 1
            continue

        numbered = ordered_item(line)
        if numbered:
            ordered_items = [numbered]
            lookahead = index + 1
            while lookahead < len(lines):
                next_item = ordered_item(lines[lookahead])
                if not next_item:
                    break
                ordered_items.append(next_item)
                lookahead += 1
            if len(ordered_items) >= 2:
                flush_paragraph()
                append_list("ol", ordered_items)
                index = lookahead
                continue

        bullet = unordered_item(line)
        if bullet:
            bullet_items = [bullet]
            lookahead = index + 1
            while lookahead < len(lines):
                next_item = unordered_item(lines[lookahead])
                if not next_item:
                    break
                bullet_items.append(next_item)
                lookahead += 1
            if len(bullet_items) >= 1:
                flush_paragraph()
                append_list("ul", bullet_items)
                index = lookahead
                continue

        heading_tag = x_article_heading(line)
        if heading_tag:
            flush_paragraph()
            output.append(f"<{heading_tag}>{html.escape(line)}</{heading_tag}>")
            index += 1
            if line in {"目录", "文章导读"}:
                toc_items: list[str] = []
                while index < len(lines):
                    next_line = lines[index]
                    if not next_line:
                        index += 1
                        if toc_items:
                            break
                        continue
                    if x_article_heading(next_line):
                        break
                    toc_items.append(strip_order_marker(next_line))
                    index += 1
                if len(toc_items) >= 2:
                    append_list("ol", toc_items)
                else:
                    paragraph_lines.extend(toc_items)
                    flush_paragraph()
            continue

        if list_intro(line):
            lookahead = index + 1
            short_items: list[str] = []
            while lookahead < len(lines) and short_list_line(lines[lookahead]):
                short_items.append(lines[lookahead])
                lookahead += 1
            if len(short_items) >= 2:
                flush_paragraph()
                output.append(f"<p>{linkify_escaped_text(html.escape(line))}</p>")
                paragraph_count += 1
                append_list("ul", short_items)
                if paragraph_count == 1:
                    figure = take_figure()
                    if figure:
                        output.append(figure)
                index = lookahead
                continue

        paragraph_lines.append(line)
        index += 1

    flush_paragraph()

    if figure_index < len(figures):
        output.append("<h2>原文配图</h2>")
        output.extend(figures[figure_index:])

    return "\n".join(output)


def x_main_script_url(source: str) -> str:
    match = re.search(
        r'https://abs\.twimg\.com/responsive-web/client-web/main\.[^"\']+\.js',
        source,
    )
    if match:
        return html.unescape(match.group(0))
    match = re.search(r'["\'](https://abs\.twimg\.com/responsive-web/client-web/[^"\']*main[^"\']*\.js)["\']', source)
    return html.unescape(match.group(1)) if match else ""


def fetch_text_asset(url: str, allow_private: bool = False, max_bytes: int = 3 * 1024 * 1024) -> str:
    ok, reason = check_fetch_url(url, allow_private)
    if not ok:
        raise ValueError(f"Refusing to fetch {url}: {reason}")
    req = request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
    with request.urlopen(req, timeout=30) as resp:
        data = read_limited(resp, max_bytes)
        charset = resp.headers.get_content_charset() or "utf-8"
        return data.decode(charset, "replace")


def x_web_api_config(tweet_id: str = "") -> dict[str, str]:
    global X_WEB_API_CONFIG
    if X_WEB_API_CONFIG:
        return X_WEB_API_CONFIG

    sources: list[str] = []
    if tweet_id:
        try:
            source, _final_url = fetch_x_page_html(f"https://x.com/i/status/{tweet_id}", False)
            sources.append(source)
        except (OSError, ValueError, error.URLError, error.HTTPError):
            pass
    source, _final_url = fetch_html("https://x.com/", False)
    sources.append(source)

    script_url = x_main_script_url(source)
    for candidate in sources:
        script_url = x_main_script_url(candidate)
        if script_url:
            break
    if not script_url:
        raise ValueError("X page did not expose main script URL")

    script = fetch_text_asset(script_url, False)
    bearer_match = re.search(r"Bearer\s+(AAAA[A-Za-z0-9%_.-]+)", script)
    query_match = re.search(r'queryId:"([^"]+)",operationName:"TweetResultByRestId"', script)
    if not bearer_match or not query_match:
        raise ValueError("X main script did not expose API bearer/query ID")

    X_WEB_API_CONFIG = {
        "bearer": bearer_match.group(1),
        "tweet_result_query_id": query_match.group(1),
    }
    return X_WEB_API_CONFIG


def x_api_bearer(tweet_id: str = "") -> str:
    return X_API_BEARER or x_web_api_config(tweet_id).get("bearer", "")


def x_tweet_result_query_id(tweet_id: str = "") -> str:
    if X_API_BEARER and X_TWEET_RESULT_QUERY_ID:
        return X_TWEET_RESULT_QUERY_ID
    return x_web_api_config(tweet_id).get("tweet_result_query_id", X_TWEET_RESULT_QUERY_ID)


def x_api_json(path: str, params: dict | None = None, guest_token: str | None = None) -> dict:
    bearer = x_api_bearer()
    if not bearer:
        raise ValueError("Set X_API_BEARER to enable X/Twitter API imports")
    url = "https://x.com" + path
    if params:
        url += "?" + parse.urlencode(params)
    headers = {
        "Authorization": "Bearer " + bearer,
        "Accept": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
        ),
        "X-Twitter-Active-User": "yes",
        "X-Twitter-Client-Language": "zh-cn",
    }
    if guest_token:
        headers["X-Guest-Token"] = guest_token
    req = request.Request(url, headers=headers)
    with request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def x_guest_token(tweet_id: str = "") -> str:
    bearer = x_api_bearer(tweet_id)
    if not bearer:
        raise ValueError("Set X_API_BEARER to enable X/Twitter API imports")
    req = request.Request(
        "https://api.x.com/1.1/guest/activate.json",
        data=b"",
        headers={
            "Authorization": "Bearer " + bearer,
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
            ),
        },
        method="POST",
    )
    with request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8", "replace"))
    token = str(data.get("guest_token") or "")
    if not token:
        raise ValueError("X guest token response is empty")
    return token


def fetch_x_tweet_result(tweet_id: str) -> dict:
    variables = {
        "tweetId": tweet_id,
        "withCommunity": False,
        "includePromotedContent": False,
        "withVoice": False,
    }
    params = {
        "variables": json.dumps(variables, separators=(",", ":")),
        "features": json.dumps(X_TWEET_RESULT_FEATURES, separators=(",", ":")),
        "fieldToggles": json.dumps(X_TWEET_RESULT_FIELD_TOGGLES, separators=(",", ":")),
    }
    data = x_api_json(
        f"/i/api/graphql/{x_tweet_result_query_id(tweet_id)}/TweetResultByRestId",
        params,
        guest_token=x_guest_token(tweet_id),
    )
    result = (((data.get("data") or {}).get("tweetResult") or {}).get("result") or {})
    if not result or result.get("__typename") != "Tweet":
        raise ValueError("X API did not return a tweet")
    return result


def x_user_identity(tweet: dict) -> tuple[str, str, str]:
    user = (((tweet.get("core") or {}).get("user_results") or {}).get("result") or {})
    core = user.get("core") or {}
    legacy = user.get("legacy") or {}
    name = clean_text(str(core.get("name") or legacy.get("name") or ""))
    screen_name = clean_text(str(core.get("screen_name") or legacy.get("screen_name") or ""))
    label = name or screen_name
    url = f"https://x.com/{screen_name}" if screen_name else ""
    return label, screen_name, url


def x_api_media_info(media: dict) -> dict:
    media_info = media.get("media_info") or media
    return media_info if isinstance(media_info, dict) else {}


def x_api_video_url(media: dict) -> str:
    media_info = x_api_media_info(media)
    video_info = media_info.get("video_info") or media.get("video_info") or {}
    variants = video_info.get("variants") or []
    mp4_variants = [
        variant
        for variant in variants
        if isinstance(variant, dict)
        and str(variant.get("content_type") or "").lower() == "video/mp4"
        and variant.get("url")
    ]
    if not mp4_variants:
        return ""
    best = max(mp4_variants, key=lambda variant: int(variant.get("bitrate") or 0))
    return str(best.get("url") or "")


def x_api_media_url(media: dict) -> str:
    media_info = x_api_media_info(media)
    return str(
        media_info.get("original_img_url")
        or media_info.get("media_url_https")
        or media_info.get("media_url")
        or ""
    )


def x_api_media_items(tweet: dict, article: dict | None = None) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()

    def add(media: dict) -> None:
        if not isinstance(media, dict):
            return
        media_url = x_api_video_url(media) or x_api_media_url(media)
        if not media_url or media_url in seen:
            return
        seen.add(media_url)
        items.append(media)

    legacy = tweet.get("legacy") or {}
    for container in (legacy.get("extended_entities") or {}, legacy.get("entities") or {}):
        for media in container.get("media") or []:
            add(media)

    if article:
        add(article.get("cover_media") or {})
        for media in article.get("media_entities") or []:
            add(media)
    return items


def x_article_result(tweet: dict) -> dict:
    article = tweet.get("article") or {}
    return ((article.get("article_results") or {}).get("result") or {})


def x_note_text(tweet: dict) -> str:
    result = (
        (((tweet.get("note_tweet") or {}).get("note_tweet_results") or {}).get("result") or {})
    )
    return clean_text_preserve_breaks(str(result.get("text") or ""))


def x_legacy_text(tweet: dict, media_items: list[dict]) -> str:
    legacy = tweet.get("legacy") or {}
    text = str(legacy.get("full_text") or "")
    display_range = legacy.get("display_text_range")
    if (
        isinstance(display_range, list)
        and len(display_range) == 2
        and all(isinstance(item, int) for item in display_range)
    ):
        text = text[display_range[0] : display_range[1]]
    for media in media_items:
        short_url = str(media.get("url") or "")
        if short_url:
            text = text.replace(short_url, "")
    return clean_text_preserve_breaks(text)


def x_article_text(article: dict) -> str:
    return clean_text_preserve_breaks(str(article.get("plain_text") or ""))


def x_article_title(article: dict) -> str:
    return clean_text(str(article.get("title") or ""))


def figure_html_for_media(media: dict, fallback_alt: str = "X 配图") -> str:
    media_url = x_api_media_url(media)
    video_url = x_api_video_url(media)
    if not media_url and not video_url:
        return ""
    alt = clean_text(
        str(
            media.get("ext_alt_text")
            or media.get("display_url")
            or media.get("media_key")
            or fallback_alt
        )
    )
    alt_attr = html.escape(alt, quote=True)
    caption_html = "" if re.fullmatch(r"(?:\d+_)?\d{10,}|[A-Za-z0-9_-]{8,}", alt) else f"<figcaption>{html.escape(alt)}</figcaption>"
    if video_url:
        video_url_attr = html.escape(video_url, quote=True)
        poster_attr = f' poster="{html.escape(media_url, quote=True)}"' if media_url else ""
        return f'<figure><video controls preload="metadata" src="{video_url_attr}"{poster_attr}></video>{caption_html}</figure>'

    media_url_attr = html.escape(media_url, quote=True)
    if re.fullmatch(r"(?:\d+_)?\d{10,}|[A-Za-z0-9_-]{8,}", alt):
        return f'<figure><img src="{media_url_attr}" alt="{alt_attr}"></figure>'
    return f'<figure><img src="{media_url_attr}" alt="{alt_attr}">{caption_html}</figure>'


def content_from_x_api(url: str, args: argparse.Namespace) -> dict:
    tweet_id = x_status_id(url)
    if not tweet_id:
        raise ValueError("X status URL has no tweet ID")
    tweet = fetch_x_tweet_result(tweet_id)
    author_label, _screen_name, author_url = x_user_identity(tweet)
    article = x_article_result(tweet)
    media_items = x_api_media_items(tweet, article if article else None)

    if article:
        title = x_article_title(article) or args.title
        text = x_article_text(article)
        source_text = text or x_legacy_text(tweet, media_items)
        content_title = title if title_should_use_remote(args.title) and title else (args.title or title or f"{author_label} on X")
    else:
        note_text = x_note_text(tweet)
        source_text = note_text or x_legacy_text(tweet, media_items)
        content_title = args.title if not title_should_use_remote(args.title) else (
            f"{author_label} on X: {summarize(source_text, 64)}" if source_text else url
        )

    pieces = []
    if source_text:
        if article:
            pieces.append(x_article_text_to_html(source_text, media_items))
        else:
            pieces.append("<blockquote>" + text_with_links_to_html(source_text) + "</blockquote>")
            for media in media_items:
                figure = figure_html_for_media(media)
                if figure:
                    pieces.append(figure)
    if author_label:
        if author_url:
            safe_author_url = html.escape(author_url, quote=True)
            safe_author = html.escape(author_label)
            pieces.append(
                f'<p><strong>作者：</strong><a href="{safe_author_url}" target="_blank" rel="noopener noreferrer">{safe_author}</a></p>'
            )
        else:
            pieces.append(f"<p><strong>作者：</strong>{html.escape(author_label)}</p>")

    return {
        "title": content_title,
        "content": "\n".join(pieces),
        "excerpt": args.excerpt or summarize(source_text),
        "source_url": args.source_url or url,
        "source_site": args.source_site or "X / Twitter",
        "source_author": args.source_author or author_label,
        "base_url": url,
    }


def fetch_x_page_html(url: str, allow_private: bool = False) -> tuple[str, str]:
    ok, reason = check_fetch_url(url, allow_private)
    if not ok:
        raise ValueError(f"Refusing to fetch {url}: {reason}")
    req = request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
            ),
            "Accept-Encoding": "identity",
        },
    )
    with request.urlopen(req, timeout=30) as resp:
        data = read_limited(resp, MAX_HTML_BYTES)
        charset = resp.headers.get_content_charset() or html_charset(data) or "utf-8"
        return data.decode(charset, "replace"), resp.geturl()


def decode_js_string_literal(value: str) -> str:
    try:
        decoded = json.loads('"' + value + '"')
    except json.JSONDecodeError:
        return value.replace("\\n", "\n").replace('\\"', '"').replace("\\/", "/")
    return decoded if isinstance(decoded, str) else ""


def first_js_string(source: str, pattern: str) -> str:
    match = re.search(pattern, source, re.S)
    if not match:
        return ""
    return decode_js_string_literal(match.group(1))


def x_stream_media_items(source: str) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for field in ("media_url_https", "original_img_url"):
        for raw_url in re.findall(field + r':"((?:\\.|[^"\\])*)"', source, re.S):
            media_url = decode_js_string_literal(raw_url)
            if not media_url or media_url in seen:
                continue
            seen.add(media_url)
            items.append({"media_url_https": media_url, "type": "photo"})
    return items


def x_author_from_meta(source: str) -> tuple[str, str, str]:
    meta = parse_metadata(source)
    title = meta_first(meta, ["og:title", "twitter:title"]) or meta.title()
    match = re.match(r"(.+?)\s+\(@([^)]+)\)\s+on X", title)
    if match:
        author_name = clean_text(match.group(1))
        screen_name = clean_text(match.group(2))
        return author_name, screen_name, f"https://x.com/{screen_name}"

    author_name = first_js_string(source, r'relevantPerson:\$R\[\d+\]=\{name:"((?:\\.|[^"\\])*)"')
    screen_name = first_js_string(source, r'relevantPerson:\$R\[\d+\]=\{name:"(?:\\.|[^"\\])*",screenName:"((?:\\.|[^"\\])*)"')
    if author_name or screen_name:
        return author_name or screen_name, screen_name, f"https://x.com/{screen_name}" if screen_name else ""

    return "", "", ""


def x_article_entity_from_stream(source: str) -> dict:
    match = re.search(
        r'__typename:"ArticleEntity",rest_id:"((?:\\.|[^"\\])*)",title:"((?:\\.|[^"\\])*)",preview_text:"((?:\\.|[^"\\])*)"',
        source,
        re.S,
    )
    if not match:
        return {}

    rest_id = clean_text(decode_js_string_literal(match.group(1)))
    title = clean_text(decode_js_string_literal(match.group(2)))
    preview = clean_text_preserve_breaks(decode_js_string_literal(match.group(3)))
    cover_url = first_js_string(source, r'original_img_url:"((?:\\.|[^"\\])*)"')

    if not title and not preview:
        return {}

    return {
        "rest_id": rest_id,
        "title": title,
        "preview": preview,
        "cover_url": cover_url,
        "url": f"https://x.com/i/article/{rest_id}" if rest_id else "",
    }


def content_from_x_article_entity(article: dict, args: argparse.Namespace, final_url: str, author_label: str, author_url: str) -> dict:
    pieces = []
    article_url = str(article.get("url") or "")
    if article_url:
        safe_url = html.escape(article_url, quote=True)
        pieces.append(
            f'<p><strong>X Article：</strong><a href="{safe_url}" target="_blank" rel="noopener noreferrer">{html.escape(article_url)}</a></p>'
        )

    cover_url = str(article.get("cover_url") or "")
    if cover_url:
        pieces.append(figure_html_for_media({"media_url_https": cover_url, "display_url": article.get("title") or "X Article"}))

    preview = clean_text_preserve_breaks(str(article.get("preview") or ""))
    if preview:
        pieces.append("<h2>文章导读</h2>")
        pieces.append(text_with_links_to_html(preview))

    if author_label:
        if author_url:
            safe_author_url = html.escape(author_url, quote=True)
            safe_author = html.escape(author_label)
            pieces.append(
                f'<p><strong>作者：</strong><a href="{safe_author_url}" target="_blank" rel="noopener noreferrer">{safe_author}</a></p>'
            )
        else:
            pieces.append(f"<p><strong>作者：</strong>{html.escape(author_label)}</p>")

    article_title = clean_text(str(article.get("title") or ""))
    return {
        "title": article_title if title_should_use_remote(args.title) and article_title else (args.title or article_title or "X Article"),
        "content": "\n".join(piece for piece in pieces if piece),
        "excerpt": args.excerpt or summarize(preview),
        "source_url": args.source_url or final_url,
        "source_site": args.source_site or "X / Twitter",
        "source_author": args.source_author or author_label,
        "base_url": final_url,
    }


def content_from_x_stream(url: str, args: argparse.Namespace) -> dict:
    source, final_url = fetch_x_page_html(url, args.allow_private_url)
    article = x_article_entity_from_stream(source)
    note_text = first_js_string(source, r'__typename:"NoteTweet",text:"((?:\\.|[^"\\])*)"')
    legacy_text = first_js_string(source, r'full_text:"((?:\\.|[^"\\])*)"')
    source_text = clean_text_preserve_breaks(note_text or legacy_text)
    author_label, _screen_name, author_url = x_author_from_meta(source)

    if article and (not source_text or text_is_url_only(source_text)):
        return content_from_x_article_entity(article, args, final_url, author_label, author_url)

    if not source_text:
        raise ValueError("X page did not expose tweet text")

    media_items = x_stream_media_items(source)

    pieces = ["<blockquote>" + text_with_links_to_html(source_text) + "</blockquote>"]
    for media in media_items:
        figure = figure_html_for_media(media)
        if figure:
            pieces.append(figure)
    if author_label:
        if author_url:
            safe_author_url = html.escape(author_url, quote=True)
            safe_author = html.escape(author_label)
            pieces.append(
                f'<p><strong>作者：</strong><a href="{safe_author_url}" target="_blank" rel="noopener noreferrer">{safe_author}</a></p>'
            )
        else:
            pieces.append(f"<p><strong>作者：</strong>{html.escape(author_label)}</p>")

    title_prefix = f"{author_label} on X" if author_label else "X / Twitter"
    return {
        "title": args.title if not title_should_use_remote(args.title) else f"{title_prefix}: {summarize(source_text, 64)}",
        "content": "\n".join(pieces),
        "excerpt": args.excerpt or summarize(source_text),
        "source_url": args.source_url or final_url,
        "source_site": args.source_site or "X / Twitter",
        "source_author": args.source_author or author_label,
        "base_url": final_url,
    }


def content_from_x_page(url: str, args: argparse.Namespace) -> dict:
    source, final_url = fetch_x_page_html(url, args.allow_private_url)
    tweet_id = x_status_id(final_url) or x_status_id(url)
    tweet = extract_x_tweet(source, tweet_id)
    if not tweet:
        raise ValueError("X page did not expose tweet data")

    user = extract_x_user(source, str(tweet.get("user") or ""))
    author_name = clean_text(str(user.get("name") or user.get("screen_name") or ""))
    screen_name = clean_text(str(user.get("screen_name") or ""))
    author_label = author_name or screen_name
    author_url = f"https://x.com/{screen_name}" if screen_name else ""
    media_items = x_media_items(tweet)
    tweet_text = x_display_text(tweet, media_items)

    pieces = []
    if tweet_text:
        pieces.append("<blockquote>" + text_with_links_to_html(tweet_text) + "</blockquote>")
    for media in media_items:
        figure = figure_html_for_media(media)
        if figure:
            pieces.append(figure)
    if author_label:
        if author_url:
            safe_author_url = html.escape(author_url, quote=True)
            safe_author = html.escape(author_label)
            pieces.append(
                f'<p><strong>作者：</strong><a href="{safe_author_url}" target="_blank" rel="noopener noreferrer">{safe_author}</a></p>'
            )
        else:
            pieces.append(f"<p><strong>作者：</strong>{html.escape(author_label)}</p>")

    title_prefix = f"{author_label} on X" if author_label else "X / Twitter"
    return {
        "title": args.title or (f"{title_prefix}: {summarize(tweet_text, 64)}" if tweet_text else final_url),
        "content": "\n".join(pieces),
        "excerpt": args.excerpt or summarize(tweet_text),
        "source_url": args.source_url or final_url,
        "source_site": args.source_site or "X / Twitter",
        "source_author": args.source_author or author_label,
        "base_url": final_url,
    }


def content_from_x_oembed(url: str, args: argparse.Namespace) -> dict:
    api_url = "https://publish.twitter.com/oembed?" + parse.urlencode(
        {
            "url": url,
            "omit_script": "true",
            "dnt": "true",
            "lang": "zh-cn",
        }
    )
    data = fetch_json(api_url, args.allow_private_url)
    embed_html = str(data.get("html") or "")
    root = build_tree(embed_html)
    paragraph_nodes = find_nodes(root, {"p"})
    tweet_node = paragraph_nodes[0] if paragraph_nodes else root
    tweet_html = collapse_empty_blocks(serialize_node(tweet_node, url))
    tweet_text = clean_text(node_text(tweet_node))
    author_name = clean_text(str(data.get("author_name") or ""))
    author_url = str(data.get("author_url") or "")
    source_url = args.source_url or str(data.get("url") or url)

    pieces = []
    if tweet_html:
        pieces.append(f"<blockquote>{tweet_html}</blockquote>")
    if author_name:
        if author_url:
            safe_author_url = html.escape(author_url, quote=True)
            safe_author = html.escape(author_name)
            pieces.append(
                f'<p><strong>作者：</strong><a href="{safe_author_url}" target="_blank" rel="noopener noreferrer">{safe_author}</a></p>'
            )
        else:
            pieces.append(f"<p><strong>作者：</strong>{html.escape(author_name)}</p>")

    title_prefix = f"{author_name} on X" if author_name else "X / Twitter"
    return {
        "title": args.title or (f"{title_prefix}: {summarize(tweet_text, 80)}" if tweet_text else source_url),
        "content": "\n".join(pieces) if pieces else "",
        "excerpt": args.excerpt or summarize(tweet_text),
        "source_url": source_url,
        "source_site": args.source_site or "X / Twitter",
        "source_author": args.source_author or author_name,
        "base_url": source_url,
    }


def text_to_html(text: str) -> str:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    return "\n".join(f"<p>{html.escape(block).replace(chr(10), '<br>')}</p>" for block in blocks)


def markdown_inline_html(value: str) -> str:
    tokens: dict[str, str] = {}

    def store(markup: str) -> str:
        token = f"KBMDTOKEN{len(tokens)}END"
        tokens[token] = markup
        return token

    def code_repl(match: re.Match[str]) -> str:
        return store(f"<code>{html.escape(match.group(1))}</code>")

    def image_repl(match: re.Match[str]) -> str:
        url = match.group(2).strip()
        if not url:
            return match.group(0)
        return store(
            '<img src="{src}" alt="{alt}" loading="lazy" decoding="async">'.format(
                src=html.escape(url, quote=True),
                alt=html.escape(match.group(1), quote=True),
            )
        )

    def link_repl(match: re.Match[str]) -> str:
        url = match.group(2).strip()
        if not url:
            return match.group(0)
        return store(
            '<a href="{href}" target="_blank" rel="noopener noreferrer">{label}</a>'.format(
                href=html.escape(url, quote=True),
                label=html.escape(match.group(1)),
            )
        )

    value = re.sub(r"`([^`\n]+)`", code_repl, value)
    value = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", image_repl, value)
    value = re.sub(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", link_repl, value)
    escaped = html.escape(value)
    escaped = re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"__([^_\n]+)__", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", escaped)
    escaped = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"<em>\1</em>", escaped)
    for token, markup in tokens.items():
        escaped = escaped.replace(token, markup)
    return escaped


def markdown_paragraph_html(lines: list[str]) -> str:
    clean_lines = [line.strip() for line in lines if line.strip()]
    if not clean_lines:
        return ""
    return "<p>" + "<br>".join(markdown_inline_html(line) for line in clean_lines) + "</p>"


def markdown_to_html(markdown: str) -> str:
    markdown = markdown.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not markdown:
        return ""

    out: list[str] = []
    paragraph: list[str] = []
    list_type = ""
    list_items: list[str] = []
    quote_lines: list[str] = []
    in_code = False
    code_lines: list[str] = []
    code_lang = ""

    def flush_paragraph() -> None:
        nonlocal paragraph
        rendered = markdown_paragraph_html(paragraph)
        if rendered:
            out.append(rendered)
        paragraph = []

    def flush_list() -> None:
        nonlocal list_type, list_items
        if list_type and list_items:
            out.append(f"<{list_type}><li>" + "</li><li>".join(list_items) + f"</li></{list_type}>")
        list_type = ""
        list_items = []

    def flush_quote() -> None:
        nonlocal quote_lines
        rendered = markdown_paragraph_html(quote_lines)
        if rendered:
            out.append(f"<blockquote>{rendered}</blockquote>")
        quote_lines = []

    for line in markdown.split("\n"):
        stripped = line.strip()
        if in_code:
            if re.match(r"^```+\s*$", stripped):
                lang = f' class="language-{html.escape(code_lang, quote=True)}"' if code_lang else ""
                out.append(f"<pre><code{lang}>{html.escape(chr(10).join(code_lines))}</code></pre>")
                in_code = False
                code_lines = []
                code_lang = ""
            else:
                code_lines.append(line)
            continue

        fence = re.match(r"^```+\s*([A-Za-z0-9_-]+)?\s*$", stripped)
        if fence:
            flush_paragraph()
            flush_list()
            flush_quote()
            in_code = True
            code_lang = fence.group(1) or ""
            continue

        if not stripped:
            flush_paragraph()
            flush_list()
            flush_quote()
            continue

        if re.match(r"^[-*_]{3,}$", stripped):
            flush_paragraph()
            flush_list()
            flush_quote()
            out.append("<hr>")
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            flush_list()
            flush_quote()
            level = min(6, len(heading.group(1)))
            out.append(f"<h{level}>{markdown_inline_html(heading.group(2))}</h{level}>")
            continue

        quote = re.match(r"^>\s?(.*)$", stripped)
        if quote:
            flush_paragraph()
            flush_list()
            quote_lines.append(quote.group(1))
            continue

        unordered = re.match(r"^[-*+]\s+(.+)$", stripped)
        if unordered:
            flush_paragraph()
            flush_quote()
            if list_type != "ul":
                flush_list()
                list_type = "ul"
            list_items.append(markdown_inline_html(unordered.group(1)))
            continue

        ordered = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if ordered:
            flush_paragraph()
            flush_quote()
            if list_type != "ol":
                flush_list()
                list_type = "ol"
            list_items.append(markdown_inline_html(ordered.group(1)))
            continue

        flush_list()
        flush_quote()
        paragraph.append(line)

    if in_code:
        lang = f' class="language-{html.escape(code_lang, quote=True)}"' if code_lang else ""
        out.append(f"<pre><code{lang}>{html.escape(chr(10).join(code_lines))}</code></pre>")
    flush_paragraph()
    flush_list()
    flush_quote()
    return "\n\n".join(out)


def is_chatgpt_share_url(url: str) -> bool:
    parsed = parse.urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    share_path = re.match(
        r"^/(?:share/[A-Za-z0-9_-]+|s/t_[A-Za-z0-9_-]+)(?:/|$)",
        parsed.path,
    )
    return host in {"chatgpt.com", "chat.openai.com"} and bool(share_path)


def fetch_chatgpt_share_page(url: str, allow_private: bool = False):
    ok, reason = check_fetch_url(url, allow_private)
    if not ok:
        raise ValueError(f"Refusing to fetch {url}: {reason}")

    cookies = cookiejar.CookieJar()
    opener = request.build_opener(request.HTTPCookieProcessor(cookies))
    req = request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Encoding": "identity",
        },
    )
    with opener.open(req, timeout=30) as resp:
        content_type = resp.headers.get_content_type()
        if content_type not in {"text/html", "application/xhtml+xml"}:
            raise ValueError(f"ChatGPT share URL returned unsupported content type: {content_type}")
        data = read_limited(resp, MAX_HTML_BYTES)
        charset = resp.headers.get_content_charset() or html_charset(data) or "utf-8"
        return data.decode(charset, "replace"), resp.geturl(), opener


def decode_chatgpt_flattened(values: list):
    if not values:
        raise ValueError("ChatGPT share payload is empty")

    memo: dict[int, object] = {}

    def resolve(index: int):
        if index < 0:
            return None
        if index >= len(values):
            raise ValueError("ChatGPT share payload contains an invalid reference")
        if index in memo:
            return memo[index]

        raw = values[index]
        if isinstance(raw, dict):
            decoded: dict[str, object] = {}
            memo[index] = decoded
            for raw_key, raw_value in raw.items():
                key_match = re.fullmatch(r"_(\d+)", raw_key)
                key = resolve(int(key_match.group(1))) if key_match else raw_key
                if not isinstance(key, (str, int, float, bool)):
                    continue
                decoded[str(key)] = (
                    resolve(raw_value)
                    if isinstance(raw_value, int) and not isinstance(raw_value, bool)
                    else raw_value
                )
            return decoded

        if isinstance(raw, list):
            decoded_list: list[object] = []
            memo[index] = decoded_list
            decoded_list.extend(
                resolve(item) if isinstance(item, int) and not isinstance(item, bool) else item
                for item in raw
            )
            return decoded_list

        memo[index] = raw
        return raw

    return resolve(0)


def chatgpt_post_conversation(post: dict) -> dict | None:
    attachments = post.get("attachments")
    if not isinstance(attachments, list):
        return None

    messages: list[dict] = []
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        attachment_messages = attachment.get("messages")
        if not isinstance(attachment_messages, list):
            continue
        messages.extend(message for message in attachment_messages if isinstance(message, dict))

    if not messages:
        return None

    return {
        "title": clean_text(str(post.get("text") or post.get("og_title") or "")),
        "linear_conversation": [{"message": message} for message in messages],
        "shared_conversation_id": str(post.get("id") or ""),
    }


def chatgpt_share_conversation(source: str) -> dict:
    parser = ScriptTextParser()
    parser.feed(source)
    chunks: list[str] = []
    enqueue_pattern = re.compile(
        r"window\.__reactRouterContext\.streamController\.enqueue\((.*)\);",
        re.S,
    )
    for script in parser.scripts:
        match = enqueue_pattern.fullmatch(script.strip())
        if not match:
            continue
        try:
            chunk = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(chunk, str):
            chunks.append(chunk)

    for line in "".join(chunks).splitlines():
        if not line.lstrip().startswith("["):
            continue
        try:
            flattened = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(flattened, list):
            continue
        root = decode_chatgpt_flattened(flattened)
        stack = [root]
        visited: set[int] = set()
        while stack:
            item = stack.pop()
            if isinstance(item, (dict, list)):
                item_id = id(item)
                if item_id in visited:
                    continue
                visited.add(item_id)
            if isinstance(item, dict):
                if isinstance(item.get("mapping"), dict) and (
                    isinstance(item.get("linear_conversation"), list) or item.get("current_node")
                ):
                    return item
                post_conversation = chatgpt_post_conversation(item)
                if post_conversation:
                    return post_conversation
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)

    raise ValueError("ChatGPT share page does not contain a readable conversation")


def chatgpt_conversation_nodes(conversation: dict) -> list[dict]:
    linear = conversation.get("linear_conversation")
    if isinstance(linear, list):
        return [item for item in linear if isinstance(item, dict)]

    mapping = conversation.get("mapping")
    current = conversation.get("current_node")
    if not isinstance(mapping, dict) or not isinstance(current, str):
        return []

    nodes: list[dict] = []
    visited: set[str] = set()
    while current and current not in visited:
        visited.add(current)
        node = mapping.get(current)
        if not isinstance(node, dict):
            break
        nodes.append(node)
        parent = node.get("parent")
        current = parent if isinstance(parent, str) else ""
    nodes.reverse()
    return nodes


def chatgpt_message_parts(content: dict) -> tuple[str, list[str]]:
    text_parts: list[str] = []
    image_pointers: list[str] = []
    parts = content.get("parts")
    if not isinstance(parts, list):
        parts = []

    for part in parts:
        if isinstance(part, str):
            if part.strip():
                text_parts.append(part.strip())
            continue
        if not isinstance(part, dict):
            continue

        content_type = str(part.get("content_type") or "")
        if content_type in {"image_asset_pointer", "image_url"}:
            pointer = part.get("asset_pointer") or part.get("image_url") or part.get("url")
            if isinstance(pointer, str) and pointer.strip():
                image_pointers.append(pointer.strip())
            continue
        for key in ("text", "content"):
            value = part.get(key)
            if isinstance(value, str) and value.strip():
                text_parts.append(value.strip())
                break

    if not text_parts:
        text = content.get("text")
        if isinstance(text, str) and text.strip():
            text_parts.append(text.strip())
    return "\n\n".join(text_parts), list(dict.fromkeys(image_pointers))


def chatgpt_conversation_to_html(conversation: dict, resolve_image) -> tuple[str, str]:
    body_parts: list[str] = []
    plain_text_parts: list[str] = []

    for node in chatgpt_conversation_nodes(conversation):
        message = node.get("message") if isinstance(node.get("message"), dict) else node
        author = message.get("author") if isinstance(message.get("author"), dict) else {}
        role = str(author.get("role") or "")
        if role not in {"user", "assistant"}:
            continue

        content = message.get("content") if isinstance(message.get("content"), dict) else {}
        content_type = str(content.get("content_type") or "")
        recipient = str(message.get("recipient") or "")
        channel = str(message.get("channel") or "")
        if role == "assistant" and (recipient not in {"", "all"} or channel not in {"", "final"}):
            continue
        if content_type in {"code", "thoughts", "reasoning_recap", "model_editable_context", "execution_output"}:
            continue
        text, image_pointers = chatgpt_message_parts(content)
        image_urls: list[str] = []
        for pointer in image_pointers:
            try:
                image_url = resolve_image(pointer)
            except (OSError, ValueError, error.URLError, error.HTTPError, json.JSONDecodeError):
                image_url = ""
            if image_url:
                image_urls.append(image_url)

        if not text and not image_pointers:
            continue
        if body_parts:
            body_parts.append("<hr>")
        body_parts.append("<h2>提问</h2>" if role == "user" else "<h2>ChatGPT 回答</h2>")
        if text:
            body_parts.append(markdown_to_html(text) or text_to_html(text))
            plain_text_parts.append(text)
        for index, image_url in enumerate(image_urls, start=1):
            safe_url = html.escape(image_url, quote=True)
            body_parts.append(
                '<figure><img src="{url}" alt="ChatGPT 分享附件 {index}" loading="lazy" decoding="async">'
                '<figcaption>分享中的图片附件</figcaption></figure>'.format(url=safe_url, index=index)
            )
        if image_pointers and not image_urls:
            body_parts.append("<p><em>图片附件暂时无法读取，请打开原始分享链接查看。</em></p>")

    return "\n\n".join(body_parts), "\n\n".join(plain_text_parts)


def chatgpt_share_id(url: str) -> str:
    match = re.match(
        r"^/(?:share/([A-Za-z0-9_-]+)|s/(t_[A-Za-z0-9_-]+))(?:/|$)",
        parse.urlparse(url).path,
    )
    return next((group for group in match.groups() if group), "") if match else ""


def chatgpt_asset_download_url(asset_pointer: str, share_url: str, opener) -> str:
    parsed = parse.urlparse(asset_pointer)
    if parsed.scheme in {"http", "https"}:
        ok, _ = check_fetch_url(asset_pointer)
        return asset_pointer if ok else ""
    if parsed.scheme != "sediment":
        return ""

    file_id = parsed.netloc or parsed.path.lstrip("/")
    if not re.fullmatch(r"file_[A-Za-z0-9_-]{8,}", file_id):
        return ""
    query = parse.parse_qs(parsed.query)
    shared_id = (query.get("shared_conversation_id") or [chatgpt_share_id(share_url)])[0]
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,}", shared_id or ""):
        return ""

    endpoint = "https://chatgpt.com/backend-api/files/download/" + parse.quote(file_id, safe="")
    endpoint += "?" + parse.urlencode({"shared_conversation_id": shared_id, "inline": "true"})
    req = request.Request(
        endpoint,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "Referer": share_url,
        },
    )
    with opener.open(req, timeout=30) as resp:
        data = read_limited(resp, 1024 * 1024)
        payload = json.loads(data.decode(resp.headers.get_content_charset() or "utf-8", "replace"))
    download_url = str(payload.get("download_url") or "") if isinstance(payload, dict) else ""
    ok, _ = check_fetch_url(download_url)
    return download_url if ok else ""


def content_from_chatgpt_share(url: str, args: argparse.Namespace) -> dict:
    source, final_url, opener = fetch_chatgpt_share_page(url, args.allow_private_url)
    conversation = chatgpt_share_conversation(source)
    image_cache: dict[str, str] = {}

    def resolve_image(pointer: str) -> str:
        if pointer not in image_cache:
            image_cache[pointer] = chatgpt_asset_download_url(pointer, final_url, opener)
        return image_cache[pointer]

    body, plain_text = chatgpt_conversation_to_html(conversation, resolve_image)
    if not body:
        raise ValueError("ChatGPT share page contains no visible user or assistant messages")

    meta = parse_metadata(source)
    remote_title = clean_text(str(conversation.get("title") or ""))
    if not remote_title:
        remote_title = re.sub(r"^ChatGPT\s*-\s*", "", meta.title(), flags=re.I)
    return {
        "title": args.title or remote_title or "ChatGPT 分享对话",
        "content": body,
        "excerpt": args.excerpt or summarize(plain_text),
        "source_url": args.source_url or final_url,
        "source_site": args.source_site or "ChatGPT",
        "source_author": args.source_author or "ChatGPT",
        "base_url": final_url,
    }


def read_local_content(path: Path, force_html: bool = False) -> str:
    text = path.read_text()
    if force_html or re.search(r"</?[a-z][\s>/]", text, re.I):
        return text
    return text_to_html(text)


def collect_image_refs(markup: str, base_url: str | None = None) -> list[dict[str, str]]:
    parser = ImageRefParser(base_url)
    parser.feed(markup)
    unique: list[dict[str, str]] = []
    seen: set[str] = set()
    for ref in parser.refs:
        key = ref["absolute"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(ref)
    return unique


def image_plan(refs: list[dict[str, str]], max_images: int, allow_private: bool) -> list[dict[str, str]]:
    planned: list[dict[str, str]] = []
    upload_count = 0
    for ref in refs:
        absolute = ref["absolute"]
        if absolute.startswith("data:"):
            planned.append({**ref, "action": "skip", "reason": "data URI"})
            continue
        ok, reason = check_fetch_url(absolute, allow_private)
        if not ok:
            planned.append({**ref, "action": "skip", "reason": reason})
            continue
        if upload_count >= max_images:
            planned.append({**ref, "action": "skip", "reason": f"over max media count {max_images}"})
            continue
        upload_count += 1
        planned.append({**ref, "action": "upload", "reason": "will validate MIME and size during upload"})
    return planned


def filename_for_media(url: str, mime: str, data: bytes) -> str:
    path_name = Path(parse.unquote(parse.urlparse(url).path)).name
    if not path_name or "." not in path_name:
        ext = mimetypes.guess_extension(mime) or ".bin"
        path_name = "media" + ext
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", path_name).strip("-._") or "media"
    digest = hashlib.sha256(url.encode("utf-8") + data[:4096]).hexdigest()[:10]
    if len(stem) > 80:
        stem = stem[-80:]
    return f"kb-{digest}-{stem}"


def replace_image_ref(markup: str, ref: dict[str, str], new_url: str) -> str:
    replacements = [
        (ref["raw"], new_url),
        (ref["absolute"], new_url),
        (html.escape(ref["raw"], quote=True), html.escape(new_url, quote=True)),
        (html.escape(ref["absolute"], quote=True), html.escape(new_url, quote=True)),
    ]
    for old, new in replacements:
        if old:
            markup = markup.replace(old, new)
    return markup


def video_fallback_html(video_url: str, video_html: str, rest_html: str) -> str:
    safe_video_url = html.escape(video_url, quote=True)
    poster_match = re.search(r'\bposter="([^"]+)"', video_html)
    poster = poster_match.group(1) if poster_match else ""
    open_link = (
        f'<a href="{safe_video_url}" target="_blank" rel="noopener noreferrer">'
        "打开原视频"
        "</a>"
    )

    poster_html = ""
    if poster:
        poster_html = (
            f'<a href="{safe_video_url}" target="_blank" rel="noopener noreferrer">'
            f'<img src="{html.escape(poster, quote=True)}" alt="视频封面">'
            "</a>"
        )

    if "<figcaption" in rest_html:
        caption_html = re.sub(r"</figcaption>", f" · {open_link}</figcaption>", rest_html, count=1)
    else:
        caption_html = f"<figcaption>{open_link}</figcaption>"

    if poster_html:
        return f"<figure>{poster_html}{caption_html}</figure>"
    return f"<p>{open_link}</p>"


def replace_unuploaded_videos(markup: str, report: list[dict[str, str]]) -> str:
    for ref in report:
        if ref.get("kind") != "video" or ref.get("status") == "uploaded":
            continue

        for target in {ref.get("raw", ""), ref.get("absolute", ""), html.escape(ref.get("raw", ""), quote=True), html.escape(ref.get("absolute", ""), quote=True)}:
            if not target or target not in markup:
                continue

            quoted = re.escape(target)
            figure_pattern = re.compile(
                rf"<figure>\s*(?P<video><video\b[^>]*\bsrc=\"{quoted}\"[^>]*>.*?</video>)(?P<rest>.*?)</figure>",
                re.S,
            )
            markup = figure_pattern.sub(
                lambda match: video_fallback_html(ref["absolute"], match.group("video"), match.group("rest")),
                markup,
            )

            bare_pattern = re.compile(rf"<video\b[^>]*\bsrc=\"{quoted}\"[^>]*>.*?</video>", re.S)
            markup = bare_pattern.sub(
                lambda match: video_fallback_html(ref["absolute"], match.group(0), ""),
                markup,
            )
    return markup


def copy_remote_images(markup: str, refs: list[dict[str, str]], base_url: str, auth: str, args: argparse.Namespace) -> tuple[str, list[dict[str, str]]]:
    report: list[dict[str, str]] = []
    uploaded = 0
    for ref in refs:
        absolute = ref["absolute"]
        if args.no_copy_images:
            report.append({**ref, "status": "skipped", "reason": "--no-copy-images"})
            continue
        if absolute.startswith("data:"):
            report.append({**ref, "status": "skipped", "reason": "data URI"})
            continue
        ok, reason = check_fetch_url(absolute, args.allow_private_images)
        if not ok:
            report.append({**ref, "status": "skipped", "reason": reason})
            continue
        if uploaded >= args.max_images:
            report.append({**ref, "status": "skipped", "reason": f"over max media count {args.max_images}"})
            continue
        try:
            data, mime = fetch_remote_media(
                absolute,
                args.max_image_bytes,
                args.max_video_bytes,
                args.allow_private_images,
            )
            filename = filename_for_media(absolute, mime, data)
            media = upload_media_bytes(base_url, auth, filename, mime, data)
            source_url = media.get("source_url")
            if not source_url:
                raise ValueError("WordPress media response has no source_url")
            markup = replace_image_ref(markup, ref, source_url)
            uploaded += 1
            report.append({**ref, "status": "uploaded", "media_id": str(media["id"]), "media_url": source_url})
        except (OSError, ValueError, error.URLError, error.HTTPError) as exc:
            report.append({**ref, "status": "skipped", "reason": str(exc)})
    markup = replace_unuploaded_videos(markup, report)
    return markup, report


def kb_content(args: argparse.Namespace, body: str) -> str:
    if args.site != "kb":
        return body

    pieces = []
    if args.source_url:
        url = html.escape(args.source_url, quote=True)
        pieces.append(f'<p><strong>原文链接：</strong><a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a></p>')
    pieces.append(body)
    if args.private_archive_file:
        archive = Path(args.private_archive_file).read_text()
        pieces.append("[private_archive]\n" + archive + "\n[/private_archive]")
    return "\n\n".join(pieces)


def content_from_url(url: str, args: argparse.Namespace) -> dict:
    if is_chatgpt_share_url(url):
        return content_from_chatgpt_share(url, args)

    if is_medisearch_share_url(url):
        return content_from_medisearch(url, args)

    if is_x_status_url(url):
        try:
            return content_from_x_api(url, args)
        except (OSError, ValueError, error.URLError, error.HTTPError, json.JSONDecodeError):
            pass
        try:
            return content_from_x_stream(url, args)
        except (OSError, ValueError, error.URLError, error.HTTPError, json.JSONDecodeError):
            pass
        try:
            return content_from_x_page(url, args)
        except (OSError, ValueError, error.URLError, error.HTTPError, json.JSONDecodeError):
            pass
        try:
            return content_from_x_oembed(url, args)
        except (OSError, ValueError, error.URLError, error.HTTPError, json.JSONDecodeError):
            pass

    source, final_url = fetch_html(url, args.allow_private_url)
    meta = parse_metadata(source)
    root = build_tree(source)
    content_node = select_content_node(root)
    body = collapse_empty_blocks(serialize_node(content_node, final_url))
    if not body:
        body = text_to_html(node_text(content_node))
    text = clean_text(node_text(content_node))
    title = args.title or meta_first(meta, ["og:title", "twitter:title"]) or meta.title() or final_url
    excerpt = args.excerpt or meta_first(meta, ["og:description", "twitter:description", "description"]) or summarize(text)
    source_site = args.source_site or meta_first(meta, ["og:site_name", "application-name"]) or site_from_url(final_url)
    source_author = args.source_author or meta_first(
        meta,
        ["article:author", "author", "parsely-author", "byl", "byline", "dc.creator"],
    )
    return {
        "title": title,
        "content": body,
        "excerpt": excerpt,
        "source_url": args.source_url or final_url,
        "source_site": source_site,
        "source_author": source_author,
        "base_url": final_url,
    }


def content_from_file(args: argparse.Namespace) -> dict:
    path = Path(args.html_file or args.content_file)
    markdown_source = ""
    if args.content_file and path.suffix.lower() in {".md", ".markdown", ".mdown"}:
        markdown_source = path.read_text()
        body = markdown_to_html(markdown_source)
    else:
        body = read_local_content(path, force_html=bool(args.html_file))
    text = clean_text(re.sub(r"<[^>]+>", " ", body))
    source_url = args.source_url or ""
    if not args.title:
        raise ValueError("--title is required when importing from a local file")
    result = {
        "title": args.title,
        "content": body,
        "excerpt": args.excerpt or summarize(text),
        "source_url": source_url,
        "source_site": args.source_site or (site_from_url(source_url) if source_url else ""),
        "source_author": args.source_author or "",
        "base_url": source_url or None,
    }
    if markdown_source != "":
        result["markdown_source"] = markdown_source
    return result


def build_payload(args: argparse.Namespace, imported: dict) -> dict:
    args.source_url = imported["source_url"]
    body = kb_content(args, imported["content"])
    payload: dict = {
        "title": imported["title"],
        "content": body,
        "status": args.status,
    }
    if imported.get("excerpt"):
        payload["excerpt"] = imported["excerpt"]

    source_meta = {
        "source_url": imported.get("source_url") or "",
        "source_site": imported.get("source_site") or "",
        "source_author": imported.get("source_author") or "",
    }
    if "markdown_source" in imported:
        source_meta["home_kb_markdown_source"] = imported.get("markdown_source") or ""
    if not args.post_id or any(source_meta.values()):
        payload["meta"] = source_meta
    return payload


def parser_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a URL or local note into the personal knowledge base.")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--base-url")
    parser.add_argument("--site", choices=["kb", "family"], default="kb")
    parser.add_argument("--post-id", type=int, help="Update an existing post instead of creating a new one.")

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="Fetch and import a static HTML web page.")
    source.add_argument("--content-file", help="Import a local text or HTML note.")
    source.add_argument("--html-file", help="Import a local HTML file without plain-text conversion.")

    parser.add_argument("--title")
    parser.add_argument("--excerpt")
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--media", action="append", default=[], help="Upload a local media file and attach it to the post.")
    parser.add_argument("--featured-media", help="Upload a local image and set it as featured media.")
    parser.add_argument("--source-url")
    parser.add_argument("--source-site")
    parser.add_argument("--source-author")
    parser.add_argument("--private-archive-file")
    parser.add_argument("--status", default="draft", choices=["draft", "private", "publish"])
    parser.add_argument("--max-images", type=int, default=DEFAULT_MAX_IMAGES)
    parser.add_argument("--max-image-bytes", type=int, default=DEFAULT_MAX_IMAGE_BYTES)
    parser.add_argument("--max-video-bytes", type=int, default=DEFAULT_MAX_VIDEO_BYTES)
    parser.add_argument("--no-copy-images", action="store_true", help="Do not copy remote images into WordPress media.")
    parser.add_argument("--allow-private-url", action="store_true", help="Allow fetching private/local page URLs for local testing.")
    parser.add_argument("--allow-private-images", action="store_true", help="Allow copying private/local image URLs for local testing.")
    parser.add_argument("--dry-run", action="store_true", help="Show the payload without calling WordPress.")
    return parser.parse_args()


def main() -> int:
    args = parser_args()
    load_env(Path(args.env_file))
    base_url, user, password = site_config(args.site, args.base_url)

    try:
        imported = content_from_url(args.url, args) if args.url else content_from_file(args)
    except (OSError, ValueError, error.URLError, error.HTTPError) as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        return 2

    image_refs = collect_image_refs(imported["content"], imported.get("base_url"))
    payload = build_payload(args, imported)

    if args.dry_run:
        preview = {
            "target": base_url,
            "method": "update" if args.post_id else "create",
            "post_id": args.post_id,
            "categories": args.category,
            "tags": args.tag,
            "media": args.media,
            "featured_media": args.featured_media,
            "image_plan": image_plan(image_refs, args.max_images, args.allow_private_images)
            if not args.no_copy_images
            else [{**ref, "action": "skip", "reason": "--no-copy-images"} for ref in image_refs],
            "payload": payload,
        }
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return 0

    if not user or not password or password.startswith("CHANGE_ME"):
        print("Missing WordPress application password in .env", file=sys.stderr)
        return 2
    auth = auth_header(user, password)

    content, image_report = copy_remote_images(payload["content"], image_refs, base_url, auth, args)
    payload["content"] = content

    category_ids = [ensure_term(base_url, auth, "categories", name) for name in args.category]
    tag_ids = [ensure_term(base_url, auth, "tags", name) for name in args.tag]
    if category_ids or not args.post_id:
        payload["categories"] = category_ids
    if tag_ids or not args.post_id:
        payload["tags"] = tag_ids

    media_ids = [int(upload_media_file(base_url, auth, Path(path))["id"]) for path in args.media]
    featured_id = None
    if args.featured_media:
        featured_id = int(upload_media_file(base_url, auth, Path(args.featured_media))["id"])
    elif media_ids:
        featured_id = media_ids[0]
    if featured_id:
        payload["featured_media"] = featured_id

    path = f"/wp-json/wp/v2/posts/{args.post_id}" if args.post_id else "/wp-json/wp/v2/posts"
    post = api_call(base_url, auth, "POST", path, payload)
    print(json.dumps({
        "id": post["id"],
        "link": post.get("link"),
        "edit": base_url.rstrip("/") + f"/wp-admin/post.php?post={post['id']}&action=edit",
        "status": post.get("status"),
        "copied_images": image_report,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
