<p align="center" draggable="false"><img src="https://github.com/AI-Maker-Space/LLM-Dev-101/assets/37101144/d1343317-fa2f-41e1-8af1-1dbb18399719"
     width="200px"
     height="auto"/>
</p>

<h1 align="center" id="heading">Session 8: Model Context Protocol (MCP)</h1>

### [Quicklinks]()

| Session Sheet | Recording | Slides | Repo | Homework | Feedback |
|:--------------|:----------|:-------|:-----|:---------|:---------|
| [Session 8: MCP](https://github.com/AI-Maker-Space/The-AI-Engineering-Certification-v1.0/tree/main/00_Docs/Modules/08_MCP) |[Recording!](https://us02web.zoom.us/rec/share/rqw5I5hwbOOHy8TrGjnu0IjDJi53ykHb0k897jYfyHqZpgRhUuFP4A18d4NrcEKS.18sNk6Do9XwyaVUy) <br> passcode: `E56&^V+8`| [Session 8 Slides](https://canva.link/k8cixqgkfeghdsn) |You are here! | [Session 8 Assignment](https://forms.gle/TcjjChq38ydMjuqn8) | [Feedback 6/25](https://forms.gle/DvcWDgBXatBWCXqi7) |

## Useful Resources

**MCP (Model Context Protocol)**
- [MCP Official Docs](https://modelcontextprotocol.io/) — Spec, tutorials, and guides
- [MCP-UI](https://mcpui.dev/) — Official standard for interactive UI in MCP
- [MCP Auth Guide (Auth0)](https://auth0.com/blog/mcp-specs-update-all-about-auth/) — Deep dive into MCP auth spec updates

## Main Assignment

In this session, you will build an MCP server with OAuth authentication — a cat
shop application that exposes tools for browsing products, managing a cart, and
checking out.

The main entry point is:

```text
server.py
```

The server implementation lives in:

```text
app/
```

Available MCP tools:

- `list_products`
- `get_product`
- `add_to_cart`
- `view_cart`
- `remove_from_cart`
- `checkout`

## Setup

From this folder:

```bash
uv sync
```

Copy the example env file and fill in your OpenAI API key:

```bash
cp .env.example .env
```

## Running the MCP Server

Run the server locally:

```bash
uv run server.py
```

The server starts on `http://localhost:8000`.

### Expose the server with ngrok

In a separate terminal, start an ngrok tunnel:

```bash
ngrok http 8000
```

Copy the ngrok forwarding URL (e.g. `https://xxxx-xx-xx-xx-xx.ngrok-free.app`) and
restart the server with it:

```bash
ISSUER_URL=https://xxxx-xx-xx-xx-xx.ngrok-free.app uv run server.py
```

> **Note:** The `ISSUER_URL` must match the public URL clients use to reach the
> server, otherwise OAuth authentication will fail.

## Outline

### Breakout Room #1

- Set up the MCP server with OAuth and the product database
- Explore the MCP tools: `list_products`, `get_product`, `add_to_cart`, `view_cart`, `remove_from_cart`, `checkout`

### Breakout Room #2

- Connect an MCP client to the server
- Build an end-to-end interaction flow using the MCP tools

## Ship

The completed MCP server and client integration!

### Deliverables

- A short Loom of either:
  - the MCP server you built and a demo of the client interacting with it; or
  - the notebook you created for the Advanced Build

## Share

Make a social media post about your final application!

### Deliverables

- Make a post on any social media platform about what you built!

Here's a template to get you started:

```
🚀 Exciting News! 🚀

I am thrilled to announce that I have just built and shipped an MCP server with OAuth authentication! 🎉🤖

🔍 Three Key Takeaways:
1️⃣
2️⃣
3️⃣

Let's continue pushing the boundaries of what's possible in the world of AI and tool integration. Here's to many more innovations! 🚀
Shout out to @AIMakerspace !

#MCP #ModelContextProtocol #OAuth #Innovation #AI #TechMilestone

Feel free to reach out if you're curious or would like to collaborate on similar projects! 🤝🔥
```

## Submitting Your Homework 

Follow these steps to prepare and submit your homework assignment:

1. Review the MCP server code in `server.py` and the `app/` directory
2. Run the MCP server locally using `uv run server.py`
3. Connect to the server using an MCP client (e.g., Claude Desktop, or a custom client)
4. Test all available tools: browsing products, adding to cart, viewing cart, removing items, and checkout
5. Record a Loom video reviewing what you have learned from this session

## Questions

### Question #1

Why is OAuth important for MCP servers, and what security considerations should you keep in mind when exposing tools to AI clients?

#### Answer

OAuth is important for MCP servers because it lets the server verify which client/user is requesting access and what permissions they have. This matters because MCP tools may expose sensitive data or perform actions like modifying a cart, querying private systems or making purchases. When exposing tools to AI clients, we should use scoped permissions, validate inputs, avoid overly powerful tools, protect tokens, and make sure destructive actions require clear user intent.

### Question #2

What is Streamable HTTP transport in MCP, and why might you expose a server publicly with OAuth instead of using a local stdio connection?

#### Answer

Streamable HTTP is an MCP transport protocol that lets a client communicate with an MCP server over HTTP instead of local standard input/output. This is useful when the MCP client is remote, such as ChatGPT or another hosted agent, because it can't directly access a local stdio process on my machine. If the server is exposed publicly, OAuth is needed to control which clients/users can connect and what actions they are allowed to perform.

## Activity 1: Extend the MCP Server

Add at least one new tool to the cat shop MCP server (e.g., `search_products`, `update_cart_quantity`, or `get_order_history`). Ensure the new tool integrates properly with the existing database and OAuth authentication. Demo the new tool through an MCP client and include it in your Loom video.

## Advanced Activity: Build a Custom MCP Client

Build a custom MCP client that connects to the cat shop server over Streamable HTTP, authenticates via OAuth, and orchestrates a multi-step shopping flow (browse → add to cart → checkout). Compare the developer experience of MCP-based tool integration vs. traditional REST API calls.

Include your findings and a demo in your Loom video.

While building the Cat Shop server, I integrated the Auspost PAC API two ways: as raw REST calls inside my server, and as an MCP tool exposed to an LLM client. That gave me a direct comparison

Tool discovery
- REST: I had to read the AusPost PAC reference docs, guess the query params (from_postcode, weight, service_code…), and confirm them by trial and error. Discovery is a human, out-of-band task.
- MCP: The client calls list_tools() and gets every tool + JSON schema at runtime. When I added estimate_shipping, the client discovered it automatically — no doc reading.

Authentication
- REST: I attached AUTH-KEY to every request myself and guarded the missing-key case in code.
- MCP: Auth is handled once by the transport. My OAuth server issues a token; the client attaches it to all tool calls. Individual tools never touch auth.

Schema & validation
- REST: Request params were hand-built dicts, and I parsed the nested response (postage_result.total_cost) manually, casting types by hand.
- MCP: FastMCP generated the input JSON Schema from my Python type hints (country: str | None, weight: float | None). The client validates arguments before they ever reach my code.

Error handling & human-in-the-loop
- REST: I checked status_code and dug error.errorMessage out of the payload.
- MCP: I returned structured results the model understands, including a need_input signal that makes the assistant ask the user for a missing postcode instead of guessing. That conversational fallback has no clean REST equivalent.

LLM integration
- REST: To let an LLM use the AusPost API, I'd have to write function-calling wrappers, schemas, and glue for each endpoint.
- MCP: The tools dropped straight into a LangChain agent (Loaded LangChain tools: … estimate_shipping). Zero per-tool glue.

Coupling & maintenance
- REST: Each API is its own client, base URL, and auth scheme.
- MCP: One session exposes many tools over a uniform interface. The trade-off I hit: because discovery is at connection time, a stale cached tool list meant a client didn't see estimate_shipping until it reconnected — a maintenance quirk REST doesn't have (but REST pays for it with manual doc-syncing instead).

Takeaway: These aren't competing protocols so much as different interaction models for different consumers. REST exposes fixed endpoints and remains the default for service-to-service and app backends. MCP layers a discoverable, self-describing tool interface (often on top of HTTP) aimed at LLM/agent consumers. In my build they were complementary — AusPost stayed a REST API and MCP wrapped it as the agent-facing layer — but that's a design choice, not a rule: agents can call REST directly, and MCP shines mainly when we have many tools or multiple agent clients that benefit from runtime discovery and a uniform interface.

The mature pattern is a hybrid, and it mirrors how MCP is meant to be used:

- Deterministic steps → direct call_tool. Anything with a fixed sequence, money, or side effects (add to cart, checkout) should be explicit code we control not left to model discretion. I probably never want an LLM deciding on its own to call checkout without approval in real application

- Open-ended steps → agent. "Find me a good toy under $10 for a kitten" is genuinely a reasoning task — let the agent choose list_products / get_product.

- Guardrails regardless of layer. The server already enforces this well: checkout and add_to_cart require auth via _get_username(), and the client system prompt says "Only call checkout when the user explicitly asks." That instruction is a soft guard; the hard guard is keeping destructive actions in deterministic code.

