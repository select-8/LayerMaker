import sqlite3
import logging
import time
import requests
import urllib.parse as urlparse
import socket
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from owslib.wfs import WebFeatureService   # <- external dep (pip install owslib)
import warnings

# Logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Keep a sane global socket timeout as a safety net
socket.setdefaulttimeout(60)

# Default column values
DEFAULT_COLUMN_VALUES = {
    "Flex": 0.3,
    "InGrid": 1,
    "Hidden": 0,
    "NullText": None,
    "NullValue": 0,
    "Zeros": None,
    "NoFilter": 0,
    "Editable": 0,
    "CustomListValues": None,
}

# Global filters mapping: property name -> filter LocalField
# GLOBAL_FILTERS = {
#     "LocalAuthority": "LocalAuthority",
#     "UsageClassificationName": "UsageClassification",
#     "MunicipalDistrictName": "MunicipalDistrict",
#     "ShortName": "ShortName",
# }

# Type mapping for Renderer and FilterType
TYPE_MAPPING = {
    "boolean": ("booleancolumn", "boolean"),
    "integer": ("numbercolumn", "number"),
    "long": ("numbercolumn", "number"),
    "double": ("numbercolumn", "number"),
    "float": ("numbercolumn", "number"),
    "timeinstanttype": ("datecolumn", "date"),
    "string": ("gridcolumn", "string"),
}

class DuplicateLayerNameError(Exception):
    """Raised when a layer name already exists in Layers."""
    pass

