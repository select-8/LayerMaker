import sys
import os

from PyQt5 import QtWidgets

# Support both `python json_generator/app.py` (script) and `python run_jsongen.py` (package)
if __package__ is None or __package__ == "":
    _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    from json_generator.main_window import LayerConfigNewLayerWizard
else:
    from .main_window import LayerConfigNewLayerWizard


def main():
    app = QtWidgets.QApplication(sys.argv)
    window = LayerConfigNewLayerWizard()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
