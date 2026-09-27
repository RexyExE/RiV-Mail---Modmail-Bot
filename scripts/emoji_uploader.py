from __future__ import annotations

import asyncio
import base64
import json
import sys
from pathlib import Path
from typing import Any

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402

API_BASE = "https://discord.com/api/v10"


def _load_json(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_json(path: str, data: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


async def _source_bytes(session: aiohttp.ClientSession, entry: dict[str, Any]) -> bytes | None:
    source_type = entry.get("source_type")
    if source_type == "discord_emoji":
        ext = "gif" if entry.get("animated") else "png"
        url = f"https://cdn.discordapp.com/emojis/{entry['source_id']}.{ext}"
    elif source_type == "url":
        url = entry["source_url"]
    else:
        return None

    async with session.get(url) as resp:
        if resp.status != 200:
            print(f"  ! failed to fetch source ({resp.status}): {url}")
            return None
        return await resp.read()


async def run(force: bool = False) -> dict[str, Any]:
    if not config.TOKEN:
        print("[emoji_uploader] BOT_TOKEN is not set, skipping.")
        return {}

    definitions = _load_json(config.EMOJIS_JSON)
    uploaded = _load_json(config.EMOJIS_UPLOADED_JSON)
    definitions = {k: v for k, v in definitions.items() if not k.startswith("_")}

    if not definitions:
        print("[emoji_uploader] emojis.json is empty, nothing to do.")
        return uploaded

    headers = {"Authorization": f"Bot {config.TOKEN}"}
    changed = False

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f"{API_BASE}/oauth2/applications/@me") as resp:
            if resp.status != 200:
                print(f"[emoji_uploader] could not resolve application id ({resp.status}), aborting.")
                return uploaded
            app = await resp.json()
        app_id = app["id"]

        # Reconcile against what Discord actually has registered for this
        # application first. emojis_uploaded.json is just a local cache - if
        # it's empty/stale (wiped, redeployed, edited by hand) the names may
        # already exist on the application, and blind-POSTing them fails with
        # APPLICATION_EMOJI_NAME_ALREADY_TAKEN forever without this step.
        existing_by_name: dict[str, dict[str, Any]] = {}
        async with session.get(f"{API_BASE}/applications/{app_id}/emojis") as resp:
            if resp.status == 200:
                remote = await resp.json()
                for item in remote.get("items", []):
                    existing_by_name[item["name"]] = item
            else:
                print(f"  ! could not list existing application emojis ({resp.status}), duplicates may fail to reconcile.")

        for key, entry in definitions.items():
            if entry.get("source_type") == "unicode":
                continue
            if not force and key in uploaded and uploaded[key].get("id"):
                continue

            wanted_name = entry["name"]
            remote_match = existing_by_name.get(wanted_name)
            if remote_match and not force:
                uploaded[key] = {
                    "id": remote_match["id"],
                    "name": remote_match["name"],
                    "animated": bool(remote_match.get("animated", entry.get("animated"))),
                }
                changed = True
                print(f"  = reconciled '{key}' -> {remote_match['name']}:{remote_match['id']} (already on application)")
                _save_json(config.EMOJIS_UPLOADED_JSON, uploaded)
                continue

            image_bytes = await _source_bytes(session, entry)
            if not image_bytes:
                print(f"  ! skipping '{key}': no source image")
                continue

            b64 = base64.b64encode(image_bytes).decode("ascii")
            mime = "image/gif" if entry.get("animated") else "image/png"
            payload = {"name": wanted_name, "image": f"data:{mime};base64,{b64}"}

            async with session.post(f"{API_BASE}/applications/{app_id}/emojis", json=payload) as resp:
                data = await resp.json()
                if resp.status not in (200, 201):
                    errors = data.get("errors", {}) if isinstance(data, dict) else {}
                    name_errors = errors.get("name", {}).get("_errors", [{}])
                    if any(e.get("code") == "APPLICATION_EMOJI_NAME_ALREADY_TAKEN" for e in name_errors):
                        # Our snapshot from the top of the run raced with reality
                        # (e.g. uploaded moments ago elsewhere) - refetch once and
                        # reconcile this single entry instead of giving up on it.
                        async with session.get(f"{API_BASE}/applications/{app_id}/emojis") as refetch:
                            if refetch.status == 200:
                                remote = await refetch.json()
                                match = next((i for i in remote.get("items", []) if i["name"] == wanted_name), None)
                                if match:
                                    uploaded[key] = {
                                        "id": match["id"],
                                        "name": match["name"],
                                        "animated": bool(match.get("animated", entry.get("animated"))),
                                    }
                                    changed = True
                                    print(f"  = reconciled '{key}' -> {match['name']}:{match['id']} (found on retry)")
                                    _save_json(config.EMOJIS_UPLOADED_JSON, uploaded)
                                    continue
                    print(f"  ! failed to upload '{key}' ({resp.status}): {data}")
                    continue
                uploaded[key] = {
                    "id": data["id"],
                    "name": data["name"],
                    "animated": bool(entry.get("animated")),
                }
                changed = True
                print(f"  + uploaded '{key}' -> {data['name']}:{data['id']}")
                _save_json(config.EMOJIS_UPLOADED_JSON, uploaded)

    if changed:
        _save_json(config.EMOJIS_UPLOADED_JSON, uploaded)
        print(f"[emoji_uploader] saved {config.EMOJIS_UPLOADED_JSON}")
    else:
        print("[emoji_uploader] nothing new to upload.")

    return uploaded


if __name__ == "__main__":
    force_flag = "--force" in sys.argv
    asyncio.run(run(force=force_flag))
