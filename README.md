# Outfit Recommendation Batch


# Overview
A batch pipeline that generates 3 outfit sets per seed item for fashion platform clients.  
Each outfit consists of 5 categories: outer, top, bottom, shoes, and accessory.
<br>

---

## Challenge 1: Combinatorial Explosion

### Problem
With 20–40 items per category, a full search requires a 4-level nested loop,
generating tens of thousands of combinations per request.
As batch requests accumulated, processing delays became a bottleneck in production.

### Insight
I examined whether pair scores could serve as a proxy for full outfit scores.

**Observation**: The top-scoring pair between the seed item (outer) and tops  
consistently ranked highest in overall outfit score aggregation.  

This pattern held consistently across clients and item pools,
so we limited scoring to the top 3 pairs only.


### Solution
1. Compute pair scores between the seed item and all tops
2. Select top 3 pairs
3. Run category combination only for the selected pairs
4. Aggregate scores → export 3 outfit sets

**Result**: Batch processing time reduced by ~67% (1/3 of original).
<br>

---

## Challenge 2: Per-client Codebase Fragmentation

### Problem
Each client had its own category taxonomy.  
The batch code was duplicated per client, requiring developer intervention  
every time a new client was onboarded — approximately 3 hours per client.

### Insight
This was a structural problem, not a code problem.  
Fixing it in code would just produce better-organized duplication.

### Solution
Proposed a category mapping architecture at the service policy level:

- Fixed macro-categories (outer, top, bottom, shoes, accessory) inside the system
- Designed a DB schema to store client-specific subcategory mappings  and outfit combination rules, both configurable via admin page
- Refactored batch code to reference only the DB, with no per-client branching

The mapping UI was designed and implemented by PM, designer, and frontend team.  
My contribution: problem identification, architecture proposal, DB schema design, batch refactoring.

**Result**: A single batch codebase now serves all clients. Developer involvement at onboarding eliminated.  
<br>

---

## Pipeline Flow
```text
Backend-triggered Batch Request
    ↓
Redis-backed Job Queue
    ↓
GPU Worker Allocation (auto-assigned to available slots)
    ↓
Metadata Validation
    (season alignment / availability / brand isolation)
    ↓
Pair Score-based Candidate Filtering
    - eliminates 4-level nested loop
    ↓
Guideline-based Outfit Generation
    + (combination rules configured by client via admin page)
    ↓
Recommendation Export
```
<br>

---

## Production Considerations

- **Season filtering**: excludes items with mismatched season tags
- **Brand isolation**: item pool separated per client
- **Availability check**: filters by stock and item status
- **GPU slot management**: FIFO queue with auto-allocation to idle slots
- **Failure logging**: records and tracks combination generation failures

---

## Tech Stack

Python · PyTorch · FastAPI · Docker · Redis