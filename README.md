# AI Agents for Omarchy

A comprehensive, native Omarchy status bar panel and widget for tracking AI coding assistants and models.

<p align="center">
  <b>Antigravity (AGY)</b> • <b>Claude Code</b> • <b>OpenAI Codex</b> • <b>GitHub Copilot</b> • <b>Grok CLI</b>
</p>

---

## Features

- **Unified Multi-Agent Dashboard**: Monitor subscription limits, token consumption, and session activity across all your AI assistants in a single panel.
- **Real-Time Rate Limits**:
  - **Claude Code**: Live 5-hour rolling session window and 7-day weekly rate limits with reset countdowns.
  - **OpenAI Codex**: Live primary window (5h) and secondary window (weekly) limits via robust non-blocking RPC.
- **Token Analytics**:
  - **Antigravity (AGY)**: Full Vertex AI session history, Gemini 3.7 Flash & 2.5 Pro token breakdown, and 7-day token history.
  - **Grok CLI**: Local session token consumption, prompt counts, and Grok 4.6 breakdown.
  - **GitHub Copilot**: CLI session tracking, prompt history, and model breakdown.
- **Polished Responsive UI**:
  - Clean tab navigation with automatic button text elision, clipping, and hover tooltips.
  - Status indicators that reflect account readiness without false warning banners.
  - Dark and light theme SVG icons for every agent.
- **Self-Contained & Plug-and-Play**:
  - Bundled collectors—no external helper scripts or manual setup required.
  - Native integration with Omarchy Shell and OmaSettings.

---

## Installation and Removal

Install directly into Omarchy using the `omarchy plugin` CLI:

```bash
omarchy plugin add https://github.com/nertwork/omarchy-ai-agents.git --enable
```

To update to the latest version:

```bash
omarchy plugin update jfarr.agents
```

To remove the plugin:

```bash
omarchy plugin remove jfarr.agents
```

---

## Dependencies

- **Omarchy Desktop / Omarchy Shell**: Required plugin host runtime and top bar container.
- **Python 3**: Uses only the Python standard library for the bundled metrics collector.
- **Optional Provider CLI Tools**: The plugin monitors local session logs and auth states for the tools you have installed:
  - Antigravity (`agy` / Vertex AI ADC credentials)
  - Claude Code (`claude` / Anthropic OAuth)
  - OpenAI Codex (`codex` / ChatGPT session state)
  - GitHub Copilot (`copilot` / GitHub CLI session state)
  - Grok CLI (`grok` / xAI CLI auth state)

---

## Supported Agents

| Agent | Source / Provider | Tracked Metrics |
|---|---|---|
| **Antigravity (AGY)** | Google Vertex AI ADC | Prompts, tokens, sessions, model breakdown (Gemini 3.7 Flash, Pro), 7-day history |
| **Claude Code** | Anthropic OAuth | 5-hour rolling limit, weekly (7-day) limit, session token counts, models |
| **OpenAI Codex** | OpenAI ChatGPT Plus/Pro | 5-hour limit, weekly limit, session counts, model breakdown |
| **GitHub Copilot** | GitHub CLI | Prompts, tokens, active models, 7-day history |
| **Grok CLI** | xAI CLI | Prompts, tokens, Grok 4.6 breakdown, 7-day history |

---

## Shortcuts & Controls

- **Left-Click (Bar Icon)**: Toggle panel open / closed.
- **Middle-Click (Bar Icon)**: Cycle to next active AI agent.
- **Right-Click (Bar Icon)**: Launch default agent selector (`omarchy-agent --pick`).
- **Keyboard Navigation (inside panel)**:
  - `h` / `l` or `Left` / `Right`: Switch agent tabs.
  - `r`: Force immediate refresh of usage and limits.
  - `Esc`: Close panel.

---

## Configuration

You can configure AI Agents via OmaSettings or directly in `~/.config/omarchy/shell.json`:

```json
{
  "id": "jfarr.agents",
  "refreshIntervalSec": 900,
  "providers": {
    "agy": { "enabled": true },
    "claude": { "enabled": true },
    "codex": { "enabled": true },
    "copilot": { "enabled": true },
    "grok": { "enabled": true }
  }
}
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.
