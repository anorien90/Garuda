# Garuda

Garuda is an entity-aware web intelligence crawler. It seeds the web, explores pages with a scoring frontier, extracts structured intel (LLM + heuristics), stores results in SQL, and optionally indexes embeddings in Qdrant for semantic/hybrid search. It includes a mark server + Chrome helper to manually capture pages, and an interactive chat mode over the collected knowledge.

## Features
- **Seeding & discovery:** DuckDuckGo seeding (`ddgs`), regex/domain pattern guidance, URL scoring + frontier.
- **Browsing & capture:** Selenium-based browser with recording hooks; manual capture via mark server or Chrome extension.
- **Extraction:** Heuristic extractor (HTML→text, metadata, images, fingerprints) plus LLM intel extractor with reflection/verification.
- **Persistence:** SQLAlchemy store (SQLite by default) for pages, content, links, intelligence, fingerprints.
- **Vector search (optional):** Qdrant-backed embeddings for semantic/hybrid search.
- **Interactive chat:** RAG-style CLI chat over SQL + optional Qdrant.
- **APIs:** Flask mark/search/view endpoints with API key protection.
- **Chrome helper:** Popup UI to mark pages/elements/images and search/view stored items.

## Architecture (high level)
- `src/search.py`: CLI entry (`run`, `chat`, `intel`).
- `src/recorder/app.py`: Flask mark/search/view service (`/mark_page`, `/search`, `/view`, `/healthz`).
- `src/active_browser.py`, `src/browser.py`: Selenium browser + recording helpers.
- `src/explorer/`: Intelligent explorer (frontier, URL scoring, extraction).
- `src/extractor/`: Heuristic + LLM extraction (`LLMIntelExtractor`, `ContentExtractor`).
- `src/persistence/`: SQLAlchemy store and models; fingerprints (`src/types/fingerprint.py`).
- `src/vector_store.py`: Qdrant client wrapper.
- `plugin/chrome/`: Extension popup UI.

Data flow:
1) **Seed** queries → candidates (DuckDuckGo) → scored frontier.  
2) **Explore** with Selenium → capture HTML/text/links → store in SQL.  
3) **Extract** intel with LLM + heuristics; verify; persist intel + embeddings (if Qdrant enabled).  
4) **Query** via CLI (`intel`/`chat`) or API `/search` + optional UI/extension.

## Requirements
- Python 3.10+
- Chrome/Chromium + chromedriver on PATH (for crawling)
- Optional: Qdrant (local or remote) for vectors
- Optional: Ollama (defaults to `granite3.1-dense:8b`) or any OpenAI-compatible endpoint

## Installation
```bash
git clone https://github.com/anorien90/Garuda.git
cd Garuda
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # or: pip install -e .
```

## Configuration
Environment variables (examples):
- `MARK_SERVER_API_KEY=changeme`
- `MARK_SERVER_HOST=0.0.0.0`
- `MARK_SERVER_PORT=8765`
- `MARK_SERVER_DB=sqlite:///crawler.db`
- `QDRANT_URL=http://localhost:6333`
- `QDRANT_COLLECTION=pages`
- `OLLAMA_URL=http://localhost:11434/api/generate`
- `OLLAMA_MODEL=granite3.1-dense:8b`
- `BROWSER_HEADLESS=true`

You can also use a `.env` file (loaders are present in code).

## Quickstart
1) **Start mark server** (for manual capture/API):
```bash
python -m src.recorder.app
# or inside CLI run: mark server thread auto-starts when enabled
```

2) **Run a crawl** (SQLite; Qdrant optional):
```bash
python -m src.search run \
  --sqlite-path crawler.db \
  --qdrant-url http://localhost:6333 \
  --qdrant-collection pages \
  --ollama-url http://localhost:11434/api/generate \
  --model granite3.1-dense:8b \
  --verbose
```

3) **Query intel (semantic/hybrid):**
```bash
python -m src.search intel --semantic-search "acme corp leadership" --top-k 5
# or SQL-only search flags as needed
```

4) **Chat over collected knowledge (RAG):**
```bash
python -m src.search chat \
  --entity-name "Acme Corp" \
  --sqlite-path crawler.db \
  --qdrant-url http://localhost:6333 \
  --qdrant-collection pages
```

5) **Mark pages via API (requires API key):**
```bash
curl -X POST "http://localhost:8765/mark_page" \
  -H "x-api-key: $MARK_SERVER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com","mode":"page","session_id":"demo"}'
```
View stored page:
```bash
curl -H "x-api-key: $MARK_SERVER_API_KEY" "http://localhost:8765/view?url=https://example.com"
```

