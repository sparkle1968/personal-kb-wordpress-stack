#!/usr/bin/env python3
"""Mobile-friendly SSH entrypoint for publishing to the personal KB.

This script is intentionally a thin wrapper around kb-import.py. It is meant to
be called from iOS Shortcuts over SSH, so WordPress credentials stay on the
Debian VM and no public HTTP endpoint is added.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any
from urllib import parse


ROOT = Path(__file__).resolve().parents[1]
IMPORTER_PATH = ROOT / "scripts" / "kb-import.py"
LOG_PATH = ROOT / "incoming" / "kb-mobile-publish.log"
DEFAULT_STATUS = "publish"
CATEGORY_ALIASES = {
    "待读": "未分类",
    "未读": "未分类",
}


def log_event(event: str, **details: Any) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event": event,
            **details,
        }
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def safe_preview(value: Any, limit: int = 500) -> str:
    text = str(value or "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def load_importer():
    spec = importlib.util.spec_from_file_location("kb_import", IMPORTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load importer from {IMPORTER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def first_url(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip()
    if value in {"0", "null", "(null)", "None"}:
        return ""
    normalized = value.replace("\\/", "/")

    x_status = re.search(
        r"https?://(?:x|twitter)\.com/[^/\"'<>\s]+/status(?:es)?/\d+",
        normalized,
        re.I,
    )
    if x_status:
        return clean_url_match(x_status.group(0))

    status_id = re.search(r'"(?:conversation_id_str|id_str)"\s*:\s*"(\d{10,})"', normalized)
    screen_name = re.search(r'"screen_name"\s*:\s*"([^"]+)"', normalized)
    if status_id and screen_name:
        return f"https://x.com/{screen_name.group(1)}/status/{status_id.group(1)}"

    matches = re.findall(r"https?://[^\"'<>\s]+", normalized)
    if not matches:
        return ""

    for candidate in matches:
        cleaned = clean_url_match(candidate)
        if cleaned and not looks_like_asset_url(cleaned):
            return cleaned
    return clean_url_match(matches[0])


def clean_url_match(value: str) -> str:
    return value.rstrip("，。；;、).,\\")


def looks_like_asset_url(value: str) -> bool:
    parsed = parse.urlparse(value)
    host = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    if host.endswith(("twimg.com", "twitter.com")) and any(
        marker in path for marker in ("/responsive-web/", "/client-web/")
    ):
        return True
    return bool(
        re.search(
            r"\.(?:css|js|mjs|woff2?|ttf|otf|eot|png|jpe?g|gif|webp|avif|svg|ico)(?:$|\?)",
            path,
        )
    )


def split_terms(values: list[str] | None) -> list[str]:
    if not values:
        return []
    terms: list[str] = []
    for value in values:
        for item in re.split(r"[,，;；\n]+", value):
            item = item.strip()
            if item and item not in terms:
                terms.append(item)
    return terms


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def env_path(value: str) -> str:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return str(path)


def load_wordpress_categories(importer, args: argparse.Namespace) -> list[str]:
    importer.load_env(Path(env_path(args.env_file)))
    base_url, user, password = importer.site_config(args.site)
    if not user or not password:
        raise SystemExit("Missing WordPress API credentials in env file.")

    auth = importer.auth_header(user, password)
    categories: list[str] = []
    page = 1
    while True:
        path = (
            "/wp-json/wp/v2/categories"
            f"?per_page=100&page={page}&hide_empty=false&orderby=name&order=asc"
        )
        batch = importer.api_call(base_url, auth, "GET", path)
        if not isinstance(batch, list):
            break

        for item in batch:
            if not isinstance(item, dict):
                continue
            if item.get("slug") == "uncategorized":
                continue
            name = str(item.get("name") or "").strip()
            if name and name not in categories:
                categories.append(name)

        if len(batch) < 100:
            break
        page += 1

    return categories


def category_hint(categories: list[str]) -> str:
    return ", ".join(categories) if categories else "WordPress 里暂无可用分类"


def normalize_category_aliases(categories: list[str], available_categories: list[str]) -> list[str]:
    normalized: list[str] = []
    for category in categories:
        target = CATEGORY_ALIASES.get(category, category)
        if target not in available_categories:
            target = category
        if target not in normalized:
            normalized.append(target)
    return normalized


def sanitize_html(importer, raw_html: str, base_url: str | None) -> str:
    root = importer.build_tree(raw_html)
    body = importer.collapse_empty_blocks(importer.serialize_node(root, base_url))
    if body:
        return body
    return importer.text_to_html(importer.clean_text(importer.node_text(root)))


def content_title(importer, raw_html: str, fallback: str) -> str:
    meta = importer.parse_metadata(raw_html)
    title = (
        importer.meta_first(meta, ["og:title", "twitter:title"])
        or meta.title()
        or fallback
    )
    return importer.clean_text(title)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publish a mobile-shared URL or article body to the personal knowledge base."
    )
    parser.add_argument("--url", help="URL shared from the phone.")
    parser.add_argument("--url-encoded", help="Percent-encoded URL shared from Shortcuts.")
    parser.add_argument("--stdin-json", action="store_true", help="Read article data as JSON from stdin.")
    parser.add_argument("--list-categories", action="store_true", help="Print current WordPress categories and exit.")
    parser.add_argument("--title")
    parser.add_argument("--category", action="append", help="Knowledge base category, e.g. 技术 or 健康.")
    parser.add_argument("--tag", action="append", default=[], help="Repeatable tag name.")
    parser.add_argument("--tags", help="Comma/newline separated tag names, easier for iOS Shortcuts.")
    parser.add_argument("--status", choices=["draft", "private", "publish"], default=DEFAULT_STATUS)
    parser.add_argument("--site", choices=["kb"], default="kb")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--source-site")
    parser.add_argument("--source-author")
    parser.add_argument("--no-copy-images", action="store_true")
    parser.add_argument("--max-images", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json-output", action="store_true", help="Print machine-readable JSON instead of a mobile-friendly message.")
    return parser


def read_payload() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        raise ValueError("--stdin-json was set but stdin is empty")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"stdin is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("stdin JSON must be an object")
    return payload


def run_importer(cmd: list[str]) -> dict[str, Any]:
    log_event("importer_start", cmd=[part if "PASSWORD" not in part else "[redacted]" for part in cmd])
    completed = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        log_event(
            "importer_failed",
            returncode=completed.returncode,
            stdout=safe_preview(completed.stdout),
            stderr=safe_preview(completed.stderr),
        )
        if completed.stderr:
            print(completed.stderr.strip(), file=sys.stderr)
        if completed.stdout:
            print(completed.stdout.strip(), file=sys.stderr)
        raise SystemExit(completed.returncode)

    output = completed.stdout.strip()
    log_event("importer_succeeded", output=safe_preview(output))
    if not output:
        return {}
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return {"output": output}


def enable_public_share(importer, args: argparse.Namespace, result: dict[str, Any]) -> str:
    post_id = result.get("id")
    if not post_id or result.get("status") != "publish":
        return ""

    try:
        importer.load_env(Path(env_path(args.env_file)))
        base_url, user, password = importer.site_config(args.site)
        if not user or not password:
            return ""
        auth = importer.auth_header(user, password)
        response = importer.api_call(
            base_url,
            auth,
            "POST",
            f"/wp-json/home-kb/v1/public-share/{int(post_id)}",
            {},
        )
        share_url = str(response.get("share_url") or "").strip()
        log_event("public_share_enabled", post_id=post_id, share_url=share_url)
        return share_url
    except Exception as exc:
        log_event("public_share_failed", post_id=post_id, error=str(exc))
        return ""


def main() -> int:
    args = build_parser().parse_args()
    log_event(
        "start",
        argv=sys.argv[1:],
        stdin_json=args.stdin_json,
        raw_url_preview=safe_preview(args.url),
        category_args=args.category or [],
    )
    importer = load_importer()
    available_categories = load_wordpress_categories(importer, args)

    if args.list_categories:
        log_event("list_categories", categories=available_categories)
        print("\n".join(available_categories))
        return 0

    raw_stdin = ""
    if args.stdin_json:
        stdin_payload: dict[str, Any] = read_payload()
    else:
        stdin_payload = {}
        if not args.url and not args.url_encoded:
            raw_stdin = sys.stdin.read()

    encoded_url = args.url_encoded or stdin_payload.get("url_encoded")
    url_value = parse.unquote(str(encoded_url)) if encoded_url else args.url or stdin_payload.get("url") or stdin_payload.get("source_url") or raw_stdin
    url = first_url(url_value)
    categories = split_terms(args.category or normalize_list(stdin_payload.get("category") or stdin_payload.get("categories")))
    categories = normalize_category_aliases(categories, available_categories)
    tags = split_terms(args.tag + normalize_list(args.tags) + normalize_list(stdin_payload.get("tag") or stdin_payload.get("tags")))
    status = str(stdin_payload.get("status") or args.status)
    log_event(
        "parsed_input",
        url=url,
        url_value_preview=safe_preview(url_value),
        categories=categories,
        tags=tags,
        status=status,
        available_categories=available_categories,
    )
    if status not in {"draft", "private", "publish"}:
        log_event("invalid_status", status=status)
        raise SystemExit("status must be draft, private, or publish")

    if not categories:
        log_event("missing_category", available_categories=available_categories)
        raise SystemExit("Missing --category. Current categories: " + category_hint(available_categories))
    unsupported = [item for item in categories if item not in available_categories]
    if unsupported:
        log_event("unsupported_category", unsupported=unsupported, available_categories=available_categories)
        raise SystemExit(
            "Unsupported category: "
            + ", ".join(unsupported)
            + ". Current categories: "
            + category_hint(available_categories)
        )

    html_body = stdin_payload.get("html") or stdin_payload.get("content_html")
    text_body = stdin_payload.get("text") or stdin_payload.get("body")
    title = args.title or stdin_payload.get("title") or ""
    source_site = args.source_site or stdin_payload.get("source_site") or ""
    source_author = args.source_author or stdin_payload.get("source_author") or ""

    base_cmd = [
        sys.executable,
        str(IMPORTER_PATH),
        "--env-file",
        env_path(args.env_file),
        "--site",
        args.site,
        "--status",
        status,
        "--max-images",
        str(args.max_images),
    ]
    if args.no_copy_images:
        base_cmd.append("--no-copy-images")
    if args.dry_run:
        base_cmd.append("--dry-run")
    for category in categories:
        base_cmd.extend(["--category", category])
    for tag in tags:
        base_cmd.extend(["--tag", tag])
    if source_site:
        base_cmd.extend(["--source-site", str(source_site)])
    if source_author:
        base_cmd.extend(["--source-author", str(source_author)])

    if html_body or text_body:
        if html_body:
            body = sanitize_html(importer, str(html_body), url or None)
            title = str(title or content_title(importer, str(html_body), url or "手机分享资料"))
        else:
            body = importer.text_to_html(str(text_body))
            title = str(title or url or "手机分享资料")

        with tempfile.TemporaryDirectory(prefix="kb-mobile-") as workdir:
            content_file = Path(workdir) / "content.html"
            content_file.write_text(body, encoding="utf-8")
            cmd = base_cmd + ["--content-file", str(content_file), "--title", title]
            if url:
                cmd.extend(["--source-url", url])
            result = run_importer(cmd)
    else:
        if not url:
            log_event("missing_url", raw_url_preview=safe_preview(url_value))
            print("没有收到有效网页链接。请从 Safari/Chrome 的网页分享菜单运行这个快捷指令。")
            return 0
        cmd = base_cmd + ["--url", url]
        if title:
            cmd.extend(["--title", str(title)])
        result = run_importer(cmd)

    if args.dry_run:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    summary = {
        "ok": True,
        "id": result.get("id"),
        "status": result.get("status"),
        "link": enable_public_share(importer, args, result) or result.get("link"),
        "share_link": "",
        "permalink": result.get("link"),
        "category": categories,
        "tags": tags,
    }
    summary["share_link"] = summary["link"] if summary["link"] != summary["permalink"] else ""
    log_event("done", summary=summary)
    if args.json_output:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    status_label = {
        "publish": "已发布",
        "draft": "草稿",
        "private": "私密",
    }.get(str(summary["status"] or ""), str(summary["status"] or "完成"))
    print(f"知识库发布成功：{status_label}")
    print(f"文章 ID：{summary['id']}")
    print(f"分类：{'、'.join(categories)}")
    if summary.get("link"):
        print(f"链接：{summary['link']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
