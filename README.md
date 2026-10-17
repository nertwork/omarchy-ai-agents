# AI Agents for Omarchy (`nertwork.agents`)

A comprehensive, native Omarchy status bar panel and widget for tracking AI coding assistants, token consumption, rate limits, and API/subscription spend on `localhost`.

<p align="center">
  <b>Antigravity (AGY)</b> • <b>Claude Code</b> • <b>OpenAI Codex</b> • <b>GitHub Copilot</b> • <b>Grok CLI</b> • <b>Fireworks AI</b>
</p>

<p align="center">
  <img src="preview.png" alt="AI Agents Panel Preview" width="480">
</p>

---

## Features

- **Out-of-the-Box Zero-Config Default**:
  - Works immediately on any Omarchy desktop with `AGY` and `Claude` enabled by default, scanning local session directories (`~/.gemini/antigravity*` and `~/.claude`) on `localhost` with zero remote SSH dependencies.
- **Modular Multi-Profile Architecture (`v2.3.0`)**:
  - **Independent AGY Modules**: Track a single unified AGY profile or split usage across primary (`agy`) and secondary/sandbox (`agy-sandbox`) Google Cloud / Vertex AI projects without double-counting.
  - **Independent Claude Code Modules**: Track a single unified Claude profile (`~/.claude`) or split usage across a primary personal profile (`claude`) and a secondary work/enterprise profile (`fiserv-claude` / `~/.claude-work`) with workspace glob routing.
  - **Combined & Family Rollups**: View individual provider tabs or switch to the **Combined** rollup tab showing localhost grand totals alongside per-family (`AGY Σ`, `Claude Σ`) spend and token summaries.
- **Deep Token & Spend Analytics**:
  - **Antigravity (AGY)**: Local `brain/*/transcript*.jsonl` scanning merged with optional Vertex AI Cloud Monitoring quota metrics, model-level input/output/cache token and cost attribution, 7-day daily activity bars, and per-project breakdowns.
  - **Claude Code**: Live 5-hour rolling session window and 7-day weekly rate limits with reset countdowns, daily prompt and session token totals, model cost attribution, and top workspace breakdowns.
  - **OpenAI Codex**: Live primary window (5h) and secondary window (7d weekly) limits via non-blocking local RPC, daily session counts, and model breakdown.
  - **GitHub Copilot & Grok CLI**: Local CLI session tracking, daily prompt and token totals, 7-day history bars, and model breakdown.
- **Native Responsive UI & In-Panel Settings**:
  - Top bar badge with configurable cost window (`Today`, `7d`, or `30d`) and display mode (`Aggregated Localhost Spend`, `Active Tab Spend`, or `Icon Only`).
  - Built-in **Settings Drawer** directly inside the popup panel (gear icon) plus full **OmaSettings** integration (`Settings.qml`).
  - Dark and light theme SVG icons for every supported provider.

---

## Installation and Removal

Install directly into Omarchy using the `omarchy plugin` CLI:

```bash
omarchy plugin add https://github.com/nertwork/omarchy-ai-agents.git --enable
```

To update to the latest version:

```bash
omarchy plugin update nertwork.agents
```

To remove the plugin:

```bash
omarchy plugin remove nertwork.agents
```

---

## Dependencies

- **Omarchy Desktop / Omarchy Shell**: Required plugin host runtime and top bar container.
- **Python 3**: Uses only the Python standard library for the bundled localhost metrics collector (`bin/collector.py`).
- **Optional Provider CLI Tools**: The plugin monitors local session logs and auth states for the tools you have installed:
  - Antigravity (`agy` / Vertex AI ADC credentials)
  - Claude Code (`claude` / Anthropic OAuth or Enterprise Bedrock)
  - OpenAI Codex (`codex` / ChatGPT session state)
  - GitHub Copilot (`copilot` / GitHub CLI session state)
  - Grok CLI (`grok` / xAI CLI auth state)

---

## Supported Providers & Telemetry

| Module ID | Default Label | Source / Provider | Tracked Metrics & Token Analytics |
|---|---|---|---|
| `agy-personal` | **AGY Personal** | Google OAuth (`antigravity-cli-personal`) | Personal & Homelab (`controller-ai-ops`, `p1-ai-ops`, `smarthome-ai-ops`, `it-titan-*`) session scanning across 5 mesh nodes, Today / 7d / 30d cost & token totals |
| `agy-census` | **AGY Census** | Google OAuth (`antigravity-cli-personal` · CSVD) | Dedicated U.S. Census Bureau (`census-ai-ops`, CSVD / IEBCloud) workspace & session telemetry, Today / 7d / 30d cost & token attribution |
| `agy` | **AGY Clover** | Google Vertex AI (`clover-corp-ai`) | Work (`~/Work`, `clover-ai-ops`, `snv-rtr-ops`, `corp-proxmox`) session scanning + GCP Cloud Monitoring quota metrics |
| `agy-sandbox` | **AGY Sandbox** | Secondary Antigravity GCP Project (`jfar-sandbox`) | Dedicated secondary/sandbox GCP project telemetry, workspace glob routing, independent cost & token attribution |
| `claude` | **Claude** | Claude Code (`~/.claude`) | 5-hour session & 7-day weekly rate limits, Today / 7d / 30d cost & token totals, model breakdown, top workspaces |
| `fiserv-claude` | **Claude Work** | Secondary / Enterprise Claude Profile | Dedicated secondary/work Claude profile (`~/.claude-work` or custom `configDir`) + workspace glob routing, 5h/7d utilization, cost & token attribution |
| `codex` | **Codex** | OpenAI Codex CLI (`~/.codex`) | 5-hour primary & 7-day secondary limit windows, Today / 30d token & session analytics, model breakdown |
| `copilot` | **Copilot** | GitHub Copilot CLI (`~/.copilot`) | Daily prompts & sessions, output & cache-read tokens, 7-day history, model breakdown |
| `grok` | **Grok** | xAI Grok CLI (`~/.grok`) | Daily prompts & sessions, input/output/cached tokens, 7-day history, model breakdown |