6) **Chrome extension:**
- Load `plugin/chrome` as an unpacked extension in Chrome.
- Use popup tabs to mark/search/view; API key must match mark server.

## Optional: lightweight web UI
A simple Flask/React (or pure Flask + HTMX) UI can sit on `/ui` to:
- Search intel (filters: query, entity, type, confidence, date)
- Browse pages and view stored text/HTML/metadata
- Trigger chat against stored data (proxy to CLI logic or backend endpoint)

See `webapp/` sample below.

## Development
- Run tests: `pytest`
- Lint/format: `ruff check . && black .`
- Typecheck: `mypy src`
- Suggested make targets:
  - `make dev` (install deps with dev extras)
  - `make crawl` (sample crawl command)
  - `make chat` (sample chat)
  - `make up` (docker compose: qdrant + mark server + ui)

## Security notes
- Protect mark/search/view endpoints with strong API keys; restrict CORS in production.
- Be mindful of LLM prompts leaking sensitive data; run Ollama locally when possible.
- Headless browser can execute untrusted JS—consider sandboxing or domain allowlists.

## Roadmap / next improvements
- Config unification and validation (pydantic-settings)
- Vector/LLM provider interfaces with fallbacks
- Alembic migrations + schema docs
- Better dedupe/normalization of URLs and links
- More extractor fingerprints per entity type
- UI polish: live crawl status, intel review/approval# Garuda

Garuda is an entity-aware web intelligence crawler. It seeds the web, explores pages with a scoring frontier, extracts structured intel (LLM + heuristics), stores results in SQL, and optionally indexes embeddings in Qdrant for semantic/hybrid search. It includes a mark server + Chrome helper to manually capture pages, and an interactive chat mode over the collected knowledge.

## Features
- **Seeding & discovery:** DuckDuckGo seeding (`ddgs`), regex/domain pattern guidance, URL scoring + frontier.
- **Browsing & capture:** Selenium-based browser with recording hooks; manual capture via mark server or Chrome extension.
- **Extraction:** Heuristic extractor (HTML→text, metadata, images, fingerprints) plus LLM intel extractor with reflection/verification.
- **Persistence:** SQLAlchemy store (SQLite by default) for pages, content, links, intelligence, fingerprints.
- **Vector search (optional):** Qdrant-backed embeddings for semantic/hybrid search.
- **Interactive chat:** RAG-style CLI chat over SQL + optional Qdrant.
- **APIs:** Flask mark/search/view endpoints with API key protection.
- **Chrome helper:** Popup UI to mark pages/elements/images and search/view stored items.

## Architecture (high level)
- `src/search.py`: CLI entry (`run`, `chat`, `intel`).
- `src/recorder/app.py`: Flask mark/search/view service (`/mark_page`, `/search`, `/view`, `/healthz`).
- `src/active_browser.py`, `src/browser.py`: Selenium browser + recording helpers.
- `src/explorer/`: Intelligent explorer (frontier, URL scoring, extraction).
- `src/extractor/`: Heuristic + LLM extraction (`LLMIntelExtractor`, `ContentExtractor`).
- `src/persistence/`: SQLAlchemy store and models; fingerprints (`src/types/fingerprint.py`).
- `src/vector_store.py`: Qdrant client wrapper.
- `plugin/chrome/`: Extension popup UI.

Data flow:
1) **Seed** queries → candidates (DuckDuckGo) → scored frontier.  
2) **Explore** with Selenium → capture HTML/text/links → store in SQL.  
3) **Extract** intel with LLM + heuristics; verify; persist intel + embeddings (if Qdrant enabled).  
4) **Query** via CLI (`intel`/`chat`) or API `/search` + optional UI/extension.

## Requirements
- Python 3.10+
- Chrome/Chromium + chromedriver on PATH (for crawling)
- Optional: Qdrant (local or remote) for vectors
- Optional: Ollama (defaults to `granite3.1-dense:8b`) or any OpenAI-compatible endpoint

## Installation
```bash
git clone https://github.com/anorien90/Garuda.git
cd Garuda
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # or: pip install -e .
```

