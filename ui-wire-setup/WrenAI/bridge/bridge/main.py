"""Wren Bridge — translates legacy REST APIs to the new wren-core engine.

This FastAPI application implements the HTTP contracts expected by the legacy
wren-ui adaptors (wrenEngineAdaptor.ts and ibisAdaptor.ts), backed by the
new Rust-based WrenEngine from the main branch.

Start with:
    uvicorn bridge.main:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import base64
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

import orjson
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from bridge.engine_manager import EngineManager

logger = logging.getLogger("wren-bridge")
logging.basicConfig(level=logging.DEBUG)

manager = EngineManager()


# ── DuckDB Connection Sharing Monkeypatch ──────────────────────────────
from wren.connector.duckdb import DuckDBConnector

class SharedDuckDBConnector(DuckDBConnector):
    def __init__(self, connection_info):
        from duckdb import HTTPException, IOException
        self._HTTPException = HTTPException
        self._IOException = IOException
        self.connection = manager.get_duckdb_connection()
        if hasattr(connection_info, "format") and connection_info.format == "duckdb":
            self._attach_database(connection_info)

    def close(self) -> None:
        pass

import wren.connector.duckdb
wren.connector.duckdb.DuckDBConnector = SharedDuckDBConnector



@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Wren Bridge starting up")
    yield
    logger.info("Wren Bridge shutting down")
    manager.close()


app = FastAPI(
    title="Wren Bridge",
    description="Legacy API compatibility layer for wren-core",
    lifespan=lifespan,
    default_response_class=ORJSONResponse,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════════════
# Wren Engine API (consumed by wrenEngineAdaptor.ts)
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/v1/mdl/status")
def mdl_status():
    """Return engine deploy status.

    The legacy UI polls this to check if the engine is ready.
    """
    return {"systemStatus": "READY", "version": "bridge-0.1.0"}


@app.get("/v1/mdl/preview")
async def mdl_preview(request: Request):
    """Preview data through the MDL semantic layer.

    Legacy UI sends: GET /v1/mdl/preview with JSON body {sql, manifest, limit}
    """
    body = await _read_json_body(request)
    sql = body.get("sql")
    manifest = body.get("manifest")
    limit = body.get("limit", 500)

    if not sql or not manifest:
        raise HTTPException(400, "Missing 'sql' or 'manifest'")

    try:
        engine = manager.get_engine(manifest)
        result = engine.query(sql, limit=limit)
        return _arrow_to_engine_response(result)
    except Exception as e:
        logger.exception("preview error")
        raise HTTPException(500, {"message": str(e)})


@app.get("/v1/mdl/dry-plan")
async def mdl_dry_plan(request: Request):
    """Plan SQL through MDL — returns native SQL string.

    Legacy UI sends: GET /v1/mdl/dry-plan with JSON body {sql, manifest, modelingOnly}
    """
    body = await _read_json_body(request)
    sql = body.get("sql")
    manifest = body.get("manifest")

    if not sql:
        raise HTTPException(400, "Missing 'sql'")

    try:
        engine = manager.get_engine(manifest)
        planned = engine.dry_plan(sql)
        return Response(content=planned, media_type="text/plain")
    except Exception as e:
        logger.exception("dry-plan error")
        raise HTTPException(500, {"message": str(e)})


@app.get("/v1/mdl/dry-run")
async def mdl_dry_run(request: Request):
    """Dry-run SQL — parse and validate, return column metadata.

    Legacy UI sends: GET /v1/mdl/dry-run with JSON body {sql, manifest}
    Returns: [{name, type}, ...]
    """
    body = await _read_json_body(request)
    sql = body.get("sql")
    manifest = body.get("manifest")

    if not sql:
        raise HTTPException(400, "Missing 'sql'")

    try:
        engine = manager.get_engine(manifest)
        # dry_plan gives us the planned SQL; we can parse column types from it
        planned = engine.dry_plan(sql)
        # For a full dry-run we'd need a connector, but we can return the plan success
        # The UI primarily uses this for validation — returning empty columns means "valid"
        return Response(content="[]", media_type="application/json")
    except Exception as e:
        logger.exception("dry-run error")
        raise HTTPException(500, {"message": str(e)})


@app.post("/v1/mdl/validate/column_is_valid")
async def mdl_validate_column(request: Request):
    """Validate a column exists in the manifest.

    Returns: [{duration, name, status}]
    """
    body = await _read_json_body(request)
    manifest = body.get("manifest")
    params = body.get("parameters", {})
    model_name = params.get("modelName")
    column_name = params.get("columnName")

    if not manifest or not model_name or not column_name:
        raise HTTPException(400, "Missing manifest, modelName, or columnName")

    # Validate against manifest directly
    models = manifest.get("models", [])
    model = next((m for m in models if m.get("name") == model_name), None)
    if not model:
        return [{"duration": "0ms", "name": "column_is_valid", "status": "FAIL"}]

    columns = model.get("columns", [])
    col = next((c for c in columns if c.get("name") == column_name), None)
    if not col:
        return [{"duration": "0ms", "name": "column_is_valid", "status": "FAIL"}]

    return [{"duration": "0ms", "name": "column_is_valid", "status": "PASS"}]


@app.patch("/v1/config")
async def patch_config(request: Request):
    """Accept config patches (no-op in bridge — config is handled by profiles)."""
    return {"status": "ok"}


# ── DuckDB-specific endpoints ─────────────────────────────────────────────

@app.put("/v1/data-source/duckdb/settings/init-sql")
async def duckdb_init_sql(request: Request):
    """Accept DuckDB init SQL (stored for later use)."""
    body = await request.body()
    sql = body.decode("utf-8")
    manager.set_duckdb_init_sql(sql)
    return {"status": "ok"}


@app.put("/v1/data-source/duckdb/settings/session-sql")
async def duckdb_session_sql(request: Request):
    """Accept DuckDB session properties."""
    body = await request.body()
    manager.set_duckdb_session_sql(body.decode("utf-8"))
    return {"status": "ok"}


@app.post("/v1/data-source/duckdb/query")
async def duckdb_query(request: Request):
    """Execute a raw SQL query against DuckDB.

    Used during onboarding to list tables via INFORMATION_SCHEMA.
    """
    body = await request.body()
    sql = body.decode("utf-8")

    try:
        import duckdb  # noqa: PLC0415

        conn = manager.get_duckdb_connection()
        result = conn.execute(sql)
        columns_meta = result.description
        rows = result.fetchall()

        columns = [{"name": col[0], "type": col[1]} for col in columns_meta]
        data = [list(row) for row in rows]

        return {"columns": columns, "data": data}
    except Exception as e:
        logger.exception("duckdb query error")
        raise HTTPException(500, {"message": str(e)})


# ═══════════════════════════════════════════════════════════════════════════
# Ibis Server API (consumed by ibisAdaptor.ts)
# ═══════════════════════════════════════════════════════════════════════════

def _introspect_tables(ds, connector, conn_info) -> list:
    """Introspect tables using standard information_schema queries, mapped by data source type."""
    from wren.model.data_source import DataSource  # noqa: PLC0415

    catalog = None
    schema = None

    if ds == DataSource.trino:
        catalog = getattr(conn_info, "catalog", None)
        schema = getattr(conn_info, "trino_schema", None)
    elif ds == DataSource.postgres:
        catalog = getattr(conn_info, "database", None)
        schema = getattr(conn_info, "schema", "public")
    elif ds == DataSource.mysql:
        catalog = getattr(conn_info, "database", None)
    elif ds == DataSource.clickhouse:
        catalog = getattr(conn_info, "database", None)
    elif ds == DataSource.athena:
        catalog = getattr(conn_info, "database", None)
        schema = getattr(conn_info, "schema", None)

    # Resolve active catalog/schema via query if not specified
    if not catalog or (ds == DataSource.trino and not schema):
        try:
            if ds == DataSource.trino:
                res = connector.query("SELECT current_catalog, current_schema")
                catalog = res.column(0)[0].as_py()
                schema = res.column(1)[0].as_py()
            elif ds == DataSource.postgres:
                res = connector.query("SELECT current_database(), current_schema()")
                catalog = res.column(0)[0].as_py()
                schema = res.column(1)[0].as_py()
            elif ds == DataSource.mysql:
                res = connector.query("SELECT database()")
                catalog = res.column(0)[0].as_py()
        except Exception:
            pass

    sql = "SELECT table_name, column_name, data_type, is_nullable FROM information_schema.columns"
    filters = []

    if ds == DataSource.trino:
        if catalog:
            filters.append(f"table_catalog = '{catalog}'")
        if schema:
            filters.append(f"table_schema = '{schema}'")
    elif ds == DataSource.postgres:
        if catalog:
            filters.append(f"table_catalog = '{catalog}'")
        if schema:
            filters.append(f"table_schema = '{schema}'")
    elif ds == DataSource.mysql:
        if catalog:
            filters.append(f"table_schema = '{catalog}'")
    elif ds == DataSource.clickhouse:
        if catalog:
            filters.append(f"database = '{catalog}'")
    else:
        if schema:
            filters.append(f"table_schema = '{schema}'")
        elif catalog:
            filters.append(f"table_schema = '{catalog}'")

    if filters:
        sql += " WHERE " + " AND ".join(filters)
    sql += " ORDER BY table_name, ordinal_position"

    try:
        table = connector.query(sql)
    except Exception as e:
        logger.warning(f"Failed to query information_schema: {e}. Trying fallback SHOW TABLES.")
        try:
            show_table = connector.query("SHOW TABLES")
            tables_list = []
            for batch in show_table.to_batches():
                for row_idx in range(batch.num_rows):
                    name = batch.column(0)[row_idx].as_py()
                    tables_list.append({
                        "name": name,
                        "columns": [],
                        "properties": {
                            "catalog": catalog,
                            "schema": schema,
                            "table": name
                        }
                    })
            return tables_list
        except Exception:
            raise e

    tables_map = {}
    t_names = table.column(0).to_pylist()
    c_names = table.column(1).to_pylist()
    d_types = table.column(2).to_pylist()
    is_nulls = table.column(3).to_pylist()

    for i in range(len(t_names)):
        t_name = t_names[i]
        c_name = c_names[i]
        d_type = d_types[i]
        is_null = is_nulls[i]

        if t_name not in tables_map:
            tables_map[t_name] = {
                "name": t_name,
                "columns": [],
                "properties": {
                    "catalog": catalog,
                    "schema": schema,
                    "table": t_name
                }
            }

        tables_map[t_name]["columns"].append({
            "name": c_name,
            "type": str(d_type).upper(),
            "notNull": str(is_null).upper() == "NO"
        })

    return list(tables_map.values())


@app.post("/v2/connector/{data_source}/metadata/tables")
@app.post("/v3/connector/{data_source}/metadata/tables")
async def ibis_get_tables(data_source: str, request: Request):
    """List tables from a data source.

    Body: {connectionInfo: {...}}
    Returns: [{name, columns: [{name, type, notNull, ...}], properties: {...}}, ...]
    """
    body = await _read_json_body(request)
    connection_info = _clean_connection_info(data_source, body.get("connectionInfo", {}))

    try:
        from wren.connector.factory import get_connector  # noqa: PLC0415
        from wren.model.data_source import DataSource  # noqa: PLC0415

        ds = DataSource(data_source.lower())
        conn_info = ds.get_connection_info(connection_info)
        connector = get_connector(ds, conn_info)

        try:
            if hasattr(connector, "list_tables"):
                tables = connector.list_tables()
            else:
                tables = _introspect_tables(ds, connector, conn_info)
        finally:
            connector.close()

        return tables
    except Exception as e:
        logger.exception(f"get tables error for {data_source}")
        raise HTTPException(500, {"message": str(e)})


@app.post("/v2/connector/{data_source}/metadata/constraints")
@app.post("/v3/connector/{data_source}/metadata/constraints")
async def ibis_get_constraints(data_source: str, request: Request):
    """Get table constraints (foreign keys, etc).

    Many connectors don't support this — return empty list.
    """
    return []


@app.post("/v2/connector/{data_source}/metadata/version")
async def ibis_get_version(data_source: str, request: Request):
    """Get data source version string."""
    return "unknown"


@app.post("/v2/connector/{data_source}/query")
@app.post("/v3/connector/{data_source}/query")
async def ibis_query(data_source: str, request: Request):
    """Execute SQL through the Wren semantic layer against a data source.

    Body: {sql, connectionInfo, manifestStr (base64)}
    Returns: {columns: [...], data: [...], dtypes: {...}}
    """
    body = await _read_json_body(request)
    sql = body.get("sql")
    manifest_b64 = body.get("manifestStr")
    connection_info = _clean_connection_info(data_source, body.get("connectionInfo", {}))
    limit = request.query_params.get("limit", 500)
    dry_run = request.query_params.get("dryRun", "false").lower() == "true"

    if not sql:
        raise HTTPException(400, "Missing 'sql'")

    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 500

    try:
        from wren.engine import WrenEngine  # noqa: PLC0415
        from wren.model.data_source import DataSource  # noqa: PLC0415

        ds = DataSource(data_source.lower())

        # Decode manifest if provided
        if manifest_b64:
            manifest_str = manifest_b64
        else:
            manifest_str = None

        if manifest_str:
            conn_info = connection_info
            if not conn_info and ds == DataSource.duckdb:
                conn_info = {"format": "csv", "url": "."}
            with WrenEngine(
                manifest_str=manifest_str,
                data_source=ds,
                connection_info=conn_info,
            ) as engine:
                if dry_run:
                    engine.dry_run(sql)
                    return Response(status_code=204)

                result = engine.query(sql, limit=limit)
                return _arrow_to_ibis_response(result)
        else:
            # No manifest — direct connector query
            from wren.connector.factory import get_connector  # noqa: PLC0415

            conn_info = ds.get_connection_info(connection_info)
            connector = get_connector(ds, conn_info)
            try:
                result = connector.query(sql, limit)
                return _arrow_to_ibis_response(result)
            finally:
                connector.close()

    except Exception as e:
        logger.exception(f"query error for {data_source}")
        raise HTTPException(500, {"message": str(e)})


@app.post("/v2/connector/{data_source}/dry-plan")
@app.post("/v3/connector/{data_source}/dry-plan")
async def ibis_dry_plan(data_source: str, request: Request):
    """Dry-plan SQL through MDL — returns native SQL.

    Body: {sql, manifestStr (base64)}
    """
    body = await _read_json_body(request)
    sql = body.get("sql")
    manifest_b64 = body.get("manifestStr")

    if not sql or not manifest_b64:
        raise HTTPException(400, "Missing 'sql' or 'manifestStr'")

    try:
        from wren.engine import WrenEngine  # noqa: PLC0415
        from wren.model.data_source import DataSource  # noqa: PLC0415

        ds = DataSource(data_source.lower())
        conn_info = {"format": "csv", "url": "."} if ds == DataSource.duckdb else {}
        with WrenEngine(
            manifest_str=manifest_b64,
            data_source=ds,
            connection_info=conn_info,
        ) as engine:
            planned = engine.dry_plan(sql)
            return Response(content=planned, media_type="text/plain")
    except Exception as e:
        logger.exception(f"dry-plan error for {data_source}")
        raise HTTPException(500, {"message": str(e)})


@app.post("/v2/connector/{data_source}/validate/{rule}")
@app.post("/v3/connector/{data_source}/validate/{rule}")
async def ibis_validate(data_source: str, rule: str, request: Request):
    """Validate a rule against the data source.

    Body: {connectionInfo, manifestStr, parameters}
    """
    body = await _read_json_body(request)
    connection_info = _clean_connection_info(data_source, body.get("connectionInfo", {}))
    manifest_b64 = body.get("manifestStr")
    parameters = body.get("parameters", {})

    try:
        from wren.engine import WrenEngine  # noqa: PLC0415
        from wren.model.data_source import DataSource  # noqa: PLC0415

        ds = DataSource(data_source.lower())
        conn_info = connection_info
        if not conn_info and ds == DataSource.duckdb:
            conn_info = {"format": "csv", "url": "."}
        with WrenEngine(
            manifest_str=manifest_b64 or "",
            data_source=ds,
            connection_info=conn_info,
        ) as engine:
            model_name = parameters.get("modelName", "")
            column_name = parameters.get("columnName", "")
            # Try a simple dry-plan to validate
            test_sql = f'SELECT "{column_name}" FROM "{model_name}" LIMIT 1'
            engine.dry_plan(test_sql)
            return Response(status_code=204)
    except Exception as e:
        raise HTTPException(422, {"message": str(e)})


@app.post("/v2/connector/{data_source}/model-substitute")
@app.post("/v3/connector/{data_source}/model-substitute")
async def ibis_model_substitute(data_source: str, request: Request):
    """Model substitution — translate dialect SQL to Wren SQL.

    This is a complex feature. For now, pass-through the SQL.
    """
    body = await _read_json_body(request)
    sql = body.get("sql", "")
    return Response(content=sql, media_type="text/plain")


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _clean_connection_info(data_source: str, connection_info: dict) -> dict:
    """Clean connection info, particularly stripping http:// or https:// from Trino host."""
    if not connection_info:
        return connection_info
    cleaned = dict(connection_info)
    if data_source.lower() == "trino" and "host" in cleaned:
        host = cleaned["host"]
        if isinstance(host, str):
            if host.startswith("https://"):
                host = host[8:]
                if "kwargs" not in cleaned or cleaned["kwargs"] is None:
                    cleaned["kwargs"] = {}
                cleaned["kwargs"]["http_scheme"] = "https"
            elif host.startswith("http://"):
                host = host[7:]
                if "kwargs" not in cleaned or cleaned["kwargs"] is None:
                    cleaned["kwargs"] = {}
                cleaned["kwargs"]["http_scheme"] = "http"
            
            # Map host.docker.internal to localhost since the bridge runs on host
            if host == "host.docker.internal":
                host = "localhost"
            
            cleaned["host"] = host
    return cleaned


