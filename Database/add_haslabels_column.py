"""
Add HasLabels column to MapServerLayers.

Controls whether a layer emits a labelClassName (WMS) / labelRule (WFS) entry
during portal JSON export. Defaults to 1 so every existing layer keeps
behaving exactly as it does today — no data backfill needed.

Safe to re-run — skips if the column already exists.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "MapMakerDB.db")


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(MapServerLayers)")
    existing_columns = {row[1] for row in cur.fetchall()}

    if "HasLabels" in existing_columns:
        print("HasLabels column already exists — nothing to do.")
        conn.close()
        return

    cur.execute("ALTER TABLE MapServerLayers ADD COLUMN HasLabels INTEGER NOT NULL DEFAULT 1")
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM MapServerLayers")
    total = cur.fetchone()[0]
    conn.close()
    print(f"Added HasLabels column. {total} row(s) default to HasLabels=1.")


if __name__ == "__main__":
    main()
