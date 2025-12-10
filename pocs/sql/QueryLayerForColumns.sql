WITH L AS (
    SELECT LayerId FROM Layers WHERE Name = 'CIRRoutes'
)
SELECT
    gc.GridColumnId,
    gc.ColumnName,
    r.Renderer,
    r.ExType,
    gc.CustomListValues,
    gc.NullText,
    gc.Zeros,
    gc.NullValue,
    gc.Editable,
    e.GroupEditIdProperty,
    e.GroupEditDataProp,
    e.EditServiceUrl,
	gdf.*
FROM GridColumns gc
JOIN L ON gc.LayerId = L.LayerId
LEFT JOIN GridColumnRenderers r
  ON r.GridColumnRendererId = gc.GridColumnRendererId
LEFT JOIN GridColumnEdit e
  ON e.GridColumnId = gc.GridColumnId
LEFT JOIN GridFilterDefinitions gdf
  ON gc.GridFilterDefinitionId = gdf.GridFilterDefinitionId
WHERE
      r.Renderer IS NULL
   OR r.ExType IS NULL
   OR gc.CustomListValues IS NULL
   OR gc.NullText IS NULL
   OR (gc.Editable = 1 AND (e.GroupEditIdProperty IS NULL
                         OR  e.GroupEditDataProp   IS NULL
                         OR  e.EditServiceUrl      IS NULL))
ORDER BY gc.ColumnName;
