# Learning Journal: Agentic RAG, Middleware, And LangGraph Control Flow

## Plan
- Source notebook: `02_Agentic_RAG_LangGraph_LangChain/01_Cat_Health_Agentic_RAG_LangGraph_LangChain.ipynb`
- Learning goal: Understand the Session 2 Cat Health Agentic RAG notebook end to end, especially how retrieval becomes a tool, how middleware observes and constrains the agent loop, and how explicit LangGraph exposes control flow.
- Why this matters: Production RAG agents are not just "retrieve then answer" pipelines. They decide when to retrieve, execute tools, inspect intermediate state, enforce budgets, route out-of-scope questions, and sometimes grade retrieval quality before answering.
- Learning mode: Mixed: concept, coding, debugging, LangGraph graph design, and AI engineering tradeoffs.
- Prior assumptions:
  - I expected stream chunks to have the same shape across stream modes.
  - I initially treated Python dicts that look like JSON as if they were JSON.
  - I thought middleware was mostly logging and call limits, but it is a broader extension layer.
  - I mixed up LangGraph nodes and routers when building conditional control flow.

## Explore
- Concepts encountered:
  - Agentic RAG vs fixed RAG pipeline
  - Retriever tool contracts: function name, docstring, typed input, formatted output
  - LangChain `create_agent`
  - Middleware hooks: `before_model`, model-call limits, tool-call limits
  - `stream_mode="updates"` vs `stream_mode="values"`
  - LangGraph `StateGraph`, `MessagesState`, `ToolNode`, `tools_condition`
  - Message history growth across model/tool/model loops
  - Deterministic routing before an agent loop
  - Tool-call budgets and graceful degradation
  - Basic retrieval quality grading after tool execution

- Plain-English explanation:
  - In fixed RAG, retrieval always happens before the model answers.
  - In agentic RAG, retrieval is a tool. The model decides whether to call it.
  - The agent loop is a conversation that grows: user question, AI tool request, tool result, final AI answer.
  - Middleware wraps or observes the existing loop. Explicit LangGraph changes the loop itself.
  - LangGraph state is the shared memory between nodes. Nodes do not call each other directly; they return state updates, and edges decide what runs next.

- Important distinctions:
  - Python dict vs JSON: the notebook input shape looks JSON-like, but it is an in-memory Python dict until the model API serializes it.
  - `updates` stream mode: each chunk is shaped like `{node_name: state_update}`.
  - `values` stream mode: each chunk is the whole state, shaped like `{"messages": [...]}`.
  - Node vs router:
    - A node returns a state update dict.
    - A router returns the name of the next node.
  - Middleware vs graph edits:
    - Middleware is for cross-cutting behavior like logging, limits, retries, redaction, and guardrails.
    - Graph edits are for new control flow like deterministic routing, grading, rewriting, and custom fallback paths.

- Related tools, APIs, or libraries:
  - LangChain `create_agent`
  - LangChain middleware: `@before_model`, `ModelCallLimitMiddleware`, `ToolCallLimitMiddleware`
  - LangChain tool decorator: `@tool`
  - LangGraph `StateGraph`, `MessagesState`, `ToolNode`, `tools_condition`, `START`, `END`
  - LangChain message types: `AIMessage`, `ToolMessage`, `SystemMessage`
  - Qdrant vector store through `QdrantVectorStore`

- Prerequisite knowledge:
  - Python dicts, lists, indexing, and `.get()`
  - Generator/iterator behavior in streaming
  - Basic graph vocabulary: nodes, edges, conditional edges
  - How LLM tool calling works: the model emits a structured tool request, the runtime executes the Python function, and the tool result is appended as a message

