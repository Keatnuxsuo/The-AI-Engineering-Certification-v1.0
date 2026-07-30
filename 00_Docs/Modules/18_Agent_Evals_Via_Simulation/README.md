# Session 18: 👩‍🚀 Agent Evals via Simulation

🎯 Learn the state-of-the-art in evaluating agent performance

📚 **Learning Outcomes**

- Understand how SDG can be used to simulate user interactions, and what tools leverage this approach today
- Understand how lessons from classic experiment tracking in ML and MLOps are making their way into agent evaluation via AgentOps

## 📛 Required Tooling & Account Setup

- No new tools or accounts are required today

## 📜 Recommended Reading

- [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), by Anthropic (Jan 2026)
- [Evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts), by LangChain

## 🗺️ Session Overview

We saw with RAG evaluation how it scores a single answer. Agents are harder — they choose tools, chain steps, recover from bad results, and should decline what they can't do. You can't measure that with one question and one answer; you have to simulate the conversation and inspect the whole trajectory.

For this we'll need to generate synthetic test tasks by composing atomic pieces (the "infinity DAG"), run each one as a simulated multi-turn dialogue between a fake user and the agent, and verifies the resulting trajectory — then roll it up into a capability profile you can track release over release.

---

## How it borrows from τ²-bench

[τ²-bench](https://huggingface.co/papers/2506.07982) (Sierra) evaluates agents with three ideas we adopt in miniature: a **compositional task generator** that builds verifiable tasks from atomic parts, a **user simulator** coupled to the environment so trajectories are multi-turn and realistic, and **programmatic verification** of the outcome rather than vibes. We keep the spirit and shrink it to one corpus and one afternoon.

---

Do you have any questions about how to best prepare for this session after reading? Please don't hesitate to provide direct feedback to jacob@aimakerspace.io or Jacops on Discord!
