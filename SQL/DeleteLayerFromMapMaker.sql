BEGIN;

DELETE FROM GridColumns
WHERE LayerId IN (SELECT LayerId FROM Layers WHERE Name = 'bla');

DELETE FROM GridSorters
WHERE LayerId IN (SELECT LayerId FROM Layers WHERE Name = 'bla');

DELETE FROM GridMData
WHERE LayerId IN (SELECT LayerId FROM Layers WHERE Name = 'bla');

DELETE FROM MapStyles
WHERE LayerId IN (SELECT LayerId FROM Layers WHERE Name = 'bla');

DELETE FROM MapLayers
WHERE LayerId IN (SELECT LayerId FROM Layers WHERE Name = 'bla');

DELETE FROM LayerPortals
WHERE LayerId IN (SELECT LayerId FROM Layers WHERE Name = 'bla');

DELETE FROM Layers
WHERE Name = 'bla';

COMMIT;