# Harnesses and structured output: what agent tools actually expect from a model

Notes recorded 2026-11-11, during the `smallModels-harness` experiment.
Verified against the sources at the bottom; implementations change, so re-check before quoting.

---

## TL;DR

Agent harnesses such as OpenCode, Pi and Claude Code **do not ask the model to write JSON in its
answer text**. They pass tool definitions to the API and read back a dedicated **tool-call object**,
whose arguments are validated against a schema before anything executes.

"Pure structured JSON" is literally true at three levels — the HTTP transport, the tool-call
arguments, and the tool schemas — but misleading as a description of what the model does. The model
fills a reserved channel; it does not compose a JSON document in prose.

This distinction matters because our own benchmark measured it: **same model, 47% with JSON-in-text
vs 73% with native tool calls** (`bench/RESULTS.md`).

---

## The three layers people conflate

| Layer | What is JSON | Who guarantees the shape |
|---|---|---|
| **Transport** | The whole HTTP request and response body | The API |
| **Tool call** | A `tool_calls` array; `function.arguments` is a JSON *string* | The provider and the model's chat template |
| **Your schema** | The argument object must match the tool's declared schema | The harness, via Zod / TypeBox / AJV validation |

If the tool-call field is missing or malformed, the harness has three options: repair it, retry, or
fail the step. Production harnesses do all three.

---

## What specific harnesses use

| Harness | Stack | How tools are called | Fallback for models without tool calling |
|---|---|---|---|
| **OpenCode** | Bun/TypeScript server + Go TUI; **Vercel AI SDK** | Provider-native tool calls; tools defined with **Zod** `inputSchema`; MCP tools merged into the same registry | Model registry flag: `tools: model.info.tool_call === false ? undefined : tools` — tools are not sent at all |
| **Pi (pi.dev)** | Own **pi-ai** library + `pi-agent-core` loop | Provider-native tool calls; **TypeBox** schemas validated with **AJV**; OpenAI-compatible endpoints incl. llama.cpp/Ollama/vLLM/LM Studio | Custom model definitions; JSON/RPC modes are for *consumers* of pi's output, not for the model |
| **Claude Code** | Closed source (Anthropic) | Anthropic's documented `tool_use` content blocks + MCP | Unknown / not public |
| **Freebuff** | Hosted, ad-funded coding agent | Not publicly documented | Not verified — do not assert internals |

### OpenCode, in its own code shape

The loop is roughly:

1. Build a system prompt and a tool registry.
2. Convert each tool to an AI SDK tool with a Zod `inputSchema`.
3. Call the provider with `tools`.
4. Consume a stream of events: `tool-call`, `tool-result`, `tool-error`, `text-delta`.
5. Execute the tool, append the result, repeat until the model stops calling tools.

Two details worth noting:

- **MCP tools are not special.** They are fetched from MCP servers at startup and added to the same
  tool map, so the model sees one uniform tool interface.
- **A model that cannot tool-call gets no tools.** OpenCode checks its model registry flag rather
  than parsing JSON out of prose.

### Pi, in its own words

- Built its own unified API because the Vercel AI SDK "doesn't play nice with self-hosted models…
  specifically when it comes to tool calling".
- Tool arguments are validated with TypeBox + AJV, with detailed validation errors.
- The agent loop runs until the model produces a response with no tool calls.
- Supports `openai-completions` as an API type, which is how llama.cpp, Ollama, vLLM and LM Studio
  are reached.
- `--mode json` and RPC are headless *output* formats for scripts — not the model-facing protocol.

---

## Where "pure structured JSON" is literally true

1. **Tool definitions** are JSON Schema (`type`, `properties`, `required`).
2. **Tool-call arguments** arrive as a JSON string (OpenAI-style) or a JSON object (Anthropic-style)
   and must parse.
3. **Tool results** are usually JSON or typed content blocks.
4. **Secondary tasks** often use JSON mode / structured outputs: plan generation, todo lists,
   summaries, sub-agent hand-off. OpenCode's `todowrite` tool, for example, takes a Zod-validated
   array of todo objects.

## Where it is misleading

- The model does **not** choose the envelope. On a native tool-call API, the envelope is part of the
  model's chat template and the provider's response schema. The model supplies a name and arguments.
- "Structured output" and "tool calling" are different mechanisms:

| Concept | Purpose | Mechanism |
|---|---|---|
| **Tool calling** | Actions: name + arguments + execution + result | A protocol in the API response |
| **Structured output** | Constrain generated text to a schema | JSON mode, JSON-schema response format, `strict: true`, GBNF grammar |

A harness's main loop is tool calling. Structured output is used when there is no action to take, or
when the model cannot tool-call at all.

---

## How this maps onto our benchmark

| Our arm | Real-world equivalent | Result |
|---|---|---|
| `native` | Harness + model whose `tool_call` capability is true | **73%** |
| `json` | Harness forced to parse free text, or model flagged `tool_call: false` | **47%** |

Same weights, same tasks. The 26-point gap is the price of losing the reserved channel.

There is also a third, subtler layer in our own code: `bench/run.py` contains a fallback parser for
LFM3's XML tool-call format (`<tool_call><function=…><parameter=…>`). That is the harness **repairing**
structured output — exactly what production harnesses do.

---

## Checklist before wiring a local model into a harness

1. **Does the model claim tool-call support?** Check the provider registry (OpenCode uses a
   `tool_call` flag) or the model card.
2. **Does the GGUF carry the current chat template?** Query `/props` and confirm `<tools>`,
   `<tool_call>` and the thinking markers are present.
3. **Does llama-server parse it natively?** Look for `Chat format:` in the log. `Generic` means the
   template was not recognised.
4. **Test two calls before benchmarking:** one single-tool call, one two-step chain. If the second
   fails, the harness, not the model, is usually the problem.
5. **Log parse failures separately from wrong answers.** They are different bugs.
6. **Prefer constrained decoding** where the provider supports it (JSON schema / GBNF), especially
   for models under ~3B.

---

## Open questions

- **Does constrained decoding close the 26-point gap?** Our `json` arm is free-text parsing, the
  worst case. A grammar-constrained arm would separate "bad at syntax" from "bad at reasoning".
- **How much do harness-side repairs hide?** Retries, regex extraction and schema coercion might
  make a weak model look better than it is.
- **MCP context cost.** Tool definitions are billed as context. Pi's author argues MCP servers can
  consume 7–9% of the window before any work starts; OpenCode accepts that cost for uniformity.
- **Registry flags are trust-based.** If a model is marked `tool_call: false` incorrectly, the
  harness silently falls back to a weaker path.

---

## Sources

- Moncef Abboud, *How Coding Agents Actually Work: Inside OpenCode*, Sep 2025 —
  https://cefboud.com/posts/coding-agents-internals-opencode-deepdive/
- Mario Zechner, *What I learned building an opinionated and minimal coding agent*, Nov 2025 —
  https://mariozechner.at/posts/2025-11-30-pi-coding-agent/
- Vercel AI SDK, *Tool Calling* — https://ai-sdk.dev/docs/ai-sdk-core/tools-and-tool-calling
- OpenAI, *Function calling* — https://developers.openai.com/api/docs/guides/function-calling
- llama.cpp, *Function calling* — https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md
- Freebuff (product page; internals not published) — https://freebuff.com/

## Related files

- `bench/RESULTS.md` — the local measurements referenced above
- `bench/run.py` — native and JSON arms, plus the XML fallback parser
- `research/SOURCES.md` — evidence on small-model capability