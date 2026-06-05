"""Engine lifecycle manager — caches WrenEngine instances keyed by manifest hash."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import threading
from typing import Any

logger = logging.getLogger("wren-bridge")


class EngineManager:
    """Manages WrenEngine instances for the bridge service.

    The legacy UI sends the full manifest with each request. We cache
    WrenEngine instances keyed by a hash of the manifest to avoid
    re-creating them on every call.
    """

    def __init__(self):
        self._engines: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._duckdb_init_sql: str | None = None
        self._duckdb_session_sql: str | None = None
        self._duckdb_conn = None

    def get_engine(self, manifest: dict | None):
        """Get or create a WrenEngine for the given manifest.

        The manifest is provided as a JSON dict (camelCase, as the UI sends it).
        We base64-encode it for the WrenEngine constructor.
        """
        from wren.engine import WrenEngine  # noqa: PLC0415
        from wren.model.data_source import DataSource  # noqa: PLC0415

        if manifest is None:
            raise ValueError("No manifest provided")

        manifest_json = json.dumps(manifest, sort_keys=True)
        manifest_hash = hashlib.sha256(manifest_json.encode()).hexdigest()[:16]

        with self._lock:
            if manifest_hash in self._engines:
                return self._engines[manifest_hash]

        # Base64-encode the manifest JSON for WrenEngine
        manifest_b64 = base64.b64encode(manifest_json.encode()).decode()

        # Determine data source from manifest
        ds_name = manifest.get("dataSource", "duckdb")
        try:
            ds = DataSource(ds_name.lower())
        except ValueError:
            ds = DataSource("duckdb")

        conn_info = {"format": "csv", "url": "."} if ds == DataSource.duckdb else {}
        engine = WrenEngine(
            manifest_str=manifest_b64,
            data_source=ds,
            connection_info=conn_info,
        )

        with self._lock:
            # Evict old engines if too many (keep last 5)
            if len(self._engines) >= 5:
                oldest_key = next(iter(self._engines))
                old_engine = self._engines.pop(oldest_key)
                try:
                    old_engine.close()
                except Exception:
                    pass
            self._engines[manifest_hash] = engine

        return engine

    def set_duckdb_init_sql(self, sql: str):
        """Store DuckDB init SQL for later use."""
        self._duckdb_init_sql = sql
        # Reset the connection so it gets re-created with new init SQL
        if self._duckdb_conn is not None:
            try:
                self._duckdb_conn.close()
            except Exception:
                pass
            self._duckdb_conn = None

    def set_duckdb_session_sql(self, sql: str):
        """Store DuckDB session SQL."""
        self._duckdb_session_sql = sql

    def get_duckdb_connection(self):
        """Get a DuckDB connection, initialised with any stored init SQL."""
        if self._duckdb_conn is None:
            import duckdb  # noqa: PLC0415

            self._duckdb_conn = duckdb.connect()
            if self._duckdb_init_sql:
                for stmt in self._duckdb_init_sql.strip().split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        try:
                            self._duckdb_conn.execute(stmt)
                        except Exception as e:
                            logger.warning(f"DuckDB init SQL error: {e}")
            if self._duckdb_session_sql:
                for stmt in self._duckdb_session_sql.strip().split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        try:
                            self._duckdb_conn.execute(stmt)
                        except Exception as e:
                            logger.warning(f"DuckDB session SQL error: {e}")
        return self._duckdb_conn

    def close(self):
        """Close all cached engines and connections."""
        with self._lock:
            for engine in self._engines.values():
                try:
                    engine.close()
                except Exception:
                    pass
            self._engines.clear()
        if self._duckdb_conn is not None:
            try:
                self._duckdb_conn.close()
            except Exception:
                pass
            self._duckdb_conn = None
