from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


def load_env(path: Path | None) -> None:
    if not path or not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def request_json(method: str, url: str, token: str | None = None, body: dict | None = None) -> dict:
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def upload_image(url: str, token: str, app_token: str, path: Path) -> str:
    boundary = f"----codex{uuid.uuid4().hex}"
    fields = {
        "file_name": path.name,
        "parent_type": "bitable_image",
        "parent_node": app_token,
        "size": str(path.stat().st_size),
    }
    parts: list[bytes] = []
    for key, value in fields.items():
        parts += [f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(), value.encode("utf-8"), b"\r\n"]
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    parts += [f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'.encode(), f"Content-Type: {mime}\r\n\r\n".encode(), path.read_bytes(), b"\r\n", f"--{boundary}--\r\n".encode()]
    req = urllib.request.Request(url, data=b"".join(parts), headers={"Authorization": f"Bearer {token}", "Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("code") != 0:
        raise RuntimeError(f"image upload failed: {result}")
    return result["data"]["file_token"]


def require_config() -> tuple[str, str, str, str | None, str]:
    required = {name: os.environ.get(name, "").strip() for name in ("FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_BASE_URL")}
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"missing configuration: {', '.join(missing)}")
    match = re.search(r"/base/([^?/#]+)", required["FEISHU_BASE_URL"])
    if not match:
        raise RuntimeError("FEISHU_BASE_URL does not contain a Bitable app token")
    return required["FEISHU_APP_ID"], required["FEISHU_APP_SECRET"], match.group(1), os.environ.get("FEISHU_TABLE_ID") or None, os.environ.get("FEISHU_TABLE_NAME", "数据表")


def token_for(app_id: str, secret: str) -> str:
    result = request_json("POST", "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal", body={"app_id": app_id, "app_secret": secret})
    if result.get("code") != 0:
        raise RuntimeError(f"Feishu authentication failed: {result}")
    return result["tenant_access_token"]


def resolve_table(token: str, app_token: str, table_id: str | None, table_name: str) -> str:
    if table_id:
        return table_id
    result = request_json("GET", f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables", token)
    if result.get("code") != 0:
        raise RuntimeError(f"unable to list tables: {result}")
    items = result.get("data", {}).get("items", [])
    for item in items:
        if item.get("name") == table_name:
            return item["table_id"]
    if len(items) == 1:
        return items[0]["table_id"]
    raise RuntimeError(f"table not found: {table_name}")


def list_all(token: str, url: str) -> list[dict]:
    items: list[dict] = []
    page_token = ""
    while True:
        suffix = "?page_size=100" + ("&page_token=" + urllib.parse.quote(page_token) if page_token else "")
        result = request_json("GET", url + suffix, token)
        if result.get("code") != 0:
            raise RuntimeError(f"list failed: {result}")
        data = result.get("data", {})
        items.extend(data.get("items", []))
        if not data.get("has_more"):
            return items
        page_token = data.get("page_token", "")


def field_name(fields: list[dict], candidates: list[str]) -> str:
    names = [item.get("field_name", "") for item in fields]
    for candidate in candidates:
        if candidate in names:
            return candidate
    raise RuntimeError(f"required field missing; candidates={candidates}; available={names}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=Path.home() / ".codex" / "secrets" / "ima-material-creation.env")
    parser.add_argument("--payload", type=Path)
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    load_env(args.env_file)
    app_id, secret, app_token, configured_table, table_name = require_config()
    token = token_for(app_id, secret)
    table_id = resolve_table(token, app_token, configured_table, table_name)
    base = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}"
    fields = list_all(token, base + "/fields")
    mapping = {
        "title": field_name(fields, ["标题", "题目"]),
        "copy": field_name(fields, ["文案", "正文", "内容"]),
        "tags": field_name(fields, ["标签", "话题"]),
        "images": field_name(fields, ["图片", "图"]),
    }
    if args.check:
        print(json.dumps({"status": "ok", "app_token": app_token, "table_id": table_id, "fields": mapping}, ensure_ascii=False))
        return
    if not args.payload:
        raise RuntimeError("--payload is required unless --check is used")
    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    images = [Path(item).expanduser().resolve() for item in payload["images"]]
    missing = [str(path) for path in images if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing images: {missing}")
    state_file = args.state_file or args.payload.with_suffix(".state.json")
    if state_file.exists() and json.loads(state_file.read_text(encoding="utf-8")).get("status") in {"running", "succeeded", "needs_confirmation"}:
        raise RuntimeError("refusing duplicate write based on state file")
    records = list_all(token, base + "/records")
    blank = next((item for item in records if not item.get("fields") or all(value in (None, "", []) for value in item.get("fields", {}).values())), None)
    if not blank:
        raise RuntimeError("no blank record available; refusing overwrite")
    record_id = blank["record_id"]
    state_file.write_text(json.dumps({"status": "running", "record_id": record_id, "started_at": time.time()}, indent=2), encoding="utf-8")
    try:
        tokens = [upload_image("https://open.feishu.cn/open-apis/drive/v1/medias/upload_all", token, app_token, path) for path in images]
        values = {mapping["title"]: payload["title"], mapping["copy"]: payload["copy"], mapping["tags"]: payload["tags"], mapping["images"]: [{"file_token": item} for item in tokens]}
        result = request_json("PUT", base + f"/records/{record_id}", token, {"fields": values})
        if result.get("code") != 0:
            raise RuntimeError(f"record update failed: {result}")
        current = request_json("GET", base + f"/records/{record_id}", token)
        readback = current.get("data", {}).get("record", {}).get("fields", {})
        if not all(readback.get(mapping[key]) for key in ("title", "copy", "tags", "images")):
            raise RuntimeError("read-back validation failed")
        final = {"status": "succeeded", "record_id": record_id, "images": len(tokens), "finished_at": time.time()}
        state_file.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(final, ensure_ascii=False))
    except Exception as exc:
        state_file.write_text(json.dumps({"status": "needs_confirmation", "record_id": record_id, "error": str(exc)}, ensure_ascii=False, indent=2), encoding="utf-8")
        raise


if __name__ == "__main__":
    main()