## Experiment
- Code, notebook, or prompt activity:
  - Traced `print_agent_stream()` for cat-health and unrelated questions.
  - Compared `stream_mode="updates"` and `stream_mode="values"` and debugged shape mismatches.
  - Interpreted middleware output showing model call counts and message history growth.
  - Added a `ToolCallLimitMiddleware` budget for the retriever tool.
  - Built deterministic scope routing with an `out_of_scope` node.
  - Tested clear cat-health, clear unrelated, and ambiguous questions.
  - Started an optional advanced graph with a simple `grade_retrieval` node after the tools node.

- Code anchors:

  ```python
  inputs = {"messages": [{"role": "user", "content": question}]}
  ```

  What this does: creates the initial LangGraph state with one user message.

  Why it matters: this is not JSON. It is a Python dict that matches the graph state schema. LangChain later normalizes the inner dict into a message object.

  Reusable rule: inside Python, work with Python objects; serialize to JSON only when crossing a boundary like an HTTP API.

  ```python
  for chunk in agent.stream(inputs, stream_mode="updates"):
      for node_name, update in chunk.items():
          ...
  ```

  What this does: streams node-level updates from the compiled graph.

  Why it matters: `updates` mode produces `{node_name: update}` chunks. When this was changed to `values`, the code broke because `values` mode produces the whole state directly.

  Debugging insight: inspect the data shape before indexing it. A `KeyError` or `'list' object has no attribute 'get'` often means the object shape is different from the code's assumption.

  ```python
  [HumanMessage, AIMessage(tool_calls=[...]), ToolMessage(...)]
  ```

  What this represents: the message history after the first model call and tool execution.

  Why it matters: the second model call sees the retrieved context because the tool result is appended to conversation state. The model API itself is stateless; the graph state carries the memory.

  Reusable rule: agent "memory" during one run is usually just accumulated messages passed into the next model call.

  ```python
  ToolCallLimitMiddleware(
      tool_name=retriever_tool.name,
      run_limit=1,
      exit_behavior="continue",
  )
  ```

  What this does: allows only one call to the retriever tool per run.

  Why it matters: the model attempted two searches for a multi-part question. The middleware allowed one and returned a synthetic `ToolMessage` saying the tool-call limit was exceeded for the other.

  Result: the model answered the urinary part from retrieved context and refused to fully answer the preventive-care part because the second retrieval was blocked.

  ```python
  advanced_builder.add_conditional_edges(
      "grade_retrieval",
      route_after_grade,
      {
          "agent": "agent",
          "out_of_scope": "out_of_scope",
      },
  )
  ```

  What this does: after the `grade_retrieval` node runs, LangGraph calls `route_after_grade(state)` and maps its returned label to the next node.

  Why it matters: without the explicit route map, the compiled graph visualization did not show the expected `grade_retrieval -> agent/out_of_scope` paths.

  Reusable rule: for conditional edges, the router returns a label; the mapping tells LangGraph which node that label means.

- Prediction before running or reasoning:
  - Cat-health questions should call retrieval.
  - Unrelated questions should not call retrieval.
  - A budgeted retriever should reduce cost but may reduce completeness.
  - A deterministic route should save model calls for obvious out-of-scope questions but may misclassify ambiguous ones.

- Result, error, or observation:
  - Urinary and preventive-care questions both called the retrieval tool, but with different rewritten search queries and different relevant chunks.
  - The World Cup question produced one model call, no tool call, and a scope refusal.
  - With the retriever budget set to one call, the model tried two tool calls in one `AIMessage`; one returned retrieved chunks and the other returned the limit-exceeded synthetic tool result.
  - The ambiguous "pet lives under water" question routed to the agent because the keyword router was broad, but the agent refused without retrieving.
  - The advanced retrieval grader appeared only when the graph actually ran through `tools`; unrelated questions that the agent refused directly never reached `grade_retrieval`.

- Debugging insight:
  - Notebook state can be stale. Editing a cell does not update functions or compiled graphs until the cell is rerun.
  - Visualizing the compiled graph with Mermaid is a powerful debugging tool. The code looked plausible, but the Mermaid graph revealed missing conditional routes.
  - If the stream path is `agent -> tools -> agent`, the base graph is running. If the advanced graph is wired correctly, the path should be `agent -> tools -> grade_retrieval -> agent`.