## Configuration
Environment variables (examples):
- `MARK_SERVER_API_KEY=changeme`
- `MARK_SERVER_HOST=0.0.0.0`
- `MARK_SERVER_PORT=8765`
- `MARK_SERVER_DB=sqlite:///crawler.db`
- `QDRANT_URL=http://localhost:6333`
- `QDRANT_COLLECTION=pages`
- `OLLAMA_URL=http://localhost:11434/api/generate`
- `OLLAMA_MODEL=granite3.1-dense:8b`
- `BROWSER_HEADLESS=true`

You can also use a `.env` file (loaders are present in code).

## Quickstart
1) **Start mark server** (for manual capture/API):
```bash
python -m src.recorder.app
# or inside CLI run: mark server thread auto-starts when enabled
```

2) **Run a crawl** (SQLite; Qdrant optional):
```bash
python -m src.search run \
  --sqlite-path crawler.db \
  --qdrant-url http://localhost:6333 \
  --qdrant-collection pages \
  --ollama-url http://localhost:11434/api/generate \
  --model granite3.1-dense:8b \
  --verbose
```

3) **Query intel (semantic/hybrid):**
```bash
python -m src.search intel --semantic-search "acme corp leadership" --top-k 5
# or SQL-only search flags as needed
```

4) **Chat over collected knowledge (RAG):**
```bash
python -m src.search chat \
  --entity-name "Acme Corp" \
  --sqlite-path crawler.db \
  --qdrant-url http://localhost:6333 \
  --qdrant-collection pages
```

5) **Mark pages via API (requires API key):**
```bash
curl -X POST "http://localhost:8765/mark_page" \
  -H "x-api-key: $MARK_SERVER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com","mode":"page","session_id":"demo"}'
```
View stored page:
```bash
curl -H "x-api-key: $MARK_SERVER_API_KEY" "http://localhost:8765/view?url=https://example.com"
```

6) **Chrome extension:**
- Load `plugin/chrome` as an unpacked extension in Chrome.
- Use popup tabs to mark/search/view; API key must match mark server.

## Optional: lightweight web UI
A simple Flask/React (or pure Flask + HTMX) UI can sit on `/ui` to:
- Search intel (filters: query, entity, type, confidence, date)
- Browse pages and view stored text/HTML/metadata
- Trigger chat against stored data (proxy to CLI logic or backend endpoint)

See `webapp/` sample below.

## Development
- Run tests: `pytest`
- Lint/format: `ruff check . && black .`
- Typecheck: `mypy src`
- Suggested make targets:
  - `make dev` (install deps with dev extras)
  - `make crawl` (sample crawl command)
  - `make chat` (sample chat)
  - `make up` (docker compose: qdrant + mark server + ui)

## Security notes
- Protect mark/search/view endpoints with strong API keys; restrict CORS in production.
- Be mindful of LLM prompts leaking sensitive data; run Ollama locally when possible.
- Headless browser can execute untrusted JS—consider sandboxing or domain allowlists.

## Roadmap / next improvements
- Config unification and validation (pydantic-settings)
- Vector/LLM provider interfaces with fallbacks
- Alembic migrations + schema docs
- Better dedupe/normalization of URLs and links
- More extractor fingerprints per entity type
- UI polish: live crawl status, intel review/approval# Garuda

Garuda is an entity-aware web intelligence crawler. It seeds the web, explores pages with a scoring frontier, extracts structured intel (LLM + heuristics), stores results in SQL, and optionally indexes embeddings in Qdrant for semantic/hybrid search. It includes a mark server + Chrome helper to manually capture pages, and an interactive chat mode over the collected knowledge.

## Features
- **Seeding & discovery:** DuckDuckGo seeding (`ddgs`), regex/domain pattern guidance, URL scoring + frontier.
- **Browsing & capture:** Selenium-based browser with recording hooks; manual capture via mark server or Chrome extension.
- **Extraction:** Heuristic extractor (HTML→text, metadata, images, fingerprints) plus LLM intel extractor with reflection/verification.
- **Persistence:** SQLAlchemy store (SQLite by default) for pages, content, links, intelligence, fingerprints.
- **Vector search (optional):** Qdrant-backed embeddings for semantic/hybrid search.
- **Interactive chat:** RAG-style CLI chat over SQL + optional Qdrant.
- **APIs:** Flask mark/search/view endpoints with API key protection.
- **Chrome helper:** Popup UI to mark pages/elements/images and search/view stored items.

