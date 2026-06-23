# Learning Journal

## Plan
- **Learning goal:** Build and inspect a first dense vector RAG app in `01_Dense_Vector_Retrieval/01_Cat_Health_Vector_RAG_LangChain_Qdrant.ipynb`: load a PDF, chunk it, embed with OpenAI, store in Qdrant, retrieve with scores, then generate grounded answers with LangChain.
- **Why this matters:** Most production RAG systems start here. If retrieval is weak, generation will look fluent but be wrong. This notebook teaches the full loop and how to debug it *before* adding agents, evaluators, or synthetic data.
- **Learning mode:** Mixed — concept, coding, AI engineering
- **Prior assumptions (inferred from your notebook work):**
  - Better embeddings alone might fix RAG quality
  - Similarity scores might mean "confidence" (e.g. 0.58 ≈ 58% sure)
  - Smaller chunks would always improve retrieval
  - Increasing `k` would improve retrieval ranking, not just add context
  - Citations in the final answer might prove retrieval was good

---

## Explore

### Concepts encountered
- Dense vector retrieval
- Embeddings and vector space
- Cosine similarity
- RAG loop: load → chunk → embed → store → retrieve → generate
- LangChain `Document` (`page_content` + `metadata`)
- `RecursiveCharacterTextSplitter` (chunk size, overlap, `add_start_index`)
- Qdrant in-memory vector store
- Retrieval depth `k`
- Retrieve-then-generate (two-step RAG, not an agent)
- LCEL chain: `prompt | llm | StrOutputParser()`
- Vibe checks and out-of-domain queries
- Retrieval tuning (chunk size, overlap, `k`, query wording)

### Plain-English explanation
Text becomes a list of numbers (an embedding). Similar meaning → vectors point in similar directions. At query time, you embed the question and ask the vector DB for the nearest chunk vectors. Those chunks become the LLM's "open book." The model should answer only from that context and refuse when the book doesn't contain enough.

Your primer made this concrete: `king` ↔ `queen` scored higher than `king` ↔ `banana`, and `cat` ↔ `cat health guidelines` beat `cat` ↔ `veterinarian`.

### Important distinctions
| Concept | What it is | Common mistake |
|---|---|---|
| **Similarity score** | Relative ranking signal | Treating 0.58 as "58% confident" |
| **Retrieval vs generation** | Finding chunks vs writing the answer | Skipping retrieval inspection and only reading the final answer |
| **Chunk size** | How much text one vector represents | Assuming bigger or smaller is always better |
| **Metadata vs semantics** | Structured filters/traceability vs meaning search | Relying on embeddings alone when metadata could filter by doc type, page, date, permissions |
| **In-memory Qdrant** | Fast local dev, no persistence | Expecting the index to survive after kernel restart |
| **Two-step RAG vs agent** | Always retrieve, then generate | Confusing this with tool-calling agents that decide *whether* to retrieve |
| **Relevant chunks vs good answer** | Retrieval can be noisy while the LLM still answers well (or vice versa) | Using citations alone as proof retrieval was strong |

### Related tools, APIs, and libraries
- **LangChain v1 packages:** `langchain_community` (PDF loader), `langchain_text_splitters`, `langchain_openai`, `langchain_qdrant`, `langchain_core`
- **Key APIs:** `PyPDFLoader.load()`, `RecursiveCharacterTextSplitter.split_documents()`, `OpenAIEmbeddings.embed_documents()`, `QdrantVectorStore.from_documents()`, `similarity_search_with_score()`, `ChatPromptTemplate`, `ChatOpenAI`
- **Models used:** `text-embedding-3-small`, `gpt-5.4-mini`
- **Helpers you built:** `cosine_similarity()`, `display_retrieval_results()`, `format_context()`, `answer_question()`

### Prerequisite knowledge
- Basic Python and notebook workflow (`uv sync`, env vars)
- What an LLM prompt is
- Rough idea of vectors / dot product (cosine similarity formula is in the notebook)

---

## Experiment

### Code, notebook, or prompt activity
You walked through seven tasks plus a tuning activity:

1. **Environment + imports** — LangChain partner packages, OpenAI key
2. **Embedding primer** — manual cosine similarity on toy words
3. **PDF loading** — 22 pages from `cat_health_guidelines.pdf`; metadata enriched with `source`, `document_type`
4. **Chunking** — baseline `1000/200` → 135 chunks; tuned `500/100` → 263 chunks
5. **Indexing** — embed all chunks into in-memory Qdrant collections
6. **Retrieval inspection** — scored results for on-topic and off-topic queries
7. **RAG** — system prompt with grounding rules, source labels, vet disclaimer; vibe checks
8. **Activity** — compare baseline vs tuned retrieval on kitten-health questions

### Predictions before running (inferred)
- Smaller chunks would sharpen retrieval for broad questions
- Higher `k` would surface better matches
- Off-topic queries would return low scores and the model would refuse

### Results, errors, and observations

**On-topic retrieval** (`"What signs suggest that a cat should be seen by a veterinarian?"`):
- Top scores ~0.54–0.58
- Chunks from pages 7–8 about pain, vomiting, behavior changes, stress signs
- Final RAG answer was detailed and cited sources well

