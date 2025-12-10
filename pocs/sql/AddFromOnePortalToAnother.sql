BEGIN TRANSACTION;

/* 1) Source rows: only PortalId = 1, exclude any layerKey already in PortalId = 4 */
DROP TABLE IF EXISTS tmp_src;
CREATE TEMP TABLE tmp_src AS
SELECT jl.*
FROM JsonLayers jl
WHERE jl.PortalId = 1
  AND jl.layerKey LIKE 'ARCHIVED%'
  AND jl.layerKey NOT IN (
      SELECT layerKey FROM JsonLayers WHERE PortalId = 4
  );

/* 2) Insert into JsonLayers for PortalId = 4 */
INSERT INTO JsonLayers (
    PortalId, layerKey, layerType, title, gridXType, helpPage, view, idProperty,
    geomFieldName, labelClassId, noCluster, visibility, featureInfoWindow,
    vectorFeaturesMinScale, legendWidth, openLayersJSON, groupingJSON,
    tooltipsConfigJSON, url, legendUrl, requestMethod
)
SELECT
    4 AS PortalId,
    layerKey, layerType, title, gridXType, helpPage, view, idProperty,
    geomFieldName, labelClassId, noCluster, visibility, featureInfoWindow,
    vectorFeaturesMinScale, legendWidth, openLayersJSON, groupingJSON,
    tooltipsConfigJSON, url, legendUrl, requestMethod
FROM tmp_src;

/* 3) Map old -> new LayerId for the rows just created in Portal 4 */
DROP TABLE IF EXISTS tmp_map;
CREATE TEMP TABLE tmp_map AS
SELECT s.LayerId AS srcLayerId, d.LayerId AS dstLayerId, s.layerKey
FROM tmp_src s
JOIN JsonLayers d
  ON d.layerKey = s.layerKey
 AND d.PortalId = 4;

/* 4) Copy STYLES (matches your real columns) */
INSERT OR IGNORE INTO JsonLayerStyles (
    LayerId, name, title, labelRule, legendUrl, displayOrder
)
SELECT
    m.dstLayerId, s.name, s.title, s.labelRule, s.legendUrl, s.displayOrder
FROM JsonLayerStyles s
JOIN tmp_map m ON m.srcLayerId = s.LayerId;

/* 5) Copy WMS options (matches your real columns) */
INSERT OR IGNORE INTO JsonLayerWmsOptions (
    LayerId, layers, orderBy, styles, version, maxResolution, requestMethod, dateFormat
)
SELECT
    m.dstLayerId, w.layers, w.orderBy, w.styles, w.version, w.maxResolution, w.requestMethod, w.dateFormat
FROM JsonLayerWmsOptions w
JOIN tmp_map m ON m.srcLayerId = w.LayerId;

/* 6) Copy WFS options */
INSERT OR IGNORE INTO JsonLayerWfsOptions (
    LayerId, featureType, propertyName, version, maxResolution
)
SELECT
    m.dstLayerId, wfs.featureType, wfs.propertyName, wfs.version, wfs.maxResolution
FROM JsonLayerWfsOptions wfs
JOIN tmp_map m ON m.srcLayerId = wfs.LayerId;

/* 7) Copy XYZ options */
INSERT OR IGNORE INTO JsonLayerXyzOptions (
    LayerId, urlTemplate, accessToken, projection, tileSize, attributionHTML, extentJSON, tileGridJSON, isBaseLayer
)
SELECT
    m.dstLayerId, x.urlTemplate, x.accessToken, x.projection, x.tileSize, x.attributionHTML, x.extentJSON, x.tileGridJSON, x.isBaseLayer
FROM JsonLayerXyzOptions x
JOIN tmp_map m ON m.srcLayerId = x.LayerId;

/* 8) Copy ArcGIS REST options */
INSERT OR IGNORE INTO JsonLayerArcGisRestOptions (LayerId, url)
SELECT m.dstLayerId, a.url
FROM JsonLayerArcGisRestOptions a
JOIN tmp_map m ON m.srcLayerId = a.LayerId;

COMMIT;

/* Optional check
SELECT layerKey, PortalId, LayerId
FROM JsonLayers
WHERE layerKey LIKE 'ARCHIVED%' AND PortalId = 4
ORDER BY layerKey;
*/
