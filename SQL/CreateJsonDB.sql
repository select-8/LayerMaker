PRAGMA foreign_keys = ON;

CREATE TABLE Layers (
  LayerId                INTEGER PRIMARY KEY,
  layerKey               TEXT    NOT NULL UNIQUE,
  layerType              TEXT    NOT NULL CHECK (layerType IN ('wms','wfs','xyz','switchlayer','arcgisrest')),
  title                  TEXT,
  gridXType              TEXT,
  idProperty             TEXT,
  featureType            TEXT,
  geomFieldName          TEXT,
  labelClassName         TEXT,
  legendWidth            INTEGER,
  visibilityDefault      INTEGER NOT NULL DEFAULT 0 CHECK (visibilityDefault IN (0,1)),
  vectorFeaturesMinScale INTEGER,
  featureInfoWindow      INTEGER CHECK (featureInfoWindow IN (0,1)),
  hasMetadata            INTEGER CHECK (hasMetadata IN (0,1)),
  isBaseLayer            INTEGER CHECK (isBaseLayer IN (0,1)),
  qtip                   TEXT,
  openLayersJSON         TEXT,
  tooltipsJSON           TEXT,
  groupingJSON           TEXT
);

CREATE INDEX ix_Layers_layerType ON Layers(layerType);
CREATE INDEX ix_Layers_gridXType ON Layers(gridXType);

CREATE TABLE LayerServerOptions (
  LayerServerOptionsId INTEGER PRIMARY KEY,
  LayerId              INTEGER NOT NULL UNIQUE REFERENCES Layers(LayerId) ON DELETE CASCADE,
  wmsLayers            TEXT,
  "orderBy"            TEXT,
  propertyName         TEXT,
  "version"            TEXT,
  maxResolution        REAL
);

CREATE TABLE LayerStyles (
  LayerStyleId   INTEGER PRIMARY KEY,
  LayerId        INTEGER NOT NULL REFERENCES Layers(LayerId) ON DELETE CASCADE,
  name           TEXT    NOT NULL,
  title          TEXT    NOT NULL,
  labelRule      TEXT,
  legendUrl      TEXT,
  isDefault      INTEGER NOT NULL DEFAULT 0 CHECK (isDefault IN (0,1)),
  displayOrder   INTEGER NOT NULL DEFAULT 0,
  UNIQUE (LayerId, name)
);

CREATE INDEX ix_Styles_LayerId_order ON LayerStyles(LayerId, displayOrder);

CREATE TABLE SwitchLayerChildren (
  SwitchChildId  INTEGER PRIMARY KEY,
  ParentLayerId  INTEGER NOT NULL REFERENCES Layers(LayerId) ON DELETE CASCADE,
  ChildLayerId   INTEGER NOT NULL REFERENCES Layers(LayerId) ON DELETE CASCADE,
  position       INTEGER NOT NULL,
  UNIQUE (ParentLayerId, ChildLayerId),
  UNIQUE (ParentLayerId, position)
);

CREATE INDEX ix_SwitchChildren_Parent ON SwitchLayerChildren(ParentLayerId);

CREATE TABLE LayerXYZOptions (
  LayerXYZOptionsId INTEGER PRIMARY KEY,
  LayerId           INTEGER NOT NULL UNIQUE REFERENCES Layers(LayerId) ON DELETE CASCADE,
  urlTemplate       TEXT    NOT NULL,
  projection        TEXT,
  tileSize          INTEGER,
  attributionHTML   TEXT,
  extentJSON        TEXT,
  tileGridJSON      TEXT
);

CREATE TABLE GlobalDefaults (
  key        TEXT PRIMARY KEY,
  valueJSON  TEXT NOT NULL
);

CREATE TABLE LayerTypeDefaults (
  layerType    TEXT PRIMARY KEY CHECK (layerType IN ('wms','wfs','xyz','switchlayer','arcgisrest')),
  defaultsJSON TEXT NOT NULL
);

CREATE TABLE EnvironmentOverrides (
  OverrideId    INTEGER PRIMARY KEY,
  envName       TEXT NOT NULL,
  scope         TEXT NOT NULL CHECK (scope IN ('global','layerType','layer')),
  scopeId       TEXT,
  overridesJSON TEXT NOT NULL
);

CREATE INDEX ix_EnvOverrides_scope ON EnvironmentOverrides(scope, scopeId);
CREATE INDEX ix_EnvOverrides_env ON EnvironmentOverrides(envName);
