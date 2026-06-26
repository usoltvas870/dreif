"""Scan audio/ directory and regenerate catalog.json metadata."""
import json
import os
import re


AUDIO_DIR = os.path.join(os.path.dirname(__file__), "..", "audio")
CATALOG_PATH = os.path.join(AUDIO_DIR, "catalog.json")

# Load existing catalog to preserve hand-written metadata
existing: dict[str, dict] = {}
if os.path.exists(CATALOG_PATH):
    with open(CATALOG_PATH) as f:
        for t in json.load(f).get("tracks", []):
            existing[t["id"]] = t

tracks = []
for fname in sorted(os.listdir(AUDIO_DIR)):
    if not fname.endswith(".mp3"):
        continue
    track_id = fname[:-4]
    if track_id in existing:
        tracks.append(existing[track_id])
    else:
        tracks.append({"id": track_id, "title": track_id, "category": "unknown"})

catalog = {"tracks": tracks}
with open(CATALOG_PATH, "w") as f:
    json.dump(catalog, f, ensure_ascii=False, indent=2)

print(f"Catalog updated: {len(tracks)} tracks")
