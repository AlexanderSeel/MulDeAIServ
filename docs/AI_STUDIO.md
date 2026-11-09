# AI Studio — quick start and capabilities

AI Studio is a real web chat interface connected to the MulDeAIServ API gateway. It works with locally registered vLLM, Ollama, llama.cpp HTTP and exo servers that expose OpenAI-compatible chat completions.

## Start

1. Run the MulDeAIServ controller with Python 3.11+ and a strong admin token. Open http://127.0.0.1:8765.
2. Sign in using the admin token printed by the controller or configured in MULDEAI_ADMIN_TOKEN.
3. Start an actual model server. For a controller-local Ollama installation, open Models & API and click **Discover** in **Connect local Ollama**. Register an installed model. For other private model APIs, register the origin and served model ID under the backend form.
4. Open AI Studio, choose a registered model, and enter a question. Enter sends; Shift+Enter adds a newline.
5. Use Settings for optional system instructions, temperature, max output tokens and streaming mode. Streaming requires OpenAI-compatible text/event-stream support.
6. Use New Chat to start fresh, or open any saved chat on the left to continue it. Search history by title or model ID.

## Functions

- Multi-turn chat sends the latest 40 conversation messages (and configured system instruction) to the chosen backend.
- Saves ordered user and assistant messages in SQLite. New conversations are automatically titled from the first prompt; title can be renamed.
- Supports model selection per conversation, SSE token streaming and regular JSON completion. Stop interrupts client streaming; a partial response is not stored as a completed assistant message.
- Search, delete, copy and export your conversations in Markdown.
- Integrates the existing device telemetry, inference backend management, model planning and manual setup guides.
- Ollama auto-discovery is a fixed local connection to 127.0.0.1:11434 on the **controller**, not the web browser's computer; no LAN scanning or downloads take place.

## API

All chat history APIs require the administrator bearer token:

- GET /api/studio/conversations — list up to 200 chats with message counts.
- POST /api/studio/conversations — create a chat; model must be registered.
- GET /api/studio/conversations/{id} — chat metadata and ordered messages.
- PATCH /api/studio/conversations/{id} — rename, change model, system prompt or temperature.
- POST /api/studio/conversations/{id}/messages — store a user or assistant message.
- DELETE /api/studio/conversations/{id} — delete the chat and cascade-delete its messages.

The client calls POST /v1/chat/completions through the existing authenticated inference gateway. The API allows inference-only credentials for external clients, but **not** for stored chat history.

GET /api/discovery/ollama (admin-only) queries the fixed controller-local Ollama inventory endpoint /api/tags. This never downloads models, installs Ollama, scans arbitrary networks or opens a port.

## Privacy and trust

Chats (including system instructions and responses) are saved as plaintext SQLite in the configured MULDEAI_DB_PATH. Use filesystem permissions and protected backups, and avoid using the chat to store secrets unless you control the environment and trust every model backend. All model prompts and recent chat history are sent to the selected backend. MulDeAIServ does not currently encrypt this data, isolate different human users, implement multi-user RBAC, or apply content retention policies beyond explicit deletion.

Admin tokens are held only in browser process memory, not localStorage. Serving over public or unprotected HTTP is unsafe; use loopback or HTTPS over a trusted private network. Model-generated text is rendered as textContent and not trusted as HTML.

## Limitations and next steps

- Model servers must be installed and running separately. Chat models may have engine-specific generation limits.
- Selecting a model does not guarantee backend availability. Use Model Test to check model discovery.
- No actual Ray/vLLM sharding or llama.cpp RPC worker process management is performed by the Studio.
- Real Android/iOS model workers and heterogeneous model partitioning are separate, unimplemented infrastructure tasks.
- Full browser accessibility/visual audits, message search, user accounts and encryption are planned but not complete.
