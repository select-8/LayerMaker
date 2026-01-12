import sqlite3
import re
from pathlib import Path

# Edit these three only
DB_PATH = Path(r"C:\DevOps\LayerMaker\Database\MapMakerDB.db")
PORTAL_KEY = "tii_default"
PORTAL_MAPFILE_PATH = Path(r"C:\DevOps\pms-maps\mapfiles\portals\tii.map")

# Mapfile INCLUDE lines, captures the quoted path
INCLUDE_RE = re.compile(r'^\s*INCLUDE\s+"([^"]+\.layer)"\s*$', re.MULTILINE | re.IGNORECASE)

# Reads NAME "SomeLayerName" inside a .layer file
LAYER_NAME_RE = re.compile(r'^\s*NAME\s+"([^"]+)"\s*$', re.MULTILINE | re.IGNORECASE)

def extract_layer_name(layer_file_path: Path) -> str:
    text = layer_file_path.read_text(encoding="utf-8", errors="strict")
    m = LAYER_NAME_RE.search(text)
    if not m:
        raise RuntimeError(f'Could not find NAME "..." in layer file: {layer_file_path}')
    return m.group(1).strip()

def main():
    map_text = PORTAL_MAPFILE_PATH.read_text(encoding="utf-8", errors="strict")
    include_rel_paths = INCLUDE_RE.findall(map_text)

    if not include_rel_paths:
        raise RuntimeError(f"No INCLUDE lines found in mapfile: {PORTAL_MAPFILE_PATH}")

    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()

        # Resolve PortalId from PortalKey
        cur.execute("SELECT PortalId FROM Portals WHERE PortalKey = ?", (PORTAL_KEY,))
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f"PortalKey not found in Portals table: {PORTAL_KEY}")
        portal_id = row[0]

        # Basic sanity: ensure expected columns exist
        cur.execute("PRAGMA table_info(Layers)")
        layer_cols = {r[1] for r in cur.fetchall()}
        if "LayerFileRelPath" not in layer_cols:
            raise RuntimeError("Layers.LayerFileRelPath does not exist. Run schema migration first.")

        missing_files = []
        created_layers = 0
        updated_paths = 0
        inserted_memberships = 0

        for include_rel in include_rel_paths:
            # Mapfiles use relative paths, resolve to absolute on disk
            layer_abs = (PORTAL_MAPFILE_PATH.parent / include_rel).resolve()

            if not layer_abs.exists():
                missing_files.append(str(layer_abs))
                continue

            layer_name = extract_layer_name(layer_abs)

            # Find canonical layer row by Name (this is now authoritative)
            cur.execute("SELECT LayerId, LayerFileRelPath FROM Layers WHERE Name = ?", (layer_name,))
            row = cur.fetchone()

            if row:
                layer_id, existing_rel = row
                # If path missing, set it. If different, overwrite (you can change this to warn instead).
                if existing_rel != include_rel:
                    cur.execute(
                        "UPDATE Layers SET LayerFileRelPath = ? WHERE LayerId = ?",
                        (include_rel, layer_id),
                    )
                    updated_paths += 1
            else:
                # Create new layer record with the NAME from the layer file
                cur.execute(
                    "INSERT INTO Layers (Name, LayerFileRelPath) VALUES (?, ?)",
                    (layer_name, include_rel),
                )
                layer_id = cur.lastrowid
                created_layers += 1

            # Insert portal membership
            cur.execute(
                "INSERT OR IGNORE INTO LayerPortals (LayerId, PortalId) VALUES (?, ?)",
                (layer_id, portal_id),
            )
            if cur.rowcount == 1:
                inserted_memberships += 1

        conn.commit()

    print(f"Mapfile: {PORTAL_MAPFILE_PATH}")
    print(f"PortalKey: {PORTAL_KEY}")
    print(f"Includes found: {len(include_rel_paths)}")
    print(f"New Layers created: {created_layers}")
    print(f"Layers paths updated: {updated_paths}")
    print(f"New LayerPortals rows: {inserted_memberships}")

    if missing_files:
        print("Missing .layer files (check PMS_MAPS_DIR / relative paths):")
        for p in missing_files:
            print(p)

if __name__ == "__main__":
    main()
