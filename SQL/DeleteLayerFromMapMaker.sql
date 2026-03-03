BEGIN;

DELETE FROM GridColumns
WHERE LayerId IN (SELECT LayerId FROM Layers WHERE Name = 'RoadScheduleSpeedEdits');

DELETE FROM GridSorters
WHERE LayerId IN (SELECT LayerId FROM Layers WHERE Name = 'RoadScheduleSpeedEdits');

DELETE FROM GridMData
WHERE LayerId IN (SELECT LayerId FROM Layers WHERE Name = 'RoadScheduleSpeedEdits');

DELETE FROM LayerPortals
WHERE LayerId IN (SELECT LayerId FROM Layers WHERE Name = 'RoadScheduleSpeedEdits');

DELETE FROM Layers
WHERE Name = 'RoadScheduleSpeedEdits';

COMMIT;