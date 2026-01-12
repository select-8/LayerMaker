"""Central configuration for external paths and service endpoints."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PROJECT_ROOT.parent
DEFAULT_DEVOPS_ROOT = REPO_ROOT.parent

PMS_MAPS_DIR = Path(os.environ.get("PMS_MAPS_DIR", DEFAULT_DEVOPS_ROOT / "pms-maps")).resolve()
PMS_JS_ROOT = Path(os.environ.get("PMS_JS_ROOT", DEFAULT_DEVOPS_ROOT / "PmsJS2")).resolve()
WFS_URL = os.environ.get("PMS_WFS_URL", "http://localhost:82/mapserver2/")
WFS_CONNECT_TIMEOUT = int(os.environ.get("PMS_WFS_CONNECT_TIMEOUT", "45"))
WFS_READ_TIMEOUT = int(os.environ.get("PMS_WFS_READ_TIMEOUT", "180"))
WFS_RETRY_ATTEMPTS = int(os.environ.get("PMS_WFS_RETRY_ATTEMPTS", "3"))
WFS_RETRY_BACKOFF = float(os.environ.get("PMS_WFS_RETRY_BACKOFF", "1.5"))

QTFILES_DIR = REPO_ROOT / "QTFiles"
LAYERMAKER_UI_PATH = QTFILES_DIR / "LayerMaker_Manual_redo_fixed_aligned3_toplevel_tabs.ui"

MAPFILES_DIR = PMS_MAPS_DIR / "mapfiles" / "generated"

MAPMAKERDB_DIR = REPO_ROOT / "Database"


def get_mapmakerdb_path() -> Path:
    """
    Return the canonical MapMaker SQLite DB path.
    """
    db = (MAPMAKERDB_DIR / "MapMakerDB.db").resolve()
    if not db.exists():
        raise FileNotFoundError(f"Expected MapMaker DB at: {db}")
    return db