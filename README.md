# Outfit Recommendation Batch Pipeline

---

# Overview

A batch pipeline that generates 3 outfit sets per seed item for fashion platform clients.  
Each outfit consists of 5 categories: outer, top, bottom, shoes, and accessory.
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
This pattern held across clients and item pools.

This pattern held consistently across clients and item pools,
so we limited scoring to the top 3 pairs only.


### Solution
1. Compute pair scores between the seed item and all tops
2. Select top 3 pairs
3. Run category combination only for the selected pairs
4. Aggregate scores → export 3 outfit sets

**Result**: Batch processing time reduced by ~67% (1/3 of original).


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
- Designed a DB schema to store client-specific subcategory mappings
- Refactored batch code to reference only the DB, with no per-client branching

The mapping UI was designed and implemented by PM, designer, and frontend team.  
My contribution: problem identification, architecture proposal, DB schema design, batch refactoring.

**Result**: A single batch codebase now serves all clients. Developer involvement at onboarding eliminated.  
