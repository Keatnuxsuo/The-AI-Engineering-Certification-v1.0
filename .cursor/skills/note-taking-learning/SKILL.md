---
name: note-taking-learning
description: >-
  Creates learning journals, reflection notes, study notes, unclear-concept
  lists, code anchors, post-task teaching debriefs, active recall questions,
  and next experiments from AI tutoring conversations. Use when the user invokes
  /note-taking-learning, asks to reflect on a conversation, create study notes,
  identify unclear concepts, explain roads not taken, preserve key code
  snippets, or apply Plan Explore Experiment Reflect to AI engineering learning.
disable-model-invocation: true
---

# Note-Taking Learning

Convert AI tutoring conversations into durable study notes using Plan, Explore, Experiment, and Reflect. This skill is designed to work alongside `ai-engineering-tutor`.

## Core Goal

Create a learning journal that captures three layers:

- Conceptual: ideas, definitions, distinctions, and mental models.
- Practical: code, APIs, notebooks, errors, debugging signals, and experiments.
- Engineering: system design, evaluation, failure modes, reliability, security, cost, deployment, and production tradeoffs.

Do not merely summarize the conversation. Extract what changed in the learner's understanding, what remains unclear, and what they should test or review next.

## Workflow

1. Identify the learner's original goal and context.
2. Extract concepts, tools, terms, and comparisons discussed.
3. Mine for confusion signals:
   - repeated questions
   - "why", "how", or "what does this mean" questions
   - corrected assumptions
   - vague use of technical terms
   - missing links between concept, code, and real AI systems
   - errors or surprising outputs that revealed a misunderstanding
4. Capture short code anchors when a snippet, API call, error, or data shape is central to the learning.
5. Convert the conversation into a Plan, Explore, Experiment, Reflect journal.
6. For substantial tasks, add a post-task teaching debrief that explains reasoning, alternatives, tradeoffs, mistakes, expert insights, and transferable lessons.
7. End with active recall questions, a small next experiment, and a spaced review suggestion.

## Post-Task Teaching Debrief

Use this deeper debrief after projects, debugging sessions, notebook work, skill creation, architecture decisions, or any task where the reasoning matters as much as the result.

Write like a sharp friend explaining over coffee: plain language, concrete examples, and occasional analogies. Do not sound like a textbook or formal technical documentation.

Cover these points when evidence is available:

- Approach taken: where the work started, what was considered first, and why this path made sense.
- Roads not taken: other approaches considered or implicitly rejected, and why they were weaker for this situation.
- How the pieces connect: how the plan, structure, code, notes, tools, or decisions fit together.
- Tools and methods: what frameworks, APIs, techniques, or workflows were used and what would change if different ones were chosen.
- Tradeoffs: what was prioritized, what was sacrificed, and the cost of each decision.
- Mistakes and dead ends: wrong turns, confusing moments, failed attempts, and how they were corrected.
- Future pitfalls: "I wish someone told me this earlier" warnings for similar work.
- Expert lens: what an experienced engineer, researcher, or practitioner would notice that a beginner might miss.
- Transferable lessons: principles the learner can apply to different projects.

Do not invent hidden reasoning or fake mistakes. If an alternative, tradeoff, or dead end was not visible in the conversation, frame it as "a likely alternative would have been..." or ask a follow-up question.

## Code Anchors

Use code snippets as memory anchors, not as a second codebase inside the journal.

Include a code anchor when it captures:

- the key API call, data shape, or function behavior the learner misunderstood
- a small before/after change that explained the behavior
- a confusing LangGraph state update, retrieval call, evaluator input, or prompt pattern
- a short error message or traceback line that revealed the root cause
- an output example that makes an abstract concept concrete

Keep code anchors short. Prefer 1-8 lines, or a focused excerpt with surrounding explanation. Avoid full notebook cells, full functions, assignment solutions, secrets, API keys, private data, or copied code without explanation.

For each code anchor, explain:

- What this snippet does
- Why this line or pattern matters
- What the learner predicted would happen
- What actually happened
- The reusable rule or debugging lesson

## Output Template

Use this structure unless the user asks for a different format:

```markdown
# Learning Journal

## Plan
- Learning goal:
- Why this matters:
- Learning mode: Concept / Coding / AI Engineering / Mixed
- Prior assumptions:

## Explore
- Concepts encountered:
- Plain-English explanation:
- Important distinctions:
- Related tools, APIs, or libraries:
- Prerequisite knowledge:

## Experiment
- Code, notebook, or prompt activity:
- Code anchor, if useful:
- Why the snippet matters:
- Prediction before running or reasoning:
- Result, error, or observation:
- Debugging insight:
- Next small experiment:

## Engineering Connection
- Where this appears in real AI systems:
- Tradeoffs:
- Failure modes:
- Evaluation or monitoring angle:
- Security, data, cost, or deployment concern:

## Reflect
- What I understand now:
- What was unclear:
- Misconception corrected:
- One-minute explanation:
- Active recall questions:
- Spaced review suggestion:
```

## Learning Psychology

Apply these principles when shaping the notes:

- Active recall: turn important ideas into questions future-you can answer without looking.
- Self-explanation: include a short explanation in the learner's own words when possible.
- Elaborative interrogation: ask why the idea works and when it fails.
- Desirable difficulty: include one small challenge that requires effort, not rereading.
- Interleaving: compare nearby concepts such as embedding search vs keyword search, retrieval evaluation vs generation evaluation, or LangChain chains vs LangGraph state machines.
- Spaced repetition: suggest when to revisit difficult concepts, such as tomorrow, in three days, or next week.

## Quality Bar

A concept is not "learned" just because it was mentioned. For each important concept, capture at least one of:

- a plain-English explanation
- a short code anchor or API behavior described in words
- a failure mode or common mistake
- an active recall question
- a next experiment

Keep the output honest. If the conversation does not contain enough evidence to infer the learner's understanding, say what is missing and ask a short follow-up question.

## Saving Notes

Do not create files automatically. Ask the user to verify the content first. Only output the journal in chat unless the user explicitly asks to save it.

When saving is requested, prefer a scalable learning-journal path such as `learning-journal/YYYY-MM-DD-topic.md` over a single catch-all file. 

## Boundaries

- Follow `.cursor/rules/teaching-mode.mdc`; do not complete assignments or write full learner solutions.
- Prefer reflection prompts, pseudocode-level experiments, and debugging questions over copy-paste code.
- When paired with `ai-engineering-tutor`, preserve the tutor's emphasis on durable understanding, CS foundations, and guided learning.
