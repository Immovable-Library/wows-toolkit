#!/usr/bin/env python3
"""Download all PVE replays from replayswows.com.

Resumable: skips already-downloaded files and records failures to failed.json.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BASE = "https://replayswows.com"
API = f"{BASE}/api/search/index"
DOWNLOAD = f"{BASE}/replay/download"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)

OUT_DIR = Path(__file__).resolve().parent.parent / "replays" / "replayswows-pve"
METADATA_PATH = OUT_DIR / "metadata.json"
FAILED_PATH = OUT_DIR / "failed.json"

CONCURRENCY = 4
REQUEST_DELAY = 0.15
MAX_RETRIES = 6


def _open(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def _open_json(url: str) -> object:
    return json.loads(_open(url).decode("utf-8"))


def fetch_all_metadata() -> list[dict]:
    """Fetch every replay object from the paged search API."""
    first = _open_json(
        f"{API}?by=desc&gameMode%5B%5D=pve&order=uploaded_at&page=1"
    )
    total_pages = int(first["pages"]["total"])
    expected = int(first["pages"]["count"])
    replays: list[dict] = list(first["replays"])
    seen = {r["id"] for r in replays}

    for page in range(2, total_pages + 1):
        url = (
            f"{API}?by=desc&gameMode%5B%5D=pve&order=uploaded_at&page={page}"
        )
        for attempt in range(MAX_RETRIES):
            try:
                data = _open_json(url)
                break
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                if attempt == MAX_RETRIES - 1:
                    raise
                time.sleep(2**attempt)
        else:
            raise RuntimeError(f"unreachable: page {page}")

        for r in data["replays"]:
            if r["id"] not in seen:
                seen.add(r["id"])
                replays.append(r)
        time.sleep(REQUEST_DELAY)

    print(f"fetched {len(replays)} replay ids (expected {expected})")
    return replays


def download_one(replay: dict) -> tuple[int, str]:
    rid = replay["id"]
    target = OUT_DIR / f"{rid}.wowsreplay"
    if target.exists() and target.stat().st_size > 0:
        return rid, "exists"

    url = f"{DOWNLOAD}/{rid}"
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            data = _open(url)
            tmp = target.with_suffix(".wowsreplay.part")
            tmp.write_bytes(data)
            tmp.replace(target)
            time.sleep(REQUEST_DELAY)
            return rid, "ok"
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code == 404:
                return rid, "404"
            if exc.code == 429:
                time.sleep(5 * (attempt + 1))
            else:
                time.sleep(2**attempt)
        except (urllib.error.URLError, TimeoutError) as exc:
            last_exc = exc
            time.sleep(2**attempt)

    return rid, f"error:{last_exc}"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    replays = fetch_all_metadata()

    METADATA_PATH.write_text(
        json.dumps(replays, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    results: dict[str, list[dict]] = {"ok": [], "exists": [], "404": [], "error": []}
    failures: list[dict] = []

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = {pool.submit(download_one, r): r for r in replays}
        done = 0
        for future in as_completed(futures):
            replay = futures[future]
            rid, status = future.result()
            done += 1
            if status == "ok":
                results["ok"].append({"id": rid})
            elif status == "exists":
                results["exists"].append({"id": rid})
            elif status == "404":
                results["404"].append({"id": rid})
                failures.append({"id": rid, "reason": "404", "title": replay.get("title")})
            else:
                results["error"].append({"id": rid, "status": status})
                failures.append({"id": rid, "reason": status, "title": replay.get("title")})
            if done % 100 == 0 or done == len(replays):
                print(
                    f"progress {done}/{len(replays)} "
                    f"(ok={len(results['ok'])} exists={len(results['exists'])} "
                    f"404={len(results['404'])} error={len(results['error'])})",
                    flush=True,
                )

    FAILED_PATH.write_text(
        json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        "done: "
        f"ok={len(results['ok'])}, exists={len(results['exists'])}, "
        f"404={len(results['404'])}, error={len(results['error'])}"
    )
    print(f"metadata: {METADATA_PATH}")
    print(f"failures: {FAILED_PATH}")


if __name__ == "__main__":
    main()
