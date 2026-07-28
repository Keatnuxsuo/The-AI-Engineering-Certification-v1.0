// Chat UI: many conversations, each mapped to its own agent session server-side,
// with the agent's progress streamed in as it works.
//
// The server needs no conversation list: POST /api/chat/stream accepts any
// conversation_id and keeps its own id -> SDK session map. So all of this is local —
// the browser owns the transcripts, the server owns the agent memory.

const STORAGE_KEY = "chat-app.conversations.v1";
const TITLE_MAX = 40;

const RESET_NOTICE =
  "The server restarted, so this conversation's memory was reset. " +
  "Earlier messages are still shown here, but the agent no longer remembers them.";

const messagesEl = document.getElementById("messages");
const formEl = document.getElementById("composer");
const inputEl = document.getElementById("input");
const sendEl = document.getElementById("send");
const listEl = document.getElementById("conversations");
const newChatEl = document.getElementById("new-chat");

/**
 * conversations: [{ id, title, messages: [{ role, text }], pending, streaming, activity }]
 * role is one of "user" | "assistant" | "error" | "notice".
 * `streaming` and `activity` are transient stream state, never meaningful after a reload.
 */
let state = { activeId: null, conversations: [] };

function blankConversation() {
  return {
    id: crypto.randomUUID(),
    title: "",
    messages: [],
    pending: false,
    streaming: "",
    thinking: "",
    tools: [],
  };
}

/** Reset the transient stream state on a conversation. */
function clearStreamState(conversation) {
  conversation.streaming = "";
  conversation.thinking = "";
  conversation.tools = [];
}

function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    if (parsed && Array.isArray(parsed.conversations) && parsed.conversations.length) {
      state = parsed;
      // A request in flight when the page closed can never resolve, so no conversation
      // should come back from storage still pending or half-streamed.
      state.conversations.forEach((conversation) => {
        conversation.pending = false;
        clearStreamState(conversation);
      });
      if (!byId(state.activeId)) state.activeId = state.conversations[0].id;
      return;
    }
  } catch {
    // Corrupt or unreadable storage is not worth failing over — start clean.
  }
  const first = blankConversation();
  state = { activeId: first.id, conversations: [first] };
}

function save() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Quota or private-mode failures shouldn't break the chat.
  }
}

function byId(id) {
  return state.conversations.find((conversation) => conversation.id === id);
}

function active() {
  return byId(state.activeId);
}

function titleOf(conversation) {
  if (conversation.title) return conversation.title;
  return conversation.messages.length ? "Untitled" : "New conversation";
}

// --- SSE parsing -----------------------------------------------------------------
// The browser's EventSource would do this for us, but it only issues GET requests and
// this endpoint is a POST, so we read the body ourselves.

/** Yield {event, data} objects from an SSE response body. */
async function* readFrames(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Frames are separated by a blank line. Whatever trails the last separator is an
    // incomplete frame — keep it buffered until the rest of it arrives.
    const parts = buffer.split("\n\n");
    buffer = parts.pop();
    for (const part of parts) {
      const frame = parseFrame(part);
      if (frame) yield frame;
    }
  }
}

function parseFrame(raw) {
  let event = "message";
  const dataLines = [];

  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }

  if (!dataLines.length) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return null; // a frame we can't read is better skipped than fatal
  }
}

function applyFrame(conversation, frame, ctx) {
  const { event, data } = frame;

  if (event === "tool") {
    // A running list, not a transient label: tool execution takes milliseconds, so a
    // label cleared on tool completion would flash and vanish before the real wait.
    conversation.tools.push(data.name);
    conversation.thinking = ""; // that thought led here; the next gap gets a fresh one
  } else if (event === "thinking") {
    conversation.thinking += data.delta;
  } else if (event === "text") {
    conversation.streaming += data.delta;
  } else if (event === "error") {
    conversation.messages.push({ role: "error", text: data.message });
    ctx.errored = true;
  } else if (event === "done") {
    // The accumulated deltas were a live preview; data.reply is the record. Replacing
    // rather than keeping the buffer means a dropped delta can't corrupt the transcript.
    if (ctx.hadHistory && data.resumed === false) {
      conversation.messages.push({ role: "notice", text: RESET_NOTICE });
    }
    // An "error" frame already delivered this text — don't render it twice.
    if (!ctx.errored) {
      conversation.messages.push({ role: "assistant", text: data.reply });
    }
    clearStreamState(conversation);
  }
}

// --- rendering -------------------------------------------------------------------

