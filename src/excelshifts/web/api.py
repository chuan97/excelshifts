from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Compute project root as: src/excelshifts/web/api.py -> go up 3 levels
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parents[2]
STATIC_DIR = PROJECT_ROOT / "static"

app = FastAPI()

# Serve /static/* from the static/ directory
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Serve the main HTML page."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/ping")
def ping() -> JSONResponse:
    """Simple health check endpoint."""
    return JSONResponse({"status": "ok"})
