import sqlite3
from pathlib import Path

# Edit these
DB_PATH = Path(r"C:\DevOps\LayerMaker\Database\MapMakerDB.db")
PORTAL_MAPFILES = [
    ("default", Path(r"C:\DevOps\pms-maps\mapfiles\generated\tipperary.map")),
    ("editor", Path(r"C:\DevOps\pms-maps\mapfiles\generated\editor.map")),
    ("nta_default", Path(r"C:\DevOps\pms-maps\mapfiles\generated\nta.map")),
    ("tii_default", Path(r"C:\DevOps\pms-maps\mapfiles\generated\tii.map")),
]

# Minimal MapServer-ish parser: grab NAME tokens only when we're inside a LAYER block.
BEGIN_BLOCKS = {
    "MAP", "LAYER", "CLASS", "STYLE", "WEB", "METADATA", "PROJECTION", "OUTPUTFORMAT",
    "LEGEND", "SCALEBAR", "QUERYMAP", "REFERENCE", "SYMBOL", "LABEL", "FEATURE",
    "COMPOSITE", "VALIDATION", "CLUSTER", "JOIN", "GRID", "CONFIG"
}

def _strip_inline_comment(line: str) -> str:
    # MapServer uses # for comments
    if "#" in line:
        line = line.split("#", 1)[0]
    return line.strip()

def _parse_value(rest: str) -> str | None:
    rest = rest.strip()
    if not rest:
        return None
    if rest.startswith('"'):
        end = rest.find('"', 1)
        if end == -1:
            return None
        return rest[1:end].strip()
    return rest.split()[0].strip()

def extract_layer_names_from_mapfile(mapfile_path: Path) -> set[str]:
    if not mapfile_path.exists():
        raise FileNotFoundError(f"Mapfile not found: {mapfile_path}")

    stack: list[str] = []
    out: set[str] = set()

    for raw in mapfile_path.read_text(encoding="utf-8", errors="strict").splitlines():
        line = _strip_inline_comment(raw)
        if not line:
            continue

        parts = line.split(None, 1)
        kw = parts[0].upper()
        rest = parts[1] if len(parts) > 1 else ""

        if kw in BEGIN_BLOCKS:
            stack.append(kw)
            continue

        if kw == "END":
            if stack:
                stack.pop()
            continue

        if kw == "NAME" and stack and stack[-1] == "LAYER":
            name = _parse_value(rest)
            if name:
                out.add(name)

    return out

def fetch_db_sets(conn: sqlite3.Connection):
    cur = conn.cursor()

    cur.execute("SELECT Name FROM Layers")
    db_layer_names = {r[0] for r in cur.fetchall()}

    # Portal membership according to DB (LayerPortals)
    cur.execute("""
        SELECT p.PortalKey, l.Name
        FROM LayerPortals lp
        JOIN Portals p ON p.PortalId = lp.PortalId
        JOIN Layers l ON l.LayerId = lp.LayerId
    """)
    portal_db_membership: dict[str, set[str]] = {}
    for portal_key, layer_name in cur.fetchall():
        portal_db_membership.setdefault(portal_key, set()).add(layer_name)

    return db_layer_names, portal_db_membership

def main():
    with sqlite3.connect(str(DB_PATH)) as conn:
        # Make FK violations visible for future work (does not fix existing data)
        conn.execute("PRAGMA foreign_keys = ON;")

        db_layer_names, portal_db_membership = fetch_db_sets(conn)

    # Mapfile layer names per portal
    portal_mapfile_layers: dict[str, set[str]] = {}
    for portal_key, map_path in PORTAL_MAPFILES:
        portal_mapfile_layers[portal_key] = extract_layer_names_from_mapfile(map_path)

    # Report per portal
    print("=== Per-portal comparison: mapfile vs Layers table (global) ===")
    for portal_key, _ in PORTAL_MAPFILES:
        mf = portal_mapfile_layers.get(portal_key, set())

        missing_in_layers_table = sorted(mf - db_layer_names)
        print(f"\nPortal: {portal_key}")
        print(f"  Mapfile layer names: {len(mf)}")
        print(f"  Missing in Layers table: {len(missing_in_layers_table)}")
        for n in missing_in_layers_table:
            print(f"    - {n}")

    print("\n=== Per-portal comparison: mapfile vs LayerPortals (membership) ===")
    for portal_key, _ in PORTAL_MAPFILES:
        mf = portal_mapfile_layers.get(portal_key, set())
        dbm = portal_db_membership.get(portal_key, set())

        missing_in_db_membership = sorted(mf - dbm)
        extra_in_db_membership = sorted(dbm - mf)

        print(f"\nPortal: {portal_key}")
        print(f"  Mapfile layer names: {len(mf)}")
        print(f"  DB membership (LayerPortals): {len(dbm)}")

        print(f"  In mapfile but NOT in DB membership: {len(missing_in_db_membership)}")
        for n in missing_in_db_membership:
            print(f"    - {n}")

        print(f"  In DB membership but NOT in mapfile: {len(extra_in_db_membership)}")
        for n in extra_in_db_membership:
            print(f"    - {n}")

    # Global: layers in DB that are in none of the 4 mapfiles
    union_mapfile_names = set().union(*portal_mapfile_layers.values()) if portal_mapfile_layers else set()
    global_extra_in_layers = sorted(db_layer_names - union_mapfile_names)

    print("\n=== Global comparison: Layers table vs union of the 4 portal mapfiles ===")
    print(f"  Unique layers in DB (Layers): {len(db_layer_names)}")
    print(f"  Unique layers in mapfiles (union): {len(union_mapfile_names)}")
    print(f"  In DB but in NONE of the 4 mapfiles: {len(global_extra_in_layers)}")
    for n in global_extra_in_layers:
        print(f"    - {n}")

if __name__ == "__main__":
    main()
