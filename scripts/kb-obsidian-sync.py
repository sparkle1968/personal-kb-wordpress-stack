#!/usr/bin/env python3
"""Sync WordPress KB posts into an Obsidian vault as Markdown files."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
from typing import Any
from urllib import error, parse, request


DEFAULT_TARGET_DIR = "个人知识库"
DEFAULT_STATUSES = "publish,draft,private"
INDEX_VERSION = 1
USER_AGENT = "HomeKnowledgeBaseObsidianSync/1.0"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


def site_config(base_url: str | None = None) -> tuple[str, str, str]:
    url = base_url or os.environ.get("KB_LOCAL_URL") or os.environ.get("KB_PUBLIC_URL")
    if not url:
        url = "https://" + os.environ.get("DOMAIN_KB", "kb.example.com")
    return url, os.environ.get("WP_KB_API_USER", ""), os.environ.get("WP_KB_APP_PASSWORD", "")


def auth_header(user: str, password: str) -> str:
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def api_call(base_url: str, auth: str, method: str, path: str) -> Any:
    req = request.Request(
        base_url.rstrip("/") + path,
        headers={
            "Authorization": auth,
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        method=method,
    )
    with request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_get_all(base_url: str, auth: str, endpoint: str, params: dict[str, str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        query = {**params, "per_page": "100", "page": str(page)}
        path = endpoint + "?" + parse.urlencode(query)
        try:
            batch = api_call(base_url, auth, "GET", path)
        except error.HTTPError as exc:
            if exc.code == 400 and page > 1:
                return items
            raise
        if not isinstance(batch, list):
            raise RuntimeError(f"Unexpected WordPress response for {endpoint}: {type(batch).__name__}")
        items.extend(item for item in batch if isinstance(item, dict))
        if len(batch) < 100:
            return items
        page += 1


def fetch_terms(base_url: str, auth: str, taxonomy: str) -> dict[int, str]:
    terms = api_get_all(
        base_url,
        auth,
        f"/wp-json/wp/v2/{taxonomy}",
        {
            "hide_empty": "false",
            "orderby": "name",
            "order": "asc",
            "_fields": "id,name",
        },
    )
    return {int(term["id"]): clean_text(str(term.get("name") or "")) for term in terms if term.get("id")}


def fetch_posts(base_url: str, auth: str, statuses: list[str]) -> list[dict[str, Any]]:
    fields = ",".join([
        "id",
        "slug",
        "status",
        "date",
        "modified",
        "link",
        "title",
        "content",
        "categories",
        "tags",
        "meta",
    ])
    return api_get_all(
        base_url,
        auth,
        "/wp-json/wp/v2/posts",
        {
            "context": "edit",
            "status": ",".join(statuses),
            "orderby": "modified",
            "order": "asc",
            "_fields": fields,
        },
    )


def fetch_sync_settings(base_url: str, auth: str) -> dict[str, Any]:
    try:
        data = api_call(base_url, auth, "GET", "/wp-json/home-kb/v1/obsidian-sync-settings")
    except error.HTTPError as exc:
        if exc.code == 404:
            return {}
        raise
    if not isinstance(data, dict):
        return {}
    return data


def sync_wait_seconds(settings: dict[str, Any], fallback: int = 3600) -> int:
    mode = str(settings.get("mode") or "schedule")
    if mode == "realtime":
        try:
            return min(300, max(15, int(settings.get("realtime_seconds") or 30)))
        except (TypeError, ValueError):
            return 30

    try:
        return min(1440, max(5, int(settings.get("interval_minutes") or 60))) * 60
    except (TypeError, ValueError):
        return fallback


class HtmlNode:
    def __init__(self, tag: str, attrs: list[tuple[str, str | None]] | None = None, parent: "HtmlNode | None" = None):
        self.tag = tag
        self.attrs = attrs or []
        self.parent = parent
        self.children: list[HtmlNode | str] = []


class MarkdownTreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = HtmlNode("document")
        self.current = self.root

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        node = HtmlNode(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}:
            self.current = node

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.current.children.append(HtmlNode(tag.lower(), attrs, self.current))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        cursor: HtmlNode | None = self.current
        while cursor and cursor is not self.root:
            if cursor.tag == tag:
                self.current = cursor.parent or self.root
                return
            cursor = cursor.parent

    def handle_data(self, data: str) -> None:
        if data:
            self.current.children.append(data)


def attrs(node: HtmlNode) -> dict[str, str]:
    return {key.lower(): value or "" for key, value in node.attrs}


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def node_text(node: HtmlNode | str) -> str:
    if isinstance(node, str):
        return html.unescape(node)
    return "".join(node_text(child) for child in node.children)


def escape_markdown_inline(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def render_inline_children(node: HtmlNode) -> str:
    text = "".join(render_node(child, inline=True) for child in node.children)
    return clean_text(text)


def render_block_children(node: HtmlNode) -> str:
    return "".join(render_node(child, inline=False) for child in node.children)


def render_list(node: HtmlNode, ordered: bool) -> str:
    lines: list[str] = []
    index = 1
    for child in node.children:
        if not isinstance(child, HtmlNode) or child.tag != "li":
            continue
        marker = f"{index}. " if ordered else "- "
        content = render_block_children(child).strip()
        if not content:
            content = clean_text(node_text(child))
        item_lines = content.splitlines() or [""]
        lines.append(marker + item_lines[0])
        for extra in item_lines[1:]:
            lines.append(("   " if ordered else "  ") + extra)
        index += 1
    return "\n".join(lines).rstrip() + "\n\n" if lines else ""


def render_table(node: HtmlNode) -> str:
    rows: list[list[str]] = []
    for row in find_child_nodes(node, {"tr"}):
        cells = [clean_text(node_text(cell)) for cell in row.children if isinstance(cell, HtmlNode) and cell.tag in {"td", "th"}]
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    output = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
    for row in rows[1:]:
        output.append("| " + " | ".join(row) + " |")
    return "\n".join(output) + "\n\n"


def find_child_nodes(node: HtmlNode, tags: set[str]) -> list[HtmlNode]:
    found: list[HtmlNode] = []
    for child in node.children:
        if not isinstance(child, HtmlNode):
            continue
        if child.tag in tags:
            found.append(child)
        found.extend(find_child_nodes(child, tags))
    return found


def render_video(node: HtmlNode) -> str:
    attr = attrs(node)
    src = attr.get("src", "")
    if not src:
        for child in node.children:
            if isinstance(child, HtmlNode) and child.tag == "source":
                src = attrs(child).get("src", "")
                break
    if not src:
        return ""
    return f'<video controls src="{html.escape(src, quote=True)}"></video>\n\n'


def render_node(node: HtmlNode | str, inline: bool = False) -> str:
    if isinstance(node, str):
        return clean_text(node) if inline else html.unescape(node)

    tag = node.tag
    if tag in {"script", "style", "noscript", "svg", "iframe", "form"}:
        return ""
    if tag in {"document", "body", "article", "main", "div", "section", "figure", "figcaption"}:
        return render_block_children(node)
    if tag == "p":
        content = render_inline_children(node)
        return f"{content}\n\n" if content else ""
    if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        level = int(tag[1])
        content = render_inline_children(node)
        return f"{'#' * level} {content}\n\n" if content else ""
    if tag == "br":
        return "\n"
    if tag == "hr":
        return "---\n\n"
    if tag in {"strong", "b"}:
        content = render_inline_children(node)
        return f"**{content}**" if content else ""
    if tag in {"em", "i"}:
        content = render_inline_children(node)
        return f"*{content}*" if content else ""
    if tag == "code":
        content = node_text(node).strip()
        if not content:
            return ""
        fence = "`" if "`" not in content else "``"
        return f"{fence}{content}{fence}"
    if tag == "pre":
        content = html.unescape(node_text(node)).strip("\n")
        return f"```\n{content}\n```\n\n" if content else ""
    if tag == "a":
        attr = attrs(node)
        href = attr.get("href", "").strip()
        label = render_inline_children(node) or href
        if not href:
            return label
        return f"[{escape_markdown_inline(label)}]({href})"
    if tag == "img":
        attr = attrs(node)
        src = attr.get("src", "").strip()
        if not src:
            return ""
        alt = attr.get("alt", "").strip()
        return f"![{escape_markdown_inline(alt)}]({src})\n\n"
    if tag == "video":
        return render_video(node)
    if tag == "blockquote":
        content = render_block_children(node).strip()
        if not content:
            return ""
        quoted = "\n".join("> " + line if line else ">" for line in content.splitlines())
        return quoted + "\n\n"
    if tag == "ul":
        return render_list(node, ordered=False)
    if tag == "ol":
        return render_list(node, ordered=True)
    if tag == "li":
        return render_block_children(node)
    if tag == "table":
        return render_table(node)
    if inline:
        return render_inline_children(node)
    return render_block_children(node)


def html_to_markdown(source: str) -> str:
    parser = MarkdownTreeBuilder()
    parser.feed(source or "")
    markdown = render_block_children(parser.root)
    markdown = re.sub(r"[ \t]+\n", "\n", markdown)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    return markdown.strip()


def strip_html(value: str) -> str:
    parser = MarkdownTreeBuilder()
    parser.feed(value or "")
    return clean_text(node_text(parser.root))


def yaml_scalar(value: Any) -> str:
    if value is None:
        value = ""
    return json.dumps(str(value), ensure_ascii=False)


def yaml_list(values: list[str]) -> list[str]:
    if not values:
        return ["  []"]
    return [f"  - {yaml_scalar(value)}" for value in values]


def obsidian_tag(value: str) -> str:
    tag = clean_text(value).lstrip("#")
    tag = re.sub(r"\s+", "-", tag)
    tag = re.sub(r"[^\w/-]+", "-", tag, flags=re.UNICODE)
    tag = re.sub(r"-+", "-", tag).strip("-_/")
    if not tag:
        return ""
    if tag.isdigit():
        return f"tag-{tag}"
    return tag


def obsidian_tags(values: list[str]) -> list[str]:
    tags: list[str] = []
    for value in values:
        tag = obsidian_tag(value)
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def frontmatter(post: dict[str, Any], title: str, categories: list[str], tags: list[str], source_meta: dict[str, str]) -> str:
    lines = [
        "---",
        f"wp_id: {int(post['id'])}",
        f"wp_slug: {yaml_scalar(post.get('slug') or '')}",
        f"wp_status: {yaml_scalar(post.get('status') or '')}",
        f"title: {yaml_scalar(title)}",
        f"date: {yaml_scalar(post.get('date') or '')}",
        f"modified: {yaml_scalar(post.get('modified') or '')}",
        f"link: {yaml_scalar(post.get('link') or '')}",
        "categories:",
        *yaml_list(categories),
        "tags:",
        *yaml_list(obsidian_tags(tags)),
        "wp_tags_original:",
        *yaml_list(tags),
        f"source_url: {yaml_scalar(source_meta.get('source_url') or '')}",
        f"source_site: {yaml_scalar(source_meta.get('source_site') or '')}",
        f"source_author: {yaml_scalar(source_meta.get('source_author') or '')}",
        "---",
    ]
    return "\n".join(lines)


def post_title(post: dict[str, Any]) -> str:
    title = post.get("title") or {}
    if isinstance(title, dict):
        return strip_html(str(title.get("rendered") or title.get("raw") or "")) or f"post-{post.get('id')}"
    return strip_html(str(title)) or f"post-{post.get('id')}"


def post_content(post: dict[str, Any]) -> str:
    content = post.get("content") or {}
    if isinstance(content, dict):
        return str(content.get("rendered") or content.get("raw") or "")
    return str(content or "")


def source_meta(post: dict[str, Any]) -> dict[str, str]:
    meta = post.get("meta") if isinstance(post.get("meta"), dict) else {}
    return {
        "source_url": scalar_meta(meta.get("source_url")),
        "source_site": scalar_meta(meta.get("source_site")),
        "source_author": scalar_meta(meta.get("source_author")),
    }


def scalar_meta(value: Any) -> str:
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value or "")


def names_from_ids(ids: Any, mapping: dict[int, str]) -> list[str]:
    names: list[str] = []
    if not isinstance(ids, list):
        return names
    for raw in ids:
        try:
            name = mapping.get(int(raw), "")
        except (TypeError, ValueError):
            name = ""
        if name and name not in names:
            names.append(name)
    return names


def sanitize_component(value: str, fallback: str = "未分类", limit: int = 80) -> str:
    value = clean_text(value)
    value = re.sub(r'[\\/:*?"<>|]+', "-", value)
    value = re.sub(r"[\x00-\x1f]+", "", value)
    value = re.sub(r"\s+", " ", value).strip(" .-_")
    if not value:
        value = fallback
    if len(value) > limit:
        value = value[:limit].rstrip(" .-_")
    return value or fallback


def post_relative_path(post: dict[str, Any], title: str, categories: list[str]) -> Path:
    category = sanitize_component(categories[0] if categories else "未分类")
    filename_title = sanitize_component(title, fallback=str(post.get("slug") or post.get("id") or "post"))
    return Path(category) / f"{int(post['id'])}-{filename_title}.md"


def markdown_for_post(post: dict[str, Any], category_map: dict[int, str], tag_map: dict[int, str]) -> tuple[Path, str]:
    title = post_title(post)
    categories = names_from_ids(post.get("categories"), category_map)
    tags = names_from_ids(post.get("tags"), tag_map)
    meta = source_meta(post)
    body = html_to_markdown(post_content(post))
    if not body:
        excerpt = post.get("excerpt") or {}
        body = strip_html(str(excerpt.get("rendered") if isinstance(excerpt, dict) else excerpt))
    rel_path = post_relative_path(post, title, categories)
    content = frontmatter(post, title, categories, tags, meta) + "\n\n" + body.strip() + "\n"
    return rel_path, content


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_index(root: Path) -> dict[str, Any]:
    path = root / "_sync" / "index.json"
    if not path.exists():
        return {"version": INDEX_VERSION, "posts": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": INDEX_VERSION, "posts": {}}
    if not isinstance(data, dict):
        return {"version": INDEX_VERSION, "posts": {}}
    posts = data.get("posts")
    if not isinstance(posts, dict):
        data["posts"] = {}
    return data


def unique_destination(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Cannot find unique path for {path}")


def move_to(root: Path, source: Path, folder: str, wp_id: str, dry_run: bool) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = unique_destination(root / folder / f"{stamp}-{wp_id}-{source.name}")
    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
    return target


def remove_empty_parents(root: Path, path: Path) -> None:
    while path != root and root in path.parents:
        try:
            path.rmdir()
        except OSError:
            return
        path = path.parent


def action(kind: str, wp_id: str, **details: Any) -> dict[str, Any]:
    return {"action": kind, "wp_id": wp_id, **details}


def sync_posts(
    posts: list[dict[str, Any]],
    category_map: dict[int, str],
    tag_map: dict[int, str],
    vault_dir: Path,
    target_dir: str,
    source_url: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    root = vault_dir / target_dir
    old_index = load_index(root)
    old_posts = old_index.get("posts", {})
    if not isinstance(old_posts, dict):
        old_posts = {}

    if not dry_run:
        root.mkdir(parents=True, exist_ok=True)
        (root / "_sync").mkdir(parents=True, exist_ok=True)

    actions: list[dict[str, Any]] = []
    new_posts: dict[str, Any] = {}
    active_ids = {str(int(post["id"])) for post in posts if post.get("id")}

    for post in posts:
        wp_id = str(int(post["id"]))
        rel_path, content = markdown_for_post(post, category_map, tag_map)
        content_hash = sha256_text(content)
        dest = root / rel_path
        old_entry = old_posts.get(wp_id) if isinstance(old_posts.get(wp_id), dict) else {}
        old_rel = str(old_entry.get("path") or "")
        old_hash = str(old_entry.get("hash") or "")
        old_path = root / old_rel if old_rel else None

        if old_path and old_path.exists() and old_path != dest:
            current_old_hash = sha256_file(old_path)
            if old_hash and current_old_hash != old_hash:
                conflict_path = move_to(root, old_path, "_conflicts", wp_id, dry_run)
                actions.append(action("conflict", wp_id, from_path=str(old_path.relative_to(root)), to_path=str(conflict_path.relative_to(root))))
            else:
                if not dry_run:
                    old_path.unlink()
                    remove_empty_parents(root, old_path.parent)
                actions.append(action("remove-old-path", wp_id, path=old_rel))

        write_needed = True
        if dest.exists():
            current_hash = sha256_file(dest)
            if current_hash == content_hash:
                write_needed = False
                actions.append(action("skip", wp_id, path=str(rel_path)))
            elif old_hash and current_hash != old_hash:
                conflict_path = move_to(root, dest, "_conflicts", wp_id, dry_run)
                actions.append(action("conflict", wp_id, from_path=str(rel_path), to_path=str(conflict_path.relative_to(root))))

        if write_needed:
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")
            actions.append(action("write", wp_id, path=str(rel_path), status=str(post.get("status") or "")))

        new_posts[wp_id] = {
            "path": str(rel_path),
            "remote_modified": str(post.get("modified") or ""),
            "hash": content_hash,
            "status": str(post.get("status") or ""),
        }

    for wp_id, entry in old_posts.items():
        if str(wp_id) in active_ids or not isinstance(entry, dict):
            continue
        rel = str(entry.get("path") or "")
        if not rel:
            continue
        old_path = root / rel
        if old_path.exists():
            archived = move_to(root, old_path, "_archived", str(wp_id), dry_run)
            if not dry_run:
                remove_empty_parents(root, old_path.parent)
            actions.append(action("archive", str(wp_id), from_path=rel, to_path=str(archived.relative_to(root))))
        else:
            actions.append(action("missing", str(wp_id), path=rel))

    new_index = {
        "version": INDEX_VERSION,
        "source": source_url.rstrip("/"),
        "target_dir": target_dir,
        "synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "posts": new_posts,
    }
    if not dry_run:
        index_path = root / "_sync" / "index.json"
        index_path.write_text(json.dumps(new_index, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "root": str(root),
        "post_count": len(posts),
        "actions": actions,
        "index": new_index,
    }


def parse_statuses(value: str) -> list[str]:
    statuses = []
    for status in re.split(r"[,，;；\s]+", value):
        status = status.strip()
        if status and status not in statuses:
            statuses.append(status)
    return statuses or ["publish", "draft", "private"]


def parser_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync WordPress KB posts into an Obsidian vault.")
    parser.add_argument("--env-file", default=".env.obsidian")
    parser.add_argument("--base-url", help="Override KB_PUBLIC_URL for this run.")
    parser.add_argument("--vault-dir", help="Override OBSIDIAN_VAULT_DIR for this run.")
    parser.add_argument("--target-dir", help="Override OBSIDIAN_KB_DIR for this run.")
    parser.add_argument("--status", default=DEFAULT_STATUSES, help="Comma-separated WordPress statuses to mirror.")
    parser.add_argument("--dry-run", action="store_true", help="Print the sync plan without writing files.")
    parser.add_argument("--watch", action="store_true", help="Keep running and use the WordPress Obsidian sync settings between runs.")
    parser.add_argument("--poll-seconds", type=int, help="Override the WordPress sync setting wait time when --watch is used.")
    parser.add_argument("--max-runs", type=int, help="Stop after this many runs; useful for testing --watch.")
    return parser.parse_args()


def run_sync_once(args: argparse.Namespace, base_url: str, auth: str) -> dict[str, Any]:
    vault_dir_value = args.vault_dir or os.environ.get("OBSIDIAN_VAULT_DIR")
    if not vault_dir_value:
        raise RuntimeError("Set OBSIDIAN_VAULT_DIR in .env.obsidian or pass --vault-dir.")
    vault_dir = Path(vault_dir_value).expanduser()
    target_dir = args.target_dir or os.environ.get("OBSIDIAN_KB_DIR") or DEFAULT_TARGET_DIR
    statuses = parse_statuses(args.status)
    remote_settings = fetch_sync_settings(base_url, auth) if args.watch else {}

    category_map = fetch_terms(base_url, auth, "categories")
    tag_map = fetch_terms(base_url, auth, "tags")
    posts = fetch_posts(base_url, auth, statuses)
    result = sync_posts(posts, category_map, tag_map, vault_dir, target_dir, base_url, dry_run=args.dry_run)
    summary = {
        "target": result["root"],
        "statuses": statuses,
        "post_count": result["post_count"],
        "dry_run": bool(args.dry_run),
        "watch": bool(args.watch),
        "remote_sync_settings": remote_settings,
        "actions": result["actions"],
    }
    return summary


def main() -> int:
    args = parser_args()
    load_env(Path(args.env_file))
    base_url, user, password = site_config(args.base_url)
    if not user or not password or password.startswith("CHANGE_ME"):
        print("Missing WordPress application password in env file.", file=sys.stderr)
        return 2

    auth = auth_header(user, password)
    run_count = 0

    while True:
        try:
            summary = run_sync_once(args, base_url, auth)
        except Exception as exc:
            print(f"Obsidian sync failed: {exc}", file=sys.stderr)
            return 2

        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
        run_count += 1

        if not args.watch or args.dry_run:
            return 0
        if args.max_runs is not None and run_count >= max(1, args.max_runs):
            return 0

        wait_seconds = args.poll_seconds if args.poll_seconds is not None else sync_wait_seconds(summary.get("remote_sync_settings") or {})
        wait_seconds = max(1, int(wait_seconds))
        mode = (summary.get("remote_sync_settings") or {}).get("mode") or "schedule"
        print(f"Next Obsidian sync in {wait_seconds} seconds ({mode}).", file=sys.stderr, flush=True)
        time.sleep(wait_seconds)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
