# layer_generator/layer_window.py
# Minimal wiring for GB_MAPFILE widgets to render a .layer via Jinja.
# Also populates Schema.Table and Unique ID comboboxes from SQL Server via pyodbc (Trusted Connection).

import os
import re
from typing import Dict, Any, List, Optional

from layer_generator.db import list_views, list_columns, list_geometry_columns, ping
from PyQt5.QtWidgets import QColorDialog, QMessageBox, QComboBox, QLineEdit, QFileDialog
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from app2.settings import PMS_MAPS_DIR


def _safe_name(s: str) -> str:
    return (re.sub(r"[^A-Za-z0-9_-]+", "_", s).strip("_") or "layer")


def _read_tw_metadata(table) -> Dict[str, str]:
    """Read metadata from TW_METADATA.

    Supports either:
      A) 2-column Key/Value layout (first col 'Key'/'Name', second col 'Value')
      B) Vertical headers as keys with a single Value column (column 0)

    Keys are normalised to lowercase.
    """
    out: Dict[str, str] = {}
    if not table:
        return out

    rows = table.rowCount()
    cols = table.columnCount()

    # Try A: Key/Value table
    if cols >= 2:
        h0 = table.horizontalHeaderItem(0)
        h1 = table.horizontalHeaderItem(1)
        if h0 and h1:
            left = h0.text().strip().lower()
            right = h1.text().strip().lower()
            if left in {"key", "name"} and right in {"value", "val"}:
                for r in range(rows):
                    ki = table.item(r, 0)
                    vi = table.item(r, 1)
                    if not ki:
                        continue
                    k = (ki.text() or "").strip().lower()
                    if not k:
                        continue
                    v = (vi.text() if vi else "") or ""
                    out[k] = v.strip()
                return out

    # Fallback B: vertical headers as keys, values in column 0
    for r in range(rows):
        vh = table.verticalHeaderItem(r)
        key = (vh.text().strip().lower() if vh else "")
        if not key:
            continue
        vi = table.item(r, 0) if cols >= 1 else None
        val = (vi.text() if vi else "") or ""
        out[key] = val.strip()

    return out


