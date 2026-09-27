from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import models
from .database import engine, run_light_migrations
from .routers import rooms, teams, mission, admin, leaderboard
from .content import MODEL_INFO, METRIC_INFO, ACHIEVEMENTS

models.Base.metadata.create_all(bind=engine)
run_light_migrations()

app = FastAPI(title="ML Forge API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rooms.router)
app.include_router(teams.router)
app.include_router(mission.router)
app.include_router(admin.router)
app.include_router(leaderboard.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/reference")
def reference():
    """Static reference info the frontend uses to render the inventory
    panel: model descriptions, metric descriptions, achievement list."""
    return {"models": MODEL_INFO, "metrics": METRIC_INFO, "achievements": ACHIEVEMENTS}


# ---------------------------------------------------------------------------
# Serve the built React app (frontend/dist) from this same process, so there
# is exactly one server and one URL both on Render/Vercel and on the LAN.
# Mounted last so it never shadows the /api/* routes above. If the frontend
# hasn't been built yet (e.g. running the backend alone in dev against the
# Vite dev server), this is skipped rather than erroring.
# ---------------------------------------------------------------------------
_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
