import sqlite3
from pathlib import Path

# Edit these
DB_PATH = Path(r"C:\DevOps\LayerMaker\Database\MapMakerDB.db")
MAPFILES = [
    ("default", Path(r"C:\DevOps\pms-maps\mapfiles\generated\tipperary.map")),
    # ("editor", Path(r"C:\DevOps\pms-maps\mapfiles\generated\editor.map")),
    # ("nta_default", Path(r"C:\DevOps\pms-maps\mapfiles\generated\nta.map")),
    # ("tii_default", Path(r"C:\DevOps\pms-maps\mapfiles\generated\tii.map")),
]

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

def _parse_name_value(rest: str) -> str | None:
    rest = rest.strip()
    if not rest:
        return None
    if rest.startswith('"'):
        end = rest.find('"', 1)
        if end == -1:
            return None
        return rest[1:end].strip()
    # Unquoted token
    return rest.split()[0].strip()

def extract_layer_names(mapfile_path: Path) -> set[str]:
    if not mapfile_path.exists():
        raise FileNotFoundError(f"Mapfile not found: {mapfile_path}")

    stack: list[str] = []
    layer_names: set[str] = set()

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

        # Only capture NAME when directly inside a LAYER block
        if kw == "NAME" and stack and stack[-1] == "LAYER":
            name = _parse_name_value(rest)
            if name:
                layer_names.add(name)
    print(len(layer_names))
    for n in sorted(layer_names):
        print(f"Found layer: {n}")
    return layer_names

def main():
    # with sqlite3.connect(str(DB_PATH)) as conn:
    #     cur = conn.cursor()

    #     # Per-portal layer names (what each portal mapfile defines)
    #     cur.execute("""
    #     CREATE TABLE IF NOT EXISTS PortalMapLayers (
    #         PortalKey TEXT NOT NULL,
    #         LayerName TEXT NOT NULL,
    #         SourceMapfile TEXT NOT NULL,
    #         PRIMARY KEY (PortalKey, LayerName)
    #     )
    #     """)

    #     # Union of all unique layer names across portals
    #     cur.execute("""
    #     CREATE TABLE IF NOT EXISTS CanonicalMapLayers (
    #         LayerName TEXT PRIMARY KEY
    #     )
    #     """)

    #     # Refresh (simple approach)
    #     cur.execute("DELETE FROM PortalMapLayers")
    #     cur.execute("DELETE FROM CanonicalMapLayers")

        total_inserted = 0
        for portal_key, mapfile_path in MAPFILES:
            names = extract_layer_names(mapfile_path)
    #         for n in names:
    #             cur.execute(
    #                 "INSERT OR IGNORE INTO PortalMapLayers (PortalKey, LayerName, SourceMapfile) VALUES (?, ?, ?)",
    #                 (portal_key, n, str(mapfile_path)),
    #             )
    #             cur.execute(
    #                 "INSERT OR IGNORE INTO CanonicalMapLayers (LayerName) VALUES (?)",
    #                 (n,),
    #             )
    #         total_inserted += len(names)

    #     conn.commit()

    # print(f"Inserted portal layer name rows (pre-dedupe): {total_inserted}")
    # print("Tables written: PortalMapLayers, CanonicalMapLayers")

if __name__ == "__main__":
    main()
