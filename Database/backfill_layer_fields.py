"""
Backfill MapServerLayerFields for all existing layers that have GridColumns entries
but no corresponding MapServerLayerFields row.

FieldType is derived from GridColumnRenderers.ExType:
    string  -> string
    number  -> integer
    float   -> double
    boolean -> boolean
    date    -> timeinstanttype
    (anything else) -> string

Run from the project root:
    python Database/backfill_layer_fields.py
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "MapMakerDB.db")

_EXTYPE_TO_FIELDTYPE = {
    "string":  "string",
    "number":  "integer",
    "float":   "double",
    "boolean": "boolean",
    "date":    "timeinstanttype",
}


def backfill(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT
                msl.MapServerLayerId,
                msl.MapLayerName,
                gc.ColumnName,
                gc.DisplayOrder,
                r.ExType
            FROM MapServerLayers msl
            JOIN Layers l ON l.Name = msl.MapLayerName
            JOIN GridColumns gc ON gc.LayerId = l.LayerId
            LEFT JOIN GridColumnRenderers r ON r.GridColumnRendererId = gc.GridColumnRendererId
            WHERE NOT EXISTS (
                SELECT 1 FROM MapServerLayerFields mf
                WHERE mf.MapServerLayerId = msl.MapServerLayerId
                  AND mf.FieldName = gc.ColumnName
            )
            ORDER BY msl.MapLayerName, COALESCE(gc.DisplayOrder, 9999), gc.ColumnName
        """)

        rows = cur.fetchall()
        print(f"Found {len(rows)} fields to backfill across all layers.")

        inserted = 0
        for row in rows:
            field_type = _EXTYPE_TO_FIELDTYPE.get((row["ExType"] or "").lower(), "string")
            cur.execute("""
                INSERT INTO MapServerLayerFields
                    (MapServerLayerId, FieldName, FieldType, IncludeInPropertyCsv, IsIdProperty, DisplayOrder)
                VALUES (?, ?, ?, 1, 0, ?)
            """, (
                row["MapServerLayerId"],
                row["ColumnName"],
                field_type,
                row["DisplayOrder"] if row["DisplayOrder"] is not None else 0,
            ))
            inserted += 1

        conn.commit()
        print(f"Inserted {inserted} MapServerLayerFields rows.")
    finally:
        conn.close()


if __name__ == "__main__":
    backfill(DB_PATH)