- Next small experiment:
  - Replace the heuristic grader with a semantic grader that asks an LLM whether the retrieved context answers the user's question.
  - Add a `retrieval_attempts` field and retry once with a rewritten query when the grade is weak.
  - Add a final guardrail node that checks whether cat-health answers include sources and a veterinarian disclaimer.

## Engineering Connection
- Where this appears in real AI systems:
  - Customer support agents that decide whether to search docs before answering.
  - Medical, legal, or financial assistants that must answer only from trusted retrieved sources.
  - Production agents with tool budgets, rate limits, and observability.
  - RAG systems that use routing, query rewriting, quality checks, and final-answer guardrails.

- Tradeoffs:
  - Retrieval as a tool saves cost and avoids irrelevant context, but relies on the model choosing the tool correctly.
  - Middleware budgets control spend and runaway behavior, but can reduce answer completeness for multi-part or high-impact questions.
  - Deterministic routing is fast and cheap, but brittle. Narrow keyword routes reject valid questions; broad routes send irrelevant questions to the model.
  - A simple heuristic grader is easy to debug, but it checks whether sources exist, not whether they are semantically relevant.

- Failure modes:
  - The model may skip retrieval when retrieval was needed.
  - The model may call retrieval for unrelated questions if the prompt/tool contract is too broad.
  - A tool-call budget may block the second half of a multi-part question.
  - A keyword router may misclassify ambiguous wording like "my pet."
  - A weak grader that only checks for `[Source` may mark irrelevant retrieved chunks as good.
  - A graph can compile differently from what the code author expected if conditional edge mappings are missing.

- Evaluation or monitoring angle:
  - Inspecting the final answer is not enough. The trace matters: Was a tool called? What query did the model generate? What chunks came back? Did a budget or router change behavior?
  - Stream output is a lightweight form of observability. LangSmith tracing would be the production-grade version.
  - Useful metrics later would include tool-call accuracy, topic adherence, context relevance, faithfulness, and answer completeness.

- Security, data, cost, or deployment concern:
  - Tool contracts and system prompts act as policy boundaries, but they are not perfect enforcement.
  - High-impact domains need conservative refusal behavior when retrieved context is insufficient.
  - Cost controls like tool-call limits and model-call limits should be paired with quality monitoring because saving calls can reduce answer quality.
  - Deterministic guards are cheap and predictable, but should be tested against edge cases and ambiguous phrasing.

## Reflect
- What I understand now:
  - Retrieval becoming a tool means the model decides whether to search.
  - Tool calls are not magic Python calls by the model. The model emits a structured request, and the runtime executes the tool.
  - Message history grows during the loop, and the retrieved context becomes a `ToolMessage`.
  - Middleware can observe and constrain the loop without changing its basic shape.
  - Explicit LangGraph makes nodes, edges, loops, and conditional routes visible and editable.
  - A graph node and a router are different: nodes write state, routers choose the next node.

- What was unclear:
  - Why model calls went from 1 message to 3 messages.
  - Why `stream_mode="values"` broke code that worked with `updates`.
  - Why `chunk["messages"]` failed in `updates` mode.
  - How to pass middleware lists without nesting lists.
  - Why the `grade_retrieval` node did not appear until the correct graph/helper was rerun and visualized.

- Misconception corrected:
  - A JSON-looking Python dict is not JSON.
  - `values` and `updates` stream modes do not have the same chunk shape.
  - `ToolCallLimitMiddleware` needs a tool name string such as `retriever_tool.name`, not the tool object itself.
  - A compiled graph is not automatically updated when the builder code changes in a notebook.
  - Returning `"agent"` from a normal node is wrong; that is router behavior.

