PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

-- 1) Map styles that reference the map layer for this LayerId
DELETE FROM MapStyles
WHERE LayerId = 25;

-- 2) MapLayers rows that reference the layer
DELETE FROM MapLayers
WHERE LayerId = 25;

-- 3) Any GridColumnEdit rows for columns on this layer
DELETE FROM GridColumnEdit
WHERE GridColumnId IN (
    SELECT GridColumnId
    FROM GridColumns
    WHERE LayerId = 25
);

-- 4) Grid columns for this layer
DELETE FROM GridColumns
WHERE LayerId = 25;

-- 5) Grid metadata for this layer
DELETE FROM GridMData
WHERE LayerId = 25;

-- 6) Grid sorters for this layer
DELETE FROM GridSorters
WHERE LayerId = 25;

-- 7) Finally, the layer itself
DELETE FROM Layers
WHERE LayerId = 25;

COMMIT;
