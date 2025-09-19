"""Central configuration for external paths and service endpoints."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PROJECT_ROOT.parent
DEFAULT_DEVOPS_ROOT = REPO_ROOT.parent / "DevOps"

PMS_MAPS_DIR = Path(os.environ.get("PMS_MAPS_DIR", DEFAULT_DEVOPS_ROOT / "pms-maps")).resolve()
PMS_JS_ROOT = Path(os.environ.get("PMS_JS_ROOT", DEFAULT_DEVOPS_ROOT / "PmsJS2")).resolve()
WFS_URL = os.environ.get("PMS_WFS_URL", "http://localhost:81//mapserver2/")

MAPFILES_DIR = PMS_MAPS_DIR / "mapfiles" / "generated"
