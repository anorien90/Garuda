# Chat UI Visual Examples

## Example 1: Quick Success (Phase 1)

**User Question:** "What is Flask?"

**UI Display:**
```
┌─────────────────────────────────────────────────────────────┐
│ ✅ Completed: Phase 1: Local Lookup                        │
│ 🧠 RAG: 8 semantic hits                                    │
│ 🕸️ Graph: 3 relation hits                                 │
│ 📊 SQL: 2 keyword hits                                     │
│ 🔄 Search Cycles: 0/3                                      │
└─────────────────────────────────────────────────────────────┘

Flask is a lightweight WSGI web application framework...

Sources & Context (13 total)
[Context items shown below]
```

## Example 2: Success After Retry (Phase 2)

**User Question:** "Who is the CEO of StartupX?"

**UI Display:**
```
┌─────────────────────────────────────────────────────────────┐
│ ✅ Completed: Phase 2: Local Lookup after Retry            │
│ 🧠 RAG: 5 semantic hits                                    │
│ 🕸️ Graph: 2 relation hits                                 │
│ 📊 SQL: 1 keyword hits                                     │
│ 🔄 Retry with paraphrasing                                 │
│ 🔄 Search Cycles: 0/3                                      │
└─────────────────────────────────────────────────────────────┘

🔄 Paraphrased Queries
• "CEO of StartupX company"
• "StartupX chief executive officer"
• "Who leads StartupX"

Based on the available information: John Doe is the CEO...

Sources & Context (8 total)
[Context items shown below]
```

## Example 3: Success After Web Crawling (Phase 4, Cycle 2)

**User Question:** "What are the latest features in ProductX?"

**UI Display:**
```
┌─────────────────────────────────────────────────────────────┐
│ ✅ Completed: Phase 4: Local Lookup after cycle 2          │
│ 🧠 RAG: 12 semantic hits                                   │
│ 🕸️ Graph: 5 relation hits                                 │
│ 📊 SQL: 3 keyword hits                                     │
│ 🌐 Live Crawl: Insufficient high-quality RAG results (1)   │
│    after retry                                             │
│ 🔄 Retry with paraphrasing                                 │
│ 🔄 Search Cycles: 2/3                                      │
└─────────────────────────────────────────────────────────────┘

🔄 Paraphrased Queries
• "ProductX new features"
• "Latest updates in ProductX"

ProductX recently added the following features:
- Feature A: Enhanced performance...
- Feature B: New integration with...

Live URLs Crawled
• https://productx.com/release-notes
• https://productx.com/blog/latest-features
• https://techcrunch.com/productx-announcement

Sources & Context (20 total)
[Context items shown below]
```

## Example 4: Insufficient After All Cycles (Phase 4, Warning State)

**User Question:** "What is the secret formula of CompanyY?"

**UI Display:**
```
┌─────────────────────────────────────────────────────────────┐
│ ⚡ Final State: Phase 4: Local Lookup Insufficient after   │
│    all cycles                                              │
│ 🧠 RAG: 2 semantic hits                                    │
│ 🕸️ Graph: 1 relation hits                                 │
│ 📊 SQL: 0 keyword hits                                     │
│ 🌐 Live Crawl: Insufficient high-quality RAG results (0)   │
│    after retry                                             │
│ 🔄 Retry with paraphrasing                                 │
│ 🔄 Search Cycles: 3/3                                      │
└─────────────────────────────────────────────────────────────┘

Based on the available information:

CompanyY's formula is proprietary and not publicly disclosed...

Live URLs Crawled
• https://companyy.com/about
• https://wikipedia.org/wiki/CompanyY

Sources & Context (3 total)
[Limited context available]
```

## Example 5: No URLs Found (Error State)

**User Question:** "Details about XyzNonexistentCompany?"

**UI Display:**
```
┌─────────────────────────────────────────────────────────────┐
│ ⚠️ Final State: Error No URLs Found after all cycles       │
│ 🧠 RAG: 0 semantic hits                                    │
│ 🕸️ Graph: 0 relation hits                                 │
│ 📊 SQL: 0 keyword hits                                     │
│ 🌐 Live Crawl: No RAG results found                        │
│ 🔄 Search Cycles: 3/3                                      │
└─────────────────────────────────────────────────────────────┘

I searched online but couldn't find relevant sources.
Try a different question or crawl some relevant pages first.

Sources & Context (0 total)
[No context available]
```

## Example 6: Fallback Answer (Error State)

**User Question:** "Complex query with no good results"

**UI Display:**
```
┌─────────────────────────────────────────────────────────────┐
│ ⚠️ Final State: Error Fallback Answer Generated            │
│ 🧠 RAG: 1 semantic hits                                    │
│ 🕸️ Graph: 1 relation hits                                 │
│ 📊 SQL: 1 keyword hits                                     │
│ 🌐 Live Crawl: Answer insufficient despite RAG results     │
│    and retry                                               │
│ 🔄 Retry with paraphrasing                                 │
│ 🔄 Search Cycles: 3/3                                      │
└─────────────────────────────────────────────────────────────┘

Based on the available information:

[Snippet 1 from context]

[Snippet 2 from context]

Sources & Context (3 total)
[Context items shown below]
```

## Color Legend

- ✅ **Green Badge** (`Completed`): Successful answer with high confidence
- ⚡ **Amber Badge** (`Final State`): Partial answer, best effort after all attempts
- ⚠️ **Red Badge** (`Final State`): Error state, fallback or no results

## State Progression Examples

### Scenario A: Immediate Success
```
Phase 1: Initial RAG → ✅ Completed
└─ Final: phase1_local_lookup
```

### Scenario B: Success After Retry
```
Phase 1: Initial RAG → Insufficient
Phase 2: Retry with Paraphrasing → ✅ Completed
└─ Final: phase2_local_lookup_after_retry
```

### Scenario C: Success After 2 Web Crawl Cycles
```
Phase 1: Initial RAG → Insufficient
Phase 2: Retry → Insufficient
Phase 3: Web Crawling
  ├─ Cycle 1 → Still insufficient
  └─ Cycle 2 → ✅ Completed
Phase 4: Final Local Lookup → Success
└─ Final: phase4_local_lookup_after_cycle_2
```

### Scenario D: All Cycles Exhausted
```
Phase 1: Initial RAG → Insufficient
Phase 2: Retry → Insufficient
Phase 3: Web Crawling
  ├─ Cycle 1 → Still insufficient
  ├─ Cycle 2 → Still insufficient
  └─ Cycle 3 → Still insufficient
Phase 4: Final Local Lookup → ⚡ Insufficient
└─ Final: phase4_local_lookup_insufficient_after_all_cycles
```

### Scenario E: No URLs Found
```
Phase 1: Initial RAG → Insufficient
Phase 2: Retry → Insufficient
Phase 3: Web Crawling → ⚠️ No URLs found in search
└─ Final: error_no_urls_found_after_all_cycles
```
