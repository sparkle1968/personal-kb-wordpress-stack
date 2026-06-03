#!/usr/bin/env python3
"""Update Aliyun DNS A records for the home WordPress sites."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from urllib import parse, request

ENDPOINT = "https://alidns.aliyuncs.com/"
IP_ENDPOINTS = (
    "https://api.ipify.org",
    "https://ipv4.icanhazip.com",
    "https://checkip.amazonaws.com",
)


def percent_encode(value: object) -> str:
    return parse.quote(str(value), safe="-_.~")


def signed_query(params: dict[str, object], access_key_id: str, access_key_secret: str) -> str:
    base = {
        "Format": "JSON",
        "Version": "2015-01-09",
        "AccessKeyId": access_key_id,
        "SignatureMethod": "HMAC-SHA1",
        "Timestamp": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "SignatureVersion": "1.0",
        "SignatureNonce": str(uuid.uuid4()),
    }
    base.update(params)
    canonical = "&".join(f"{percent_encode(k)}={percent_encode(base[k])}" for k in sorted(base))
    string_to_sign = "GET&%2F&" + percent_encode(canonical)
    digest = hmac.new(
        (access_key_secret + "&").encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    signature = base64.b64encode(digest).decode("ascii")
    base["Signature"] = signature
    return parse.urlencode(base)


def aliyun_call(params: dict[str, object]) -> dict:
    access_key_id = os.environ["ALIYUN_ACCESS_KEY_ID"]
    access_key_secret = os.environ["ALIYUN_ACCESS_KEY_SECRET"]
    url = ENDPOINT + "?" + signed_query(params, access_key_id, access_key_secret)
    with request.urlopen(url, timeout=20) as resp:
        payload = resp.read().decode("utf-8")
    data = json.loads(payload)
    if "Code" in data and data.get("Code") not in {"200", 200}:
        raise RuntimeError(f"Aliyun API error: {data}")
    return data


def current_public_ip() -> str:
    last_error: Exception | None = None
    for endpoint in IP_ENDPOINTS:
        try:
            with request.urlopen(endpoint, timeout=10) as resp:
                ip = resp.read().decode("utf-8").strip()
            parts = ip.split(".")
            if len(parts) == 4 and all(part.isdigit() and 0 <= int(part) <= 255 for part in parts):
                return ip
        except Exception as exc:  # pragma: no cover - network dependent
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"Could not detect public IPv4 address: {last_error}")


def find_record(domain_name: str, rr: str) -> dict | None:
    data = aliyun_call({
        "Action": "DescribeSubDomainRecords",
        "SubDomain": f"{rr}.{domain_name}",
        "Type": "A",
    })
    records = data.get("DomainRecords", {}).get("Record", [])
    if isinstance(records, dict):
        records = [records]
    return records[0] if records else None


def update_record(domain_name: str, rr: str, ip: str, ttl: int, dry_run: bool) -> str:
    record = find_record(domain_name, rr)
    if record and record.get("Value") == ip:
        return f"{rr}.{domain_name} already points to {ip}"

    if dry_run:
        action = "would update" if record else "would create"
        old = record.get("Value") if record else "missing"
        return f"{rr}.{domain_name}: {action} A record {old} -> {ip}"

    if record:
        aliyun_call({
            "Action": "UpdateDomainRecord",
            "RecordId": record["RecordId"],
            "RR": rr,
            "Type": "A",
            "Value": ip,
            "TTL": ttl,
        })
        return f"{rr}.{domain_name}: updated {record.get('Value')} -> {ip}"

    aliyun_call({
        "Action": "AddDomainRecord",
        "DomainName": domain_name,
        "RR": rr,
        "Type": "A",
        "Value": ip,
        "TTL": ttl,
    })
    return f"{rr}.{domain_name}: created A record -> {ip}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ip", help="Override detected public IP")
    args = parser.parse_args()

    required = ["ALIYUN_ACCESS_KEY_ID", "ALIYUN_ACCESS_KEY_SECRET", "ALIYUN_DOMAIN_NAME"]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print(f"Missing environment variables: {', '.join(missing)}", file=sys.stderr)
        return 2

    domain_name = os.environ["ALIYUN_DOMAIN_NAME"]
    rr_list = [rr.strip() for rr in os.environ.get("ALIYUN_RR_LIST", "kb,family").split(",") if rr.strip()]
    ttl = int(os.environ.get("ALIYUN_TTL", "600"))
    ip = args.ip or current_public_ip()

    for rr in rr_list:
        print(update_record(domain_name, rr, ip, ttl, args.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

