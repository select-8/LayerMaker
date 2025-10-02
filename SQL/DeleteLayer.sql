DELETE FROM GridColumns WHERE LayerId = 126;
DELETE FROM GridSorters WHERE LayerId = 126;
    -- only if filters are layer-scoped
DELETE FROM GridMData WHERE LayerId = 126;
DELETE FROM Layers WHERE LayerId = 126;