# AI-Trader Project Analysis

## Executive Summary
AI-Trader orchestrates autonomous trading tournaments where multiple large language model (LLM) agents trade NASDAQ-100 equities using a shared set of Model Context Protocol (MCP) tools. The public README frames the project as a zero-human-intervention benchmark that evaluates models on identical capital, data, and infrastructure while surfacing live dashboards and scheduled enhancements.【F:README.md†L3-L113】 The codebase couples an asynchronous Python control plane, a suite of MCP microservices for data, execution, math, and news retrieval, and a static web dashboard that visualizes portfolio performance from persisted trade logs.【F:main.py†L1-L240】【F:agent_tools/start_mcp_services.py†L1-L200】【F:docs/assets/js/data-loader.js†L1-L200】

## Runtime Architecture
- **Entry Point** – `main.py` loads configuration, instantiates the requested agent class dynamically, and iterates over enabled LLM models. For each model it initializes MCP connections, executes the date range asynchronously, and prints end-of-run position summaries.【F:main.py†L94-L240】
- **Agent Base Class** – `agent/base_agent/base_agent.py` encapsulates MCP client wiring, trading loops, logging, retry strategy, and position file management. It synthesizes prompts with current market context and orchestrates tool-driven decision cycles until a stop signal is emitted or the max reasoning steps are exhausted.【F:agent/base_agent/base_agent.py†L1-L465】
- **MCP Services** – `agent_tools/start_mcp_services.py` supervises four FastMCP servers (math, news search, trading execution, local price lookup), including lifecycle management, health checks, and log handling. Each tool script exposes specific functionality over HTTP ports configurable via environment variables.【F:agent_tools/start_mcp_services.py†L17-L200】
- **Operational Pipeline** – `main.sh` describes the intended sequential workflow: fetch and merge Alpha Vantage data, start MCP services, run trading agents, and finally host the static dashboard via Python’s `http.server`.【F:main.sh†L1-L34】

## Agent Workflow Details
1. **Initialization** – Agents configure MCP endpoints, instantiate a `ChatOpenAI` client using either per-model credentials or `.env` fallbacks, and validate tool availability. Misconfigured MCP services raise actionable runtime errors.【F:agent/base_agent/base_agent.py†L99-L190】
2. **Daily Session Loop** – For each trading day, `run_trading_session` sets up per-day logs, rebuilds the system prompt with up-to-date prices and positions, and repeatedly invokes the LangChain agent. It stops when the tool responses contain the `<FINISH_SIGNAL>` token defined in `prompts/agent_prompt.py`.【F:agent/base_agent/base_agent.py†L223-L292】【F:prompts/agent_prompt.py†L30-L92】
3. **Tool Coordination** – The session monitors tool outputs, appends them to the conversational context, and persists both assistant reasoning and tool feedback to JSONL log files under `data/agent_data/{signature}/log/{date}/`.【F:agent/base_agent/base_agent.py†L232-L285】
4. **Position Management** – Post-session, the agent inspects whether any trade tool executed (tracked via the shared runtime config). If not, it appends a synthetic “no_trade” record to keep the position timeline continuous.【F:agent/base_agent/base_agent.py†L294-L339】【F:tools/price_tools.py†L224-L349】

## MCP Tool Ecosystem
- **Trade Execution (`tool_trade.py`)** – Provides `buy` and `sell` actions that look up the latest holdings, validate cash or share availability, and append transactions to the agent’s position ledger. Both update a shared runtime flag (`IF_TRADE`) to inform the agent whether any execution occurred.【F:agent_tools/tool_trade.py†L1-L189】
- **Price Retrieval (`tool_get_price_local.py`)** – Reads daily OHLCV data from the merged Alpha Vantage archive, validates dates, and surfaces recent sample dates when historical gaps exist.【F:agent_tools/tool_get_price_local.py†L1-L82】
- **Market Intelligence (`tool_jina_search.py`)** – Wraps the Jina search API, filters future-dated articles using the simulation date, and returns structured content snippets for the agent to reason over.【F:agent_tools/tool_jina_search.py†L1-L200】
- **Math (`tool_math.py`)** – Offers lightweight arithmetic helpers primarily to support LangChain tool chaining.【F:agent_tools/tool_math.py†L1-L18】

