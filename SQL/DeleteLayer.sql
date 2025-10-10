DELETE FROM GridColumns WHERE LayerId = 112;
DELETE FROM GridSorters WHERE LayerId = 112;
    -- only if filters are layer-scoped
DELETE FROM GridMData WHERE LayerId = 112;
DELETE FROM Layers WHERE LayerId = 112;