PRAGMA foreign_keys = OFF;
/* WARNING: This script DROPs existing tables. Use only if you are okay losing current data. */

DROP TABLE IF EXISTS EnvironmentOverrides;
DROP TABLE IF EXISTS SwitchLayerChildren;
DROP TABLE IF EXISTS LayerStyles;
DROP TABLE IF EXISTS LayerXYZOptions;
DROP TABLE IF EXISTS LayerServerOptions;
DROP TABLE IF EXISTS LayerTypeDefaults;
DROP TABLE IF EXISTS GlobalDefaults;
DROP TABLE IF EXISTS Layers;
DROP TABLE IF EXISTS Portals;

PRAGMA foreign_keys = ON;

/* ---------- Core: Portals ---------- */
CREATE TABLE Portals (
  PortalId   INTEGER PRIMARY KEY,
  code       TEXT NOT NULL UNIQUE CHECK (code IN ('default','editor','nta_default','tii_default')),
  title      TEXT
);

INSERT INTO Portals (code, title) VALUES
  ('default','Default'),
  ('editor','Editor'),
  ('nta_default','NTA Default'),
  ('tii_default','TII Default');

/* ---------- Layers (portal-scoped) ---------- */
CREATE TABLE Layers (
  LayerId                INTEGER PRIMARY KEY,
  portalId               INTEGER NOT NULL REFERENCES Portals(PortalId) ON DELETE CASCADE,
  layerKey               TEXT    NOT NULL,
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
  groupingJSON           TEXT,
  UNIQUE (portalId, layerKey)
);

CREATE INDEX ix_Layers_portalId  ON Layers(portalId);
CREATE INDEX ix_Layers_type      ON Layers(layerType);
CREATE INDEX ix_Layers_gridXType ON Layers(gridXType);

/* ---------- WMS/WFS server options ---------- */
CREATE TABLE LayerServerOptions (
  LayerServerOptionsId INTEGER PRIMARY KEY,
  LayerId              INTEGER NOT NULL UNIQUE REFERENCES Layers(LayerId) ON DELETE CASCADE,
  wmsLayers            TEXT,
  "orderBy"            TEXT,
  propertyName         TEXT,
  "version"            TEXT,
  maxResolution        REAL
);

/* ---------- Styles ---------- */
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

/* ---------- Switchlayer composition ---------- */
CREATE TABLE SwitchLayerChildren (
  SwitchChildId  INTEGER PRIMARY KEY,
  ParentLayerId  INTEGER NOT NULL REFERENCES Layers(LayerId) ON DELETE CASCADE,
  ChildLayerId   INTEGER NOT NULL REFERENCES Layers(LayerId) ON DELETE CASCADE,
  position       INTEGER NOT NULL,
  UNIQUE (ParentLayerId, ChildLayerId),
  UNIQUE (ParentLayerId, position)
);

CREATE INDEX ix_SwitchChildren_Parent ON SwitchLayerChildren(ParentLayerId);

/* ---------- XYZ specifics ---------- */
CREATE TABLE LayerXYZOptions (
  LayerXYZOptionsId INTEGER PRIMARY KEY,
  LayerId           INTEGER NOT NULL UNIQUE REFERENCES Layers(LayerId) ON DELETE CASCADE,
  urlTemplate       TEXT    NOT NULL,
  accessToken       TEXT,
  projection        TEXT,
  tileSize          INTEGER,
  attributionHTML   TEXT,
  extentJSON        TEXT,
  tileGridJSON      TEXT
);

/* ---------- Defaults (portal-scoped) ---------- */
CREATE TABLE GlobalDefaults (
  key        TEXT NOT NULL,
  portalId   INTEGER NOT NULL REFERENCES Portals(PortalId) ON DELETE CASCADE,
  valueJSON  TEXT NOT NULL,
  PRIMARY KEY (portalId, key)
);

CREATE TABLE LayerTypeDefaults (
  layerType    TEXT NOT NULL CHECK (layerType IN ('wms','wfs','xyz','switchlayer','arcgisrest')),
  portalId     INTEGER NOT NULL REFERENCES Portals(PortalId) ON DELETE CASCADE,
  defaultsJSON TEXT NOT NULL,
  PRIMARY KEY (portalId, layerType)
);

/* ---------- Environment overrides (optional, portal-scoped) ---------- */
CREATE TABLE EnvironmentOverrides (
  OverrideId    INTEGER PRIMARY KEY,
  portalId      INTEGER NOT NULL REFERENCES Portals(PortalId) ON DELETE CASCADE,
  envName       TEXT NOT NULL,
  scope         TEXT NOT NULL CHECK (scope IN ('global','layerType','layer')),
  scopeId       TEXT,
  overridesJSON TEXT NOT NULL
);

CREATE INDEX ix_EnvOverrides_scope ON EnvironmentOverrides(portalId, scope, scopeId);
CREATE INDEX ix_EnvOverrides_env   ON EnvironmentOverrides(portalId, envName);
