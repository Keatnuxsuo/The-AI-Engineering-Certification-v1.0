# Learning Journal: Agentic RAG And Agent Evaluation

## Plan
- Learning goal: Understand Session 6 RAG and agent evaluation workflows using Ragas, LangGraph, LangChain tools, Vercel AI Gateway, and early regression-suite design.
- Why this matters: Production AI systems need evaluation beyond "it seemed to answer well." You need to know whether retrieval worked, whether answers were grounded, whether tools were called correctly, and whether scope guardrails behaved as intended.
- Learning mode: Mixed: concept, notebook debugging, AI engineering, evaluation design.
- Prior assumptions: I initially expected Ragas to expose a visible knowledge graph directly in the notebook, and expected LangSmith tracing to appear once variables were set.

## Explore
- Concepts encountered:
  - Ragas synthetic test generation and hidden `KnowledgeGraph`
  - LangGraph state passing
  - RAG metrics: `context_recall`, `faithfulness`, `answer_accuracy`, `context_entity_recall`, `noise_sensitivity`
  - MMR retrieval and `k` vs `fetch_k`
  - Agent/tool evaluation: `ToolCallAccuracy`, `AgentGoalAccuracyWithReference`, `TopicAdherence`
  - Normalized traces: LangChain messages converted into Ragas messages
  - Regression suites using JSONL cases
  - LangSmith tracing vs local latency/cost reporting

- Plain-English explanation:
  - RAG evaluation asks: "Did we retrieve the right evidence, and did the model answer from it?"
  - Agent evaluation asks: "Did the agent choose the right tool, use the result correctly, and stay within product boundaries?"
  - A trace is the evidence trail: human message, AI tool request, tool output, final answer.
  - A normalized trace means the thing I manually inspect is the same thing the metric scores.

- Important distinctions:
  - `reference_contexts`: Ragas/source-side expected context.
  - `retrieved_contexts`: my RAG system's actual retrieved chunks.
  - `response`: my RAG system's answer.
  - `reference`: expected/reference answer.
  - `ToolCallAccuracy`: did the agent call the expected tool with expected args?
  - `AgentGoalAccuracy`: did the whole interaction accomplish the goal?
  - `TopicAdherence` precision: did the agent avoid answering out-of-scope topics?
  - `k`: final number of chunks returned.
  - `fetch_k`: candidate pool size before MMR selects diverse chunks.
  - Tool schema: shape of one tool's input arguments, not the number of times the tool is called.

- Related tools, APIs, or libraries:
  - LangGraph `StateGraph`, `ToolNode`, `add_messages`
  - LangChain `AIMessage.tool_calls`
  - Ragas `RagasToolCall`, `RagasAIMessage`, `ToolCallAccuracy`, `TopicAdherence`
  - PyVis for visualizing Ragas `KnowledgeGraph`
  - LangSmith tracing, `traceable`, projects, environment variables
  - Vercel AI Gateway as the unified model endpoint

- Prerequisite knowledge:
  - Python dictionaries vs objects and attributes
  - JSONL structure
  - Async function wrappers
  - Basic dataframe reporting
  - Tool calling lifecycle: model requests tool call, runtime executes tool, model observes tool result

## Experiment
- Code, notebook, or prompt activity:
  - Visualized the Ragas `KnowledgeGraph` via PyVis.
  - Reviewed synthetic test rows manually before scoring.
  - Compared baseline similarity retrieval against MMR.
  - Built a custom MMR experiment with larger `k`.
  - Converted LangChain traces to Ragas message format.
  - Evaluated tool-call accuracy and agent goal accuracy.
  - Designed a JSONL eval dataset for metal-agent regression cases.
  - Began a reusable runner: JSONL case -> agent run -> Ragas trace -> metric row.
  - Attempted LangSmith tracing and identified setup friction.

