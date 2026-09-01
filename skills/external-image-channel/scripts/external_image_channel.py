from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import re
import struct
import time
from pathlib import Path

import requests


CHANNELS = {
    "frimodel": {
        "api_base": "https://api.frimodel.com/v1/images",
        "model": "gpt-image-2-w",
        "key_file": Path(r"C:\Users\86158\Documents\Codex\2026-06-20\ni\work\frimodel_api_keys.txt"),
    },
    "laozhang": {
        "api_base": "https://api2.laozhang.ai/v1/images",
        "model": "gpt-image-2-vip",
        "key_file": Path(r"C:\Users\86158\Documents\Codex\2026-06-20\ni\work\image_api_keys.txt"),
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--channel", choices=sorted(CHANNELS), default="frimodel")
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--key-index", type=int, default=0)
    parser.add_argument("--size", default="1536x2048")
    parser.add_argument("--quality", default="high")
    parser.add_argument("--timeout", type=int, default=600)
    return parser.parse_args()


def write_state(path: Path, body: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")


def read_keys(path: Path) -> list[str]:
    keys = re.findall(r"\bsk-[A-Za-z0-9_-]+", path.read_text(encoding="utf-8"))
    if not keys:
        raise RuntimeError(f"No API keys found in {path}")
    return keys


def receive_image(session: requests.Session, response: requests.Response) -> bytes:
    payload = response.json()
    item = payload.get("data", [{}])[0]
    raw = item.get("b64_json")
    if raw:
        if raw.startswith("data:"):
            raw = raw.split(",", 1)[1]
        raw += "=" * ((4 - len(raw) % 4) % 4)
        return base64.b64decode(raw)
    url = item.get("url")
    if url:
        downloaded = session.get(url, timeout=(30, 180))
        downloaded.raise_for_status()
        return downloaded.content
    raise RuntimeError("Image response has neither b64_json nor url")


def image_size(data: bytes) -> tuple[int, int] | None:
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            length = int.from_bytes(data[index + 2:index + 4], "big")
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                height = int.from_bytes(data[index + 5:index + 7], "big")
                width = int.from_bytes(data[index + 7:index + 9], "big")
                return width, height
            index += 2 + length
    return None


def main() -> None:
    args = parse_args()
    if not args.prompt_file.exists():
        raise RuntimeError(f"Missing prompt file: {args.prompt_file}")
    if args.reference and not args.reference.exists():
        raise RuntimeError(f"Missing reference image: {args.reference}")

    if args.state_file.exists():
        old = json.loads(args.state_file.read_text(encoding="utf-8"))
        if old.get("status") in {"running", "succeeded", "timeout_needs_confirmation"}:
            raise RuntimeError(f"Refusing duplicate request; state={old.get('status')}")

    channel = CHANNELS[args.channel]
    key_file = args.key_file or channel["key_file"]
    keys = read_keys(key_file)
    key = keys[args.key_index % len(keys)]
    prompt = args.prompt_file.read_text(encoding="utf-8").strip()
    if not prompt:
        raise RuntimeError("Prompt file is empty")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_state(
        args.state_file,
        {
            "status": "running",
            "channel": args.channel,
            "model": channel["model"],
            "key_index": args.key_index % len(keys),
            "output": str(args.output),
            "reference": str(args.reference) if args.reference else None,
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
    )

    session = requests.Session()
    session.trust_env = False
    try:
        headers = {"Authorization": f"Bearer {key}"}
        if args.reference:
            mime = mimetypes.guess_type(args.reference.name)[0] or "application/octet-stream"
            with args.reference.open("rb") as handle:
                response = session.post(
                    f"{channel['api_base']}/edits",
                    headers=headers,
                    data={
                        "model": channel["model"],
                        "prompt": prompt,
                        "size": args.size,
                        "quality": args.quality,
                    },
                    files={"image": (args.reference.name, handle, mime)},
                    timeout=(30, args.timeout),
                )
        else:
            response = session.post(
                f"{channel['api_base']}/generations",
                headers={**headers, "Content-Type": "application/json"},
                json={
                    "model": channel["model"],
                    "prompt": prompt,
                    "size": args.size,
                    "quality": args.quality,
                },
                timeout=(30, args.timeout),
            )
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:1000]}")
        data = receive_image(session, response)
        size = image_size(data)
        if size is None:
            raise RuntimeError("Returned data is not a supported PNG or JPEG image")
        args.output.write_bytes(data)
        write_state(
            args.state_file,
            {
                "status": "succeeded",
                "channel": args.channel,
                "model": channel["model"],
                "output": str(args.output),
                "size": list(size),
                "bytes": len(data),
                "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
        print(json.dumps({"status": "succeeded", "output": str(args.output), "size": size}, ensure_ascii=False))
    except requests.Timeout as exc:
        write_state(
            args.state_file,
            {
                "status": "timeout_needs_confirmation",
                "output": str(args.output),
                "error": str(exc),
            },
        )
        raise
    except Exception as exc:
        write_state(
            args.state_file,
            {"status": "failed", "output": str(args.output), "error": repr(exc)},
        )
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
