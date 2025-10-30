PRAGMA foreign_keys = ON;

-- 1. Portals
CREATE TABLE Portals (
    PortalId   INTEGER PRIMARY KEY,
    code       TEXT NOT NULL UNIQUE,
    title      TEXT
);

-- 2. Global defaults, per portal
CREATE TABLE GlobalDefaults (
    GlobalDefaultId INTEGER PRIMARY KEY,
    portalId        INTEGER NOT NULL,
    key             TEXT NOT NULL,
    valueJSON       TEXT NOT NULL,
    FOREIGN KEY (portalId) REFERENCES Portals(PortalId)
);

CREATE INDEX ix_GlobalDefaults_portal ON GlobalDefaults(portalId);

-- 3. Layer type defaults, per portal and per layerType
CREATE TABLE LayerTypeDefaults (
    LayerTypeDefaultId INTEGER PRIMARY KEY,
    portalId           INTEGER NOT NULL,
    layerType          TEXT NOT NULL,
    defaultsJSON       TEXT NOT NULL,
    FOREIGN KEY (portalId) REFERENCES Portals(PortalId),
    UNIQUE (portalId, layerType)
);

-- 4. Label classes lookup
CREATE TABLE LabelClasses (
    LabelClassId INTEGER PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE
);

-- 5. Layers
-- this is the "portalised" layer table as we discussed
CREATE TABLE Layers (
    LayerId               INTEGER PRIMARY KEY,
    PortalId              INTEGER NOT NULL,
    layerKey              TEXT NOT NULL,
    layerType             TEXT NOT NULL,
    title                 TEXT,
    gridXType             TEXT,
    helpPage              TEXT,
    view                  TEXT,
    idProperty            TEXT,
    geomFieldName         TEXT,
    labelClassId          INTEGER,
    noCluster             INTEGER,  -- 0/1
    visibility            INTEGER,  -- 0/1
    featureInfoWindow     INTEGER,  -- 0/1
    vectorFeaturesMinScale INTEGER,
    legendWidth           INTEGER,
    openLayersJSON        TEXT,
    groupingJSON          TEXT,
    tooltipsConfigJSON    TEXT,
    FOREIGN KEY (PortalId) REFERENCES Portals(PortalId),
    FOREIGN KEY (labelClassId) REFERENCES LabelClasses(LabelClassId),
    UNIQUE (PortalId, layerKey)
);

CREATE INDEX ix_Layers_portal ON Layers(PortalId);
CREATE INDEX ix_Layers_key ON Layers(layerKey);

-- 6. WMS options, 1:1 with Layers when layerType='wms'
CREATE TABLE LayerWmsOptions (
    LayerId        INTEGER PRIMARY KEY,
    layers         TEXT,
    orderBy        TEXT,
    styles         TEXT,
    version        TEXT,
    maxResolution  REAL,
    requestMethod  TEXT,
    dateFormat     TEXT,
    FOREIGN KEY (LayerId) REFERENCES Layers(LayerId) ON DELETE CASCADE
);

-- 7. WFS options, 1:1 with Layers when layerType='wfs'
CREATE TABLE LayerWfsOptions (
    LayerId        INTEGER PRIMARY KEY,
    featureType    TEXT,
    propertyName   TEXT,
    version        TEXT,
    maxResolution  REAL,
    FOREIGN KEY (LayerId) REFERENCES Layers(LayerId) ON DELETE CASCADE
);

-- 8. ArcGIS REST options, very light
CREATE TABLE LayerArcGisRestOptions (
    LayerId INTEGER PRIMARY KEY,
    url     TEXT,
    FOREIGN KEY (LayerId) REFERENCES Layers(LayerId) ON DELETE CASCADE
);

-- 9. XYZ options, like you had before
CREATE TABLE LayerXyzOptions (
    LayerId        INTEGER PRIMARY KEY,
    urlTemplate    TEXT,
    accessToken    TEXT,
    projection     TEXT,
    tileSize       INTEGER,
    attributionHTML TEXT,
    extentJSON     TEXT,
    tileGridJSON   TEXT,
    isBaseLayer    INTEGER,
    FOREIGN KEY (LayerId) REFERENCES Layers(LayerId) ON DELETE CASCADE
);

-- 10. Styles, with no isDefault
CREATE TABLE LayerStyles (
    LayerId      INTEGER NOT NULL,
    name         TEXT NOT NULL,
    title        TEXT,
    labelRule    TEXT,
    legendUrl    TEXT,
    displayOrder INTEGER,
    PRIMARY KEY (LayerId, name),
    FOREIGN KEY (LayerId) REFERENCES Layers(LayerId) ON DELETE CASCADE
);

CREATE INDEX ix_LayerStyles_layer ON LayerStyles(LayerId);

-- 11. Switch-layer children (per portal layer)
CREATE TABLE SwitchLayerChildren (
    ParentLayerId INTEGER NOT NULL,
    ChildLayerId  INTEGER NOT NULL,
    position      INTEGER NOT NULL,
    PRIMARY KEY (ParentLayerId, ChildLayerId),
    FOREIGN KEY (ParentLayerId) REFERENCES Layers(LayerId) ON DELETE CASCADE,
    FOREIGN KEY (ChildLayerId)  REFERENCES Layers(LayerId) ON DELETE CASCADE
);

CREATE INDEX ix_SwitchChildren_parent ON SwitchLayerChildren(ParentLayerId);
