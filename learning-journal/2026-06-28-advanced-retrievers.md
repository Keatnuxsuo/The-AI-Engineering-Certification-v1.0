# Learning Journal — Session 7: Advanced Retrievers

**Source notebook:** `07_Advanced_Retrievers/01_Cat_Health_Advanced_Retrieval.ipynb`

## Plan
- Learning goal: Work through `07_Advanced_Retrievers/01_Cat_Health_Advanced_Retrieval.ipynb` — compare dense, BM25, parent-child, hybrid RRF, Cohere reranking, and multi-query retrieval on the same cat-health PDF — then make an evidence-based retriever recommendation.
- Why this matters: Retrieval decides what evidence the LLM ever sees. A weak retriever caps the quality and safety of every answer, no matter how good the model is.
- Learning mode: Mixed (AI Engineering + Coding).
- Prior assumptions going in:
  - Higher score = more relevant, even across different retrievers.
  - More retrieval stages = better results.
  - MRR measures diversity of retrieved chunks.
  - Multi-query is mostly cleaning up the user's prompt.
- Prerequisite knowledge this session leaned on: embeddings and cosine similarity, vector stores (Qdrant), chunking, RAG basics, and the idea of evaluation with reviewed cases.

## Explore
- Concepts encountered: dense retrieval, sparse/BM25 retrieval, parent-child retrieval, hybrid retrieval, reciprocal rank fusion (RRF), cross-encoder reranking, multi-query expansion, metadata filtering, retrieval eval vs answer eval, MMR.
- Plain-English explanations:
  - Dense = search by meaning, in embedding space.
  - BM25 = search by exact tokens/keywords.
  - Parent-child = search small precise chunks, return the larger parent page.
  - RRF = merge ranked lists by rank position, not raw score.
  - Reranking = a slower, more accurate second-stage relevance judge.
  - Multi-query = rewrite the question into several phrasings to widen recall.
  - MMR = pick results that are relevant **and** non-redundant.
