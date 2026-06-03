#!/usr/bin/env python3
"""Publish a draft post to one of the WordPress sites via REST API."""

from __future__ import annotations

import argparse
import base64
import html
import json
import mimetypes
import os
import sys
from pathlib import Path
from urllib import parse, request


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
        return (
            base_url or os.environ.get("KB_LOCAL_URL") or os.environ.get("KB_PUBLIC_URL") or "https://" + os.environ["DOMAIN_KB"],
            os.environ["WP_KB_API_USER"],
            os.environ["WP_KB_APP_PASSWORD"],
        )
    if site == "family":
        return (
            "https://" + os.environ["DOMAIN_FAMILY"],
            os.environ["WP_FAMILY_API_USER"],
            os.environ["WP_FAMILY_APP_PASSWORD"],
        )
    raise ValueError(f"Unknown site: {site}")


def auth_header(user: str, password: str) -> str:
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def api_call(base_url: str, auth: str, method: str, path: str, payload: dict | None = None, headers: dict | None = None) -> dict:
    data = None
    req_headers = {"Authorization": auth, "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/json; charset=utf-8"
    req = request.Request(base_url.rstrip("/") + path, data=data, headers=req_headers, method=method)
    with request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def upload_media(base_url: str, auth: str, file_path: Path) -> int:
    mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    headers = {
        "Authorization": auth,
        "Content-Type": mime,
        "Content-Disposition": f"attachment; filename={file_path.name}",
    }
    req = request.Request(
        base_url.rstrip("/") + "/wp-json/wp/v2/media",
        data=file_path.read_bytes(),
        headers=headers,
        method="POST",
    )
    with request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))["id"]


def ensure_term(base_url: str, auth: str, taxonomy: str, name: str) -> int:
    path = f"/wp-json/wp/v2/{taxonomy}?search={parse.quote(name)}"
    found = api_call(base_url, auth, "GET", path)
    for item in found:
        if item.get("name") == name:
            return int(item["id"])
    created = api_call(base_url, auth, "POST", f"/wp-json/wp/v2/{taxonomy}", {"name": name})
    return int(created["id"])


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--base-url")
    parser.add_argument("--site", choices=["kb", "family"], required=True)
    parser.add_argument("--post-id", type=int, help="Update an existing post instead of creating a new one.")
    parser.add_argument("--title", required=True)
    parser.add_argument("--content-file", required=True)
    parser.add_argument("--excerpt")
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--media", action="append", default=[])
    parser.add_argument("--featured-media")
    parser.add_argument("--source-url")
    parser.add_argument("--source-site")
    parser.add_argument("--source-author")
    parser.add_argument("--private-archive-file")
    parser.add_argument("--status", default="draft", choices=["draft", "private", "publish"])
    parser.add_argument("--dry-run", action="store_true", help="Show the payload without calling WordPress.")
    args = parser.parse_args()

    load_env(Path(args.env_file))
    base_url, user, password = site_config(args.site, args.base_url)

    body = Path(args.content_file).read_text()
    payload: dict = {
        "title": args.title,
        "content": kb_content(args, body),
        "status": args.status,
    }

    if args.excerpt is not None:
        payload["excerpt"] = args.excerpt

    source_meta = {
        "source_url": args.source_url or "",
        "source_site": args.source_site or "",
        "source_author": args.source_author or "",
    }
    if not args.post_id or any([args.source_url, args.source_site, args.source_author]):
        payload["meta"] = source_meta

    if args.dry_run:
        preview = {
            "target": base_url,
            "method": "update" if args.post_id else "create",
            "post_id": args.post_id,
            "categories": args.category,
            "tags": args.tag,
            "media": args.media,
            "featured_media": args.featured_media,
            "payload": payload,
        }
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return 0

    if not password or password.startswith("CHANGE_ME"):
        print("Missing WordPress application password in .env", file=sys.stderr)
        return 2
    auth = auth_header(user, password)

    category_ids = [ensure_term(base_url, auth, "categories", name) for name in args.category]
    tag_ids = [ensure_term(base_url, auth, "tags", name) for name in args.tag]
    if category_ids or not args.post_id:
        payload["categories"] = category_ids
    if tag_ids or not args.post_id:
        payload["tags"] = tag_ids

    media_ids = [upload_media(base_url, auth, Path(path)) for path in args.media]
    featured_id = None
    if args.featured_media:
        featured_id = upload_media(base_url, auth, Path(args.featured_media))
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
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
