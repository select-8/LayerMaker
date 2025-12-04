import os
import sys

from PyQt5 import QtWidgets, QtCore, QtGui, uic

from db_access import DBAccess
from mapfile_utils import parse_mapfile, extract_styles, extract_fields

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app2.wfs_to_db import WFSToDB, DEFAULT_WFS_URL


DB_FILENAME = "LayerConfig_v2.db"
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

        db_path = os.path.join(base_dir, DB_FILENAME)
        self.db = DBAccess(db_path)

        # Internal caches
        self._portal_id_by_index = []  # index -> PortalId
        self._tree_model = None
        self._mapfile_layers = {}      # layer_name -> layer dict

        self._connect_signals()
        self._load_portals()

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
            self.btnLoadFieldsFromWFS.clicked.connect(
                self.on_load_fields_from_wfs
            )

        # Tab 2
        if hasattr(self, "cmbPortalSelect"):
            self.cmbPortalSelect.currentIndexChanged.connect(
                self.on_portal_changed
            )

        if hasattr(self, "btnSavePortalToDatabase"):
            self.btnSavePortalToDatabase.clicked.connect(
                self.on_save_portal_to_database
            )

    # ------------------------------------------------------------------
    # WFS
    # ------------------------------------------------------------------

    def fetch_wfs_schema(self, layer_name: str, wfs_url: str = None, timeout: int = 180) -> dict:
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
        if not (hasattr(self, "txtMapFilePath") and hasattr(self, "cmbMapFileLayerNames")):
            return

        map_path = self.txtMapFilePath.text().strip()
        if not map_path:
            QtWidgets.QMessageBox.warning(self, "No mapfile", "Please select a mapfile first.")
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
        """
        if not (hasattr(self, "tblFields") and hasattr(self, "cmbIdProperty")):
            return

        layer_name = self.txtLayerName.text().strip() if hasattr(self, "txtLayerName") else ""
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
        id_prop = (
            (metadata.get("wfs_featureid") or "").strip()
            or (metadata.get("gml_featureid") or "").strip()
        )

        tbl = self.tblFields
        tbl.clearContents()
        tbl.setRowCount(0)
        self.cmbIdProperty.clear()

        field_names = list(schema.keys())  # order preserved from DescribeFeatureType

        # Column indices:
        COL_IDPROP = 0
        COL_INCLUDE = 1
        COL_FIELD = 2
        COL_TYPE = 3
        COL_TOOLTIP = 4
        COL_TOOLTIP_ALIAS = 5

        for idx, fname in enumerate(field_names):
            ftype = schema[fname] or "string"

            tbl.insertRow(idx)

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

            # Field name
            name_item = QtWidgets.QTableWidgetItem(fname)
            tbl.setItem(idx, COL_FIELD, name_item)

            # Type (raw WFS type)
            type_item = QtWidgets.QTableWidgetItem(ftype)
            tbl.setItem(idx, COL_TYPE, type_item)

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


    # ------------------------------------------------------------------
    # Tab 2: portals, tree, available layers
    # ------------------------------------------------------------------
    def _load_portals(self):
        if not hasattr(self, "cmbPortalSelect"):
            return

        portals = self.db.get_portals()
        self.cmbPortalSelect.blockSignals(True)
        self.cmbPortalSelect.clear()
        self._portal_id_by_index = []

        for row in portals:
            label = f"{row['PortalKey']} ({row['PortalTitle']})"
            self.cmbPortalSelect.addItem(label)
            self._portal_id_by_index.append(row["PortalId"])

        self.cmbPortalSelect.blockSignals(False)

        if self._portal_id_by_index:
            self.cmbPortalSelect.setCurrentIndex(0)
            self.on_portal_changed(0)

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

    def _load_portal_tree(self, portal_id):
        rows = self.db.get_portal_tree(portal_id)

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

            title_item.setData(row["PortalTreeNodeId"], QtCore.Qt.UserRole)
            title_item.setData(is_folder, QtCore.Qt.UserRole + 1)
            title_item.setData(row["LayerKey"], QtCore.Qt.UserRole + 2)

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

    def on_tree_selection_changed(self, selected, _deselected):
        indexes = selected.indexes()
        if not indexes:
            self._clear_node_details()
            return

        idx = indexes[0]
        item = self._tree_model.itemFromIndex(idx)
        if item is None:
            self._clear_node_details()
            return

        node_id = item.data(QtCore.Qt.UserRole)
        is_folder = bool(item.data(QtCore.Qt.UserRole + 1))

        if node_id is None:
            self._clear_node_details()
            return

        # Fetch full row for this node
        # Make a tiny direct query (could be pushed to DBAccess, but not critical)
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

    def _clear_node_details(self):
        self._populate_folder_details(None)
        self._populate_layer_details(None)

    def _populate_folder_details(self, row):
        if not hasattr(self, "groupBox_folderDetails"):
            return

        if row is None or not bool(row["IsFolder"]):
            self.groupBox_folderDetails.setEnabled(False)
            if hasattr(self, "txtFolderTitle"):
                self.txtFolderTitle.clear()
            if hasattr(self, "chkFolderExpanded"):
                self.chkFolderExpanded.setChecked(False)
            if hasattr(self, "chkFolderChecked"):
                self.chkFolderChecked.setChecked(False)
            return

        self.groupBox_folderDetails.setEnabled(True)
        if hasattr(self, "txtFolderTitle"):
            self.txtFolderTitle.setText(row["FolderTitle"] or "")
        if hasattr(self, "chkFolderExpanded"):
            self.chkFolderExpanded.setChecked(bool(row["ExpandedDefault"]))
        if hasattr(self, "chkFolderChecked"):
            self.chkFolderChecked.setChecked(bool(row["CheckedDefault"]))

    def _populate_layer_details(self, row):
        if not hasattr(self, "groupBox_layerDetails"):
            return

        if row is None or bool(row["IsFolder"]):
            self.groupBox_layerDetails.setEnabled(False)
            if hasattr(self, "txtLayerKey"):
                self.txtLayerKey.clear()
            if hasattr(self, "txtLayerTitle"):
                self.txtLayerTitle.clear()
            if hasattr(self, "txtLayerGlyph"):
                self.txtLayerGlyph.clear()
            if hasattr(self, "txtLayerTooltip"):
                self.txtLayerTooltip.clear()
            return

        self.groupBox_layerDetails.setEnabled(True)

        layer_key = row["LayerKey"] or ""
        if hasattr(self, "txtLayerKey"):
            self.txtLayerKey.setText(layer_key)
        if hasattr(self, "txtLayerTitle"):
            self.txtLayerTitle.setText(layer_key)
        if hasattr(self, "txtLayerGlyph"):
            self.txtLayerGlyph.setText(row["Glyph"] or "")
        if hasattr(self, "txtLayerTooltip"):
            self.txtLayerTooltip.setPlainText(row["Tooltip"] or "")

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

    # ------------------------------------------------------------------
    # Saving: Tab1 -> DB via Save button
    # ------------------------------------------------------------------
    def on_save_portal_to_database(self):
        try:
            self._save_new_layer_from_tab1()
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            QtWidgets.QMessageBox.critical(
                self,
                "Error saving layer",
                f"Failed to save new layer:\n{exc}",
            )
            return

        # Refresh available layers for current portal
        idx = self.cmbPortalSelect.currentIndex() if hasattr(self, "cmbPortalSelect") else -1
        if 0 <= idx < len(self._portal_id_by_index):
            portal_id = self._portal_id_by_index[idx]
            self._load_available_layers(portal_id)

        QtWidgets.QMessageBox.information(
            self,
            "Layer saved",
            "New layer (if any) saved to database.",
        )

    def _save_new_layer_from_tab1(self):
        if not (
            hasattr(self, "txtLayerName")
            and hasattr(self, "txtWmsLayerKey")
            and hasattr(self, "txtVectorLayerKey")
        ):
            return

        layer_name = self.txtLayerName.text().strip()
        wms_key = self.txtWmsLayerKey.text().strip()
        vector_key = self.txtVectorLayerKey.text().strip()

        if not layer_name or not wms_key or not vector_key:
            # Nothing to save
            return

        base_key = wms_key
        if base_key.upper().endswith("_WMS"):
            base_key = base_key[:-4]

        gridxtype = self.txtGridXType.text().strip() if hasattr(self, "txtGridXType") else ""
        if not gridxtype:
            gridxtype = f"pms_{layer_name.lower()}grid"

        geom_field = self.txtGeomFieldName.text().strip() if hasattr(self, "txtGeomFieldName") else "msGeometry"
        if not geom_field:
            geom_field = "msGeometry"

        label_class = self.txtLabelClassName.text().strip() if hasattr(self, "txtLabelClassName") else "labels"
        if not label_class:
            label_class = "labels"

        opacity = self.spinOpacity.value() if hasattr(self, "spinOpacity") else 0.75

        exists, _ = self.db.layer_exists(layer_name, base_key)
        if exists:
            # Already there, bail out quietly for now
            return

        # Insert MapServerLayers
        mapserver_layer_id = self.db.insert_mapserver_layer(
            map_layer_name=layer_name,
            base_layer_key=base_key,
            gridxtype=gridxtype,
            geometry_type="LINESTRING",          # POC default
            default_geom_field=geom_field,
            default_label_class=label_class,
            default_opacity=opacity,
            notes=None,
        )

        # idProperty from combo
        id_property_name = ""
        if hasattr(self, "cmbIdProperty") and self.cmbIdProperty.currentText():
            id_property_name = self.cmbIdProperty.currentText().strip()

        # Insert WMS + WFS
        for service_type, layer_key in (("WMS", wms_key), ("WFS", vector_key)):
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

        # Fields
        if hasattr(self, "tblFields"):
            self._save_fields_for_layer(mapserver_layer_id, id_property_name)

        # Styles
        if hasattr(self, "tblStyles"):
            self._save_styles_for_layer(mapserver_layer_id)

    def _save_fields_for_layer(self, mapserver_layer_id: int, id_property_name: str):
        tbl = self.tblFields
        row_count = tbl.rowCount()

        # Column indices must match the UI definition
        COL_IDPROP = 0
        COL_INCLUDE = 1
        COL_FIELD = 2
        COL_TYPE = 3
        COL_TOOLTIP = 4
        COL_TOOLTIP_ALIAS = 5

        for row_idx in range(row_count):
            # Include in CSV
            include_item = tbl.item(row_idx, COL_INCLUDE)
            include_csv = (
                include_item
                and include_item.checkState() == QtCore.Qt.Checked
            )

            # Field name
            name_item = tbl.item(row_idx, COL_FIELD)
            field_name = name_item.text().strip() if name_item else ""
            if not field_name:
                continue

            # Type
            type_item = tbl.item(row_idx, COL_TYPE)
            field_type = type_item.text().strip() if type_item else "string"

            # Is idProperty
            id_item = tbl.item(row_idx, COL_IDPROP)
            is_id_flag = False
            if id_item and id_item.checkState() == QtCore.Qt.Checked:
                is_id_flag = True
            elif id_property_name and field_name == id_property_name:
                is_id_flag = True

            # Tooltip config (not yet persisted in DB – kept for future use)
            tooltip_item = tbl.item(row_idx, COL_TOOLTIP)
            is_tooltip = (
                tooltip_item
                and tooltip_item.checkState() == QtCore.Qt.Checked
            )
            alias_item = tbl.item(row_idx, COL_TOOLTIP_ALIAS)
            tooltip_alias = alias_item.text().strip() if alias_item else ""

            # For now, we ignore is_tooltip / tooltip_alias at DB level.
            # They can be wired into Json export or an expanded DB schema later.

            display_order = row_idx + 1

            self.db.insert_layer_field(
                mapserver_layer_id=mapserver_layer_id,
                field_name=field_name,
                field_type=field_type,
                include_in_csv=include_csv,
                is_id_property=is_id_flag,
                display_order=display_order,
            )


    def _save_styles_for_layer(self, mapserver_layer_id: int):
        tbl = self.tblStyles
        row_count = tbl.rowCount()
        for row_idx in range(row_count):
            group_item = tbl.item(row_idx, 0)
            title_item = tbl.item(row_idx, 1)

            group_name = group_item.text().strip() if group_item else ""
            style_title = title_item.text().strip() if title_item else ""

            if not group_name:
                continue
            if not style_title:
                style_title = group_name

            display_order = row_idx + 1

            self.db.insert_layer_style(
                mapserver_layer_id=mapserver_layer_id,
                group_name=group_name,
                style_title=style_title,
                display_order=display_order,
            )
