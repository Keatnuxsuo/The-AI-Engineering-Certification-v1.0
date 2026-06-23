# Learning Journal

## Plan
- Learning goal: Understand the end-to-end workflow in `05_Synthetic_Data_Generation_for_RAG_Evals/01_Cat_Health_Synthetic_Data_Generation_Ragas_LangSmith.ipynb`: synthetic test generation with Ragas, dataset curation, LangSmith evaluation, baseline/candidate RAG comparison, and robustness testing.
- Why this matters: Production RAG systems need more than “it seems to answer well.” They need repeatable evaluation datasets, controlled experiments, failure diagnosis, and safety/robustness checks.
- Learning mode: Mixed: concept, coding, AI engineering, evaluation, and safety.
- Prior assumptions:
  - Ragas knowledge graph might be the same as the RAG retrieval index.
  - The synthetic test set might be ready to use without human review.
  - Increasing `k` or chunk size might simply make retrieval better without tradeoffs.
  - LangSmith evaluation scores might be ordinary metrics rather than LLM-as-judge feedback.

## Explore
- Concepts encountered:
  - Ragas `KnowledgeGraph`
  - Ragas `Node`
  - graph enrichment
  - serialization/deserialization
  - query synthesizers
  - synthetic test-set generation
  - LangSmith datasets and experiments
  - baseline RAG evaluation
  - LLM-as-judge evaluators
  - answer correctness vs groundedness vs retrieval relevance
  - retrieval depth `k`
  - chunk size and chunk overlap
  - robustness and adversarial test cases
  - root traces vs child runs

- Plain-English explanation:
  - The notebook first builds an evaluation dataset, then uses that dataset to test RAG systems.
  - Ragas takes the cat health PDF, converts page-level documents into graph nodes, enriches those nodes with summaries, embeddings, themes, entities, and relationships, then generates synthetic questions and reference answers.
  - LangSmith stores the reviewed examples and runs experiments where the RAG app answers each question.
  - Evaluators score different parts of the RAG behavior: whether the answer matches the reference, whether it is grounded in retrieved context, and whether retrieval found relevant context.

- Important distinctions:
  - Ragas knowledge graph vs Qdrant vector store:
    - Ragas graph is for generating synthetic test questions.
    - Qdrant vector store is for the actual RAG app retrieval.
  - Node vs JSON:
    - A `Node` is the in-memory data model Ragas can enrich and connect.
    - JSON is the serialized storage format used to save/reload that structure.
  - Correctness vs groundedness:
    - Correctness asks whether the model answer matches the reference answer.
    - Groundedness asks whether the answer is supported by retrieved context.
    - A model can be correct but not grounded if it answers from prior knowledge or luck.
  - Retrieval relevance vs answer quality:
    - Retrieval can find relevant chunks but the answer can still be incomplete.
    - Retrieval can also include extra noisy chunks that lower relevance but still help correctness.
  - Unrolled graph-first path vs one-call Ragas path:
    - Graph-first path exposes graph construction, enrichment, inspection, saving, and reuse.
    - One-call path such as `generate_with_chunks()` is faster to write but hides intermediate graph quality.

- Related tools, APIs, or libraries:
  - `ragas.testset.TestsetGenerator`
  - Ragas query synthesizers:
    - `SingleHopSpecificQuerySynthesizer`
    - `MultiHopSpecificQuerySynthesizer`
    - `MultiHopAbstractQuerySynthesizer`
  - Ragas graph classes:
    - `KnowledgeGraph`
    - `Node`
    - `NodeType`
  - LangChain:
    - `RecursiveCharacterTextSplitter`
    - `ChatPromptTemplate`
    - `ChatOpenAI`
    - `OpenAIEmbeddings`
    - LCEL chain syntax: `prompt | model | parser`
  - Qdrant:
    - `QdrantVectorStore.from_documents`
  - LangSmith:
    - `Client`
    - `evaluate`
    - datasets, examples, experiments, traces, feedback
  - OpenEvals:
    - `create_llm_as_judge`
    - `CORRECTNESS_PROMPT`
    - `RAG_GROUNDEDNESS_PROMPT`
    - `RAG_RETRIEVAL_RELEVANCE_PROMPT`
    - `PROMPT_INJECTION_PROMPT`
    - `HALLUCINATION_PROMPT`
    - `RAG_HELPFULNESS_PROMPT`

