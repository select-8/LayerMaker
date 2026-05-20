-- Copy column properties from SurfaceCourse to all other PavementLayer grids
-- and set the correct Material filter for each layer

-- Update Base (262) -> pavementLayerId 5 -> 157
UPDATE GridColumns
SET DisplayOrder = (SELECT DisplayOrder FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Text = (SELECT Text FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    InGrid = (SELECT InGrid FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Hidden = (SELECT Hidden FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Flex = (SELECT Flex FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    GridFilterTypeId = (SELECT GridFilterTypeId FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    SortIndex = (SELECT SortIndex FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName)
WHERE LayerId = 262 AND ColumnName IN (SELECT ColumnName FROM GridColumns WHERE LayerId = 261);

UPDATE GridColumns SET GridFilterDefinitionId = 157 WHERE LayerId = 262 AND ColumnName = 'Material';

-- Update Regulating (263) -> pavementLayerId 3 -> 160
UPDATE GridColumns
SET DisplayOrder = (SELECT DisplayOrder FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Text = (SELECT Text FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    InGrid = (SELECT InGrid FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Hidden = (SELECT Hidden FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Flex = (SELECT Flex FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    GridFilterTypeId = (SELECT GridFilterTypeId FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    SortIndex = (SELECT SortIndex FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName)
WHERE LayerId = 263 AND ColumnName IN (SELECT ColumnName FROM GridColumns WHERE LayerId = 261);

UPDATE GridColumns SET GridFilterDefinitionId = 160 WHERE LayerId = 263 AND ColumnName = 'Material';

-- Update BinderCourse (264) -> pavementLayerId 4 -> 161
UPDATE GridColumns
SET DisplayOrder = (SELECT DisplayOrder FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Text = (SELECT Text FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    InGrid = (SELECT InGrid FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Hidden = (SELECT Hidden FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Flex = (SELECT Flex FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    GridFilterTypeId = (SELECT GridFilterTypeId FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    SortIndex = (SELECT SortIndex FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName)
WHERE LayerId = 264 AND ColumnName IN (SELECT ColumnName FROM GridColumns WHERE LayerId = 261);

UPDATE GridColumns SET GridFilterDefinitionId = 161 WHERE LayerId = 264 AND ColumnName = 'Material';

-- Update SubBase (265) -> pavementLayerId 7 -> 162
UPDATE GridColumns
SET DisplayOrder = (SELECT DisplayOrder FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Text = (SELECT Text FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    InGrid = (SELECT InGrid FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Hidden = (SELECT Hidden FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Flex = (SELECT Flex FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    GridFilterTypeId = (SELECT GridFilterTypeId FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    SortIndex = (SELECT SortIndex FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName)
WHERE LayerId = 265 AND ColumnName IN (SELECT ColumnName FROM GridColumns WHERE LayerId = 261);

UPDATE GridColumns SET GridFilterDefinitionId = 162 WHERE LayerId = 265 AND ColumnName = 'Material';

-- Update Capping (266) -> pavementLayerId 8 -> 163
UPDATE GridColumns
SET DisplayOrder = (SELECT DisplayOrder FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Text = (SELECT Text FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    InGrid = (SELECT InGrid FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Hidden = (SELECT Hidden FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Flex = (SELECT Flex FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    GridFilterTypeId = (SELECT GridFilterTypeId FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    SortIndex = (SELECT SortIndex FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName)
WHERE LayerId = 266 AND ColumnName IN (SELECT ColumnName FROM GridColumns WHERE LayerId = 261);

UPDATE GridColumns SET GridFilterDefinitionId = 163 WHERE LayerId = 266 AND ColumnName = 'Material';

-- Update GeotexAR variants (267, 270, 271) -> pavementLayerId 10 -> 164
UPDATE GridColumns
SET DisplayOrder = (SELECT DisplayOrder FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Text = (SELECT Text FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    InGrid = (SELECT InGrid FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Hidden = (SELECT Hidden FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Flex = (SELECT Flex FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    GridFilterTypeId = (SELECT GridFilterTypeId FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    SortIndex = (SELECT SortIndex FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName)
WHERE LayerId IN (267, 270, 271) AND ColumnName IN (SELECT ColumnName FROM GridColumns WHERE LayerId = 261);

UPDATE GridColumns SET GridFilterDefinitionId = 164 WHERE LayerId IN (267, 270, 271) AND ColumnName = 'Material';

-- Update GeotexSD variants (268, 273, 275) -> pavementLayerId 11 -> 165
UPDATE GridColumns
SET DisplayOrder = (SELECT DisplayOrder FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Text = (SELECT Text FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    InGrid = (SELECT InGrid FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Hidden = (SELECT Hidden FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Flex = (SELECT Flex FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    GridFilterTypeId = (SELECT GridFilterTypeId FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    SortIndex = (SELECT SortIndex FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName)
WHERE LayerId IN (268, 273, 275) AND ColumnName IN (SELECT ColumnName FROM GridColumns WHERE LayerId = 261);

UPDATE GridColumns SET GridFilterDefinitionId = 165 WHERE LayerId IN (268, 273, 275) AND ColumnName = 'Material';

-- Update GeotexUBR variants (269, 272, 274) -> pavementLayerId 12 -> 166
UPDATE GridColumns
SET DisplayOrder = (SELECT DisplayOrder FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Text = (SELECT Text FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    InGrid = (SELECT InGrid FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Hidden = (SELECT Hidden FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Flex = (SELECT Flex FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    GridFilterTypeId = (SELECT GridFilterTypeId FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    SortIndex = (SELECT SortIndex FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName)
WHERE LayerId IN (269, 272, 274) AND ColumnName IN (SELECT ColumnName FROM GridColumns WHERE LayerId = 261);

UPDATE GridColumns SET GridFilterDefinitionId = 166 WHERE LayerId IN (269, 272, 274) AND ColumnName = 'Material';

-- Update SurfaceTreatments (260) -> pavementLayerId 1 -> 155
UPDATE GridColumns
SET DisplayOrder = (SELECT DisplayOrder FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Text = (SELECT Text FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    InGrid = (SELECT InGrid FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Hidden = (SELECT Hidden FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    Flex = (SELECT Flex FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    GridFilterTypeId = (SELECT GridFilterTypeId FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName),
    SortIndex = (SELECT SortIndex FROM GridColumns src WHERE src.LayerId = 261 AND src.ColumnName = GridColumns.ColumnName)
WHERE LayerId = 260 AND ColumnName IN (SELECT ColumnName FROM GridColumns WHERE LayerId = 261);

UPDATE GridColumns SET GridFilterDefinitionId = 155 WHERE LayerId = 260 AND ColumnName = 'Material';

-- Verify Material filters are set correctly
SELECT l.Name, gc.ColumnName, gc.GridFilterDefinitionId, gfd.StoreFilter
FROM GridColumns gc
JOIN Layers l ON gc.LayerId = l.LayerId
LEFT JOIN GridFilterDefinitions gfd ON gc.GridFilterDefinitionId = gfd.GridFilterDefinitionId
WHERE l.Name LIKE 'PavementLayer%' AND gc.ColumnName = 'Material'
ORDER BY l.Name;
