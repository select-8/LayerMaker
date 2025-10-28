# app2/UI/mixin_dialogs.py

from PyQt5.QtWidgets import QDialog, QFileDialog
import mappyfile

class DialogsMixin:
    @staticmethod
    def open_layer_selector(owner):
        from app2.layer_select_dialog import LayerSelectDialog
        db_path = owner.controller.db_path
        dialog = LayerSelectDialog(db_path, parent=owner)
        if dialog.exec_() == QDialog.Accepted:
            selected_layer = dialog.selected_layer
            if selected_layer:
                print(f"Loading layer: {selected_layer}")
                owner.controller.read_db(selected_layer)
                owner.populate_ui()

    @staticmethod
    def openmapfile_filehandler(owner):
        print("MapDir: ", owner.controller.mapfiles_dir)
        fname = QFileDialog.getOpenFileName(
            owner,
            "Open file",
            owner.controller.mapfiles_dir,
            "map Files (*.map)",
        )
        print("mapfile fname", fname)
        if fname and fname[0] != "":
            DialogsMixin.get_layer_list_from_mapfile_and_populate_listwidget(owner, fname[0])

    @staticmethod
    def get_layer_list_from_mapfile_and_populate_listwidget(owner, mapfile_path):
        mapfile = mappyfile.open(mapfile_path)
        layers = mapfile["layers"]
        layer_names = [layer["name"] for layer in layers]
        owner.CB_MAPLAYERS.clear()
        owner.CB_MAPLAYERS.addItems(layer_names)
