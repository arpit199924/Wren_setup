# Semantic Analytics Platform — HLD (Wren Legacy v1)

**Project:** Conversational Data Query Platform for Banking (Legacy v1 Stack)  
**Version:** 1.0  
**Deployment:** Google Cloud Platform (GKE) — Private Network Isolation

---

## 1. Multi-Tenant System Architecture

The platform adapts the components from the Wren `legacy/v1` architecture to provide multi-tenant query intelligence and database access across different business units (BUs) within the bank. 

```mermaid
graph TB
    subgraph Client ["Layer 1 — Presentation"]
        UI["Wren UI Next.js Client"]
        Gateway["API Gateway / Reverse Proxy"]
    end

    subgraph Control ["Layer 2 — Control & Metadata (Tenant-Aware)"]
        Apollo["Apollo GraphQL Server (wren-ui Backend)"]
        DB[(PostgreSQL Metadata Store)]
        RBAC["Table-Level RBAC Middleware"]
    end

    subgraph Intelligence ["Layer 3 — AI Orchestration"]
        AIService["wren-ai-service (FastAPI)"]
        Qdrant["Qdrant Vector DB (Tenant-Scoped Collections)"]
        Gemini["Gemini via Vertex AI"]
    end

    subgraph Semantic ["Layer 4 — Semantic SQL & Execution"]
        Ibis["ibis-server (FastAPI/Ibis Connectors)"]
        Engine["wren-engine (Rust core)"]
    end

    subgraph Data ["Layer 5 — Target Databases"]
        Postgres[("PostgreSQL")]
        BigQuery[("Google BigQuery")]
        Iceberg[("Apache Iceberg on GCS")]
    end

    UI --> Gateway
    Gateway --> Apollo
    Apollo --> DB
    Apollo --> RBAC
    RBAC --> AIService
    AIService --> Qdrant
    AIService --> Gemini
    AIService --> Engine
    Apollo --> Ibis
    Ibis --> Engine
    Ibis --> Postgres
    Ibis --> BigQuery
    Ibis --> Iceberg
```

### Component Breakdown & Responsibilities

| Component | Technology | Multi-Tenant Responsibility |
|:---|:---|:---|
| **Wren UI Client** | Next.js, React | Exposes the web console, schema builder, dashboard, and conversation threads. Routes user session with `tenant_id` context. |
| **Apollo GraphQL Server** | Node.js, Apollo | The backend for `wren-ui`. Persists schema metadata, user preferences, and chat history. Scopes all queries and mutations by `tenant_id`. |
| **Metadata Store** | PostgreSQL (migrated from SQLite) | Central database storing project, model, column, metric, relationship, thread, and permissions tables, isolated using `tenant_id`. |
| **wren-ai-service** | FastAPI, Python | Manages AI pipelines (intent classification, SQL planning, corrections). Communicates with Qdrant and LLM, routing requests to tenant-isolated vector namespaces. |
| **Qdrant Vector DB** | Qdrant | Stores high-dimensional vector embeddings of schemas and historical queries. Isolated by utilizing tenant-specific collections. |
| **ibis-server** | FastAPI, Ibis, SQLGlot | A Python-based database execution service. Receives connection credentials and compiled MDL manifests dynamically on each request to fetch metadata or execute queries. |
| **wren-engine** | Rust, PyO3 bindings | Rust-based semantic SQL compiler (`wren-core`) that validates and compiles semantic queries into native SQL dialetcs. Runs statelessly. |

---

## 2. Multi-Tenancy Design Model

The banking environment requires strict isolation between different business units (e.g., Retail Banking, Corporate Banking, Risk, Treasury).