- Code anchors:
  - LangGraph state handoff in the RAG graph:

    ```python
    def retrieve(state: RAGState):
        return {"context": retriever.invoke(state["question"])}

    def generate(state: RAGState):
        context_text = "\n\n".join(
            document.page_content for document in state["context"]
        )
    ```

    What this does: `retrieve()` writes retrieved documents into the graph state under `"context"`, and `generate()` reads that same state key later.

    Why it matters: this corrected the confusion about how `generate()` "knows" about retrieved context. The reusable rule is: LangGraph nodes do not need to call each other directly; they pass data through state updates.

  - Agent routing based on tool-call requests:

    ```python
    def should_continue(state: AgentState):
        last_message = state["messages"][-1]
        return "tools" if getattr(last_message, "tool_calls", []) else END
    ```

    What this does: after the assistant responds, the graph checks whether the latest AI message requested any tool calls. If yes, it routes to `ToolNode`; otherwise, the graph ends.

    Why it matters: this clarified the difference between an AI message that requests a tool call and the tool message that contains the executed result.

  - Ragas knowledge graph location:

    ```python
    kg = testset_generator.knowledge_graph
    len(kg.nodes), len(kg.relationships)
    ```

    What this does: accesses the intermediate Ragas graph after `generate_with_chunks(...)` has run.

    Why it matters: the final `synthetic_testset` is not the graph. Ragas stores the enriched graph on the generator object, which explained why there was no obvious `knowledge_graph` variable in the notebook.

  - Tool-call references come from the JSONL expected field:

    ```python
    def reference_tool_calls_from_case(case):
        return [
            RagasToolCall(
                name=tool_call["name"],
                args=dict(tool_call.get("args") or {}),
            )
            for tool_call in case["reference_tool_calls"]
        ]
    ```

    What this does: converts expected tool-call dictionaries from the JSONL case into Ragas `ToolCall` objects.

    Why it matters: `case["messages"]` contains only the user input transcript. Expected tool calls live in `case["reference_tool_calls"]`. Actual tool calls only exist after the agent runs and produces a trace.

  - One-case runner shape:

    ```python
    messages = run_case(agent, case)
    trace = to_ragas_messages(messages)
    reference_tool_calls = reference_tool_calls_from_case(case)
    ```

    What this does: runs one case through one agent, converts the resulting conversation into a Ragas trace, and prepares the expected tool calls.

    Why it matters: this separated one-case scoring from many-case looping. The reusable rule is: make the inner function handle one case cleanly, then use an outer loop to run the whole JSONL suite.

- Prediction before running or reasoning:
  - Increasing MMR diversity might improve entity coverage but add noise.
  - Guarded prompt should improve scope safety.
  - Multiple tool calls should pass tool-call accuracy if expected calls match the actual tool input schema.

- Result, error, or observation:
  - Ragas `KnowledgeGraph` existed at `testset_generator.knowledge_graph`, but raw visualization looked sparse because it had 7 chunk nodes and only 1 relationship.
  - Baseline RAG scores were high, but `context_entity_recall` was weaker.
  - MMR with many retrieved chunks hurt faithfulness, answer accuracy, and noise sensitivity.
  - Tool-call accuracy dropped when expected args included `unit`, because the actual tool schema only accepted `metal_name`.
  - Topic-adherence precision improved from baseline to guarded because guarded refused investment advice.
  - LangSmith project could be created, but notebook traces did not reliably appear; local timing is a reasonable fallback.

- Debugging insight:
  - `case["messages"]` is only the input transcript from JSONL.
  - `case["reference_tool_calls"]` contains expected tool calls.
  - Actual tool calls only exist after running the agent and converting the trace.
  - A function should score one case; an outer loop should run many cases.
  - `agent_name` is just a label; `agent` is the executable graph object.

- Next small experiment:
  - Run the first 3 JSONL cases through both `baseline_agent` and `guarded_agent`.
  - Return a dataframe with `case_name`, `agent_name`, `tool_call_accuracy`, `num_expected_tool_calls`, `num_actual_tool_calls`, `latency_seconds`, and `cost_usd=None`.

