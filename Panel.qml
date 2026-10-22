import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import qs.Ui as Ui

Ui.Panel {
  id: root
  moduleName: "nertwork.agents"
  ipcTarget: "nertwork.agents"
  manageIpc: false

  property var pluginService: null
  property bool allowFallbackUsage: false

  readonly property var hostWidget: (parent && parent.parent && ("usageService" in parent.parent))
    ? parent.parent
    : null
  readonly property var sharedService: root.pluginService
    ? root.pluginService
    : (root.bar && root.bar.shell
        ? (typeof root.bar.shell.ensureService === "function"
            ? root.bar.shell.ensureService("nertwork.agents")
            : (typeof root.bar.shell.firstPartyServiceFor === "function"
                ? root.bar.shell.firstPartyServiceFor("nertwork.agents")
                : null))
        : null)
  readonly property Item barIdentity: hostWidget ? hostWidget : root
  readonly property Item anchorTarget: (hostWidget && hostWidget.anchorButton)
    ? hostWidget.anchorButton
    : button

  function syncServiceSettings() {
    if (root.sharedService && root.settings) {
      root.sharedService.settings = root.settings
    }
  }

  onSharedServiceChanged: syncServiceSettings()
  onSettingsChanged: syncServiceSettings()
  Component.onCompleted: Qt.callLater(function() {
    root.syncServiceSettings()
    if (!root.sharedService && !(root.hostWidget && root.hostWidget.usageService)) {
      root.allowFallbackUsage = true
    }
  })

  QtObject {
    id: emptyUsage
    property var currentProvider: null
    property var enabledProviders: []
    property var providersByGroup: []
    property var effectiveSettings: ({})
    property int selectedIndex: 0
    property bool showCombinedView: false
    property bool showAggregatedSummary: true
    property bool showBarCost: true
    property string barDisplayMode: "total"
    property string barCostWindow: "today"
    property string barCostLabel: ""
    property string barTooltipText: "AI Agents Usage & Quota"
    property string terminalCommand: "xdg-terminal-exec"
    property bool localhostOnly: false
    property real dailyQuotaUsd: 50
    property bool isOverDailyQuota: false
    property bool isActiveProviderOverDailyQuota: false
    property bool isBarOverDailyQuota: false
    property bool isRefreshing: false
    property bool refreshing: false
    property real aggregatedTotalTodayCost: 0
    property real aggregatedTotal7dCost: 0
    property real aggregatedTotal30dCost: 0
    property real aggregatedTotal30dTokens: 0
    property var workVsPersonalTotals: ({ personalTodayCostUsd: 0, personal7dCostUsd: 0, personal30dCostUsd: 0, personal30dTokens: 0, censusTodayCostUsd: 0, census7dCostUsd: 0, census30dCostUsd: 0, census30dTokens: 0, workTodayCostUsd: 0, work7dCostUsd: 0, work30dCostUsd: 0, work30dTokens: 0 })
    property var meshHostsBreakdown: []
    property var agyFamilyTotals: ({ count: 0, todayCostUsd: 0, thirtyDayCostUsd: 0, todayTokens: 0, thirtyDayTokens: 0 })
    property var claudeFamilyTotals: ({ count: 0, todayCostUsd: 0, thirtyDayCostUsd: 0, todayTokens: 0, thirtyDayTokens: 0 })
    signal requestOpen()
    signal requestClose()
    signal requestToggle()
    function formatUsd(v, c) { return "$0.00" }
    function formatCompactNumber(v) { return "0" }
    function formatShortDay(v) { return "" }
    function formatUpdatedAt(v) { return "never" }
    function refreshAll(f) {}
    function reloadFiles() {}
    function cycleProvider(d) {}
    function selectProvider(i) {}
    function setSetting(k, v) {}
    function setProviderEnabled(id, en) {}
  }

  Loader {
    id: fallbackUsageLoader
    active: root.allowFallbackUsage && !root.sharedService && !(root.hostWidget && root.hostWidget.usageService)
    sourceComponent: Component {
      Main {
        settings: root.settings
      }
    }
  }

  readonly property var usage: root.sharedService
    ? root.sharedService
    : ((hostWidget && hostWidget.usageService)
        ? hostWidget.usageService
        : (fallbackUsageLoader.item ? fallbackUsageLoader.item : emptyUsage))

  property bool showSettings: false
  readonly property var activeProvider: usage.currentProvider
  readonly property var currentModule: activeProvider
  readonly property bool hasVisibleAgents: usage.enabledProviders.length > 0
  readonly property real availableCardHeight: panel.availableCardHeight > 0
    ? panel.availableCardHeight
    : Style.space(960)

  readonly property var activeNodesBreakdown: {
    var isCombined = !!(usage && usage.showCombinedView) || !!(root.activeProvider && root.activeProvider.id === "combined")
    if (!isCombined && root.activeProvider) {
      var pList = (root.activeProvider.hostsBreakdown instanceof Array) ? root.activeProvider.hostsBreakdown : []
      if (pList.length > 0) {
        var pOut = []
        for (var j = 0; j < pList.length; j++) {
          var ph = pList[j]
          if (ph && ph.host) {
            if (usage && usage.localhostOnly && String(ph.host) !== "james-mbp1") continue
            pOut.push({
              host: String(ph.host),
              role: String(ph.role || (ph.host === "james-mbp1" ? "local" : "mesh-sync")),
              status: String(ph.status || "synced"),
              costUsd: Number(ph.costUsd !== undefined ? ph.costUsd : (ph.costUsd30d || 0)),
              sessions: Number(ph.sessions !== undefined ? ph.sessions : (ph.sessions30d || 0)),
              tokens: Number(ph.tokens !== undefined ? ph.tokens : (ph.tokens30d || 0))
            })
          }
        }
        return pOut
      }
      var pid = String(root.activeProvider.id || "")
      var fallbackOrder = ["james-mbp1"]
      if (!(usage && usage.localhostOnly)) {
        if (pid === "agy-personal" || pid === "claude") {
          fallbackOrder = ["james-mbp1", "controller", "gpu01"]
        } else if (pid === "agy" || pid === "fiserv-claude") {
          fallbackOrder = ["james-mbp1", "netctl1", "netctl2"]
        } else if (pid === "agy-sandbox") {
          fallbackOrder = ["james-mbp1", "controller", "gpu01", "netctl1", "netctl2"]
        } else if (pid === "agy-census") {
          fallbackOrder = ["james-mbp1"]
        }
      }
      var fOut = []
      for (var f = 0; f < fallbackOrder.length; f++) {
        var fh = fallbackOrder[f]
        fOut.push({
          host: fh,
          role: fh === "james-mbp1" ? "local" : "mesh-sync",
          status: fh === "james-mbp1" ? "local" : "synced",
          costUsd: fh === "james-mbp1" ? Number(root.activeProvider.thirtyDayCostUsd || 0) : 0,
          sessions: fh === "james-mbp1" ? Number(root.activeProvider.totalSessions || 0) : 0,
          tokens: fh === "james-mbp1" ? Number(root.activeProvider.thirtyDayTokens || 0) : 0
        })
      }
      return fOut
    }
    var map = {}
    var meshList = (usage && usage.meshHostsBreakdown instanceof Array) ? usage.meshHostsBreakdown : []
    for (var i = 0; i < meshList.length; i++) {
      var mh = meshList[i]
      if (mh && mh.host) {
        map[String(mh.host)] = {
          host: String(mh.host),
          role: String(mh.role || (mh.host === "james-mbp1" ? "local" : "mesh-sync")),
          status: String(mh.status || "synced"),
          costUsd: Number(mh.costUsd !== undefined ? mh.costUsd : (mh.costUsd30d || 0)),
          sessions: Number(mh.sessions !== undefined ? mh.sessions : (mh.sessions30d || 0)),
          tokens: Number(mh.tokens !== undefined ? mh.tokens : (mh.tokens30d || 0))
        }
      }
    }
    var order = (usage && usage.localhostOnly) ? ["james-mbp1"] : ["james-mbp1", "controller", "gpu01", "netctl1", "netctl2"]
    var out = []
    for (var k = 0; k < order.length; k++) {
      var hName = order[k]
      if (map[hName]) {
        out.push(map[hName])
      } else {
        out.push({ host: hName, role: hName === "james-mbp1" ? "local" : "mesh-sync", status: "synced", costUsd: 0, sessions: 0, tokens: 0 })
      }
    }
    return out
  }

  readonly property bool isVertical: bar ? !!bar.vertical : false
  readonly property bool shouldShowCostPill: !isVertical && usage.showBarCost && usage.barCostLabel !== ""
  readonly property int pillWidth: shouldShowCostPill
    ? Math.max(Style.bar.iconSlot, barRow.implicitWidth + Style.space(18))
    : Style.bar.iconSlot

  readonly property color fgColor: Color.popups.text
  readonly property color bgColor: Color.popups.background
  readonly property color borderColor: Color.popups.border
  readonly property color accentColor: Color.accent
  readonly property color urgentColor: Color.urgent ? Color.urgent : "#e06c75"
  readonly property bool isBarOverDailyQuota: usage.isBarOverDailyQuota !== undefined
    ? !!usage.isBarOverDailyQuota
    : (Number(usage.dailyQuotaUsd || 0) > 0 && Number(usage.aggregatedTotalTodayCost || 0) >= Number(usage.dailyQuotaUsd || 50))
  readonly property color mutedColor: Qt.darker(fgColor, 1.35)
  readonly property color subtleColor: Qt.darker(fgColor, 1.72)
  readonly property color cardFill: Qt.rgba(fgColor.r, fgColor.g, fgColor.b, 0.035)
  readonly property color cardBorder: Qt.rgba(fgColor.r, fgColor.g, fgColor.b, 0.12)
  readonly property color elevatedFill: Qt.rgba(fgColor.r, fgColor.g, fgColor.b, 0.06)

  readonly property bool isLightPopupBackground: {
    var r = Number(bgColor.r || 0)
    var g = Number(bgColor.g || 0)
    var b = Number(bgColor.b || 0)
    var luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return luminance >= 0.62
  }

  implicitWidth: hostWidget ? 0 : (hasVisibleAgents ? button.implicitWidth : 0)
  implicitHeight: hostWidget ? 0 : (hasVisibleAgents ? button.implicitHeight : 0)
  visible: !hostWidget && hasVisibleAgents

  Ui.WidgetButton {
    id: button
    bar: root.bar
    active: root.opened
    visible: !root.hostWidget && root.hasVisibleAgents
    hasVisualContent: true
    labelVisible: false
    fixedWidth: root.isVertical ? Style.bar.sizeVertical : root.pillWidth
    fixedHeight: root.isVertical ? Style.bar.iconSlot : Style.bar.sizeHorizontal
    tooltipText: root.usage.barTooltipText

    onPressed: function(mouseButton) {
      if (mouseButton === Qt.LeftButton) {
        root.toggle()
      } else if (mouseButton === Qt.RightButton) {
        root.usage.refreshAll(true)
      } else if (mouseButton === Qt.MiddleButton) {
        root.usage.cycleProvider(1)
      }
    }

    Row {
      id: barRow
      anchors.centerIn: parent
      spacing: Style.space(5)

      Text {
        id: barIconLabel
        anchors.verticalCenter: parent.verticalCenter
        textFormat: Text.PlainText
        text: "󱚣"
        color: root.isBarOverDailyQuota
          ? root.urgentColor
          : (button.active && button.useActiveColor ? button.activeColor : button.foreground)
        font.family: Style.font.family
        font.pixelSize: Style.font.icon
      }

      Text {
        id: barCostText
        visible: root.shouldShowCostPill
        anchors.verticalCenter: parent.verticalCenter
        textFormat: Text.PlainText
        text: root.usage.barCostLabel
        color: root.isBarOverDailyQuota
          ? root.urgentColor
          : (button.active && button.useActiveColor ? button.activeColor : button.foreground)
        font.family: Style.font.family
        font.pixelSize: Style.font.bodySmall
        font.weight: root.isBarOverDailyQuota ? Font.Bold : Font.DemiBold
      }
    }

    Rectangle {
      visible: root.usage.isRefreshing
      width: Style.space(6)
      height: Style.space(6)
      radius: width / 2
      color: root.accentColor
      anchors.right: parent.right
      anchors.top: parent.top
      anchors.rightMargin: Style.space(3)
      anchors.topMargin: Style.space(3)
    }
  }

  Connections {
    target: root.usage
    enabled: !root.hostWidget
    function onRequestOpen() { root.open() }
    function onRequestClose() { root.close() }
    function onRequestToggle() { root.toggle() }
  }

  readonly property var availableIcons: ({
    "agy-personal": { dark: "assets/agy.svg", light: "assets/agy-light.svg" },
    "agy-census": { dark: "assets/agy.svg", light: "assets/agy-light.svg" },
    "agy": { dark: "assets/agy.svg", light: "assets/agy-light.svg" },
    "agy-sandbox": { dark: "assets/agy.svg", light: "assets/agy-light.svg" },
    "claude": { dark: "assets/claude.svg", light: "assets/claude.svg" },
    "fiserv-claude": { dark: "assets/claude.svg", light: "assets/claude.svg" },
    "codex": { dark: "assets/codex.svg", light: "assets/codex-light.svg" },
    "copilot": { dark: "assets/copilot.svg", light: "assets/copilot-light.svg" },
    "fireworks": { dark: "assets/fireworks.svg", light: "assets/fireworks.svg" },
    "grok": { dark: "assets/grok.svg", light: "assets/grok-light.svg" }
  })

  function iconUrlForProvider(providerObj) {
    if (!providerObj) return ""
    var idKey = String(providerObj.id || "").toLowerCase()
    var iconKey = String(providerObj.icon || providerObj.family || idKey).toLowerCase()
    var entry = availableIcons[idKey] || availableIcons[iconKey] || null
    if (!entry) return ""
    var rel = root.isLightPopupBackground ? (entry.light || entry.dark) : (entry.dark || entry.light)
    return rel ? Qt.resolvedUrl(rel) : ""
  }

  function launchCommandForProvider(providerObj) {
    var p = providerObj || activeProvider
    if (!p) return "agy"
    var pCfg = (usage && usage.effectiveSettings && usage.effectiveSettings.providers && usage.effectiveSettings.providers[p.id])
      ? usage.effectiveSettings.providers[p.id]
      : {}
    var configuredCmd = String((pCfg && pCfg.command) ? pCfg.command : (p.command || "")).trim()
    if (configuredCmd.length > 0) {
      return configuredCmd
    }
    if (p.id === "fiserv-claude") {
      var cfgDir = String(pCfg.configDir || p.configDir || "$HOME/.claude-work").replace(/^~/, "$HOME")
      return "CLAUDE_CONFIG_DIR=" + cfgDir + " claude"
    }
    if (p.id === "agy" || p.id === "agy-sandbox") {
      var gcpProj = String(pCfg.gcpProject || p.gcpProject || p.profile || "")
      if (gcpProj && ["default", "all", "primary", "sandbox", "agy-primary", "agy-sandbox"].indexOf(gcpProj.toLowerCase()) === -1) {
        return "GOOGLE_CLOUD_PROJECT=" + gcpProj + " agy"
      }
      return "agy"
    }
    return String(p.command || "agy")
  }

  function launchAgent(providerObj) {
    var cmd = launchCommandForProvider(providerObj)
    var customTerm = usage.terminalCommand
    if (customTerm !== "") {
      launchProcess.command = ["sh", "-c", "nohup " + customTerm + " " + cmd + " >/dev/null 2>&1 &"]
    } else {
      launchProcess.command = [
        "sh",
        "-c",
        "if command -v uwsm-app >/dev/null 2>&1 && command -v xdg-terminal-exec >/dev/null 2>&1; then " +
        "nohup uwsm-app -- xdg-terminal-exec --working-directory=\"$HOME\" -e sh -lc '" + cmd + "' >/dev/null 2>&1 & " +
        "elif command -v xdg-terminal-exec >/dev/null 2>&1; then " +
        "nohup xdg-terminal-exec --working-directory=\"$HOME\" -e sh -lc '" + cmd + "' >/dev/null 2>&1 & " +
        "elif command -v ghostty >/dev/null 2>&1; then " +
        "nohup ghostty -e sh -lc '" + cmd + "' >/dev/null 2>&1 & " +
        "elif command -v alacritty >/dev/null 2>&1; then " +
        "nohup alacritty -e sh -lc '" + cmd + "' >/dev/null 2>&1 & " +
        "elif command -v kitty >/dev/null 2>&1; then " +
        "nohup kitty sh -lc '" + cmd + "' >/dev/null 2>&1 & " +
        "fi"
      ]
    }
    launchProcess.running = true
    root.close()
  }

  Process {
    id: launchProcess
    running: false
  }

  component ProviderMark: Item {
    id: markRoot
    property var provider: null
    property int iconSize: Style.space(18)

    readonly property url currentIconUrl: root.iconUrlForProvider(provider)

    implicitWidth: iconSize
    implicitHeight: iconSize
    width: iconSize
    height: iconSize

    Image {
      id: svgImage
      anchors.fill: parent
      source: markRoot.currentIconUrl
      fillMode: Image.PreserveAspectFit
      smooth: true
      mipmap: true
      visible: status === Image.Ready && markRoot.currentIconUrl !== ""
    }

    Text {
      anchors.centerIn: parent
      visible: svgImage.status !== Image.Ready
      textFormat: Text.PlainText
      text: "󱚣"
      color: root.accentColor
      font.family: Style.font.family
      font.pixelSize: Math.round(markRoot.iconSize * 0.85)
    }
  }

  component BadgePill: Rectangle {
    id: pillRoot
    property string text: ""
    property color textColor: root.mutedColor
    property color pillFill: Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.06)
    property color pillBorder: Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.14)

    visible: text !== ""
    implicitWidth: pillText.implicitWidth + Style.space(12)
    implicitHeight: Style.space(20)
    width: implicitWidth
    height: implicitHeight
    radius: height / 2
    color: pillFill
    border.width: 1
    border.color: pillBorder

    Text {
      id: pillText
      anchors.centerIn: parent
      textFormat: Text.PlainText
      text: pillRoot.text
      color: pillRoot.textColor
      font.family: Style.font.family
      font.pixelSize: Style.font.caption
      font.weight: Font.Medium
    }
  }

  component KpiCard: Rectangle {
    id: kpiRoot
    property string label: ""
    property string primaryValue: "$0.00"
    property string tokenPillText: "0 tok"
    property string subtext: ""
    property bool highlight: false
    property bool urgent: false

    implicitHeight: Style.space(86)
    radius: Style.cornerRadius
    color: urgent
      ? Qt.rgba(root.urgentColor.r, root.urgentColor.g, root.urgentColor.b, 0.14)
      : (highlight
        ? Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.08)
        : root.cardFill)
    border.width: 1
    border.color: urgent
      ? Qt.rgba(root.urgentColor.r, root.urgentColor.g, root.urgentColor.b, 0.55)
      : (highlight
        ? Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.32)
        : root.cardBorder)

    Column {
      anchors.fill: parent
      anchors.margins: Style.space(10)
      spacing: Style.space(4)

      Text {
        width: parent.width
        textFormat: Text.PlainText
        text: kpiRoot.label
        color: kpiRoot.urgent ? root.urgentColor : (kpiRoot.highlight ? root.accentColor : root.subtleColor)
        font.family: Style.font.family
        font.pixelSize: Style.font.caption
        font.weight: Font.Bold
        font.capitalization: Font.AllUppercase
        font.letterSpacing: 0.6
        elide: Text.ElideRight
      }

      Text {
        width: parent.width
        textFormat: Text.PlainText
        text: kpiRoot.primaryValue
        color: kpiRoot.urgent ? root.urgentColor : root.fgColor
        font.family: Style.font.family
        font.pixelSize: Style.font.heading
        font.weight: Font.Bold
        elide: Text.ElideRight
      }

      Row {
        width: parent.width
        spacing: Style.space(6)

        Rectangle {
          id: kpiTokPill
          width: Math.min(parent.width, tokText.implicitWidth + Style.space(10))
          height: Style.space(18)
          radius: height / 2
          color: Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.07)

          Text {
            id: tokText
            anchors.centerIn: parent
            textFormat: Text.PlainText
            text: kpiRoot.tokenPillText
            color: root.mutedColor
            font.family: Style.font.family
            font.pixelSize: Style.font.caption
            font.weight: Font.Medium
          }
        }

        Text {
          visible: kpiRoot.subtext !== ""
          width: Math.max(0, parent.width - (kpiTokPill.visible ? kpiTokPill.width + parent.spacing : 0))
          anchors.verticalCenter: parent.verticalCenter
          textFormat: Text.PlainText
          text: kpiRoot.subtext
          color: root.subtleColor
          font.family: Style.font.family
          font.pixelSize: Style.font.caption
          elide: Text.ElideRight
        }
      }
    }
  }

  Ui.KeyboardPanel {
    id: panel
    anchorItem: root.anchorTarget
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    readonly property real maxCardHeight: Math.min(
      Style.space(855),
      Math.max(Style.space(420), root.availableCardHeight - panel.verticalContentInset * 2)
    )
    contentWidth: panel.fittedContentWidth(Style.space(560))
    contentHeight: panel.fittedContentHeight(
      Math.max(Style.space(420), mainRootColumn.implicitHeight),
      maxCardHeight
    )

    onOpenChanged: {
      if (open) {
        usage.reloadFiles()
        usage.refreshAll(false)
      } else {
        root.showSettings = false
      }
    }

    Ui.PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: {
        if (root.showSettings) {
          root.showSettings = false
        } else {
          root.close()
        }
      }
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onMoveRequested: function(dx, dy) {
        if (!root.showSettings && dx !== 0) {
          usage.cycleProvider(dx > 0 ? 1 : -1)
        }
      }
      onTextKey: function(t) {
        if (t === "r" || t === "R") usage.refreshAll(true)
        else if (!root.showSettings && t === "]") usage.cycleProvider(1)
        else if (!root.showSettings && t === "[") usage.cycleProvider(-1)
      }
    }

    readonly property real headerChromeHeight: (aggregateBanner.visible ? aggregateBanner.implicitHeight + Style.space(10) : 0)
      + (tabsFlick.visible ? tabsFlick.height + Style.space(10) : 0)
      + moduleHeaderCard.implicitHeight + Style.space(10)
    readonly property real maxScrollAreaHeight: Math.max(
      Style.space(200),
      maxCardHeight - panel.verticalContentInset - headerChromeHeight - Style.space(6)
    )

    Column {
      id: mainRootColumn
      width: parent.width
      height: Math.min(implicitHeight, parent.height)
      spacing: Style.space(10)
      clip: true

      // =======================================================================
      // 1. TOP AGGREGATE / OVERVIEW BANNER
      // =======================================================================
      Rectangle {
        id: aggregateBanner
        readonly property bool overQuota: usage.isOverDailyQuota === true
        visible: !root.showSettings && usage.showAggregatedSummary && usage.enabledProviders.length > 1
        width: parent.width
        implicitHeight: bannerCol.implicitHeight + Style.space(18)
        radius: Style.cornerRadius
        color: overQuota
          ? Qt.rgba(root.urgentColor.r, root.urgentColor.g, root.urgentColor.b, 0.12)
          : Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.075)
        border.width: 1
        border.color: overQuota
          ? Qt.rgba(root.urgentColor.r, root.urgentColor.g, root.urgentColor.b, 0.50)
          : Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.28)

        Column {
          id: bannerCol
          anchors.fill: parent
          anchors.margins: Style.space(9)
          spacing: Style.space(6)

          Row {
            width: parent.width
            spacing: Style.space(8)

            Column {
              width: parent.width - modeToggleBtn.width - Style.space(8)
              spacing: Style.space(2)

              Row {
                spacing: Style.space(6)

                Text {
                  anchors.verticalCenter: parent.verticalCenter
                  textFormat: Text.PlainText
                  text: usage.localhostOnly ? "LOCALHOST AI SPEND" : "MULTI-HOST AI SPEND · 5 NODES"
                  color: aggregateBanner.overQuota ? root.urgentColor : root.accentColor
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                  font.weight: Font.Bold
                  font.letterSpacing: 0.7
                }

                BadgePill {
                  anchors.verticalCenter: parent.verticalCenter
                  text: usage.formatCompactNumber(usage.aggregatedTotal30dTokens) + " tok (30d)"
                  textColor: root.fgColor
                  pillFill: Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.08)
                }

                BadgePill {
                  visible: Number(usage.dailyQuotaUsd || 0) > 0
                  anchors.verticalCenter: parent.verticalCenter
                  text: aggregateBanner.overQuota
                    ? ("OVER " + usage.formatUsd(usage.dailyQuotaUsd, true) + " QUOTA")
                    : ("Quota " + usage.formatUsd(usage.dailyQuotaUsd, true) + "/d")
                  textColor: aggregateBanner.overQuota ? root.urgentColor : root.mutedColor
                  pillFill: aggregateBanner.overQuota
                    ? Qt.rgba(root.urgentColor.r, root.urgentColor.g, root.urgentColor.b, 0.18)
                    : Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.06)
                  pillBorder: aggregateBanner.overQuota
                    ? Qt.rgba(root.urgentColor.r, root.urgentColor.g, root.urgentColor.b, 0.45)
                    : Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.14)
                }
              }

              Text {
                width: parent.width
                textFormat: Text.PlainText
                text: "Today " + usage.formatUsd(usage.aggregatedTotalTodayCost, false)
                  + "   ·   7d " + usage.formatUsd(usage.aggregatedTotal7dCost, false)
                  + "   ·   30d " + usage.formatUsd(usage.aggregatedTotal30dCost, false)
                color: aggregateBanner.overQuota ? root.urgentColor : root.fgColor
                font.family: Style.font.family
                font.pixelSize: Style.font.bodySmall
                font.weight: Font.Bold
                elide: Text.ElideRight
              }
            }

            Rectangle {
              id: modeToggleBtn
              anchors.verticalCenter: parent.verticalCenter
              width: modeToggleText.implicitWidth + Style.space(16)
              height: Style.space(26)
              radius: height / 2
              color: usage.showCombinedView
                ? root.accentColor
                : (modeToggleMouse.containsMouse
                  ? Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.12)
                  : Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.07))
              border.width: 1
              border.color: usage.showCombinedView
                ? root.accentColor
                : Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.2)

              Text {
                id: modeToggleText
                anchors.centerIn: parent
                textFormat: Text.PlainText
                text: usage.showCombinedView ? "󰕰 Combined View" : "󰕰 View Combined"
                color: usage.showCombinedView ? root.bgColor : root.fgColor
                font.family: Style.font.family
                font.pixelSize: Style.font.caption
                font.weight: Font.DemiBold
              }

              MouseArea {
                id: modeToggleMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: usage.showCombinedView = !usage.showCombinedView
              }
            }
          }

          // 3-Way Environment Spend Split Strip (Work / Census / Personal)
          Row {
            width: parent.width
            spacing: Style.space(6)

            Repeater {
              model: {
                var isToday = usage.barCostWindow !== "30d"
                var sfx = isToday ? " (Today):" : " (30d):"
                return [
                  { label: "Work" + sfx, cost: isToday ? usage.workVsPersonalTotals.workTodayCostUsd : usage.workVsPersonalTotals.work30dCostUsd, accent: false },
                  { label: "Census" + sfx, cost: isToday ? usage.workVsPersonalTotals.censusTodayCostUsd : usage.workVsPersonalTotals.census30dCostUsd, accent: true },
                  { label: "Personal" + sfx, cost: isToday ? usage.workVsPersonalTotals.personalTodayCostUsd : usage.workVsPersonalTotals.personal30dCostUsd, accent: false }
                ]
              }
              delegate: Rectangle {
                required property var modelData
                width: (parent.width - Style.space(12)) / 3
                height: Style.space(22)
                radius: Style.space(6)
                clip: true
                color: modelData.accent
                  ? Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.08)
                  : Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.06)
                border.width: 1
                border.color: modelData.accent
                  ? Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.24)
                  : Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.16)

                Row {
                  width: Math.min(implicitWidth, parent.width - Style.space(10))
                  anchors.centerIn: parent
                  spacing: Style.space(4)

                  Text {
                    id: envLbl
                    textFormat: Text.PlainText
                    text: modelData.label
                    color: root.mutedColor
                    font.family: Style.font.family
                    font.pixelSize: Style.font.caption
                  }

                  Text {
                    width: Math.min(implicitWidth, Math.max(0, parent.parent.width - Style.space(10) - envLbl.implicitWidth - parent.spacing))
                    textFormat: Text.PlainText
                    text: usage.formatUsd(modelData.cost, false)
                    color: root.fgColor
                    font.family: Style.font.family
                    font.pixelSize: Style.font.caption
                    font.weight: Font.Bold
                    elide: Text.ElideRight
                  }
                }
              }
            }
          }

          // Family Subtotals Strip (AGY Total | Claude Total)
          Row {
            visible: usage.agyFamilyTotals.count > 0 || usage.claudeFamilyTotals.count > 0
            width: parent.width
            spacing: Style.space(6)

            Rectangle {
              visible: usage.agyFamilyTotals.count > 0
              width: (usage.agyFamilyTotals.count > 0 && usage.claudeFamilyTotals.count > 0)
                ? (parent.width - Style.space(6)) * 0.5
                : parent.width
              height: Style.space(22)
              radius: Style.space(6)
              clip: true
              color: Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.05)
              border.width: 1
              border.color: Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.12)

              Row {
                id: agyFamRow
                width: Math.min(implicitWidth, parent.width - Style.space(12))
                anchors.centerIn: parent
                spacing: Style.space(5)

                Text {
                  id: agyFamLabel
                  textFormat: Text.PlainText
                  text: "AGY Total (" + usage.agyFamilyTotals.count + "):"
                  color: root.mutedColor
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                }

                Text {
                  width: Math.min(implicitWidth, Math.max(0, parent.parent.width - Style.space(12) - agyFamLabel.implicitWidth - parent.spacing))
                  textFormat: Text.PlainText
                  text: usage.formatUsd(usage.barCostWindow !== "30d" ? usage.agyFamilyTotals.todayCostUsd : usage.agyFamilyTotals.thirtyDayCostUsd, false)
                    + " · " + usage.formatCompactNumber(usage.barCostWindow !== "30d" ? usage.agyFamilyTotals.todayTokens : usage.agyFamilyTotals.thirtyDayTokens)
                  color: root.fgColor
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                  font.weight: Font.DemiBold
                  elide: Text.ElideRight
                }
              }
            }

            Rectangle {
              visible: usage.claudeFamilyTotals.count > 0
              width: (usage.agyFamilyTotals.count > 0 && usage.claudeFamilyTotals.count > 0)
                ? (parent.width - Style.space(6)) * 0.5
                : parent.width
              height: Style.space(22)
              radius: Style.space(6)
              clip: true
              color: Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.05)
              border.width: 1
              border.color: Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.12)

              Row {
                id: claudeFamRow
                width: Math.min(implicitWidth, parent.width - Style.space(12))
                anchors.centerIn: parent
                spacing: Style.space(5)

                Text {
                  id: claudeFamLabel
                  textFormat: Text.PlainText
                  text: "Claude Total (" + usage.claudeFamilyTotals.count + "):"
                  color: root.mutedColor
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                }

                Text {
                  width: Math.min(implicitWidth, Math.max(0, parent.parent.width - Style.space(12) - claudeFamLabel.implicitWidth - parent.spacing))
                  textFormat: Text.PlainText
                  text: usage.formatUsd(usage.barCostWindow !== "30d" ? usage.claudeFamilyTotals.todayCostUsd : usage.claudeFamilyTotals.thirtyDayCostUsd, false)
                    + " · " + usage.formatCompactNumber(usage.barCostWindow !== "30d" ? usage.claudeFamilyTotals.todayTokens : usage.claudeFamilyTotals.thirtyDayTokens)
                  color: root.fgColor
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                  font.weight: Font.DemiBold
                  elide: Text.ElideRight
                }
              }
            }
          }

          // Quick-Launch Workspace Chips Row (Work / Census / Homelab)
          Row {
            width: parent.width
            spacing: Style.space(6)

            Text {
              anchors.verticalCenter: parent.verticalCenter
              textFormat: Text.PlainText
              text: "Launch:"
              color: root.subtleColor
              font.family: Style.font.family
              font.pixelSize: Style.font.caption
              font.weight: Font.Bold
            }

            Repeater {
              model: [
                { label: "󰆍 Work (~/Work)", cmd: ["/home/jfarr/.local/bin/omarchy-agent-work"] },
                { label: "󰆍 Census (CSVD)", cmd: ["/home/jfarr/.local/bin/omarchy-agent-census"] },
                { label: "󰆍 Homelab (Ops)", cmd: ["/home/jfarr/.local/bin/omarchy-agent-controller"] }
              ]
              delegate: Rectangle {
                required property var modelData
                width: launchChipText.implicitWidth + Style.space(14)
                height: Style.space(20)
                radius: height / 2
                color: launchChipMouse.containsMouse
                  ? Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.20)
                  : Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.06)
                border.width: 1
                border.color: launchChipMouse.containsMouse
                  ? Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.45)
                  : Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.16)

                Text {
                  id: launchChipText
                  anchors.centerIn: parent
                  textFormat: Text.PlainText
                  text: modelData.label
                  color: launchChipMouse.containsMouse ? root.accentColor : root.fgColor
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                  font.weight: Font.DemiBold
                }

                MouseArea {
                  id: launchChipMouse
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: Quickshell.execDetached(modelData.cmd)
                }
              }
            }
          }
        }
      }

      // =======================================================================
      // 2. MODULAR PROVIDER SWITCHER TABS
      // =======================================================================
      Flow {
        id: tabsFlick
        visible: !root.showSettings && usage.enabledProviders.length > 0
        width: parent.width
        spacing: Style.space(5)

        Repeater {
          model: usage.enabledProviders

          delegate: Rectangle {
            id: tabPill
            required property var modelData
            required property int index

            readonly property bool isSelected: !usage.showCombinedView && usage.selectedIndex === index

            width: tabInnerRow.implicitWidth + Style.space(12)
            height: Style.space(28)
            radius: Style.cornerRadius
            color: isSelected
              ? Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.16)
              : (tabMouse.containsMouse
                ? Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.08)
                : root.cardFill)
            border.width: isSelected ? 1.5 : 1
            border.color: isSelected
              ? root.accentColor
              : (tabMouse.containsMouse
                ? Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.24)
                : root.cardBorder)

            Behavior on color { ColorAnimation { duration: 100 } }

            Row {
              id: tabInnerRow
              anchors.centerIn: parent
              spacing: Style.space(5)

              ProviderMark {
                anchors.verticalCenter: parent.verticalCenter
                provider: tabPill.modelData
                iconSize: Style.space(14)
              }

              Text {
                anchors.verticalCenter: parent.verticalCenter
                textFormat: Text.PlainText
                text: tabPill.modelData.shortLabel || tabPill.modelData.name
                color: tabPill.isSelected ? root.fgColor : root.mutedColor
                font.family: Style.font.family
                font.pixelSize: Style.font.caption
                font.weight: tabPill.isSelected ? Font.Bold : Font.Medium
              }

              Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: tabCostText.implicitWidth + Style.space(6)
                height: Style.space(16)
                radius: height / 2
                color: tabPill.isSelected
                  ? Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.22)
                  : Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.06)

                Text {
                  id: tabCostText
                  anchors.centerIn: parent
                  textFormat: Text.PlainText
                  text: usage.formatUsd(usage.barCostWindow !== "30d" ? tabPill.modelData.todayCostUsd : tabPill.modelData.thirtyDayCostUsd, true)
                  color: tabPill.isSelected ? root.fgColor : root.subtleColor
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                  font.weight: Font.DemiBold
                }
              }
            }

            MouseArea {
              id: tabMouse
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: usage.selectProvider(tabPill.index)
            }
          }
        }
      }

      // =======================================================================
      // 3. ACTIVE MODULE HEADER + ACTION CONTROLS
      // =======================================================================
      Rectangle {
        id: moduleHeaderCard
        width: parent.width
        implicitHeight: Style.space(52)
        radius: Style.cornerRadius
        color: root.cardFill
        border.width: 1
        border.color: root.cardBorder

        Row {
          anchors.fill: parent
          anchors.leftMargin: Style.space(12)
          anchors.rightMargin: Style.space(10)
          spacing: Style.space(10)

          ProviderMark {
            visible: !root.showSettings && root.activeProvider !== null
            anchors.verticalCenter: parent.verticalCenter
            provider: root.activeProvider
            iconSize: Style.space(24)
          }

          Column {
            id: headerTitleCol
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width
              - ((!root.showSettings && root.activeProvider !== null) ? Style.space(34) : 0)
              - headerActionsRow.implicitWidth
              - Style.space(20)
            spacing: Style.space(2)

            Row {
              width: parent.width
              spacing: Style.space(6)

              Text {
                width: Math.min(
                  implicitWidth,
                  Math.max(
                    Style.space(90),
                    parent.width
                      - (modBadgePill.visible ? modBadgePill.width + parent.spacing : 0)
                      - (hostCountPill.visible ? hostCountPill.width + parent.spacing : 0)
                  )
                )
                anchors.verticalCenter: parent.verticalCenter
                textFormat: Text.PlainText
                text: root.showSettings
                  ? "AI Agents Settings"
                  : (root.currentModule ? (root.currentModule.label || root.currentModule.displayName || root.currentModule.name) : "No Module Enabled")
                color: root.fgColor
                font.family: Style.font.family
                font.pixelSize: Style.font.subtitle
                font.weight: Font.Bold
                elide: Text.ElideRight
              }

              BadgePill {
                id: modBadgePill
                visible: !root.showSettings && root.currentModule !== null
                anchors.verticalCenter: parent.verticalCenter
                text: root.currentModule ? root.currentModule.badge : ""
                textColor: root.accentColor
                pillFill: Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.12)
                pillBorder: Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.3)
              }

              BadgePill {
                id: hostCountPill
                visible: !root.showSettings
                anchors.verticalCenter: parent.verticalCenter
                text: usage.localhostOnly ? "localhost" : (root.activeNodesBreakdown.length + (root.activeNodesBreakdown.length === 1 ? " node" : " nodes"))
                textColor: root.mutedColor
              }
            }

            Text {
              width: parent.width
              textFormat: Text.PlainText
              text: root.showSettings
                ? "Configure modular profiles, localhost telemetry, and status bar display"
                : (root.currentModule
                  ? ((root.currentModule.displayName ? (root.currentModule.displayName + " · ") : "")
                    + usage.formatUpdatedAt(root.currentModule.updatedAt)
                    + (root.currentModule.activeModel ? (" · " + root.currentModule.activeModel) : ""))
                  : "Enable one or more modules in Settings")
              color: root.subtleColor
              font.family: Style.font.family
              font.pixelSize: Style.font.caption
              elide: Text.ElideRight
            }
          }

          Row {
            id: headerActionsRow
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(5)

            PanelActionButton {
              visible: !root.showSettings && root.activeProvider !== null && root.activeProvider.id !== "combined"
              iconText: "󰆍"
              tooltipText: "Launch " + (root.activeProvider ? root.activeProvider.shortLabel : "CLI") + " in terminal"
              foreground: root.fgColor
              hoverColor: root.accentColor
              bordered: true
              onClicked: root.launchAgent(root.activeProvider)
            }

            Rectangle {
              width: syncBtnRow.implicitWidth + Style.space(14)
              height: Style.space(28)
              radius: Style.space(7)
              color: syncBtnMouse.containsMouse || usage.refreshing
                ? Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.18)
                : Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.06)
              border.width: 1
              border.color: syncBtnMouse.containsMouse || usage.refreshing
                ? Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.45)
                : Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.16)

              Row {
                id: syncBtnRow
                anchors.centerIn: parent
                spacing: Style.space(4)

                Text {
                  anchors.verticalCenter: parent.verticalCenter
                  textFormat: Text.PlainText
                  text: usage.refreshing ? "󰑓" : "󰑐"
                  color: usage.refreshing || syncBtnMouse.containsMouse ? root.accentColor : root.fgColor
                  font.family: Style.font.family
                  font.pixelSize: Style.font.bodySmall
                }

                Text {
                  anchors.verticalCenter: parent.verticalCenter
                  textFormat: Text.PlainText
                  text: usage.refreshing ? "Syncing..." : "Sync Nodes"
                  color: usage.refreshing || syncBtnMouse.containsMouse ? root.accentColor : root.fgColor
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                  font.weight: Font.DemiBold
                }
              }

              MouseArea {
                id: syncBtnMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: usage.refreshAll(true)
              }
            }

            PanelActionButton {
              iconText: root.showSettings ? "󰅖" : "󰒓"
              tooltipText: root.showSettings ? "Back to usage dashboard" : "Configure modules & settings"
              foreground: root.showSettings ? root.accentColor : root.fgColor
              hoverColor: root.accentColor
              bordered: true
              onClicked: root.showSettings = !root.showSettings
            }
          }
        }
      }

      // =======================================================================
      // 4A. EMBEDDED SETTINGS VIEW (when gear icon is toggled)
      // =======================================================================
      Flickable {
        id: settingsFlick
        visible: root.showSettings
        width: parent.width
        height: Math.min(panel.maxScrollAreaHeight, settingsViewItem.implicitHeight)
        contentWidth: width
        contentHeight: settingsViewItem.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Column {
          id: settingsViewItem
          width: settingsFlick.width
          spacing: Style.space(10)

          component SettingsSectionCard: Rectangle {
            id: sCard
            property string title: ""
            property string subtitle: ""
            default property alias content: sInnerColumn.data

            width: parent ? parent.width : Style.space(516)
            implicitHeight: sInnerColumn.implicitHeight + Style.space(22)
            radius: Style.cornerRadius
            color: root.cardFill
            border.width: 1
            border.color: root.cardBorder

            Column {
              id: sInnerColumn
              anchors.fill: parent
              anchors.margins: Style.space(11)
              spacing: Style.space(8)

              Column {
                visible: sCard.title !== ""
                width: parent.width
                spacing: Style.space(2)

                Text {
                  textFormat: Text.PlainText
                  text: sCard.title
                  color: root.mutedColor
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                  font.weight: Font.Bold
                  font.letterSpacing: 0.7
                }

                Text {
                  visible: sCard.subtitle !== ""
                  width: parent.width
                  textFormat: Text.PlainText
                  text: sCard.subtitle
                  color: root.subtleColor
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                  wrapMode: Text.WordWrap
                }
              }
            }
          }

          component SettingsToggleRow: Rectangle {
            id: sRowRoot
            property string label: ""
            property string description: ""
            property string badgeText: ""
            property bool checked: false
            signal toggled(bool value)

            width: parent ? parent.width : Style.space(492)
            implicitHeight: Math.max(Style.space(36), sTextCol.implicitHeight + Style.space(10))
            radius: Math.max(4, Style.cornerRadius - 2)
            color: sRowHover.containsMouse
              ? Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.05)
              : "transparent"

            Column {
              id: sTextCol
              anchors.left: parent.left
              anchors.leftMargin: Style.space(6)
              anchors.right: sToggleSwitch.left
              anchors.rightMargin: Style.space(10)
              anchors.verticalCenter: parent.verticalCenter
              spacing: Style.space(2)

              Row {
                width: parent.width
                spacing: Style.space(6)

                Text {
                  width: Math.min(
                    implicitWidth,
                    Math.max(
                      Style.space(80),
                      parent.width - (sRowBadgePill.visible ? sRowBadgePill.width + parent.spacing : 0)
                    )
                  )
                  textFormat: Text.PlainText
                  anchors.verticalCenter: parent.verticalCenter
                  text: sRowRoot.label
                  color: root.fgColor
                  font.family: Style.font.family
                  font.pixelSize: Style.font.bodySmall
                  font.weight: Font.Medium
                  elide: Text.ElideRight
                }

                BadgePill {
                  id: sRowBadgePill
                  visible: sRowRoot.badgeText !== ""
                  anchors.verticalCenter: parent.verticalCenter
                  text: sRowRoot.badgeText
                  textColor: root.accentColor
                  pillFill: Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.14)
                  pillBorder: Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.35)
                }
              }

              Text {
                visible: sRowRoot.description !== ""
                width: parent.width
                textFormat: Text.PlainText
                text: sRowRoot.description
                color: root.subtleColor
                font.family: Style.font.family
                font.pixelSize: Style.font.caption
                elide: Text.ElideRight
              }
            }

            Ui.ToggleSwitch {
              id: sToggleSwitch
              anchors.right: parent.right
              anchors.rightMargin: Style.space(6)
              anchors.verticalCenter: parent.verticalCenter
              checked: sRowRoot.checked
              foreground: root.fgColor
              accent: root.accentColor
              onToggled: sRowRoot.toggled(!sRowRoot.checked)
            }

            MouseArea {
              id: sRowHover
              anchors.left: parent.left
              anchors.top: parent.top
              anchors.bottom: parent.bottom
              anchors.right: sToggleSwitch.left
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: sRowRoot.toggled(!sRowRoot.checked)
            }
          }

          SettingsSectionCard {
            title: "EXECUTION & AGGREGATION"
            subtitle: "Multi-host or localhost collection with optional multi-module rollups."

            SettingsToggleRow {
              label: "Localhost-only collection"
              badgeText: root.usage.localhostOnly ? "localhost" : "5 nodes"
              description: "When enabled, restrict collection to this host only (disables multi-host SSH fan-out)"
              checked: root.usage.localhostOnly
              onToggled: function(val) { root.usage.setSetting("localhostOnly", val) }
            }

            Rectangle {
              width: parent.width
              implicitHeight: pQuotaCol.implicitHeight + Style.space(12)
              radius: Math.max(4, Style.cornerRadius - 2)
              color: "transparent"

              Column {
                id: pQuotaCol
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.margins: Style.space(6)
                anchors.verticalCenter: parent.verticalCenter
                spacing: Style.space(5)

                Row {
                  width: parent.width
                  spacing: Style.space(6)

                  Column {
                    width: Math.max(Style.space(120), parent.width - pStepperRow.implicitWidth - Style.space(8))
                    spacing: Style.space(2)

                    Row {
                      spacing: Style.space(6)

                      Text {
                        textFormat: Text.PlainText
                        text: "Daily Cost Quota"
                        color: root.fgColor
                        font.family: Style.font.family
                        font.pixelSize: Style.font.bodySmall
                        font.weight: Font.Medium
                      }

                      Rectangle {
                        width: pqBadgeLbl.implicitWidth + Style.space(10)
                        height: Style.space(16)
                        radius: height / 2
                        color: root.usage.isOverDailyQuota
                          ? Qt.rgba(root.urgentColor.r, root.urgentColor.g, root.urgentColor.b, 0.18)
                          : Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.14)
                        border.width: 1
                        border.color: root.usage.isOverDailyQuota
                          ? Qt.rgba(root.urgentColor.r, root.urgentColor.g, root.urgentColor.b, 0.45)
                          : Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.35)

                        Text {
                          id: pqBadgeLbl
                          anchors.centerIn: parent
                          textFormat: Text.PlainText
                          text: root.usage.dailyQuotaUsd <= 0
                            ? "Off"
                            : ("$" + Math.round(root.usage.dailyQuotaUsd) + "/day")
                          color: root.usage.isOverDailyQuota ? root.urgentColor : root.accentColor
                          font.family: Style.font.family
                          font.pixelSize: Style.font.caption - 1
                          font.weight: Font.DemiBold
                        }
                      }
                    }

                    Text {
                      width: parent.width
                      textFormat: Text.PlainText
                      text: "Turns bar widget, today card & daily chart red when daily spend meets quota"
                      color: root.subtleColor
                      font.family: Style.font.family
                      font.pixelSize: Style.font.caption
                      elide: Text.ElideRight
                    }
                  }

                  Row {
                    id: pStepperRow
                    spacing: Style.space(4)
                    anchors.verticalCenter: parent.verticalCenter

                    Repeater {
                      model: [
                        { label: "-$5", delta: -5, preset: -1 },
                        { label: "+$5", delta: 5, preset: -1 },
                        { label: "$25", delta: 0, preset: 25 },
                        { label: "$50", delta: 0, preset: 50 },
                        { label: "$100", delta: 0, preset: 100 },
                        { label: "$250", delta: 0, preset: 250 },
                        { label: "Off", delta: 0, preset: 0 }
                      ]
                      delegate: Rectangle {
                        required property var modelData
                        readonly property real curQuota: Number(root.usage.dailyQuotaUsd || 0)
                        readonly property bool isSelected: modelData.preset >= 0 && Math.round(curQuota) === modelData.preset
                        width: pChipTxt.implicitWidth + Style.space(10)
                        height: Style.space(22)
                        radius: height / 2
                        color: isSelected
                          ? Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.22)
                          : (pChipMouse.containsMouse
                            ? Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.12)
                            : Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.06))
                        border.width: 1
                        border.color: isSelected
                          ? root.accentColor
                          : Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.18)

                        Text {
                          id: pChipTxt
                          anchors.centerIn: parent
                          textFormat: Text.PlainText
                          text: modelData.label
                          color: isSelected ? root.accentColor : root.fgColor
                          font.family: Style.font.family
                          font.pixelSize: Style.font.caption
                          font.weight: isSelected ? Font.Bold : Font.Medium
                        }

                        MouseArea {
                          id: pChipMouse
                          anchors.fill: parent
                          hoverEnabled: true
                          cursorShape: Qt.PointingHandCursor
                          onClicked: {
                            if (modelData.preset >= 0) {
                              root.usage.setSetting("dailyQuotaUsd", modelData.preset)
                            } else {
                              var nextVal = Math.max(0, Math.round(curQuota + modelData.delta))
                              root.usage.setSetting("dailyQuotaUsd", nextVal)
                            }
                          }
                        }
                      }
                    }
                  }
                }
              }
            }

            SettingsToggleRow {
              label: "Show aggregated totals banner"
              badgeText: "Overview"
              description: "Display combined AGY + Claude spend and token rollup across enabled modules at top of panel"
              checked: root.usage.showAggregatedSummary
              onToggled: function(val) { root.usage.setSetting("showAggregatedSummary", val) }
            }

            SettingsToggleRow {
              label: "Show cost in status bar"
              badgeText: root.usage.barDisplayMode === "active" ? "Active Module" : (root.usage.barCostWindow !== "30d" ? "Today $" : "30d $")
              description: "Render live " + (root.usage.barCostWindow !== "30d" ? "daily (Today)" : "30d") + " USD spend next to the AI Agents status bar icon (turns red ≥ $" + root.usage.dailyQuotaUsd + "/day)"
              checked: root.usage.showBarCost
              onToggled: function(val) { root.usage.setSetting("showBarCost", val) }
            }

            SettingsToggleRow {
              label: "Show current daily cost"
              badgeText: root.usage.barCostWindow !== "30d" ? "Today ($" + root.usage.dailyQuotaUsd + " budget)" : "30d Window"
              description: "Default to current daily (Today) cost in the status bar, tabs, and summary strips instead of 30-day cumulative cost"
              checked: root.usage.barCostWindow !== "30d"
              onToggled: function(val) { root.usage.setSetting("barCostWindow", val ? "today" : "30d") }
            }

            SettingsToggleRow {
              label: "Bar widget displays aggregated total"
              badgeText: root.usage.barCostWindow !== "30d" ? "Daily Rollup" : "30d Rollup"
              description: "When enabled, bar cost shows combined spend across enabled modules; otherwise shows active tab"
              checked: root.usage.barDisplayMode !== "active"
              onToggled: function(val) { root.usage.setSetting("barDisplayMode", val ? "aggregated" : "active") }
            }
          }

          SettingsSectionCard {
            title: "AGY MODULES (PERSONAL / CENSUS / CLOVER)"
            subtitle: "Enable Antigravity modules across Personal (Homelab), Census (CSVD), and Clover (Work / Sandbox)."

            Repeater {
              model: root.usage.providersByGroup("agy")
              delegate: SettingsToggleRow {
                required property var modelData
                label: modelData.displayName
                badgeText: modelData.badge
                description: modelData.description
                checked: modelData.enabled
                onToggled: function(val) { root.usage.setProviderEnabled(modelData.id, val) }
              }
            }
          }

          SettingsSectionCard {
            title: "CLAUDE MODULES (WORK / ENTERPRISE & PERSONAL)"
            subtitle: "Enable secondary/work Claude profile and/or primary personal Claude (~/.claude)."

            Repeater {
              model: root.usage.providersByGroup("claude")
              delegate: SettingsToggleRow {
                required property var modelData
                label: modelData.displayName
                badgeText: modelData.badge
                description: modelData.description
                checked: modelData.enabled
                onToggled: function(val) { root.usage.setProviderEnabled(modelData.id, val) }
              }
            }
          }

          SettingsSectionCard {
            title: "OTHER AI CODING PROVIDERS"
            subtitle: "Optional local CLI and IDE coding assistants."

            Repeater {
              model: root.usage.providersByGroup("other")
              delegate: SettingsToggleRow {
                required property var modelData
                label: modelData.displayName
                badgeText: modelData.badge
                description: modelData.description
                checked: modelData.enabled
                onToggled: function(val) { root.usage.setProviderEnabled(modelData.id, val) }
              }
            }
          }
        }
      }

      // =======================================================================
      // 4B. DASHBOARD BODY (Scrollable when content is tall)
      // =======================================================================
      Flickable {
        id: dashboardFlick
        visible: !root.showSettings && root.activeProvider !== null
        width: parent.width
        height: Math.min(panel.maxScrollAreaHeight, dashboardColumn.implicitHeight)
        contentWidth: width
        contentHeight: dashboardColumn.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Column {
          id: dashboardColumn
          width: dashboardFlick.width
          spacing: Style.space(10)

          // -------------------------------------------------------------------
          // KPI 3-COLUMN GRID (TODAY | LAST 7 DAYS | LAST 30 DAYS)
          // -------------------------------------------------------------------
          Row {
            id: kpiGrid
            width: parent.width
            spacing: Style.space(8)

            readonly property real cardWidth: Math.floor((width - spacing * 2) / 3)

            KpiCard {
              width: kpiGrid.cardWidth
              label: "TODAY"
              primaryValue: root.activeProvider ? usage.formatUsd(root.activeProvider.todayCostUsd, false) : "$0.00"
              tokenPillText: (root.activeProvider ? usage.formatCompactNumber(root.activeProvider.todayTotalTokens) : "0") + " tok"
              subtext: root.activeProvider && root.activeProvider.todayPrompts > 0
                ? (root.activeProvider.todayPrompts + " req")
                : ""
              highlight: root.activeProvider ? (root.activeProvider.todayCostUsd > 0 || root.activeProvider.todayTotalTokens > 0) : false
              urgent: Number(usage.dailyQuotaUsd || 0) > 0 && root.activeProvider !== null && Number(root.activeProvider.todayCostUsd || 0) >= Number(usage.dailyQuotaUsd || 50)
            }

            KpiCard {
              width: kpiGrid.cardWidth
              label: "LAST 7 DAYS"
              primaryValue: root.activeProvider ? usage.formatUsd(root.activeProvider.sevenDayCostUsd, false) : "$0.00"
              tokenPillText: (root.activeProvider ? usage.formatCompactNumber(root.activeProvider.sevenDayTokens) : "0") + " tok"
              subtext: root.activeProvider && root.activeProvider.recentDays
                ? (root.activeProvider.recentDays.length + "d window")
                : ""
              highlight: false
            }

            KpiCard {
              width: parent.width - kpiGrid.cardWidth * 2 - kpiGrid.spacing * 2
              label: "LAST 30 DAYS"
              primaryValue: root.activeProvider ? usage.formatUsd(root.activeProvider.thirtyDayCostUsd, false) : "$0.00"
              tokenPillText: (root.activeProvider ? usage.formatCompactNumber(root.activeProvider.thirtyDayTokens) : "0") + " tok"
              subtext: root.activeProvider && root.activeProvider.totalSessions > 0
                ? (root.activeProvider.totalSessions + " sess")
                : ""
              highlight: false
            }
          }

          // -------------------------------------------------------------------
          // 7-DAY DAILY USAGE BAR CHART
          // -------------------------------------------------------------------
          Rectangle {
            id: chartCard
            visible: root.activeProvider !== null
              && (root.activeProvider.recentDays instanceof Array)
              && root.activeProvider.recentDays.length > 0
            width: parent.width
            implicitHeight: chartCol.implicitHeight + Style.space(22)
            radius: Style.cornerRadius
            color: root.cardFill
            border.width: 1
            border.color: root.cardBorder

            readonly property var daysData: (root.activeProvider && root.activeProvider.recentDays instanceof Array)
              ? root.activeProvider.recentDays.slice(-7)
              : []

            readonly property real maxDailyCost: {
              var m = 0
              for (var i = 0; i < daysData.length; i++) {
                var c = Number(daysData[i].costUsd !== undefined ? daysData[i].costUsd : (daysData[i].costUSD || 0))
                if (c > m) m = c
              }
              return m
            }

            readonly property double maxDailyTokens: {
              var m = 1
              for (var i = 0; i < daysData.length; i++) {
                var t = Number(daysData[i].tokens !== undefined ? daysData[i].tokens : (daysData[i].messageCount || 0))
                if (t > m) m = t
              }
              return m
            }

            Column {
              id: chartCol
              anchors.fill: parent
              anchors.margins: Style.space(11)
              spacing: Style.space(8)

              Row {
                width: parent.width

                Text {
                  width: parent.width * 0.55
                  textFormat: Text.PlainText
                  text: "7-DAY DAILY ACTIVITY"
                  color: root.subtleColor
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                  font.weight: Font.Bold
                  font.letterSpacing: 0.7
                }

                Text {
                  width: parent.width * 0.45
                  horizontalAlignment: Text.AlignRight
                  textFormat: Text.PlainText
                  text: chartCard.maxDailyCost > 0
                    ? ("Peak: " + usage.formatUsd(chartCard.maxDailyCost, false) + "/day")
                    : ("Peak: " + usage.formatCompactNumber(chartCard.maxDailyTokens) + " tok/day")
                  color: root.mutedColor
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                }
              }

              Row {
                id: barsRow
                width: parent.width
                height: Style.space(108)
                spacing: Style.space(6)

                readonly property real colWidth: chartCard.daysData.length > 0
                  ? Math.floor((width - spacing * (chartCard.daysData.length - 1)) / chartCard.daysData.length)
                  : width

                Repeater {
                  model: chartCard.daysData

                  delegate: Item {
                    id: dayCol
                    required property var modelData
                    required property int index

                    readonly property real dayCost: Number(modelData.costUsd !== undefined ? modelData.costUsd : (modelData.costUSD || 0))
                    readonly property double dayTokens: Number(modelData.tokens !== undefined ? modelData.tokens : (modelData.messageCount || 0))
                    readonly property string dayShort: usage.formatShortDay(modelData.date)
                    readonly property bool isToday: dayShort === "Today" || index === (chartCard.daysData.length - 1)
                    readonly property bool isOverQuota: Number(usage.dailyQuotaUsd || 0) > 0 && dayCost >= Number(usage.dailyQuotaUsd || 50)
                    readonly property real fillRatio: {
                      if (chartCard.maxDailyCost > 0 && dayCost > 0) {
                        return Math.max(0.08, Math.min(1.0, dayCost / chartCard.maxDailyCost))
                      }
                      if (dayTokens > 0 && chartCard.maxDailyTokens > 0) {
                        return Math.max(0.08, Math.min(1.0, dayTokens / chartCard.maxDailyTokens))
                      }
                      return 0.04
                    }

                    width: barsRow.colWidth
                    height: barsRow.height

                    // Top cost label above bar
                    Text {
                      id: topCostText
                      width: parent.width
                      anchors.top: parent.top
                      horizontalAlignment: Text.AlignHCenter
                      textFormat: Text.PlainText
                      text: dayCol.dayCost > 0
                        ? usage.formatUsd(dayCol.dayCost, dayCol.dayCost >= 100)
                        : (dayCol.dayTokens > 0 ? usage.formatCompactNumber(dayCol.dayTokens) : "—")
                      color: dayCol.isOverQuota ? root.urgentColor : (dayCol.isToday ? root.fgColor : root.mutedColor)
                      font.family: Style.font.family
                      font.pixelSize: Style.font.caption
                      font.weight: (dayCol.isToday || dayCol.isOverQuota) ? Font.Bold : Font.Normal
                      elide: Text.ElideRight
                    }

                    // Bar track
                    Rectangle {
                      id: barTrack
                      width: Math.min(Style.space(34), Math.max(Style.space(16), parent.width * 0.56))
                      anchors.horizontalCenter: parent.horizontalCenter
                      anchors.top: topCostText.bottom
                      anchors.topMargin: Style.space(4)
                      anchors.bottom: bottomLabelsCol.top
                      anchors.bottomMargin: Style.space(5)
                      radius: Style.space(5)
                      color: Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.05)

                      Rectangle {
                        width: parent.width
                        height: Math.max(Style.space(4), Math.round(parent.height * dayCol.fillRatio))
                        anchors.bottom: parent.bottom
                        radius: parent.radius
                        color: (dayCol.dayCost <= 0 && dayCol.dayTokens <= 0)
                          ? Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.14)
                          : (dayCol.isOverQuota
                            ? root.urgentColor
                            : (dayCol.isToday || barHover.containsMouse
                              ? root.accentColor
                              : Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.62)))

                        Behavior on height { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
                        Behavior on color { ColorAnimation { duration: 100 } }
                      }
                    }

                    // Bottom day & token labels
                    Column {
                      id: bottomLabelsCol
                      width: parent.width
                      anchors.bottom: parent.bottom
                      spacing: 0

                      Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        textFormat: Text.PlainText
                        text: dayCol.dayShort
                        color: dayCol.isOverQuota ? root.urgentColor : (dayCol.isToday ? root.accentColor : root.fgColor)
                        font.family: Style.font.family
                        font.pixelSize: Style.font.caption
                        font.weight: dayCol.isToday ? Font.Bold : Font.Medium
                      }

                      Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        textFormat: Text.PlainText
                        text: dayCol.dayTokens > 0 ? usage.formatCompactNumber(dayCol.dayTokens) : "0"
                        color: root.subtleColor
                        font.family: Style.font.family
                        font.pixelSize: Math.max(9, Style.font.caption - 1)
                        elide: Text.ElideRight
                      }
                    }

                    MouseArea {
                      id: barHover
                      anchors.fill: parent
                      hoverEnabled: true
                    }

                    PanelToolTip {
                      visible: barHover.containsMouse
                      text: String(dayCol.modelData.date || dayCol.dayShort)
                        + " · " + usage.formatUsd(dayCol.dayCost, false)
                        + " · " + usage.formatCompactNumber(dayCol.dayTokens) + " tok"
                        + (dayCol.modelData.prompts ? (" · " + dayCol.modelData.prompts + " prompts") : "")
                    }
                  }
                }
              }
            }
          }

          // -------------------------------------------------------------------
          // MODEL BREAKDOWN TABLE (TOKENS & COST BY MODEL)
          // -------------------------------------------------------------------
          Rectangle {
            id: modelTableCard
            visible: root.activeProvider !== null
              && (root.activeProvider.modelRows instanceof Array)
              && root.activeProvider.modelRows.length > 0
            width: parent.width
            implicitHeight: modelTableCol.implicitHeight + Style.space(22)
            radius: Style.cornerRadius
            color: root.cardFill
            border.width: 1
            border.color: root.cardBorder

            Column {
              id: modelTableCol
              anchors.fill: parent
              anchors.margins: Style.space(11)
              spacing: Style.space(6)

              // Table Header
              Row {
                x: Style.space(6)
                width: parent.width - Style.space(8)
                height: Style.space(18)

                Text {
                  width: parent.width * 0.46
                  textFormat: Text.PlainText
                  text: "TOKENS & COST BY MODEL (30D)"
                  color: root.subtleColor
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                  font.weight: Font.Bold
                  font.letterSpacing: 0.6
                  elide: Text.ElideRight
                }

                Text {
                  width: parent.width * 0.20
                  horizontalAlignment: Text.AlignRight
                  textFormat: Text.PlainText
                  text: "IN / CACHE"
                  color: root.subtleColor
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                  font.weight: Font.Bold
                }

                Text {
                  width: parent.width * 0.16
                  horizontalAlignment: Text.AlignRight
                  textFormat: Text.PlainText
                  text: "OUT"
                  color: root.subtleColor
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                  font.weight: Font.Bold
                }

                Text {
                  width: parent.width * 0.18
                  horizontalAlignment: Text.AlignRight
                  textFormat: Text.PlainText
                  text: "COST"
                  color: root.subtleColor
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                  font.weight: Font.Bold
                }
              }

              Rectangle {
                width: parent.width
                height: 1
                color: root.cardBorder
              }

              Repeater {
                model: (root.activeProvider && root.activeProvider.modelRows instanceof Array)
                  ? root.activeProvider.modelRows
                  : []

                delegate: Item {
                  id: modelRowItem
                  required property var modelData
                  required property int index

                  width: modelTableCol.width
                  height: Style.space(32)

                  // Subtle share bar background
                  Rectangle {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.max(Style.space(4), Math.round(parent.width * 0.44 * Number(modelRowItem.modelData.shareRatio || 0.05)))
                    height: Style.space(24)
                    radius: Style.space(4)
                    color: Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.08)
                  }

                  Row {
                    anchors.fill: parent
                    anchors.leftMargin: Style.space(6)
                    anchors.rightMargin: Style.space(2)

                    Text {
                      width: parent.width * 0.46
                      anchors.verticalCenter: parent.verticalCenter
                      textFormat: Text.PlainText
                      text: modelRowItem.modelData.moduleLabel
                        ? (modelRowItem.modelData.moduleLabel + " · " + modelRowItem.modelData.label)
                        : modelRowItem.modelData.label
                      color: root.fgColor
                      font.family: Style.font.family
                      font.pixelSize: Style.font.bodySmall
                      font.weight: Font.Medium
                      elide: Text.ElideRight
                    }

                    Text {
                      width: parent.width * 0.20
                      anchors.verticalCenter: parent.verticalCenter
                      horizontalAlignment: Text.AlignRight
                      textFormat: Text.PlainText
                      text: usage.formatCompactNumber(
                        Number(modelRowItem.modelData.inputTokens || 0) + Number(modelRowItem.modelData.cacheTokens || 0)
                      )
                      color: root.mutedColor
                      font.family: Style.font.family
                      font.pixelSize: Style.font.caption
                    }

                    Text {
                      width: parent.width * 0.16
                      anchors.verticalCenter: parent.verticalCenter
                      horizontalAlignment: Text.AlignRight
                      textFormat: Text.PlainText
                      text: usage.formatCompactNumber(modelRowItem.modelData.outputTokens || 0)
                      color: root.mutedColor
                      font.family: Style.font.family
                      font.pixelSize: Style.font.caption
                    }

                    Text {
                      width: parent.width * 0.18
                      anchors.verticalCenter: parent.verticalCenter
                      horizontalAlignment: Text.AlignRight
                      textFormat: Text.PlainText
                      text: usage.formatUsd(modelRowItem.modelData.costUsd, false)
                      color: root.fgColor
                      font.family: Style.font.family
                      font.pixelSize: Style.font.bodySmall
                      font.weight: Font.Bold
                    }
                  }
                }
              }
            }
          }

          // -------------------------------------------------------------------
          // ACTIVE NODES & TOP WORKSPACES BREAKDOWN (30D)
          // -------------------------------------------------------------------
          Rectangle {
            visible: root.activeProvider !== null
              && (((root.activeProvider.workspaceUsage instanceof Array) && root.activeProvider.workspaceUsage.length > 0)
                  || (root.activeNodesBreakdown.length > 0))
            width: parent.width
            implicitHeight: wsCol.implicitHeight + Style.space(20)
            radius: Style.cornerRadius
            color: root.cardFill
            border.width: 1
            border.color: root.cardBorder

            Column {
              id: wsCol
              anchors.fill: parent
              anchors.margins: Style.space(10)
              spacing: Style.space(6)

              Row {
                visible: root.activeNodesBreakdown.length > 0
                x: Style.space(6)
                width: parent.width - Style.space(8)

                Text {
                  width: parent.width - syncNodesInlineBtn.width
                  anchors.verticalCenter: parent.verticalCenter
                  textFormat: Text.PlainText
                  text: "ACTIVE NODES (30D · " + root.activeNodesBreakdown.length + (root.activeNodesBreakdown.length === 1 ? " HOST)" : " MESH HOSTS)")
                  color: root.subtleColor
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                  font.weight: Font.Bold
                  font.letterSpacing: 0.6
                }

                Rectangle {
                  id: syncNodesInlineBtn
                  width: syncNodesInlineText.implicitWidth + Style.space(12)
                  height: Style.space(18)
                  radius: height / 2
                  color: syncNodesInlineMouse.containsMouse || usage.refreshing
                    ? Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.18)
                    : Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.06)
                  border.width: 1
                  border.color: syncNodesInlineMouse.containsMouse || usage.refreshing
                    ? Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.45)
                    : Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.16)

                  Text {
                    id: syncNodesInlineText
                    anchors.centerIn: parent
                    textFormat: Text.PlainText
                    text: usage.refreshing ? "󰑓 Syncing..." : "󰑐 Sync"
                    color: usage.refreshing || syncNodesInlineMouse.containsMouse ? root.accentColor : root.mutedColor
                    font.family: Style.font.family
                    font.pixelSize: Style.font.caption
                    font.weight: Font.DemiBold
                  }

                  MouseArea {
                    id: syncNodesInlineMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: usage.refreshAll(true)
                  }
                }
              }

              Flow {
                visible: root.activeNodesBreakdown.length > 0
                width: parent.width
                spacing: Style.space(6)
                bottomPadding: Style.space(4)

                Repeater {
                  model: root.activeNodesBreakdown

                  delegate: Rectangle {
                    required property var modelData
                    width: hostChipRow.implicitWidth + Style.space(12)
                    height: Style.space(20)
                    radius: Style.space(5)
                    color: Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.06)
                    border.width: 1
                    border.color: Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.14)

                    Row {
                      id: hostChipRow
                      anchors.centerIn: parent
                      spacing: Style.space(4)

                      Text {
                        textFormat: Text.PlainText
                        text: String(modelData.host || "") + ":"
                        color: root.mutedColor
                        font.family: Style.font.family
                        font.pixelSize: Style.font.caption
                      }

                      Text {
                        textFormat: Text.PlainText
                        text: usage.formatUsd(modelData.costUsd !== undefined ? modelData.costUsd : (modelData.costUsd30d || 0), false)
                          + " (" + String(modelData.sessions !== undefined ? modelData.sessions : (modelData.sessions30d || 0)) + "s)"
                        color: root.fgColor
                        font.family: Style.font.family
                        font.pixelSize: Style.font.caption
                        font.weight: Font.DemiBold
                      }
                    }
                  }
                }
              }

              Row {
                visible: (root.activeProvider && root.activeProvider.workspaceUsage instanceof Array && root.activeProvider.workspaceUsage.length > 0)
                x: Style.space(6)
                width: parent.width - Style.space(8)

                Text {
                  width: parent.width * 0.50
                  textFormat: Text.PlainText
                  text: "TOP WORKSPACES (30D)"
                  color: root.subtleColor
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                  font.weight: Font.Bold
                  font.letterSpacing: 0.6
                }

                Text {
                  width: parent.width * 0.16
                  horizontalAlignment: Text.AlignRight
                  textFormat: Text.PlainText
                  text: "SESS / PR"
                  color: root.subtleColor
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                  font.weight: Font.Bold
                }

                Text {
                  width: parent.width * 0.16
                  horizontalAlignment: Text.AlignRight
                  textFormat: Text.PlainText
                  text: "TOKENS"
                  color: root.subtleColor
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                  font.weight: Font.Bold
                }

                Text {
                  width: parent.width * 0.18
                  horizontalAlignment: Text.AlignRight
                  textFormat: Text.PlainText
                  text: "30D COST"
                  color: root.subtleColor
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                  font.weight: Font.Bold
                }
              }

              Repeater {
                model: (root.activeProvider && root.activeProvider.workspaceUsage instanceof Array)
                  ? root.activeProvider.workspaceUsage.slice(0, 6)
                  : []

                delegate: Item {
                  id: wsRowItem
                  required property var modelData
                  required property int index
                  width: wsCol.width
                  height: Style.space(22)

                  Rectangle {
                    anchors.fill: parent
                    radius: Style.space(4)
                    color: wsRowItem.index % 2 === 0
                      ? Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.03)
                      : "transparent"
                  }

                  Row {
                    anchors.fill: parent
                    anchors.leftMargin: Style.space(6)
                    anchors.rightMargin: Style.space(2)

                    Text {
                      width: parent.width * 0.50
                      anchors.verticalCenter: parent.verticalCenter
                      textFormat: Text.PlainText
                      text: wsRowItem.modelData.moduleLabel
                        ? (wsRowItem.modelData.workspace + " (" + wsRowItem.modelData.moduleLabel + ")")
                        : String(wsRowItem.modelData.workspace || "")
                      color: root.fgColor
                      font.family: Style.font.family
                      font.pixelSize: Style.font.bodySmall
                      font.weight: Font.Medium
                      elide: Text.ElideRight
                    }

                    Text {
                      width: parent.width * 0.16
                      anchors.verticalCenter: parent.verticalCenter
                      horizontalAlignment: Text.AlignRight
                      textFormat: Text.PlainText
                      text: String(wsRowItem.modelData.sessions || 0) + " / " + String(wsRowItem.modelData.prompts || 0)
                      color: root.mutedColor
                      font.family: Style.font.family
                      font.pixelSize: Style.font.caption
                    }

                    Text {
                      width: parent.width * 0.16
                      anchors.verticalCenter: parent.verticalCenter
                      horizontalAlignment: Text.AlignRight
                      textFormat: Text.PlainText
                      text: usage.formatCompactNumber(wsRowItem.modelData.tokens || 0)
                      color: root.mutedColor
                      font.family: Style.font.family
                      font.pixelSize: Style.font.caption
                    }

                    Text {
                      width: parent.width * 0.18
                      anchors.verticalCenter: parent.verticalCenter
                      horizontalAlignment: Text.AlignRight
                      textFormat: Text.PlainText
                      text: usage.formatUsd(wsRowItem.modelData.costUsd || 0, false)
                      color: root.fgColor
                      font.family: Style.font.family
                      font.pixelSize: Style.font.bodySmall
                      font.weight: Font.Bold
                    }
                  }
                }
              }


            }
          }

          // -------------------------------------------------------------------
          // RATE LIMITS (when present, e.g. Codex / Claude / AGY)
          // -------------------------------------------------------------------
          Rectangle {
            visible: root.activeProvider !== null
              && (root.activeProvider.limits instanceof Array)
              && root.activeProvider.limits.length > 0
            width: parent.width
            implicitHeight: limitsCol.implicitHeight + Style.space(20)
            radius: Style.cornerRadius
            color: root.cardFill
            border.width: 1
            border.color: root.cardBorder

            Column {
              id: limitsCol
              anchors.fill: parent
              anchors.margins: Style.space(10)
              spacing: Style.space(6)

              Text {
                textFormat: Text.PlainText
                text: "RATE LIMITS & QUOTA WINDOWS"
                color: root.subtleColor
                font.family: Style.font.family
                font.pixelSize: Style.font.caption
                font.weight: Font.Bold
                font.letterSpacing: 0.6
              }

              Repeater {
                model: (root.activeProvider && root.activeProvider.limits instanceof Array)
                  ? root.activeProvider.limits
                  : []

                delegate: Column {
                  required property var modelData
                  width: limitsCol.width
                  spacing: Style.space(3)

                  readonly property real pct: Math.max(0, Math.min(100, Number(modelData.percent || 0)))

                  Row {
                    width: parent.width

                    Text {
                      width: parent.width * 0.6
                      textFormat: Text.PlainText
                      text: String(modelData.label || "Window")
                      color: root.fgColor
                      font.family: Style.font.family
                      font.pixelSize: Style.font.caption
                      font.weight: Font.Medium
                    }

                    Text {
                      width: parent.width * 0.4
                      horizontalAlignment: Text.AlignRight
                      textFormat: Text.PlainText
                      text: Math.round(pct) + "%" + (modelData.resetsAt ? (" · resets " + modelData.resetsAt) : "")
                      color: pct >= 85 ? root.urgentColor : root.mutedColor
                      font.family: Style.font.family
                      font.pixelSize: Style.font.caption
                    }
                  }

                  Rectangle {
                    width: parent.width
                    height: Style.space(6)
                    radius: height / 2
                    color: Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.08)

                    Rectangle {
                      width: Math.round(parent.width * (pct / 100.0))
                      height: parent.height
                      radius: parent.radius
                      color: pct >= 85 ? root.urgentColor : root.accentColor
                    }
                  }
                }
              }
            }
          }

          // -------------------------------------------------------------------
          // PROFILE & GCP TELEMETRY FOOTER CARD (Local vs Shared Org Quota)
          // -------------------------------------------------------------------
          Rectangle {
            visible: root.activeProvider !== null
              && (root.activeProvider.sharedOrgTokens30d > 0
                || root.activeProvider.totalPrompts > 0
                || root.activeProvider.totalSessions > 0)
            width: parent.width
            implicitHeight: telemetryRow.implicitHeight + Style.space(16)
            radius: Style.cornerRadius
            color: root.cardFill
            border.width: 1
            border.color: root.cardBorder

            Flow {
              id: telemetryRow
              width: parent.width - Style.space(16)
              anchors.left: parent.left
              anchors.top: parent.top
              anchors.margins: Style.space(8)
              spacing: Style.space(8)

              BadgePill {
                text: "Local 30d: " + (root.activeProvider ? root.activeProvider.totalSessions : 0) + " sessions · "
                  + (root.activeProvider ? usage.formatCompactNumber(root.activeProvider.totalPrompts) : "0") + " prompts"
                textColor: root.fgColor
              }

              BadgePill {
                visible: root.activeProvider !== null && root.activeProvider.sharedOrgTokens30d > 0
                text: "Shared GCP Project Quota (30d): " + (root.activeProvider ? usage.formatCompactNumber(root.activeProvider.sharedOrgTokens30d) : "0") + " tok"
                textColor: root.mutedColor
              }
            }
          }
        }
      }
    }
  }
}
