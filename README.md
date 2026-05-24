# GitHub Dev Card Generator

Stack: FastMCP, Gemini 2.5 Flash, FastAPI, HTML, Cloud Run.

## Local dev (with uv)

```bash
cd backend
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
cp ../.env.example ../.env  # optional: add GOOGLE_API_KEY for AI analysis
python main.py
```

Open `frontend/index.html` in a browser, or run everything together:

```bash
docker compose up --build
# frontend: http://localhost:3000
# backend:  http://localhost:8080
```

## Deploy to Cloud Run

```bash
gcloud run deploy card-backend  --source ./backend  --region us-central1 --allow-unauthenticated
gcloud run deploy card-frontend --source ./frontend --region us-central1 --allow-unauthenticated
```
