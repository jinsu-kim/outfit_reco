# Outfit Recommendation Batch Pipeline

---

# Overview

Generating three outfit recommendations for a seed item.

In production systems, recommendation pipelines must enforce:

- season alignment
- sellable item filtering
- valid outfit combination
- brand/site isolation

This repository demonstrates how these orchestration constraints can be handled in a batch recommendation pipeline.

---

# Pipeline Flow

```text
Backend-triggered Batch Request
    ↓
Metadata Validation
    ↓
Candidate Filtering
    ↓
Guideline-based Outfit Generation
    ↓
Failure Logging
    ↓
Batch Export