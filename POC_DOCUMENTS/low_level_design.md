# Low-Level Design Document

**Project:** Semantic Analytics Platform  
**Version:** 1.0  
**Date:** May 2026  

---

## Table of Contents

1. [Database Schema Design](#1-database-schema-design)
2. [Service Architecture](#2-service-architecture)
3. [RBAC Engine Design](#3-rbac-engine-design)
4. [Wren MDL Management](#4-wren-mdl-management)
5. [Trino Catalog Management](#5-trino-catalog-management)
6. [Qdrant Vector Store Design](#6-qdrant-vector-store-design)
7. [API Contract Specifications](#7-api-contract-specifications)
8. [Error Handling](#8-error-handling)
9. [Configuration Management](#9-configuration-management)

---

## 1. Database Schema Design

### 1A. Entity Relationship Diagram

```mermaid
erDiagram
    TENANTS {
        varchar tenant_id PK
        varchar tenant_name
        varchar org_id
        boolean is_active
        timestamp created_at
    }

    USERS {
        uuid user_id PK
        varchar email UK
        varchar password_hash
        varchar name
        varchar default_tenant_id FK
        timestamp created_at
    }

    USER_TENANT_MEMBERSHIP {
        uuid user_id FK
        varchar tenant_id FK
        varchar role
        timestamp joined_at
    }

    DATASOURCES {
        uuid datasource_id PK
        varchar tenant_id FK
        varchar source_type
        varchar display_name
        jsonb connection_config
        varchar trino_catalog
        boolean is_active
        timestamp created_at
    }

    MDL_MODELS {
        uuid mdl_id PK
        varchar tenant_id FK
        uuid datasource_id FK
        text model_yaml
        integer version
        boolean is_active
        timestamp created_at
        timestamp updated_at
    }

    TABLE_PERMISSIONS {
        serial id PK
        uuid user_id FK
        varchar tenant_id FK
        uuid datasource_id FK
        varchar table_name
        varchar access
        uuid granted_by FK
        timestamp granted_at
    }

    QUERY_AUDIT_LOG {
        serial id PK
        uuid user_id
        varchar tenant_id
        text nl_query
        text generated_sql
        text[] tables_accessed
        integer row_count
        integer execution_ms
        varchar status
        timestamp created_at
    }

    PERMISSION_AUDIT_LOG {
        serial id PK
        varchar action
        uuid user_id
        varchar tenant_id
        varchar table_name
        uuid performed_by
        timestamp performed_at
    }

    TENANTS ||--o{ USER_TENANT_MEMBERSHIP : has
    USERS ||--o{ USER_TENANT_MEMBERSHIP : belongs_to
    TENANTS ||--o{ DATASOURCES : owns
    TENANTS ||--o{ MDL_MODELS : owns
    DATASOURCES ||--o{ MDL_MODELS : defines
    USERS ||--o{ TABLE_PERMISSIONS : has
    TENANTS ||--o{ TABLE_PERMISSIONS : scopes
    DATASOURCES ||--o{ TABLE_PERMISSIONS : scopes
```

### 1B. Complete DDL

```sql
-- ============================================
-- Platform Metadata Database Schema
-- ============================================

-- Tenants (Business Units)
CREATE TABLE tenants (
    tenant_id     VARCHAR(100) PRIMARY KEY,
    tenant_name   VARCHAR(255) NOT NULL,
    org_id        VARCHAR(100) NOT NULL DEFAULT 'default_bank',
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMP DEFAULT NOW(),
    updated_at    TIMESTAMP DEFAULT NOW()
);

-- Users
CREATE TABLE users (
    user_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    name            VARCHAR(255) NOT NULL,
    default_tenant_id VARCHAR(100) REFERENCES tenants(tenant_id),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- User-Tenant Membership
CREATE TABLE user_tenant_membership (
    user_id     UUID REFERENCES users(user_id) ON DELETE CASCADE,
    tenant_id   VARCHAR(100) REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    role        VARCHAR(50) NOT NULL DEFAULT 'viewer',
    joined_at   TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id, tenant_id),
    CONSTRAINT valid_role CHECK (role IN ('super_admin', 'admin', 'analyst', 'viewer'))
);

-- Data Sources
CREATE TABLE datasources (
    datasource_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         VARCHAR(100) REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    source_type       VARCHAR(50) NOT NULL,
    display_name      VARCHAR(255) NOT NULL,
    connection_config JSONB NOT NULL,
    trino_catalog     VARCHAR(100) UNIQUE NOT NULL,
    is_active         BOOLEAN DEFAULT TRUE,
    created_by        UUID REFERENCES users(user_id),
    created_at        TIMESTAMP DEFAULT NOW(),
    updated_at        TIMESTAMP DEFAULT NOW(),
    CONSTRAINT valid_source_type CHECK (
        source_type IN ('postgresql', 'mysql', 'sqlserver', 'bigquery', 'iceberg')
    )
);

-- Wren MDL Models
CREATE TABLE mdl_models (
    mdl_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       VARCHAR(100) REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    datasource_id   UUID REFERENCES datasources(datasource_id) ON DELETE CASCADE,
    model_name      VARCHAR(255) NOT NULL,
    model_yaml      TEXT NOT NULL,
    version         INTEGER DEFAULT 1,
    is_active       BOOLEAN DEFAULT TRUE,
    created_by      UUID REFERENCES users(user_id),
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (tenant_id, datasource_id, model_name, version)
);

-- Table-Level Permissions
CREATE TABLE table_permissions (
    id              SERIAL PRIMARY KEY,
    user_id         UUID REFERENCES users(user_id) ON DELETE CASCADE,
    tenant_id       VARCHAR(100) REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    datasource_id   UUID REFERENCES datasources(datasource_id) ON DELETE CASCADE,
    table_name      VARCHAR(255) NOT NULL,
    access          VARCHAR(10) NOT NULL DEFAULT 'READ',
    granted_by      UUID REFERENCES users(user_id),
    granted_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (user_id, tenant_id, datasource_id, table_name),
    CONSTRAINT valid_access CHECK (access IN ('READ', 'DENY'))
);

-- Query Audit Log
CREATE TABLE query_audit_log (
    id                SERIAL PRIMARY KEY,
    user_id           UUID NOT NULL,
    tenant_id         VARCHAR(100) NOT NULL,
    nl_query          TEXT NOT NULL,
    generated_sql     TEXT,
    tables_accessed   TEXT[],
    datasources_used  TEXT[],
    row_count         INTEGER,
    execution_ms      INTEGER,
    status            VARCHAR(20) NOT NULL,
    error_message     TEXT,
    created_at        TIMESTAMP DEFAULT NOW(),
    CONSTRAINT valid_status CHECK (status IN ('success', 'error', 'denied', 'timeout'))
);

-- Permission Audit Log
CREATE TABLE permission_audit_log (
    id              SERIAL PRIMARY KEY,
    action          VARCHAR(20) NOT NULL,
    user_id         UUID NOT NULL,
    tenant_id       VARCHAR(100) NOT NULL,
    datasource_id   UUID,
    table_name      VARCHAR(255) NOT NULL,
    performed_by    UUID NOT NULL,
    performed_at    TIMESTAMP DEFAULT NOW(),
    CONSTRAINT valid_action CHECK (action IN ('GRANT', 'REVOKE'))
);

-- Indexes
CREATE INDEX idx_membership_tenant ON user_tenant_membership(tenant_id);
CREATE INDEX idx_datasources_tenant ON datasources(tenant_id);
CREATE INDEX idx_mdl_tenant ON mdl_models(tenant_id, is_active);
CREATE INDEX idx_permissions_user_tenant ON table_permissions(user_id, tenant_id);
CREATE INDEX idx_audit_tenant_time ON query_audit_log(tenant_id, created_at DESC);
CREATE INDEX idx_audit_user_time ON query_audit_log(user_id, created_at DESC);
CREATE INDEX idx_perm_audit_tenant ON permission_audit_log(tenant_id, performed_at DESC);
```

---

## 2. Service Architecture

### 2A. Module Structure

```
app/
├── main.py                     # FastAPI app entry point
├── config.py                   # Settings and environment config
├── dependencies.py             # Dependency injection
│
├── models/                     # SQLAlchemy / Pydantic models
│   ├── tenant.py               # Tenant, UserTenantMembership
│   ├── user.py                 # User
│   ├── datasource.py           # DataSource
│   ├── mdl.py                  # MDLModel
│   ├── rbac.py                 # TablePermission, PermissionAuditLog
│   └── audit.py                # QueryAuditLog
│
├── schemas/                    # Pydantic request/response schemas
│   ├── auth.py                 # LoginRequest, TokenResponse
│   ├── tenant.py               # TenantCreate, TenantResponse
│   ├── datasource.py           # DataSourceCreate, SchemaDiscovery
│   ├── query.py                # AskRequest, AskResponse
│   └── rbac.py                 # PermissionGrant, PermissionMatrix
│
├── routers/                    # API route handlers
│   ├── auth.py                 # /api/auth/*
│   ├── tenants.py              # /api/tenants/*
│   ├── datasources.py          # /api/datasources/*
│   ├── query.py                # /api/ask
│   ├── rbac.py                 # /api/rbac/*
│   └── audit.py                # /api/audit/*
│
├── services/                   # Business logic layer
│   ├── auth_service.py         # JWT creation, validation
│   ├── tenant_service.py       # Tenant CRUD operations
│   ├── datasource_service.py   # Data source onboarding
│   ├── rbac_service.py         # Permission management
│   ├── mdl_service.py          # MDL storage, filtering, compilation
│   ├── query_service.py        # Main query orchestration
│   ├── trino_service.py        # Trino catalog management
│   ├── qdrant_service.py       # Vector similarity operations
│   └── audit_service.py        # Query and permission audit logging
│
├── middleware/                  # Request middleware
│   ├── auth_middleware.py      # JWT validation
│   ├── tenant_middleware.py    # Tenant context injection
│   └── rate_limiter.py         # Per-tenant rate limiting
│
├── agents/                     # AI agent configuration
│   ├── gemini_agent.py         # Pydantic AI agent with tools
│   └── tools.py                # wren_query, execute_sql tools
│
└── utils/
    ├── encryption.py           # KMS-based credential encryption
    ├── logging.py              # Structured logging
    └── errors.py               # Custom exception classes
```

### 2B. Service Interaction Diagram

```mermaid
graph TD
    subgraph Routers ["API Routers"]
        R_Auth["auth.py"]
        R_Query["query.py"]
        R_DS["datasources.py"]
        R_RBAC["rbac.py"]
    end

    subgraph Middleware ["Middleware Chain"]
        MW_Auth["AuthMiddleware"]
        MW_Tenant["TenantMiddleware"]
        MW_Rate["RateLimiter"]
    end

    subgraph Services ["Business Logic Services"]
        S_Auth["AuthService"]
        S_Query["QueryService"]
        S_DS["DataSourceService"]
        S_RBAC["RBACService"]
        S_MDL["MDLService"]
        S_Trino["TrinoService"]
        S_Qdrant["QdrantService"]
        S_Audit["AuditService"]
    end

    subgraph External ["External Systems"]
        DB[("Metadata DB")]
        Trino["Trino Cluster"]
        Wren["Wren Engine"]
        Qdrant["Qdrant"]
        Vertex["Vertex AI"]
    end

    MW_Auth --> MW_Tenant --> MW_Rate

    R_Auth --> S_Auth
    R_Query --> S_Query
    R_DS --> S_DS
    R_RBAC --> S_RBAC

    S_Query --> S_RBAC
    S_Query --> S_MDL
    S_Query --> S_Qdrant
    S_Query --> S_Audit
    S_DS --> S_Trino
    S_DS --> S_MDL

    S_Auth --> DB
    S_RBAC --> DB
    S_MDL --> DB
    S_MDL --> Wren
    S_Trino --> Trino
    S_Qdrant --> Qdrant
    S_Query --> Vertex
    S_Audit --> DB
```

### 2C. Request Lifecycle

```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant MW as Middleware Stack
    participant Router as Router
    participant Service as Service Layer
    participant DB as Database
    participant External as External Services

    Client->>MW: HTTP Request

    rect rgb(60, 40, 40)
        Note over MW: Middleware Chain
        MW->>MW: 1. AuthMiddleware - validate JWT
        MW->>MW: 2. TenantMiddleware - resolve tenant context
        MW->>MW: 3. RateLimiter - check tenant quota
    end

    MW->>Router: Forward with TenantContext
    Router->>Router: Validate request body via Pydantic
    Router->>Service: Call service method

    Service->>DB: Read/write data
    Service->>External: Call Trino/Wren/Qdrant/Vertex

    External-->>Service: Response
    Service-->>Router: Result
    Router-->>Client: HTTP Response
```

---

## 3. RBAC Engine Design

### 3A. RBACService Class

```python
class RBACService:
    """
    Table-level RBAC engine.
    Resolves which tables a user can access within a tenant,
    and filters MDL models accordingly.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._cache: dict[str, list[str]] = {}  # user_tenant -> tables

    async def get_allowed_tables(
        self, user_id: UUID, tenant_id: str
    ) -> list[AllowedTable]:
        """
        Returns list of tables this user can READ in this tenant.
        Checks cache first, then database.
        """
        cache_key = f"{user_id}:{tenant_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        permissions = await self.db.execute(
            select(TablePermission)
            .where(TablePermission.user_id == user_id)
            .where(TablePermission.tenant_id == tenant_id)
            .where(TablePermission.access == 'READ')
        )
        allowed = [
            AllowedTable(
                datasource_id=p.datasource_id,
                table_name=p.table_name
            )
            for p in permissions.scalars()
        ]
        self._cache[cache_key] = allowed
        return allowed

    async def filter_mdl(
        self, full_mdl: dict, allowed_tables: list[AllowedTable]
    ) -> dict:
        """
        Removes models from the MDL that the user is not
        authorized to access. Also removes relationships
        that reference unauthorized tables.
        """
        allowed_set = {
            (t.datasource_id, t.table_name) for t in allowed_tables
        }
        filtered_models = []
        for model in full_mdl.get("models", []):
            table_ref = model.get("table_reference", "")
            datasource_id = self._extract_datasource(table_ref)
            table_name = self._extract_table(table_ref)
            if (datasource_id, table_name) in allowed_set:
                # Also filter relationships to only allowed tables
                model = self._filter_relationships(model, allowed_set)
                filtered_models.append(model)

        return {"models": filtered_models}

    async def grant_access(
        self,
        user_id: UUID,
        tenant_id: str,
        datasource_id: UUID,
        table_name: str,
        granted_by: UUID
    ) -> TablePermission:
        """Grant READ access to a specific table."""
        permission = TablePermission(
            user_id=user_id,
            tenant_id=tenant_id,
            datasource_id=datasource_id,
            table_name=table_name,
            access='READ',
            granted_by=granted_by
        )
        self.db.add(permission)
        await self.db.commit()
        self._invalidate_cache(user_id, tenant_id)

        # Audit log
        await self._log_permission_change(
            'GRANT', user_id, tenant_id,
            datasource_id, table_name, granted_by
        )
        return permission

    async def revoke_access(
        self, user_id: UUID, tenant_id: str,
        datasource_id: UUID, table_name: str,
        performed_by: UUID
    ):
        """Revoke access to a specific table."""
        await self.db.execute(
            delete(TablePermission)
            .where(TablePermission.user_id == user_id)
            .where(TablePermission.tenant_id == tenant_id)
            .where(TablePermission.datasource_id == datasource_id)
            .where(TablePermission.table_name == table_name)
        )
        await self.db.commit()
        self._invalidate_cache(user_id, tenant_id)

        await self._log_permission_change(
            'REVOKE', user_id, tenant_id,
            datasource_id, table_name, performed_by
        )
```

### 3B. MDL Filtering Algorithm

```mermaid
graph TD
    Start["Input: Full MDL + User Permissions"] --> Load["Load allowed tables from DB"]
    Load --> Loop["For each model in MDL"]
    Loop --> Check{"Is model's table in allowed list?"}
    Check -->|Yes| FilterRel["Filter relationships to only allowed targets"]
    Check -->|No| Remove["Remove model from MDL"]
    FilterRel --> Keep["Keep model in filtered MDL"]
    Remove --> Next["Next model"]
    Keep --> Next
    Next --> Done{"More models?"}
    Done -->|Yes| Loop
    Done -->|No| Output["Output: Filtered MDL"]
    Output --> Agent["Send to Gemini Agent"]
```

### 3C. Permission Resolution Rules

| Rule | Behavior |
|------|----------|
| No entry in `table_permissions` | **DENY** — default deny, explicit grant required |
| `access = 'READ'` | User can query this table |
| `access = 'DENY'` | Explicit deny — overrides any other grant |
| User role = `admin` in tenant | Can see ALL tables in their tenant — bypass RBAC |
| User role = `super_admin` | Can see all tables across ALL tenants |
| Cache invalidation | On any `GRANT` or `REVOKE`, clear user's permission cache |

---

## 4. Wren MDL Management

### 4A. MDL Storage and Versioning

Each tenant's semantic models are versioned. Only the latest active version is used for query compilation.

```mermaid
graph LR
    subgraph MDL_Store ["MDL Storage per Tenant"]
        V1["Version 1 - Initial Draft"]
        V2["Version 2 - Added Relationships"]
        V3["Version 3 - Current Active"]
    end

    V1 -->|superseded| V2
    V2 -->|superseded| V3
    V3 --> Compiler["Wren Compiler"]
```

### 4B. MDL Lifecycle

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Tenant Admin
    participant API as MDL Service
    participant DB as Metadata DB
    participant Wren as Wren Engine

    Admin->>API: Update MDL model for datasource X
    API->>DB: Load current active MDL version
    DB-->>API: Version 2

    API->>Wren: Validate new MDL via dry-run compilation
    alt Compilation Success
        Wren-->>API: Validation passed
        API->>DB: Save new MDL as Version 3, set is_active=true
        API->>DB: Set Version 2 is_active=false
        API-->>Admin: MDL updated successfully
    else Compilation Error
        Wren-->>API: Validation failed with errors
        API-->>Admin: Error - invalid MDL with details
    end
```

### 4C. MDL Model Structure

```python
@dataclass
class MDLModel:
    """Represents a single semantic model in the MDL."""
    name: str                      # e.g., "orders"
    table_reference: str           # e.g., "core_banking.public.orders"
    columns: list[MDLColumn]
    calculated_fields: list[MDLCalculatedField]
    relationships: list[MDLRelationship]

@dataclass
class MDLColumn:
    name: str
    type: str                      # INTEGER, VARCHAR, DECIMAL, etc.
    description: str               # Business-friendly description

@dataclass
class MDLCalculatedField:
    name: str
    expression: str                # SQL expression, e.g., "SUM(total_amount)"
    description: str               # What this field represents

@dataclass
class MDLRelationship:
    name: str
    target_model: str              # Name of related model
    join_type: str                 # MANY_TO_ONE, ONE_TO_MANY, etc.
    condition: str                 # Join condition SQL
```

---

## 5. Trino Catalog Management

### 5A. Dynamic Catalog Registration

When a data source is onboarded, a Trino catalog is created dynamically.

```mermaid
sequenceDiagram
    autonumber
    participant DS as DataSourceService
    participant Trino as TrinoService
    participant Coord as Trino Coordinator

    DS->>Trino: register_catalog with config
    Trino->>Trino: Generate catalog properties file
    Trino->>Coord: POST catalog properties via REST API
    Coord->>Coord: Load connector, introspect schema
    Coord-->>Trino: Catalog registered
    Trino-->>DS: Return discovered tables and columns
```

### 5B. Connector Configurations

**PostgreSQL Connector**
```properties
# catalog: core_banking
connector.name=postgresql
connection-url=jdbc:postgresql://10.0.1.5:5432/bank_a_retail
connection-user=${SECRET:pg_user}
connection-password=${SECRET:pg_password}
```

**BigQuery Connector**
```properties
# catalog: analytics_warehouse
connector.name=bigquery
bigquery.project-id=my-gcp-project
bigquery.credentials-file=/secrets/bq-service-account.json
bigquery.case-insensitive-name-matching=true
```

**Iceberg Connector**
```properties
# catalog: data_lake
connector.name=iceberg
iceberg.catalog.type=rest
iceberg.rest-catalog.uri=http://iceberg-rest:8181
iceberg.file-format=PARQUET
hive.gcs.json-key-file-path=/secrets/gcs-service-account.json
```

### 5C. TrinoService Class

```python
class TrinoService:
    """Manages Trino catalogs and query execution."""

    def __init__(self, trino_host: str, trino_port: int):
        self.trino_url = f"http://{trino_host}:{trino_port}"

    async def register_catalog(
        self, catalog_name: str, source_type: str,
        connection_config: dict
    ) -> list[DiscoveredTable]:
        """
        Register a new catalog in Trino and return discovered schema.
        """
        properties = self._build_properties(source_type, connection_config)
        # Write properties file or use Trino REST API
        await self._create_catalog(catalog_name, properties)
        # Introspect schema
        tables = await self.discover_schema(catalog_name)
        return tables

    async def discover_schema(
        self, catalog_name: str
    ) -> list[DiscoveredTable]:
        """
        Query information_schema to discover all tables and columns.
        """
        query = f"""
            SELECT table_schema, table_name, column_name, data_type
            FROM {catalog_name}.information_schema.columns
            ORDER BY table_schema, table_name, ordinal_position
        """
        results = await self.execute_query(query)
        return self._parse_schema(results)

    async def execute_query(self, sql: str) -> PyArrowTable:
        """Execute SQL via Trino and return PyArrow table."""
        conn = trino.dbapi.connect(
            host=self.trino_url,
            port=443,
            user="trino-service",
            catalog="system"
        )
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        return self._to_pyarrow(rows, columns)
```

---

## 6. Qdrant Vector Store Design

### 6A. Collection Strategy

Each tenant gets a dedicated Qdrant collection. Query-SQL pairs are embedded and cached for similarity-based retrieval.

```mermaid
graph TD
    subgraph Qdrant_Cluster ["Qdrant Cluster"]
        C1["Collection: queries_retail_banking"]
        C2["Collection: queries_corporate_banking"]
        C3["Collection: queries_treasury"]
        C4["Collection: queries_risk_management"]
    end

    subgraph Point_Structure ["Point Structure"]
        Vec["Vector: 768-dim embedding of NL query"]
        Pay["Payload: nl_query, generated_sql, tables_used, timestamp"]
    end
```

### 6B. QdrantService Class

```python
class QdrantService:
    """Per-tenant vector similarity search for query caching."""

    EMBEDDING_DIM = 768  # text-embedding-004 dimension

    def __init__(self, qdrant_url: str):
        self.client = QdrantClient(url=qdrant_url)

    def _collection_name(self, tenant_id: str) -> str:
        return f"queries_{tenant_id}"

    async def ensure_collection(self, tenant_id: str):
        """Create collection for tenant if it doesn't exist."""
        name = self._collection_name(tenant_id)
        if not self.client.collection_exists(name):
            self.client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(
                    size=self.EMBEDDING_DIM,
                    distance=Distance.COSINE
                )
            )

    async def search_similar(
        self, tenant_id: str, query_embedding: list[float],
        top_k: int = 3
    ) -> list[CachedQuery]:
        """Find similar past queries for few-shot examples."""
        results = self.client.search(
            collection_name=self._collection_name(tenant_id),
            query_vector=query_embedding,
            limit=top_k,
            score_threshold=0.75
        )
        return [
            CachedQuery(
                nl_query=r.payload["nl_query"],
                generated_sql=r.payload["generated_sql"],
                similarity=r.score
            )
            for r in results
        ]

    async def cache_query(
        self, tenant_id: str, nl_query: str,
        generated_sql: str, embedding: list[float],
        tables_used: list[str]
    ):
        """Cache a successful query-SQL pair."""
        self.client.upsert(
            collection_name=self._collection_name(tenant_id),
            points=[PointStruct(
                id=str(uuid4()),
                vector=embedding,
                payload={
                    "nl_query": nl_query,
                    "generated_sql": generated_sql,
                    "tables_used": tables_used,
                    "cached_at": datetime.utcnow().isoformat()
                }
            )]
        )
```

---

## 7. API Contract Specifications

### 7A. Authentication

**POST /api/auth/login**

Request:
```json
{
    "email": "priya@bank.com",
    "password": "secure_password"
}
```

Response:
```json
{
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "expires_in": 3600,
    "user": {
        "user_id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "Priya Sharma",
        "email": "priya@bank.com",
        "tenants": [
            {
                "tenant_id": "retail_banking",
                "tenant_name": "Retail Banking",
                "role": "analyst"
            },
            {
                "tenant_id": "corporate_banking",
                "tenant_name": "Corporate Banking",
                "role": "viewer"
            }
        ],
        "default_tenant_id": "retail_banking"
    }
}
```

JWT Payload:
```json
{
    "sub": "550e8400-e29b-41d4-a716-446655440000",
    "email": "priya@bank.com",
    "tenant_id": "retail_banking",
    "role": "analyst",
    "exp": 1717200000
}
```

### 7B. Query

**POST /api/ask**

Request:
```json
{
    "question": "What is the total loan default rate this quarter?",
    "tenant_id": "retail_banking"
}
```

Response:
```json
{
    "answer": "The total loan default rate this quarter is **2.3%**, based on 1,247 defaulted loans out of 54,217 total active loans.",
    "generated_sql": "SELECT COUNT(CASE WHEN status = 'default' THEN 1 END)::FLOAT / COUNT(*) * 100 AS default_rate FROM core_banking.public.loans WHERE loan_date >= DATE_TRUNC('quarter', CURRENT_DATE)",
    "tables_accessed": ["loans"],
    "data": [
        {"default_rate": 2.3}
    ],
    "execution_time_ms": 342,
    "query_id": "audit-log-uuid"
}
```

### 7C. Data Source Onboarding

**POST /api/datasources**

Request:
```json
{
    "display_name": "Core Banking PostgreSQL",
    "source_type": "postgresql",
    "connection_config": {
        "host": "10.0.1.5",
        "port": 5432,
        "database": "bank_a_retail",
        "username": "readonly_user",
        "password": "encrypted_via_kms"
    }
}
```

Response:
```json
{
    "datasource_id": "ds-uuid-1234",
    "tenant_id": "retail_banking",
    "display_name": "Core Banking PostgreSQL",
    "source_type": "postgresql",
    "trino_catalog": "retail_banking_core",
    "status": "connected",
    "discovered_tables": [
        {
            "schema": "public",
            "table_name": "accounts",
            "columns": [
                {"name": "account_id", "type": "INTEGER"},
                {"name": "customer_id", "type": "INTEGER"},
                {"name": "balance", "type": "DECIMAL"},
                {"name": "account_type", "type": "VARCHAR"}
            ]
        },
        {
            "schema": "public",
            "table_name": "loans",
            "columns": [
                {"name": "loan_id", "type": "INTEGER"},
                {"name": "customer_id", "type": "INTEGER"},
                {"name": "amount", "type": "DECIMAL"},
                {"name": "status", "type": "VARCHAR"}
            ]
        }
    ]
}
```

### 7D. RBAC Permissions

**POST /api/rbac/permissions** — Grant access

Request:
```json
{
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "datasource_id": "ds-uuid-1234",
    "table_name": "loans",
    "access": "READ"
}
```

Response:
```json
{
    "id": 42,
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "tenant_id": "retail_banking",
    "datasource_id": "ds-uuid-1234",
    "table_name": "loans",
    "access": "READ",
    "granted_by": "admin-user-uuid",
    "granted_at": "2026-05-31T11:30:00Z"
}
```

**GET /api/rbac/matrix** — Permission matrix for admin

Response:
```json
{
    "tenant_id": "retail_banking",
    "datasource_id": "ds-uuid-1234",
    "matrix": [
        {
            "user_id": "priya-uuid",
            "user_name": "Priya Sharma",
            "tables": {
                "accounts": "READ",
                "loans": "READ",
                "branches": "READ",
                "employee_salary": "DENY",
                "internal_audit": "DENY"
            }
        },
        {
            "user_id": "amit-uuid",
            "user_name": "Amit Kumar",
            "tables": {
                "accounts": "READ",
                "loans": "READ",
                "branches": "READ",
                "employee_salary": "READ",
                "internal_audit": "READ"
            }
        }
    ]
}
```

---

## 8. Error Handling

### 8A. Error Response Format

All errors follow a consistent JSON structure:

```json
{
    "error": {
        "code": "RBAC_TABLE_DENIED",
        "message": "You do not have access to table 'employee_salary'",
        "details": {
            "tenant_id": "retail_banking",
            "table_name": "employee_salary"
        },
        "request_id": "req-uuid-5678"
    }
}
```

### 8B. Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `AUTH_INVALID_TOKEN` | 401 | JWT token is expired or malformed |
| `AUTH_UNAUTHORIZED` | 403 | User is not a member of the requested tenant |
| `TENANT_NOT_FOUND` | 404 | Tenant ID does not exist |
| `TENANT_INACTIVE` | 403 | Tenant has been deactivated |
| `RBAC_TABLE_DENIED` | 403 | User does not have READ access to a table |
| `RBAC_NO_TABLES` | 403 | User has no table permissions in this tenant |
| `DS_CONNECTION_FAILED` | 502 | Cannot connect to data source |
| `DS_NOT_FOUND` | 404 | Data source ID does not exist |
| `MDL_COMPILATION_ERROR` | 422 | Wren MDL failed to compile |
| `QUERY_TIMEOUT` | 504 | Trino query exceeded timeout |
| `QUERY_RATE_LIMITED` | 429 | Tenant has exceeded query rate limit |
| `LLM_ERROR` | 502 | Vertex AI Gemini returned an error |
| `WREN_ERROR` | 502 | Wren engine returned an error |

### 8C. Exception Classes

```python
class AppError(Exception):
    """Base exception for application errors."""
    def __init__(self, code: str, message: str,
                 status_code: int = 500, details: dict = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}

class AuthError(AppError):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__("AUTH_INVALID_TOKEN", message, 401)

class RBACDeniedError(AppError):
    def __init__(self, table_name: str, tenant_id: str):
        super().__init__(
            "RBAC_TABLE_DENIED",
            f"Access denied to table '{table_name}'",
            403,
            {"table_name": table_name, "tenant_id": tenant_id}
        )

class TenantNotFoundError(AppError):
    def __init__(self, tenant_id: str):
        super().__init__(
            "TENANT_NOT_FOUND",
            f"Tenant '{tenant_id}' not found",
            404,
            {"tenant_id": tenant_id}
        )

class QueryTimeoutError(AppError):
    def __init__(self, timeout_seconds: int):
        super().__init__(
            "QUERY_TIMEOUT",
            f"Query exceeded {timeout_seconds}s timeout",
            504,
            {"timeout_seconds": timeout_seconds}
        )
```

---

## 9. Configuration Management

### 9A. Environment Variables

```bash
# ============================================
# Application Config
# ============================================
APP_ENV=production                    # development | staging | production
APP_PORT=8000
APP_WORKERS=4
LOG_LEVEL=INFO

# ============================================
# Database
# ============================================
DATABASE_URL=postgresql+asyncpg://user:pass@10.0.1.5:5432/platform_metadata
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# ============================================
# Authentication
# ============================================
JWT_SECRET_KEY=secret-from-secret-manager
JWT_ALGORITHM=HS256
JWT_EXPIRY_HOURS=8

# ============================================
# Vertex AI
# ============================================
GCP_PROJECT_ID=my-gcp-project
GCP_REGION=asia-south1
VERTEX_AI_MODEL=gemini-2.5-flash
VERTEX_AI_ENDPOINT=private-endpoint-url

# ============================================
# Trino
# ============================================
TRINO_HOST=trino-coordinator.federation.svc.cluster.local
TRINO_PORT=8080
TRINO_QUERY_TIMEOUT_SECONDS=60

# ============================================
# Wren
# ============================================
WREN_HOST=wren-engine.semantic.svc.cluster.local
WREN_PORT=8080

# ============================================
# Qdrant
# ============================================
QDRANT_HOST=qdrant.vector.svc.cluster.local
QDRANT_PORT=6333

# ============================================
# Rate Limiting
# ============================================
RATE_LIMIT_DEFAULT_PER_HOUR=100
RATE_LIMIT_MAX_CONCURRENT=5

# ============================================
# Encryption
# ============================================
KMS_KEY_RING=platform-keys
KMS_KEY_NAME=datasource-credentials
```

### 9B. Config Class

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App
    app_env: str = "development"
    app_port: int = 8000
    log_level: str = "INFO"

    # Database
    database_url: str
    database_pool_size: int = 20

    # Auth
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 8

    # Vertex AI
    gcp_project_id: str
    gcp_region: str = "asia-south1"
    vertex_ai_model: str = "gemini-2.5-flash"

    # Trino
    trino_host: str
    trino_port: int = 8080
    trino_query_timeout_seconds: int = 60

    # Wren
    wren_host: str
    wren_port: int = 8080

    # Qdrant
    qdrant_host: str
    qdrant_port: int = 6333

    # Rate Limiting
    rate_limit_default_per_hour: int = 100
    rate_limit_max_concurrent: int = 5

    class Config:
        env_file = ".env"

settings = Settings()
```

---

> This LLD document should be read alongside the [Architecture Document](bank_semantic_platform_architecture.md) for the full system context. Implementation should follow the phased approach defined in the [Multi-Tenancy Roadmap](multitenancy_roadmap.md).
