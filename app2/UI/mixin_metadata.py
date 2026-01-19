# app2/UI/mixin_metadata.py
import pprint


pp = pprint.PrettyPrinter(indent=4)

class MetadataMixin:
    """
    We're using @staticmethod to keep a tidy namespace of UI helper functions without inheriting them. That:
    avoids the Qt/SIP multiple-inheritance issues,
    makes calls explicit (MetadataMixin.method(self, ...)),
    and lets you keep expanding with more mixins (Sorters, Filters) in the same safe pattern.
    """
    @staticmethod
    def setup_metadata_connections(owner):
        """Connect all metadata fields with proper change tracking."""
        # Text fields
        text_fields = {
            'Window': owner.LE_Window,
            'Model': owner.LE_Model,
            'HelpPage': owner.LE_Help,
            'Controller': owner.LE_Controller,
        }
        for field, widget in text_fields.items():
            widget.textChanged.connect(
                MetadataMixin._create_metadata_updater(owner, field, str)
            )

        # Combo boxes
        owner.CB_service.currentTextChanged.connect(
            MetadataMixin._create_metadata_updater(owner, 'Service', str)
        )

        # Checkboxes – use the *same* keys the controller/DB use
        checkboxes = {
            'IsSpatial':     owner.CBX_IsSpatial,
            'ExcelExporter': owner.CBX_Excel,
            'ShpExporter':   owner.CBX_Shapefile,
            'IsSwitch':      owner.CBX_IsSwitch,
        }
        for field, widget in checkboxes.items():
            widget.stateChanged.connect(
                MetadataMixin._create_metadata_updater(owner, field, bool)
            )

        # Special cases
        owner.CB_ID.currentTextChanged.connect(
            MetadataMixin._create_metadata_updater(owner, 'IdField', str)
        )
        owner.CB_GETID.currentTextChanged.connect(
            MetadataMixin._create_metadata_updater(owner, 'GetId', str)
        )


    @staticmethod
    def _create_metadata_updater(owner, field_name, type_converter):
        def updater(value):
            if getattr(owner, "is_loading", False):
                return
            if hasattr(owner.controller, 'active_mdata'):
                try:
                    if isinstance(value, str) and not value.strip():
                        owner.controller.active_mdata[field_name] = None
                    else:
                        owner.controller.active_mdata[field_name] = type_converter(value)
                except (ValueError, TypeError):
                    owner.controller.active_mdata[field_name] = None
        return updater

    @staticmethod
    def populate_combo_boxes(owner):
        active_columns = owner.controller.active_columns or []
        active_columns_with_no_order = [""] + active_columns

        owner.set_combo_box(
            owner.CB_ID,
            active_columns_with_no_order,
            owner.controller.active_mdata.get("IdField", ""),
        )
        owner.set_combo_box(
            owner.CB_GETID,
            active_columns_with_no_order,
            owner.controller.active_mdata.get("GetId", ""),
        )

        service_value = owner.controller.active_mdata.get("Service", "")
        owner.CB_service.setCurrentText(str(service_value) if service_value else "")

        owner.LE_IDPROPERTY.clear()
        owner.LE_DATAPROPERTY.clear()
        owner.LE_EDITURL.clear()
        for _, col_data in owner.controller.columns_with_data.items():
            if "edit" in col_data and col_data["edit"] is not None:
                owner.LE_IDPROPERTY.setText(col_data["edit"].get("groupEditIdProperty", ""))
                owner.LE_DATAPROPERTY.setText(col_data["edit"].get("groupEditDataProp", ""))
                owner.LE_EDITURL.setText(col_data["edit"].get("editServiceUrl", ""))
                break

        owner.set_combo_box(owner.CB_SelectLocalField, active_columns_with_no_order, "")
        owner.set_combo_box(owner.CB_SelectDataIndex,  active_columns_with_no_order, "")

    @staticmethod
    def populate_line_edits(owner):
        
        if not hasattr(owner.controller, "active_mdata"):
            return
        mdata = owner.controller.active_mdata
        owner.LE_Window.blockSignals(True)
        owner.LE_Model.blockSignals(True)
        owner.LE_Help.blockSignals(True)
        owner.LE_Controller.blockSignals(True)
        try:
            owner.LE_Window.setText(mdata.get("Window") or "")
            owner.LE_Model.setText(mdata.get("Model") or "")
            owner.LE_Help.setText(mdata.get("HelpPage") or "")
            owner.LE_Controller.setText(mdata.get("Controller") or "")
        finally:
            owner.LE_Window.blockSignals(False)
            owner.LE_Model.blockSignals(False)
            owner.LE_Help.blockSignals(False)
            owner.LE_Controller.blockSignals(False)

    @staticmethod
    def populate_checkboxes(owner):
        md = owner.controller.active_mdata or {}
        MetadataMixin.set_checkbox(owner.CBX_IsSwitch, bool(md.get("IsSwitch", False)))
        MetadataMixin.set_checkbox(owner.CBX_Excel, bool(md.get("ExcelExporter", False)))
        MetadataMixin.set_checkbox(owner.CBX_IsSpatial, bool(md.get("IsSpatial", False)))
        MetadataMixin.set_checkbox(owner.CBX_Shapefile, bool(md.get("ShpExporter", False)))

    @staticmethod
    def set_checkbox(checkbox, condition):
        checkbox.setChecked(True if condition else False)