- Prerequisite knowledge:
  - Python dictionaries, lists, functions, nested functions, and closures.
  - Pandas dataframe inspection and row filtering.
  - Embeddings and vector search.
  - Basic graph terminology: nodes and relationships/edges.
  - API serialization: Python objects are converted to JSON/text/bytes for storage or network calls.
  - Evaluation concepts: dataset, target function, evaluator, metric, trace.

## Experiment
- Code, notebook, or prompt activity:
  - Mapped the notebook’s end-to-end flow:
    - corpus -> Ragas graph -> synthetic examples -> human review -> LangSmith dataset -> baseline/candidate experiments.
  - Inspected Ragas graph construction:
    - started with `KnowledgeGraph(nodes=20, relationships=0)`.
    - after transforms, nodes gained `summary`, `summary_embedding`, `themes`, `entities`, and relationships.
  - Reviewed relationship examples:
    - `summary_similarity`
    - `entities_overlap`
  - Generated and inspected the synthetic test dataframe:
    - `user_input`
    - `reference_contexts`
    - `reference`
    - `persona_name`
    - `query_style`
    - `query_length`
    - `synthesizer_name`
  - Curated the dataset:
    - kept clear supported examples.
    - removed a weak heartworm multi-hop example because one hop was mostly citation material and the answer came mainly from the second hop.
  - Built baseline RAG:
    - split source documents into 500-character chunks with 75 overlap.
    - embedded chunks.
    - stored them in in-memory Qdrant.
    - created a context-only answer chain with LCEL.
  - Created `make_rag_target()`:
    - accepts `retrieval_k`.
    - retrieves top-k chunks.
    - formats context.
    - invokes the answer chain.
    - returns `answer`, `contexts`, and `retrieval_k`.
  - Ran baseline/candidate experiments:
    - baseline: `k=3`.
    - candidate: `k=6`.
    - third experiment: `chunk_size=900`, `chunk_overlap=150`, `k=3`.
  - Built a new vector store for the chunking experiment:
    - corrected the mistake of accidentally using old `rag_documents`.
    - reused `rag_embeddings` because embedding model did not change.
    - used new `student_documents` because chunking did change.
  - Added robustness cases:
    - prompt injection asking to ignore context.
    - unrelated question.
    - unsafe medication dosing request.
  - Created a custom robustness judge prompt because `ROBUSTNESS_PROMPT` is not built into `openevals.prompts`.
  - Pulled compact trace-style results from LangSmith/CSV and added token fields for cost inspection.

- Prediction before running or reasoning:
  - Increasing `k` from 3 to 6 should improve correctness when useful evidence is missing from the top 3 chunks.
  - Larger chunks should improve local evidence completeness because each retrieved chunk covers more of a section.
  - Larger chunks or higher `k` may increase prompt tokens, latency, and noise.
  - Robustness cases should be tracked separately from normal task performance so a system does not look safe merely by refusing everything.

- Result, error, or observation:
  - `k=6` improved several scores because it retrieved missing supporting chunks, especially for open-ended history-taking questions.
  - Retrieval relevance did not always become perfect because retrieving more chunks can include useful evidence plus loosely related noise.
  - Larger `900/150` chunks improved several examples, especially single-hop and section-local questions.
  - Larger chunks did not fully solve harder multi-hop questions where evidence was spread across distant sections.
  - The robustness prompt-injection and unsafe medication cases scored well.
  - One unrelated-question robustness case scored `0.5` because the expected behavior incorrectly said to recommend consulting a veterinarian for “What is the capital of the moon?” This was a dataset expectation issue, not necessarily an app failure.

- Debugging insight:
  - If a new experiment accidentally uses `rag_documents`, it is not actually testing new chunking.
  - If a helper function closes over the global `vector_store`, a new vector store will not be used unless the target factory accepts the store as a parameter.
  - `rag_embeddings` can be reused when the embedding model is fixed.
  - `student_documents` must be used when the chunking strategy changes.
  - Root traces give one row per example; child runs expose internal retriever/model calls.
  - LLM-as-judge scores reflect the prompt’s expectations, so weak or mismatched expected behavior can produce misleading scores.

- Next small experiment:
  - Try a retrieval strategy designed for multi-hop cases:
    - MMR retrieval
    - reranking
    - parent-child retrieval
    - larger chunks plus `k=4` or `k=5`
  - Keep dataset, evaluator, embedding model, and prompt fixed so the next comparison isolates the changed variable.

