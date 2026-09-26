from __future__ import annotations

import json


def publication_media_asset_ids(publication) -> list[str]:
    try:
        stored_ids = json.loads(publication.media_asset_ids_json or "[]")
    except (TypeError, json.JSONDecodeError):
        stored_ids = []
    if isinstance(stored_ids, list):
        ids = list(dict.fromkeys(item for item in stored_ids if isinstance(item, str) and item))
        if ids:
            return ids
    return [publication.render_asset_id] if publication.render_asset_id else []
