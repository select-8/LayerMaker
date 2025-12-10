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

    # ---------- Portal layer helpers ----------

    def get_portal_layer_services(self, portal_id):
        """
        Return all ServiceLayers that are enabled in the given portal,
        joined to MapServerLayers, one row per (portal, service layer).
        """
        cur = self.conn.execute(
            """
            SELECT
                pl.PortalLayerId,
                pl.IsEnabled,
                sl.ServiceLayerId,
                sl.ServiceType,
                sl.LayerKey,
                sl.FeatureType,
                sl.LabelClassName,
                sl.Opacity,
                sl.ProjectionOverride,
                sl.OpacityOverride,
                m.MapServerLayerId,
                m.MapLayerName,
                m.BaseLayerKey,
                m.GeometryType,
                m.GridXType          AS MapGridXType,
                m.DefaultOpacity     AS MapDefaultOpacity
            FROM PortalLayers pl
            JOIN ServiceLayers sl
              ON sl.ServiceLayerId = pl.ServiceLayerId
            JOIN MapServerLayers m
              ON m.MapServerLayerId = sl.MapServerLayerId
            WHERE pl.PortalId = ?
              AND pl.IsEnabled = 1
            ORDER BY m.MapLayerName, sl.ServiceType
            """,
            (portal_id,),
        )
        return cur.fetchall()

    # ---------- Portal switch layers ----------

    def get_switch_base_keys_for_portal(self, portal_id: int):
        """
        Return a set of BaseLayerKey values that participate as children
        in any switchlayer for this portal.
        """
        cur = self.conn.execute(
            """
            SELECT DISTINCT m.BaseLayerKey
            FROM PortalSwitchLayers psl
            JOIN PortalSwitchLayerChildren c
              ON c.PortalSwitchLayerId = psl.PortalSwitchLayerId
            JOIN ServiceLayers sl
              ON sl.ServiceLayerId = c.ServiceLayerId
            JOIN MapServerLayers m
              ON m.MapServerLayerId = sl.MapServerLayerId
            WHERE psl.PortalId = ?
            """,
            (portal_id,),
        )
        return {row["BaseLayerKey"] for row in cur.fetchall()}

    def get_portal_switch_layers(self, portal_id):
        """
        Return switchlayers for a portal with their WMS and WFS child layer keys.

        One row per switch:
          PortalSwitchLayerId, SwitchKey, VectorFeaturesMinScale,
          WmsLayerKey, WfsLayerKey
        """
        cur = self.conn.execute(
            """
            SELECT
                psl.PortalSwitchLayerId,
                psl.SwitchKey,
                psl.VectorFeaturesMinScale,
                MAX(CASE WHEN sl.ServiceType = 'WMS' THEN sl.LayerKey END) AS WmsLayerKey,
                MAX(CASE WHEN sl.ServiceType = 'WFS' THEN sl.LayerKey END) AS WfsLayerKey
            FROM PortalSwitchLayers psl
            JOIN PortalSwitchLayerChildren c
              ON c.PortalSwitchLayerId = psl.PortalSwitchLayerId
            JOIN ServiceLayers sl
              ON sl.ServiceLayerId = c.ServiceLayerId
            WHERE psl.PortalId = ?
            GROUP BY
                psl.PortalSwitchLayerId,
                psl.SwitchKey,
                psl.VectorFeaturesMinScale
            ORDER BY psl.SwitchKey
            """,
            (portal_id,),
        )
        return cur.fetchall()

    def create_switch_layer(
        self,
        portal_id: int,
        switch_key: str,
        wms_service_layer_id: int,
        wfs_service_layer_id: int,
        vector_features_min_scale: int = 50000,
    ) -> int:
        """
        Create a new PortalSwitchLayers row and two PortalSwitchLayerChildren rows.

        Returns the new PortalSwitchLayerId.
        """
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO PortalSwitchLayers (PortalId, SwitchKey, VectorFeaturesMinScale)
            VALUES (?, ?, ?)
            """,
            (portal_id, switch_key, vector_features_min_scale),
        )
        psl_id = cur.lastrowid

        cur.execute(
            """
            INSERT INTO PortalSwitchLayerChildren
                (PortalSwitchLayerId, ServiceLayerId, ChildOrder)
            VALUES (?, ?, ?)
            """,
            (psl_id, wms_service_layer_id, 1),
        )
        cur.execute(
            """
            INSERT INTO PortalSwitchLayerChildren
                (PortalSwitchLayerId, ServiceLayerId, ChildOrder)
            VALUES (?, ?, ?)
            """,
            (psl_id, wfs_service_layer_id, 2),
        )

        self.conn.commit()
        return psl_id

    def delete_switch_layer(self, portal_switch_layer_id: int) -> None:
        """
        Remove a switchlayer and its children.
        """
        cur = self.conn.cursor()
        cur.execute(
            "DELETE FROM PortalSwitchLayerChildren WHERE PortalSwitchLayerId = ?",
            (portal_switch_layer_id,),
        )
        cur.execute(
            "DELETE FROM PortalSwitchLayers WHERE PortalSwitchLayerId = ?",
            (portal_switch_layer_id,),
        )
        self.conn.commit()

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
