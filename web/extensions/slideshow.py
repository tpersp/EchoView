from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from config import load_config, save_config, IMAGE_DIR
import os

router = APIRouter()

@router.get("/slideshow/images")
async def list_images():
    images = []
    for root, dirs, files in os.walk(IMAGE_DIR):
        for file in files:
            if file.lower().endswith((".jpg", ".jpeg", ".png", ".gif")):
                images.append(os.path.join(root, file))
    return JSONResponse(content={"images": images})

@router.post("/slideshow/config")
async def update_slideshow_config(request: Request):
    data = await request.json()
    cfg = load_config()
    cfg["slideshow"] = data
    save_config(cfg)
    return JSONResponse(content={"message": "Slideshow config updated."})

