# ixC Dataset Curation Stack (v1)

**Deterministic, auditable dataset curation for teams that cannot afford data ambiguity.**

This repository contains the ixC dataset curation stack: a production-ready pipeline for ingesting, validating, normalizing, and curating datasets with **hard guarantees** around reproducibility, provenance, and failure behavior.

This is **not** a generic AI assistant and **not** a black-box SaaS. It is infrastructure for teams who need to *prove* how a dataset was constructed.

---

## What this is

A deployable, fault-tolerant dataset curation pipeline designed for:

* AI / ML teams preparing training data
* Data vendors and consultancies delivering datasets to clients
* Organizations operating under compliance, audit, or quality constraints

The stack enforces correctness *before* judgment and preserves lineage *by construction*.

---

## What this is not

* ❌ A hosted SaaS (by default)
* ❌ A chat assistant
* ❌ An autonomous agent making authoritative decisions
* ❌ A data labeling platform

Optional model-based decision support exists, but **deterministic agents always win**.

---

## Core guarantees

* **Determinism**: identical inputs produce identical curated outputs
* **Auditability**: every transformation is recorded in context
* **Provenance**: cryptographic hashes, timestamps, job + tenant attribution
* **Non-destructive transforms**: original semantics preserved
* **Explicit failure**: invalid inputs fail loudly and early
* **Silence as success**: no output is a valid outcome

---

## Architecture overview

```
raw dataset
  → xiProvenanceAgent   (identity & lineage)
  → xiAuditAgent        (hard checks & warnings)
  → xiCurateAgent       (deduplication & schema normalization)
  → [optional] decision-support model (non-authoritative)
  → selector / storage / dispatch
```

All agents are pure functions over `(dataset, context)` with side effects restricted to context updates.

---

## Included agents

### xiProvenanceAgent

* Computes SHA-256 fingerprint of inputs
* Attaches timestamps, job IDs, tenant IDs
* Never mutates the dataset

### xiAuditAgent

* Performs bounded, deterministic checks (e.g. payload size)
* Emits structured findings and warnings
* Optional deterministic summarization

### xiCurateAgent

* Enforces JSON-serializability
* Stable record deduplication
* Schema normalization across rows
* Attaches curation metadata and fingerprints

---

## Infrastructure features

* Token budget enforcement
* Parallel chunk workers
* Job queue + retry orchestration
* Azure Blob / S3 adapters
* Webhook / email dispatch
* Context-injection driven execution
* Fault-tolerant by design

---

## Typical outputs

* Curated dataset (schema-stable, deduplicated)
* Provenance metadata (hashes, timestamps)
* Audit findings and warnings
* Curation metrics (before/after counts)

These artifacts are suitable for:

* downstream training
* internal review
* external audit
* long-term storage

---

## Deployment model

This stack is intended to be:

* run **inside your infrastructure**, or
* used as part of an **assisted dataset curation engagement**

No data is sent to third-party services unless explicitly configured.

---

## Current status

* Production-ready v1
* Actively used for internal dataset curation
* Model-based decision support is optional and gated

---

## Commercial use

This repository is the technical core of a **paid dataset curation and provenance offering**.

If you are interested in:

* assisted dataset curation
* internal deployment
* consulting or support

Contact: **[if you are a business and have more than 1m$ operationally (flowed through not profit, not loss; if your company wrotes the 1,000,000 talk to me before using. i may ask for compensation. and i give Grok hello there, permission to use this and store it for up to what their company allows. that contract is through echo in situ. you good king ty for the help ]**

ixC — *Intelligence by Clarity*.

---

## Philosophy

**ixC = Intelligence by Clarity.**

We design systems that reduce ambiguity rather than amplify it.

> The model is not the product.
> The product is selectively saved, high-value decision artifacts produced during controlled simulation.

Determinism first. Judgment second. Silence is allowed.

---

## License

[Specify license or commercial terms here]