function renderSidebar() {
  listEl.replaceChildren();

  for (const conversation of state.conversations) {
    const item = document.createElement("li");
    item.className = `conversation${conversation.id === state.activeId ? " active" : ""}`;

    const title = document.createElement("button");
    title.type = "button";
    title.className = "conversation-title";
    title.textContent = titleOf(conversation); // titles are user text, never innerHTML
    title.addEventListener("click", () => selectConversation(conversation.id));
    item.append(title);

    if (conversation.pending) {
      const spinner = document.createElement("span");
      spinner.className = "conversation-pending";
      spinner.textContent = "…";
      spinner.title = "Waiting for a reply";
      item.append(spinner);
    }

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "conversation-delete";
    remove.textContent = "×";
    remove.title = "Delete conversation";
    remove.setAttribute("aria-label", `Delete ${titleOf(conversation)}`);
    remove.addEventListener("click", (event) => {
      event.stopPropagation(); // don't also select the row we're deleting
      deleteConversation(conversation.id);
    });
    item.append(remove);

    listEl.append(item);
  }
}

function renderMessages() {
  const conversation = active();
  messagesEl.replaceChildren();

  for (const message of conversation.messages) {
    const el = document.createElement("div");
    el.className = `message ${message.role}`;
    el.textContent = message.text; // never innerHTML — replies are arbitrary model output
    messagesEl.append(el);
  }

  if (conversation.pending) {
    // Tools that have run, in order. Accumulates rather than replacing, so the user can
    // see the whole path the agent took rather than whatever it touched most recently.
    if (conversation.tools.length) {
      const trace = document.createElement("div");
      trace.className = "trace";
      trace.textContent = `Used ${conversation.tools.join(" · ")}`;
      messagesEl.append(trace);
    }

    // The agent's reasoning, which is what fills the gaps between tool calls.
    if (conversation.thinking) {
      const thought = document.createElement("div");
      thought.className = "message assistant thinking";
      thought.textContent = conversation.thinking;
      messagesEl.append(thought);
    }

    // Answer text so far, with a caret, so it visibly builds.
    if (conversation.streaming) {
      const el = document.createElement("div");
      el.className = "message assistant streaming";
      el.textContent = conversation.streaming;
      messagesEl.append(el);
    }

    // Nothing has arrived yet — say something rather than showing an empty pane.
    if (!conversation.tools.length && !conversation.thinking && !conversation.streaming) {
      const status = document.createElement("div");
      status.className = "message assistant pending";
      status.textContent = "Thinking…";
      messagesEl.append(status);
    }
  }

  // Deferred a frame: scrollHeight is only final once the new nodes have been laid out.
  requestAnimationFrame(() => {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  });
}

function renderComposer() {
  const busy = active().pending;
  inputEl.disabled = busy;
  sendEl.disabled = busy;
}

function render() {
  renderSidebar();
  renderMessages();
  renderComposer();
}

// --- actions ---------------------------------------------------------------------

function selectConversation(id) {
  if (id === state.activeId) return;
  state.activeId = id;
  save();
  render();
  if (!active().pending) inputEl.focus();
}

function newConversation() {
  const conversation = blankConversation();
  state.conversations.unshift(conversation);
  state.activeId = conversation.id;
  save();
  render();
  inputEl.focus();
}

function deleteConversation(id) {
  const index = state.conversations.findIndex((c) => c.id === id);
  if (index === -1) return;

  state.conversations.splice(index, 1);

  if (!state.conversations.length) {
    const fresh = blankConversation();
    state.conversations.push(fresh);
    state.activeId = fresh.id;
  } else if (state.activeId === id) {
    state.activeId = state.conversations[Math.min(index, state.conversations.length - 1)].id;
  }

  save();
  render();
}

async function send(message) {
  // Captured now, on purpose: a reply takes many seconds and the user may switch
  // conversations before it lands. It must go back to the one it was asked in.
  const conversation = active();
  const ctx = {
    hadHistory: conversation.messages.some((m) => m.role === "assistant"),
    errored: false,
  };

  conversation.messages.push({ role: "user", text: message });
  if (!conversation.title) conversation.title = message.slice(0, TITLE_MAX);
  conversation.pending = true;
  clearStreamState(conversation);
  render();

  // Only touch the message list if this conversation is still on screen; otherwise the
  // sidebar spinner is the only thing that needs updating.
  const repaint = () => {
    if (conversation.id === state.activeId) render();
    else renderSidebar();
  };

  try {
    const response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, conversation_id: conversation.id }),
    });

    if (!response.ok) throw new Error(`Server returned ${response.status}`);

    for await (const frame of readFrames(response)) {
      applyFrame(conversation, frame, ctx);
      repaint();
    }
  } catch (error) {
    conversation.messages.push({
      role: "error",
      text: `Couldn't get a reply: ${error.message}`,
    });
  } finally {
    conversation.pending = false;
    clearStreamState(conversation);
    save();
    repaint();
  }
}

formEl.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = inputEl.value.trim();
  if (!message || active().pending) return;

  inputEl.value = "";
  send(message);
});

newChatEl.addEventListener("click", newConversation);

load();
render();
inputEl.focus();