async def _read_json_body(request: Request) -> dict:
    """Read JSON body from request, handling both GET-with-body and POST."""
    raw = await request.body()
    if not raw:
        return {}
    try:
        return orjson.loads(raw)
    except Exception:
        return {}


def _arrow_to_engine_response(table) -> dict:
    """Convert a PyArrow table to the legacy EngineQueryResponse format.

    Format: {columns: [{name, type}], data: [[val, val, ...], ...]}
    """
    schema = table.schema
    columns = [{"name": field.name, "type": str(field.type)} for field in schema]
    # Convert to row-oriented (list of lists)
    data = []
    for batch in table.to_batches():
        for row_idx in range(batch.num_rows):
            row = []
            for col_idx in range(batch.num_columns):
                val = batch.column(col_idx)[row_idx].as_py()
                row.append(val)
            data.append(row)
    return {"columns": columns, "data": data}


def _arrow_to_ibis_response(table) -> dict:
    """Convert a PyArrow table to the legacy IbisQueryResponse format.

    Format: {columns: [name, ...], data: [[val, ...], ...], dtypes: {name: type}}
    """
    schema = table.schema
    columns = [field.name for field in schema]
    dtypes = {field.name: str(field.type) for field in schema}
    data = []
    for batch in table.to_batches():
        for row_idx in range(batch.num_rows):
            row = []
            for col_idx in range(batch.num_columns):
                val = batch.column(col_idx)[row_idx].as_py()
                row.append(val)
            data.append(row)
    return {"columns": columns, "data": data, "dtypes": dtypes}