## Architecture (high level)
- `src/search.py`: CLI entry (`run`, `chat`, `intel`).
- `src/recorder/app.py`: Flask mark/search/view service (`/mark_page`, `/search`, `/view`, `/healthz`).
- `src/active_browser.py`, `src/browser.py`: Selenium browser + recording helpers.
- `src/explorer/`: Intelligent explorer (frontier, URL scoring, extraction).
- `src/extractor/`: Heuristic + LLM extraction (`LLMIntelExtractor`, `ContentExtractor`).
- `src/persistence/`: SQLAlchemy store and models; fingerprints (`src/types/fingerprint.py`).
- `src/vector_store.py`: Qdrant client wrapper.
- `plugin/chrome/`: Extension popup UI.

Data flow:
1) **Seed** queries → candidates (DuckDuckGo) → scored frontier.  
2) **Explore** with Selenium → capture HTML/text/links → store in SQL.  
3) **Extract** intel with LLM + heuristics; verify; persist intel + embeddings (if Qdrant enabled).  
4) **Query** via CLI (`intel`/`chat`) or API `/search` + optional UI/extension.

## Requirements
- Python 3.10+
- Chrome/Chromium + chromedriver on PATH (for crawling)
- Optional: Qdrant (local or remote) for vectors
- Optional: Ollama (defaults to `granite3.1-dense:8b`) or any OpenAI-compatible endpoint

## Installation
```bash
git clone https://github.com/anorien90/Garuda.git
cd Garuda
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # or: pip install -e .
```

## Configuration
Environment variables (examples):
- `MARK_SERVER_API_KEY=changeme`
- `MARK_SERVER_HOST=0.0.0.0`
- `MARK_SERVER_PORT=8765`
- `MARK_SERVER_DB=sqlite:///crawler.db`
- `QDRANT_URL=http://localhost:6333`
- `QDRANT_COLLECTION=pages`
- `OLLAMA_URL=http://localhost:11434/api/generate`
- `OLLAMA_MODEL=granite3.1-dense:8b`
- `BROWSER_HEADLESS=true`

You can also use a `.env` file (loaders are present in code).

## Quickstart
1) **Start mark server** (for manual capture/API):
```bash
python -m src.recorder.app
# or inside CLI run: mark server thread auto-starts when enabled
```

2) **Run a crawl** (SQLite; Qdrant optional):
```bash
python -m src.search run \
  --sqlite-path crawler.db \
  --qdrant-url http://localhost:6333 \
  --qdrant-collection pages \
  --ollama-url http://localhost:11434/api/generate \
  --model granite3.1-dense:8b \
  --verbose
```

3) **Query intel (semantic/hybrid):**
```bash
python -m src.search intel --semantic-search "acme corp leadership" --top-k 5
# or SQL-only search flags as needed
```

4) **Chat over collected knowledge (RAG):**
```bash
python -m src.search chat \
  --entity-name "Acme Corp" \
  --sqlite-path crawler.db \
  --qdrant-url http://localhost:6333 \
  --qdrant-collection pages
```

5) **Mark pages via API (requires API key):**
```bash
curl -X POST "http://localhost:8765/mark_page" \
  -H "x-api-key: $MARK_SERVER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com","mode":"page","session_id":"demo"}'
```
View stored page:
```bash
curl -H "x-api-key: $MARK_SERVER_API_KEY" "http://localhost:8765/view?url=https://example.com"
```

6) **Chrome extension:**
- Load `plugin/chrome` as an unpacked extension in Chrome.
- Use popup tabs to mark/search/view; API key must match mark server.

## Optional: lightweight web UI
A simple Flask/React (or pure Flask + HTMX) UI can sit on `/ui` to:
- Search intel (filters: query, entity, type, confidence, date)
- Browse pages and view stored text/HTML/metadata
- Trigger chat against stored data (proxy to CLI logic or backend endpoint)

See `webapp/` sample below.

## Development
- Run tests: `pytest`
- Lint/format: `ruff check . && black .`
- Typecheck: `mypy src`
- Suggested make targets:
  - `make dev` (install deps with dev extras)
  - `make crawl` (sample crawl command)
  - `make chat` (sample chat)
  - `make up` (docker compose: qdrant + mark server + ui)

## Security notes
- Protect mark/search/view endpoints with strong API keys; restrict CORS in production.
- Be mindful of LLM prompts leaking sensitive data; run Ollama locally when possible.
- Headless browser can execute untrusted JS—consider sandboxing or domain allowlists.

## Roadmap / next improvements
- Config unification and validation (pydantic-settings)
- Vector/LLM provider interfaces with fallbacks
- Alembic migrations + schema docs
- Better dedupe/normalization of URLs and links
- More extractor fingerprints per entity type
- UI polish: live crawl status, intel review/approval
