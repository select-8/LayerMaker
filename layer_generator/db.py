import os
import configparser
from typing import List, Tuple, Sequence, Any

import pyodbc

# Load minimal config once
_CONF = configparser.ConfigParser()
_CONF.read(os.path.join(os.path.dirname(__file__), "db.conf"), encoding="utf-8")
_SEC = _CONF["sqlserver"]

_DRIVER = _SEC.get("driver", "ODBC Driver 17 for SQL Server")
_SERVER = _SEC["server"].strip()
_DATABASE = _SEC["database"].strip()
_TRUSTED = _SEC.get("trusted_connection", "yes")
_ENCRYPT = _SEC.get("encrypt", "yes")
_TRUST_CERT = _SEC.get("trust_server_certificate", "no")
_CONN_TIMEOUT = _SEC.getint("connection_timeout_seconds", fallback=15)
_QUERY_TIMEOUT = _SEC.getint("query_timeout_seconds", fallback=15)

def _conn_str() -> str:
    parts = [
        f"DRIVER={{{_DRIVER}}}",
        f"SERVER={_SERVER}",
        f"DATABASE={_DATABASE}",
        f"Trusted_Connection={_TRUSTED}",
        f"Encrypt={_ENCRYPT}",
    ]
    if _TRUST_CERT.lower() in ("yes", "true", "1"):
        parts.append("TrustServerCertificate=Yes")
    if _CONN_TIMEOUT:
        parts.append(f"Connection Timeout={_CONN_TIMEOUT}")
    return ";".join(parts) + ";"

def get_connection() -> pyodbc.Connection:
    """
    Open a pyodbc connection using Windows Trusted Connection.
    Raises pyodbc.Error if it cannot connect.
    """
    cn = pyodbc.connect(_conn_str(), autocommit=True)
    if _QUERY_TIMEOUT:
        cn.timeout = _QUERY_TIMEOUT
    return cn

def fetch_all(sql: str, params: Sequence[Any] = ()) -> List[dict]:
    """
    Run a parameterised SELECT (use ? placeholders) and return rows as list[dict].
    """
    with get_connection() as cn:
        cur = cn.cursor()
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

def list_views(schema: str) -> List[str]:
    """
    Return fully-qualified view names for a given schema, e.g. ['dbo.ViewA', 'dbo.ViewB'].
    """
    rows = fetch_all(
        """
        SELECT TABLE_NAME
        FROM INFORMATION_SCHEMA.VIEWS
        WHERE TABLE_SCHEMA = ?
        ORDER BY TABLE_NAME
        """,
        (schema,),
    )
    return [f"{schema}.{r['TABLE_NAME']}" for r in rows]

def list_columns(schema_table: str) -> List[str]:
    """
    Return column names for 'schema.table' (schema required).
    """
    if "." not in schema_table:
        raise ValueError("Expected 'schema.table'")
    schema, table = schema_table.split(".", 1)
    rows = fetch_all(
        """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
        ORDER BY COLUMN_NAME
        """,
        (schema, table),
    )
    return [r["COLUMN_NAME"] for r in rows]

def list_geometry_columns(schema_table: str) -> List[str]:
    """Return geometry/geography columns for 'schema.table'."""
    if "." not in schema_table:
        raise ValueError("Expected 'schema.table'")
    schema, table = schema_table.split(".", 1)
    rows = fetch_all(
        """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
          AND DATA_TYPE IN ('geometry','geography')
        ORDER BY COLUMN_NAME
        """,
        (schema, table),
    )
    return [r["COLUMN_NAME"] for r in rows]

def ping() -> bool:
    """
    Quick connectivity check.
    """
    try:
        _ = fetch_all("SELECT 1 AS ok")
        return True
    except pyodbc.Error:
        return False
