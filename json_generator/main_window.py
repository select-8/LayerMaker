import os
import sqlite3
import sys
import json

from PyQt5 import QtWidgets, QtCore, QtGui, uic

from db_access import DBAccess
from mapfile_utils import parse_mapfile, extract_styles, extract_fields
import layer_export

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app2.wfs_to_db import WFSToDB, DEFAULT_WFS_URL

DB_FILENAME = "LayerConfig_v3.db"
UI_FILENAME = "LayerConfigNewLayerWizard.ui"


class LayerConfigNewLayerWizard(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)

        base_dir = os.path.dirname(os.path.abspath(__file__))
        ui_path = os.path.join(base_dir, UI_FILENAME)
        if not os.path.exists(ui_path):
            raise FileNotFoundError(f"UI file not found: {ui_path}")

        uic.loadUi(ui_path, self)
        self.setWindowTitle("LayerConfig - New Layer From Mapfile")

        db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            DB_FILENAME,
        )
        self.db_path = db_path  # keep a reference for exporters
        self.db = DBAccess(db_path)

        # Internal caches
        self._portal_id_by_index = []  # index -> PortalId
        self._tree_model = None
        self._mapfile_layers = {}  # layer_name -> layer dict
        self._building_tree = False

        # Track current tree selection (for folder checkboxes etc.)
        self._current_node_id = None
        self._current_node_is_folder = False

        # Icon type <-> glyph/icon mapping
        self._icon_type_to_glyph = {
            "Point": "ea0a@font-gis",
            "Line": "ea52@font-gis",
            "Polygon": "ea02@font-gis",
            "Bars": "x-fas fa-bars",
            "Map": "x-fas fa-map",
        }
        # reverse lookup
        self._glyph_to_icon_type = {
            v: k for k, v in self._icon_type_to_glyph.items()
        }

        self._connect_signals()
        self._load_portals()
        self._refresh_all_layers_table()
        self._refresh_portal_layers_table()
        self._refresh_db_layer_combo()

    def _error(self, title: str, message: str):
        """Log an error to console and show a critical popup."""
        print(f"[{title}] {message}")
        QtWidgets.QMessageBox.critical(self, title, message)

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------
    def _connect_signals(self):
        # Tab 1
        if hasattr(self, "btnBrowseMapFile"):
            self.btnBrowseMapFile.clicked.connect(self.on_browse_mapfile)

        if hasattr(self, "btnScanMapFile"):
            self.btnScanMapFile.clicked.connect(self.on_scan_mapfile)

        if hasattr(self, "cmbMapFileLayerNames"):
            self.cmbMapFileLayerNames.currentTextChanged.connect(
                self.on_map_layer_selected
            )

            # Load fields from WFS on demand
        if hasattr(self, "btnLoadFieldsFromWFS"):
            self.btnLoadFieldsFromWFS.clicked.connect(self.on_load_fields_from_wfs)

            # make current Tab 1 layer available to portals
        if hasattr(self, "btnMakeLayerAvailable"):
            self.btnMakeLayerAvailable.clicked.connect(
                self.on_make_layer_available
            )

            # Load existing layers from DB (Tab 1)
        if hasattr(self, "cmbDbLayers"):
            # no signal for change needed yet, we drive via the button
            pass

        if hasattr(self, "btnLoadFromDb"):
            self.btnLoadFromDb.clicked.connect(self.on_load_layer_from_db)

        # Save current Tab 1 state to DB
        if hasattr(self, "btnSaveLayerToDb"):
            self.btnSaveLayerToDb.clicked.connect(self.on_save_layer_to_db_clicked)

        # Tab 2

            # Export layer JSON for current portal (Tab 2)
        if hasattr(self, "btnExportCurrentPortalLayersJson"):
            self.btnExportCurrentPortalLayersJson.clicked.connect(
                self.on_btnExportPortalLayerJson_clicked
            )

            # Export layer JSON for ALL portals (Tab 2)
        if hasattr(self, "btnExportAllPortalsLayersJson"):
            self.btnExportAllPortalsLayersJson.clicked.connect(
                self.on_export_all_portals_layers_json
            )

        if hasattr(self, "tblPortalLayers"):
            self.tblPortalLayers.currentCellChanged.connect(
                self.on_portal_layer_row_changed
            )

        if hasattr(self, "btnAddLayerToPortalAsWms"):
            self.btnAddLayerToPortalAsWms.clicked.connect(
                self.on_add_layer_to_portal_as_wms_clicked
            )
        if hasattr(self, "btnAddLayerToPortalAsWfs"):
            self.btnAddLayerToPortalAsWfs.clicked.connect(
                self.on_add_layer_to_portal_as_wfs_clicked
            )
        if hasattr(self, "btnAddLayerToPortalAsSwitch"):
            self.btnAddLayerToPortalAsSwitch.clicked.connect(
                self.on_add_layer_to_portal_as_switch_clicked
            )
        if hasattr(self, "btnRemoveLayerFromPortal"):
            self.btnRemoveLayerFromPortal.clicked.connect(
                self.on_remove_layer_from_portal_clicked
            )

            # Switch layers (Tab 2)
        if hasattr(self, "btnAddSwitchLayerPortal"):
            self.btnAddSwitchLayerPortal.clicked.connect(
                self.on_add_switch_layer_portal_clicked
            )

        if hasattr(self, "btnRemoveSwitchLayerPortal"):
            self.btnRemoveSwitchLayerPortal.clicked.connect(
                self.on_remove_switch_layer_portal_clicked
            )

        # Tab 3/2
        if hasattr(self, "cmbPortalSelect"):
            self.cmbPortalSelect.currentIndexChanged.connect(self.on_portal_combo_changed)

        if hasattr(self, "cmbPortalSelectLayers"):
            self.cmbPortalSelectLayers.currentIndexChanged.connect(
                self.on_portal_layers_portal_changed
            )

        # Tab 3/2
        # if hasattr(self, "btnSavePortalToDatabase"):
        #     self.btnSavePortalToDatabase.clicked.connect(
        #         self.on_save_portal_to_database
        #     )

            # tree editing
        if hasattr(self, "btnAddFolderNode"):
            self.btnAddFolderNode.clicked.connect(self.on_add_folder_node)

        if hasattr(self, "btnDeleteNode"):
            self.btnDeleteNode.clicked.connect(self.on_delete_selected_node)

            # folder checkboxes
        if hasattr(self, "chkFolderExpanded"):
            self.chkFolderExpanded.toggled.connect(self.on_folder_expanded_toggled)
        if hasattr(self, "chkFolderChecked"):
            self.chkFolderChecked.toggled.connect(self.on_folder_checked_toggled)

            # add selected layer to portal tree
        if hasattr(self, "btnAddLayerToTree"):
            self.btnAddLayerToTree.clicked.connect(self.on_add_layer_to_tree)

            # Export JSON for current portal
        if hasattr(self, "btnExportCurrentPortalJson"):
            self.btnExportCurrentPortalJson.clicked.connect(
                self.on_export_current_portal_json
            )

            # Folder title change
        if hasattr(self, "txtFolderTitle"):
            self.txtFolderTitle.editingFinished.connect(
                self.on_folder_title_edited
                )

            # Folder Id change
        if hasattr(self, "txtFolderId"):
            self.txtFolderId.editingFinished.connect(
                self.on_folder_id_edited
            )

            # Folder title change
        if hasattr(self, "txtLayerTitle"):
            self.txtLayerTitle.editingFinished.connect(
                self.on_layer_title_edited
            )

            # Layer icon type change
        if hasattr(self, "cmbLayerIconType"):
            self.cmbLayerIconType.currentIndexChanged.connect(
                self.on_layer_icon_type_changed
            )

    # ------------------------------------------------------------------
    # WFS
    # ------------------------------------------------------------------

    def fetch_wfs_schema(
        self, layer_name: str, wfs_url: str = None, timeout: int = 180
    ) -> dict:
        """
        Return {field_name: type} from WFS DescribeFeatureType using WFSToDB.
        """
        if not wfs_url:
            wfs_url = DEFAULT_WFS_URL  # <- now http://127.0.0.1:81/mapserver2

        importer = WFSToDB(
            db_path=":memory:",
            wfs_url=wfs_url,
            timeout=timeout,
        )
        return importer.get_schema(layer_name)

    # ------------------------------------------------------------------
    # Tab 1: Mapfile loading
    # ------------------------------------------------------------------
    def on_browse_mapfile(self):
        if not hasattr(self, "txtMapFilePath"):
            return

        start_dir = (
            os.path.dirname(self.txtMapFilePath.text())
            if self.txtMapFilePath.text()
            else os.getcwd()
        )

        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select mapfile",
            start_dir,
            "MapServer mapfiles (*.map);;All files (*)",
        )
        if path:
            self.txtMapFilePath.setText(path)

    def on_scan_mapfile(self):
        if not (
            hasattr(self, "txtMapFilePath") and hasattr(self, "cmbMapFileLayerNames")
        ):
            return

        map_path = self.txtMapFilePath.text().strip()
        if not map_path:
            QtWidgets.QMessageBox.warning(
                self, "No mapfile", "Please select a mapfile first."
            )
            return

        layers_by_name, error = parse_mapfile(map_path)
        if error:
            QtWidgets.QMessageBox.critical(self, "Mapfile error", error)
            self._mapfile_layers = {}
            self.cmbMapFileLayerNames.clear()
            return

        self._mapfile_layers = layers_by_name

        self.cmbMapFileLayerNames.blockSignals(True)
        self.cmbMapFileLayerNames.clear()
        for name in sorted(layers_by_name.keys()):
            self.cmbMapFileLayerNames.addItem(name)
        self.cmbMapFileLayerNames.blockSignals(False)

        if self._mapfile_layers:
            self.cmbMapFileLayerNames.setCurrentIndex(0)
            self.on_map_layer_selected(self.cmbMapFileLayerNames.currentText())

    def on_map_layer_selected(self, layer_name: str):
        layer_name = (layer_name or "").strip()
        if not layer_name:
            return

        lyr = self._mapfile_layers.get(layer_name)
        if lyr is None:
            return

        # Show layer name
        if hasattr(self, "txtLayerName"):
            self.txtLayerName.setText(layer_name)

        # Derive keys and GridXType
        self._derive_keys_from_layer_name(layer_name)

        # Populate styles from mapfile
        self._populate_styles_from_layer(lyr)

        # IMPORTANT: do NOT hit WFS here anymore.
        # Just clear fields/idProperty so the user knows they are not loaded.
        if hasattr(self, "tblFields"):
            self.tblFields.clearContents()
            self.tblFields.setRowCount(0)
        if hasattr(self, "cmbIdProperty"):
            self.cmbIdProperty.clear()

    def _derive_keys_from_layer_name(self, layer_name: str):
        base = layer_name.upper()
        wms_key = f"{base}_WMS"
        vector_key = f"{base}_VECTOR"
        gridxtype = f"pms_{layer_name.lower()}grid"

        if hasattr(self, "txtWmsLayerKey"):
            self.txtWmsLayerKey.setText(wms_key)
        if hasattr(self, "txtVectorLayerKey"):
            self.txtVectorLayerKey.setText(vector_key)
        if hasattr(self, "txtGridXType"):
            self.txtGridXType.setText(gridxtype)

    def _populate_styles_from_layer(self, lyr_dict):
        if not hasattr(self, "tblStyles"):
            return

        styles = extract_styles(lyr_dict)

        tbl = self.tblStyles
        tbl.clearContents()
        tbl.setRowCount(0)

        for idx, (group_name, style_title) in enumerate(styles):
            tbl.insertRow(idx)
            group_item = QtWidgets.QTableWidgetItem(group_name)
            title_item = QtWidgets.QTableWidgetItem(style_title)
            tbl.setItem(idx, 0, group_item)
            tbl.setItem(idx, 1, title_item)

    def on_load_fields_from_wfs(self):
        """
        Called by btnLoadFieldsFromWFS.
        Uses the currently selected FeatureType (layer name) and WFS
        to populate tblFields and cmbIdProperty.

        Column layout in tblFields:

          0 Field name
          1 Is idProperty
          2 Include
          3 Is ToolTip
          4 ToolTip alias

        The field type is stored in the Field name cell's UserRole.
        """
        if not (hasattr(self, "tblFields") and hasattr(self, "cmbIdProperty")):
            return

        layer_name = (
            self.txtLayerName.text().strip() if hasattr(self, "txtLayerName") else ""
        )
        if not layer_name:
            self._error("No layer selected", "Select a layer from the mapfile first.")
            return

        # Optional: need the mapfile layer dict for metadata hints
        lyr_dict = self._mapfile_layers.get(layer_name, {})

        # 1) Get schema from WFS
        try:
            schema = self.fetch_wfs_schema(layer_name)  # {field_name: type}
        except Exception as exc:
            msg = f"Failed to fetch WFS schema for '{layer_name}':\n{exc}"
            self._error("WFS schema error", msg)
            return

        # 2) Optional id hint from mapfile METADATA
        metadata = lyr_dict.get("metadata", {}) or {}
        id_prop = (metadata.get("wfs_featureid") or "").strip() or (
            metadata.get("gml_featureid") or ""
        ).strip()

        tbl = self.tblFields
        tbl.clearContents()
        tbl.setRowCount(0)
        self.cmbIdProperty.clear()

        field_names = list(schema.keys())  # order preserved from DescribeFeatureType

        # Column indices (new layout)
        COL_FIELD = 0
        COL_IDPROP = 1
        COL_INCLUDE = 2
        COL_TOOLTIP = 3
        COL_TOOLTIP_ALIAS = 4

        for idx, fname in enumerate(field_names):
            ftype = schema[fname] or "string"

            tbl.insertRow(idx)

            # Field name (also stash type in UserRole)
            name_item = QtWidgets.QTableWidgetItem(fname)
            name_item.setData(QtCore.Qt.UserRole, ftype)
            tbl.setItem(idx, COL_FIELD, name_item)

            # Is idProperty checkbox
            id_item = QtWidgets.QTableWidgetItem()
            id_item.setFlags(id_item.flags() | QtCore.Qt.ItemIsUserCheckable)
            if id_prop and fname == id_prop:
                id_item.setCheckState(QtCore.Qt.Checked)
            else:
                id_item.setCheckState(QtCore.Qt.Unchecked)
            tbl.setItem(idx, COL_IDPROP, id_item)

            # Include checkbox (for propertyname CSV)
            include_item = QtWidgets.QTableWidgetItem()
            include_item.setFlags(include_item.flags() | QtCore.Qt.ItemIsUserCheckable)
            include_item.setCheckState(QtCore.Qt.Unchecked)
            tbl.setItem(idx, COL_INCLUDE, include_item)

            # Is ToolTip checkbox
            tooltip_item = QtWidgets.QTableWidgetItem()
            tooltip_item.setFlags(tooltip_item.flags() | QtCore.Qt.ItemIsUserCheckable)
            tooltip_item.setCheckState(QtCore.Qt.Unchecked)
            tbl.setItem(idx, COL_TOOLTIP, tooltip_item)

            # ToolTip alias (editable text, default empty for now)
            alias_item = QtWidgets.QTableWidgetItem("")
            tbl.setItem(idx, COL_TOOLTIP_ALIAS, alias_item)

            # Add to idProperty combo
            self.cmbIdProperty.addItem(fname)

        # If we got an id hint, select it in the combo
        if id_prop and self.cmbIdProperty.count() > 0:
            combo_idx = self.cmbIdProperty.findText(id_prop)
            if combo_idx >= 0:
                self.cmbIdProperty.setCurrentIndex(combo_idx)

    #-------------------------------------------------------------------
    # Tab 2
    #-------------------------------------------------------------------

    def _refresh_all_layers_table(self):
        """
        Populate tblAllLayers with ALL layers in the system, plus a summary
        of which portals they are used in.

        Columns:
          0: Layer name (MapLayerName)
          1: BaseLayerKey
          2: In portals  (e.g. 'default: WMS; editor: Switch')
        """
        if not hasattr(self, "tblAllLayers"):
            return

        try:
            all_layers = self.db.get_all_layers()
            usage_rows = self.db.get_layer_portal_usage()
        except Exception as e:
            self._error("Database error", f"Could not load layers: {e}")
            return

        # Build a mapping: portal_usage[BaseLayerKey][PortalKey] = status
        portal_usage = {}
        for row in usage_rows:
            base_key = row["BaseLayerKey"]
            portal_key = row["PortalKey"]
            has_wms = row["HasWms"] or 0
            has_wfs = row["HasWfs"] or 0
            has_switch = row["HasSwitch"] or 0

            if has_switch:
                status = "Switch"
            elif has_wms and has_wfs:
                status = "WMS+WFS"
            elif has_wms:
                status = "WMS"
            elif has_wfs:
                status = "WFS"
            else:
                status = "Off"

            portal_usage.setdefault(base_key, {})[portal_key] = status

        table = self.tblAllLayers
        table.setRowCount(0)
        table.setRowCount(len(all_layers))

        for row_idx, layer in enumerate(all_layers):
            map_name = layer["MapLayerName"]
            base_key = layer["BaseLayerKey"]

            usage_for_layer = portal_usage.get(base_key, {})

            # Build "In portals" string – only portals where status != Off
            fragments = []
            for portal_key in sorted(usage_for_layer.keys()):
                status = usage_for_layer[portal_key]
                if status and status != "Off":
                    fragments.append(f"{portal_key}: {status}")
            in_portals = "; ".join(fragments) if fragments else "—"

            item_name = QtWidgets.QTableWidgetItem(map_name)

            meta = {
                "mapLayerId": layer["MapServerLayerId"],
                "baseLayerKey": base_key,
                "mapLayerName": map_name,
                "services": {
                    "WMS": bool(layer["HasWms"]),
                    "WFS": bool(layer["HasWfs"]),
                    "XYZ": bool(layer["IsXYZ"]),
                },
                "portalUsage": usage_for_layer,
            }
            item_name.setData(QtCore.Qt.UserRole, meta)

            table.setItem(row_idx, 0, item_name)
            table.setItem(row_idx, 1, QtWidgets.QTableWidgetItem(base_key))
            table.setItem(row_idx, 2, QtWidgets.QTableWidgetItem(in_portals))

        table.resizeColumnsToContents()

    def _refresh_db_layer_combo(self):
        """Populate cmbDbLayers with existing MapServerLayers."""
        if not hasattr(self, "cmbDbLayers"):
            return

        self.cmbDbLayers.clear()

        try:
            rows = self.db.get_tab1_layer_list()
        except Exception as exc:
            self._error("Database error", f"Could not load layers from DB:\n{exc}")
            return

        if not rows:
            self.cmbDbLayers.setEnabled(False)
            return

        self.cmbDbLayers.setEnabled(True)

        # Optional placeholder
        self.cmbDbLayers.addItem("-- select layer --", None)

        for row in rows:
            name = row["MapLayerName"]
            base = row["BaseLayerKey"]
            label = f"{name} [{base}]"
            self.cmbDbLayers.addItem(label, row["MapServerLayerId"])

    def on_load_layer_from_db(self):
        """Slot for btnLoadFromDb, loads selected DB layer into Tab 1."""
        if not hasattr(self, "cmbDbLayers"):
            self._error("UI error", "cmbDbLayers is not available in this UI.")
            return

        idx = self.cmbDbLayers.currentIndex()
        layer_id = self.cmbDbLayers.itemData(idx) if idx >= 0 else None
        if not layer_id:
            self._error("No layer selected", "Select a layer from the DB first.")
            return

        try:
            details = self.db.get_tab1_layer_details(int(layer_id))
        except Exception as exc:
            self._error("Database error", f"Could not load layer details:\n{exc}")
            return

        if details is None:
            self._error("Not found", "The selected layer no longer exists in the DB.")
            return

        self._populate_tab1_from_db(details)

    def _populate_tab1_from_db(self, details: dict):
        """Populate Tab 1 controls from a DB layer details dict."""
        layer = details.get("layer")
        wms = details.get("wms")
        wfs = details.get("wfs")
        fields = details.get("fields") or []
        styles = details.get("styles") or []

        if not layer:
            return

        map_name = layer["MapLayerName"]
        base_key = layer["BaseLayerKey"]
        gridxtype = layer["GridXType"] if "GridXType" in layer.keys() else ""

        # Basic text fields
        if hasattr(self, "txtLayerName"):
            self.txtLayerName.setText(map_name)
        if hasattr(self, "txtBaseLayerKey"):
            self.txtBaseLayerKey.setText(base_key)
        if hasattr(self, "txtGridXType"):
            self.txtGridXType.setText(gridxtype or "")

        # WMS / WFS keys from ServiceLayers
        if hasattr(self, "txtWmsLayerKey"):
            self.txtWmsLayerKey.setText(wms["LayerKey"] if wms else "")
        if hasattr(self, "txtVectorLayerKey"):
            self.txtVectorLayerKey.setText(wfs["LayerKey"] if wfs else "")

        # Geom field name - prefer WFS service value, otherwise default from MapServerLayers
        geom_field = None
        if wfs is not None:
            geom_field = wfs["GeomFieldName"]
        if not geom_field and "DefaultGeomFieldName" in layer.keys():
            geom_field = layer["DefaultGeomFieldName"]
        if not geom_field:
            geom_field = "msGeometry"

        if hasattr(self, "txtGeomFieldName"):
            self.txtGeomFieldName.setText(geom_field)

        # Fields table and idProperty combo
        if hasattr(self, "tblFields") and hasattr(self, "cmbIdProperty"):
            tbl = self.tblFields
            tbl.clearContents()
            tbl.setRowCount(0)
            self.cmbIdProperty.clear()

            COL_FIELD = 0
            COL_IDPROP = 1
            COL_INCLUDE = 2
            COL_TOOLTIP = 3
            COL_TOOLTIP_ALIAS = 4

            id_prop_name = ""
            if wfs is not None and wfs["IdPropertyName"]:
                id_prop_name = wfs["IdPropertyName"]

            # Load service-level field config for WFS (include + tooltip + alias)
            wfs_fields = self.db.get_wfs_service_layer_fields(layer["MapServerLayerId"])
            wfs_by_name = {row["FieldName"]: row for row in wfs_fields}

            id_combo_index = -1

            for row_idx, f in enumerate(fields):
                tbl.insertRow(row_idx)

                fname = f["FieldName"]
                ftype = f["FieldType"]
                include_csv = bool(f["IncludeInPropertyCsv"])
                is_id_prop = bool(f["IsIdProperty"])

                # Prefer service-level config if present
                sf = wfs_by_name.get(fname)
                if sf is not None:
                    include_effective = bool(sf["IncludeInPropertyname"])
                    is_tooltip = bool(sf["IsTooltip"])
                    tooltip_alias = sf["TooltipAlias"] or ""
                else:
                    include_effective = include_csv
                    is_tooltip = False
                    tooltip_alias = ""

                # Field name (also stash type in UserRole)
                name_item = QtWidgets.QTableWidgetItem(fname)
                name_item.setData(QtCore.Qt.UserRole, ftype or "string")
                tbl.setItem(row_idx, COL_FIELD, name_item)

                # ID property checkbox
                id_item = QtWidgets.QTableWidgetItem()
                id_item.setFlags(id_item.flags() | QtCore.Qt.ItemIsUserCheckable)
                id_item.setCheckState(
                    QtCore.Qt.Checked
                    if is_id_prop or (id_prop_name and fname == id_prop_name)
                    else QtCore.Qt.Unchecked
                )
                tbl.setItem(row_idx, COL_IDPROP, id_item)

                # Include checkbox
                include_item = QtWidgets.QTableWidgetItem()
                include_item.setFlags(
                    include_item.flags() | QtCore.Qt.ItemIsUserCheckable
                )
                include_item.setCheckState(
                    QtCore.Qt.Checked if include_effective else QtCore.Qt.Unchecked
                )
                tbl.setItem(row_idx, COL_INCLUDE, include_item)

                # Is ToolTip checkbox
                tooltip_item = QtWidgets.QTableWidgetItem()
                tooltip_item.setFlags(
                    tooltip_item.flags() | QtCore.Qt.ItemIsUserCheckable
                )
                tooltip_item.setCheckState(
                    QtCore.Qt.Checked if is_tooltip else QtCore.Qt.Unchecked
                )
                tbl.setItem(row_idx, COL_TOOLTIP, tooltip_item)

                # Tooltip alias
                alias_item = QtWidgets.QTableWidgetItem(tooltip_alias)
                tbl.setItem(row_idx, COL_TOOLTIP_ALIAS, alias_item)

                # IdProperty combo
                self.cmbIdProperty.addItem(fname)
                if fname == id_prop_name and id_combo_index < 0:
                    id_combo_index = self.cmbIdProperty.count() - 1

            if id_combo_index >= 0:
                self.cmbIdProperty.setCurrentIndex(id_combo_index)


        # Styles table
        if hasattr(self, "tblStyles"):
            tbls = self.tblStyles
            tbls.clearContents()
            tbls.setRowCount(0)

            for row_idx, s in enumerate(styles):
                tbls.insertRow(row_idx)
                group_item = QtWidgets.QTableWidgetItem(s["GroupName"])
                title_item = QtWidgets.QTableWidgetItem(s["StyleTitle"])
                tbls.setItem(row_idx, 0, group_item)
                tbls.setItem(row_idx, 1, title_item)

    def on_portal_layers_portal_changed(self, idx: int):
        """
        Called when cmbPortalSelectLayers changes.
        Refreshes both portal entries and the global 'In portals' view.
        """
        self._refresh_portal_layers_table()
        self._refresh_all_layers_table()

    def _get_selected_all_layers_meta(self):
        if not hasattr(self, "tblAllLayers"):
            return None
        row = self.tblAllLayers.currentRow()
        if row < 0:
            return None
        item = self.tblAllLayers.item(row, 0)
        if item is None:
            return None
        return item.data(QtCore.Qt.UserRole) or None

    def on_btnExportPortalLayerJson_clicked(self):
        """
        Export layer JSON for the currently selected portal (Tab 2),
        using the v3 schema and layer_export module.
        """
        portal_key = self._get_current_portal_key()
        if not portal_key:
            self._error("No portal selected", "Please select a portal.")
            return

        out_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select folder to save layer JSON",
            "",
        )
        if not out_dir:
            return

        filename = f"{portal_key}.json"
        out_path = os.path.join(out_dir, filename)

        try:
            # if you've already switched to using self.db.conn, use that here instead
            conn = getattr(self, "db", None).conn if hasattr(self, "db") else sqlite3.connect(self.db_path)
            if conn is None:
                self._error("Export failed", "Database connection is not available.")
                return

            layer_export.export_portal_layer_json(conn, portal_key, out_path)
        except Exception as e:
            self._error(
                "Export failed",
                f"Could not export layer JSON for portal '{portal_key}':\n{e}",
            )
            return

        QtWidgets.QMessageBox.information(
            self,
            "Layer JSON exported",
            f"Layer JSON for portal '{portal_key}' exported to:\n{out_path}",
        )

    def on_export_all_portals_layers_json(self):
        """
        Export layer JSON for all portals defined in the database.
        Uses the same exporter as the single-portal export.
        """
        # Choose target folder once
        out_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select folder to save layer JSON for all portals",
            "",
        )
        if not out_dir:
            return

        try:
            portals = self.db.get_portals()
            if not portals:
                QtWidgets.QMessageBox.warning(
                    self,
                    "No portals defined",
                    "There are no portals in the database to export.",
                )
                return

            conn = self.db.conn
            errors = []
            for row in portals:
                portal_key = row["PortalKey"]
                filename = f"{portal_key}.json"
                out_path = os.path.join(out_dir, filename)
                try:
                    layer_export.export_portal_layer_json(conn, portal_key, out_path)
                except Exception as e:
                    errors.append(f"{portal_key}: {e}")

            if errors:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Export completed with errors",
                    "Some portals failed to export:\n\n" + "\n".join(errors),
                )
            else:
                QtWidgets.QMessageBox.information(
                    self,
                    "Layer JSON exported",
                    f"Layer JSON for {len(portals)} portals exported to:\n{out_dir}",
                )

        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Export failed",
                f"Could not export layer JSON for all portals:\n{e}",
            )

    def on_portal_combo_changed(self, idx):
        """
        Unified handler when either portal combo changes (Tab 2 or Tab 3).
        Keeps both combos in sync and then triggers the existing logic
        for loading portal-specific UI.
        """
        if idx is None or idx < 0:
            return

        sender = self.sender()

        # Mirror the index to the other combo without causing recursion
        if hasattr(self, "cmbPortalSelect") and sender is not self.cmbPortalSelect:
            self.cmbPortalSelect.blockSignals(True)
            self.cmbPortalSelect.setCurrentIndex(idx)
            self.cmbPortalSelect.blockSignals(False)

        if hasattr(self, "cmbPortalSelectLayers") and sender is not self.cmbPortalSelectLayers:
            self.cmbPortalSelectLayers.blockSignals(True)
            self.cmbPortalSelectLayers.setCurrentIndex(idx)
            self.cmbPortalSelectLayers.blockSignals(False)

        # Existing Tab 3 logic: refresh tree etc.
        if hasattr(self, "on_portal_changed"):
            self.on_portal_changed(idx)

        # New Tab 2 hook: refresh "layers for this portal" UI
        if hasattr(self, "on_portal_layers_changed"):
            self.on_portal_layers_changed(idx)

    def _clear_portal_layers_table(self):
        if not hasattr(self, "tblPortalLayers"):
            return
        self.tblPortalLayers.setRowCount(0)
        self.tblPortalLayers.clearContents()

    def _refresh_portal_layers_table(self):
        """
        Populate tblPortalLayers with entries actually in the current portal.

        Columns:
          0: LayerKey (or SwitchKey)
          1: Layer name
          2: Service ('WMS' / 'WFS' / 'Switch')
        """
        if not hasattr(self, "tblPortalLayers"):
            return

        portal_id = self._get_current_portal_id()
        table = self.tblPortalLayers
        table.setRowCount(0)

        if portal_id is None:
            return

        try:
            rows = self.db.get_portal_layer_entries(portal_id)
        except Exception as e:
            self._error("Database error", f"Could not load portal layers: {e}")
            return

        table.setRowCount(len(rows))

        for row_idx, r in enumerate(rows):
            layer_key = r["LayerKey"]
            layer_name = r["LayerName"]
            service = r["Service"]

            item_key = QtWidgets.QTableWidgetItem(layer_key)

            meta = {
                "EntryType": r["EntryType"],
                "LayerKey": layer_key,
                "Service": service,
                "PortalLayerId": r["PortalLayerId"],
                "PortalSwitchLayerId": r["PortalSwitchLayerId"],
            }
            item_key.setData(QtCore.Qt.UserRole, meta)

            table.setItem(row_idx, 0, item_key)
            table.setItem(row_idx, 1, QtWidgets.QTableWidgetItem(layer_name))
            table.setItem(row_idx, 2, QtWidgets.QTableWidgetItem(service))

        table.resizeColumnsToContents()

    def on_portal_layers_changed(self, idx):
        portal_id = self._get_current_portal_id()
        if portal_id is None:
            self._clear_portal_layers_table()
            self._clear_switch_layers_table()
            return

        self._refresh_portal_layers_table()
        self._refresh_switch_layers_table(portal_id)

    def _clear_portal_layer_details(self):
        for name in [
            "txtLayerNamePortal",
            "txtWmsKeyPortal",
            "txtWfsKeyPortal",
            "txtLabelClassPortal",
            "txtOpacityPortal",
        ]:
            if hasattr(self, name):
                getattr(self, name).setText("")

    def on_portal_layer_row_changed(self, current_row, current_col, prev_row, prev_col):
        """
        Update the read-only detail fields on Tab 2 when a row in
        tblPortalLayers is selected.
        """
        if not hasattr(self, "tblPortalLayers"):
            return

        if current_row is None or current_row < 0:
            self._clear_portal_layer_details()
            return

        item0 = self.tblPortalLayers.item(current_row, 0)
        if item0 is None:
            self._clear_portal_layer_details()
            return

        meta = item0.data(QtCore.Qt.UserRole) or {}
        name = meta.get("mapLayerName") or ""
        wms = meta.get("wms")
        wfs = meta.get("wfs")

        wms_key = wms["LayerKey"] if wms else ""
        wfs_key = wfs["LayerKey"] if wfs else ""

        # label class / opacity – prefer WFS, fall back to WMS
        src = wfs or wms or {}
        label_class = src.get("LabelClassName") or ""
        # effective opacity: override if present, else Map default, else Service opacity
        opacity = ""
        if src:
            ov = src.get("OpacityOverride")
            if ov is not None:
                opacity = str(ov)
            else:
                mdef = src.get("MapDefaultOpacity")
                if mdef is not None:
                    opacity = str(mdef)
                else:
                    sop = src.get("Opacity")
                    if sop is not None:
                        opacity = str(sop)

        if hasattr(self, "txtLayerNamePortal"):
            self.txtLayerNamePortal.setText(name)
        if hasattr(self, "txtWmsKeyPortal"):
            self.txtWmsKeyPortal.setText(wms_key)
        if hasattr(self, "txtWfsKeyPortal"):
            self.txtWfsKeyPortal.setText(wfs_key)
        if hasattr(self, "txtLabelClassPortal"):
            self.txtLabelClassPortal.setText(label_class)
        if hasattr(self, "txtOpacityPortal"):
            self.txtOpacityPortal.setText(opacity)

    def on_add_layer_to_portal_as_wms_clicked(self):
        portal_id = self._get_current_portal_id()
        if portal_id is None:
            self._error("No portal selected", "Please select a portal first.")
            return

        meta = self._get_selected_all_layers_meta()
        if not meta:
            self._error("No layer selected", "Select a layer in the global list first.")
            return

        base_key = meta["baseLayerKey"]

        try:
            wms = self.db.get_service_layer_for_base(base_key, "WMS")
            if not wms:
                self._error(
                    "No WMS service",
                    f"No WMS ServiceLayer exists for base '{base_key}'.",
                )
                return

            self.db.ensure_portal_layer(portal_id, wms["ServiceLayerId"])
        except Exception as e:
            self._error(
                "Failed to add layer",
                f"Could not add '{base_key}' as WMS to this portal:\n{e}",
            )
            return

        self._refresh_portal_layers_table()
        self._refresh_all_layers_table()

    def on_add_layer_to_portal_as_wfs_clicked(self):
        portal_id = self._get_current_portal_id()
        if portal_id is None:
            self._error("No portal selected", "Please select a portal first.")
            return

        meta = self._get_selected_all_layers_meta()
        if not meta:
            self._error("No layer selected", "Select a layer in the global list first.")
            return

        base_key = meta["baseLayerKey"]

        try:
            wfs = self.db.get_service_layer_for_base(base_key, "WFS")
            if not wfs:
                self._error(
                    "No WFS service",
                    f"No WFS ServiceLayer exists for base '{base_key}'.",
                )
                return

            self.db.ensure_portal_layer(portal_id, wfs["ServiceLayerId"])
        except Exception as e:
            self._error(
                "Failed to add layer",
                f"Could not add '{base_key}' as WFS to this portal:\n{e}",
            )
            return

        self._refresh_portal_layers_table()
        self._refresh_all_layers_table()

    def on_add_layer_to_portal_as_switch_clicked(self):
        portal_id = self._get_current_portal_id()
        if portal_id is None:
            self._error("No portal selected", "Please select a portal first.")
            return

        meta = self._get_selected_all_layers_meta()
        if not meta:
            self._error("No layer selected", "Select a layer in the global list first.")
            return

        base_key = meta["baseLayerKey"]

        # Default switch key suggestion
        default_switch_key = f"{base_key}_SWITCH"

        switch_key, ok = QtWidgets.QInputDialog.getText(
            self,
            "Switch key",
            "Enter a switch layer key:",
            QtWidgets.QLineEdit.Normal,
            default_switch_key,
        )
        if not ok or not switch_key.strip():
            return

        switch_key = switch_key.strip()

        try:
            self.db.ensure_switch_for_base(
                portal_id=portal_id,
                base_layer_key=base_key,
                switch_key=switch_key,
                vector_features_min_scale=50000,
            )
        except Exception as e:
            self._error(
                "Failed to add switchlayer",
                f"Could not add switchlayer for '{base_key}':\n{e}",
            )
            return

        self._refresh_portal_layers_table()
        self._refresh_all_layers_table()

    def on_remove_layer_from_portal_clicked(self):
        portal_id = self._get_current_portal_id()
        if portal_id is None:
            self._error("No portal selected", "Please select a portal first.")
            return

        meta = self._get_selected_all_layers_meta()
        if not meta:
            self._error("No layer selected", "Select a layer in the global list first.")
            return

        base_key = meta["baseLayerKey"]

        reply = QtWidgets.QMessageBox.question(
            self,
            "Remove from portal",
            f"Remove all usages of base layer '{base_key}' from this portal?\n"
            f"(WMS, WFS and any switches will be removed.)",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return

        try:
            self.db.remove_portal_usage_for_base(portal_id, base_key)
        except Exception as e:
            self._error(
                "Failed to remove layer",
                f"Could not remove '{base_key}' from this portal:\n{e}",
            )
            return

        self._refresh_portal_layers_table()
        self._refresh_all_layers_table()

    #--------------------switch layers----------------------------

    def _clear_switch_layers_table(self):
        if not hasattr(self, "tblSwitchLayersPortal"):
            return
        self.tblSwitchLayersPortal.setRowCount(0)
        self.tblSwitchLayersPortal.clearContents()

    def _refresh_switch_layers_table(self, portal_id: int):
        """
        Populate tblSwitchLayersPortal with one row per switchlayer in this portal.

        Columns:
          0: Switch key
          1: WMS layer key (child)
          2: WFS layer key (child)
        """
        if not hasattr(self, "tblSwitchLayersPortal"):
            return

        rows = self.db.get_portal_switch_layers(portal_id)

        table = self.tblSwitchLayersPortal
        table.setRowCount(0)

        table.setRowCount(len(rows))
        for row_idx, r in enumerate(rows):
            switch_key = r["SwitchKey"]
            wms_key = r["WmsLayerKey"] or ""
            wfs_key = r["WfsLayerKey"] or ""

            item0 = QtWidgets.QTableWidgetItem(switch_key)
            # store the primary key so we can delete later
            meta = {
                "PortalSwitchLayerId": r["PortalSwitchLayerId"],
                "SwitchKey": switch_key,
            }
            item0.setData(QtCore.Qt.UserRole, meta)

            table.setItem(row_idx, 0, item0)
            table.setItem(row_idx, 1, QtWidgets.QTableWidgetItem(wms_key))
            table.setItem(row_idx, 2, QtWidgets.QTableWidgetItem(wfs_key))

        table.resizeColumnsToContents()

    def on_add_switch_layer_portal_clicked(self):
        """
        Create a new switchlayer for the current portal.

        Behaviour:
          - uses the currently selected row in tblPortalLayers as the base
            (must have both WMS and WFS)
          - asks for a switchKey
          - inserts into PortalSwitchLayers + PortalSwitchLayerChildren
        """
        portal_id = self._get_current_portal_id()
        if portal_id is None:
            self._error("No portal selected", "Please select a portal first.")
            return

        if not hasattr(self, "tblPortalLayers"):
            self._error("UI error", "tblPortalLayers widget not found.")
            return

        row = self.tblPortalLayers.currentRow()
        if row < 0:
            self._error(
                "No base layer selected",
                "Select a row in the portal layers table (with both WMS and WFS) first.",
            )
            return

        item0 = self.tblPortalLayers.item(row, 0)
        if item0 is None:
            self._error("No base layer selected", "Selected row has no data.")
            return

        meta = item0.data(QtCore.Qt.UserRole) or {}
        wms = meta.get("wms")
        wfs = meta.get("wfs")

        if not wms or not wfs:
            self._error(
                "Cannot create switchlayer",
                "Selected base layer must have both WMS and WFS variants in this portal.",
            )
            return

        base_layer_name = meta.get("mapLayerName") or ""
        default_switch_key = f"{base_layer_name}_SWITCH" if base_layer_name else "NEW_SWITCH"

        switch_key, ok = QtWidgets.QInputDialog.getText(
            self,
            "Switch key",
            "Enter a switch layer key:",
            QtWidgets.QLineEdit.Normal,
            default_switch_key,
        )
        if not ok or not switch_key.strip():
            return

        switch_key = switch_key.strip()

        try:
            self.db.create_switch_layer(
                portal_id=portal_id,
                switch_key=switch_key,
                wms_service_layer_id=wms["ServiceLayerId"],
                wfs_service_layer_id=wfs["ServiceLayerId"],
                vector_features_min_scale=50000,
            )
        except Exception as e:
            self._error(
                "Failed to create switchlayer",
                f"Could not create switchlayer '{switch_key}':\n{e}",
            )
            return

        # Refresh switchlayers table
        self._refresh_switch_layers_table(portal_id)

    def on_remove_switch_layer_portal_clicked(self):
        """
        Remove the selected switchlayer from the current portal.
        """
        portal_id = self._get_current_portal_id()
        if portal_id is None:
            self._error("No portal selected", "Please select a portal first.")
            return

        if not hasattr(self, "tblSwitchLayersPortal"):
            self._error("UI error", "tblSwitchLayersPortal widget not found.")
            return

        row = self.tblSwitchLayersPortal.currentRow()
        if row < 0:
            self._error(
                "No switchlayer selected",
                "Select a switchlayer in the table first.",
            )
            return

        item0 = self.tblSwitchLayersPortal.item(row, 0)
        if item0 is None:
            self._error("No switchlayer selected", "Selected row has no data.")
            return

        meta = item0.data(QtCore.Qt.UserRole) or {}
        psl_id = meta.get("PortalSwitchLayerId")
        switch_key = meta.get("SwitchKey") or ""

        if psl_id is None:
            self._error("Internal error", "Switchlayer row has no PortalSwitchLayerId.")
            return

        reply = QtWidgets.QMessageBox.question(
            self,
            "Remove switchlayer",
            f"Remove switchlayer '{switch_key}' from this portal?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return

        try:
            self.db.delete_switch_layer(psl_id)
        except Exception as e:
            self._error(
                "Failed to remove switchlayer",
                f"Could not remove switchlayer '{switch_key}':\n{e}",
            )
            return

        self._refresh_switch_layers_table(portal_id)

    # ------------------------------------------------------------------
    # Tab 3: portals, tree, available layers
    # ------------------------------------------------------------------

    def _get_current_portal_id(self):
        """
        Return the currently selected PortalId, or None if nothing valid
        is selected.
        Prefers cmbPortalSelectLayers (Tab 2), falls back to cmbPortalSelect (Tab 3).
        """
        idx = -1

        if hasattr(self, "cmbPortalSelectLayers") and self.cmbPortalSelectLayers.count() > 0:
            idx = self.cmbPortalSelectLayers.currentIndex()
        elif hasattr(self, "cmbPortalSelect") and self.cmbPortalSelect.count() > 0:
            idx = self.cmbPortalSelect.currentIndex()

        if idx < 0 or idx >= len(getattr(self, "_portal_id_by_index", [])):
            return None

        return self._portal_id_by_index[idx]

    def _get_current_portal_key(self):
        """
        Return the PortalKey for the currently selected portal, or None
        if nothing valid is selected.
        """
        portal_id = self._get_current_portal_id()
        if portal_id is None:
            return None

        cur = self.db.conn.execute(
            "SELECT PortalKey FROM Portals WHERE PortalId = ?",
            (portal_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return row["PortalKey"]

    def _load_portals(self):
        """
        Populate both portal selection combos (Tab 2 and Tab 3) from the
        Portals table, keeping a shared _portal_id_by_index list.
        """
        self._portal_id_by_index = []

        portals = self.db.get_portals()  # expects rows with PortalId, PortalKey, PortalTitle

        # Clear existing items if widgets exist
        if hasattr(self, "cmbPortalSelect"):
            self.cmbPortalSelect.blockSignals(True)
            self.cmbPortalSelect.clear()
            self.cmbPortalSelect.blockSignals(False)

        if hasattr(self, "cmbPortalSelectLayers"):
            self.cmbPortalSelectLayers.blockSignals(True)
            self.cmbPortalSelectLayers.clear()
            self.cmbPortalSelectLayers.blockSignals(False)

        for idx, row in enumerate(portals):
            portal_id = row["PortalId"]
            portal_key = row["PortalKey"]
            portal_title = row["PortalTitle"]

            self._portal_id_by_index.append(portal_id)

            label = f"{portal_title} ({portal_key})"

            if hasattr(self, "cmbPortalSelect"):
                self.cmbPortalSelect.addItem(label)

            if hasattr(self, "cmbPortalSelectLayers"):
                self.cmbPortalSelectLayers.addItem(label)

    def on_portal_changed(self, index):
        if index < 0 or index >= len(self._portal_id_by_index):
            return

        portal_id = self._portal_id_by_index[index]
        self._load_portal_tree(portal_id)
        self._load_available_layers(portal_id)

    def _set_tree_model(self, model):
        self._tree_model = model
        self.treePortalLayers.setModel(model)
        self.treePortalLayers.setHeaderHidden(False)
        self.treePortalLayers.header().setSectionResizeMode(
            0, QtWidgets.QHeaderView.Stretch
        )
        self.treePortalLayers.header().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeToContents
        )

        sel_model = self.treePortalLayers.selectionModel()
        if sel_model is not None:
            sel_model.selectionChanged.connect(self.on_tree_selection_changed)

        # NEW: persist folder renames
        if self._tree_model is not None:
            self._tree_model.itemChanged.connect(self.on_tree_item_changed)

    def _load_portal_tree(self, portal_id):
        rows = self.db.get_portal_tree(portal_id)

        self._building_tree = True
        try:
            model = QtGui.QStandardItemModel()
            model.setHorizontalHeaderLabels(["Title", "LayerKey"])

            items_by_id = {}

            for row in rows:
                is_folder = bool(row["IsFolder"])
                if is_folder:
                    title = row["FolderTitle"]
                    layer_key = ""
                else:
                    title = row["LayerKey"]
                    layer_key = row["LayerKey"] or ""

                title_item = QtGui.QStandardItem(title if title else "")
                layer_item = QtGui.QStandardItem(layer_key)

                # Custom metadata
                title_item.setData(row["PortalTreeNodeId"], QtCore.Qt.UserRole)
                title_item.setData(is_folder, QtCore.Qt.UserRole + 1)
                title_item.setData(row["LayerKey"], QtCore.Qt.UserRole + 2)

                # Only folders are editable by the user
                title_item.setEditable(is_folder)
                layer_item.setEditable(False)

                items_by_id[row["PortalTreeNodeId"]] = (title_item, layer_item)

            root = model.invisibleRootItem()
            for row in rows:
                node_id = row["PortalTreeNodeId"]
                parent_id = row["ParentNodeId"]
                title_item, layer_item = items_by_id[node_id]

                if parent_id is None:
                    root.appendRow([title_item, layer_item])
                else:
                    parent_items = items_by_id.get(parent_id)
                    if parent_items is None:
                        root.appendRow([title_item, layer_item])
                    else:
                        parent_title_item = parent_items[0]
                        parent_title_item.appendRow([title_item, layer_item])

            self._set_tree_model(model)
            self.treePortalLayers.expandAll()
            self._clear_node_details()
        finally:
            self._building_tree = False

    def _get_selected_tree_node(self):
        """
        Return (node_id, is_folder) for the currently selected node in the portal tree,
        or (None, None) if nothing valid is selected.
        We always resolve to column 0 so we can read the custom data we stored there.
        """
        if not hasattr(self, "treePortalLayers") or self._tree_model is None:
            return None, None

        sel_model = self.treePortalLayers.selectionModel()
        if sel_model is None:
            return None, None

        indexes = sel_model.selectedIndexes()
        if not indexes:
            return None, None

        idx = indexes[0]
        # force column 0 so we land on the title item that has our UserRole data
        idx0 = idx.sibling(idx.row(), 0)
        item = self._tree_model.itemFromIndex(idx0)
        if item is None:
            return None, None

        node_id = item.data(QtCore.Qt.UserRole)
        is_folder = bool(item.data(QtCore.Qt.UserRole + 1))
        return node_id, is_folder

    def on_tree_selection_changed(self, selected, _deselected):
        indexes = selected.indexes()
        if not indexes:
            self._current_node_id = None
            self._current_node_is_folder = False
            self._clear_node_details()
            return

        idx = indexes[0]
        item = self._tree_model.itemFromIndex(idx)
        if item is None:
            self._current_node_id = None
            self._current_node_is_folder = False
            self._clear_node_details()
            return

        node_id = item.data(QtCore.Qt.UserRole)
        is_folder = bool(item.data(QtCore.Qt.UserRole + 1))

        self._current_node_id = node_id
        self._current_node_is_folder = is_folder

        if node_id is None:
            self._clear_node_details()
            return

        # Fetch full row for this node
        cur = self.db.conn.execute(
            "SELECT * FROM PortalTreeNodes WHERE PortalTreeNodeId = ?",
            (node_id,),
        )
        row = cur.fetchone()
        if row is None:
            self._clear_node_details()
            return

        if is_folder:
            self._populate_folder_details(row)
            self._populate_layer_details(None)
        else:
            self._populate_folder_details(None)
            self._populate_layer_details(row)

    def on_tree_item_changed(self, item: QtGui.QStandardItem):
        """
        Persist folder title edits from the tree into PortalTreeNodes.FolderTitle,
        and reflect the change in txtFolderTitle when the edited folder is selected.
        """
        # Ignore changes while we are building the model
        if getattr(self, "_building_tree", False):
            return

        # Only care about the "Title" column (0)
        if item.column() != 0:
            return

        node_id = item.data(QtCore.Qt.UserRole)
        is_folder = bool(item.data(QtCore.Qt.UserRole + 1))

        # Only folders have editable titles
        if not is_folder or node_id is None:
            return

        new_title = (item.text() or "").strip()

        # Update DB
        conn = self.db.conn
        conn.execute(
            "UPDATE PortalTreeNodes SET FolderTitle = ? WHERE PortalTreeNodeId = ?",
            (new_title, node_id),
        )
        conn.commit()

        # If this node is currently selected, update the folder details panel
        if hasattr(self, "treePortalLayers") and hasattr(self, "txtFolderTitle"):
            sel_model = self.treePortalLayers.selectionModel()
            if sel_model is not None:
                sel_indexes = sel_model.selectedIndexes()
                if sel_indexes:
                    # compare against the selected index in column 0
                    selected_idx0 = sel_indexes[0].sibling(sel_indexes[0].row(), 0)
                    current_idx = self._tree_model.indexFromItem(item)
                    if current_idx == selected_idx0:
                        self.txtFolderTitle.setText(new_title)

    def _clear_node_details(self):
        self._populate_folder_details(None)
        self._populate_layer_details(None)

    def _populate_folder_details(self, row):
        if not hasattr(self, "groupBox_folderDetails"):
            return

        if row is None or not bool(row["IsFolder"]):
            self.groupBox_folderDetails.setEnabled(False)

            if hasattr(self, "txtFolderId"):
                self.txtFolderId.blockSignals(True)
                self.txtFolderId.clear()
                self.txtFolderId.blockSignals(False)

            if hasattr(self, "txtFolderTitle"):
                self.txtFolderId.blockSignals(True)
                self.txtFolderTitle.clear()
                self.txtFolderId.blockSignals(False)

            if hasattr(self, "chkFolderExpanded"):
                self.chkFolderExpanded.blockSignals(True)
                self.chkFolderExpanded.setChecked(False)
                self.chkFolderExpanded.blockSignals(False)

            if hasattr(self, "chkFolderChecked"):
                self.chkFolderChecked.blockSignals(True)
                self.chkFolderChecked.setChecked(False)
                self.chkFolderChecked.blockSignals(False)

            return

        self.groupBox_folderDetails.setEnabled(True)

        # FolderId
        if hasattr(self, "txtFolderId"):
            self.txtFolderId.blockSignals(True)
            self.txtFolderId.setText(row["FolderId"] or "")
            self.txtFolderId.blockSignals(False)

        # Title
        if hasattr(self, "txtFolderTitle"):
            self.txtFolderTitle.blockSignals(True)
            self.txtFolderTitle.setText(row["FolderTitle"] or "")
            self.txtFolderTitle.blockSignals(False)

        # Expanded / checked
        if hasattr(self, "chkFolderExpanded"):
            self.chkFolderExpanded.blockSignals(True)
            self.chkFolderExpanded.setChecked(bool(row["ExpandedDefault"]))
            self.chkFolderExpanded.blockSignals(False)

        if hasattr(self, "chkFolderChecked"):
            self.chkFolderChecked.blockSignals(True)
            self.chkFolderChecked.setChecked(bool(row["CheckedDefault"]))
            self.chkFolderChecked.blockSignals(False)

    def on_add_folder_node(self):
        """
        Add a new folder node into the portal tree.

        Behaviour:
        - If a folder is selected: new folder is added as a child of that folder.
        - If a layer node is selected: new folder is added as a sibling (same parent).
        - If nothing is selected: new folder is added at the root for this portal.
        """
        if not hasattr(self, "cmbPortalSelect") or not hasattr(
            self, "treePortalLayers"
        ):
            return

        if not getattr(self, "_portal_id_by_index", None):
            self._error("No portal", "No portals are configured.")
            return

        portal_index = self.cmbPortalSelect.currentIndex()
        if portal_index < 0 or portal_index >= len(self._portal_id_by_index):
            self._error("No portal", "Select a portal first.")
            return

        portal_id = self._portal_id_by_index[portal_index]

        conn = self.db.conn

        # Determine parent node based on current selection
        node_id, is_folder = self._get_selected_tree_node()

        parent_node_id = None

        if node_id is not None:
            # If selection is a folder: new folder is a child
            if is_folder:
                parent_node_id = node_id
            else:
                # If selection is a layer: new folder is a sibling (same parent)
                cur = conn.execute(
                    "SELECT ParentNodeId FROM PortalTreeNodes WHERE PortalTreeNodeId = ?",
                    (node_id,),
                )
                row = cur.fetchone()
                parent_node_id = row["ParentNodeId"] if row else None

        # Compute next DisplayOrder among siblings
        if parent_node_id is None:
            cur = conn.execute(
                """
                SELECT COALESCE(MAX(DisplayOrder), 0) + 1 AS NextOrd
                FROM PortalTreeNodes
                WHERE PortalId = ? AND ParentNodeId IS NULL
                """,
                (portal_id,),
            )
        else:
            cur = conn.execute(
                """
                SELECT COALESCE(MAX(DisplayOrder), 0) + 1 AS NextOrd
                FROM PortalTreeNodes
                WHERE PortalId = ? AND ParentNodeId = ?
                """,
                (portal_id, parent_node_id),
            )

        row = cur.fetchone()
        next_order = row["NextOrd"] if row and row["NextOrd"] is not None else 1

        # Insert the new folder
        cur = conn.execute(
            """
            INSERT INTO PortalTreeNodes
                (PortalId, ParentNodeId, IsFolder,
                 FolderTitle, LayerKey, Glyph, Tooltip,
                 ExpandedDefault, CheckedDefault, DisplayOrder)
            VALUES (?, ?, 1,
                    ?, NULL, NULL, NULL,
                    1, 0, ?)
            """,
            (portal_id, parent_node_id, "New folder", next_order),
        )
        conn.commit()

        # For now just reload the tree; user can rename via Folder Properties
        self._load_portal_tree(portal_id)

    def on_delete_selected_node(self):
        """
        Delete the selected node and all its descendants from the portal tree,
        after a confirmation dialog.
        """
        if not hasattr(self, "cmbPortalSelect") or not hasattr(
            self, "treePortalLayers"
        ):
            return

        if not getattr(self, "_portal_id_by_index", None):
            self._error("No portal", "No portals are configured.")
            return

        portal_index = self.cmbPortalSelect.currentIndex()
        if portal_index < 0 or portal_index >= len(self._portal_id_by_index):
            self._error("No portal", "Select a portal first.")
            return

        portal_id = self._portal_id_by_index[portal_index]

        node_id, _is_folder = self._get_selected_tree_node()
        if node_id is None:
            self._error("No selection", "Select a folder or layer in the tree first.")
            return

        reply = QtWidgets.QMessageBox.question(
            self,
            "Delete node",
            "Delete the selected node and all of its child nodes from this portal tree?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return

        conn = self.db.conn

        # Recursive delete of the subtree using a CTE
        conn.execute(
            """
            WITH RECURSIVE to_delete AS (
                SELECT PortalTreeNodeId
                FROM PortalTreeNodes
                WHERE PortalTreeNodeId = ?

                UNION ALL

                SELECT p.PortalTreeNodeId
                FROM PortalTreeNodes p
                JOIN to_delete td
                  ON p.ParentNodeId = td.PortalTreeNodeId
            )
            DELETE FROM PortalTreeNodes
            WHERE PortalTreeNodeId IN (SELECT PortalTreeNodeId FROM to_delete)
            """,
            (node_id,),
        )
        conn.commit()

        self._load_portal_tree(portal_id)

    def _populate_layer_details(self, row):
        if not hasattr(self, "groupBox_layerDetails"):
            return

        if row is None or bool(row["IsFolder"]):
            self.groupBox_layerDetails.setEnabled(False)

            if hasattr(self, "txtLayerKey"):
                self.txtLayerKey.clear()
            if hasattr(self, "txtLayerTitle"):
                self.txtLayerTitle.clear()
            if hasattr(self, "txtLayerTooltip"):
                self.txtLayerTooltip.clear()
            if hasattr(self, "cmbLayerIconType"):
                self.cmbLayerIconType.blockSignals(True)
                self.cmbLayerIconType.setCurrentIndex(-1)
                self.cmbLayerIconType.blockSignals(False)

            return

        self.groupBox_layerDetails.setEnabled(True)

        if hasattr(self, "txtLayerKey"):
            self.txtLayerKey.setText(row["LayerKey"] or "")

        # Display title from LayerTitle
        if hasattr(self, "txtLayerTitle"):
            if "LayerTitle" in row.keys():
                self.txtLayerTitle.setText(row["LayerTitle"] or "")
            else:
                self.txtLayerTitle.setText("")
        
        # Tooltip
        if hasattr(self, "txtLayerTooltip"):
            self.txtLayerTooltip.setPlainText(row["Tooltip"] or "")

        # Icon type combo based on Glyph/IconCls
        if hasattr(self, "cmbLayerIconType"):
            glyph = row["Glyph"] or ""
            icon_type = self._glyph_to_icon_type.get(glyph)
            self.cmbLayerIconType.blockSignals(True)
            if icon_type is None:
                # unknown / empty glyph: no selection
                self.cmbLayerIconType.setCurrentIndex(-1)
            else:
                # find that text in the combo
                idx = self.cmbLayerIconType.findText(icon_type)
                self.cmbLayerIconType.setCurrentIndex(idx)
            self.cmbLayerIconType.blockSignals(False)

    def _load_available_layers(self, portal_id):
        if not hasattr(self, "listAvailableLayers"):
            return

        self.listAvailableLayers.clear()

        used_keys = self.db.get_portal_used_layer_keys(portal_id)
        all_layers = self.db.get_service_layers()

        for row in all_layers:
            if row["LayerKey"] in used_keys:
                continue
            label = f"{row['LayerKey']} ({row['ServiceType']})"
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.UserRole, row["LayerKey"])
            item.setData(QtCore.Qt.UserRole + 1, row["ServiceLayerId"])
            self.listAvailableLayers.addItem(item)

    def on_add_layer_to_tree(self):
        """
        Add the selected layer from listAvailableLayers into the portal tree
        under the currently selected folder (or as a sibling of a selected
        layer, or as a root node if nothing is selected).
        """
        portal_id = self._get_current_portal_id()
        if portal_id is None:
            self._error("No portal selected", "Select a portal first.")
            return

        if not hasattr(self, "listAvailableLayers"):
            self._error("UI error", "Available layers list is missing.")
            return

        item = self.listAvailableLayers.currentItem()
        if item is None:
            self._error(
                "No layer selected",
                "Select a layer in 'Available Layers' before adding it to the tree.",
            )
            return

        layer_key = item.data(QtCore.Qt.UserRole)
        if not layer_key:
            self._error("Missing LayerKey", "Selected item has no LayerKey.")
            return

        # Determine parent node: folder -> child; layer -> sibling; nothing -> root
        parent_node_id = None
        display_order = 1

        if hasattr(self, "treePortalLayers") and self._tree_model is not None:
            sel = self.treePortalLayers.selectionModel()
            if sel is not None:
                indexes = sel.selectedIndexes()
                if indexes:
                    idx = indexes[0]
                    tree_item = self._tree_model.itemFromIndex(idx)
                    if tree_item is not None:
                        node_id = tree_item.data(QtCore.Qt.UserRole)
                        is_folder = bool(tree_item.data(QtCore.Qt.UserRole + 1))

                        if is_folder:
                            # Add as child of the selected folder
                            parent_node_id = node_id
                        else:
                            # Add as sibling of the selected layer (same parent)
                            parent_item = tree_item.parent()
                            if parent_item is not None:
                                parent_node_id = parent_item.data(QtCore.Qt.UserRole)
                            else:
                                parent_node_id = None  # top-level sibling

        # Compute DisplayOrder among siblings
        conn = self.db.conn
        if parent_node_id is None:
            cur = conn.execute(
                """
                SELECT COALESCE(MAX(DisplayOrder), 0) AS max_order
                FROM PortalTreeNodes
                WHERE PortalId = ? AND ParentNodeId IS NULL
                """,
                (portal_id,),
            )
        else:
            cur = conn.execute(
                """
                SELECT COALESCE(MAX(DisplayOrder), 0) AS max_order
                FROM PortalTreeNodes
                WHERE PortalId = ? AND ParentNodeId = ?
                """,
                (portal_id, parent_node_id),
            )
        row = cur.fetchone()
        max_order = row["max_order"] if row is not None else 0
        display_order = max_order + 1

        try:
            conn.execute(
                """
                INSERT INTO PortalTreeNodes
                    (PortalId,
                     ParentNodeId,
                     IsFolder,
                     FolderTitle,
                     LayerKey,
                     Glyph,
                     Tooltip,
                     ExpandedDefault,
                     CheckedDefault,
                     DisplayOrder)
                VALUES (?, ?, 0, NULL, ?, '', '', 0, 0, ?)
                """,
                (portal_id, parent_node_id, layer_key, display_order),
            )
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            self._error(
                "Error adding layer to tree",
                f"Failed to insert PortalTreeNode for {layer_key}:\n{exc}",
            )
            return

        # Reload tree + available layers for this portal
        self._load_portal_tree(portal_id)
        self._load_available_layers(portal_id)

        # Optionally: select the newly added node (best effort, not critical)
        # We just find the first row with this layer_key under this portal.
        try:
            model = self._tree_model
            if model is not None:
                root = model.invisibleRootItem()

                def _walk(item):
                    for r in range(item.rowCount()):
                        t_item = item.child(r, 0)
                        l_item = item.child(r, 1)
                        if l_item and l_item.text() == layer_key:
                            return t_item.index()
                        child_idx = _walk(t_item)
                        if child_idx is not None:
                            return child_idx
                    return None

                idx = _walk(root)
                if idx is not None:
                    self.treePortalLayers.setCurrentIndex(idx)
        except Exception:
            # If selection fails, we do not care; DB is already correct.
            pass

    def on_folder_expanded_toggled(self, checked: bool):
        """
        Persist ExpandedDefault for the currently selected folder node.
        """
        node_id = self._current_node_id
        if not self._current_node_is_folder or node_id is None:
            return

        try:
            self.db.conn.execute(
                "UPDATE PortalTreeNodes SET ExpandedDefault = ? WHERE PortalTreeNodeId = ?",
                (1 if checked else 0, node_id),
            )
            self.db.conn.commit()
        except Exception as exc:
            self._error(
                "Error saving folder", f"Failed to update ExpandedDefault:\n{exc}"
            )

    def on_folder_checked_toggled(self, checked: bool):
        """
        Persist CheckedDefault for the currently selected folder node.
        """
        node_id = self._current_node_id
        if not self._current_node_is_folder or node_id is None:
            return

        try:
            self.db.conn.execute(
                "UPDATE PortalTreeNodes SET CheckedDefault = ? WHERE PortalTreeNodeId = ?",
                (1 if checked else 0, node_id),
            )
            self.db.conn.commit()
        except Exception as exc:
            self._error(
                "Error saving folder", f"Failed to update CheckedDefault:\n{exc}"
            )

    def on_folder_title_edited(self):
        """
        Persist a folder's title when edited in txtFolderTitle,
        and update the tree node's text so the UI stays in sync.
        """
        node_id = getattr(self, "_current_node_id", None)
        is_folder = getattr(self, "_current_node_is_folder", False)
        if node_id is None or not is_folder:
            return

        if not hasattr(self, "txtFolderTitle"):
            return

        new_title = (self.txtFolderTitle.text() or "").strip()

        try:
            # Update DB
            self.db.conn.execute(
                "UPDATE PortalTreeNodes SET FolderTitle = ? WHERE PortalTreeNodeId = ?",
                (new_title, node_id),
            )
            self.db.conn.commit()
        except Exception as exc:
            self._error(
                "Error updating folder title",
                f"Failed to save folder title:\n{exc}",
            )
            return

        # Update the selected tree item title
        index = self.treePortalLayers.currentIndex()
        if not index.isValid():
            return

        model = self.treePortalLayers.model()
        item = model.itemFromIndex(index)
        if item:
            item.setText(new_title)

    def on_folder_id_edited(self):
        """
        Persist FolderId for the currently selected folder node.
        """
        node_id = getattr(self, "_current_node_id", None)
        is_folder = getattr(self, "_current_node_is_folder", False)
        if node_id is None or not is_folder:
            return

        if not hasattr(self, "txtFolderId"):
            return

        folder_id = (self.txtFolderId.text() or "").strip()

        try:
            self.db.conn.execute(
                "UPDATE PortalTreeNodes SET FolderId = ? WHERE PortalTreeNodeId = ?",
                (folder_id, node_id),
            )
            self.db.conn.commit()
        except Exception as exc:
            self._error(
                "Error saving folder",
                f"Failed to update FolderId:\n{exc}",
            )

    def on_layer_title_edited(self):
        """
        Persist LayerTitle for the currently selected layer node.
        """
        node_id = getattr(self, "_current_node_id", None)
        is_folder = getattr(self, "_current_node_is_folder", False)
        if node_id is None or is_folder:
            return

        if not hasattr(self, "txtLayerTitle"):
            return

        title = (self.txtLayerTitle.text() or "").strip()

        try:
            self.db.conn.execute(
                "UPDATE PortalTreeNodes SET LayerTitle = ? WHERE PortalTreeNodeId = ?",
                (title, node_id),
            )
            self.db.conn.commit()
        except Exception as exc:
            self._error(
                "Error saving layer title",
                f"Failed to update LayerTitle:\n{exc}",
            )

    def on_layer_icon_type_changed(self, index: int):
        """
        Persist Glyph/IconCls based on selected icon type for current layer node.
        """
        if index < 0:
            return

        node_id = getattr(self, "_current_node_id", None)
        is_folder = getattr(self, "_current_node_is_folder", False)
        if node_id is None or is_folder:
            return

        if not hasattr(self, "cmbLayerIconType"):
            return

        icon_type = self.cmbLayerIconType.currentText()
        glyph = self._icon_type_to_glyph.get(icon_type)
        if glyph is None:
            return

        try:
            self.db.conn.execute(
                "UPDATE PortalTreeNodes SET Glyph = ? WHERE PortalTreeNodeId = ?",
                (glyph, node_id),
            )
            self.db.conn.commit()
        except Exception as exc:
            self._error(
                "Error saving layer icon",
                f"Failed to update Glyph for node {node_id}:\n{exc}",
            )

    def _build_portal_tree_file_json(self, portal_id: int) -> dict:
        """
        Build a tree.json-style structure for the given portal, matching
        the existing MapMaker tree schema:

        {
          "defaults": { "general": { "leaf": true } },
          "treeConfig": {
            "id": "root",
            "leaf": false,
            "children": [ ... ]
          }
        }

        Folders use:
          - id:   "folder-<PortalTreeNodeId>"
          - leaf: false
          - title
          - expanded
          - checked
          - children: [...]

        Layers use:
          - id:   LayerKey
          - text: LayerKey (for now; can later use a stored display title)
          - glyph: from PortalTreeNodes.Glyph
          - qtip:  from PortalTreeNodes.Tooltip
          - checked: from CheckedDefault
        """
        rows = self.db.get_portal_tree(portal_id)
        if not rows:
            return {
                "defaults": {"general": {"leaf": True}},
                "treeConfig": {"id": "root", "leaf": False, "children": []},
            }

        # Index rows by node id and parent
        rows_by_id = {}
        children_by_parent = {}
        order_by_id = {}

        for row in rows:
            nid = row["PortalTreeNodeId"]
            pid = row["ParentNodeId"]
            rows_by_id[nid] = row
            children_by_parent.setdefault(pid, []).append(nid)
            order_by_id[nid] = (
                row["DisplayOrder"] if row["DisplayOrder"] is not None else 0
            )

        def build_node(node_id: int) -> dict:
            row = rows_by_id[node_id]
            is_folder = bool(row["IsFolder"])

            if is_folder:
                folder_id = row["FolderId"] or f"folder-{node_id}"
                node = {
                    "id": folder_id,
                    "leaf": False,
                    "title": row["FolderTitle"] or "",
                    "expanded": bool(row["ExpandedDefault"]),
                    "checked": bool(row["CheckedDefault"]),
                    "children": [],
                }
                child_ids = children_by_parent.get(node_id, [])
                # sort by DisplayOrder
                child_ids = sorted(child_ids, key=lambda cid: order_by_id.get(cid, 0))
                for cid in child_ids:
                    node["children"].append(build_node(cid))
                return node
            else:
                layer_key = row["LayerKey"] or ""

                # Prefer LayerTitle; fall back to LayerKey if not set
                if "LayerTitle" in row.keys() and row["LayerTitle"]:
                    layer_text = row["LayerTitle"]
                else:
                    layer_text = layer_key

                node = {
                    "id": layer_key,
                    "text": layer_text,
                }

                glyph = row["Glyph"] or ""
                if glyph:
                    if glyph.startswith("x-fas "):
                        node["iconCls"] = glyph
                    else:
                        node["glyph"] = glyph

                if row["CheckedDefault"] is not None:
                    node["checked"] = bool(row["CheckedDefault"])

                return node

        # Build root children (ParentNodeId IS NULL)
        root_children = []
        root_ids = children_by_parent.get(None, [])
        root_ids = sorted(root_ids, key=lambda nid: order_by_id.get(nid, 0))
        for nid in root_ids:
            root_children.append(build_node(nid))

        return {
            "defaults": {"general": {"leaf": True}},
            "treeConfig": {
                "id": "root",
                "leaf": False,
                "children": root_children,
            },
        }

    # ------------------------------------------------------------------
    # Saving: Tab1 
    # ------------------------------------------------------------------

    def on_make_layer_available(self):
        """
        Save the Tab 1 layer to the DB (if not already there)
        and refresh the 'Available Layers' list for the current portal,
        plus the Tab 1 DB dropdown.
        """
        try:
            result = self._save_new_layer_from_tab1()
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            self._error(
                "Error saving layer",
                f"Failed to save new layer:\n{exc}",
            )
            return

        if result == "none":
            QtWidgets.QMessageBox.information(
                self,
                "Nothing to do",
                "No layer name or keys set, nothing was saved.",
            )
            return
        elif result == "updated":
            QtWidgets.QMessageBox.information(
                self,
                "Layer updated",
                "Existing layer updated in the database.",
            )
        elif result == "created":
            QtWidgets.QMessageBox.information(
                self,
                "Layer made available",
                "New layer saved to the database and made available to portals.",
            )

        # Refresh Tab 3: available layers for the currently selected portal
        if hasattr(self, "cmbPortalSelect") and getattr(self, "_portal_id_by_index", None):
            idx = self.cmbPortalSelect.currentIndex()
            if 0 <= idx < len(self._portal_id_by_index):
                portal_id = self._portal_id_by_index[idx]
                self._load_available_layers(portal_id)

        # Refresh Tab 1 DB dropdown so the new layer appears in cmbDbLayers
        if hasattr(self, "_refresh_db_layer_combo"):
            self._refresh_db_layer_combo()

        # (Optional, if you haven’t already) refresh Tab 2 views as well
        if hasattr(self, "tblAllLayers"):
            self._refresh_all_layers_table()
        if hasattr(self, "tblPortalLayers") and hasattr(self, "cmbPortalSelectLayers"):
            self._refresh_portal_layers_table()

    def on_save_layer_to_db_clicked(self):
        """
        Save the current Tab 1 layer definition to the database ONLY.
        Does not change which portals use this layer.
        """
        try:
            result = self._save_new_layer_from_tab1()
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            self._error(
                "Error saving layer",
                f"Failed to save layer to the database:\n{exc}",
            )
            return

        if result == "none":
            QtWidgets.QMessageBox.information(
                self,
                "Nothing to save",
                "No layer name or keys set, nothing was saved.",
            )
            return
        elif result == "updated":
            QtWidgets.QMessageBox.information(
                self,
                "Layer updated",
                "Existing layer updated in the database.",
            )
        elif result == "created":
            QtWidgets.QMessageBox.information(
                self,
                "Layer saved",
                "New layer saved to the database.",
            )
        elif result == "updated":
            # Only if _save_new_layer_from_tab1 ever returns this;
            # if not, you can drop this branch.
            QtWidgets.QMessageBox.information(
                self,
                "Layer updated",
                "Existing layer updated in the database.",
            )

        # Refresh Tab 1 DB dropdown so the layer appears / updates in cmbDbLayers
        if hasattr(self, "_refresh_db_layer_combo"):
            self._refresh_db_layer_combo()

        # Keep Tab 2 global view in sync too
        if hasattr(self, "tblAllLayers"):
            self._refresh_all_layers_table()

    def _save_new_layer_from_tab1(self):
        """
        Save the layer configured on Tab 1 into the DB.

        Returns one of:
            "none"     -> nothing to save (no layer name / keys)
            "created"  -> new MapServerLayers + ServiceLayers + fields/styles created
            "updated"  -> existing layer updated (metadata + fields/styles)
        """
        if not (
            hasattr(self, "txtLayerName")
            and hasattr(self, "txtWmsLayerKey")
            and hasattr(self, "txtVectorLayerKey")
        ):
            return "none"

        layer_name = self.txtLayerName.text().strip()
        wms_key = self.txtWmsLayerKey.text().strip()
        vector_key = self.txtVectorLayerKey.text().strip()

        if not layer_name or not wms_key or not vector_key:
            # Nothing to save
            return "none"

        # Derive a base key from the WMS key, e.g. ROADSCHEDULEPUBLIC_WMS -> ROADSCHEDULEPUBLIC
        base_key = wms_key
        if base_key.upper().endswith("_WMS"):
            base_key = base_key[:-4]

        gridxtype = (
            self.txtGridXType.text().strip()
            if hasattr(self, "txtGridXType")
            else ""
        )
        if not gridxtype:
            gridxtype = f"pms_{layer_name.lower()}grid"

        geom_field = (
            self.txtGeomFieldName.text().strip()
            if hasattr(self, "txtGeomFieldName")
            else "msGeometry"
        )
        if not geom_field:
            geom_field = "msGeometry"

        label_class = (
            self.txtLabelClassName.text().strip()
            if hasattr(self, "txtLabelClassName")
            else "labels"
        )
        if not label_class:
            label_class = "labels"

        opacity = (
            self.spinOpacity.value()
            if hasattr(self, "spinOpacity")
            else 0.75
        )

        # idProperty from combo
        id_property_name = ""
        if hasattr(self, "cmbIdProperty") and self.cmbIdProperty.currentText():
            id_property_name = self.cmbIdProperty.currentText().strip()

        # Check if layer already exists
        exists, existing_id = self.db.layer_exists(layer_name, base_key)

        if exists:
            # Update existing MapServerLayers row
            mapserver_layer_id = existing_id
            self.db.update_mapserver_layer(
                mapserver_layer_id=mapserver_layer_id,
                map_layer_name=layer_name,
                base_layer_key=base_key,
                gridxtype=gridxtype,
                geometry_type="LINESTRING",  # still our default for now
                default_geom_field=geom_field,
                default_label_class=label_class,
                default_opacity=opacity,
                notes=None,
            )
            result = "updated"
        else:
            # Insert new MapServerLayers row
            mapserver_layer_id = self.db.insert_mapserver_layer(
                map_layer_name=layer_name,
                base_layer_key=base_key,
                gridxtype=gridxtype,
                geometry_type="LINESTRING",  # POC default
                default_geom_field=geom_field,
                default_label_class=label_class,
                default_opacity=opacity,
                notes=None,
            )
            result = "created"

        # Upsert WMS + WFS ServiceLayers
        for service_type, layer_key in (("WMS", wms_key), ("WFS", vector_key)):
            service_layer_id = self.db.get_service_layer_id(
                mapserver_layer_id, service_type
            )
            if service_layer_id is None:
                # New service layer
                self.db.insert_service_layer(
                    mapserver_layer_id=mapserver_layer_id,
                    service_type=service_type,
                    layer_key=layer_key,
                    feature_type=layer_name,
                    id_property_name=id_property_name or None,
                    geom_field_name=geom_field,
                    label_class_name=label_class,
                    opacity=opacity,
                    openlayers_json='{"projection":"EPSG:2157"}',
                    server_options_json=None,
                )
            else:
                # Update existing service layer
                self.db.update_service_layer(
                    service_layer_id=service_layer_id,
                    layer_key=layer_key,
                    feature_type=layer_name,
                    id_property_name=id_property_name or None,
                    geom_field_name=geom_field,
                    label_class_name=label_class,
                    opacity=opacity,
                    openlayers_json='{"projection":"EPSG:2157"}',
                    server_options_json=None,
                )

        # Fields (layer level + service-level tooltip etc)
        if hasattr(self, "tblFields"):
            self._save_fields_for_layer(mapserver_layer_id, id_property_name)

        # Styles (unchanged for now, but could also be made "replace" instead of "append")
        if hasattr(self, "tblStyles"):
            self._save_styles_for_layer(mapserver_layer_id)

        return result

    def _save_tab1_layer_to_db(self):
        """
        Wrap _save_new_layer_from_tab1() in a transaction and messages.

        Returns:
            "none"    - nothing to save (no name/keys)
            "created" - new layer inserted
            "updated" - existing layer updated
            "exists"  - layer already exists and nothing changed (if your
                        underlying helper distinguishes this)
            None      - on error (dialog already shown)
        """
        try:
            result = self._save_new_layer_from_tab1()
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            self._error(
                "Error saving layer",
                f"Failed to save layer to the database:\n{exc}",
            )
            return None

        # basic user feedback; tweak text to match what _save_new_layer_from_tab1 returns
        if result == "none":
            QtWidgets.QMessageBox.information(
                self,
                "Nothing to save",
                "No layer name or keys set, nothing was saved.",
            )
        elif result == "created":
            QtWidgets.QMessageBox.information(
                self,
                "Layer saved",
                "New layer saved to the database.",
            )
        elif result == "updated":
            QtWidgets.QMessageBox.information(
                self,
                "Layer updated",
                "Existing layer updated in the database.",
            )
        elif result == "exists":
            # If your helper uses this code, you can either be silent or inform the user
            QtWidgets.QMessageBox.information(
                self,
                "No changes",
                "A matching layer already exists in the database. No changes were made.",
            )

        # refresh Tab 1 DB list regardless of result (so new layers appear)
        if hasattr(self, "_refresh_db_layer_combo"):
            self._refresh_db_layer_combo()

        # also keep Tab 2's global view in sync
        if hasattr(self, "tblAllLayers"):
            self._refresh_all_layers_table()

        return result

    def _save_fields_for_layer(self, mapserver_layer_id: int, id_property_name: str):
        """
        Persist fields from tblFields for this layer.

        UI column order:
          0 Field name
          1 Is idProperty
          2 Include
          3 Is ToolTip
          4 ToolTip alias

        Writes:
          - MapServerLayerFields (canonical defaults)
          - ServiceLayerFields for the WFS service (include + tooltip + alias)
        Existing rows for this layer/service are deleted first.
        """
        tbl = self.tblFields
        row_count = tbl.rowCount()

        COL_FIELD = 0
        COL_IDPROP = 1
        COL_INCLUDE = 2
        COL_TOOLTIP = 3
        COL_TOOLTIP_ALIAS = 4

        # Find WFS ServiceLayerId for this MapServerLayer
        wfs_service_layer_id = self.db.get_service_layer_id(
            mapserver_layer_id, "WFS"
        )

        # Clear existing rows for this layer
        self.db.delete_layer_fields(mapserver_layer_id)
        if wfs_service_layer_id is not None:
            self.db.delete_service_layer_fields(wfs_service_layer_id)

        for row_idx in range(row_count):
            # Field name (also holds the type in UserRole)
            name_item = tbl.item(row_idx, COL_FIELD)
            field_name = name_item.text().strip() if name_item else ""
            if not field_name:
                continue

            field_type = None
            if name_item is not None:
                data = name_item.data(QtCore.Qt.UserRole)
                if isinstance(data, str) and data:
                    field_type = data
            if not field_type:
                field_type = "string"

            # Is idProperty
            id_item = tbl.item(row_idx, COL_IDPROP)
            is_id_flag = False
            if id_item and id_item.checkState() == QtCore.Qt.Checked:
                is_id_flag = True
            elif id_property_name and field_name == id_property_name:
                is_id_flag = True

            # Include in CSV / propertyname
            include_item = tbl.item(row_idx, COL_INCLUDE)
            include_csv = (
                include_item and include_item.checkState() == QtCore.Qt.Checked
            )

            # Tooltip config
            tooltip_item = tbl.item(row_idx, COL_TOOLTIP)
            is_tooltip = (
                tooltip_item
                and tooltip_item.checkState() == QtCore.Qt.Checked
            )
            alias_item = tbl.item(row_idx, COL_TOOLTIP_ALIAS)
            tooltip_alias = alias_item.text().strip() if alias_item else ""

            display_order = row_idx + 1

            # Layer-level defaults
            self.db.insert_layer_field(
                mapserver_layer_id=mapserver_layer_id,
                field_name=field_name,
                field_type=field_type,
                include_in_csv=include_csv,
                is_id_property=is_id_flag,
                display_order=display_order,
            )

            # Service-level (WFS) config including tooltip and alias
            if wfs_service_layer_id is not None:
                self.db.insert_service_layer_field(
                    service_layer_id=wfs_service_layer_id,
                    field_name=field_name,
                    field_type=field_type,
                    include_in_propertyname=include_csv,
                    is_tooltip=is_tooltip,
                    tooltip_alias=tooltip_alias or None,
                    field_order=display_order,
                )

    def _save_styles_for_layer(self, mapserver_layer_id: int):
        """
        Persist styles from tblStyles for this layer.

        Strategy:
          - delete existing MapServerLayerStyles for this layer
          - reinsert from the current grid, in row order
        """
        if not hasattr(self, "tblStyles"):
            return

        tbl = self.tblStyles
        row_count = tbl.rowCount()

        # Clear existing styles to avoid UNIQUE constraint violations
        self.db.delete_layer_styles(mapserver_layer_id)

        for row_idx in range(row_count):
            group_item = tbl.item(row_idx, 0)
            title_item = tbl.item(row_idx, 1)

            group_name = group_item.text().strip() if group_item else ""
            style_title = title_item.text().strip() if title_item else ""
            if not group_name or not style_title:
                continue

            display_order = row_idx + 1

            self.db.insert_layer_style(
                mapserver_layer_id=mapserver_layer_id,
                group_name=group_name,
                style_title=style_title,
                display_order=display_order,
            )

    def on_export_current_portal_json(self):
        """
        Export a tree.json-style file for the currently selected portal.

        The output filename is <PortalKey>_tree.json in a folder chosen
        by the user.
        """
        portal_id = self._get_current_portal_id()
        if portal_id is None:
            self._error("No portal selected", "Select a portal to export.")
            return

        # Ask for export folder
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select export folder for tree.json",
            "",
            QtWidgets.QFileDialog.ShowDirsOnly
            | QtWidgets.QFileDialog.DontResolveSymlinks,
        )
        if not folder:
            return  # user cancelled

        # Get portal key (for filename)
        cur = self.db.conn.execute(
            "SELECT PortalKey, PortalTitle FROM Portals WHERE PortalId = ?",
            (portal_id,),
        )
        row = cur.fetchone()
        if row is None:
            self._error("Portal missing", f"No portal with id {portal_id} found in DB.")
            return

        portal_key = row["PortalKey"] or f"portal_{portal_id}"

        # Build tree.json-style structure
        tree_json = self._build_portal_tree_file_json(portal_id)

        out_path = os.path.join(folder, f"{portal_key}_tree.json")

        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(tree_json, f, ensure_ascii=False, indent=2)
                f.write("\n")
        except Exception as exc:
            self._error(
                "Export failed",
                f"Could not write JSON to:\n{out_path}\n\nError:\n{exc}",
            )
            return

        QtWidgets.QMessageBox.information(
            self,
            "Export complete",
            f"Portal tree JSON exported to:\n{out_path}",
        )
