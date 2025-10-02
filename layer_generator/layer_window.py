# layer_generator/mapfile_ui.py
# Minimal wiring for GB_MAPFILE widgets to render a .layer via Jinja.
# Output is written to the same folder as this file by default.

import os
import re
from typing import Dict, Any, List, Optional

from PyQt5.QtWidgets import QColorDialog, QMessageBox
from jinja2 import Environment, FileSystemLoader, StrictUndefined


def _safe_name(s: str) -> str:
    return (re.sub(r"[^A-Za-z0-9_-]+", "_", s).strip("_") or "layer")


def _read_tw_metadata(table) -> Dict[str, str]:
    """
    Read metadata from TW_METADATA.

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
    """
    Wires GB_MAPFILE UI, collects values, validates, renders layer.template, writes .layer.
    Expects the following widgets to exist on 'ui':
      LE_LAYERNAME, LE_GROUP, RB_POINT, RB_LINE, RB_POLYGON,
      LE_SCHEMATABLE, LE_UNIQUEID, LE_GEOMETRYFIELD, CBX_LA_FILTER,
      LE_LABELFIELD, BTN_COLOURPICKER, BTN_GENLAYERFILE, TW_METADATA
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
            if not v.LE_GEOMETRYFIELD.text().strip():
                v.LE_GEOMETRYFIELD.setText("Geom2157")
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

        out_path = os.path.join(self.out_dir, f"{_safe_name(ctx['name'])}.layer")
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(rendered)
        except Exception as ex:
            QMessageBox.critical(v, "Error", f"Write failed: {ex}")
            print("Write failed:", ex)
            return

        QMessageBox.information(v, "Done", f"Wrote layer:\n{out_path}")
        print("Wrote layer:", out_path)

    # ---------- data ----------

    def _collect_ctx(self) -> Dict[str, Any]:
        v = self.ui

        def _t(obj_name: str, default: str = "") -> str:
            w = getattr(v, obj_name, None)
            return w.text().strip() if w else default

        # Basics
        name = _t("LE_LAYERNAME")
        group = _t("LE_GROUP")

        if getattr(v, "RB_POINT", None) and v.RB_POINT.isChecked():
            gtype = "POINT"
        elif getattr(v, "RB_POLYGON", None) and v.RB_POLYGON.isChecked():
            gtype = "POLYGON"
        else:
            gtype = "LINE"

        # Data
        schema_table = _t("LE_SCHEMATABLE")
        id_col = _t("LE_UNIQUEID")
        geom_field = _t("LE_GEOMETRYFIELD", "Geom2157") or "Geom2157"
        use_la_filter = bool(getattr(v, "CBX_LA_FILTER", None) and v.CBX_LA_FILTER.isChecked())

        # Style / labels
        label_field = _t("LE_LABELFIELD") or None

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
