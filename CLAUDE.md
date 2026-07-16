# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
python run.py
```

No build step required. Dependencies:

```bash
pip install -r requirements.txt
```

There are no automated tests (`pytest` is listed but no test files exist).

## External Path Dependencies

All external paths are configured in `app2/settings.py` and resolved via environment variables with sensible defaults:

| Variable | Default | Purpose |
|---|---|---|
| `PMS_MAPS_DIR` | `../pms-maps` | MapServer `.map` / `.layer` files |
| `PMS_JS_ROOT` | `../PmsJS2` | ExtJS frontend (not in git) |
| `PMS_WFS_URL` | `http://localhost:82/mapserver2/` | WFS introspection endpoint |

The unified SQLite database lives at `Database/MapMakerDB.db`.  
`app2/settings.get_mapmakerdb_path()` is the canonical way to get its path — it raises if the file is missing.

TFS checkout is attempted when writing generated files; it silently no-ops if `TF.exe` is absent.

## Architecture Overview

### Data flow

```
WFS service ──► wfs_to_db.py ──► MapMakerDB.db
                                      │
                          ┌───────────┼────────────────┐
                          ▼           ▼                 ▼
                   grid_from_db  layer_export.py   layer_window.py
                   (Jinja grids)  (portal JSONs)  (mapfile fragments)
                          │                             │
                     PmsJS2/                    pms-maps/mapfiles/generated/
```

### Module responsibilities

**`app2/controller.py` — `Controller`**  
Single source of truth for in-memory layer state: `active_layer`, `saved_columns`, `active_filters`, `active_sorters`, `active_mdata`. Reads from and writes to `MapMakerDB.db`. Emits `data_updated` and `filter_selected` PyQt5 signals to notify the UI. All DB writes use `save_layer_atomic()` which wraps everything in one SQLite transaction.

**`app2/main_window.py` — `MainWindowUIClass`**  
PyQt5 main window loaded from `QTFiles/layermaker.ui`. Composed from 6 UI mixins (see `app2/UI/`). Hosts three top-level tabs:
- **Mapfile** — mapfile wiring via `layer_generator/layer_window.py`
- **Grid** — column/filter/sorter/metadata editing via `Controller`
- **Layers** — portal tree, layer JSON export via `json_generator/`

**`grid_generator/grid_from_db.py` — `GridGenerator`**  
Reads `MapMakerDB.db` and renders Jinja2 templates from `grid_generator/templates/` to produce ExtJS grid JS (Model, Store, ViewModel, Grid). Output goes to `PmsJS2/`. Templates are: `main.template`, `columns.template`, `column_renderer.template`, `filters.template`, `fields.template`.

**`json_generator/layer_export.py`**  
Exports portal-scoped layer JSON files (`default.json`, `editor.json`, `tree.json`, etc.) consumed by the frontend. Export output: `json_generator/app_jsons/`. Production JSONs live in `PmsJS2/resources/data/layers/` and are NOT managed by this repo's git.

**`json_generator/db_access.py` — `DBAccess`**  
Read-only query class for the LayerConfig side of `MapMakerDB.db` (portals, portal trees, switch layers, service layers).

**`app2/wfs_to_db.py` — `WFSToDB`**  
Imports layer schemas from a live WFS endpoint into `MapMakerDB.db` (creates `MapServerLayers`, `ServiceLayers`, and `GridColumns` rows). `sync_new_columns()` adds missing columns without touching existing ones.

**`layer_generator/layer_window.py` — `MapfileWiring`**  
Reads SQL Server views (via `pyodbc` Trusted Connection) to populate schema/column combos, then renders `.layer` mapfile fragments via Jinja2 into `pms-maps/mapfiles/generated/`.

### Key DB tables

- `Layers` — canonical layer registry; `Name` is the join key used everywhere
- `MapServerLayers` / `ServiceLayers` — WMS/WFS service registrations; `BaseLayerKey` → WMS/WFS key suffix
- `GridColumns` / `GridMData` / `GridSorters` — grid configuration per layer
- `GridFilterDefinitions` / `GridFilterTypes` / `BooleanOptions` — filter metadata (shared, referenced by FK from `GridColumns`)
- `Portals` / `PortalLayers` / `PortalSwitchLayers` — portal membership and tree structure
- `GridColumnRenderers` / `EditorRoles` — lookup tables for renderer type and edit role

Join key: `Layers.Name == MapServerLayers.MapLayerName` (126 of 137 layers linked; 11 report/schedule layers have no WFS equivalent — expected).

### UI mixin pattern

`MainWindowUIClass` inherits from all six mixins plus the uic-loaded base. Each mixin is a stateless helper that takes `owner` (the main window) as a parameter rather than using `self` for UI widget access. This avoids MRO conflicts when mixing uic-loaded classes.

## Working Style

**Plans:** When asked to create a plan, write the plan file and stop — do not begin implementation. Wait for an explicit go-ahead before touching any code.

**Plan filenames:** Use a short descriptive kebab-case name that reflects the task (e.g. `plan-add-orderby-support.md`, `plan-migrate-portal-tree.md`). Do not use random IDs, timestamps, or generic names like `plan.md`. If in doubt, consult with the user.

**Commits:** Only commit when explicitly asked to. Do not offer to commit after completing a task.

## Generating Outputs

**Grid JS for one layer (CLI):**
```bash
python -c "
from grid_generator.grid_from_db import GridGenerator
from app2.settings import get_mapmakerdb_path, PMS_JS_ROOT
g = GridGenerator('.', str(PMS_JS_ROOT))
g.generate_grid('<LayerName>', str(get_mapmakerdb_path()))
"
```

**Portal JSON export:** use the "Tree JSONs" sub-tab in the Layers tab, or call `json_generator.layer_export` directly.