**Off-topic retrieval** (`"How do I bake sourdough bread?"`):
- Scores dropped to ~0.08–0.10
- Still returned cat-health chunks (vector search always returns *something*)
- Useful signal: score gap between on-topic and off-topic queries

**Vibe checks:**
- Preventive care, vet symptoms, adult feeding — grounded, cited answers
- `"Can my cat help me file my taxes?"` → correct refusal via system prompt

**Tuning activity — your documented findings:**
- **Baseline (`1000/200`, k=5)** on `"What are commons illness in kitten?"`: top score 0.551; broader answer (URI/parasites, congenital issues, dentition, behavior)
- **Tuned (`500/100`, k=7)** on same broad question: top score 0.513; narrower answer; top chunk was house-soiling workup — *worse* for this question
- **Query rephrase** on tuned store: `"What diseases should veterinarians screen for in kittens?"` → scores ~0.55–0.57; pages 7 and 15; more focused answer aligned with PDF language
- **Increasing `k` alone:** more chunks to the LLM, same ranking — did not fix match quality

### Debugging insights
- **Inspect retrieval before generation.** Your sourdough experiment showed the DB still returns chunks; the score drop is the useful signal.
- **Read chunk previews, not just scores.** For the kitten illness question, baseline chunks were more on-target even with a higher top score.
- **Query wording is a retrieval lever.** Rephrasing to "screen for" matched how the guideline is written.
- **Scores are not comparable across indexes.** After changing chunk size, you rebuilt the collection — compare relevance by page/content, not raw score.
- **Generation can partially mask bad retrieval** (tax question), but that depends on prompt rules — not a reliable production safeguard.

### Next small experiment
Pick one failure mode and change **one variable**:
1. Keep `1000/200`, rephrase the broad kitten question to match PDF headings (e.g. "kitten examination focus areas" or "diseases requiring focus during kitten examination").
2. Or keep tuned `500/100`, add metadata filter later (e.g. only pages tagged `document_type=cat_health_guideline`) and see if noise drops.
3. Log `(query, top-3 previews, answer)` in a small table for 5 questions so you can compare settings side by side.

---

## Engineering Connection

### Where this appears in real AI systems
- Internal doc Q&A (policies, runbooks, medical guidelines)
- Support bots grounded in product docs
- Any "chat with your PDF" product

This notebook is the **retrieval substrate** that later modules build on (multi-agent research, synthetic eval datasets, agentic RAG evaluation).

### Tradeoffs
| Knob | Upside | Downside |
|---|---|---|
| Larger chunks | More local context per hit | More noise; lower precision |
| Smaller chunks | More precise hits | Split facts across boundaries; more vectors to store/embed |
| Overlap | Reduces boundary cuts | More storage, redundancy, embedding cost |
| Higher `k` | More evidence for the LLM | More tokens, latency, noise |
| In-memory Qdrant | Simple dev setup | No persistence; not production scale |
| OpenAI embeddings | Strong baseline quality | API cost, vendor lock-in, latency |

### Failure modes
- **Scanned PDFs** → empty text without OCR
- **Always-something retrieval** → irrelevant chunks for off-domain queries unless you add score thresholds or refusal logic
- **Chunk boundary splits** → eligibility in one chunk, exceptions in the next
- **Prompt-only grounding** → model may still hallucinate if retrieval is weak and rules are weak
- **Confusing score with confidence** → bad monitoring and bad thresholds
- **`langchain-community` deprecation** → migration to standalone integration packages over time

### Evaluation or monitoring angle
Before LangSmith/Ragas (later modules), you already have manual eval signals:
- Top-k chunk previews and pages
- Score gap for in-domain vs out-of-domain queries
- Whether the answer cites the right pages
- Whether the model refuses when context is insufficient

Your activity notes are an early form of **retrieval regression testing**: same question, different settings, compare sources + answer.

### Security, data, cost, deployment concerns
- **Safety:** Cat health domain needs vet disclaimers (you included these in the system prompt)
- **Cost:** Every chunk embedded once at index time; every query embeds again; every answer sends `k` chunks to the LLM
- **Deployment:** Production would use persistent Qdrant (or another vector DB), incremental indexing, auth on metadata, and retrieval evals — not `:memory:`

---

## Reflect

### What you understand now
- The full RAG pipeline end to end, with LangChain + Qdrant + OpenAI
- Cosine similarity as a **ranking** tool, not absolute truth
- Metadata supports filtering, traceability, freshness, and security — "better RAG ≠ only better embeddings"
- Chunk size/overlap trades precision vs context preservation, plus storage cost
- Retrieval quality must be inspected directly; generation quality can hide retrieval problems
- Tuning is multidimensional: chunk settings, `k`, and **query wording** interact

### What was unclear (or still worth sharpening)
- When to prefer character-based vs token-based chunking for this PDF
- Whether a similarity **threshold** should block retrieval before generation
- How your tuned store would compare on the *same* rephrased question vs baseline (A/B not fully logged)
- Production path: persistent Qdrant, re-indexing when the PDF updates, hybrid search (keywords + vectors)

