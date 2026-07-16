"""
Add GWP Value per m² style to all ProgrammeProjects layers that are missing it.

Source: ProgrammeProjectsCCAR_CurrentYear (StyleId=1804, GroupName='GWPPerM2',
        StyleTitle='GWP Value per m²', DisplayOrder=18, IsIncluded=1)

Safe to re-run — skips layers that already have the GWPPerM2 style.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "MapMakerDB.db")

GROUP_NAME = "GWPPerM2"
STYLE_TITLE = "GWP Value per m²"
DISPLAY_ORDER = 18
IS_INCLUDED = 1


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT msl.MapServerLayerId, msl.MapLayerName
        FROM MapServerLayers msl
        WHERE msl.MapLayerName LIKE 'ProgrammeProjects%'
          AND NOT EXISTS (
              SELECT 1 FROM MapServerLayerStyles s
              WHERE s.MapServerLayerId = msl.MapServerLayerId
                AND s.GroupName = ?
          )
        ORDER BY msl.MapLayerName
    """, (GROUP_NAME,))

    targets = cur.fetchall()

    if not targets:
        print("No layers to update — all ProgrammeProjects layers already have GWPPerM2.")
        conn.close()
        return

    print(f"Adding '{STYLE_TITLE}' style to {len(targets)} layer(s):")
    for msl_id, name in targets:
        cur.execute("""
            INSERT INTO MapServerLayerStyles
                (MapServerLayerId, GroupName, StyleTitle, DisplayOrder, IsIncluded)
            VALUES (?, ?, ?, ?, ?)
        """, (msl_id, GROUP_NAME, STYLE_TITLE, DISPLAY_ORDER, IS_INCLUDED))
        print(f"  [{msl_id}] {name}")

    conn.commit()
    conn.close()
    print(f"\nDone. {len(targets)} layer(s) updated.")


if __name__ == "__main__":
    main()
