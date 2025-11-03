from PyQt5.QtWidgets import QApplication, QMessageBox, QProgressDialog
from PyQt5.QtCore import Qt
from app2.wfs_to_db import WFSToDB
from grid_generator.grid_from_db import GridGenerator, GridGenerationError
import settings  # app2/settings.py

class ServicesMixin:
    @staticmethod
    def add_new_layer_to_db(owner):
        """Import a WFS layer into the DB, using WFSToDB's _layer_exists for pre/post checks."""
        progress = None
        try:
            layer_name = owner.CB_MAPLAYERS.currentText().strip()
            if not layer_name:
                QMessageBox.warning(owner, "Select a layer", "Pick a layer from CB_MAPLAYERS first.")
                return

            # Initialise the importer
            wfs_url = settings.WFS_URL
            importer = WFSToDB(
                owner.controller.db_path,
                wfs_url,
                timeout=settings.WFS_READ_TIMEOUT,
                connect_timeout=settings.WFS_CONNECT_TIMEOUT,
                retries=settings.WFS_RETRY_ATTEMPTS,
                backoff_factor=settings.WFS_RETRY_BACKOFF,
            )

            # --- PRE-FLIGHT: does it already exist? ---
            if importer._layer_exists(layer_name):
                QMessageBox.information(
                    owner,
                    "Already exists",
                    f"Layer '{layer_name}' is already in the database. No changes were made.",
                )
                ## owner.controller.read_db(layer_name)
                return

            # --- Import process ---
            progress = QProgressDialog("Importing layer from WFS...", None, 0, 0, owner)
            progress.setWindowModality(Qt.WindowModal)
            progress.setRange(0, 100)
            progress.show()
            QApplication.processEvents()

            importer.run(layer_name)

            # --- POST-FLIGHT: verify creation ---
            if not importer._layer_exists(layer_name):
                raise RuntimeError(f"Layer '{layer_name}' was not created. See logs for details.")

            # --- Refresh UI ---
            owner.controller.read_db(layer_name)
            progress.setValue(100)
            QMessageBox.information(owner, "Success", f"Layer '{layer_name}' added to the database.")

        except Exception as e:
            QMessageBox.critical(owner, "WFS import failed", str(e))
        finally:
            if progress is not None:
                progress.close()

    @staticmethod
    def generate_grid(owner):
            """Generate the grid (JS) for the currently loaded layer."""
            progress = None
            try:
                layer_name = (owner.controller.active_layer or "").strip()
                if not layer_name:
                    #QMessageBox.warning(owner, "No layer loaded", "Load a layer first.")
                    raise GridGenerationError("No layer loaded", "Load a layer first.")

                # Resolve folders expected by GridGenerator
                # Prefer controller-provided paths, then fall back to settings
                py_root = getattr(owner.controller, "pms_maps_folder", None) or getattr(settings, "PMS_MAPS_DIR", None)
                js_root = getattr(owner.controller, "js_root_folder", None) or getattr(settings, "PMS_JS_ROOT", None)

                if not py_root or not js_root:
                    QMessageBox.critical(
                        owner,
                        "Path error",
                        "Missing project paths for Grid generation.\n"
                        f"py_root={py_root!r}\njs_root={js_root!r}"
                    )
                    return

                # Force-commit any in-progress edits (spin boxes, line edits)
                # Not sure if we want this but will leave it for now
                for w in (owner.DSB_Zeros, owner.DSB_NullVal, owner.DSB_ColumnFlex, owner.LE_NullText):
                    try:
                        # QAbstractSpinBox: ensure text is parsed into value
                        if hasattr(w, "interpretText"):
                            w.interpretText()
                        # Drop focus to commit edits
                        w.clearFocus()
                    except Exception:
                        pass

                # Validate and push current UI state to DB (same as Save, but quiet)
                from app2.UI.mixin_columns import ColumnsMixin
                if not ColumnsMixin._validate_edit_before_save(owner):
                    return
                ColumnsMixin.save_column_data(owner)
                owner._update_active_mdata_from_ui()
                try:
                    ordered = ColumnsMixin.get_ordered_listwidget_items(owner)
                    owner.controller.update_display_order_from_ui(ordered)
                except Exception:
                    pass
                owner.controller.save_layer_atomic(owner.controller.db_path)


                progress = QProgressDialog("Generating grid...", None, 0, 0, owner)
                progress.setWindowModality(Qt.WindowModal)
                progress.show()
                QApplication.processEvents()

                # Initialise correctly per grid_from_db.py
                gg = GridGenerator(py_project_folder=py_root, js_project_folder=js_root, project_name="Pms")

                # Pass db_path to generate_grid as required by grid_from_db.py
                gg.generate_grid(layer_name, db_path=owner.controller.db_path)

                progress.setValue(100)
                QMessageBox.information(owner, "Success", f"Grid generated for '{layer_name}'.")
            except GridGenerationError as ge:
                QMessageBox.critical(owner, "Grid generation failed", str(ge))
                return
            except Exception as e:
                QMessageBox.critical(owner, "Grid generation crashed", str(e))
                return
            finally:
                if progress is not None:
                    progress.close()

    @staticmethod
    def add_new_columns(owner):
        """Create/append missing columns for the current layer."""
        progress = None
        try:
            layer_name = (owner.controller.active_layer_name or "").strip()
            if not layer_name:
                QMessageBox.warning(owner, "No layer loaded", "Load a layer first.")
                return

            progress = QProgressDialog("Adding new columns...", None, 0, 0, owner)
            progress.setWindowModality(Qt.WindowModal)
            progress.show()
            QApplication.processEvents()

            # Reuse your existing controller method if present, else call a helper
            # Replace this call with your real implementation:
            owner.controller.add_missing_columns_for_layer(layer_name)

            # Reload so UI reflects any new fields
            owner.controller.read_db(layer_name)

            progress.setValue(100)
            QMessageBox.information(owner, "Success", f"New columns added for '{layer_name}'.")
        except AttributeError:
            # Fallback: if controller doesn’t have the helper yet
            QMessageBox.warning(
                owner,
                "Not implemented",
                "add_missing_columns_for_layer is not available on the controller."
            )
        except Exception as e:
            QMessageBox.critical(owner, "Add columns failed", str(e))
        finally:
            if progress is not None:
                progress.close()

