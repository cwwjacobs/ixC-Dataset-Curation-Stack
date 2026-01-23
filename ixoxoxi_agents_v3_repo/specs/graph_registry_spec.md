Graph Registry Spec (v1)

Purpose
- Provide immutable, versioned agent graphs that can be activated per-tenant and swapped without code deploys.
- Enable safe rollback via tenant-scoped history.

Definitions
- graph_id: stable logical identifier (e.g. "xi-default")
- graph_version: sha256 hash of the canonical JSON graph definition (excluding graph_version field)
- graph spec location: specs/graphs/<graph_id>/<graph_version>.json

Graph JSON schema (minimum)
{
  "graph_id": "<string>",
  "graph_version": "<sha256>",
  "sequence": ["<AgentClassName>", "..."],
  "metadata": { ... }
}

Hot-swap model
- Jobs MUST pin graph_version (context_contract v1 requirement).
- Tenant activation pointer is used to decide what *new* jobs should pin.
- Swapping a tenant to a new graph_version is an admin action:
  - Write `.tenants/<tenant_id>/graphs/active.json`
  - Append `.tenants/<tenant_id>/graphs/history.jsonl`

Compatibility checks (v1)
- GraphRegistry validates:
  - file exists
  - declared graph_version matches computed version
  - sequence is a list[str]
- Runner validates:
  - every agent name in sequence is known and instantiable
  - policy gates evaluate at pre_exec and around each agent stage

Rollback
- TenantGraphManager.rollback(graph_id) re-activates the previous graph_version if present in history.

Default graph shipped
- graph_id: xi-default
- graph_version: 30ab6ebb28daac2ffb4478303e6a490d2f62cee19d6182dcfd9d3a8bcee98f7a
- sequence: xiProvenanceAgent -> xiAuditAgent -> xiCurateAgent
