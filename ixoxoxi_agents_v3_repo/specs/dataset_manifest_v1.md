# Dataset Manifest v1 (immutable)

This document defines the minimum dataset versioning contract for the agent pipeline.

## Goals

- Every dataset version is immutable and addressable.
- A dataset version can be verified from its manifest hash.
- Storage paths are tenant-scoped (deny-by-default sharing).

## Storage layout

For a given `tenant_id` and `dataset_id`:

```
.tenants/<tenant_id>/datasets/<dataset_id>/
  blobs/<sha256>
  manifests/<dataset_version>.json
```

## Version identity

`dataset_version` is defined as:

`sha256(canonical_json(manifest))`

where canonical JSON is UTF-8, sorted keys, and no whitespace separators.

## Manifest schema

Required fields:

- `manifest_version`: integer (must be `1`)
- `tenant_id`: string (kebab-case)
- `dataset_id`: string
- `created_at`: RFC3339-like UTC (`...Z`)
- `parent_version`: string|null
- `source`: string|null
- `content.blob_sha256`: string|null
- `content.media_type`: string
- `metadata`: object

## Invariants

- No implicit "latest". All reads use explicit `dataset_version`.
- Any write produces a new `dataset_version` (new manifest).
- Content blobs are content-addressed by sha256.

## Future extensions (non-breaking)

- Tagging/aliases (`latest`, `prod`) as separate mutable pointers.
- Multi-blob datasets (chunks) by extending `content` to a list.
- Share scopes for cross-tenant access.
