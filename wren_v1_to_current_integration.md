# RhinoGenBI — Legacy/v1 to Current Wren Integration

This document outlines the architectural options and details of how legacy/v1 Wren components are wired with the current version of Wren to support our multi-tenant GenBI platform.

---

## 1. Architectural Options

To integrate legacy/v1 Wren (Next.js GraphQL UI, Python AI service) with the current version of Wren (Rust core engine, Python SDK/CLI), three main options exist:

### Option A: Loose Coupling via Service Boundaries (API-Based)
* **Description**: Services communicate over HTTP. The legacy Next.js server (`wren-ui`) and Python backend (`wren-ai-service`) run alongside containerized instances of the new Rust-based `wren-engine` and `ibis-server` connectors.
* **Pros**:
  - **Stability**: Complete runtime isolation prevents library version conflicts.
  - **Ease of Deployment**: Leverages pre-built Docker images for heavy computational components (Rust engine, Trino).
  - **No Compilation Overhead**: Developers do not need native Rust toolchains or complex local setups to build/run the application.
* **Cons**:
  - Higher memory footprint due to multiple running containers.
  - API network overhead between components.

### Option B: Monorepo Library Integration (Native Bindings)
* **Description**: The core Rust engine (`wren-core`) is built locally and wired directly into the Node.js/Next.js backend via native addons (e.g., Neon or N-API) or FFI. The Python AI service imports `wren` (the Python SDK) as a dependency rather than using HTTP.
* **Pros**:
  - **Performance**: In-memory function calls; no network serialization overhead.
  - **Single Process**: Reduces the overall number of running containers.
* **Cons**:
  - **Platform Incompatibilities**: Compiling native packages (like `duckdb` or `better-sqlite3`) on macOS arm64 (Apple Silicon) frequently runs into linking issues.
  - Requires developers to maintain Rust and Python compilers on their host machines.

### Option C: In-Process WebAssembly (WASM) Bindings
* **Description**: Compile `wren-core-wasm` into WebAssembly and load it directly inside the Next.js API routes.
* **Pros**:
  - **Portability**: Runs in any environment (including edge runtimes) without native compiler dependencies.
* **Cons**:
  - Data transfer limits across the JS-WASM boundary.
  - Performance penalty for large metadata schemas.

---

## 2. Our Implementation: Option A + Unified Monorepo

We selected **Option A (API-Based Service Boundaries)** paired with a **Unified Monorepo Layout**. This provides the best compromise between dev velocity, runtime stability, and production reliability.

### Directory Structure
The repository is structured as a monorepo that houses both legacy and current versions:
* `wren-ui/` (Legacy/v1 Next.js frontend + GraphQL API middleware)
* `wren-ai-service/` (Legacy/v1 Python AI service + RAG pipelines)
* `core/` (Current Wren core engine, models, and bindings)
  - `core/wren-core/` (Rust engine)
  - `core/wren-core-py/` (Python bindings)
  - `core/wren/` (Python SDK + CLI)
  - `core/wren-mdl/` (MDL definitions)
* `sdk/` (Current SDK integrations)
  - `sdk/wren-langchain/` (LangChain)
  - `sdk/wren-pydantic/` (Pydantic models)

### How they are wired

#### 1. Containerized Service Mesh
The services are orchestrated using a unified `docker-compose.yaml`. The network topology is structured as follows:

```
                  ┌──────────────────────┐
                  │    RhinoGenBI UI     │
                  │   (Next.js on 3000)  │
                  └─────┬──────────┬─────┘
                        │          │
         GraphQL / REST │          │ REST (Metadata & substitute)
                        ▼          ▼
             ┌───────────┐    ┌─────────────┐
             │ Keycloak  │    │ ibis-server │ ◄──► Trino (8443)
             │  (8180)   │    │   (8000)    │
             └───────────┘    └─────────────┘
                        ▲          ▲
        Deploy manifest │          │ Dry-run & SQL rewrite
                        ▼          ▼
            ┌─────────────┐   ┌─────────────┐
            │   Wren AI   │──►│ wren-engine │
            │   (5555)    │   │   (8080)    │
            └──────┬──────┘   └─────────────┘
                   │
                   ▼
               ┌────────┐
               │ Qdrant │
               │ (6333) │
               └────────┘
```

#### 2. Model Definition Language (MDL) Pipeline
Wren uses an MDL manifest to define models, columns, calculations, and relationships.
* **Extraction**: During tenant onboarding, `onboardingService` queries `ibis-server` to fetch database catalog tables and foreign key constraints.
* **Building**: `MDLBuilder` translates the catalog metadata into a valid MDL JSON manifest.
* **Deployment**: The manifest is deployed to `wren-engine` and indexed in `wren-ai-service` via API endpoints.

#### 3. Multi-Tenant Request Lifecycle
To support multiple tenants on a single shared instance of `wren-ai-service` and `wren-engine`:
1. **Tenant Filtering**: The Next.js BFF hooks into requests and appends `X-Tenant-Id` and `X-LLM-Api-Key` to outgoing API calls.
2. **Qdrant Isolation**: The `wren-ai-service` intercepts these headers and restricts vector search queries to documents tagged with the tenant's `project_id`.
3. **Table ACL**: The Next.js BFF parses generated SQL queries and verifies that the requesting user has permission to read the referenced tables before executing them on Trino.
