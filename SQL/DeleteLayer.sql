DELETE FROM GridColumns WHERE LayerId = 125;
DELETE FROM GridSorters WHERE LayerId = 125;
    -- only if filters are layer-scoped
DELETE FROM GridMData WHERE LayerId = 125;
DELETE FROM Layers WHERE LayerId = 125;