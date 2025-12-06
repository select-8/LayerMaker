import os
import sys
import json

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

        # Tab 2
        if hasattr(self, "cmbPortalSelect"):
            self.cmbPortalSelect.currentIndexChanged.connect(self.on_portal_changed)

        if hasattr(self, "btnSavePortalToDatabase"):
            self.btnSavePortalToDatabase.clicked.connect(
                self.on_save_portal_to_database
            )

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

    def _get_current_portal_id(self):
        """
        Return the currently selected PortalId, or None if nothing valid
        is selected.
        """
        if not hasattr(self, "cmbPortalSelect"):
            return None

        idx = self.cmbPortalSelect.currentIndex()
        if idx < 0 or idx >= len(self._portal_id_by_index):
            return None
        return self._portal_id_by_index[idx]

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

    def _build_portal_tree_json(self, portal_id: int):
        """
        Build a hierarchical layertree JSON structure for the given portal.

        Returns a list of root nodes, each node a dict:
        - folder:
            {
                "title": str,
                "expanded": bool,
                "checked": bool,
                "children": [...]
            }
        - layer:
            {
                "layerKey": str,
                "title": str,
                "glyph": str or "",
                "qtip": str or "",
                "checked": bool
            }
        """
        rows = self.db.get_portal_tree(portal_id)

        # Map node id -> json node dict
        node_json = {}
        children_by_parent = {}

        for row in rows:
            node_id = row["PortalTreeNodeId"]
            parent_id = row["ParentNodeId"]
            is_folder = bool(row["IsFolder"])

            if is_folder:
                title = row["FolderTitle"] or ""
                node = {
                    "title": title,
                    "expanded": bool(row["ExpandedDefault"]),
                    "checked": bool(row["CheckedDefault"]),
                    "children": [],
                }
            else:
                layer_key = row["LayerKey"] or ""
                node = {
                    "layerKey": layer_key,
                    # for now title defaults to layerKey; can be extended later
                    "title": layer_key,
                    "glyph": row["Glyph"] or "",
                    "qtip": row["Tooltip"] or "",
                    "checked": bool(row["CheckedDefault"]),
                }

            node_json[node_id] = node
            children_by_parent.setdefault(parent_id, []).append(node_id)

        # Attach children to parents according to DisplayOrder
        roots = []
        for parent_id, child_ids in children_by_parent.items():
            # Keep sibling ordering from DisplayOrder
            child_ids_sorted = sorted(
                child_ids,
                key=lambda nid: next(
                    r["DisplayOrder"] for r in rows if r["PortalTreeNodeId"] == nid
                ),
            )
            if parent_id is None:
                for cid in child_ids_sorted:
                    roots.append(node_json[cid])
            else:
                parent_node = node_json.get(parent_id)
                if not parent_node:
                    # orphaned, treat as root
                    for cid in child_ids_sorted:
                        roots.append(node_json[cid])
                    continue
                for cid in child_ids_sorted:
                    parent_node.setdefault("children", []).append(node_json[cid])

        return roots

    def _build_portal_layers_json(self, portal_id: int):
        """
        Build a dict of layerKey -> config for all layers used in the given portal.
        """
        conn = self.db.conn

        # All layer keys referenced in this portal tree
        cur = conn.execute(
            """
            SELECT DISTINCT LayerKey
            FROM PortalTreeNodes
            WHERE PortalId = ?
              AND IsFolder = 0
              AND LayerKey IS NOT NULL
            """,
            (portal_id,),
        )
        layer_keys = [row["LayerKey"] for row in cur.fetchall()]

        if not layer_keys:
            return {}

        layers_json = {}

        for layer_key in layer_keys:
            cur = conn.execute(
                """
                SELECT
                    sl.ServiceType,
                    sl.LayerKey,
                    sl.MapServerLayerId,
                    m.MapLayerName,
                    m.GridXType,
                    m.LabelClassName,
                    m.GeomFieldName,
                    m.Opacity
                FROM ServiceLayers sl
                JOIN MapServerLayers m
                  ON sl.MapServerLayerId = m.MapServerLayerId
                WHERE sl.LayerKey = ?
                """,
                (layer_key,),
            )
            row = cur.fetchone()
            if row is None:
                # LayerKey present in tree but no backing service
                continue

            msl_id = row["MapServerLayerId"]

            # Fields for propertyname and idProperty
            try:
                fcur = conn.execute(
                    """
                    SELECT FieldName,
                           FieldType,
                           IncludeInCsv,
                           IsIdProperty,
                           DisplayOrder
                    FROM MapServerLayerFields
                    WHERE MapServerLayerId = ?
                    ORDER BY DisplayOrder
                    """,
                    (msl_id,),
                )
                fields = fcur.fetchall()
            except Exception:
                fields = []

            property_names = [f["FieldName"] for f in fields if f["IncludeInCsv"]]
            id_props = [f["FieldName"] for f in fields if f["IsIdProperty"]]
            id_property = id_props[0] if id_props else None

            layer_cfg = {
                "layerKey": row["LayerKey"],
                "serviceType": row["ServiceType"],
                "mapLayerName": row["MapLayerName"],
                "gridXType": row["GridXType"],
                "labelClassName": row["LabelClassName"],
                "geomFieldName": row["GeomFieldName"],
                "opacity": row["Opacity"],
            }
            if id_property:
                layer_cfg["idProperty"] = id_property
            if property_names:
                layer_cfg["propertyNames"] = property_names

            layers_json[layer_key] = layer_cfg

        return layers_json

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
        idx = (
            self.cmbPortalSelect.currentIndex()
            if hasattr(self, "cmbPortalSelect")
            else -1
        )
        if 0 <= idx < len(self._portal_id_by_index):
            portal_id = self._portal_id_by_index[idx]
            self._load_available_layers(portal_id)

        QtWidgets.QMessageBox.information(
            self,
            "Layer saved",
            "New layer (if any) saved to database.",
        )

    def on_make_layer_available(self):
        """
        Save the Tab 1 layer to the DB (if not already there)
        and refresh the 'Available Layers' list for the current portal.
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
            QtWidgets.QMessageBox.warning(
                self,
                "No layer to save",
                "There is no valid layer on Tab 1. "
                "Scan a mapfile and select a layer first.",
            )
            return

        if result == "exists":
            QtWidgets.QMessageBox.information(
                self,
                "Layer already exists",
                "A layer with this name/base key already exists in the database.\n"
                "Nothing new was added.",
            )
        elif result == "created":
            QtWidgets.QMessageBox.information(
                self,
                "Layer made available",
                "New layer saved to the database and made available to portals.",
            )

        # Refresh available layers for the currently selected portal
        if hasattr(self, "cmbPortalSelect") and self._portal_id_by_index:
            idx = self.cmbPortalSelect.currentIndex()
            if 0 <= idx < len(self._portal_id_by_index):
                portal_id = self._portal_id_by_index[idx]
                self._load_available_layers(portal_id)

    def _save_new_layer_from_tab1(self):
        """
        Save the layer configured on Tab 1 into the DB.

        Returns one of:
            "none"   -> nothing to save (no layer name / keys)
            "exists" -> a layer with this name/base key already exists
            "created"-> new MapServerLayers + ServiceLayers + fields/styles created
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

        # Duplicate check
        exists, _ = self.db.layer_exists(layer_name, base_key)
        if exists:
            # Already in the DB, nothing to insert
            return "exists"

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

        # Insert WMS + WFS ServiceLayers
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

        return "created"

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
                include_item and include_item.checkState() == QtCore.Qt.Checked
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
            is_tooltip = tooltip_item and tooltip_item.checkState() == QtCore.Qt.Checked
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
