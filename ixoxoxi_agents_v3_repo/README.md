# ixC Dataset Curation Stack (v1)

**ixC = Intelligence by Clarity**

Deterministic, auditable dataset curation for teams that cannot afford ambiguity.

This repository contains the ixC Dataset Curation Stack: a production-ready pipeline for ingesting, validating, normalizing, and curating datasets with hard guarantees around reproducibility, provenance, and failure behavior.

This is infrastructure, not a demo. It is designed for real data, real constraints, and real accountability.

---

## What this stack does

The ixC stack provides a controlled, deterministic workflow to turn raw datasets into curated, audit-ready artifacts suitable for:

* model training
* internal review
* external delivery
* long-term storage

The system prioritizes clarity over cleverness, and correctness over automation.

---

## Core agents

### xiProvenanceAgent

* Computes cryptographic fingerprints (SHA-256)
* Attaches timestamps, job IDs, and tenant context
* Never mutates the dataset payload

### xiAuditAgent

* Performs bounded, deterministic checks (e.g. payload size, basic integrity)
* Emits structured findings and warnings
* Designed to fail loudly on invalid conditions

### xiCurateAgent

* Enforces JSON-serializability
* Performs stable deduplication
* Normalizes schema across records
* Attaches curation metadata without altering semantics

All agents are pure functions over `(dataset, context)` with side effects restricted to context updates.

---

## Architecture overview

```
raw dataset
  → xiProvenanceAgent   (identity & lineage)
  → xiAuditAgent        (hard checks & warnings)
  → xiCurateAgent       (structural normalization)
  → [optional] decision-support model (non-authoritative)
  → selector / storage / dispatch
```

Deterministic agents always take precedence over any probabilistic decision support.

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

## What this is not

* Not a chat assistant
* Not a black-box AI system
* Not an autonomous decision-maker
* Not a hosted SaaS by default

Silence is a valid outcome. Explicit failure is preferred to ambiguous success.

---

## Deployment model

The ixC Dataset Curation Stack is intended to be:

* run inside your own infrastructure, or
* used as part of an assisted dataset curation engagement

No data leaves your environment unless explicitly configured.

---

## Current status

* Production-ready v1
* Actively used for internal dataset curation
* Optional model-based decision support is gated and non-authoritative

---

## Commercial use

This repository is the technical core of a paid dataset curation and provenance offering.

If you are interested in:

* assisted dataset curation
* internal deployment
* consulting or operational support

Contact: **[your contact here]**

---

## Philosophy

> The model is not the product. The product is selectively saved, high-value decision artifacts produced under explicit constraints.

ixC intelligencexClarity 

---

## License

[Specify license or commercial terms here]
