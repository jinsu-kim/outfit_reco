# Outfit Recommendation Batch Pipeline

---

# Overview

A batch pipeline that generates 3 outfit sets per seed item for fashion platform clients.  
Each outfit consists of 5 categories: outer, top, bottom, shoes, and accessory.
---

* For reproducibility, this project uses CSV/JSON mock data.
* In production systems, item tables and outfit guidelines are usually loaded from internal databases.
* The compatibility matrix is assumed to be precomputed by a separate compatibility scoring module with GPUs.


---

# Pipeline Flow

```text
Backend-triggered Batch Request
    ↓
Redis-backed Job Queue
    ↓
GPU Worker Allocation
    ↓
Metadata Validation
    ↓
Candidate Filtering
    ↓
Guideline-based Outfit Generation
    ↓
Failure Logging
    ↓
Recommendation Export