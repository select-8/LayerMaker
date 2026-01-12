import sys
from PyQt5 import QtWidgets, uic
from PyQt5.QtGui import QFont


def main():
    app = QtWidgets.QApplication(sys.argv)

    # Set global application font
    font = QFont("Segoe UI", 9)
    app.setFont(font)

    # Load the UI file
    ui_path = r"C:\DevOps\LayerMaker\QTFiles\LayerMaker_Manual_redo_fixed_aligned3_toplevel_tabs.ui"
    window = uic.loadUi(ui_path)

    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
