"""
Add Excluded column to PortalTreeNodes.

Lets a folder node (and, by extension, its whole subtree) be kept in the
tree editor and DB but omitted from exported tree JSON — useful for
in-progress folders that need to disappear from a release without losing
their configuration. Defaults to 0 so every existing node keeps behaving
exactly as it does today.

Safe to re-run — skips if the column already exists.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "MapMakerDB.db")


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(PortalTreeNodes)")
    existing_columns = {row[1] for row in cur.fetchall()}

    if "Excluded" in existing_columns:
        print("Excluded column already exists — nothing to do.")
        conn.close()
        return

    cur.execute("ALTER TABLE PortalTreeNodes ADD COLUMN Excluded INTEGER NOT NULL DEFAULT 0")
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM PortalTreeNodes")
    total = cur.fetchone()[0]
    conn.close()
    print(f"Added Excluded column. {total} row(s) default to Excluded=0.")


if __name__ == "__main__":
    main()
