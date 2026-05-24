"""FastMCP server exposing GitHub Dev Card tools."""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP

BACKEND_DIR = Path(__file__).resolve().parent

# Load environment variables, trying both the backend folder and parent/root folder
load_dotenv(dotenv_path=BACKEND_DIR / ".env")
load_dotenv(dotenv_path=BACKEND_DIR.parent / ".env")

mcp = FastMCP("github-card-generator")

GITHUB_API = "https://api.github.com"
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)

STATIC_DIR = Path(__file__).parent / "static" / "cards"
STATIC_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Tool 1: scrape_github
# ---------------------------------------------------------------------------
@mcp.tool()
async def scrape_github(username: str) -> dict[str, Any]:
    """Fetch a public GitHub profile + top repos + aggregated languages."""
    headers = {"Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
        user_resp = await client.get(f"{GITHUB_API}/users/{username}")
        user_resp.raise_for_status()
        user = user_resp.json()

        repos_resp = await client.get(
            f"{GITHUB_API}/users/{username}/repos",
            params={"per_page": 100, "sort": "updated", "type": "owner"},
        )
        repos_resp.raise_for_status()
        repos = repos_resp.json()

    repos_sorted = sorted(
        [r for r in repos if not r.get("fork")],
        key=lambda r: r.get("stargazers_count", 0),
        reverse=True,
    )
    top_repos = [
        {
            "name": r["name"],
            "stars": r.get("stargazers_count", 0),
            "language": r.get("language"),
            "description": r.get("description") or "",
            "url": r.get("html_url"),
        }
        for r in repos_sorted[:6]
    ]

    lang_counter: Counter[str] = Counter()
    for r in repos_sorted:
        lang = r.get("language")
        if lang:
            lang_counter[lang] += 1
    top_languages = [lang for lang, _ in lang_counter.most_common(5)]

    return {
        "username": user.get("login", username),
        "name": user.get("name") or user.get("login", username),
        "bio": user.get("bio") or "",
        "location": user.get("location") or "",
        "avatar_url": user.get("avatar_url", ""),
        "public_repos": user.get("public_repos", 0),
        "followers": user.get("followers", 0),
        "following": user.get("following", 0),
        "html_url": user.get("html_url", ""),
        "top_repos": top_repos,
        "top_languages": top_languages,
    }


# ---------------------------------------------------------------------------
# Tool 2: analyze_profile
# ---------------------------------------------------------------------------
@mcp.tool()
async def analyze_profile(github_data: dict[str, Any]) -> dict[str, Any]:
    """Use Gemini 2.5 Flash to extract a developer 'vibe' + theme."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return fallback_analysis(github_data)

    prompt = (
        "You are profiling a developer from their GitHub data. "
        "Return STRICT JSON only (no markdown fences) with this shape:\n"
        "{\n"
        '  "developer_vibe": "one-sentence personality summary",\n'
        '  "top_skills": ["skill1", "skill2", "skill3"],\n'
        '  "fun_fact": "a clever insight inferred from their repos",\n'
        '  "card_theme": "hacker" | "builder" | "researcher" | "designer" | "open-source-hero"\n'
        "}\n\n"
        f"GitHub data:\n{json.dumps(github_data, indent=2)}"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "responseMimeType": "application/json",
        },
    }

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                GEMINI_URL,
                params={"key": api_key},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        return fallback_analysis(github_data)

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Gemini response: {data}") from e

    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        analysis = json.loads(cleaned)
    except json.JSONDecodeError:
        return fallback_analysis(github_data)

    valid_themes = {"hacker", "builder", "researcher", "designer", "open-source-hero"}
    if analysis.get("card_theme") not in valid_themes:
        analysis["card_theme"] = "builder"
    return analysis


# ---------------------------------------------------------------------------
# Tool 3: generate_card_html
# ---------------------------------------------------------------------------
THEMES = {
    "hacker": {"bg": "#0a0f0a", "fg": "#22ff88", "accent": "#22ff88", "muted": "#7fae8b", "font": "ui-monospace, Menlo, monospace"},
    "builder": {"bg": "#eaf2ff", "fg": "#111827", "accent": "#2563eb", "muted": "#6b7280", "font": "ui-sans-serif, system-ui, sans-serif"},
    "researcher": {"bg": "#0f172a", "fg": "#e2e8f0", "accent": "#a78bfa", "muted": "#94a3b8", "font": "Georgia, 'Times New Roman', serif"},
    "designer": {"bg": "#fff0f5", "fg": "#1f1235", "accent": "#ec4899", "muted": "#7c5e8a", "font": "'Helvetica Neue', Helvetica, Arial, sans-serif"},
    "open-source-hero": {"bg": "#1a1209", "fg": "#fde68a", "accent": "#f59e0b", "muted": "#c4a572", "font": "ui-sans-serif, system-ui, sans-serif"},
}


def fallback_analysis(github_data: dict[str, Any]) -> dict[str, Any]:
    """Build a useful profile analysis when Gemini is unavailable."""
    languages = github_data.get("top_languages") or []
    repos = github_data.get("top_repos") or []
    skills = languages[:3]
    if len(skills) < 3:
        skills.extend(["Open Source", "GitHub", "Software Engineering"][: 3 - len(skills)])

    public_repos = int(github_data.get("public_repos") or 0)
    followers = int(github_data.get("followers") or 0)
    theme = "builder"
    if languages and languages[0] in {"HTML", "CSS", "Vue", "Svelte"}:
        theme = "designer"
    elif languages and languages[0] in {"Jupyter Notebook", "R", "Julia", "MATLAB"}:
        theme = "researcher"
    elif followers >= 1000 or public_repos >= 75:
        theme = "open-source-hero"
    elif languages and languages[0] in {"Shell", "C", "C++", "Rust", "Go"}:
        theme = "hacker"

    top_repo = repos[0]["name"] if repos else "public projects"
    name = github_data.get("name") or github_data.get("username") or "This developer"

    return {
        "developer_vibe": (
            f"{name} looks like a {theme.replace('-', ' ')} who ships practical work "
            f"across {', '.join(languages[:3]) if languages else 'multiple areas'}."
        ),
        "top_skills": skills,
        "fun_fact": f"The standout repository is {top_repo}, which helps anchor the profile's technical style.",
        "card_theme": theme,
    }


def _esc(s: Any) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


@mcp.tool()
async def generate_card_html(
    username: str, github_data: dict[str, Any], analysis: dict[str, Any]
) -> str:
    """Render a self-contained HTML dev card."""
    theme_key = analysis.get("card_theme", "builder")
    t = THEMES.get(theme_key, THEMES["builder"])

    skills = analysis.get("top_skills", []) or []
    skills_html = "".join(
        f'<span class="badge">{_esc(s)}</span>' for s in skills
    )

    top3 = (github_data.get("top_repos") or [])[:3]
    repos_html = "".join(
        f"""
        <a class="repo" href="{_esc(r.get('url', '#'))}" target="_blank" rel="noopener">
          <div class="repo-name">{_esc(r.get('name', ''))}</div>
          <div class="repo-desc">{_esc(r.get('description', ''))}</div>
          <div class="repo-meta">
            <span>★ {_esc(r.get('stars', 0))}</span>
            <span>{_esc(r.get('language') or '—')}</span>
          </div>
        </a>
        """
        for r in top3
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>{_esc(github_data.get('name', username))} · Dev Card</title>
<style>
  :root {{
    --bg: {t['bg']}; --fg: {t['fg']}; --accent: {t['accent']}; --muted: {t['muted']};
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; min-height: 100vh; display: grid; place-items: center;
    background: var(--bg); color: var(--fg); font-family: {t['font']}; padding: 2rem;
  }}
  .card {{
    width: min(560px, 100%); background: color-mix(in oklab, var(--bg) 92%, var(--fg) 8%);
    border: 1px solid color-mix(in oklab, var(--fg) 18%, transparent);
    border-radius: 18px; padding: 2rem; box-shadow: 0 24px 60px rgba(0,0,0,.25);
  }}
  .head {{ display: flex; gap: 1.25rem; align-items: center; }}
  .avatar {{
    width: 84px; height: 84px; border-radius: 50%; object-fit: cover;
    border: 2px solid var(--accent);
  }}
  h1 {{ margin: 0; font-size: 1.5rem; }}
  .handle {{ color: var(--muted); font-size: .95rem; }}
  .theme-tag {{
    display: inline-block; margin-top: .35rem; padding: .15rem .55rem;
    border-radius: 999px; background: var(--accent); color: var(--bg);
    font-size: .72rem; text-transform: uppercase; letter-spacing: .08em;
  }}
  .vibe {{ margin: 1.25rem 0 1rem; font-size: 1.05rem; line-height: 1.5; }}
  .badges {{ display: flex; flex-wrap: wrap; gap: .4rem; margin-bottom: 1rem; }}
  .badge {{
    padding: .25rem .65rem; border-radius: 999px;
    background: color-mix(in oklab, var(--accent) 18%, transparent);
    color: var(--fg); font-size: .8rem;
    border: 1px solid color-mix(in oklab, var(--accent) 40%, transparent);
  }}
  .stats {{ display: flex; gap: 1.5rem; margin: 1rem 0; color: var(--muted); font-size: .9rem; }}
  .stats b {{ color: var(--fg); font-size: 1.1rem; display: block; }}
  .fun {{
    font-style: italic; color: var(--muted); border-left: 3px solid var(--accent);
    padding-left: .75rem; margin: 1rem 0;
  }}
  .repos {{ display: grid; gap: .6rem; margin-top: 1rem; }}
  .repo {{
    display: block; padding: .75rem .9rem; border-radius: 10px; text-decoration: none;
    color: var(--fg);
    background: color-mix(in oklab, var(--fg) 5%, transparent);
    border: 1px solid color-mix(in oklab, var(--fg) 12%, transparent);
  }}
  .repo:hover {{ border-color: var(--accent); }}
  .repo-name {{ font-weight: 600; }}
  .repo-desc {{ color: var(--muted); font-size: .85rem; margin: .15rem 0 .35rem; }}
  .repo-meta {{ display: flex; gap: 1rem; font-size: .78rem; color: var(--muted); }}
  footer {{ margin-top: 1.25rem; font-size: .75rem; color: var(--muted); text-align: center; }}
</style>
</head>
<body>
  <main class="card">
    <div class="head">
      <img class="avatar" src="{_esc(github_data.get('avatar_url', ''))}" alt="{_esc(username)} avatar" />
      <div>
        <h1>{_esc(github_data.get('name', username))}</h1>
        <div class="handle">@{_esc(username)}{f" · {_esc(github_data.get('location'))}" if github_data.get('location') else ''}</div>
        <span class="theme-tag">{_esc(theme_key)}</span>
      </div>
    </div>

    <p class="vibe">{_esc(analysis.get('developer_vibe', ''))}</p>

    <div class="badges">{skills_html}</div>

    <div class="stats">
      <div><b>{_esc(github_data.get('public_repos', 0))}</b>repos</div>
      <div><b>{_esc(github_data.get('followers', 0))}</b>followers</div>
      <div><b>{_esc(len(github_data.get('top_languages', [])))}</b>languages</div>
    </div>

    <div class="fun">💡 {_esc(analysis.get('fun_fact', ''))}</div>

    <div class="repos">{repos_html}</div>

    <footer>Generated by GitHub Dev Card Generator</footer>
  </main>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Tool 4: save_card
# ---------------------------------------------------------------------------
@mcp.tool()
async def save_card(username: str, html: str) -> str:
    """Persist the card HTML and return its relative URL path."""
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", username)
    path = STATIC_DIR / f"{safe}.html"
    path.write_text(html, encoding="utf-8")
    return f"/static/cards/{safe}.html"


if __name__ == "__main__":
    mcp.run()
