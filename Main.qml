import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons

Item {
  id: root
  visible: false
  width: 0
  height: 0

  property var settings: null
  property int selectedIndex: 0
  property bool showCombinedView: false

  readonly property string homeDir: Quickshell.env("HOME") || ""
  readonly property string stateHome: Quickshell.env("XDG_STATE_HOME") || (homeDir + "/.local/state")
  readonly property string configHome: Quickshell.env("XDG_CONFIG_HOME") || (homeDir + "/.config")
  readonly property string usageDir: stateHome + "/omarchy/agents/usage"
  readonly property string legacyUsageDir: stateHome + "/omarchy/agent-usage"
  readonly property string stateSettingsPath: stateHome + "/omarchy/settings/nertwork.agents.json"
  readonly property string profilesConfigPath: configHome + "/omarchy/agents/profiles.json"
  readonly property string legacyAgentsConfigPath: configHome + "/omarchy/agents.json"
  readonly property string pluginDir: Qt.resolvedUrl(".").toString().replace(/^file:\/\//, "").replace(/\/$/, "")
  readonly property string bundledUpdateBin: pluginDir + "/bin/update-all"

  readonly property var providerMeta: ({
    "agy": {
      id: "agy",
      label: "AGY",
      shortLabel: "AGY",
      displayName: "Antigravity (Primary)",
      badge: "primary",
      family: "agy",
      familyLabel: "AGY",
      profile: "default",
      icon: "agy",
      command: "agy",
      description: "Antigravity CLI · Primary profile",
      order: 10,
      defaultEnabled: true
    },
    "agy-sandbox": {
      id: "agy-sandbox",
      label: "AGY Sandbox",
      shortLabel: "AGY · Sandbox",
      displayName: "Antigravity (Sandbox)",
      badge: "sandbox",
      family: "agy",
      familyLabel: "AGY",
      profile: "sandbox",
      icon: "agy",
      command: "agy",
      description: "Antigravity CLI · Secondary/Sandbox GCP project",
      order: 11,
      defaultEnabled: false
    },
    "fiserv-claude": {
      id: "fiserv-claude",
      label: "Claude Work",
      shortLabel: "Claude · Work",
      displayName: "Claude Code (Work)",
      badge: "work",
      family: "claude",
      familyLabel: "Claude",
      profile: "work",
      icon: "claude",
      command: "claude",
      description: "Claude Code · Secondary/Work profile (~/.claude-work)",
      order: 20,
      defaultEnabled: false
    },
    "claude": {
      id: "claude",
      label: "Claude",
      shortLabel: "Claude",
      displayName: "Claude Code (Personal)",
      badge: "personal",
      family: "claude",
      familyLabel: "Claude",
      profile: "personal",
      icon: "claude",
      command: "claude",
      description: "Claude Code · ~/.claude",
      order: 21,
      defaultEnabled: true
    },
    "codex": {
      id: "codex",
      label: "Codex",
      shortLabel: "Codex",
      displayName: "OpenAI Codex",
      badge: "openai",
      family: "codex",
      familyLabel: "Codex",
      profile: "default",
      icon: "codex",
      command: "codex",
      description: "OpenAI Codex CLI",
      order: 30,
      defaultEnabled: false
    },
    "copilot": {
      id: "copilot",
      label: "Copilot",
      shortLabel: "Copilot",
      displayName: "GitHub Copilot",
      badge: "github",
      family: "copilot",
      familyLabel: "Copilot",
      profile: "default",
      icon: "copilot",
      command: "copilot",
      description: "GitHub Copilot CLI",
      order: 40,
      defaultEnabled: false
    },
    "cursor": {
      id: "cursor",
      label: "Cursor",
      shortLabel: "Cursor",
      displayName: "Cursor Agent",
      badge: "ide",
      family: "cursor",
      familyLabel: "Cursor",
      profile: "default",
      icon: "codex",
      command: "cursor",
      description: "Cursor IDE Agent",
      order: 50,
      defaultEnabled: false
    },
    "gemini": {
      id: "gemini",
      label: "Gemini",
      shortLabel: "Gemini",
      displayName: "Gemini CLI",
      badge: "google",
      family: "gemini",
      familyLabel: "Gemini",
      profile: "default",
      icon: "agy",
      command: "gemini",
      description: "Google Gemini CLI",
      order: 60,
      defaultEnabled: false
    },
    "opencode": {
      id: "opencode",
      label: "OpenCode",
      shortLabel: "OpenCode",
      displayName: "OpenCode",
      badge: "cli",
      family: "opencode",
      familyLabel: "OpenCode",
      profile: "default",
      icon: "codex",
      command: "opencode",
      description: "OpenCode CLI",
      order: 70,
      defaultEnabled: false
    },
    "openrouter": {
      id: "openrouter",
      label: "OpenRouter",
      shortLabel: "OpenRouter",
      displayName: "OpenRouter",
      badge: "api",
      family: "openrouter",
      familyLabel: "OpenRouter",
      profile: "default",
      icon: "fireworks",
      command: "openrouter",
      description: "OpenRouter API",
      order: 80,
      defaultEnabled: false
    },
    "zaicodingplan": {
      id: "zaicodingplan",
      label: "Z.ai",
      shortLabel: "Z.ai",
      displayName: "Z.ai Coding Plan",
      badge: "glm",
      family: "zaicodingplan",
      familyLabel: "Z.ai",
      profile: "default",
      icon: "fireworks",
      command: "zai",
      description: "Z.ai Coding Plan",
      order: 90,
      defaultEnabled: false
    },
    "grok": {
      id: "grok",
      label: "Grok",
      shortLabel: "Grok",
      displayName: "Grok CLI",
      badge: "xai",
      family: "grok",
      familyLabel: "Grok",
      profile: "default",
      icon: "grok",
      command: "grok",
      description: "xAI Grok CLI",
      order: 100,
      defaultEnabled: false
    },
    "fireworks": {
      id: "fireworks",
      label: "Fireworks",
      shortLabel: "Fireworks",
      displayName: "Fireworks AI",
      badge: "firectl",
      family: "fireworks",
      familyLabel: "Fireworks",
      profile: "default",
      icon: "fireworks",
      command: "firectl",
      description: "Fireworks AI CLI",
      order: 110,
      defaultEnabled: false
    }
  })

  readonly property var orderedProviderIds: [
    "agy",
    "agy-sandbox",
    "fiserv-claude",
    "claude",
    "codex",
    "copilot",
    "cursor",
    "gemini",
    "opencode",
    "openrouter",
    "zaicodingplan",
    "grok",
    "fireworks"
  ]

  property var stateSettingsData: ({})
  property var profilesConfigData: ({})
  property var localSettingsOverride: ({})
  property var summaryPayload: ({})

  readonly property var effectiveSettings: {
    var merged = {
      localhostOnly: true,
      aggregateByDefault: true,
      showAggregatedSummary: true,
      barDisplayMode: "aggregated",
      showBarCost: true,
      barCostWindow: "30d",
      pollIntervalSeconds: 300,
      terminalCommand: "",
      providers: {}
    }

    var i = 0
    for (i = 0; i < orderedProviderIds.length; i++) {
      var pid = orderedProviderIds[i]
      var meta = providerMeta[pid]
      merged.providers[pid] = {
        enabled: meta ? !!meta.defaultEnabled : false,
        profile: meta ? meta.profile : "default",
        label: meta ? meta.label : pid
      }
    }

    function applySource(src) {
      if (!src || typeof src !== "object") return
      if (src.localhostOnly !== undefined) merged.localhostOnly = !!src.localhostOnly
      if (src.aggregateByDefault !== undefined) merged.aggregateByDefault = !!src.aggregateByDefault
      if (src.showAggregatedSummary !== undefined) merged.showAggregatedSummary = !!src.showAggregatedSummary
      if (src.barDisplayMode !== undefined && String(src.barDisplayMode).trim() !== "")
        merged.barDisplayMode = String(src.barDisplayMode).trim()
      if (src.showBarCost !== undefined) merged.showBarCost = !!src.showBarCost
      if (src.barCostWindow !== undefined && String(src.barCostWindow).trim() !== "")
        merged.barCostWindow = String(src.barCostWindow).trim()
      if (src.pollIntervalSeconds !== undefined && !isNaN(Number(src.pollIntervalSeconds)))
        merged.pollIntervalSeconds = Number(src.pollIntervalSeconds)
      if (src.terminalCommand !== undefined)
        merged.terminalCommand = String(src.terminalCommand || "")

      if (src.enabledAgents instanceof Array && !src.providers) {
        for (var j = 0; j < orderedProviderIds.length; j++) {
          var idKey = orderedProviderIds[j]
          merged.providers[idKey].enabled = src.enabledAgents.indexOf(idKey) !== -1
        }
      }

      if (src.providers && typeof src.providers === "object") {
        var pKeys = Object.keys(src.providers)
        for (var k = 0; k < pKeys.length; k++) {
          var pk = pKeys[k]
          var pv = src.providers[pk]
          if (!merged.providers[pk]) {
            merged.providers[pk] = { enabled: false, profile: "default", label: pk }
          }
          if ( typeof pv === "boolean" ) {
            merged.providers[pk].enabled = pv
          } else if (pv && typeof pv === "object") {
            var pvKeys = Object.keys(pv)
            for (var m = 0; m < pvKeys.length; m++) {
              var pvk = pvKeys[m]
              if (pv[pvk] !== undefined) {
                merged.providers[pk][pvk] = pv[pvk]
              }
            }
            if (pv.enabled !== undefined) merged.providers[pk].enabled = !!pv.enabled
            if (pv.profile) merged.providers[pk].profile = String(pv.profile)
            if (pv.label) merged.providers[pk].label = String(pv.label)
          }
        }
      }
    }

    // Apply in priority order: injected shell defaults < profiles.json < state settings < runtime overrides
    applySource(root.settings)
    applySource(root.profilesConfigData)
    applySource(root.stateSettingsData)
    applySource(root.localSettingsOverride)

    return merged
  }

  readonly property bool localhostOnly: !!effectiveSettings.localhostOnly
  readonly property bool aggregateByDefault: !!effectiveSettings.aggregateByDefault
  readonly property bool showAggregatedSummary: !!effectiveSettings.showAggregatedSummary
  readonly property string barDisplayMode: String(effectiveSettings.barDisplayMode || "aggregated")
  readonly property bool showBarCost: effectiveSettings.showBarCost !== undefined ? !!effectiveSettings.showBarCost : true
  readonly property string barCostWindow: String(effectiveSettings.barCostWindow || "30d")
  readonly property int pollIntervalSeconds: Math.max(60, Math.min(3600, Number(effectiveSettings.pollIntervalSeconds || 300)))
  readonly property string terminalCommand: String(effectiveSettings.terminalCommand || "").trim()

  property var discoveredFileIds: []
  property var rawPayloads: ({})
  property bool refreshing: false
  readonly property alias isRefreshing: root.refreshing
  property bool refreshQueued: false
  property bool refreshQueuedForce: false
  property string saveScriptPayload: ""

  function isProviderEnabled(providerId) {
    var id = String(providerId || "").toLowerCase()
    var pMap = effectiveSettings.providers || {}
    if (pMap[id] !== undefined) {
      return !!pMap[id].enabled
    }
    var meta = providerMeta[id]
    return meta ? !!meta.defaultEnabled : false
  }

  function persistSettingsObject(updatedObj) {
    root.localSettingsOverride = updatedObj
    var jsonStr = JSON.stringify(updatedObj, null, 2)
    root.saveScriptPayload = jsonStr
    if (!saveSettingsProcess.running) {
      saveSettingsProcess.running = true
    }
  }

  function setProviderEnabled(providerId, enabled) {
    var id = String(providerId || "").toLowerCase()
    var next = JSON.parse(JSON.stringify(effectiveSettings))
    if (!next.providers) next.providers = {}
    if (!next.providers[id]) {
      var meta = providerMeta[id]
      next.providers[id] = {
        enabled: !!enabled,
        profile: meta ? meta.profile : "default",
        label: meta ? meta.label : id
      }
    } else {
      next.providers[id].enabled = !!enabled
    }
    var enabledList = []
    for (var i = 0; i < orderedProviderIds.length; i++) {
      var k = orderedProviderIds[i]
      if (next.providers[k] && next.providers[k].enabled) {
        enabledList.push(k)
      }
    }
    next.enabledAgents = enabledList
    persistSettingsObject(next)
    refreshAll(false)
  }

  function setSetting(key, value) {
    var next = JSON.parse(JSON.stringify(effectiveSettings))
    next[key] = value
    persistSettingsObject(next)
  }

  Process {
    id: saveSettingsProcess
    running: false
    command: [
      "python3",
      "-c",
      "import json, os, sys; from pathlib import Path\n" +
      "raw = sys.argv[1]\n" +
      "data = json.loads(raw)\n" +
      "for p_str in [sys.argv[2], sys.argv[3]]:\n" +
      "    p = Path(p_str)\n" +
      "    p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)\n" +
      "    existing = {}\n" +
      "    if p.exists():\n" +
      "        try:\n" +
      "            existing = json.loads(p.read_text(encoding='utf-8'))\n" +
      "        except Exception:\n" +
      "            existing = {}\n" +
      "    if isinstance(existing, dict):\n" +
      "        old_p = existing.get('providers') if isinstance(existing.get('providers'), dict) else {}\n" +
      "        existing.update(data)\n" +
      "        if isinstance(data.get('providers'), dict):\n" +
      "            mp = dict(old_p)\n" +
      "            for k, v in data['providers'].items():\n" +
      "                mp[k] = {**mp[k], **v} if (isinstance(mp.get(k), dict) and isinstance(v, dict)) else v\n" +
      "            existing['providers'] = mp\n" +
      "        p.write_text(json.dumps(existing, indent=2) + '\\n', encoding='utf-8')\n" +
      "    else:\n" +
      "        p.write_text(json.dumps(data, indent=2) + '\\n', encoding='utf-8')\n" +
      "    try:\n" +
      "        p.chmod(0o600)\n" +
      "    except OSError:\n" +
      "        pass\n",
      root.saveScriptPayload,
      root.stateSettingsPath,
      root.profilesConfigPath
    ]
  }

  FileView {
    id: stateSettingsView
    path: root.stateSettingsPath
    watchChanges: true
    printErrors: false
    onLoaded: {
      try {
        var parsed = JSON.parse(text())
        if (parsed && typeof parsed === "object") root.stateSettingsData = parsed
      } catch (e) {}
    }
    onFileChanged: reload()
  }

  FileView {
    id: profilesConfigView
    path: root.profilesConfigPath
    watchChanges: true
    printErrors: false
    onLoaded: {
      try {
        var parsed = JSON.parse(text())
        if (parsed && typeof parsed === "object") root.profilesConfigData = parsed
      } catch (e) {}
    }
    onFileChanged: reload()
  }

  FileView {
    id: summaryFileView
    path: root.usageDir + "/_summary.json"
    watchChanges: true
    printErrors: false
    onLoaded: {
      try {
        var parsed = JSON.parse(text())
        if (parsed && typeof parsed === "object") root.summaryPayload = parsed
      } catch (e) {}
    }
    onFileChanged: reload()
  }

  // Build list of JSON files to watch in ~/.local/state/omarchy/agents/usage/
  readonly property var watchedFileIds: {
    var set = {}
    var list = []
    var i = 0
    for (i = 0; i < orderedProviderIds.length; i++) {
      var pid = orderedProviderIds[i]
      set[pid] = true
      list.push(pid)
    }
    for (i = 0; i < discoveredFileIds.length; i++) {
      var fid = discoveredFileIds[i]
      if (!fid || fid.charAt(0) === "_") continue
      if (!set[fid]) {
        set[fid] = true
        list.push(fid)
      }
    }
    return list
  }

  readonly property var allProviders: {
    var list = []
    for (var i = 0; i < orderedProviderIds.length; i++) {
      var id = orderedProviderIds[i]
      var rec = normalizedRecord(id)
      if (rec) list.push(rec)
    }
    return list
  }

  readonly property var enabledProviders: {
    var list = []
    for (var i = 0; i < allProviders.length; i++) {
      var p = allProviders[i]
      if (p && p.enabled) {
        list.push(p)
      }
    }
    return list
  }

  // Backward-compatible alias
  readonly property alias visibleProviders: root.enabledProviders

  readonly property real aggregatedTotalTodayCost: {
    var sum = 0
    for (var i = 0; i < enabledProviders.length; i++) {
      sum += Number(enabledProviders[i].todayCostUsd || 0)
    }
    return sum
  }

  readonly property real aggregatedTotal7dCost: {
    var sum = 0
    for (var i = 0; i < enabledProviders.length; i++) {
      sum += Number(enabledProviders[i].sevenDayCostUsd || 0)
    }
    return sum
  }

  readonly property real aggregatedTotal30dCost: {
    var sum = 0
    for (var i = 0; i < enabledProviders.length; i++) {
      sum += Number(enabledProviders[i].thirtyDayCostUsd || 0)
    }
    return sum
  }

  readonly property double aggregatedTotalTodayTokens: {
    var sum = 0
    for (var i = 0; i < enabledProviders.length; i++) {
      sum += Number(enabledProviders[i].todayTotalTokens || 0)
    }
    return sum
  }

  readonly property double aggregatedTotal7dTokens: {
    var sum = 0
    for (var i = 0; i < enabledProviders.length; i++) {
      sum += Number(enabledProviders[i].sevenDayTokens || 0)
    }
    return sum
  }

  readonly property double aggregatedTotal30dTokens: {
    var sum = 0
    for (var i = 0; i < enabledProviders.length; i++) {
      sum += Number(enabledProviders[i].thirtyDayTokens || 0)
    }
    return sum
  }

  readonly property int aggregatedTodayPrompts: {
    var sum = 0
    for (var i = 0; i < enabledProviders.length; i++) {
      sum += Number(enabledProviders[i].todayPrompts || 0)
    }
    return sum
  }

  readonly property int aggregatedTodaySessions: {
    var sum = 0
    for (var i = 0; i < enabledProviders.length; i++) {
      sum += Number(enabledProviders[i].todaySessions || 0)
    }
    return sum
  }

  readonly property int aggregatedTotalPrompts30d: {
    var sum = 0
    for (var i = 0; i < enabledProviders.length; i++) {
      sum += Number(enabledProviders[i].totalPrompts || 0)
    }
    return sum
  }

  readonly property int aggregatedTotalSessions30d: {
    var sum = 0
    for (var i = 0; i < enabledProviders.length; i++) {
      sum += Number(enabledProviders[i].totalSessions || 0)
    }
    return sum
  }

  function familyTotals(familyName) {
    var fam = String(familyName || "").toLowerCase()
    var todayCost = 0
    var sevenDayCost = 0
    var thirtyDayCost = 0
    var todayTok = 0
    var sevenDayTok = 0
    var thirtyDayTok = 0
    var enabledCount = 0

    for (var i = 0; i < enabledProviders.length; i++) {
      var p = enabledProviders[i]
      if (p && p.family === fam) {
        enabledCount += 1
        todayCost += Number(p.todayCostUsd || 0)
        sevenDayCost += Number(p.sevenDayCostUsd || 0)
        thirtyDayCost += Number(p.thirtyDayCostUsd || 0)
        todayTok += Number(p.todayTotalTokens || 0)
        sevenDayTok += Number(p.sevenDayTokens || 0)
        thirtyDayTok += Number(p.thirtyDayTokens || 0)
      }
    }

    return {
      family: fam,
      count: enabledCount,
      todayCostUsd: todayCost,
      sevenDayCostUsd: sevenDayCost,
      thirtyDayCostUsd: thirtyDayCost,
      todayTokens: todayTok,
      sevenDayTokens: sevenDayTok,
      thirtyDayTokens: thirtyDayTok
    }
  }

  readonly property var agyFamilyTotals: familyTotals("agy")
  readonly property var claudeFamilyTotals: familyTotals("claude")

  // Synthesizes a combined virtual provider across all enabled modules for "Combined" view mode
  readonly property var combinedProvider: {
    var dayMap = {}
    var dayOrder = []
    var combinedModels = []
    var combinedBreakdowns = []
    var latestUpdated = ""

    for (var i = 0; i < enabledProviders.length; i++) {
      var p = enabledProviders[i]
      if (!p) continue
      if (p.updatedAt && (!latestUpdated || String(p.updatedAt) > latestUpdated)) {
        latestUpdated = String(p.updatedAt)
      }
      var rDays = p.recentDays || []
      for (var d = 0; d < rDays.length; d++) {
        var dayEntry = rDays[d]
        if (!dayEntry || !dayEntry.date) continue
        var ds = String(dayEntry.date)
        if (!dayMap[ds]) {
          dayMap[ds] = {
            date: ds,
            tokens: 0,
            messageCount: 0,
            prompts: 0,
            sessions: 0,
            costUsd: 0
          }
          dayOrder.push(ds)
        }
        dayMap[ds].tokens += Number(dayEntry.tokens !== undefined ? dayEntry.tokens : (dayEntry.messageCount || 0))
        dayMap[ds].messageCount = dayMap[ds].tokens
        dayMap[ds].prompts += Number(dayEntry.prompts || 0)
        dayMap[ds].sessions += Number(dayEntry.sessions || 0)
        dayMap[ds].costUsd += Number(dayEntry.costUsd !== undefined ? dayEntry.costUsd : (dayEntry.costUSD || 0))
      }

      var mList = p.modelRows || []
      for (var m = 0; m < mList.length; m++) {
        var mr = mList[m]
        combinedModels.push({
          id: p.shortLabel + " · " + mr.label,
          label: mr.label,
          moduleLabel: p.shortLabel,
          family: p.family,
          inputTokens: mr.inputTokens,
          outputTokens: mr.outputTokens,
          cacheTokens: mr.cacheTokens,
          totalTokens: mr.totalTokens,
          costUsd: mr.costUsd
        })
      }

      combinedBreakdowns.push({
        project: p.shortLabel,
        badge: p.badge,
        scope: "localhost_module",
        localTokensToday: p.todayTotalTokens,
        localTokens7d: p.sevenDayTokens,
        localTokens30d: p.thirtyDayTokens,
        localCostUsdToday: p.todayCostUsd,
        localCostUsd7d: p.sevenDayCostUsd,
        localCostUsd30d: p.thirtyDayCostUsd,
        localSessions30d: p.totalSessions,
        tokens30d: p.sharedOrgTokens30d || p.thirtyDayTokens,
        sharePct: aggregatedTotal30dCost > 0 ? Math.round((p.thirtyDayCostUsd / aggregatedTotal30dCost) * 1000) / 10 : 0
      })
    }

    dayOrder.sort()
    if (dayOrder.length > 7) {
      dayOrder = dayOrder.slice(dayOrder.length - 7)
    }
    var mergedDays = []
    for (var j = 0; j < dayOrder.length; j++) {
      mergedDays.push(dayMap[dayOrder[j]])
    }

    combinedModels.sort(function(a, b) {
      if (b.costUsd !== a.costUsd) return b.costUsd - a.costUsd
      return b.totalTokens - a.totalTokens
    })

    return {
      id: "combined",
      name: "All Enabled Agents",
      shortLabel: "All Modules",
      badge: enabledProviders.length + " modules",
      family: "combined",
      profile: "localhost",
      icon: "agy",
      enabled: true,
      ready: enabledProviders.length > 0,
      hasLocalStats: true,
      hasPromptStats: true,
      updatedAt: latestUpdated,
      tierLabel: "Localhost Combined",
      usageStatusText: "",
      authHelpText: "",
      activeModel: enabledProviders.length + " active profiles",
      limits: [],
      todayCostUsd: aggregatedTotalTodayCost,
      sevenDayCostUsd: aggregatedTotal7dCost,
      thirtyDayCostUsd: aggregatedTotal30dCost,
      todayTotalTokens: aggregatedTotalTodayTokens,
      sevenDayTokens: aggregatedTotal7dTokens,
      thirtyDayTokens: aggregatedTotal30dTokens,
      todayPrompts: aggregatedTodayPrompts,
      todaySessions: aggregatedTodaySessions,
      totalPrompts: aggregatedTotalPrompts30d,
      totalSessions: aggregatedTotalSessions30d,
      activeDays: mergedDays.length,
      recentDays: mergedDays,
      modelRows: combinedModels.slice(0, 8),
      projectsBreakdown: combinedBreakdowns,
      sharedOrgTokens30d: 0
    }
  }

  readonly property var currentProvider: {
    if (showCombinedView && enabledProviders.length > 1) {
      return combinedProvider
    }
    if (!enabledProviders || enabledProviders.length === 0) return null
    var idx = Math.max(0, Math.min(selectedIndex, enabledProviders.length - 1))
    return enabledProviders[idx]
  }

  onEnabledProvidersChanged: {
    if (enabledProviders.length === 0) {
      selectedIndex = 0
    } else if (selectedIndex >= enabledProviders.length) {
      selectedIndex = 0
    }
  }

  Component.onCompleted: {
    rescanFiles()
    refreshAll(false)
  }

  function selectProvider(index) {
    if (!enabledProviders || enabledProviders.length === 0) {
      selectedIndex = 0
      return
    }
    showCombinedView = false
    selectedIndex = Math.max(0, Math.min(index, enabledProviders.length - 1))
  }

  function selectProviderById(id) {
    var target = String(id || "").toLowerCase()
    if (target === "combined" || target === "all") {
      showCombinedView = true
      return
    }
    for (var i = 0; i < enabledProviders.length; i++) {
      if (enabledProviders[i].id === target) {
        showCombinedView = false
        selectedIndex = i
        return
      }
    }
  }

  function cycleProvider(step) {
    if (!enabledProviders || enabledProviders.length === 0) return
    var count = enabledProviders.length
    var delta = Number(step || 1)
    showCombinedView = false
    selectedIndex = (selectedIndex + delta % count + count) % count
  }

  function refreshAll(force) {
    var wantForce = !!force
    if (refreshProcess.running) {
      refreshQueued = true
      refreshQueuedForce = refreshQueuedForce || wantForce
      return
    }
    refreshing = true
    var cmd = [root.bundledUpdateBin]
    if (wantForce) cmd.push("--force")
    refreshProcess.command = cmd
    refreshProcess.running = true
  }

  function reloadFiles() {
    for (var i = 0; i < fileWatchers.count; i++) {
      var watcher = fileWatchers.itemAt(i)
      if (watcher && typeof watcher.reload === "function") {
        watcher.reload()
      }
    }
    summaryFileView.reload()
  }

  function rescanFiles() {
    if (!scanFilesProcess.running) {
      scanFilesProcess.running = true
    }
  }

  readonly property real barDisplayCostValue: {
    var win = root.barCostWindow
    if (root.barDisplayMode === "active" && root.currentProvider) {
      if (win === "today") return Number(root.currentProvider.todayCostUsd || 0)
      if (win === "7d") return Number(root.currentProvider.sevenDayCostUsd || 0)
      return Number(root.currentProvider.thirtyDayCostUsd || 0)
    }
    if (win === "today") return Number(root.aggregatedTotalTodayCost || 0)
    if (win === "7d") return Number(root.aggregatedTotal7dCost || 0)
    return Number(root.aggregatedTotal30dCost || 0)
  }

  readonly property string barCostLabel: {
    if (!root.showBarCost || root.barDisplayMode === "icon") return ""
    return root.formatUsd(root.barDisplayCostValue, true)
  }

  readonly property string barTooltipText: {
    if (root.enabledProviders.length === 0) return "AI Agents · No modules enabled"
    var totalLine = "Localhost Total: Today " + root.formatUsd(root.aggregatedTotalTodayCost, false)
      + " · 7d " + root.formatUsd(root.aggregatedTotal7dCost, false)
      + " · 30d " + root.formatUsd(root.aggregatedTotal30dCost, false)
    if (root.currentProvider) {
      return root.currentProvider.shortLabel + " (" + root.formatUsd(root.currentProvider.thirtyDayCostUsd, false) + " 30d)  |  " + totalLine
    }
    return totalLine
  }

  function providersByGroup(groupName) {
    var out = []
    var g = String(groupName || "").toLowerCase()
    for (var i = 0; i < root.allProviders.length; i++) {
      var p = root.allProviders[i]
      var pf = String(p.family || "other").toLowerCase()
      if (g === "agy" && pf === "agy") out.push(p)
      else if (g === "claude" && pf === "claude") out.push(p)
      else if (g === "other" && pf !== "agy" && pf !== "claude") out.push(p)
    }
    return out
  }

  function statusJson() {
    var mods = []
    for (var i = 0; i < root.enabledProviders.length; i++) {
      var p = root.enabledProviders[i]
      mods.push({
        id: p.id,
        shortLabel: p.shortLabel,
        profile: p.profile,
        todayCostUsd: p.todayCostUsd,
        sevenDayCostUsd: p.sevenDayCostUsd,
        thirtyDayCostUsd: p.thirtyDayCostUsd,
        todayTokens: p.todayTotalTokens,
        sevenDayTokens: p.sevenDayTokens,
        thirtyDayTokens: p.thirtyDayTokens
      })
    }
    return JSON.stringify({
      localhostOnly: root.localhostOnly,
      showAggregatedSummary: root.showAggregatedSummary,
      barDisplayMode: root.barDisplayMode,
      barCostLabel: root.barCostLabel,
      aggregatedTodayCostUsd: root.aggregatedTotalTodayCost,
      aggregated7dCostUsd: root.aggregatedTotal7dCost,
      aggregated30dCostUsd: root.aggregatedTotal30dCost,
      aggregated30dTokens: root.aggregatedTotal30dTokens,
      agyFamilyTodayCostUsd: root.agyFamilyTotals.todayCostUsd,
      agyFamily30dCostUsd: root.agyFamilyTotals.thirtyDayCostUsd,
      claudeFamilyTodayCostUsd: root.claudeFamilyTotals.todayCostUsd,
      claudeFamily30dCostUsd: root.claudeFamilyTotals.thirtyDayCostUsd,
      enabledCount: root.enabledProviders.length,
      enabledModules: mods
    })
  }

  function defaultNameForId(id) {
    var key = String(id || "").toLowerCase()
    var meta = providerMeta[key]
    if (meta && meta.label) return meta.label
    if (key.length === 0) return "Agent"
    return key.charAt(0).toUpperCase() + key.slice(1)
  }

  function findProjectBreakdownEntry(list, projectKey) {
    if (!(list instanceof Array)) return null
    var target = String(projectKey || "").toLowerCase()
    if (!target) return null
    for (var i = 0; i < list.length; i++) {
      var item = list[i]
      if (!item) continue
      var pName = String(item.project || item.profile || item.id || "").toLowerCase()
      var pId = String(item.profileId || "").toLowerCase()
      if (pName === target || pId === target || (target === "personal" && pName.indexOf("personal") !== -1)) {
        return item
      }
    }
    return null
  }

  function scaleRecentDays(days, ratio, total7dCost, total7dTokens) {
    if (!(days instanceof Array)) return []
    var r = Math.max(0, Math.min(1, Number(ratio || 0)))
    var out = []
    for (var i = 0; i < days.length; i++) {
      var d = days[i]
      if (!d) continue
      var rawTok = Number(d.tokens !== undefined ? d.tokens : (d.messageCount || 0))
      var rawCost = Number(d.costUsd !== undefined ? d.costUsd : (d.costUSD || 0))
      var scaledTok = Math.round(rawTok * r)
      var scaledCost = Math.round(rawCost * r * 100) / 100
      out.push({
        date: String(d.date || ""),
        tokens: scaledTok,
        messageCount: scaledTok,
        prompts: Math.round(Number(d.prompts || 0) * r),
        sessions: Math.round(Number(d.sessions || 0) * r),
        costUsd: scaledCost,
        costUSD: scaledCost
      })
    }
    return out
  }

  function buildModelRows(modelUsageMap, projectModels, costScaleRatio) {
    var rows = []
    var scale = (costScaleRatio !== undefined && costScaleRatio !== null) ? Number(costScaleRatio) : 1.0

    if (modelUsageMap && typeof modelUsageMap === "object" && Object.keys(modelUsageMap).length > 0) {
      var keys = Object.keys(modelUsageMap)
      for (var i = 0; i < keys.length; i++) {
        var k = keys[i]
        var entry = modelUsageMap[k]
        if (!entry) continue
        var inTok = Math.round(Number(entry.inputTokens || 0) * scale)
        var outTok = Math.round(Number(entry.outputTokens || 0) * scale)
        var cacheTok = Math.round((Number(entry.cacheReadInputTokens || 0) + Number(entry.cacheCreationInputTokens || 0)) * scale)
        var totTok = entry.totalTokens !== undefined ? Math.round(Number(entry.totalTokens) * scale) : (inTok + outTok + cacheTok)
        var mCost = entry.costUsd !== undefined ? (Number(entry.costUsd) * scale) : estimateModelCost(k, inTok, outTok, cacheTok)
        if (totTok <= 0 && mCost <= 0) continue
        rows.push({
          id: k,
          label: cleanModelLabel(k),
          inputTokens: inTok,
          outputTokens: outTok,
          cacheTokens: cacheTok,
          totalTokens: totTok,
          costUsd: Math.round(mCost * 100) / 100
        })
      }
    } else if (projectModels instanceof Array && projectModels.length > 0) {
      for (var j = 0; j < projectModels.length; j++) {
        var pm = projectModels[j]
        if (!pm) continue
        var mName = String(pm.model || pm.id || "model")
        var pIn = Math.round(Number(pm.inputTokens || 0) * scale)
        var pOut = Math.round(Number(pm.outputTokens || 0) * scale)
        var pTot = Math.round(Number(pm.tokens || (pIn + pOut)) * scale)
        var pCost = pm.costUsd !== undefined ? (Number(pm.costUsd) * scale) : estimateModelCost(mName, pIn, pOut, 0)
        rows.push({
          id: mName,
          label: cleanModelLabel(mName),
          inputTokens: pIn,
          outputTokens: pOut,
          cacheTokens: 0,
          totalTokens: pTot,
          costUsd: Math.round(pCost * 100) / 100
        })
      }
    }

    rows.sort(function(a, b) {
      if (b.costUsd !== a.costUsd) return b.costUsd - a.costUsd
      return b.totalTokens - a.totalTokens
    })

    var maxTok = 1
    var maxCost = 0.01
    for (var r = 0; r < rows.length; r++) {
      if (rows[r].totalTokens > maxTok) maxTok = rows[r].totalTokens
      if (rows[r].costUsd > maxCost) maxCost = rows[r].costUsd
    }
    for (var s = 0; s < rows.length; s++) {
      rows[s].shareRatio = maxCost > 0.01 ? (rows[s].costUsd / maxCost) : (rows[s].totalTokens / maxTok)
    }

    return rows.slice(0, 6)
  }

  function cleanModelLabel(rawModel) {
    var m = String(rawModel || "").trim()
    if (!m) return "Unknown"
    m = m.split("@")[0]
    return m
  }

  function estimateModelCost(modelName, inTok, outTok, cacheTok) {
    var m = String(modelName || "").toLowerCase()
    var inM = Number(inTok || 0) / 1000000.0
    var outM = Number(outTok || 0) / 1000000.0
    var cacheM = Number(cacheTok || 0) / 1000000.0

    if (m.indexOf("opus") !== -1) {
      return inM * 5.0 + outM * 25.0 + cacheM * 0.50
    }
    if (m.indexOf("sonnet") !== -1) {
      return inM * 3.0 + outM * 15.0 + cacheM * 0.30
    }
    if (m.indexOf("haiku") !== -1) {
      return inM * 0.80 + outM * 4.0 + cacheM * 0.08
    }
    if (m.indexOf("pro") !== -1 || m.indexOf("argon") !== -1) {
      return inM * 1.25 + outM * 10.0 + cacheM * 0.3125
    }
    if (m.indexOf("lite") !== -1) {
      return inM * 0.30 + outM * 2.50 + cacheM * 0.03
    }
    // Default Flash pricing
    return inM * 0.75 + outM * 3.75 + cacheM * 0.075
  }

  function normalizedRecord(id) {
    var key = String(id || "").toLowerCase()
    var baseMeta = providerMeta[key] || {
      id: key,
      label: defaultNameForId(key),
      shortLabel: defaultNameForId(key),
      displayName: defaultNameForId(key),
      badge: "default",
      family: key,
      familyLabel: defaultNameForId(key),
      profile: "default",
      icon: key,
      command: key,
      description: defaultNameForId(key),
      order: 999,
      defaultEnabled: false
    }

    var isEnabled = isProviderEnabled(key)
    var raw = rawPayloads[key] || null
    var pCfg = (effectiveSettings.providers && effectiveSettings.providers[key]) ? effectiveSettings.providers[key] : {}
    var meta = {
      id: baseMeta.id,
      label: String(pCfg.label || (raw && raw.name) || baseMeta.label),
      shortLabel: String(pCfg.shortLabel || (raw && raw.shortLabel) || pCfg.label || baseMeta.shortLabel),
      displayName: String(pCfg.displayName || (raw && raw.displayName) || baseMeta.displayName),
      badge: String(pCfg.badge || (raw && raw.badge) || pCfg.gcpProject || pCfg.profile || baseMeta.badge),
      family: baseMeta.family,
      familyLabel: baseMeta.familyLabel,
      profile: String(pCfg.gcpProject || pCfg.profile || (raw && raw.profile) || baseMeta.profile),
      gcpProject: String(pCfg.gcpProject || (raw && raw.gcpProject) || ""),
      configDir: String(pCfg.configDir || ""),
      icon: baseMeta.icon,
      command: baseMeta.command,
      description: String(pCfg.description || baseMeta.description),
      order: baseMeta.order,
      defaultEnabled: baseMeta.defaultEnabled
    }

    // Fallback synthesis for modular profiles if dedicated file does not exist yet
    // or if base file (agy.json / claude.json) contains unsplit multi-profile breakdown
    var synthesizedFromParent = false
    var targetProjectBreakdown = null
    var parentRaw = null
    var shareRatio = 1.0

    if (key === "agy-sandbox" && !raw && rawPayloads["agy"]) {
      parentRaw = rawPayloads["agy"]
      targetProjectBreakdown = findProjectBreakdownEntry(parentRaw.projectsBreakdown, "agy-sandbox") || findProjectBreakdownEntry(parentRaw.projectsBreakdown, meta.profile)
      if (targetProjectBreakdown) {
        raw = parentRaw
        synthesizedFromParent = true
      }
    } else if (key === "agy" && raw && raw.projectsBreakdown instanceof Array && raw.projectsBreakdown.length > 1) {
      var sbCfg = (effectiveSettings.providers && effectiveSettings.providers["agy-sandbox"]) ? effectiveSettings.providers["agy-sandbox"] : {}
      var primaryEntry = findProjectBreakdownEntry(raw.projectsBreakdown, "agy") || findProjectBreakdownEntry(raw.projectsBreakdown, meta.profile)
      var sbEntry = findProjectBreakdownEntry(raw.projectsBreakdown, "agy-sandbox") || findProjectBreakdownEntry(raw.projectsBreakdown, sbCfg.gcpProject || sbCfg.profile || "sandbox")
      if (primaryEntry && sbEntry) {
        var combinedLocalCost = Number(primaryEntry.localCostUsd30d || 0) + Number(sbEntry.localCostUsd30d || 0)
        var rawTopCost = Number(raw.thirtyDayCostUsd !== undefined ? raw.thirtyDayCostUsd : (raw.costUsd || 0))
        if (combinedLocalCost > 0 && Math.abs(rawTopCost - combinedLocalCost) < 2.0) {
          parentRaw = raw
          targetProjectBreakdown = primaryEntry
          synthesizedFromParent = true
        }
      }
    } else if (key === "fiserv-claude" && !raw && rawPayloads["claude"]) {
      parentRaw = rawPayloads["claude"]
      targetProjectBreakdown = findProjectBreakdownEntry(parentRaw.projectsBreakdown, "fiserv-claude") || findProjectBreakdownEntry(parentRaw.projectsBreakdown, meta.profile)
      if (targetProjectBreakdown) {
        raw = parentRaw
        synthesizedFromParent = true
      }
    } else if (key === "claude" && raw && raw.projectsBreakdown instanceof Array && raw.projectsBreakdown.length > 1) {
      var workEntry = findProjectBreakdownEntry(raw.projectsBreakdown, "fiserv-claude")
      var personalEntry = findProjectBreakdownEntry(raw.projectsBreakdown, "claude") || findProjectBreakdownEntry(raw.projectsBreakdown, "personal")
      if (workEntry && personalEntry) {
        var combinedClaudeCost = Number(workEntry.costUSD || workEntry.costUsd || 0) + Number(personalEntry.costUSD || personalEntry.costUsd || 0)
        var rawClaudeTopCost = Number(raw.thirtyDayCostUsd !== undefined ? raw.thirtyDayCostUsd : (raw.costUsd || 0))
        if (combinedClaudeCost > 0 && Math.abs(rawClaudeTopCost - combinedClaudeCost) < 1.0 && Number(workEntry.costUSD || 0) > 0) {
          parentRaw = raw
          targetProjectBreakdown = personalEntry
          synthesizedFromParent = true
        }
      }
    }

    if (!raw || typeof raw !== "object") {
      return {
        id: key,
        name: meta.label,
        shortLabel: meta.shortLabel,
        displayName: meta.displayName,
        badge: meta.badge,
        family: meta.family,
        familyLabel: meta.familyLabel,
        profile: meta.profile,
        icon: meta.icon,
        command: meta.command,
        description: meta.description,
        order: meta.order,
        enabled: isEnabled,
        ready: false,
        hasLocalStats: false,
        hasPromptStats: false,
        updatedAt: "",
        tierLabel: meta.badge,
        usageStatusText: "No local telemetry yet",
        authHelpText: "",
        activeModel: "",
        limits: [],
        todayCostUsd: 0,
        sevenDayCostUsd: 0,
        thirtyDayCostUsd: 0,
        todayTotalTokens: 0,
        sevenDayTokens: 0,
        thirtyDayTokens: 0,
        todayPrompts: 0,
        todaySessions: 0,
        totalPrompts: 0,
        totalSessions: 0,
        activeDays: 0,
        recentDays: [],
        modelRows: [],
        projectsBreakdown: [],
        sharedOrgTokens30d: 0
      }
    }

    var todayCost = Number(raw.todayCostUsd !== undefined ? raw.todayCostUsd : 0)
    var sevenDayCost = Number(raw.sevenDayCostUsd !== undefined ? raw.sevenDayCostUsd : 0)
    var thirtyDayCost = Number(raw.thirtyDayCostUsd !== undefined ? raw.thirtyDayCostUsd : (raw.costUsd || 0))

    var todayTok = Number(raw.todayTotalTokens !== undefined ? raw.todayTotalTokens : (raw.todayTokens || 0))
    var sevenDayTok = Number(raw.sevenDayTokens !== undefined ? raw.sevenDayTokens : 0)
    var thirtyDayTok = Number(raw.totalTokens30d !== undefined ? raw.totalTokens30d : (raw.totalTokens || 0))

    var todayPr = Number(raw.todayPrompts || 0)
    var todaySess = Number(raw.todaySessions || 0)
    var totalPr = Number(raw.totalPrompts30d !== undefined ? raw.totalPrompts30d : (raw.totalPrompts || 0))
    var totalSess = Number(raw.totalSessions30d !== undefined ? raw.totalSessions30d : (raw.totalSessions || 0))
    var sharedOrgTok30d = 0
    var recentDaysList = raw.recentDays instanceof Array ? raw.recentDays : []
    var scopedBreakdown = raw.projectsBreakdown instanceof Array ? raw.projectsBreakdown : []

    if (synthesizedFromParent && targetProjectBreakdown) {
      var pCost30d = Number(targetProjectBreakdown.localCostUsd30d !== undefined
        ? targetProjectBreakdown.localCostUsd30d
        : (targetProjectBreakdown.costUSD !== undefined ? targetProjectBreakdown.costUSD : (targetProjectBreakdown.costUsd || 0)))
      var pTok30d = Number(targetProjectBreakdown.localTokens30d !== undefined
        ? targetProjectBreakdown.localTokens30d
        : (targetProjectBreakdown.tokens30d || 0))
      var pTok7d = Number(targetProjectBreakdown.localTokens7d !== undefined
        ? targetProjectBreakdown.localTokens7d
        : (targetProjectBreakdown.tokens7d || 0))
      var pTokToday = Number(targetProjectBreakdown.localTokensToday !== undefined
        ? targetProjectBreakdown.localTokensToday
        : (targetProjectBreakdown.tokensToday || 0))

      var parentCost30d = Math.max(0.0001, thirtyDayCost)
      var parentTok30d = Math.max(1, thirtyDayTok)
      shareRatio = thirtyDayCost > 0 ? Math.min(1.0, pCost30d / parentCost30d) : Math.min(1.0, pTok30d / parentTok30d)

      var ratePerTok = pTok30d > 0 ? (pCost30d / pTok30d) : 0
      thirtyDayCost = pCost30d
      sevenDayCost = targetProjectBreakdown.localCostUsd7d !== undefined
        ? Number(targetProjectBreakdown.localCostUsd7d)
        : (ratePerTok > 0 ? Math.round(pTok7d * ratePerTok * 100) / 100 : Math.round(sevenDayCost * shareRatio * 100) / 100)
      todayCost = targetProjectBreakdown.localCostUsdToday !== undefined
        ? Number(targetProjectBreakdown.localCostUsdToday)
        : (ratePerTok > 0 ? Math.round(pTokToday * ratePerTok * 100) / 100 : Math.round(todayCost * shareRatio * 100) / 100)

      thirtyDayTok = pTok30d
      sevenDayTok = pTok7d
      todayTok = pTokToday

      if (targetProjectBreakdown.localSessions30d !== undefined) {
        totalSess = Number(targetProjectBreakdown.localSessions30d)
      } else if (targetProjectBreakdown.sessions !== undefined) {
        totalSess = Number(targetProjectBreakdown.sessions)
      }
      if (targetProjectBreakdown.requests30d !== undefined && meta.family === "claude") {
        totalPr = Number(targetProjectBreakdown.requests30d)
      } else {
        totalPr = Math.round(totalPr * shareRatio)
      }
      todayPr = Math.round(todayPr * shareRatio)
      todaySess = Math.round(todaySess * shareRatio)
      sharedOrgTok30d = Number(targetProjectBreakdown.tokens30d || 0)
      recentDaysList = scaleRecentDays(recentDaysList, shareRatio, sevenDayCost, sevenDayTok)
      scopedBreakdown = [targetProjectBreakdown]
    } else if (scopedBreakdown.length > 0) {
      var matchingEntry = findProjectBreakdownEntry(scopedBreakdown, meta.profile) || scopedBreakdown[0]
      if (matchingEntry && matchingEntry.tokens30d !== undefined && matchingEntry.scope === "shared_gcp_project") {
        sharedOrgTok30d = Number(matchingEntry.tokens30d || 0)
      }
    }

    // If recentDays has today's date with >0 cost/tokens while top-level todayCostUsd was 0 (e.g. UTC vs local rollover)
    if (todayCost <= 0 && recentDaysList.length > 0) {
      var lastDay = recentDaysList[recentDaysList.length - 1]
      if (lastDay) {
        var lastCost = Number(lastDay.costUsd !== undefined ? lastDay.costUsd : (lastDay.costUSD || 0))
        var lastTok = Number(lastDay.tokens !== undefined ? lastDay.tokens : (lastDay.messageCount || 0))
        if (lastCost > 0 && todayTok > 0) {
          todayCost = lastCost
        }
      }
    }

    var modelRows = buildModelRows(
      synthesizedFromParent && targetProjectBreakdown && targetProjectBreakdown.models ? null : raw.modelUsage,
      targetProjectBreakdown && targetProjectBreakdown.models ? targetProjectBreakdown.models : null,
      synthesizedFromParent ? shareRatio : 1.0
    )

    var activeModelStr = String(raw.activeModel || "").trim()
    if (!activeModelStr && modelRows.length > 0) {
      activeModelStr = modelRows[0].label
    }

    var hasStats = (thirtyDayTok > 0 || thirtyDayCost > 0 || totalSess > 0 || totalPr > 0 || !!raw.hasLocalStats)

    return {
      id: key,
      name: meta.label,
      shortLabel: meta.shortLabel,
      displayName: meta.displayName,
      badge: meta.badge,
      family: meta.family,
      familyLabel: meta.familyLabel,
      profile: String(raw.profile || meta.profile),
      gcpProject: meta.gcpProject,
      configDir: meta.configDir,
      icon: meta.icon,
      command: meta.command,
      description: meta.description,
      order: meta.order,
      enabled: isEnabled,
      ready: raw.ready !== undefined ? !!raw.ready : (raw.status === "online" || hasStats),
      hasLocalStats: hasStats,
      hasPromptStats: raw.hasPromptStats !== undefined ? !!raw.hasPromptStats : (totalPr > 0),
      updatedAt: String(raw.updatedAt || raw.fetchedAt || ""),
      tierLabel: String(raw.tierLabel || meta.badge),
      usageStatusText: String(raw.usageStatusText || ""),
      authHelpText: String(raw.authHelpText || ""),
      activeModel: activeModelStr,
      limits: raw.limits instanceof Array ? raw.limits : [],
      todayCostUsd: Math.round(todayCost * 100) / 100,
      sevenDayCostUsd: Math.round(sevenDayCost * 100) / 100,
      thirtyDayCostUsd: Math.round(thirtyDayCost * 100) / 100,
      todayTotalTokens: Math.round(todayTok),
      sevenDayTokens: Math.round(sevenDayTok),
      thirtyDayTokens: Math.round(thirtyDayTok),
      todayPrompts: Math.round(todayPr),
      todaySessions: Math.round(todaySess),
      totalPrompts: Math.round(totalPr),
      totalSessions: Math.round(totalSess),
      activeDays: Number(raw.activeDays || recentDaysList.length),
      recentDays: recentDaysList,
      modelRows: modelRows,
      projectsBreakdown: scopedBreakdown,
      sharedOrgTokens30d: sharedOrgTok30d
    }
  }

  function formatCompactNumber(value) {
    var num = Math.max(0, Number(value || 0))
    if (num >= 1000000000) {
      var b = num / 1000000000
      return String(b >= 100 ? Math.round(b) : b.toFixed(b >= 10 ? 1 : 2)).replace(/\.0+$/, "") + "B"
    }
    if (num >= 1000000) {
      var m = num / 1000000
      return String(m >= 100 ? Math.round(m) : m.toFixed(1)).replace(/\.0$/, "") + "M"
    }
    if (num >= 1000) {
      var k = num / 1000
      return String(k >= 100 ? Math.round(k) : k.toFixed(1)).replace(/\.0$/, "") + "K"
    }
    return String(Math.round(num))
  }

  function formatUsd(value, compact) {
    var num = Math.max(0, Number(value || 0))
    if (compact && num >= 100) {
      return "$" + Math.round(num)
    }
    return "$" + num.toFixed(2)
  }

  function formatUpdatedAt(isoText) {
    if (!isoText) return "Not updated yet"
    var parsed = new Date(isoText)
    if (isNaN(parsed.getTime())) return "Updated recently"
    var diffSec = Math.max(0, Math.floor((Date.now() - parsed.getTime()) / 1000))
    if (diffSec < 60) return "Updated just now"
    if (diffSec < 3600) return "Updated " + Math.floor(diffSec / 60) + "m ago"
    if (diffSec < 86400) return "Updated " + Math.floor(diffSec / 3600) + "h ago"
    return "Updated " + Qt.formatDateTime(parsed, "MMM d, hh:mm")
  }

  function formatShortDay(dateStr) {
    if (!dateStr) return ""
    var parts = String(dateStr).split("-")
    if (parts.length !== 3) return String(dateStr)
    var dt = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]))
    if (isNaN(dt.getTime())) return String(dateStr)
    var today = new Date()
    if (dt.getFullYear() === today.getFullYear() && dt.getMonth() === today.getMonth() && dt.getDate() === today.getDate()) {
      return "Today"
    }
    var names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    return names[dt.getDay()]
  }

  Repeater {
    id: fileWatchers
    model: root.watchedFileIds

    delegate: Item {
      required property string modelData
      visible: false

      FileView {
        path: root.usageDir + "/" + modelData + ".json"
        watchChanges: true
        printErrors: false

        onLoaded: {
          try {
            var parsed = JSON.parse(text())
            var next = Object.assign({}, root.rawPayloads)
            next[modelData] = parsed
            root.rawPayloads = next
          } catch (err) {}
        }

        onLoadFailed: function(error) {
          if (error === FileViewError.FileNotFound) {
            var next = Object.assign({}, root.rawPayloads)
            if (next[modelData] !== undefined) {
              delete next[modelData]
              root.rawPayloads = next
            }
          }
        }

        onFileChanged: reload()
      }
    }
  }

  Process {
    id: scanFilesProcess
    command: ["sh", "-c", "ls -1 \"" + root.usageDir + "\"/*.json 2>/dev/null || true"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var lines = String(text || "").split(/\r?\n/)
        var ids = []
        for (var i = 0; i < lines.length; i++) {
          var line = String(lines[i] || "").trim()
          if (!line) continue
          var base = line.split("/").pop()
          if (!base || base.slice(-5) !== ".json") continue
          var id = base.slice(0, -5).toLowerCase()
          if (id && id.charAt(0) !== "_" && ids.indexOf(id) === -1) {
            ids.push(id)
          }
        }
        root.discoveredFileIds = ids
      }
    }
  }

  Process {
    id: refreshProcess
    running: false
    command: [root.bundledUpdateBin]

    onExited: function(exitCode, exitStatus) {
      root.refreshing = false
      root.rescanFiles()
      root.reloadFiles()

      if (root.refreshQueued) {
        var nextForce = root.refreshQueuedForce
        root.refreshQueued = false
        root.refreshQueuedForce = false
        root.refreshAll(nextForce)
      }
    }
  }

  Timer {
    interval: root.pollIntervalSeconds * 1000
    running: true
    repeat: true
    onTriggered: root.refreshAll(false)
  }
}
