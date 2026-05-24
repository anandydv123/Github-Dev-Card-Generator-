"""FastAPI app exposing the GitHub Dev Card generator."""
from __future__ import annotations

import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from mcp_server import analyze_profile, generate_card_html, save_card, scrape_github

BACKEND_DIR = Path(__file__).resolve().parent
CARDS_DIR = BACKEND_DIR / "static" / "cards"
CARDS_DIR.mkdir(parents=True, exist_ok=True)

# Load environment variables, trying both the backend folder and parent/root folder
load_dotenv(dotenv_path=BACKEND_DIR / ".env")
load_dotenv(dotenv_path=BACKEND_DIR.parent / ".env")

app = FastAPI(title="GitHub Dev Card Generator", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=BACKEND_DIR / "static"), name="static")


class CardRequest(BaseModel):
    username: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/generate")
async def generate(req: CardRequest):
    username = req.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="username is required")

    try:
        github_data = await scrape_github(username)
        analysis = await analyze_profile(github_data)
        card_html = await generate_card_html(username, github_data, analysis)
        card_url = await save_card(username, card_html)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail="GitHub user not found") from exc
        raise HTTPException(
            status_code=502,
            detail=f"GitHub API request failed ({exc.response.status_code})",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="Could not reach the GitHub API"
        ) from exc

    return JSONResponse(
        {
            "username": username,
            "card_url": card_url,
            "card_html": card_html,
            "analysis": analysis,
        }
    )


@app.get("/card/{username}")
async def get_card(username: str):
    safe = "".join(c for c in username if c.isalnum() or c in "_.-")
    if not safe:
        raise HTTPException(status_code=400, detail="invalid username")
    path = CARDS_DIR / f"{safe}.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="card not found")
    return FileResponse(path, media_type="text/html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        reload=False,
    )

