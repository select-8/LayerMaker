SELECT
    l.LayerId,
    l.Name            AS LayerName,
    gm.Controller,
    gm.IsSpatial,
    gm.ExcelExporter,
    gm.ShpExporter,
    gc.GridColumnId,
	gc.DisplayOrder,
    gc.ColumnName,
    gc.Text           AS ColumnText,
    gc.InGrid,
    gc.Hidden,
    gc.NullText,
    gc.NullValue,
    gc.Zeros,
    gc.NoFilter,
    gc.Flex,
    --gc.FilterType,
	gc.GridColumnRendererId,
    gc.CustomListValues,
    gcr.Renderer      AS ColumnRenderer,
    gcr.ExType        AS ColumnExType,
	gfd.GridFilterDefinitionId,
	gfd.Store,
	gfd.StoreId,
	gfd.IdField,
	gfd.LabelField,
	gfd.LocalField,
	gfd.DataIndex
--     gce.GroupEditIdProperty,
--     gce.GroupEditDataProp,
--     gce.EditServiceUrl,
--     er.RoleName       AS EditUserRole,
--     gs.GridSorterId,
--     gs.Property       AS SorterProperty,
--     gs.Direction      AS SorterDirection,
--     gs.SortOrder
FROM Layers l
LEFT JOIN GridMData gm
       ON gm.LayerId = l.LayerId
LEFT JOIN GridColumns gc
       ON gc.LayerId = l.LayerId
LEFT JOIN GridColumnRenderers gcr
       ON gcr.GridColumnRendererId = gc.GridColumnRendererId
LEFT JOIN GridFilterDefinitions gfd
        ON gfd.GridFilterDefinitionId = gc.GridFilterDefinitionId
-- LEFT JOIN GridColumnEdit gce
--        ON gce.GridColumnId = gc.GridColumnId
-- LEFT JOIN EditorRoles er
--        ON er.EditorRoleId = gce.EditorRoleId
-- LEFT JOIN GridSorters gs
--        ON gs.LayerId = l.LayerId
WHERE l.LayerId = 78
--WHERE l.name LIKE 'RoadSc%'
ORDER BY gc.DisplayOrder, gc.ColumnName, gc.GridColumnId--, gs.SortOrder;