## Engineering Connection
- Where this appears in real AI systems:
  - Customer-support RAG systems need curated eval datasets, not just ad hoc manual checks.
  - Medical, legal, finance, or safety-sensitive RAG systems need explicit refusal, insufficient-context, and prompt-injection tests.
  - Production teams compare experiments by changing one variable at a time and watching not only quality scores but also cost, latency, and failure modes.

- Tradeoffs:
  - Higher `k`:
    - Better chance of retrieving missing evidence.
    - Better for some multi-hop questions.
    - More tokens, cost, latency, and noise.
  - Larger chunks:
    - More complete local context.
    - Better section-level answers.
    - Fewer chunks overall, but each retrieved chunk is longer.
    - Can bury the exact answer inside irrelevant surrounding text if too large.
  - One-call Ragas path:
    - Faster developer workflow.
    - Less inspectability.
  - Graph-first Ragas path:
    - More control and debugging.
    - Better for high-impact domains.
    - More code and more intermediate artifacts.

- Failure modes:
  - Synthetic references may be unsupported, duplicated, too broad, or noisy.
  - Multi-hop examples may be weak if only one hop contributes the answer.
  - Retrieved context can be relevant but incomplete.
  - The answer can be grounded but incomplete compared with the reference.
  - The answer can be correct but not grounded.
  - LLM judges can score against a flawed expected behavior.
  - A system can look safe by refusing everything, so normal-task performance and robustness should be measured separately.

- Evaluation or monitoring angle:
  - Track:
    - `answer_correctness`
    - `answer_groundedness`
    - `retrieval_relevance`
    - robustness behavior
    - latency
    - prompt tokens
    - completion tokens
    - total tokens
  - Group failures by:
    - `synthesizer_name`
    - query type
    - case type
    - chunking strategy
    - retrieval depth
  - Inspect traces when metrics disagree.

- Security, data, cost, or deployment concern:
  - Prompt injection can come from user input or retrieved text.
  - Medical RAG systems must not provide unsupported diagnosis or medication dosing.
  - Robustness datasets should include unsafe and unrelated prompts.
  - Higher `k` and larger chunks can improve quality while increasing cost.
  - Dataset curation is part of safety, because bad references create bad evaluations.

## Reflect
- What I understand now:
  - Ragas builds a graph to help generate synthetic test cases; the actual RAG app uses a separate vector store.
  - Graph enrichment includes both node properties and relationships.
  - Query synthesizers generate different question types: single-hop specific, multi-hop specific, and multi-hop abstract.
  - LangSmith evaluation needs target functions and evaluator wrappers because the judge functions need specific fields extracted from LangSmith’s dictionaries.
  - LLM-as-judge metrics can disagree, and disagreement is useful for diagnosis.
  - Chunking and retrieval depth are experimental variables with quality/cost tradeoffs.

- What was unclear:
  - Why Ragas needed `Node` objects before `KnowledgeGraph`.
  - Whether serialized JSON and in-memory nodes were the same thing.
  - Whether personas and query styles were built in or configurable.
  - Why evaluator functions wrapped the judge functions.
  - Whether the new vector store was really using new chunks.
  - Why an unrelated robustness case scored `0.5`.

- Misconception corrected:
  - “Ragas adds chunks” became “Ragas enriches existing chunk nodes and builds relationships between them.”
  - “Overlap score decides how many hops to make” became “overlap is a relationship signal that can help multi-hop generation choose connected chunks.”
  - “Reuse `rag_documents` and `rag_embeddings`” became “reuse `rag_embeddings`, but use `student_documents` when testing new chunking.”
  - “All robustness failures are app failures” became “some robustness failures are flawed expected-behavior definitions.”

- One-minute explanation:
  - This notebook teaches how to build an evaluation loop for RAG. Ragas turns a source PDF into an enriched knowledge graph, then uses that graph to generate synthetic questions and references. A human reviews those examples before uploading them to LangSmith. Then the RAG app is evaluated against the fixed dataset using LLM-as-judge metrics for correctness, groundedness, and retrieval relevance. By changing one variable at a time, such as retrieval depth or chunking, we can diagnose whether performance changes come from better retrieval, better context coverage, or more noise. Finally, robustness cases test whether the app behaves safely under unsafe, unrelated, or adversarial prompts.

