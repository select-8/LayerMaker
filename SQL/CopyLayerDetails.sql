BEGIN TRANSACTION;

-- 0) Define target layers in a temp table (CTE-free)
DROP TABLE IF EXISTS "_tmp_target_layers";
CREATE TEMP TABLE "_tmp_target_layers" (
    "LayerId" INTEGER PRIMARY KEY
);

INSERT INTO "_tmp_target_layers" ("LayerId") VALUES
(242),(243),(244),(245),(246),(247),(248),(249);

-- 1) Clear existing per-layer data
-- GridColumnEdit depends on GridColumns via GridColumnId, so delete edits first
DELETE FROM "GridColumnEdit"
WHERE "GridColumnId" IN (
    SELECT "GridColumnId"
    FROM "GridColumns"
    WHERE "LayerId" IN (SELECT "LayerId" FROM "_tmp_target_layers")
);

DELETE FROM "GridColumns"
WHERE "LayerId" IN (SELECT "LayerId" FROM "_tmp_target_layers");

DELETE FROM "GridSorters"
WHERE "LayerId" IN (SELECT "LayerId" FROM "_tmp_target_layers");

DELETE FROM "GridMData"
WHERE "LayerId" IN (SELECT "LayerId" FROM "_tmp_target_layers");

-- 2) Clone GridColumns from LayerId 66 into each target layer
INSERT INTO "GridColumns" (
    "LayerId",
    "ColumnName",
    "DisplayOrder",
    "Text",
    "IndexValue",
    "YesText",
    "NoText",
    "InGrid",
    "Hidden",
    "NullText",
    "NullValue",
    "Zeros",
    "NoFilter",
    "Flex",
    "CustomListValues",
    "Editable",
    "GridColumnRendererId",
    "GridFilterDefinitionId",
    "GridFilterTypeId"
)
SELECT
    tl."LayerId",
    src."ColumnName",
    src."DisplayOrder",
    src."Text",
    src."IndexValue",
    src."YesText",
    src."NoText",
    src."InGrid",
    src."Hidden",
    src."NullText",
    src."NullValue",
    src."Zeros",
    src."NoFilter",
    src."Flex",
    src."CustomListValues",
    src."Editable",
    src."GridColumnRendererId",
    src."GridFilterDefinitionId",
    src."GridFilterTypeId"
FROM "GridColumns" AS src
JOIN "_tmp_target_layers" AS tl
WHERE src."LayerId" = 66;

-- 3) Clone GridColumnEdit, rewired to the NEW GridColumnId via ColumnName
INSERT INTO "GridColumnEdit" (
    "GridColumnId",
    "GroupEditIdProperty",
    "GroupEditDataProp",
    "EditServiceUrl",
    "EditorRoleId"
)
SELECT
    newc."GridColumnId",
    e."GroupEditIdProperty",
    e."GroupEditDataProp",
    e."EditServiceUrl",
    e."EditorRoleId"
FROM "GridColumnEdit" AS e
JOIN "GridColumns" AS srcc
    ON srcc."GridColumnId" = e."GridColumnId"
JOIN "_tmp_target_layers" AS tl
JOIN "GridColumns" AS newc
    ON newc."LayerId" = tl."LayerId"
   AND newc."ColumnName" = srcc."ColumnName"
WHERE srcc."LayerId" = 66;

-- 4) Clone GridSorters
INSERT INTO "GridSorters" (
    "LayerId",
    "Property",
    "Direction",
    "SortOrder"
)
SELECT
    tl."LayerId",
    s."Property",
    s."Direction",
    s."SortOrder"
FROM "GridSorters" AS s
JOIN "_tmp_target_layers" AS tl
WHERE s."LayerId" = 66;

-- 5) Clone GridMData (one row per LayerId)
INSERT INTO "GridMData" (
    "LayerId",
    "IdField",
    "Service",
    "Window",
    "Model",
    "HelpPage",
    "Controller",
    "GetId",
    "IsSwitch",
    "IsSpatial",
    "ExcelExporter",
    "ShpExporter",
    "HasEditableColumns"
)
SELECT
    tl."LayerId",
    m."IdField",
    m."Service",
    m."Window",
    m."Model",
    m."HelpPage",
    m."Controller",
    m."GetId",
    m."IsSwitch",
    m."IsSpatial",
    m."ExcelExporter",
    m."ShpExporter",
    m."HasEditableColumns"
FROM "GridMData" AS m
JOIN "_tmp_target_layers" AS tl
WHERE m."LayerId" = 66;

COMMIT;