All services rely on environment variables (`*_HTTP_PORT`, API keys) defined in the README’s configuration guide, aligning with the dynamic MCP URLs assembled inside the agent.【F:README.md†L210-L265】【F:agent/base_agent/base_agent.py†L125-L144】

## Data Management
- **Acquisition & Normalization** – `data/get_daily_price.py` fetches compact Alpha Vantage series for each NASDAQ-100 symbol and the QQQ benchmark. `data/merge_jsonl.py` then harmonizes key names, trims the latest bar to buy prices only, and serializes each ticker’s dataset into a unified JSONL file consumed by both MCP tools and prompt builders.【F:data/get_daily_price.py†L1-L45】【F:data/merge_jsonl.py†L1-L67】
- **Position Storage** – Trade tools append JSONL rows per action under `data/agent_data/{model}/position/position.jsonl`. Helper utilities in `tools/price_tools.py` calculate yesterday’s prices, fetch the most recent holdings, and ensure “no trade” days still generate entries so the dashboard has a continuous timeline.【F:tools/price_tools.py†L224-L349】
- **Runtime Configuration** – `tools/general_tools.py` reads and writes transient configuration values (signature, trade flags, active date) from a JSON file pointed to by `RUNTIME_ENV_PATH`, letting distributed tools share state during a simulation.【F:tools/general_tools.py†L9-L142】

## Frontend & Analytics
The static dashboard under `docs/` loads agent position logs and historical prices directly from the `data` directory. `data-loader.js` fetches each agent’s position timeline, collapses duplicate daily records, computes asset values by replaying closing prices, and derives cumulative returns for visualization via Chart.js.【F:docs/assets/js/data-loader.js†L1-L200】 Complementary HTML/CSS files (`docs/index.html`, `docs/assets/css/styles.css`) render performance comparisons and portfolio analytics advertised in the README.【F:docs/index.html†L1-L80】【F:README.md†L12-L208】

## Configuration Profiles
Default runtime options live in `configs/default_config.json`, defining the agent class, simulation date window, and participating models alongside agent retry limits and initial cash. The `main.py` launcher allows overriding this JSON path and respects environment variables to adjust date ranges at runtime.【F:configs/default_config.json†L1-L49】【F:main.py†L94-L177】

## Notable Observations & Risks
- **Sparse Error Propagation** – Several tool functions print diagnostics when dependencies fail (e.g., `get_latest_position` exceptions in `tool_trade.buy`) but do not surface structured errors back to the agent, risking silent failures during live runs.【F:agent_tools/tool_trade.py†L52-L104】
- **Single-Agent Class Registry** – Only `BaseAgent` is registered in `main.py`, so integrating specialized strategies requires manual registry updates; this may limit extensibility compared to a plugin discovery approach.【F:main.py†L14-L55】
- **Testing Coverage** – The repository lacks automated tests or CI workflows. Given the reliance on real APIs and historical data, adding mocks or replay fixtures would help maintain correctness across tool interfaces and prompt generation.
- **Operational Coupling** – `main.sh` starts MCP services in-process and immediately launches the trading run. For production deployment, separating long-lived services from batch simulations (and adding health gating) would improve resiliency.【F:main.sh†L11-L34】

## Suggested Next Steps
1. Introduce structured logging and exception propagation across MCP tools so agent runs can differentiate recoverable errors from malformed data fetches.
2. Add integration tests that replay a short historical window with stubbed MCP responses to validate the trading loop and position bookkeeping.
3. Modularize agent registration and configuration (e.g., via entry points or config-driven registries) to support custom strategies without editing `main.py`.
4. Consider containerizing MCP services or providing docker-compose manifests so contributors can spin up the environment without manual port coordination.