## Engineering Connection
- Where this appears in real AI systems:
  - RAG systems need retrieval and generation evals before deployment.
  - Tool agents need trace-level testing because the final answer can look fine while tool use is wrong, or tool use can be right while the final answer is wrong.
  - Scope safety matters for narrow products: a metal-price assistant should not become a financial advisor.

- Tradeoffs:
  - More retrieved chunks can improve coverage but increase cost, latency, and noise.
  - Smaller judge models are cheap and fast but may be less reliable for nuanced evaluation.
  - Guardrails improve safety but can reduce helpfulness if they refuse adjacent valid tasks.
  - JSONL local evals are simple and versionable; LangSmith datasets are more structured but add setup complexity.

- Failure modes:
  - Synthetic test data can be too clean and make a RAG system look better than it is.
  - Ragas metric scores can mislead if references are weak or if judge models are inconsistent.
  - Expected tool calls can be wrong if they do not match the real tool schema.
  - Tracing setup can silently fail if environment variables are set after clients/agents are created.
  - Visualizing raw graph objects may not produce an intuitive "knowledge graph."

- Evaluation or monitoring angle:
  - Use deterministic checks for tool name/args.
  - Use LLM-as-judge for goal completion and topic adherence.
  - Add human review for safety-sensitive boundaries.
  - Report latency beside quality scores.
  - Track cost when token usage or provider observability is available.

- Security, data, cost, or deployment concern:
  - API keys should use `getpass()` or env vars, not hardcoded values.
  - Evaluation runs can become costly because generation, judging, and tracing all add calls.
  - In CI, use small curated regression sets and threshold-based checks rather than exact LLM scores.

## Reflect
- What I understand now:
  - Ragas testset generation creates an intermediate knowledge graph, but the notebook stores it on the generator, not as the final testset.
  - LangGraph nodes communicate through shared state.
  - Tool calls are requested by the AI message and executed by `ToolNode`.
  - Ragas compares actual normalized traces against references.
  - A reusable eval runner should separate one-case execution from many-case looping.

- What was unclear:
  - Where Ragas' knowledge graph lived.
  - Why `generate()` could access retrieved context.
  - Difference between `reference_contexts` and `retrieved_contexts`.
  - Difference between tool schema and multiple tool calls.
  - Why an `agent_name` string is useful when the actual agent object already exists.
  - Why LangSmith tracing did not appear automatically.

- Misconception corrected:
  - `baseline_graph` was not the Ragas document knowledge graph; it was a LangGraph RAG pipeline.
  - `message.tool_calls` exists on actual AI messages after execution, not in JSONL input messages.
  - Adding `"unit": "g"` to expected tool calls was wrong because the tool input schema did not include `unit`.
  - More retrieval is not automatically better.

- One-minute explanation:
  - In this session, I learned how to evaluate both RAG and tool agents. For RAG, Ragas checks whether retrieved chunks contain the right evidence and whether the answer is accurate and faithful. For agents, Ragas scores the normalized trace: what the user asked, what tool the model requested, what the tool returned, and what the model answered. A good regression suite stores cases in JSONL, runs each case through the agent, converts the trace, scores it, and records quality plus latency/cost. The key is to compare the actual trace against a clearly defined expected behavior.

- Active recall questions:
  - What is the difference between `reference_contexts` and `retrieved_contexts`?
  - Why can tool-call accuracy be `1.0` while agent-goal accuracy is low?
  - Why should expected tool calls match the tool input schema, not the tool output?
  - What is the difference between MMR `k` and `fetch_k`?
  - Why can increasing retrieval `k` hurt answer quality?
  - What does `TopicAdherence(mode="precision")` measure?
  - Why do we need both `agent` and `agent_name` in an eval runner?
  - What should happen before moving a notebook eval into CI?

- Spaced review suggestion:
  - Tomorrow: Rebuild the JSONL eval runner from memory for 3 cases.
  - In 3 days: Explain all five RAG metrics without looking.
  - Next week: Convert the notebook runner into a small Python script and add a threshold check.