- One-minute explanation:
  - This notebook turns RAG into an agent loop. The model receives a user question and a retriever tool. If the question is about cat health, the model emits a tool call with a search query. LangGraph executes the tool, appends the retrieved chunks as a `ToolMessage`, and calls the model again so it can answer from that context. Middleware can log or limit the loop. Explicit LangGraph lets me change the route, such as bypassing unrelated questions or grading retrieved context before answering.

- Active recall questions:
  - What is the difference between `stream_mode="updates"` and `stream_mode="values"`?
  - Why does the second model call see 3 messages after one tool call?
  - What does the model actually emit when it wants to call a tool?
  - Why does `ToolCallLimitMiddleware(..., exit_behavior="continue")` still let the model finish?
  - When should I use middleware instead of changing the graph?
  - What is the difference between a LangGraph node and a router function?
  - Why did the Mermaid graph help debug the missing `grade_retrieval` route?
  - What does my current retrieval grader check, and what does it fail to check?

- Spaced review suggestion:
  - Tomorrow: redraw the basic agentic RAG loop from memory: `agent -> tools -> agent`.
  - In three days: re-implement a tiny graph with one router and one fallback node without looking.
  - Next week: add a semantic retrieval grader and one retry with a rewritten query, then compare traces against the simple heuristic grader.

## Post-Task Teaching Debrief
- Approach taken:
  - The learning started with understanding the notebook's existing `create_agent` loop and stream helper. Then it moved from observation to control: middleware budgets, explicit LangGraph routing, and finally a basic advanced retrieval-quality checkpoint.

- Roads not taken:
  - A full semantic grader and query-rewrite loop were not completed yet. That was the right restraint because the node-vs-router distinction and compiled graph debugging needed to be solid first.
  - A hardcoded all-in-one advanced graph was avoided because debugging multiple new features at once would hide which concept was failing.

- How the pieces connect:
  - The retriever tool is the shared capability.
  - `create_agent` hides the agent loop but makes it easy to run.
  - Middleware wraps that loop for logging and budgets.
  - Explicit LangGraph exposes the loop so new nodes and conditional edges can be added.
  - The advanced graph inserts `grade_retrieval` after `tools`, proving that retrieval quality control is a graph-level concern.

- Tools and methods:
  - Stream traces were used as the main debugging method.
  - Mermaid graph visualization was used to verify actual compiled control flow.
  - Short code anchors clarified data shapes and API behavior.

- Tradeoffs:
  - The notebook favors inspectability over abstraction in the explicit LangGraph section.
  - The simple grader is easy to understand but not robust.
  - The deterministic scope router saves cost on obvious unrelated questions, but its quality depends entirely on the keyword list.

- Mistakes and dead ends:
  - `stream_mode="values"` was used with code written for `updates`, causing shape errors.
  - Middleware was accidentally nested as `[agent_middleware, retrieval_budget]` instead of flattened.
  - `tool_name` was confused with the tool object rather than the tool name string.
  - `AdvancedState` was initially treated like a message type rather than a graph state type.
  - Conditional routing from `grade_retrieval` needed an explicit mapping to show the intended edges.

- Future pitfalls:
  - Always check whether a helper streams from the graph you think it streams from.
  - Always rerun graph-build cells after changing edges.
  - Always visualize compiled graphs when routes look wrong.
  - Do not treat a retrieval result as relevant just because vector search returned something.

- Expert lens:
  - An experienced engineer would focus on traces, not just final answers.
  - They would separate policy, capability, and control flow:
    - Policy: system prompt and guardrails.
    - Capability: retriever tool.
    - Control flow: LangGraph nodes and edges.
  - They would also evaluate cost-saving mechanisms against answer quality, especially in high-impact domains like health.

- Transferable lessons:
  - When a library returns structured data, inspect the shape before writing indexing logic.
  - Keep baseline and experimental graphs separate.
  - Start with one graph modification, test it, then add the next.
  - Use visualizations and traces as debugging artifacts, not just pretty outputs.