- Important distinctions:
  - Dense, BM25, RRF, and reranker scores live on **different scales** and are not directly comparable.
  - Retrieval eval asks "did we fetch the right evidence?"; answer eval asks "is the generated answer grounded and complete?"
  - MRR = how early the first relevant hit appears; it says nothing about diversity.
  - Faithfulness ≠ completeness. An answer can be 1.0 faithful but still miss content (that's what answer similarity catches).
- Related tools/APIs: `QdrantVectorStore`, `BM25Okapi`, `CohereRerank`, OpenAI embeddings, and the local `lib/` eval framework (`run_retrieval_eval`, `run_eval`, `compare_reports`).

## Experiment
- Notebook: `07_Advanced_Retrievers/01_Cat_Health_Advanced_Retrieval.ipynb`
- Activity: compared dense, BM25, parent-child, hybrid+RRF+Cohere, and multi-query pipelines on both retrieval metrics and answer metrics; then started an optional MMR build.
- Code anchor 1 — the parent-child link:
```python
page_id = child.metadata["page_id"]
parent = parents_by_id[page_id]
```
  - What it does: maps a retrieved child chunk back to its full parent page.
  - Why it matters: this metadata link is the whole mechanism behind "search small, return large" and behind citations.
  - Predicted: "page" was maybe the parent. Confirmed: the page **is** the parent unit in this notebook, joined via `page_id`.
  - Reusable rule: traceability is a metadata design decision made at indexing time, not an afterthought.
- Code anchor 2 — the MMR bug that kept recurring:
```python
candidate_embeddings = [embeddings.embed_query(doc.text) for doc in candidates]  # .text, not .page_content
```
  - What it does: embeds candidate text for the diversity comparison.
  - Why it matters: `RetrievedDocument` stores text in `.text`; `.page_content` belongs to LangChain `Document`. Mixing the two types was the root confusion.
  - Predicted: the loop would just work. Actual: repeated structural bugs (selecting twice per loop, indexing a `set`, one global redundancy value).
  - Reusable rule: MMR is the selection rule **from the first pick** (redundancy = 0 when nothing is selected yet), not similarity-first then MMR-second.
- Results / observations:
  - Retrieval table: all retrievers hit recall 1.0 on 3 cases; the real separators were **MRR and latency**. `dense_parent_child` had MRR 1.0 at ~379ms; multi-query was ~3487ms; BM25 was sub-millisecond but lowest MRR.
  - Answer table: parent-child had strong similarity but one faithfulness dip on BCS/MCS (0.833); BM25 was best on the acronym case but worst on life-stage (faithfulness 0.5, similarity 0.558).
- Next small experiment: finish `run_mmr_selection`, then measure whether MMR cuts duplicate-page results without hurting recall/MRR.

## Engineering Connection
- Where this appears in real systems: production RAG often **routes** queries — keyword/acronym queries to BM25/hybrid, broad semantic queries to dense/parent-child, hard/ambiguous queries to multi-query as a heavier fallback.
- Tradeoffs: each added stage buys quality with latency and cost. RRF avoids the score-scale problem; reranking adds an API dependency; multi-query multiplies retrieval calls.
- Failure modes: comparing raw scores across methods; over-trusting aggregate metrics on tiny eval sets; redundant chunks from one page; faithful-but-incomplete answers; over-filtering metadata until recall collapses.
- Evaluation/monitoring angle: track hit@k, recall@k, MRR, latency for retrieval; faithfulness + answer similarity for generation. In production you'd also log per-query latency and which route handled it.
- Security / data / cost / deployment: Cohere reranking sends candidate text to a third party — a data-governance consideration for sensitive corpora, and a reason OSS rerankers (bge, Qwen3-Reranker, jina) can be attractive. The "free model" still carries GPU/serving cost. Changing documents also means re-indexing: the vector index is a derived structure that must stay in sync with the source of truth.

## Follow-up: Metric Tradeoffs & Product Decisions

### Is more retrieval always better?
No. Each added stage (hybrid, RRF, rerank, multi-query) trades latency, cost, and complexity for a specific gain. A stage only earns its place when eval shows it improves the **answer the user actually sees**, not just retrieval counts.

### Ship multi-query + rerank for every question?
No — not as the default. In this session, multi-query + rerank had faithfulness 1.0 on all cases and strong answer similarity, but much higher latency (~4–5s vs ~1.4–1.7s for parent-child on some cases) and lower MRR than parent-child (0.78 vs 1.0). It did not clearly beat simpler pipelines enough to justify the cost on every query.

**Production routing pattern:**
```text
Default: dense parent-child (or naive dense)
Acronym/keyword queries → BM25 or hybrid
Hard, vague, multi-part questions → multi-query + rerank as a heavier fallback
```

### What does recall↑ but MRR↓ mean?
They measure different things:

| Metric | Question it answers |
|--------|---------------------|
| **Recall@k** | Did relevant evidence appear *somewhere* in the top k? |
| **MRR** | How *early* did the first relevant result appear? |

**Recall↑ + MRR↓** = the right evidence was found, but it landed **lower in the ranking** (e.g. rank #4 instead of #1).

For RAG, that matters because the LLM often prioritizes top-ranked chunks. Weak context at #1–#2 can produce a **faithful but thin** answer even when the best passage sits at #4.

Example: senior cat exam frequency — recall finds page 6 in top 4, but MRR is low because a behavior/scratching chunk ranks first. A faithful answer might mention behavior but miss "minimum annual examinations."

### When retrieval metrics disagree — which tell you if the answer got better?
Use **both layers**:

**Retrieval layer** (evidence finding):
- Hit@k / recall@k — did we fetch the right pages/chunks?
- MRR — did the best evidence rank high?
- Latency — fast enough to ship?

**Answer layer** (what the user actually sees):
- **Faithfulness** — are the answer's claims supported by retrieved passages?
- **Answer similarity** — does the answer match the reviewed reference in content?

If retrieval metrics disagree, **answer-level metrics are the tiebreaker** for "did the user-facing answer improve?"

### For a health corpus — which metric is non-negotiable?
**Faithfulness** (groundedness). A fluent but unsupported answer is dangerous in health-adjacent contexts. High answer similarity without faithfulness can mean plausible wording not backed by the source.

**Priority order for cat-health RAG:**
```text
1. Faithfulness — must not hallucinate beyond retrieved context
2. Recall / hit@k — must find the right evidence at all
3. MRR — must rank best evidence high (ranking affects what the LLM prioritizes)
4. Answer similarity — catches incomplete answers faithfulness misses
5. Latency / cost — ship only if 1–4 are acceptable
```

### Faithful ≠ complete (misconception corrected)
Initial instinct: recall 1.0 + faithfulness 1.0 = "good enough" even with low MRR.

**Correction:** That combo is **not** automatically good enough.

```text
recall = 1.0, MRR = 0.25, faithfulness = 1.0
```

- Recall 1.0 → right evidence is in top k
- MRR 0.25 → first relevant hit around rank #4 (1/4 = 0.25)
- Faithfulness 1.0 → what the model said is supported by retrieved text

Faithfulness checks whether claims are **supported**; it does not check whether the model **said everything important**. With low MRR, the LLM may answer faithfully from weaker top chunks and never use the strongest passage — safe but shallow.

**Rule of thumb:** faithfulness = non-negotiable; recall + MRR + answer similarity together tell you whether the answer is also **useful and complete**.

Think of this session like tuning a kitchen, not picking one "best knife."

- Approach taken: you climbed the ladder in order — naive dense first, then added one capability at a time. That ordering is deliberate: each rung exposes the weakness the next rung fixes (dense is fuzzy → BM25 for exact terms → parent-child for context → RRF to combine → rerank for precision → multi-query for recall). Building in that order means every added stage has to *earn* its place against a baseline.
- Roads not taken: you could have jumped straight to the full multi-query + rerank pipeline and called it "the best." The eval is exactly what talked you out of that — it added latency without improving the metrics on these cases. A likely alternative default would have been naive dense (perfect faithfulness, lower latency); you chose parent-child for richer context, which is a reasonable, defensible call.
- How the pieces connect: the `lib/` framework is the spine. `eval_core.py` is generic (data + task + scorers → report); `retrieval_eval.py` and `answer_eval.py` are thin layers on top. The notebook just defines cases and composes retrievers. That separation is why you could swap retrievers and compare apples-to-apples.
- Mistakes and dead ends: the MMR build was the honest struggle — `.page_content` vs `.text`, selecting two docs per loop, subscripting a `set`, and a single global redundancy value. Each was a real bug, and each fix taught the actual MMR definition better than reading it would have.
- "Wish I'd known earlier": scores are only comparable within one scorer/query/candidate set (Adrian's rule). Internalizing that early prevents a whole category of misreadings.
- Expert lens: an experienced engineer treats 3 eval cases as a smoke test, not a verdict, and immediately asks "what query types am I *not* testing?" (tables, multi-page answers, adversarial phrasings). They also separate the *default* retriever from *routing* exceptions.
- Transferable lesson: in any ML system, prefer the simplest component that passes eval, add complexity only when measured gains justify the cost, and keep the evaluation harness as the source of truth.

## Reflect
- What I understand now: advanced retrieval is evidence-driven system design, not technique-stacking. The right choice depends on query type, corpus, latency budget, and safety needs.
- What was still unclear / to revisit: whether MMR actually reduces redundancy here (untested), and how routing between BM25 and parent-child would be implemented in practice.
- Misconceptions corrected: cross-method score comparison; "more stages = better"; MRR = diversity; multi-query = prompt cleanup; higher aggregate metric settles a product decision; and **recall 1.0 + faithfulness 1.0 alone does not mean "good enough"** when MRR is low (faithful but incomplete answers are still a failure mode).
- One-minute explanation: Default to dense parent-child for focused search with page-level context. Route exact acronym/keyword queries (like BCS/MCS) to BM25. Reserve multi-query + rerank for ambiguous, multi-part questions where recall is worth the latency.
- Active recall questions:
  1. Why can't you compare a dense 0.77 with an RRF 0.03?
  2. What exactly does MRR measure, and what does it ignore?
  3. Why does parent-child search children but return parents?
  4. Why is `1/(60+rank)` shaped that way, and what does the 60 control?
  5. Why can an answer score 1.0 faithfulness yet still be a weak answer?
  6. If recall = 1.0, MRR = 0.25, and faithfulness = 1.0, is that pipeline good enough for every health question? Why or why not?
- Desirable-difficulty challenge: without rereading, write the MMR scoring line for one candidate (relevance term minus redundancy term) and state what redundancy equals on the very first pick.
- Spaced review: revisit RRF + MRR + retrieval-vs-answer eval tomorrow; redo the recall questions in 3 days; in ~1 week, re-derive MMR from memory and run it against dense.
