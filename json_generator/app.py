import sys

from PyQt5 import QtWidgets

from main_window import LayerConfigNewLayerWizard


def main():
    app = QtWidgets.QApplication(sys.argv)
    window = LayerConfigNewLayerWizard()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
