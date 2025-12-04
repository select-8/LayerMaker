import os
import sqlite3


class DBAccess:
    def __init__(self, db_path):
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database not found: {db_path}")
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    # ---------- Portal basics ----------

    def get_portals(self):
        cur = self.conn.execute(
            "SELECT PortalId, PortalKey, PortalTitle "
            "FROM Portals ORDER BY PortalId"
        )
        return list(cur.fetchall())

    def get_portal_tree(self, portal_id):
        cur = self.conn.execute(
            "SELECT * FROM PortalTreeNodes "
            "WHERE PortalId = ? "
            "ORDER BY ParentNodeId, DisplayOrder, PortalTreeNodeId",
            (portal_id,),
        )
        return list(cur.fetchall())

    def get_portal_used_layer_keys(self, portal_id):
        cur = self.conn.execute(
            "SELECT LayerKey FROM PortalTreeNodes "
            "WHERE PortalId = ? AND IsFolder = 0 AND LayerKey IS NOT NULL",
            (portal_id,),
        )
        return {row["LayerKey"] for row in cur.fetchall()}

    # ---------- Service layers ----------

    def get_service_layers(self):
        cur = self.conn.execute(
            "SELECT ServiceLayerId, LayerKey, ServiceType "
            "FROM ServiceLayers "
            "ORDER BY LayerKey"
        )
        return list(cur.fetchall())

    # ---------- New layer persistence ----------

    def layer_exists(self, layer_name, base_layer_key):
        cur = self.conn.execute(
            "SELECT MapServerLayerId FROM MapServerLayers "
            "WHERE MapLayerName = ? OR BaseLayerKey = ?",
            (layer_name, base_layer_key),
        )
        row = cur.fetchone()
        if row is None:
            return False, None
        return True, row["MapServerLayerId"]

    def insert_mapserver_layer(
        self,
        map_layer_name,
        base_layer_key,
        gridxtype,
        geometry_type,
        default_geom_field,
        default_label_class,
        default_opacity,
        notes=None,
    ):
        cur = self.conn.execute(
            """
            INSERT INTO MapServerLayers
                (MapLayerName, BaseLayerKey, GridXType,
                 GeometryType, DefaultGeomFieldName,
                 DefaultLabelClassName, DefaultOpacity, Notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                map_layer_name,
                base_layer_key,
                gridxtype,
                geometry_type,
                default_geom_field,
                default_label_class,
                default_opacity,
                notes,
            ),
        )
        return cur.lastrowid

    def insert_service_layer(
        self,
        mapserver_layer_id,
        service_type,
        layer_key,
        feature_type,
        id_property_name,
        geom_field_name,
        label_class_name,
        opacity,
        openlayers_json,
        server_options_json=None,
    ):
        self.conn.execute(
            """
            INSERT INTO ServiceLayers
                (MapServerLayerId, ServiceType, LayerKey,
                 FeatureType, IdPropertyName,
                 GeomFieldName, LabelClassName,
                 Opacity, OpenLayersJson, ServerOptionsJson)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mapserver_layer_id,
                service_type,
                layer_key,
                feature_type,
                id_property_name,
                geom_field_name,
                label_class_name,
                opacity,
                openlayers_json,
                server_options_json,
            ),
        )

    def insert_layer_field(
        self,
        mapserver_layer_id,
        field_name,
        field_type,
        include_in_csv,
        is_id_property,
        display_order,
    ):
        self.conn.execute(
            """
            INSERT INTO MapServerLayerFields
                (MapServerLayerId, FieldName, FieldType,
                 IncludeInPropertyCsv, IsIdProperty, DisplayOrder)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                mapserver_layer_id,
                field_name,
                field_type,
                int(bool(include_in_csv)),
                int(bool(is_id_property)),
                display_order,
            ),
        )

    def insert_layer_style(
        self,
        mapserver_layer_id,
        group_name,
        style_title,
        display_order,
    ):
        self.conn.execute(
            """
            INSERT INTO MapServerLayerStyles
                (MapServerLayerId, GroupName, StyleTitle, DisplayOrder)
            VALUES (?, ?, ?, ?)
            """,
            (
                mapserver_layer_id,
                group_name,
                style_title,
                display_order,
            ),
        )

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()