class MapfileWiring:
    """Wires GB_MAPFILE UI, collects values, validates, renders layer.template, writes .layer.

    Expects the following widgets on 'ui':
      LE_LAYERNAME, LE_GROUP, RB_POINT, RB_LINE, RB_POLYGON,
      CB_SCHEMATABLE, CB_UNIQUEID, LE_GEOMETRYFIELD, CBX_LA_FILTER,
      LE_LABELFIELD, BTN_COLOURPICKER, BTN_GENLAYERFILE, TW_METADATA

    (Legacy fallback: LE_SCHEMATABLE / LE_UNIQUEID are still supported as text inputs.)
    """

    def __init__(
        self,
        ui,
        template_dir: Optional[str] = None,
        template_name: str = "layer.template",
        out_dir: Optional[str] = None,
    ):
        self.ui = ui
        self.template_dir = template_dir or os.path.dirname(os.path.abspath(__file__))
        self.template_name = template_name
        self.out_dir = out_dir or self.template_dir

        self.env = Environment(
            loader=FileSystemLoader(self.template_dir),
            keep_trailing_newline=True,
            lstrip_blocks=True,
            trim_blocks=True,
            undefined=StrictUndefined,
        )

        # Default colour [R, G, B]
        self.colour = [12, 120, 200]

        self._attach()

    # ---------- wiring ----------

    def _attach(self) -> None:
        v = self.ui

        # Defaults that do not alter layout
        try:
            if not (v.RB_POINT.isChecked() or v.RB_LINE.isChecked() or v.RB_POLYGON.isChecked()):
                v.RB_LINE.setChecked(True)
        except Exception:
            pass

        try:
            v.CBX_LA_FILTER.setChecked(True)
        except Exception:
            pass

        # Button signals
        try:
            v.BTN_COLOURPICKER.clicked.connect(self._on_pick_colour)
        except Exception:
            pass

        try:
            v.BTN_GENLAYERFILE.clicked.connect(self._on_generate_layer_file)
        except Exception:
            pass

        # ---- DB-backed population (comboboxes) ----
        # Set the default schema used to populate CB_SCHEMATABLE here:
        self._db_default_schema = "mapserver"
        try:
            self._db_populate_views(self._db_default_schema)
            # When a view is chosen, populate the Unique ID columns
            if hasattr(v, "CB_SCHEMATABLE") and isinstance(v.CB_SCHEMATABLE, QComboBox):
                v.CB_SCHEMATABLE.currentIndexChanged.connect(lambda _ix: self._db_on_schema_table_changed())
        except Exception:
            # Keep UI resilient even if DB isn't reachable
            pass

    # ---------- events ----------

    def _on_pick_colour(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.colour = [int(c.red()), int(c.green()), int(c.blue())]
            # visual cue on the button if possible
            try:
                self.ui.BTN_COLOURPICKER.setStyleSheet(
                    "QPushButton { background-color: rgb(%d,%d,%d); }"
                    % (self.colour[0], self.colour[1], self.colour[2])
                )
            except Exception:
                pass

    def _on_generate_layer_file(self):
        v = self.ui

        out_dir = self._get_or_choose_out_dir()
        if not out_dir:
            return  # user cancelled the folder chooser
        os.makedirs(self.out_dir, exist_ok=True)

        tmpl_path = os.path.join(self.template_dir, self.template_name)
        if not os.path.exists(tmpl_path):
            QMessageBox.critical(v, "Error", f"Template not found:\n{tmpl_path}")
            print("Error: template not found:", tmpl_path)
            return

        ctx = self._collect_ctx()
        errs = self._validate_ctx(ctx)
        if errs:
            QMessageBox.warning(v, "Cannot generate", "\n".join(errs))
            print("Validation errors:", errs)
            return

        try:
            rendered = self.env.get_template(self.template_name).render(**ctx)
        except Exception as ex:
            QMessageBox.critical(v, "Error", f"Render failed: {ex}")
            print("Render failed:", ex)
            return

        os.makedirs(self.out_dir, exist_ok=True)
        out_path = os.path.join(self.out_dir, f"{_safe_name(ctx['name'])}.layer")
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(rendered)
        except Exception as ex:
            QMessageBox.critical(v, "Error", f"Write failed: {ex}")
            print("Write failed:", ex)
            return

        QMessageBox.information(v, "Layer generated", f"Wrote:\n{out_path}\n\nOutput folder:\n{self.out_dir}")
        self._print_ctx_summary(ctx)
        print("Wrote layer:", out_path)
     

    # ---------- data ----------

    def _collect_ctx(self) -> Dict[str, Any]:
        v = self.ui

        def _t(obj_name: str, default: str = "") -> str:
            """Return text from QComboBox or QLineEdit (fallback)."""
            w = getattr(v, obj_name, None)
            if w is None:
                return default
            if isinstance(w, QComboBox):
                return w.currentText().strip()
            if isinstance(w, QLineEdit):
                return w.text().strip()
            return default

        # Basics
        name = _t("LE_LAYERNAME")
        group = _t("LE_GROUP")

        if getattr(v, "RB_POINT", None) and v.RB_POINT.isChecked():
            gtype = "POINT"
        elif getattr(v, "RB_POLYGON", None) and v.RB_POLYGON.isChecked():
            gtype = "POLYGON"
        else:
            gtype = "LINE"

        # Data (prefer comboboxes; fall back to old line-edits if still present)
        schema_table = _t("CB_SCHEMATABLE")
        id_col = _t("CB_UNIQUEID")
        geom_field = _t("CB_GEOMETRYFIELD") or "Geom2157"
        use_la_filter = bool(getattr(v, "CBX_LA_FILTER", None) and v.CBX_LA_FILTER.isChecked())

        # Style / labels
        label_field = _t("CB_LABELFIELD") or None

        # Metadata strictly from TW_METADATA
        md = _read_tw_metadata(getattr(v, "TW_METADATA", None))
        # Accept either "ows title" or "ows_title" as key; same for abstract
        ows_title = md.get("ows title") or md.get("ows_title") or None
        ows_abstract = md.get("ows abstract") or md.get("ows_abstract") or None

        ctx = {
            "name": name,
            "group": group,
            "gtype": gtype,
            "schema_table": schema_table,
            "id_col": id_col,
            "geom_field": geom_field,
            "use_la_filter": use_la_filter,
            "colour": self.colour,         # [R, G, B]
            "label_field": label_field,
            "ows_title": ows_title,        # template falls back to name if None
            "ows_abstract": ows_abstract,  # template falls back to ''
        }
        return ctx

    # ---------- Printing ----------

    def _ctx_rows(self, ctx):
        """Return ordered (Field, Value) rows for summary output."""
        return [
            ("Layer name",        ctx["name"]),
            ("Group",             ctx["group"]),
            ("Geometry type",     ctx["gtype"]),
            ("Schema.Table",      ctx["schema_table"]),
            ("Unique ID",         ctx["id_col"]),
            ("Geometry field",    ctx["geom_field"]),
            ("Label field",       ctx.get("label_field") or "-"),
            ("LA filter",         "Yes" if ctx["use_la_filter"] else "No"),
            ("Colour [R,G,B]",    ", ".join(map(str, ctx["colour"]))),
            ("ows_title",         ctx.get("ows_title") or ctx["name"]),
            ("ows_abstract",      ctx.get("ows_abstract") or ""),
        ]

    def _print_ctx_summary(self, ctx):
        """Print a table of the layer context to stdout (tabulate if available)."""
        rows = self._ctx_rows(ctx)
        try:
            from tabulate import tabulate  # optional dependency
            table = tabulate(rows, headers=["Field", "Value"], tablefmt="github")
        except Exception:
            width = max(len(k) for k, _ in rows)
            lines = [f"{k:<{width}} : {v}" for k, v in rows]
            table = "\n".join(lines)
        print("\n=== Layer summary ===\n" + table + "\n")

    # ---------- validation ----------

    def _validate_ctx(self, ctx: Dict[str, Any]) -> List[str]:
        errs: List[str] = []
        if not ctx["name"]:
            errs.append("Layer Name is required")
        if not ctx["group"]:
            errs.append("Group is required")
        if not ctx["schema_table"]:
            errs.append("Schema.Table is required")
        if not ctx["id_col"]:
            errs.append("Unique ID column is required")

        gf = ctx.get("geom_field", "")
        if gf and not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", gf):
            errs.append("Geometry field should be a simple column name, e.g. Geom2157")

        colour = ctx.get("colour", [])
        if not (isinstance(colour, list) and len(colour) == 3 and all(isinstance(v, int) for v in colour)):
            errs.append("Colour must be three integers [R, G, B]")
        else:
            if any(v < 0 or v > 255 for v in colour):
                errs.append("Colour values must be in the range 0 to 255")

        return errs

    # ---------- File Helpers ----------

    def _is_default_out_dir(self) -> bool:
        """True if out_dir is unset or still the default (template_dir)."""
        cur = getattr(self, "out_dir", None)
        if not cur:
            return True
        # Compare normalized absolute paths
        a = os.path.normcase(os.path.abspath(cur))
        b = os.path.normcase(os.path.abspath(self.template_dir))
        return a == b

    def _get_or_choose_out_dir(self) -> str | None:
        """
        If out_dir is still the default, prompt once and remember the choice.
        Otherwise reuse the configured out_dir.
        """
        if self._is_default_out_dir():
            start = self.out_dir or self.template_dir
            chosen = QFileDialog.getExistingDirectory(self.ui, "Select output folder", start)
            if not chosen:
                return None  # user cancelled
            self.out_dir = chosen
        return self.out_dir


    # ---------- DB helpers (combobox population) ----------

    def _geomish(self, spatial_cols):
        """Prefer Geom2157 first, then the rest. Case-insensitive match."""
        if not spatial_cols:
            return []
        preferred = [c for c in spatial_cols if c.lower() == "geom2157"]
        others = [c for c in spatial_cols if c.lower() != "geom2157"]
        return preferred + others

    def _db_populate_views(self, schema: str) -> None:
        """Fill CB_SCHEMATABLE with 'schema.table' items from INFORMATION_SCHEMA.VIEWS."""
        v = self.ui
        cb = getattr(v, "CB_SCHEMATABLE", None)
        if not isinstance(cb, QComboBox):
            # Support older layouts by hinting into a line-edit if present
            le = getattr(v, "LE_SCHEMATABLE", None)
            if le and isinstance(le, QLineEdit):
                try:
                    if ping():
                        items = list_views(schema)
                        if items:
                            le.setPlaceholderText(items[0])
                except Exception:
                    pass
            return

        try:
            if not ping():
                QMessageBox.warning(v, "Database", "Cannot connect to SQL Server (Trusted Connection).")
                return
            items = list_views(schema)
            cb.blockSignals(True)
            cb.clear()
            cb.addItem("") # <-- blank first choice
            cb.addItems(items)
            cb.setEditable(True)
            cb.lineEdit().setReadOnly(True)
            cb.setPlaceholderText("Select a view...")
            cb.setEditable(False)
            cb.blockSignals(False)
        except Exception as ex:
            QMessageBox.warning(v, "Database", f"Failed to list views for schema '{schema}'.\n{ex}")

    def _db_on_schema_table_changed(self) -> None:
        """When CB_SCHEMATABLE changes, refresh CB_UNIQUEID with that view's columns."""
        v = self.ui
        schema_table = v.CB_SCHEMATABLE.currentText().strip()
        if not schema_table or "." not in schema_table:
            return
        try:
            cols = list_columns(schema_table)  # ['ColumnA','ColumnB',...]
            # Nudge likely ID columns to the top
            idish = [c for c in cols if c.lower().endswith(("id", "_id"))] or cols
            cb = getattr(v, "CB_UNIQUEID", None)
            if isinstance(cb, QComboBox):
                cb.blockSignals(True)
                cb.clear()
                cb.addItems(idish)
                cb.blockSignals(False)
            cb_label = getattr(v, "CB_LABELFIELD", None)
            if isinstance(cb_label, QComboBox):
                cb_label.blockSignals(True)
                cb_label.clear()
                cb_label.addItems(cols)
                cb_label.blockSignals(False)
            # Populate Geometry Field combobox from real spatial columns
            cb_geom = getattr(v, "CB_GEOMETRYFIELD", None)
            if isinstance(cb_geom, QComboBox):
                try:
                    spatial = list_geometry_columns(schema_table)   # ['Geom2157', 'Geom3857', ...] or []
                except Exception as ex:
                    QMessageBox.warning(v, "Database", f"Failed to inspect spatial columns for '{schema_table}'.\n{ex}")
                    spatial = []

                geom_opts = self._geomish(spatial)

                cb_geom.blockSignals(True)
                cb_geom.clear()
                if geom_opts:
                    cb_geom.addItems(geom_opts)
                    cb_geom.setCurrentIndex(0)   # pick the preferred one
                else:
                    # no spatial columns detected; fall back to a sensible default
                    cb_geom.addItem("Geom2157")
                    cb_geom.setCurrentIndex(0)
                cb_geom.blockSignals(False)
            # Auto-fill Layer Name from selected view (e.g., mapserver.vw_MyView -> MyView)
            le_name = getattr(v, "LE_LAYERNAME", None)
            if isinstance(le_name, QLineEdit):
                if not le_name.text().strip():
                # get object name after the last dot
                    _, _, obj_name = schema_table.rpartition(".")
                    base = obj_name[3:] if obj_name.lower().startswith("vw_") else obj_name
                    le_name.setText(base)
        except Exception as ex:
            QMessageBox.warning(v, "Database", f"Failed to list columns for '{schema_table}'.\n{ex}")