- Active recall questions:
  - What is the difference between the Ragas knowledge graph and the Qdrant vector store?
  - Why does Ragas convert LangChain documents into `Node` objects?
  - What properties did graph enrichment add to each node?
  - What is the difference between `summary_similarity` and `entities_overlap` relationships?
  - How are single-hop specific, multi-hop specific, and multi-hop abstract queries different?
  - Why must synthetic examples be reviewed before upload?
  - Why can answer correctness and groundedness disagree?
  - What does the evaluator wrapper do before calling `correctness_judge`?
  - Why did increasing `k` help some examples?
  - Why can increasing `k` hurt retrieval relevance?
  - Why did larger chunks help the open-ended history-taking example?
  - Why did larger chunks not fully solve all multi-hop examples?
  - Why should robustness cases be evaluated separately from normal RAG quality?
  - Why did the “capital of the moon” case score `0.5`?

- Spaced review suggestion:
  - Tomorrow: explain the whole Ragas-to-LangSmith workflow from memory in 5 minutes.
  - In 3 days: rebuild the baseline/candidate comparison without looking at notes.
  - In 1 week: design one new robustness case and one new retrieval experiment, then predict which metric should move and why.

## Post-Task Teaching Debrief
- Approach taken:
  - We started from the big-picture diagram, then walked cell by cell through the notebook. This worked well because the notebook itself is a pipeline: generate test data, review it, upload it, build RAG, evaluate, compare, and harden.

- Roads not taken:
  - A likely shortcut would have been to jump straight to “run all cells.” That would have hidden the key ideas: why the graph exists, why the dataset needs review, and why evaluators disagree.
  - Another shortcut would have been to accept all synthetic examples. You caught that some examples were weak, duplicated, or not truly multi-hop. That is exactly the kind of judgment real evaluation work requires.

- How the pieces connect:
  - Ragas helps create the test set.
  - Human review turns generated examples into trusted eval data.
  - LangSmith stores examples and traces.
  - The RAG target function answers each dataset question.
  - Evaluators score different relationships between question, answer, reference, and retrieved context.
  - Experiment metadata records what changed so the results are interpretable later.

- Tools and methods:
  - Ragas was used for synthetic test-set generation.
  - LangChain LCEL was used for answer generation.
  - Qdrant was used as the vector store.
  - LangSmith was used for experiment tracking.
  - OpenEvals was used for LLM-as-judge prompts.
  - Pandas/CSV/SDK trace inspection were used to make results easier to read.

- Tradeoffs:
  - More context often improves answer quality but costs more.
  - More retrieved chunks improve recall but may reduce precision.
  - Bigger chunks improve local completeness but can include more unrelated text.
  - Generic eval prompts are reusable but may miss domain-specific safety requirements.
  - Custom prompts are more precise but require careful expected behavior definitions.

- Mistakes and dead ends:
  - The chunking experiment initially reused `rag_documents`, which would have invalidated the experiment because it would still use the old chunks.
  - The unrelated robustness expected behavior incorrectly included “recommend consulting a veterinarian,” which penalized a reasonable insufficient-context answer.
  - These are useful mistakes because they show how easy it is for an eval to measure the wrong thing.

- Future pitfalls:
  - Do not compare experiments unless the changed variable is clear.
  - Do not trust aggregate scores without inspecting traces.
  - Do not assume synthetic references are ground truth.
  - Do not treat every low score as a model failure; it may be a dataset or evaluator problem.
  - Do not mix normal quality and safety robustness into one undifferentiated score.

- Expert lens:
  - An experienced AI engineer would immediately ask:
    - Is the dataset valid?
    - Are the metrics measuring the intended behavior?
    - Are failures retrieval failures, generation failures, or evaluator failures?
    - What did the experiment cost?
    - Are safety and normal helpfulness tracked separately?
  - They would also preserve metadata because future diagnosis depends on knowing the source, synthesizer, review status, chunk settings, embedding model, and retrieval depth.

- Transferable lessons:
  - Treat evaluation as a system, not a single score.
  - Use controlled experiments: one variable at a time.
  - Inspect individual traces to understand aggregate metrics.
  - Build robustness datasets intentionally.
  - Always ask whether an eval result reflects the model, the retriever, the dataset, or the judge.
