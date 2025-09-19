import sqlite3
import yaml
import os

# Resolve paths
this_dir = os.path.dirname(__file__)
layers_yaml_path = os.path.abspath(os.path.join(this_dir, "layers.yaml"))
schema_path = os.path.abspath(os.path.join(this_dir, "schema.sql"))
db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Database", "MapMakerDB.db"))

def import_layer_names(layers_yaml_path, db_path):
    with open(layers_yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    layer_names = data.get("layers", [])
    if not isinstance(layer_names, list):
        raise ValueError("Expected 'layers' key to be a list.")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.executescript("""
DROP TABLE IF EXISTS Layers;
DROP TABLE IF EXISTS GridMData;
DROP TABLE IF EXISTS GridColumns;
DROP TABLE IF EXISTS GridColumnEdit;
DROP TABLE IF EXISTS GridSorters;
DROP TABLE IF EXISTS GridFilterDefinitions;
""")
    conn.commit()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Layers (
        LayerId INTEGER PRIMARY KEY AUTOINCREMENT,
        Name TEXT NOT NULL UNIQUE
    )
    """)

    for name in layer_names:
        if isinstance(name, str):
            cursor.execute("INSERT OR IGNORE INTO Layers (Name) VALUES (?)", (name,))

    conn.commit()
    conn.close()
    print(f"Imported {len(layer_names)} layer names into {db_path}")

# Step 1: Import known layers
import_layer_names(layers_yaml_path, db_path)

# Step 2: Load schema
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
with open(schema_path, "r", encoding="utf-8") as f:
    schema_sql = f.read()
cursor.executescript(schema_sql)
