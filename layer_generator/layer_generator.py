# layer_generator_main.py
# Minimal runner for MapServer layer generation from your Qt UI using Jinja.
# Places the output .layer file in the same directory as this script.
import os
import re
import sys
from typing import List

from PyQt5 import QtWidgets, uic
from PyQt5.QtWidgets import QColorDialog, QMessageBox
from jinja2 import Environment, FileSystemLoader, StrictUndefined


class LayerGenerator(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.ui_path = os.path.join(self.base_dir, "LayerMaker_GUI_v1.ui")
        self.template_path = os.path.join(self.base_dir, "layer.template")

        if not os.path.exists(self.ui_path):
            raise FileNotFoundError("Could not find LayerMaker_GUI_v1.ui next to this script")
        if not os.path.exists(self.template_path):
            raise FileNotFoundError("Could not find layer.template next to this script")

        uic.loadUi(self.ui_path, self)

        # Default colour if user never picks one
        self.colour_rgb: List[int] = [12, 120, 200]

        # Sensible defaults
        self._ensure_defaults()

        # Wire up buttons
        if hasattr(self, "BTN_COLOURPICKER"):
            self.BTN_COLOURPICKER.clicked.connect(self.pick_colour)
        if hasattr(self, "BTN_GENLAYERFILE"):
            self.BTN_GENLAYERFILE.clicked.connect(self.generate_layer_file)

    # ---------- UI helpers ----------
    def _le(self, name: str):
        return getattr(self, name, None)

    def _get_text(self, name: str, default: str = "") -> str:
        w = self._le(name)
        if w is not None:
            return w.text().strip()
        return default

    def _ensure_defaults(self) -> None:
        # Geometry type default: LINE if none selected
        if hasattr(self, "RB_LINE") and hasattr(self, "RB_POINT") and hasattr(self, "RB_POLYGON"):
            if not (self.RB_POINT.isChecked() or self.RB_LINE.isChecked() or self.RB_POLYGON.isChecked()):
                self.RB_LINE.setChecked(True)

        # Geometry field default
        le_geom = self._le("LE_GEOMETRYFIELD")
        if le_geom is not None and not le_geom.text().strip():
            le_geom.setText("Geom2157")

        # LA filter default to checked if present
        if hasattr(self, "CBX_LA_FILTER"):
            self.CBX_LA_FILTER.setChecked(True)

    def pick_colour(self) -> None:
        c = QColorDialog.getColor()
        if c.isValid():
            self.colour_rgb = [int(c.red()), int(c.green()), int(c.blue())]
            # Optional: give a visual cue on the button
            if hasattr(self, "BTN_COLOURPICKER"):
                self.BTN_COLOURPICKER.setStyleSheet(
                    "QPushButton { background-color: rgb(%d,%d,%d); }"
                    % (self.colour_rgb[0], self.colour_rgb[1], self.colour_rgb[2])
                )

    # ---------- Data collection ----------
    def collect_values(self) -> dict:
        # Required
        name = self._get_text("LE_LAYERNAME")
        group = self._get_text("LE_GROUP")
        schema_table = self._get_text("LE_SCHEMATABLE")
        id_col = self._get_text("LE_UNIQUEID")

        # Geometry type
        if hasattr(self, "RB_POINT") and self.RB_POINT.isChecked():
            gtype = "POINT"
        elif hasattr(self, "RB_POLYGON") and self.RB_POLYGON.isChecked():
            gtype = "POLYGON"
        else:
            gtype = "LINE"

        # Geometry field (editable, default Geom2157)
        geom_field = self._get_text("LE_GEOMETRYFIELD", "Geom2157") or "Geom2157"

        # LA filter
        use_la_filter = False
        if hasattr(self, "CBX_LA_FILTER"):
            use_la_filter = bool(self.CBX_LA_FILTER.isChecked())

        # Style / label
        label_field = self._get_text("LE_LABELFIELD", "")

        # Optional metadata widgets (safe fallbacks in template)
        ows_title = None
        ows_abstract = None
        if hasattr(self, "LE_OWS_TITLE"):
            ows_title = self._get_text("LE_OWS_TITLE") or None
        if hasattr(self, "TE_OWS_ABSTRACT"):
            try:
                ows_abstract = self.TE_OWS_ABSTRACT.toPlainText().strip() or None
            except Exception:
                ows_abstract = None

        # Build context for Jinja
        ctx = {
            "name": name,
            "group": group,
            "gtype": gtype,
            "schema_table": schema_table,
            "id_col": id_col,
            "geom_field": geom_field,
            "use_la_filter": use_la_filter,
            "colour": self.colour_rgb,        # [R, G, B]
            "label_field": label_field or None,
            "ows_title": ows_title,
            "ows_abstract": ows_abstract,
        }
        return ctx

    # ---------- Validation ----------
    def validate(self, ctx: dict) -> List[str]:
        errs: List[str] = []

        if not ctx["name"]:
            errs.append("Layer Name is required")
        if not ctx["group"]:
            errs.append("Group is required")
        if not ctx["schema_table"]:
            errs.append("Schema.Table is required")
        if not ctx["id_col"]:
            errs.append("Unique ID column is required")

        # Basic geometry field sanity. Warn but do not block for advanced use.
        geom_field = ctx.get("geom_field", "")
        if geom_field and not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", geom_field):
            errs.append("Geometry field should be a simple column name, e.g. Geom2157")

        # Colour sanity
        colour = ctx.get("colour", [])
        if not (isinstance(colour, list) and len(colour) == 3 and all(isinstance(v, int) for v in colour)):
            errs.append("Colour must be three integers [R, G, B]")
        else:
            for v in colour:
                if v < 0 or v > 255:
                    errs.append("Colour values must be in the range 0 to 255")
                    break

        return errs

    # ---------- Render + save ----------
    def generate_layer_file(self) -> None:
        try:
            ctx = self.collect_values()
            errs = self.validate(ctx)
            if errs:
                QMessageBox.warning(self, "Cannot generate", "\n".join(errs))
                return

            # Prepare Jinja environment
            env = Environment(
                loader=FileSystemLoader(self.base_dir),
                keep_trailing_newline=True,
                lstrip_blocks=True,
                trim_blocks=True,
                undefined=StrictUndefined,
            )
            tmpl = env.get_template("layer.template")
            rendered = tmpl.render(**ctx)

            # Output filename beside the script
            safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", ctx["name"]).strip("_") or "layer"
            out_path = os.path.join(self.base_dir, f"{safe_name}.layer")

            with open(out_path, "w", encoding="utf-8") as f:
                f.write(rendered)

            QMessageBox.information(self, "Done", f"Layer file written:\n{out_path}")
            print("Layer file written:", out_path)

        except Exception as ex:
            QMessageBox.critical(self, "Error", str(ex))
            print("Error:", str(ex))


def main():
    app = QtWidgets.QApplication(sys.argv)
    win = LayerGenerator()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
