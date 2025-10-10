
SELECT l.LayerId,
       l.Name AS LayerName,
	   gc.ColumnName,
	   gc.[Text]
FROM Layers AS l
JOIN GridColumns AS gc
  ON gc.LayerId = l.LayerId
WHERE lower(gc.ColumnName) LIKE '%' || lower('Munic') || '%' AND gc.ColumnName NOT LIKE '%' || lower('ID') || '%'
GROUP BY l.LayerId, l.Name
ORDER BY l.Name;


SELECT l.LayerId,
       l.Name AS LayerName,
	   gc.ColumnName,
	   gc.[Text]
FROM Layers AS l
JOIN GridColumns AS gc
  ON gc.LayerId = l.LayerId
WHERE (lower(gc.ColumnName) LIKE '%' || lower('Local') || '%' OR lower(gc.ColumnName) LIKE '%' || lower('Short') || '%') AND gc.ColumnName NOT LIKE '%' || lower('ID') || '%'
GROUP BY l.LayerId, l.Name
ORDER BY l.Name;