---

## Shortcuts & Controls

- **Left-Click (Bar Badge)**: Toggle the AI Agents dashboard panel open or closed.
- **Middle-Click (Bar Badge)**: Cycle to the next enabled AI agent module.
- **Scroll Wheel (Bar Badge)**: Cycle forward/backward through enabled modules.
- **Sync Nodes Button (Panel Header / Active Nodes Card)**: Trigger an immediate multi-node telemetry sync across all 5 mesh hosts (`james-mbp1`, `controller`, `gpu01`, `netctl1`, `netctl2`).
- **Gear Icon (Panel Header)**: Toggle the in-panel modular Settings Drawer.
- **3-Way Environment Profile Classification & Quick Launchers**:
  - **Work (`~/Work`, Clover/Fiserv repos)** — Classified under `work` (`agy` / `AGY · Clover`, `fiserv-claude`). Launch via **`SUPER + ALT + A`**, `omarchy-agent-work`, `omarchy-agent`, `agy-clover`, or the **Work (`~/Work`)** chip in the panel.
  - **Census (`~/projects/census-ai-ops`)** — Classified under `census` (`agy-census` / `AGY · Census`). Launch via **`SUPER + ALT + C`**, `omarchy-agent-census`, `agy-census`, or the **Census (`CSVD`)** chip in the panel.
  - **Personal / Homelab (`~/projects/controller-ai-ops`, homelab repos)** — Classified under `personal` (`agy-personal` / `AGY · Personal`, `claude`). Launch via **`SUPER + ALT + H`**, `omarchy-agent-controller`, `agy-personal`, or the **Homelab (`Ops`)** chip in the panel.
- **Zero-Idle-CPU Incremental Telemetry Cache**:
  - `bin/collector.py` uses an incremental `st_mtime_ns + st_size` per-file cache (`~/.cache/omarchy/agent-usage-transcript-cache-v4.json`), cutting warm collector refreshes to `<0.2s` with `0%` background CPU between 120s timer ticks.
- **IPC Commands**:
  - `omarchy-shell nertwork.agents toggle` — Toggle panel visibility.
  - `omarchy-shell nertwork.agents refresh` — Trigger an immediate collector refresh.
  - `omarchy-shell nertwork.agents cycle` — Cycle active provider tab.
  - `omarchy-shell nertwork.agents select <id|combined>` — Select a specific module tab or the Combined view.
  - `omarchy-shell nertwork.agents status` — Print live JSON status of enabled modules and aggregated totals.

---

## Configuration & Multi-Profile Customization

All modules and display options can be toggled live from the **in-panel Settings gear button** or **OmaSettings**. Settings are stored in `~/.local/state/omarchy/settings/nertwork.agents.json` and `~/.config/omarchy/agents/profiles.json`.

### Optional Multi-Profile Example (`~/.config/omarchy/agents/profiles.json`)

To customize labels, GCP projects, config directories, or workspace routing globs for split `AGY` and `Claude` profiles:

```json
{
  "schemaVersion": 2,
  "localhostOnly": true,
  "aggregateByDefault": true,
  "showAggregatedSummary": true,
  "barDisplayMode": "aggregated",
  "showBarCost": true,
  "barCostWindow": "30d",
  "providers": {
    "agy": {
      "enabled": true,
      "profile": "my-gcp-prod",
      "label": "AGY",
      "shortLabel": "AGY · Prod",
      "displayName": "Antigravity (Prod)",
      "badge": "my-gcp-prod",
      "gcpProject": "my-gcp-prod",
      "description": "Antigravity CLI · my-gcp-prod"
    },
    "agy-sandbox": {
      "enabled": true,
      "profile": "my-gcp-sandbox",
      "label": "AGY Sandbox",
      "shortLabel": "AGY · Sandbox",
      "displayName": "Antigravity (Sandbox)",
      "badge": "my-gcp-sandbox",
      "gcpProject": "my-gcp-sandbox",
      "description": "Antigravity CLI · my-gcp-sandbox"
    },
    "fiserv-claude": {
      "enabled": true,
      "profile": "work",
      "label": "Claude Work",
      "shortLabel": "Claude · Work",
      "displayName": "Claude Code (Work)",
      "badge": "work",
      "configDir": "~/.claude-work",
      "authMode": "AWS Bedrock / Enterprise",
      "tierPrefix": "Enterprise",
      "dirs": ["~/.claude-work"],
      "sharedProjectGlobs": ["*work-*", "*enterprise-*"]
    },
    "claude": {
      "enabled": true,
      "profile": "personal",
      "label": "Claude",
      "shortLabel": "Claude",
      "displayName": "Claude Code (Personal)",
      "badge": "personal",
      "configDir": "~/.claude",
      "dirs": ["~/.claude"]
    }
  }
}
```

### Environment Variables (Optional)

- `OMARCHY_AGY_PROJECTS`: Comma-separated GCP projects to query via Vertex AI Cloud Monitoring.
- `OMARCHY_AGY_DIRS`: Colon/comma-separated extra Antigravity directories to scan alongside `~/.gemini/antigravity-cli`.
- `OMARCHY_CLAUDE_DIRS`: Colon/comma-separated extra Claude Code profile directories to scan alongside `~/.claude`.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