```mermaid
graph TD
    Bank["Bank (Organization)"]
    Bank --> BU1["Retail Banking (tenant_id: retail_banking)"]
    Bank --> BU2["Corporate Banking (tenant_id: corp_banking)"]

    subgraph Retail ["Retail Banking Sandbox"]
        MDL1["Retail MDL Manifest"]
        Coll1["Qdrant Collection: tenant_retail_schema"]
        DS1[("BigQuery: retail_warehouse")]
    end

    subgraph Corp ["Corporate Banking Sandbox"]
        MDL2["Corporate MDL Manifest"]
        Coll2["Qdrant Collection: tenant_corp_schema"]
        DS2[("Postgres: corp_loans")]
    end

    BU1 --> Retail
    BU2 --> Corp
```

### Isolation Vector Matrix

*   **User Identity & Session:** Users authenticate at the API Gateway. The resulting JWT carries the user's roles and `tenant_id` (representing their business unit).
*   **Metadata DB (PostgreSQL):** A shared-database, shared-schema architecture is used. Every table has a `tenant_id` column. Every database query executed by `wren-ui`'s backend includes an explicit filter: `WHERE tenant_id = <current_tenant_id>`.
*   **Semantic Model (MDL):** Since the `wren-engine` and `ibis-server` compile SQL dynamically by accepting the MDL JSON string in the request payload, we store the MDL schema in the metadata database scoped by `tenant_id`. It is compiled and transmitted on-the-fly per tenant request.
*   **AI Context & Embeddings:** Embeddings are indexed in Qdrant. To prevent leakage, `wren-ai-service` dynamically prefixes Qdrant collections with `tenant_{tenant_id}_`.

---

## 3. Table-Level RBAC Enforcement

Within any business unit, users have varying access rights. For example, a Retail Analyst can view the `loans` table but is blocked from the `salary` table.

```mermaid
sequenceDiagram
    autonumber
    actor User as Analyst (Priya)
    participant GW as API Gateway / Auth
    participant Apollo as Apollo GraphQL Server
    participant DB as Metadata DB (PostgreSQL)
    participant AIService as wren-ai-service
    participant Ibis as ibis-server

    User->>GW: POST /ask (Question: "Show loan amounts")
    GW->>GW: Validate JWT, extract tenant_id & user_id
    GW->>Apollo: Forward request with Headers (X-Tenant-ID, X-User-ID)
    Apollo->>DB: Query allowed tables in table_permissions for User Priya
    DB-->>Apollo: Allowed: loans, branches (Blocked: salaries)
    Apollo->>DB: Load Full MDL for tenant_id
    Apollo->>Apollo: Filter MDL: Remove salaries model and columns
    Apollo->>AIService: POST /v1/ask (Question + Filtered MDL Schema)
    Note over AIService: AI sees only allowed tables.<br/>Hallucinating blocked tables is prevented.
    AIService->>Ibis: Dry-run & Compile (Filtered MDL + Query)
    Ibis-->>AIService: Compiled Dialect SQL
    AIService-->>Apollo: Compiled SQL
    Apollo->>Ibis: Execute query with target Connection Info
    Ibis-->>Apollo: Raw Rows
    Apollo-->>User: Format markdown table with results
```

---

## 4. Query Federation & Data Source Connectivity

`ibis-server` connects to target databases using Ibis connectors. In our banking environment, BUs register their data sources via `wren-ui`.

*   **Federation:** For cross-database joins (e.g. Postgres transactional data joined with BigQuery historical data), queries are federated through a central **Trino** coordinator.
*   **Stateless execution:** When running a query or fetching metadata, `wren-ui` retrieves the encrypted connection details from its database, decrypts them, and sends them inside the request payload to `ibis-server`. This ensures `ibis-server` never has to maintain persistent connection states or credentials.

---

## 5. Security & Isolation Controls

1.  **VPC Service Controls:** GKE pods run in private namespaces.
2.  **KMS Encryption:** All database connection strings and passwords stored in the PostgreSQL database are encrypted at rest using GCP KMS.
3.  **No Schema Leakage to LLM:** Because the schema is pruned dynamically at the Apollo gateway layer, the LLM is entirely unaware of the existence of unauthorized database tables, preventing any indirect data discovery.
