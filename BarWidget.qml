import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui as Ui

Ui.BarWidget {
  id: root
  moduleName: "nertwork.agents"

  Main {
    id: usage
    settings: root.settings
  }

  readonly property alias usageService: usage
  readonly property alias anchorButton: button
  readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false
  readonly property bool panelOpened: opened
  readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing === true : false
  readonly property bool hasVisibleAgents: usage.enabledProviders.length > 0
  readonly property var activeProvider: usage.currentProvider

  readonly property real displayCostValue: {
    var win = usage.barCostWindow
    if (usage.barDisplayMode === "active" && activeProvider) {
      if (win === "today") return Number(activeProvider.todayCostUsd || 0)
      if (win === "7d") return Number(activeProvider.sevenDayCostUsd || 0)
      return Number(activeProvider.thirtyDayCostUsd || 0)
    }
    if (win === "today") return Number(usage.aggregatedTotalTodayCost || 0)
    if (win === "7d") return Number(usage.aggregatedTotal7dCost || 0)
    return Number(usage.aggregatedTotal30dCost || 0)
  }

  readonly property string barCostLabel: {
    if (!usage.showBarCost || usage.barDisplayMode === "icon" || root.vertical) return ""
    return usage.formatUsd(displayCostValue, true)
  }

  readonly property string barTooltip: {
    if (!hasVisibleAgents) return "AI Agents · No modules enabled"
    var totalLine = "Localhost Total: Today " + usage.formatUsd(usage.aggregatedTotalTodayCost, false)
      + " · 7d " + usage.formatUsd(usage.aggregatedTotal7dCost, false)
      + " · 30d " + usage.formatUsd(usage.aggregatedTotal30dCost, false)
    if (activeProvider) {
      return activeProvider.shortLabel + " (" + usage.formatUsd(activeProvider.thirtyDayCostUsd, false) + " 30d)  |  " + totalLine
    }
    return totalLine
  }

  implicitWidth: hasVisibleAgents ? button.implicitWidth : 0
  implicitHeight: hasVisibleAgents ? button.implicitHeight : 0
  visible: hasVisibleAgents

  function open() {
    if (panelLoader.item) panelLoader.item.open()
  }

  function close() {
    if (panelLoader.item) panelLoader.item.close()
  }

  function closeForPopoutSwitch() {
    if (panelLoader.item && panelLoader.item.closeForPopoutSwitch) {
      panelLoader.item.closeForPopoutSwitch()
    } else {
      close()
    }
  }

  function toggle() {
    if (panelLoader.item) panelLoader.item.toggle()
  }

  function openSettings() {
    if (panelLoader.item) {
      panelLoader.item.showSettings = true
      panelLoader.item.open()
    }
  }

  IpcHandler {
    target: "nertwork.agents"

    function open(): void { root.open() }
    function close(): void { root.close() }
    function show(): void { root.open() }
    function hide(): void { root.close() }
    function toggle(): string {
      root.toggle()
      return root.opened ? "opened" : "closed"
    }

    function refresh(): string {
      usage.refreshAll(true)
      return "refreshing"
    }

    function status(): string {
      var mods = []
      for (var i = 0; i < usage.enabledProviders.length; i++) {
        var p = usage.enabledProviders[i]
        mods.push({
          id: p.id,
          shortLabel: p.shortLabel,
          profile: p.profile,
          todayCostUsd: p.todayCostUsd,
          sevenDayCostUsd: p.sevenDayCostUsd,
          thirtyDayCostUsd: p.thirtyDayCostUsd,
          thirtyDayTokens: p.thirtyDayTokens
        })
      }
      return JSON.stringify({
        opened: root.opened,
        localhostOnly: usage.localhostOnly,
        showAggregatedSummary: usage.showAggregatedSummary,
        barDisplayMode: usage.barDisplayMode,
        barCostLabel: root.barCostLabel,
        aggregatedTodayCostUsd: usage.aggregatedTotalTodayCost,
        aggregated7dCostUsd: usage.aggregatedTotal7dCost,
        aggregated30dCostUsd: usage.aggregatedTotal30dCost,
        agyFamily30dCostUsd: usage.agyFamilyTotals.thirtyDayCostUsd,
        claudeFamily30dCostUsd: usage.claudeFamilyTotals.thirtyDayCostUsd,
        enabledCount: usage.enabledProviders.length,
        enabledModules: mods
      })
    }
  }

  Ui.WidgetButton {
    id: button
    bar: root.bar
    active: root.opened
    visible: root.hasVisibleAgents
    hasVisualContent: true
    labelVisible: false
    tooltipText: root.barTooltip

    fixedWidth: root.vertical
      ? Style.bar.sizeVertical
      : (root.barCostLabel !== "" ? contentRow.implicitWidth + Style.space(14) : Style.bar.iconSlot)
    fixedHeight: root.vertical ? Style.bar.iconSlot : Style.bar.sizeHorizontal

    onPressed: function(mouseButton) {
      if (mouseButton === Qt.LeftButton) {
        root.toggle()
      } else if (mouseButton === Qt.MiddleButton) {
        usage.cycleProvider(1)
      } else if (mouseButton === Qt.RightButton) {
        root.openSettings()
      }
    }

    Row {
      id: contentRow
      anchors.centerIn: parent
      spacing: Style.space(5)

      Text {
        textFormat: Text.PlainText
        anchors.verticalCenter: parent.verticalCenter
        text: "󱚣"
        color: button.active && button.useActiveColor ? button.activeColor : button.foreground
        font.family: Style.font.family
        font.pixelSize: Style.bar.iconFont
      }

      Text {
        visible: !root.vertical && root.barCostLabel !== ""
        textFormat: Text.PlainText
        anchors.verticalCenter: parent.verticalCenter
        text: root.barCostLabel
        color: button.active && button.useActiveColor ? button.activeColor : button.foreground
        font.family: Style.font.family
        font.pixelSize: Style.font.bodySmall
        font.weight: Font.DemiBold
      }
    }
  }

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
  }
}