class WFSToDB:
    def __init__(
        self,
        db_path,
        wfs_url,
        timeout=180,
        wfs_version="2.0.0",
        connect_timeout=45,
        retries=3,
        backoff_factor=1.5,
    ):
        """
        db_path: Path to your SQLite DB
        wfs_url: Base WFS endpoint (e.g. http://127.0.0.1:81/mapserver2)
        wfs_version: WFS version to use (default 2.0.0)
        """
        self.db_path = db_path
        self.wfs_url = wfs_url.rstrip("?&")
        self.timeout = timeout
        self.connect_timeout = connect_timeout
        self.max_retries = retries
        self.backoff_factor = backoff_factor
        self.wfs_version = wfs_version

        # One session for all HTTP calls; ignore env proxies (IIS + localhost)
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({"User-Agent": "MapMaker/1.0", "Connection": "close"})

        retry_cfg = Retry(
            total=self.max_retries,
            status_forcelist=[408, 425, 429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
            backoff_factor=self.backoff_factor,
        )
        adapter = HTTPAdapter(max_retries=retry_cfg)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    # ------------------------
    # Schema via OWSLib (WFS 2.0.0)
    # ------------------------
    def _capabilities_url(self) -> str:
        parts = urlparse.urlsplit(self.wfs_url)
        q = dict(urlparse.parse_qsl(parts.query, keep_blank_values=True))
        q.update({"service": "WFS", "request": "GetCapabilities", "version": self.wfs_version})
        return urlparse.urlunsplit((parts.scheme, parts.netloc, parts.path, urlparse.urlencode(q), parts.fragment))

    def _clean_props(self, props: dict) -> dict:
        """
        Normalize property dict from OWSLib: drop geometry, normalize names/types.
        """
        out = {}
        for k, v in (props or {}).items():
            # Normalize name (strip ns)
            name = (k or "").split(":")[-1]
            lname = name.lower()
            # Skip geometry-ish fields
            if lname in {"msgeometry", "the_geom", "geom", "shape"} or "geom" in lname:
                continue

            # Normalize type (lowercase, drop ns)
            t = (v or "")
            if isinstance(t, (list, tuple)):
                t = t[0] if t else ""
            t = str(t).split(":")[-1].lower()

            # MapServer date often appears as 'timeinstanttype'
            # Anything unrecognized falls back to 'string' later during renderer mapping
            out[name] = t or "string"
        return out

    def get_schema(self, typename: str) -> dict:
        """
        Use OWSLib (WFS 2.0.0) to return {field_name: type}.
        Assumes your service and layer are healthy (you tested this).
        """
        if ":" not in typename:
            typename = f"ms:{typename}"

        # Fetch capabilities with our session/timeouts and feed XML to OWSLib
        url = self._capabilities_url()
        logger.info(f"[WFS/OWSLib] GET {url}")
        r = self.session.get(
            url,
            timeout=(self.connect_timeout, self.timeout),
            allow_redirects=True,
        )
        r.raise_for_status()
        logger.info(f"[WFS/OWSLib] Capabilities {len(r.content)} bytes")

        try:
            from owslib.wfs import WebFeatureService
        except ImportError as e:
            raise RuntimeError("OWSLib is required (pip install owslib)") from e

        wfs = WebFeatureService(url=self.wfs_url, version=self.wfs_version, xml=r.content)
        logger.info(f"[WFS/OWSLib] Using base URL for DFT: {getattr(wfs, 'url', None)}")

        t0 = time.time()
        schema = wfs.get_schema(typename)
        print(schema)
        logger.info(f"[WFS/OWSLib] DescribeFeatureType OK in {time.time() - t0:.2f}s (v{self.wfs_version})")

        props = self._clean_props(schema.get("properties", {}))

        if not props:
            raise RuntimeError(f"No non-geometry fields found for {typename}")
        return props

    # ------------------------
    # DB helpers
    # ------------------------

    def _layer_exists(self, name: str) -> bool:
        name = (name or "").strip()
        if not name:
            return False
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute("SELECT 1 FROM Layers WHERE Name = ? LIMIT 1", (name,))
            return cur.fetchone() is not None
        finally:
            conn.close()

    def determine_extype_from_wfs(self, prop_type: str) -> str:
        """
        Map MapServer/OWSLib types to a simple 'extype' used by the UI:
          - TimeInstantType -> date
          - integer/long/double/float -> number
          - boolean -> boolean
          - default -> string
        """
        t = (prop_type or "").lower().split(":")[-1]
        if t == "timeinstanttype":
            return "date"
        if t in {"integer", "long", "double", "float"}:
            return "number"
        if t == "boolean":
            return "boolean"
        return "string"

    def get_table_columns(self, conn, table_name: str) -> set[str]:
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table_name})")
        return {row["name"] for row in cur.fetchall()}

    def determine_renderer_filter(self, prop_type):
        return TYPE_MAPPING.get((prop_type or "").lower(), ("gridcolumn", "string"))

    def resolve_renderer_id(self, cursor, renderer_name):
        cursor.execute(
            "SELECT GridColumnRendererId FROM GridColumnRenderers WHERE LOWER(Renderer) = LOWER(?)",
            (renderer_name,),
        )
        row = cursor.fetchone()
        return row["GridColumnRendererId"] if row else None

    def insert_layer_metadata(self, conn, layer_name):
        name = layer_name.strip()
        cur = conn.cursor()

        # 1) Hard stop if it exists (exact match, aligned with your UNIQUE constraint)
        cur.execute("SELECT LayerId FROM Layers WHERE Name = ?", (name,))
        row = cur.fetchone()
        if row:
            raise DuplicateLayerNameError(f"Layer '{name}' already exists (LayerId={row['LayerId']}).")

        # 2) Fresh insert only if not present
        cur.execute("INSERT INTO Layers (Name) VALUES (?)", (name,))
        layer_id = cur.lastrowid

        cur.execute("""
            INSERT INTO GridMData (LayerId, Controller, IsSpatial, ExcelExporter, ShpExporter)
            VALUES (?, 'cmv_grid', 1, 1, 1)
        """, (layer_id,))
        conn.commit()
        return layer_id

    def insert_columns(self, conn, layer_id, properties):
        """
        Insert missing GridColumns for this layer. Dynamically includes optional fields:
        - IndexValue (same as ColumnName)
        - ExType (simple UI type: date/number/boolean/string)
        - Renderer (text) = ExType
        Also sets GridColumnRendererId using TYPE_MAPPING as before.

        NEW: seeds DisplayOrder based on the order properties are seen from the WFS.
             Continues from the current MAX(DisplayOrder) per LayerId.
        """
        cursor = conn.cursor()
        existing_cols = self.get_table_columns(conn, "GridColumns")

        # Determine if DisplayOrder exists in this DB
        has_display_order = "DisplayOrder" in existing_cols

        # Find the current max(DisplayOrder) for this layer, default 0
        next_disp = 1
        if has_display_order:
            cursor.execute(
                "SELECT COALESCE(MAX(DisplayOrder), 0) AS mx FROM GridColumns WHERE LayerId = ?",
                (layer_id,),
            )
            row = cursor.fetchone()
            next_disp = (row["mx"] or 0) + 1

        # Iterate in the order received from WFS (properties is already ordered in Py3.7+)
        for prop_name, prop_type in (properties or {}).items():
            # Skip if already present for this layer
            cursor.execute(
                "SELECT 1 FROM GridColumns WHERE LayerId = ? AND ColumnName = ?",
                (layer_id, prop_name),
            )
            if cursor.fetchone():
                logger.info(f"Column '{prop_name}' already exists, skipping")
                continue

            # Derive renderer/filter & extype
            renderer_key, filter_type = self.determine_renderer_filter(prop_type)
            lookup_name = filter_type or renderer_key
            renderer_id = self.resolve_renderer_id(cursor, lookup_name)
            extype = self.determine_extype_from_wfs(prop_type)  # 'date'/'number'/'boolean'/'string'

            # Build a row dict; include only keys that exist in the table
            row = {
                "LayerId": layer_id,
                "ColumnName": prop_name,
                "Text": prop_name,
                "InGrid": DEFAULT_COLUMN_VALUES["InGrid"],
                "Hidden": DEFAULT_COLUMN_VALUES["Hidden"],
                "NullText": DEFAULT_COLUMN_VALUES["NullText"],
                "NullValue": DEFAULT_COLUMN_VALUES["NullValue"],
                "Zeros": DEFAULT_COLUMN_VALUES["Zeros"],
                "NoFilter": DEFAULT_COLUMN_VALUES["NoFilter"],
                "Flex": DEFAULT_COLUMN_VALUES["Flex"],
                "CustomListValues": DEFAULT_COLUMN_VALUES["CustomListValues"],
                "Editable": DEFAULT_COLUMN_VALUES["Editable"],
                "FilterType": filter_type,
                "GridColumnRendererId": renderer_id,
                "GridFilterDefinitionId": None,
                # Optional fields (only added if present in DB schema)
                "IndexValue": prop_name,
                "ExType": extype,
                "Renderer": extype,
            }

            # NEW: seed DisplayOrder incrementally if column exists
            if has_display_order:
                row["DisplayOrder"] = next_disp
                next_disp += 1

            insert_data = {k: v for k, v in row.items() if k in existing_cols}
            cols = ", ".join(insert_data.keys())
            qmarks = ", ".join("?" for _ in insert_data)
            sql = f"INSERT INTO GridColumns ({cols}) VALUES ({qmarks})"

            cursor.execute(sql, tuple(insert_data.values()))
            logger.info(
                f"Inserted GridColumn '{prop_name}' "
                f"(extype={extype}, renderer_id={renderer_id}, filterType={filter_type}"
                + (f", DisplayOrder={insert_data.get('DisplayOrder')}" if has_display_order else "")
                + ")"
            )

        conn.commit()

    def link_applicable_gridfilters(self, conn, layer_id: int, properties: dict) -> int:
        """
        Link default/applicable list filters for columns on this layer
        using GridFilterTypeId / GridFilterTypes.Code.
        Returns number of links created.
        """
        created = 0
        c = conn.cursor()

        # 1) Find all columns on this layer whose filter type is 'list'
        c.execute(
            """
            SELECT gc.GridColumnId, gc.ColumnName
            FROM GridColumns AS gc
            JOIN GridFilterTypes AS gft
              ON gft.GridFilterTypeId = gc.GridFilterTypeId
            WHERE gc.LayerId = ?
              AND LOWER(gft.Code) = 'list'
            """,
            (layer_id,),
        )
        list_columns = c.fetchall()  # rows of (GridColumnId, Name)

        if not list_columns:
            return 0

        # 2) For each 'list' column, ensure a GridFilterDefinitions (or equivalent) row exists
        for col_id, col_name in list_columns:
            # Check if a filter already exists for this column
            c.execute(
                """
                SELECT gfd.GridFilterDefinitionId
                FROM GridFilterDefinitions AS gfd
                WHERE gfd.LayerId = ?
                  AND gfd.LocalField = ?
                """,
                (layer_id, col_name),
            )
            row = c.fetchone()

            if row:
                # Already has a definition — skip
                continue

            # Otherwise, create a skeleton filter definition
            c.execute(
                """
                INSERT INTO GridFilterDefinitions
                    (LayerId, LocalField, DataIndex, IdField, LabelField, Store, StoreId)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    layer_id,
                    col_name,
                    col_name,  # DataIndex defaults to same as LocalField
                    "",
                    "",
                    "",
                    "",
                ),
            )
            created += 1

        conn.commit()
        return created


    # ------------------------
    # Public entry points
    # ------------------------
    def run(self, layer_name):
        name = layer_name.strip()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            # Fast preflight: abort before hitting WFS if layer exists
            cur = conn.cursor()
            cur.execute("SELECT LayerId FROM Layers WHERE Name = ?", (name,))
            row = cur.fetchone()
            if row:
                raise DuplicateLayerNameError(
                    f"Layer '{name}' already exists (LayerId={row['LayerId']})."
                )

            logger.info(f"Fetching schema for '{name}' via OWSLib (WFS {self.wfs_version})...")
            properties = self.get_schema(name)
            logger.info(f"Schema properties: {properties}")

            logger.info("Inserting layer metadata...")
            conn.execute("BEGIN")
            layer_id = self.insert_layer_metadata(conn, name)  # will also guard duplicates

            logger.info("Inserting columns...")
            self.insert_columns(conn, layer_id, properties)

            # Link filters where LocalField and DataIndex both exist in the layer
            linked = self.link_applicable_gridfilters(conn, layer_id, properties)
            logger.info(f"[FILTER] Linked {linked} GridFilterDefinition(s) to layer '{name}'")

            conn.commit()
            logger.info(f"Successfully imported layer '{name}' into DB")

        except DuplicateLayerNameError as e:
            conn.rollback()
            logger.warning(str(e))
            return  # stop: do not modify DB
        except Exception as e:
            conn.rollback()
            logger.exception("Import failed")
            raise
        finally:
            conn.close()


    def get_existing_columns(self, conn, layer_name):
        cursor = conn.cursor()
        cursor.execute("SELECT LayerId FROM Layers WHERE Name = ?", (layer_name,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Layer '{layer_name}' not found in Layers")
        layer_id = row["LayerId"]

        cursor.execute("SELECT ColumnName FROM GridColumns WHERE LayerId = ?", (layer_id,))
        existing = {r["ColumnName"] for r in cursor.fetchall()}
        return layer_id, existing

    def sync_new_columns(self, layer_name):
        """
        Compare schema vs existing GridColumns for layer_name.
        Insert any missing columns. Return list of names added.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            logger.info(f"[SYNC] Starting sync_new_columns for {layer_name} (OWSLib WFS {self.wfs_version})")
            properties = self.get_schema(layer_name)
            logger.info(f"[SYNC] schema returned {len(properties)} fields")
            layer_id, existing = self.get_existing_columns(conn, layer_name)
            new_props = {k: v for k, v in properties.items() if k not in existing}
            print('new_props: ', new_props)
            if not new_props:
                return []
            self.insert_columns(conn, layer_id, new_props)
            linked = self.link_applicable_gridfilters(conn, layer_id, properties)
            if linked:
                logger.info(f"[FILTER] Linked {linked} GridFilterDefinition(s) after syncing new columns")

            return list(new_props.keys())
        finally:
            conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Import WFS layer into MapMaker DB (OWSLib, WFS 2.0.0)")
    parser.add_argument("db_path", help="Path to MapMaker SQLite DB")
    parser.add_argument("wfs_url", help="Base WFS endpoint (e.g. http://127.0.0.1:81/mapserver2)")
    parser.add_argument("layer_name", help="Qualified or unqualified layer name (adds ms: if missing)")
    parser.add_argument("--timeout", type=int, default=180, help="Read timeout (seconds)")
    parser.add_argument(
        "--connect-timeout",
        type=int,
        default=45,
        help="Socket connect timeout in seconds (default 45)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Number of retries for WFS calls (default 3)",
    )
    parser.add_argument(
        "--retry-backoff",
        type=float,
        default=1.5,
        help="Backoff multiplier between retries (default 1.5)",
    )
    parser.add_argument("--version", default="2.0.0", help="WFS version (default 2.0.0)")
    args = parser.parse_args()

    importer = WFSToDB(
        args.db_path,
        args.wfs_url,
        timeout=args.timeout,
        wfs_version=args.version,
        connect_timeout=args.connect_timeout,
        retries=args.retries,
        backoff_factor=args.retry_backoff,
    )
    importer.run(args.layer_name)
