import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui as Ui

Ui.BarWidget {
  id: root
  moduleName: "nertwork.agents"

  property var pluginService: null
  property bool allowFallbackUsage: false

  readonly property var sharedService: root.pluginService
    ? root.pluginService
    : (root.bar && root.bar.shell
        ? (typeof root.bar.shell.ensureService === "function"
            ? root.bar.shell.ensureService("nertwork.agents")
            : (typeof root.bar.shell.firstPartyServiceFor === "function"
                ? root.bar.shell.firstPartyServiceFor("nertwork.agents")
                : null))
        : null)

  function syncServiceSettings() {
    if (root.sharedService && root.settings) {
      root.sharedService.settings = root.settings
    }
  }

  onSharedServiceChanged: syncServiceSettings()
  onSettingsChanged: syncServiceSettings()
  Component.onCompleted: Qt.callLater(function() {
    root.syncServiceSettings()
    if (!root.sharedService) {
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
    property var agyFamilyTotals: ({ count: 0, cost30d: 0, tokens30d: 0 })
    property var claudeFamilyTotals: ({ count: 0, cost30d: 0, tokens30d: 0 })
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
    active: root.allowFallbackUsage && !root.sharedService
    sourceComponent: Component {
      Main {
        settings: root.settings
      }
    }
  }

  readonly property var usage: root.sharedService
    ? root.sharedService
    : (fallbackUsageLoader.item ? fallbackUsageLoader.item : emptyUsage)
  readonly property var usageService: root.usage
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

  readonly property string barTooltip: usage.barTooltipText
  readonly property bool isOverDailyQuota: usage.isBarOverDailyQuota !== undefined
    ? !!usage.isBarOverDailyQuota
    : (Number(usage.dailyQuotaUsd || 0) > 0 && Number(usage.aggregatedTotalTodayCost || 0) >= Number(usage.dailyQuotaUsd || 50))
  readonly property color urgentColor: Color.urgent ? Color.urgent : "#e06c75"

  implicitWidth: hasVisibleAgents ? button.implicitWidth : 0
  implicitHeight: hasVisibleAgents ? button.implicitHeight : 0
  visible: hasVisibleAgents

  function ensurePanelLoaded() {
    if (!panelLoader.active) {
      panelLoader.active = true
    }
    return panelLoader.item
  }

  function open() {
    var item = ensurePanelLoaded()
    if (item) item.open()
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
    var item = ensurePanelLoaded()
    if (item) item.toggle()
  }

  function openSettings() {
    var item = ensurePanelLoaded()
    if (item) {
      item.showSettings = true
      item.open()
    }
  }

  Connections {
    target: root.usage
    function onRequestOpen() { root.open() }
    function onRequestClose() { root.close() }
    function onRequestToggle() { root.toggle() }
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
        color: root.isOverDailyQuota ? root.urgentColor : (button.active && button.useActiveColor ? button.activeColor : button.foreground)
        font.family: Style.font.family
        font.pixelSize: Style.bar.iconFont
      }

      Text {
        visible: !root.vertical && root.barCostLabel !== ""
        textFormat: Text.PlainText
        anchors.verticalCenter: parent.verticalCenter
        text: root.barCostLabel
        color: root.isOverDailyQuota ? root.urgentColor : (button.active && button.useActiveColor ? button.activeColor : button.foreground)
        font.family: Style.font.family
        font.pixelSize: Style.font.bodySmall
        font.weight: Font.DemiBold
      }
    }
  }

  Loader {
    id: panelLoader
    active: false
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
  }
}
