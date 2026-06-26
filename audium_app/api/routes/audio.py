import json
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from audium_app.api.deps import get_current_user, has_access
from audium_app.core.models import User

router = APIRouter()

AUDIO_DIR = "/app/audio"
CATALOG_PATH = os.path.join(AUDIO_DIR, "catalog.json")


@router.get("/catalog")
async def get_catalog():
    if not os.path.exists(CATALOG_PATH):
        return {"tracks": []}
    with open(CATALOG_PATH) as f:
        return json.load(f)


@router.get("/{track_id}")
async def stream_audio(
    track_id: str,
    user: User = Depends(get_current_user),
):
    if not has_access(user):
        raise HTTPException(status_code=403, detail="Subscription required")

    # Sanitize: only allow alphanumeric, dash, underscore
    safe_id = "".join(c for c in track_id if c.isalnum() or c in "-_")
    if safe_id != track_id:
        raise HTTPException(status_code=400, detail="Invalid track id")

    file_path = os.path.join(AUDIO_DIR, f"{safe_id}.mp3")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Track not found")

    return FileResponse(file_path, media_type="audio/mpeg")
