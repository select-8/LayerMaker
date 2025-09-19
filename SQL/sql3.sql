SELECT
	Layers.Name,
    gc.*,
    --gcr.Renderer AS Renderer,
    --gcr.ExType AS ExType,
    gfd.GridFilterDefinitionId,
    gfd.Store, gfd.StoreId, gfd.IdField, gfd.LabelField, gfd.LocalField, gfd.DataIndex
FROM GridColumns gc
LEFT JOIN Layers on gc.LayerId = Layers.LayerId
LEFT JOIN GridColumnRenderers gcr 
    ON gc.GridColumnRendererId = gcr.GridColumnRendererId
LEFT JOIN GridFilterDefinitions gfd
    ON gc.GridFilterDefinitionId = gfd.GridFilterDefinitionId
WHERE gc.LayerId = 123 --and gc.GridFilterDefinitionId IS NOT NULL
--AND gc.FilterType = 'list'
--AND gc.InGrid = 1
--WHERE gc.GridFilterDefinitionId = 15
ORDER BY ColumnName

/*

We will need to do this for a lot of the GridFilters but lets start with the ElementTypeCode filter.
Currently in GridColumns, the GridFilterDefinitionId of 15 is assigned in GridColumns to the ElementTypeId column, whereas it should be assigned to the ElementTypeCode column.
We need to make GridFilterDefinitionId NULL for ElementTypeId and change its FilterType to 'number', and make it 15 for all ElementTypeCode columns and also change the ElementTypeCode FilterType values to 'list'.
Produce a SQL to do this

*/