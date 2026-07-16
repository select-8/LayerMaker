"""
Apply ProgrammeProjectsRI_CurrentYear grid config to all other 55 ProgrammeProjects layers.

Changes:
  GridMData  — IdField, GetId, Window, Model (all 55 layers)
  GridSorters — 1 row: ProgrammeProjectsRI_LastYear second sorter (GridSorterId=1897)
  GridColumns — DisplayOrder, Text, Hidden, Flex from RI_CurrentYear template (all 55 layers)
  GridColumns — INSERT ProjectLead for all 55 layers that don't have it
"""

import sqlite3
import sys

DB_PATH = r'C:\DevOps\LayerMaker\Database\MapMakerDB.db'
TEMPLATE_LAYER = 'ProgrammeProjectsRI_CurrentYear'
LASTYEAR_SORTER_ID = 1897  # GridSorterId for RI_LastYear's second sorter (still RoadsProgrammeId)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# ── 1. Load template column map from RI_CurrentYear ──────────────────────────
cur.execute(
    '''SELECT ColumnName, DisplayOrder, Text, Hidden, Flex,
              InGrid, NullText, NullValue, Zeros, NoFilter,
              CustomListValues, Editable, GridColumnRendererId,
              GridFilterDefinitionId, GridFilterTypeId, SortIndex, BooleanOptionId
       FROM GridColumns
       JOIN Layers ON Layers.LayerId = GridColumns.LayerId
       WHERE Layers.Name = ?''',
    (TEMPLATE_LAYER,)
)
template_cols = {r['ColumnName']: dict(r) for r in cur.fetchall()}
print(f'Loaded {len(template_cols)} columns from template ({TEMPLATE_LAYER})')

# ── 2. Get the 55 target LayerIds ─────────────────────────────────────────────
cur.execute(
    '''SELECT LayerId, Name FROM Layers
       WHERE Name LIKE "ProgrammeProjects%"
       AND Name != ?
       ORDER BY Name''',
    (TEMPLATE_LAYER,)
)
target_layers = [(r['LayerId'], r['Name']) for r in cur.fetchall()]
print(f'Target layers: {len(target_layers)}')

target_ids = [lid for lid, _ in target_layers]

# ── 3. GridMData — update IdField, GetId, Window, Model ──────────────────────
cur.execute(
    f'''UPDATE GridMData
        SET IdField = "CalculatedParentProjectId",
            GetId   = "CalculatedParentProjectId",
            Window  = "projects.ProjectsEditWindow",
            Model   = "projects.Project"
        WHERE LayerId IN ({",".join("?" * len(target_ids))})''',
    target_ids
)
print(f'GridMData updated: {cur.rowcount} rows')

# ── 4. GridSorters — fix RI_LastYear second sorter ───────────────────────────
cur.execute(
    'UPDATE GridSorters SET Property = "CalculatedParentProjectId" WHERE GridSorterId = ?',
    (LASTYEAR_SORTER_ID,)
)
print(f'GridSorters updated: {cur.rowcount} rows (RI_LastYear second sorter)')

# ── 5. GridColumns — bulk UPDATE per column per layer ─────────────────────────
col_updates = 0
for layer_id, layer_name in target_layers:
    for col_name, tmpl in template_cols.items():
        cur.execute(
            '''UPDATE GridColumns
               SET DisplayOrder = ?, Text = ?, Hidden = ?, Flex = ?
               WHERE LayerId = ? AND ColumnName = ?''',
            (tmpl['DisplayOrder'], tmpl['Text'], tmpl['Hidden'], tmpl['Flex'],
             layer_id, col_name)
        )
        col_updates += cur.rowcount
print(f'GridColumns updated: {col_updates} cell-updates across {len(target_layers)} layers')

# ── 6. GridColumns — INSERT ProjectLead where missing ────────────────────────
pl = template_cols.get('ProjectLead')
if not pl:
    print('ERROR: ProjectLead not found in template — aborting insert step', file=sys.stderr)
else:
    inserts = 0
    for layer_id, layer_name in target_layers:
        cur.execute(
            'SELECT 1 FROM GridColumns WHERE LayerId=? AND ColumnName="ProjectLead"',
            (layer_id,)
        )
        if cur.fetchone():
            continue
        cur.execute(
            '''INSERT INTO GridColumns
               (LayerId, ColumnName, DisplayOrder, Text, InGrid, Hidden,
                NullText, NullValue, Zeros, NoFilter, Flex,
                CustomListValues, Editable, GridColumnRendererId,
                GridFilterDefinitionId, GridFilterTypeId, SortIndex, BooleanOptionId)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (
                layer_id,
                'ProjectLead',
                pl['DisplayOrder'],  # 3
                pl['Text'],          # 'Project Lead'
                pl['InGrid'],        # 1
                pl['Hidden'],        # 0
                pl['NullText'],      # None
                pl['NullValue'],     # None
                pl['Zeros'],         # 0
                pl['NoFilter'],      # 0
                pl['Flex'],          # 0.3
                pl['CustomListValues'],   # None
                pl['Editable'],      # 0
                pl['GridColumnRendererId'],  # 1 (string)
                pl['GridFilterDefinitionId'],  # None
                pl['GridFilterTypeId'],  # 1 (string)
                pl['SortIndex'],     # None
                pl['BooleanOptionId'],   # None
            )
        )
        inserts += 1
    print(f'ProjectLead inserted: {inserts} rows')

# ── Commit ────────────────────────────────────────────────────────────────────
conn.commit()
conn.close()
print('\nDone. All changes committed.')