### Misconception corrected
- **Smaller chunks do not always improve retrieval** — your activity showed they hurt a broad overview question while helping a screening-focused rephrase.
- **Similarity scores are for ordering, not calibrated confidence** — your Q3 answer captured this well.
- **Citations ≠ proof of good retrieval** — your Q4 answer noted the tax case: chunks were cat-related but irrelevant; the system prompt saved the answer.

### One-minute explanation
"RAG turns a PDF into searchable vectors. I split the doc into chunks, embed them, store them in Qdrant, and when a user asks a question I find the closest chunks and paste them into the prompt. The LLM answers from that context only. If retrieval sends the wrong chunks, the answer gets worse — so I check retrieved text and scores before trusting the final output."

### Active recall questions
1. What are the six steps of the RAG loop in this notebook?
2. Why embed document chunks once at index time but embed the query at search time?
3. What does cosine similarity measure, and why is it useful for ranking but not for absolute confidence?
4. Name two reasons metadata matters beyond semantic search.
5. What happens when you ask an off-topic question — does the vector store return nothing?
6. Why can increasing `k` fail to improve retrieval quality?
7. In your tuning activity, why did smaller chunks hurt the broad kitten question but help after rephrasing?
8. What is the difference between retrieve-then-generate RAG and an agent that chooses tools?

### Spaced review suggestion
- **Tomorrow:** Re-run one on-topic and one off-topic query; explain the score gap without looking at notes.
- **In 3 days:** Compare dense retrieval to keyword search mentally — when would BM25/hybrid beat pure vectors?
- **Next week:** Before opening the synthetic eval notebook, write down three manual retrieval checks you would automate later.

---

## Post-Task Teaching Debrief

### Approach taken
You did the right engineering sequence: **make retrieval visible first**, then add generation. The cosine-similarity primer on tiny examples (`king`/`queen`) before the full PDF kept the mechanism concrete. Building `display_retrieval_results()` and printing formatted context before calling the LLM is exactly how experienced RAG engineers debug — they don't start by reading polished answers.

### Roads not taken (likely alternatives)
- **Agent with a retrieval tool** — flexible, but hides the retrieval step; weaker for learning the core loop.
- **Hybrid search (BM25 + vectors)** — can help exact terms like "FeLV" or "panleukopenia"; more moving parts.
- **Score threshold / abstain before LLM** — could refuse earlier on off-topic queries instead of relying on the system prompt.
- **Token-based chunking** — often better aligned with embedding model limits than raw character counts.

For a first lesson, the two-step RAG path was the right call.

### How the pieces connect
PDF pages → `Document` objects → splitter → chunks with metadata (`page`, `start_index`) → embeddings → Qdrant collection → `similarity_search_with_score` → `format_context` → prompt variables → LLM → cited answer. Metadata flows from loader through retrieval into source labels, which supports both user trust and debugging.

### Tools and methods
LangChain v1's split packages mirror production modularity. Qdrant `:memory:` is a dev stand-in for a real vector service. OpenAI embeddings + chat model are a strong default, but swapping embedding models would change scores and possibly ranking — another reason not to treat scores as universal.

### Tradeoffs you actually hit
You prioritized **inspectability** (scores, previews, vibe checks) over **automation**. That paid off in the activity: you discovered smaller chunks alone did not help the broad question. You also saw that **prompt guardrails** can rescue bad retrieval on absurd queries (taxes), which is useful in demos but dangerous if mistaken for a retrieval fix in production.

### Mistakes and dead ends (from your notebook evidence)
- Initial broad kitten question with tuned `500/100` produced a more hesitant, narrower answer — a real dead end, not a failure: it proved chunk tuning is question-dependent.
- Trying `k=7` without changing ranking improved context volume, not relevance — a common early mistake.
- Off-topic sourdough still retrieved cat chunks — surprising if you expected "no results," but normal for vector search.

### Future pitfalls ("I wish someone told me earlier")
- Vector search **always returns the least-bad matches**, even when all matches are bad.
- **Rebuild the index** after changing chunk settings — old vectors are invalid for fair comparison.
- Don't compare top scores across different chunk configurations; compare **source pages and chunk text**.
- OCR matters for scanned PDFs; your loader assumes extractable text.
- `langchain-community` is being sunset — plan to migrate loaders to standalone packages.

### Expert lens
An experienced engineer would notice you already ran an informal **retrieval eval**: baseline vs tuned, broad vs rephrased query, manual judgment on page alignment. They would next add a fixed question set, log top-k metadata, and only then tune chunk hyperparameters systematically — one change at a time. They would also separate **retrieval failure** (wrong chunks) from **generation failure** (right chunks, wrong synthesis) by inspecting `format_context` output before blaming the LLM.

### Transferable lessons
1. **Debug retrieval before generation.**
2. **Treat hyperparameters as joint, not independent** — chunk size and query phrasing interact.
3. **Use refusal prompts as a safety net, not a retrieval substitute.**
4. **Metadata is a first-class RAG feature**, not decoration.
5. **Manual vibe checks become automated evals** in later course modules — you're already doing the primitive version.
