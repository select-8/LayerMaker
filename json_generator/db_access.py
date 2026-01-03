import os
import sqlite3


class DBAccess:
    def __init__(self, db_path):
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database not found: {db_path}")
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    # ------------------------------------------------------------------
    # Global layers + portal usage
    # ------------------------------------------------------------------

    def get_all_layers(self):
        """
        Return one row per MapServerLayer with flags for whether WMS/WFS
        services exist.

        Columns:
          MapServerLayerId, MapLayerName, BaseLayerKey,
          IsXYZ, HasWms, HasWfs
        """
        cur = self.conn.execute(
            """
            SELECT
                m.MapServerLayerId,
                m.MapLayerName,
                m.BaseLayerKey,
                m.IsXYZ,
                MAX(CASE WHEN s.ServiceType = 'WMS' THEN 1 ELSE 0 END) AS HasWms,
                MAX(CASE WHEN s.ServiceType = 'WFS' THEN 1 ELSE 0 END) AS HasWfs
            FROM MapServerLayers m
            LEFT JOIN ServiceLayers s
              ON s.MapServerLayerId = m.MapServerLayerId
            GROUP BY
                m.MapServerLayerId,
                m.MapLayerName,
                m.BaseLayerKey,
                m.IsXYZ
            ORDER BY
                m.MapLayerName
            """
        )
        return list(cur.fetchall())

    def get_layer_portal_usage(self):
        """
        Return usage per BaseLayerKey per portal.

        One row per (BaseLayerKey, PortalId):

          BaseLayerKey, PortalId, PortalKey,
          HasWms, HasWfs, HasSwitch

        Where:
          - HasWms   = layer has a WMS ServiceLayer and PortalLayers row exists
          - HasWfs   = layer has a WFS ServiceLayer and PortalLayers row exists
          - HasSwitch = layer participates as a child in a PortalSwitchLayers
                        entry for that portal.
        """
        cur = self.conn.execute(
            """
            SELECT
                m.BaseLayerKey,
                p.PortalId,
                p.PortalKey,
                MAX(
                    CASE
                        WHEN s.ServiceType = 'WMS'
                         AND pl.PortalLayerId IS NOT NULL
                        THEN 1 ELSE 0
                    END
                ) AS HasWms,
                MAX(
                    CASE
                        WHEN s.ServiceType = 'WFS'
                         AND pl.PortalLayerId IS NOT NULL
                        THEN 1 ELSE 0
                    END
                ) AS HasWfs,
                MAX(
                    CASE
                        WHEN psl.PortalSwitchLayerId IS NOT NULL
                        THEN 1 ELSE 0
                    END
                ) AS HasSwitch
            FROM MapServerLayers m
            CROSS JOIN Portals p
            LEFT JOIN ServiceLayers s
              ON s.MapServerLayerId = m.MapServerLayerId
            LEFT JOIN PortalLayers pl
              ON pl.ServiceLayerId = s.ServiceLayerId
             AND pl.PortalId = p.PortalId
            LEFT JOIN PortalSwitchLayerChildren c
              ON c.ServiceLayerId = s.ServiceLayerId
            LEFT JOIN PortalSwitchLayers psl
              ON psl.PortalSwitchLayerId = c.PortalSwitchLayerId
             AND psl.PortalId = p.PortalId
            GROUP BY
                m.BaseLayerKey,
                p.PortalId,
                p.PortalKey
            ORDER BY
                m.BaseLayerKey,
                p.PortalId
            """
        )
        return list(cur.fetchall())

    def get_tab1_layer_list(self):
        """Return basic info for all MapServerLayers for the Tab 1 DB dropdown.

        Columns: MapServerLayerId, MapLayerName, BaseLayerKey
        """
        cur = self.conn.execute(
            """
            SELECT MapServerLayerId, MapLayerName, BaseLayerKey
            FROM MapServerLayers
            ORDER BY MapLayerName
            """
        )
        return list(cur.fetchall())

    def get_tab1_layer_details(self, mapserver_layer_id: int):
        """Return MapServerLayers + WMS/WFS ServiceLayers + fields + styles
        for a given MapServerLayerId.

        Result is a dict with keys:
          layer  -> MapServerLayers row
          wms    -> ServiceLayers row for ServiceType='WMS' or None
          wfs    -> ServiceLayers row for ServiceType='WFS' or None
          fields -> list of MapServerLayerFields rows (ordered)
          styles -> list of MapServerLayerStyles rows (ordered)
        """
        # Layer-level data is authoritative for:
        #   Opacity, Projection, LabelClassName, NoCluster
        cur = self.conn.execute(
            """
            SELECT
                msl.*
            FROM MapServerLayers msl
            WHERE msl.MapServerLayerId = ?
            """,
            (mapserver_layer_id,),
        )
        layer = cur.fetchone()
        if layer is None:
            return None

        # Service layers (WMS + WFS identity/config only)
        cur = self.conn.execute(
            """
            SELECT *
            FROM ServiceLayers
            WHERE MapServerLayerId = ?
            """,
            (mapserver_layer_id,),
        )
        wms = None
        wfs = None
        for row in cur.fetchall():
            st = (row["ServiceType"] or "").upper()
            if st == "WMS" and wms is None:
                wms = row
            elif st == "WFS" and wfs is None:
                wfs = row

        # Fields
        cur = self.conn.execute(
            """
            SELECT *
            FROM MapServerLayerFields
            WHERE MapServerLayerId = ?
            ORDER BY DisplayOrder, FieldName
            """,
            (mapserver_layer_id,),
        )
        fields = list(cur.fetchall())

        # Styles
        cur = self.conn.execute(
            """
            SELECT *
            FROM MapServerLayerStyles
            WHERE MapServerLayerId = ?
            ORDER BY DisplayOrder, GroupName, StyleTitle
            """,
            (mapserver_layer_id,),
        )
        styles = list(cur.fetchall())

        return {
            "layer": layer,
            "wms": wms,
            "wfs": wfs,
            "fields": fields,
            "styles": styles,
        }

    # ---------- Portal basics ----------

    def get_portals(self):
        cur = self.conn.execute(
            "SELECT PortalId, PortalKey, PortalTitle " "FROM Portals ORDER BY PortalId"
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
                sl.ServiceLayerId,
                sl.ServiceType,
                sl.LayerKey,
                sl.FeatureType,

                m.MapServerLayerId,
                m.MapLayerName,
                m.BaseLayerKey,
                m.GeometryType,
                m.GridXType AS MapGridXType,

                m.LabelClassName AS MapLabelClassName,
                m.Opacity        AS MapOpacity,
                m.NoCluster      AS MapNoCluster
            FROM PortalLayers pl
            JOIN ServiceLayers sl
              ON sl.ServiceLayerId = pl.ServiceLayerId
            JOIN MapServerLayers m
              ON m.MapServerLayerId = sl.MapServerLayerId
            WHERE pl.PortalId = ?
            ORDER BY m.MapLayerName, sl.ServiceType
            """,
            (portal_id,),
        )
        return cur.fetchall()

    def ensure_portal_layer(self, portal_id: int, service_layer_id: int):
        """
        Ensure there is an enabled PortalLayers row for (portal_id, service_layer_id).
        """
        cur = self.conn.execute(
            """
            SELECT PortalLayerId, IsEnabled
            FROM PortalLayers
            WHERE PortalId = ? AND ServiceLayerId = ?
            """,
            (portal_id, service_layer_id),
        )
        row = cur.fetchone()
        if row:
            if not row["IsEnabled"]:
                self.conn.execute(
                    "UPDATE PortalLayers SET IsEnabled = 1 WHERE PortalLayerId = ?",
                    (row["PortalLayerId"],),
                )
                self.conn.commit()
            return row["PortalLayerId"]

        self.conn.execute(
            """
            INSERT INTO PortalLayers (PortalId, ServiceLayerId, IsEnabled)
            VALUES (?, ?, 1)
            """,
            (portal_id, service_layer_id),
        )
        self.conn.commit()
        return self.conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]

    def disable_portal_layer(self, portal_id: int, service_layer_id: int):
        """
        Disable a PortalLayers row (soft delete).
        """
        self.conn.execute(
            """
            UPDATE PortalLayers
            SET IsEnabled = 0
            WHERE PortalId = ? AND ServiceLayerId = ?
            """,
            (portal_id, service_layer_id),
        )
        self.conn.commit()

    def ensure_switch_for_base(
        self,
        portal_id: int,
        base_layer_key: str,
        switch_key: str,
        vector_features_min_scale: int = 50000,
    ):
        """
        Ensure a PortalSwitchLayers entry exists for this portal + switch key.

        Rules:
          - Requires both WMS and WFS ServiceLayers for the base.
          - Ensures BOTH children have PortalLayers membership for this portal.
          - Recreates children: WMS childOrder=1, WFS childOrder=2.
          - Does NOT commit. Caller owns the transaction.
        """
        wms = self.get_service_layer_for_base(base_layer_key, "WMS")
        wfs = self.get_service_layer_for_base(base_layer_key, "WFS")
        if not wms or not wfs:
            raise ValueError(
                f"Both WMS and WFS ServiceLayers must exist for base '{base_layer_key}'"
            )

        wms_id = wms["ServiceLayerId"]
        wfs_id = wfs["ServiceLayerId"]

        # Mandatory: children are members of the portal (even if hidden in Tab 2).
        self.ensure_portal_layer(portal_id, wms_id)
        self.ensure_portal_layer(portal_id, wfs_id)

        # Ensure switch wrapper row exists
        cur = self.conn.execute(
            """
            SELECT PortalSwitchLayerId
            FROM PortalSwitchLayers
            WHERE PortalId = ? AND SwitchKey = ?
            """,
            (portal_id, switch_key),
        )
        row = cur.fetchone()

        if row:
            psl_id = row["PortalSwitchLayerId"]
            # Keep wrapper, replace children
            self.conn.execute(
                "DELETE FROM PortalSwitchLayerChildren WHERE PortalSwitchLayerId = ?",
                (psl_id,),
            )
            # Optional: keep VectorFeaturesMinScale in sync with latest chosen value
            self.conn.execute(
                """
                UPDATE PortalSwitchLayers
                SET VectorFeaturesMinScale = ?
                WHERE PortalSwitchLayerId = ?
                """,
                (vector_features_min_scale, psl_id),
            )
        else:
            cur2 = self.conn.execute(
                """
                INSERT INTO PortalSwitchLayers (PortalId, SwitchKey, VectorFeaturesMinScale)
                VALUES (?, ?, ?)
                """,
                (portal_id, switch_key, vector_features_min_scale),
            )
            psl_id = cur2.lastrowid

        # Reinsert children (order fixed: WMS=1, WFS=2)
        self.conn.execute(
            """
            INSERT INTO PortalSwitchLayerChildren (PortalSwitchLayerId, ServiceLayerId, ChildOrder)
            VALUES (?, ?, 1)
            """,
            (psl_id, wms_id),
        )
        self.conn.execute(
            """
            INSERT INTO PortalSwitchLayerChildren (PortalSwitchLayerId, ServiceLayerId, ChildOrder)
            VALUES (?, ?, 2)
            """,
            (psl_id, wfs_id),
        )

        return psl_id

    def remove_switch_for_base(self, portal_id: int, base_layer_key: str):
        """
        Remove all switchlayers in this portal whose children come from the given base layer.
        """
        cur = self.conn.execute(
            """
            SELECT DISTINCT psl.PortalSwitchLayerId
            FROM PortalSwitchLayers psl
            JOIN PortalSwitchLayerChildren c
              ON c.PortalSwitchLayerId = psl.PortalSwitchLayerId
            JOIN ServiceLayers s
              ON s.ServiceLayerId = c.ServiceLayerId
            JOIN MapServerLayers m
              ON m.MapServerLayerId = s.MapServerLayerId
            WHERE psl.PortalId = ?
              AND m.BaseLayerKey = ?
            """,
            (portal_id, base_layer_key),
        )
        rows = cur.fetchall()
        ids = [r["PortalSwitchLayerId"] for r in rows]
        for psl_id in ids:
            self.conn.execute(
                "DELETE FROM PortalSwitchLayerChildren WHERE PortalSwitchLayerId = ?",
                (psl_id,),
            )
            self.conn.execute(
                "DELETE FROM PortalSwitchLayers WHERE PortalSwitchLayerId = ?",
                (psl_id,),
            )
        if ids:
            self.conn.commit()

    def remove_portal_usage_for_base(self, portal_id: int, base_layer_key: str):
        """
        Set Off for this base in the given portal:
          - disable WMS/WFS PortalLayers rows
          - remove any switchlayers using this base
        """
        # Disable PortalLayers
        cur = self.conn.execute(
            """
            SELECT s.ServiceLayerId
            FROM ServiceLayers s
            JOIN MapServerLayers m
              ON m.MapServerLayerId = s.MapServerLayerId
            WHERE m.BaseLayerKey = ?
            """,
            (base_layer_key,),
        )
        for row in cur.fetchall():
            self.disable_portal_layer(portal_id, row["ServiceLayerId"])

        # Remove switchlayers
        self.remove_switch_for_base(portal_id, base_layer_key)

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

    def get_portal_layer_entries(self, portal_id: int):
        """
        Return entries for Tab 2 (tblPortalLayers) for a portal.

        One row per entry:

          EntryType: 'WMS' / 'WFS' / 'Switch'
          LayerKey:  ServiceLayers.LayerKey or SwitchKey
          LayerName: MapServerLayers.MapLayerName (or SwitchKey for switch)
          Service:   'WMS' / 'WFS' / 'Switch'
          PortalLayerId: nullable (for WMS/WFS)
          PortalSwitchLayerId: nullable (for Switch)
          ServiceLayerId: nullable (for WMS/WFS)
        """
        rows = self.conn.execute(
            """
            SELECT
                'WMS' AS EntryType,
                s.LayerKey AS LayerKey,
                m.MapLayerName AS LayerName,
                m.BaseLayerKey AS BaseLayerKey,
                'WMS' AS Service,
                pl.PortalLayerId AS PortalLayerId,
                NULL AS PortalSwitchLayerId
            FROM PortalLayers pl
            JOIN ServiceLayers s
              ON s.ServiceLayerId = pl.ServiceLayerId
            JOIN MapServerLayers m
              ON m.MapServerLayerId = s.MapServerLayerId
            WHERE pl.PortalId = ?
              AND s.ServiceType = 'WMS'

            UNION ALL

            SELECT
                'WFS' AS EntryType,
                s.LayerKey AS LayerKey,
                m.MapLayerName AS LayerName,
                m.BaseLayerKey AS BaseLayerKey,
                'WFS' AS Service,
                pl.PortalLayerId AS PortalLayerId,
                NULL AS PortalSwitchLayerId
            FROM PortalLayers pl
            JOIN ServiceLayers s
              ON s.ServiceLayerId = pl.ServiceLayerId
            JOIN MapServerLayers m
              ON m.MapServerLayerId = s.MapServerLayerId
            WHERE pl.PortalId = ?
              AND s.ServiceType = 'WFS'

            UNION ALL

            SELECT
                'Switch' AS EntryType,
                psl.SwitchKey AS LayerKey,
                psl.SwitchKey AS LayerName,
                NULL AS BaseLayerKey,
                'Switch' AS Service,
                NULL AS PortalLayerId,
                psl.PortalSwitchLayerId AS PortalSwitchLayerId
            FROM PortalSwitchLayers psl
            WHERE psl.PortalId = ?
            """,
            (portal_id, portal_id, portal_id),
        ).fetchall()

        switch_base_keys = self.get_switch_base_keys_for_portal(portal_id)

        filtered = []
        for r in rows:
            if r["EntryType"] in ("WMS", "WFS"):
                bk = r["BaseLayerKey"]
                if bk and bk in switch_base_keys:
                    # This service layer is represented via a switchlayer in this portal.
                    continue
            filtered.append(r)

        return filtered

    # ---------- Service layers ----------

    def get_service_layers(self):
        cur = self.conn.execute(
            "SELECT ServiceLayerId, LayerKey, ServiceType "
            "FROM ServiceLayers "
            "ORDER BY LayerKey"
        )
        return list(cur.fetchall())

    def get_service_layer_for_base(self, base_layer_key: str, service_type: str):
        """
        Return the ServiceLayers row for the given BaseLayerKey + ServiceType,
        or None if not found.
        """
        cur = self.conn.execute(
            """
            SELECT s.*
            FROM ServiceLayers s
            JOIN MapServerLayers m
              ON m.MapServerLayerId = s.MapServerLayerId
            WHERE m.BaseLayerKey = ?
              AND s.ServiceType = ?
            ORDER BY s.ServiceLayerId
            """,
            (base_layer_key, service_type),
        )
        row = cur.fetchone()
        return row

    def get_wfs_service_layer_fields(self, mapserver_layer_id: int):
        """
        Return ServiceLayerFields rows for the WFS service of this layer.

        Each row has:
          FieldName, FieldType, IncludeInPropertyname,
          IsTooltip, TooltipAlias, FieldOrder, ServiceLayerId, FieldId, ...
        """
        cur = self.conn.execute(
            """
            SELECT f.*
            FROM ServiceLayerFields f
            JOIN ServiceLayers s
              ON s.ServiceLayerId = f.ServiceLayerId
            WHERE s.MapServerLayerId = ?
              AND UPPER(s.ServiceType) = 'WFS'
            ORDER BY f.FieldOrder, f.FieldName
            """,
            (mapserver_layer_id,),
        )
        return list(cur.fetchall())

    # ---------- Layer persistence ----------

    def get_max_field_display_order(self, mapserver_layer_id: int) -> int:
        cur = self.conn.execute(
            "SELECT COALESCE(MAX(DisplayOrder), 0) AS MaxOrd "
            "FROM MapServerLayerFields WHERE MapServerLayerId = ?",
            (mapserver_layer_id,),
        )
        row = cur.fetchone()
        return int(row["MaxOrd"] or 0)

    def get_max_style_display_order(self, mapserver_layer_id: int) -> int:
        cur = self.conn.execute(
            "SELECT COALESCE(MAX(DisplayOrder), 0) AS MaxOrd "
            "FROM MapServerLayerStyles WHERE MapServerLayerId = ?",
            (mapserver_layer_id,),
        )
        row = cur.fetchone()
        return int(row["MaxOrd"] or 0)

    def get_layer_field_names(self, mapserver_layer_id: int):
        cur = self.conn.execute(
            """
            SELECT FieldName
            FROM MapServerLayerFields
            WHERE MapServerLayerId = ?
            """,
            (mapserver_layer_id,),
        )
        return [r["FieldName"] for r in cur.fetchall()]

    def get_layer_styles(self, mapserver_layer_id: int):
        cur = self.conn.execute(
            """
            SELECT GroupName, StyleTitle, IsIncluded
            FROM MapServerLayerStyles
            WHERE MapServerLayerId = ?
            ORDER BY DisplayOrder, GroupName, StyleTitle
            """,
            (mapserver_layer_id,),
        )
        return [(r["GroupName"], r["StyleTitle"], r["IsIncluded"]) for r in cur.fetchall()]

    def layer_exists(self, layer_name, base_layer_key):
        cur = self.conn.execute(
            "SELECT MapServerLayerId FROM MapServerLayers "
            "WHERE MapLayerName = ? OR BaseLayerKey = ?",
            (layer_name, base_layer_key),
        )
        row = cur.fetchone()
        if row is None:
            return False, None
        return True, int(row["MapServerLayerId"])

    def insert_mapserver_layer(
        self,
        map_layer_name,
        base_layer_key,
        gridxtype,
        geometry_type,
        default_geom_field,
        label_class_name=None,
        opacity=None,
        projection=None,
        no_cluster=1,
    ):
        op = 0.75 if opacity is None else float(opacity)
        nc = 1 if no_cluster is None else int(no_cluster)

        cur = self.conn.execute(
            """
            INSERT INTO MapServerLayers
                (
                    MapLayerName,
                    BaseLayerKey,
                    GridXType,
                    GeometryType,
                    DefaultGeomFieldName,
                    LabelClassName,
                    Opacity,
                    Projection,
                    NoCluster
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                map_layer_name,
                base_layer_key,
                gridxtype,
                geometry_type,
                default_geom_field,
                label_class_name,
                op,
                projection,
                nc,
            ),
        )
        return cur.lastrowid

    def update_mapserver_layer(
        self,
        mapserver_layer_id,
        base_layer_key,
        gridxtype,
        geometry_type,
        default_geom_field,
        label_class_name=None,
        opacity=None,
        projection=None,
        no_cluster=None,
    ):
        """
        Update a MapServerLayers row by ID.
        MapLayerName is immutable and is NOT updated.
        """
        self.conn.execute(
            """
            UPDATE MapServerLayers
            SET BaseLayerKey = ?,
                GridXType = ?,
                GeometryType = ?,
                DefaultGeomFieldName = ?,
                LabelClassName = ?,
                Opacity = COALESCE(?, Opacity, 0.75),
                Projection = ?,
                NoCluster = COALESCE(?, NoCluster, 1)
            WHERE MapServerLayerId = ?
            """,
            (
                base_layer_key,
                gridxtype,
                geometry_type,
                default_geom_field,
                label_class_name,
                None if opacity is None else float(opacity),
                projection,
                None if no_cluster is None else int(no_cluster),
                mapserver_layer_id,
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

    def insert_layer_style(self, mapserver_layer_id, group_name, style_title, display_order, is_included=1):
        self.conn.execute(
            """
            INSERT INTO MapServerLayerStyles
                (MapServerLayerId, GroupName, StyleTitle, DisplayOrder, IsIncluded)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                mapserver_layer_id,
                group_name,
                style_title,
                display_order,
                int(is_included),
            ),
        )

    def delete_layer_styles(self, mapserver_layer_id: int):
        self.conn.execute(
            "DELETE FROM MapServerLayerStyles WHERE MapServerLayerId = ?",
            (mapserver_layer_id,),
        )

    def get_service_layer_id(self, mapserver_layer_id: int, service_type: str):
        """
        Return ServiceLayerId for this MapServerLayer + service type, or None.
        """
        cur = self.conn.execute(
            """
            SELECT ServiceLayerId
            FROM ServiceLayers
            WHERE MapServerLayerId = ?
              AND ServiceType = ?
            ORDER BY ServiceLayerId
            """,
            (mapserver_layer_id, service_type),
        )
        row = cur.fetchone()
        return row["ServiceLayerId"] if row else None

    def update_service_layer(
        self,
        service_layer_id,
        layer_key,
        feature_type,
        id_property_name,
        geom_field_name,
        label_class_name=None,
        opacity=None,
    ):
        """
        Update a ServiceLayers row by ID.

        ServiceType is immutable and not updated.
        Layer-level config (label/opactity/projection/noCluster) is handled on MapServerLayers.
        """

        self.conn.execute(
            """
            UPDATE ServiceLayers
            SET LayerKey = ?,
                FeatureType = ?,
                IdPropertyName = ?,
                GeomFieldName = ?
            WHERE ServiceLayerId = ?
            """,
            (
                layer_key,
                feature_type,
                id_property_name,
                geom_field_name,
                service_layer_id,
            ),
        )

    def insert_service_layer(
        self,
        mapserver_layer_id,
        service_type,
        layer_key,
        feature_type,
        id_property_name,
        geom_field_name,
        label_class_name=None,
        opacity=None,
    ):
        cur = self.conn.execute(
            """
            INSERT INTO ServiceLayers
                (MapServerLayerId, ServiceType, LayerKey, FeatureType, IdPropertyName, GeomFieldName)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                mapserver_layer_id,
                service_type,
                layer_key,
                feature_type,
                id_property_name,
                geom_field_name,
            ),
        )
        return cur.lastrowid

    def delete_layer_fields(self, mapserver_layer_id: int):
        """
        Delete all MapServerLayerFields rows for this layer.
        """
        self.conn.execute(
            "DELETE FROM MapServerLayerFields WHERE MapServerLayerId = ?",
            (mapserver_layer_id,),
        )

    def delete_layer_styles(self, mapserver_layer_id: int):
        """
        Delete all MapServerLayerStyles rows for this layer.
        """
        self.conn.execute(
            "DELETE FROM MapServerLayerStyles WHERE MapServerLayerId = ?",
            (mapserver_layer_id,),
        )

    def delete_service_layer_fields(self, service_layer_id: int):
        """
        Delete all ServiceLayerFields rows for this service layer.
        """
        self.conn.execute(
            "DELETE FROM ServiceLayerFields WHERE ServiceLayerId = ?",
            (service_layer_id,),
        )

    def insert_service_layer_field(
        self,
        service_layer_id: int,
        field_name: str,
        field_type: str,
        include_in_propertyname: bool,
        is_tooltip: bool,
        tooltip_alias: str | None,
        field_order: int,
    ):
        self.conn.execute(
            """
            INSERT INTO ServiceLayerFields
                (ServiceLayerId, FieldName, FieldType,
                 IncludeInPropertyname, IsTooltip, TooltipAlias, FieldOrder)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                service_layer_id,
                field_name,
                field_type,
                int(bool(include_in_propertyname)),
                int(bool(is_tooltip)),
                tooltip_alias,
                field_order,
            ),
        )

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()
