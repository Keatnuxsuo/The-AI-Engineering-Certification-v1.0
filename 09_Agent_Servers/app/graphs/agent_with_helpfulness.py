from __future__ import annotations

from langgraph.graph import END, START, StateGraph, MessagesState
from langchain_core.messages import HumanMessage, SystemMessage
from app.models import get_chat_model
from app.tools import get_tool_belt
from langchain.agents import create_agent

MAX_ATTEMPTS = 3  # the safety valve so the loop can't run forever


class State(MessagesState):
    attempts: int
    helpfulness: str


# The inner agent (reuses your model + tool belt) — same idea as simple_agent.py
_agent = create_agent(
    model=get_chat_model(),
    tools=get_tool_belt(),
    system_prompt= "You are a helpful assistant specialized in feline (cat) health. "
    "Use the retrieve_information tool for cat-health questions, web search for "
    "current information, and Arxiv for research papers. Cite tool results when "
    "they inform your answer."
)


def agent_node(state: State) -> dict:
    # TODO:
    # 1. run the inner agent on the current messages:  _agent.invoke({"messages": state["messages"]})
    result = _agent.invoke({"messages": state["messages"]})
    # 2. grab the agent's messages from the result
    messages = result.get("messages", [])
    # 3. return them AND bump the counter:
    return {"messages": messages, "attempts": state.get("attempts", 0) + 1}


def judge_node(state: State) -> dict:
    # TODO:
    # 1. find the user's original question + the agent's latest answer in state["messages"]
    user_message = state["messages"][0] 
    agent_message = state["messages"][-1]
    # 2. ask a judge model to reply with EXACTLY "Y" or "N" (constrain it in the prompt)
    judge_model = get_chat_model()
    judge_result = judge_model.invoke([
        SystemMessage(content="You judge whether the answer helpfully addresses the question. Reply with EXACTLY one character: Y or N."),
        HumanMessage(content=f"User question: {user_message.content}\n\nAgent answer: {agent_message.content}"),
    ])
    # 3. return {"helpfulness": "Y" or "N"}
    return {"helpfulness": judge_result.content.strip().upper()}
    

def route(state: State) -> str:
    # TODO (return the NAME of the next node):
    # - if helpfulness is "Y"          -> END
    if state["helpfulness"] == "Y":
        return END
    # - if attempts >= MAX_ATTEMPTS    -> END   (safety valve)
    if state["attempts"] >= MAX_ATTEMPTS:
        return END  
    # - otherwise                      -> "agent"
    return "agent"


# --- wire the graph (this order matters) ---
builder = StateGraph(State)
builder.add_node("agent", agent_node)
builder.add_node("judge", judge_node)
builder.add_edge(START, "agent")
builder.add_edge("agent", "judge")
builder.add_conditional_edges("judge", route, {"agent": "agent", END: END})

graph = builder.compile()