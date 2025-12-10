-- Script Date: 09/12/2025 10:15  - ErikEJ.SqlCeScripting version 3.5.2.103
-- Database information:
-- Database: C:\DevOps\LayerMaker\tree_generator\LayerConfig_v3.db
-- ServerVersion: 3.46.1
-- DatabaseSize: 140 KB
-- Created: 08/12/2025 14:15

-- User Table information:
-- Number of tables: 11
-- MapServerLayerFields: -1 row(s)
-- MapServerLayers: -1 row(s)
-- MapServerLayerStyles: -1 row(s)
-- PortalLayers: -1 row(s)
-- Portals: -1 row(s)
-- PortalSwitchLayerChildren: -1 row(s)
-- PortalSwitchLayers: -1 row(s)
-- PortalTreeNodes: -1 row(s)
-- ServiceLayerFields: -1 row(s)
-- ServiceLayers: -1 row(s)
-- ServiceLayerStyles: -1 row(s)

SELECT 1;
PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE [Portals] (
  [PortalId] bigint NOT NULL
, [PortalKey] text NOT NULL
, [PortalTitle] text NOT NULL
, CONSTRAINT [sqlite_master_PK_Portals] PRIMARY KEY ([PortalId])
);
CREATE TABLE [PortalSwitchLayers] (
  [PortalSwitchLayerId] bigint NOT NULL
, [PortalId] bigint NOT NULL
, [SwitchKey] text NOT NULL
, [VectorFeaturesMinScale] bigint NULL
, CONSTRAINT [sqlite_master_PK_PortalSwitchLayers] PRIMARY KEY ([PortalSwitchLayerId])
, CONSTRAINT [FK_PortalSwitchLayers_0_0] FOREIGN KEY ([PortalId]) REFERENCES [Portals] ([PortalId]) ON DELETE CASCADE ON UPDATE NO ACTION
);
CREATE TABLE [MapServerLayers] (
  [MapServerLayerId] bigint NOT NULL
, [MapLayerName] text NOT NULL
, [BaseLayerKey] text NOT NULL
, [GridXType] text NOT NULL
, [GeometryType] text NOT NULL
, [DefaultGeomFieldName] text DEFAULT ('msGeometry') NOT NULL
, [DefaultLabelClassName] text DEFAULT ('labels') NOT NULL
, [DefaultOpacity] real DEFAULT (0.75) NOT NULL
, [Notes] text NULL
, [LabelClassName] text NULL
, [GeomFieldName] text NULL
, [Opacity] real NULL
, [IsXYZ] bigint DEFAULT (0) NOT NULL
, [IsArcGisRest] bigint DEFAULT (0) NOT NULL
, CONSTRAINT [sqlite_master_PK_MapServerLayers] PRIMARY KEY ([MapServerLayerId])
);
CREATE TABLE [MapServerLayerStyles] (
  [StyleId] bigint NOT NULL
, [MapServerLayerId] bigint NOT NULL
, [GroupName] text NOT NULL
, [StyleTitle] text NOT NULL
, [DisplayOrder] bigint DEFAULT (0) NOT NULL
, CONSTRAINT [sqlite_master_PK_MapServerLayerStyles] PRIMARY KEY ([StyleId])
, CONSTRAINT [FK_MapServerLayerStyles_0_0] FOREIGN KEY ([MapServerLayerId]) REFERENCES [MapServerLayers] ([MapServerLayerId]) ON DELETE CASCADE ON UPDATE NO ACTION
);
CREATE TABLE [ServiceLayers] (
  [ServiceLayerId] bigint NOT NULL
, [MapServerLayerId] bigint NOT NULL
, [ServiceType] text NOT NULL
, [LayerKey] text NOT NULL
, [FeatureType] text NULL
, [IdPropertyName] text NULL
, [GeomFieldName] text DEFAULT ('msGeometry') NOT NULL
, [LabelClassName] text DEFAULT ('labels') NOT NULL
, [Opacity] real DEFAULT (0.75) NOT NULL
, [OpenLayersJson] text NULL
, [ServerOptionsJson] text NULL
, [GridXType] text NULL
, [ProjectionOverride] text NULL
, [OpacityOverride] real NULL
, [NoClusterOverride] bigint NULL
, [FeatureInfoWindowOverride] bigint NULL
, [Grouping] text NULL
, [IsUserConfigurable] bigint DEFAULT (1) NOT NULL
, CONSTRAINT [sqlite_master_PK_ServiceLayers] PRIMARY KEY ([ServiceLayerId])
, CONSTRAINT [FK_ServiceLayers_0_0] FOREIGN KEY ([MapServerLayerId]) REFERENCES [MapServerLayers] ([MapServerLayerId]) ON DELETE CASCADE ON UPDATE NO ACTION
);
CREATE TABLE [PortalSwitchLayerChildren] (
  [PortalSwitchLayerChildId] bigint NOT NULL
, [PortalSwitchLayerId] bigint NOT NULL
, [ServiceLayerId] bigint NOT NULL
, [ChildOrder] bigint NULL
, CONSTRAINT [sqlite_master_PK_PortalSwitchLayerChildren] PRIMARY KEY ([PortalSwitchLayerChildId])
, CONSTRAINT [FK_PortalSwitchLayerChildren_0_0] FOREIGN KEY ([ServiceLayerId]) REFERENCES [ServiceLayers] ([ServiceLayerId]) ON DELETE CASCADE ON UPDATE NO ACTION
, CONSTRAINT [FK_PortalSwitchLayerChildren_1_0] FOREIGN KEY ([PortalSwitchLayerId]) REFERENCES [PortalSwitchLayers] ([PortalSwitchLayerId]) ON DELETE CASCADE ON UPDATE NO ACTION
);
CREATE TABLE [PortalLayers] (
  [PortalLayerId] bigint NOT NULL
, [PortalId] bigint NOT NULL
, [ServiceLayerId] bigint NOT NULL
, [IsEnabled] bigint DEFAULT (1) NOT NULL
, CONSTRAINT [sqlite_master_PK_PortalLayers] PRIMARY KEY ([PortalLayerId])
, CONSTRAINT [FK_PortalLayers_0_0] FOREIGN KEY ([ServiceLayerId]) REFERENCES [ServiceLayers] ([ServiceLayerId]) ON DELETE CASCADE ON UPDATE NO ACTION
, CONSTRAINT [FK_PortalLayers_1_0] FOREIGN KEY ([PortalId]) REFERENCES [Portals] ([PortalId]) ON DELETE CASCADE ON UPDATE NO ACTION
);
CREATE TABLE [ServiceLayerFields] (
  [FieldId] bigint NOT NULL
, [ServiceLayerId] bigint NOT NULL
, [FieldName] text NOT NULL
, [FieldType] text NULL
, [IncludeInPropertyname] bigint DEFAULT (0) NOT NULL
, [IsTooltip] bigint DEFAULT (0) NOT NULL
, [TooltipAlias] text NULL
, [FieldOrder] bigint NULL
, CONSTRAINT [sqlite_master_PK_ServiceLayerFields] PRIMARY KEY ([FieldId])
, CONSTRAINT [FK_ServiceLayerFields_0_0] FOREIGN KEY ([ServiceLayerId]) REFERENCES [ServiceLayers] ([ServiceLayerId]) ON DELETE CASCADE ON UPDATE NO ACTION
);
CREATE TABLE [ServiceLayerStyles] (
  [StyleId] bigint NOT NULL
, [ServiceLayerId] bigint NOT NULL
, [StyleName] text NOT NULL
, [StyleTitle] text NOT NULL
, [UseLabelRule] bigint DEFAULT (0) NOT NULL
, [StyleOrder] bigint NULL
, CONSTRAINT [sqlite_master_PK_ServiceLayerStyles] PRIMARY KEY ([StyleId])
, CONSTRAINT [FK_ServiceLayerStyles_0_0] FOREIGN KEY ([ServiceLayerId]) REFERENCES [ServiceLayers] ([ServiceLayerId]) ON DELETE CASCADE ON UPDATE NO ACTION
);
CREATE TABLE [PortalTreeNodes] (
  [PortalTreeNodeId] bigint NOT NULL
, [PortalId] bigint NOT NULL
, [ParentNodeId] bigint NULL
, [IsFolder] bigint NOT NULL
, [FolderTitle] text NULL
, [LayerKey] text NULL
, [DisplayOrder] bigint DEFAULT (0) NOT NULL
, [Glyph] text NULL
, [CheckedDefault] bigint DEFAULT (1) NOT NULL
, [ExpandedDefault] bigint DEFAULT (0) NOT NULL
, [Tooltip] text NULL
, [FolderId] text NULL
, [LayerTitle] text NULL
, CONSTRAINT [sqlite_master_PK_PortalTreeNodes] PRIMARY KEY ([PortalTreeNodeId])
, CONSTRAINT [FK_PortalTreeNodes_0_0] FOREIGN KEY ([LayerKey]) REFERENCES [ServiceLayers] ([LayerKey]) ON DELETE RESTRICT ON UPDATE NO ACTION
, CONSTRAINT [FK_PortalTreeNodes_1_0] FOREIGN KEY ([ParentNodeId]) REFERENCES [PortalTreeNodes] ([PortalTreeNodeId]) ON DELETE CASCADE ON UPDATE NO ACTION
, CONSTRAINT [FK_PortalTreeNodes_2_0] FOREIGN KEY ([PortalId]) REFERENCES [Portals] ([PortalId]) ON DELETE CASCADE ON UPDATE NO ACTION
);
CREATE TABLE [MapServerLayerFields] (
  [FieldId] bigint NOT NULL
, [MapServerLayerId] bigint NOT NULL
, [FieldName] text NOT NULL
, [FieldType] text NOT NULL
, [IncludeInPropertyCsv] bigint DEFAULT (0) NOT NULL
, [IsIdProperty] bigint DEFAULT (0) NOT NULL
, [DisplayOrder] bigint DEFAULT (0) NOT NULL
, CONSTRAINT [sqlite_master_PK_MapServerLayerFields] PRIMARY KEY ([FieldId])
, CONSTRAINT [FK_MapServerLayerFields_0_0] FOREIGN KEY ([MapServerLayerId]) REFERENCES [MapServerLayers] ([MapServerLayerId]) ON DELETE CASCADE ON UPDATE NO ACTION
);
INSERT INTO [Portals] ([PortalId],[PortalKey],[PortalTitle]) VALUES (
1,'default','Default viewer');
INSERT INTO [Portals] ([PortalId],[PortalKey],[PortalTitle]) VALUES (
2,'editor','Editor viewer');
INSERT INTO [Portals] ([PortalId],[PortalKey],[PortalTitle]) VALUES (
3,'tii_default','TII viewer');
INSERT INTO [Portals] ([PortalId],[PortalKey],[PortalTitle]) VALUES (
4,'nta_default','NTA viewer');
INSERT INTO [MapServerLayers] ([MapServerLayerId],[MapLayerName],[BaseLayerKey],[GridXType],[GeometryType],[DefaultGeomFieldName],[DefaultLabelClassName],[DefaultOpacity],[Notes],[LabelClassName],[GeomFieldName],[Opacity],[IsXYZ],[IsArcGisRest]) VALUES (
1,'ROADSCHEDULENATIONAL','ROADSCHEDULENATIONAL','pms_roadschedulenationalgrid','line','msGeometry','labels',0.75,NULL,NULL,NULL,NULL,0,0);
INSERT INTO [MapServerLayerStyles] ([StyleId],[MapServerLayerId],[GroupName],[StyleTitle],[DisplayOrder]) VALUES (
1,1,'default','Roads',1);
INSERT INTO [ServiceLayers] ([ServiceLayerId],[MapServerLayerId],[ServiceType],[LayerKey],[FeatureType],[IdPropertyName],[GeomFieldName],[LabelClassName],[Opacity],[OpenLayersJson],[ServerOptionsJson],[GridXType],[ProjectionOverride],[OpacityOverride],[NoClusterOverride],[FeatureInfoWindowOverride],[Grouping],[IsUserConfigurable]) VALUES (
1,1,'WMS','ROADSCHEDULENATIONAL_WMS','ROADSCHEDULENATIONAL','SegmentId','msGeometry','labels',0.75,NULL,NULL,'pms_roadschedulenationalgrid',NULL,NULL,NULL,NULL,NULL,1);
INSERT INTO [ServiceLayers] ([ServiceLayerId],[MapServerLayerId],[ServiceType],[LayerKey],[FeatureType],[IdPropertyName],[GeomFieldName],[LabelClassName],[Opacity],[OpenLayersJson],[ServerOptionsJson],[GridXType],[ProjectionOverride],[OpacityOverride],[NoClusterOverride],[FeatureInfoWindowOverride],[Grouping],[IsUserConfigurable]) VALUES (
2,1,'WFS','ROADSCHEDULENATIONAL_VECTOR','ROADSCHEDULENATIONAL','SegmentId','msGeometry','labels',0.75,NULL,NULL,'pms_roadschedulenationalgrid',NULL,NULL,NULL,NULL,NULL,1);
INSERT INTO [PortalLayers] ([PortalLayerId],[PortalId],[ServiceLayerId],[IsEnabled]) VALUES (
1,1,2,1);
INSERT INTO [PortalLayers] ([PortalLayerId],[PortalId],[ServiceLayerId],[IsEnabled]) VALUES (
2,1,1,1);
INSERT INTO [PortalLayers] ([PortalLayerId],[PortalId],[ServiceLayerId],[IsEnabled]) VALUES (
3,2,2,1);
INSERT INTO [PortalLayers] ([PortalLayerId],[PortalId],[ServiceLayerId],[IsEnabled]) VALUES (
4,2,1,1);
INSERT INTO [MapServerLayerFields] ([FieldId],[MapServerLayerId],[FieldName],[FieldType],[IncludeInPropertyCsv],[IsIdProperty],[DisplayOrder]) VALUES (
1,1,'SegmentId','int',1,1,1);
INSERT INTO [MapServerLayerFields] ([FieldId],[MapServerLayerId],[FieldName],[FieldType],[IncludeInPropertyCsv],[IsIdProperty],[DisplayOrder]) VALUES (
2,1,'RoadNumber','string',1,0,2);
INSERT INTO [MapServerLayerFields] ([FieldId],[MapServerLayerId],[FieldName],[FieldType],[IncludeInPropertyCsv],[IsIdProperty],[DisplayOrder]) VALUES (
3,1,'RoadCategory','string',0,0,3);
CREATE UNIQUE INDEX [sqlite_autoindex_Portals_1] ON [Portals] ([PortalKey] ASC);
CREATE INDEX [idx_PortalSwitchLayers_PortalId] ON [PortalSwitchLayers] ([PortalId] ASC);
CREATE UNIQUE INDEX [sqlite_autoindex_PortalSwitchLayers_1] ON [PortalSwitchLayers] ([PortalId] ASC,[SwitchKey] ASC);
CREATE UNIQUE INDEX [sqlite_autoindex_MapServerLayers_2] ON [MapServerLayers] ([BaseLayerKey] ASC);
CREATE UNIQUE INDEX [sqlite_autoindex_MapServerLayers_1] ON [MapServerLayers] ([MapLayerName] ASC);
CREATE UNIQUE INDEX [idx_LayerStyles_group] ON [MapServerLayerStyles] ([MapServerLayerId] ASC,[GroupName] ASC);
CREATE UNIQUE INDEX [idx_ServiceLayers_layer_service] ON [ServiceLayers] ([MapServerLayerId] ASC,[ServiceType] ASC);
CREATE UNIQUE INDEX [sqlite_autoindex_ServiceLayers_1] ON [ServiceLayers] ([LayerKey] ASC);
CREATE INDEX [idx_PortalSwitchLayerChildren_ServiceLayerId] ON [PortalSwitchLayerChildren] ([ServiceLayerId] ASC);
CREATE INDEX [idx_PortalSwitchLayerChildren_PortalSwitchLayerId] ON [PortalSwitchLayerChildren] ([PortalSwitchLayerId] ASC);
CREATE UNIQUE INDEX [sqlite_autoindex_PortalSwitchLayerChildren_1] ON [PortalSwitchLayerChildren] ([PortalSwitchLayerId] ASC,[ServiceLayerId] ASC);
CREATE INDEX [idx_PortalLayers_ServiceLayerId] ON [PortalLayers] ([ServiceLayerId] ASC);
CREATE INDEX [idx_PortalLayers_PortalId] ON [PortalLayers] ([PortalId] ASC);
CREATE UNIQUE INDEX [sqlite_autoindex_PortalLayers_1] ON [PortalLayers] ([PortalId] ASC,[ServiceLayerId] ASC);
CREATE INDEX [idx_ServiceLayerFields_ServiceLayerId] ON [ServiceLayerFields] ([ServiceLayerId] ASC);
CREATE INDEX [idx_ServiceLayerStyles_ServiceLayerId] ON [ServiceLayerStyles] ([ServiceLayerId] ASC);
CREATE INDEX [idx_PortalTree_parent] ON [PortalTreeNodes] ([ParentNodeId] ASC);
CREATE INDEX [idx_PortalTree_portal] ON [PortalTreeNodes] ([PortalId] ASC);
CREATE UNIQUE INDEX [idx_LayerFields_idProperty] ON [MapServerLayerFields] ([MapServerLayerId] ASC,[IsIdProperty] ASC);
CREATE UNIQUE INDEX [idx_LayerFields_name] ON [MapServerLayerFields] ([MapServerLayerId] ASC,[FieldName] ASC);
CREATE TRIGGER [fki_PortalSwitchLayers_PortalId_Portals_PortalId] BEFORE Insert ON [PortalSwitchLayers] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Insert on table PortalSwitchLayers violates foreign key constraint FK_PortalSwitchLayers_0_0') WHERE NOT EXISTS (SELECT * FROM Portals WHERE  PortalId = NEW.PortalId); END;
CREATE TRIGGER [fku_PortalSwitchLayers_PortalId_Portals_PortalId] BEFORE Update ON [PortalSwitchLayers] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Update on table PortalSwitchLayers violates foreign key constraint FK_PortalSwitchLayers_0_0') WHERE NOT EXISTS (SELECT * FROM Portals WHERE  PortalId = NEW.PortalId); END;
CREATE TRIGGER [fki_MapServerLayerStyles_MapServerLayerId_MapServerLayers_MapServerLayerId] BEFORE Insert ON [MapServerLayerStyles] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Insert on table MapServerLayerStyles violates foreign key constraint FK_MapServerLayerStyles_0_0') WHERE NOT EXISTS (SELECT * FROM MapServerLayers WHERE  MapServerLayerId = NEW.MapServerLayerId); END;
CREATE TRIGGER [fku_MapServerLayerStyles_MapServerLayerId_MapServerLayers_MapServerLayerId] BEFORE Update ON [MapServerLayerStyles] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Update on table MapServerLayerStyles violates foreign key constraint FK_MapServerLayerStyles_0_0') WHERE NOT EXISTS (SELECT * FROM MapServerLayers WHERE  MapServerLayerId = NEW.MapServerLayerId); END;
CREATE TRIGGER [fki_ServiceLayers_MapServerLayerId_MapServerLayers_MapServerLayerId] BEFORE Insert ON [ServiceLayers] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Insert on table ServiceLayers violates foreign key constraint FK_ServiceLayers_0_0') WHERE NOT EXISTS (SELECT * FROM MapServerLayers WHERE  MapServerLayerId = NEW.MapServerLayerId); END;
CREATE TRIGGER [fku_ServiceLayers_MapServerLayerId_MapServerLayers_MapServerLayerId] BEFORE Update ON [ServiceLayers] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Update on table ServiceLayers violates foreign key constraint FK_ServiceLayers_0_0') WHERE NOT EXISTS (SELECT * FROM MapServerLayers WHERE  MapServerLayerId = NEW.MapServerLayerId); END;
CREATE TRIGGER [fki_PortalSwitchLayerChildren_ServiceLayerId_ServiceLayers_ServiceLayerId] BEFORE Insert ON [PortalSwitchLayerChildren] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Insert on table PortalSwitchLayerChildren violates foreign key constraint FK_PortalSwitchLayerChildren_0_0') WHERE NOT EXISTS (SELECT * FROM ServiceLayers WHERE  ServiceLayerId = NEW.ServiceLayerId); END;
CREATE TRIGGER [fku_PortalSwitchLayerChildren_ServiceLayerId_ServiceLayers_ServiceLayerId] BEFORE Update ON [PortalSwitchLayerChildren] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Update on table PortalSwitchLayerChildren violates foreign key constraint FK_PortalSwitchLayerChildren_0_0') WHERE NOT EXISTS (SELECT * FROM ServiceLayers WHERE  ServiceLayerId = NEW.ServiceLayerId); END;
CREATE TRIGGER [fki_PortalSwitchLayerChildren_PortalSwitchLayerId_PortalSwitchLayers_PortalSwitchLayerId] BEFORE Insert ON [PortalSwitchLayerChildren] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Insert on table PortalSwitchLayerChildren violates foreign key constraint FK_PortalSwitchLayerChildren_1_0') WHERE NOT EXISTS (SELECT * FROM PortalSwitchLayers WHERE  PortalSwitchLayerId = NEW.PortalSwitchLayerId); END;
CREATE TRIGGER [fku_PortalSwitchLayerChildren_PortalSwitchLayerId_PortalSwitchLayers_PortalSwitchLayerId] BEFORE Update ON [PortalSwitchLayerChildren] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Update on table PortalSwitchLayerChildren violates foreign key constraint FK_PortalSwitchLayerChildren_1_0') WHERE NOT EXISTS (SELECT * FROM PortalSwitchLayers WHERE  PortalSwitchLayerId = NEW.PortalSwitchLayerId); END;
CREATE TRIGGER [fki_PortalLayers_ServiceLayerId_ServiceLayers_ServiceLayerId] BEFORE Insert ON [PortalLayers] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Insert on table PortalLayers violates foreign key constraint FK_PortalLayers_0_0') WHERE NOT EXISTS (SELECT * FROM ServiceLayers WHERE  ServiceLayerId = NEW.ServiceLayerId); END;
CREATE TRIGGER [fku_PortalLayers_ServiceLayerId_ServiceLayers_ServiceLayerId] BEFORE Update ON [PortalLayers] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Update on table PortalLayers violates foreign key constraint FK_PortalLayers_0_0') WHERE NOT EXISTS (SELECT * FROM ServiceLayers WHERE  ServiceLayerId = NEW.ServiceLayerId); END;
CREATE TRIGGER [fki_PortalLayers_PortalId_Portals_PortalId] BEFORE Insert ON [PortalLayers] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Insert on table PortalLayers violates foreign key constraint FK_PortalLayers_1_0') WHERE NOT EXISTS (SELECT * FROM Portals WHERE  PortalId = NEW.PortalId); END;
CREATE TRIGGER [fku_PortalLayers_PortalId_Portals_PortalId] BEFORE Update ON [PortalLayers] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Update on table PortalLayers violates foreign key constraint FK_PortalLayers_1_0') WHERE NOT EXISTS (SELECT * FROM Portals WHERE  PortalId = NEW.PortalId); END;
CREATE TRIGGER [fki_ServiceLayerFields_ServiceLayerId_ServiceLayers_ServiceLayerId] BEFORE Insert ON [ServiceLayerFields] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Insert on table ServiceLayerFields violates foreign key constraint FK_ServiceLayerFields_0_0') WHERE NOT EXISTS (SELECT * FROM ServiceLayers WHERE  ServiceLayerId = NEW.ServiceLayerId); END;
CREATE TRIGGER [fku_ServiceLayerFields_ServiceLayerId_ServiceLayers_ServiceLayerId] BEFORE Update ON [ServiceLayerFields] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Update on table ServiceLayerFields violates foreign key constraint FK_ServiceLayerFields_0_0') WHERE NOT EXISTS (SELECT * FROM ServiceLayers WHERE  ServiceLayerId = NEW.ServiceLayerId); END;
CREATE TRIGGER [fki_ServiceLayerStyles_ServiceLayerId_ServiceLayers_ServiceLayerId] BEFORE Insert ON [ServiceLayerStyles] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Insert on table ServiceLayerStyles violates foreign key constraint FK_ServiceLayerStyles_0_0') WHERE NOT EXISTS (SELECT * FROM ServiceLayers WHERE  ServiceLayerId = NEW.ServiceLayerId); END;
CREATE TRIGGER [fku_ServiceLayerStyles_ServiceLayerId_ServiceLayers_ServiceLayerId] BEFORE Update ON [ServiceLayerStyles] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Update on table ServiceLayerStyles violates foreign key constraint FK_ServiceLayerStyles_0_0') WHERE NOT EXISTS (SELECT * FROM ServiceLayers WHERE  ServiceLayerId = NEW.ServiceLayerId); END;
CREATE TRIGGER [fki_PortalTreeNodes_LayerKey_ServiceLayers_LayerKey] BEFORE Insert ON [PortalTreeNodes] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Insert on table PortalTreeNodes violates foreign key constraint FK_PortalTreeNodes_0_0') WHERE NEW.LayerKey IS NOT NULL AND NOT EXISTS (SELECT * FROM ServiceLayers WHERE  LayerKey = NEW.LayerKey); END;
CREATE TRIGGER [fku_PortalTreeNodes_LayerKey_ServiceLayers_LayerKey] BEFORE Update ON [PortalTreeNodes] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Update on table PortalTreeNodes violates foreign key constraint FK_PortalTreeNodes_0_0') WHERE NEW.LayerKey IS NOT NULL AND NOT EXISTS (SELECT * FROM ServiceLayers WHERE  LayerKey = NEW.LayerKey); END;
CREATE TRIGGER [fki_PortalTreeNodes_ParentNodeId_PortalTreeNodes_PortalTreeNodeId] BEFORE Insert ON [PortalTreeNodes] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Insert on table PortalTreeNodes violates foreign key constraint FK_PortalTreeNodes_1_0') WHERE NEW.ParentNodeId IS NOT NULL AND NOT EXISTS (SELECT * FROM PortalTreeNodes WHERE  PortalTreeNodeId = NEW.ParentNodeId); END;
CREATE TRIGGER [fku_PortalTreeNodes_ParentNodeId_PortalTreeNodes_PortalTreeNodeId] BEFORE Update ON [PortalTreeNodes] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Update on table PortalTreeNodes violates foreign key constraint FK_PortalTreeNodes_1_0') WHERE NEW.ParentNodeId IS NOT NULL AND NOT EXISTS (SELECT * FROM PortalTreeNodes WHERE  PortalTreeNodeId = NEW.ParentNodeId); END;
CREATE TRIGGER [fki_PortalTreeNodes_PortalId_Portals_PortalId] BEFORE Insert ON [PortalTreeNodes] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Insert on table PortalTreeNodes violates foreign key constraint FK_PortalTreeNodes_2_0') WHERE NOT EXISTS (SELECT * FROM Portals WHERE  PortalId = NEW.PortalId); END;
CREATE TRIGGER [fku_PortalTreeNodes_PortalId_Portals_PortalId] BEFORE Update ON [PortalTreeNodes] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Update on table PortalTreeNodes violates foreign key constraint FK_PortalTreeNodes_2_0') WHERE NOT EXISTS (SELECT * FROM Portals WHERE  PortalId = NEW.PortalId); END;
CREATE TRIGGER [fki_MapServerLayerFields_MapServerLayerId_MapServerLayers_MapServerLayerId] BEFORE Insert ON [MapServerLayerFields] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Insert on table MapServerLayerFields violates foreign key constraint FK_MapServerLayerFields_0_0') WHERE NOT EXISTS (SELECT * FROM MapServerLayers WHERE  MapServerLayerId = NEW.MapServerLayerId); END;
CREATE TRIGGER [fku_MapServerLayerFields_MapServerLayerId_MapServerLayers_MapServerLayerId] BEFORE Update ON [MapServerLayerFields] FOR EACH ROW BEGIN SELECT RAISE(ROLLBACK, 'Update on table MapServerLayerFields violates foreign key constraint FK_MapServerLayerFields_0_0') WHERE NOT EXISTS (SELECT * FROM MapServerLayers WHERE  MapServerLayerId = NEW.MapServerLayerId); END;
COMMIT;

