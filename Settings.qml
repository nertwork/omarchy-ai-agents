import QtQuick
import QtQuick.Controls
import Quickshell
import qs.Commons
import qs.Ui as Ui

Item {
  id: root

  property var usage: null
  property color fgColor: Color.popups.text
  property color bgColor: Color.popups.background
  property color borderColor: Color.popups.border
  property color accentColor: Color.accent
  property color mutedColor: Qt.darker(fgColor, 1.35)
  property color subtleColor: Qt.darker(fgColor, 1.72)

  implicitWidth: parent ? parent.width : Style.space(516)
  implicitHeight: settingsColumn.implicitHeight

  component SectionCard: Rectangle {
    id: card
    property string title: ""
    property string subtitle: ""
    default property alias content: innerColumn.data

    width: parent ? parent.width : Style.space(516)
    implicitHeight: innerColumn.implicitHeight + Style.space(22)
    radius: Style.cornerRadius
    color: Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.035)
    border.width: 1
    border.color: Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.12)

    Column {
      id: innerColumn
      anchors.fill: parent
      anchors.margins: Style.space(11)
      spacing: Style.space(8)

      Column {
        visible: card.title !== ""
        width: parent.width
        spacing: Style.space(2)

        Text {
          textFormat: Text.PlainText
          text: card.title
          color: root.mutedColor
          font.family: Style.font.family
          font.pixelSize: Style.font.caption
          font.weight: Font.Bold
          font.letterSpacing: 0.7
        }

        Text {
          visible: card.subtitle !== ""
          width: parent.width
          textFormat: Text.PlainText
          text: card.subtitle
          color: root.subtleColor
          font.family: Style.font.family
          font.pixelSize: Style.font.caption
          wrapMode: Text.WordWrap
        }
      }
    }
  }

  component ToggleRow: Rectangle {
    id: rowRoot
    property string label: ""
    property string description: ""
    property string badgeText: ""
    property bool checked: false
    signal toggled(bool value)

    width: parent ? parent.width : Style.space(492)
    implicitHeight: Math.max(Style.space(36), textCol.implicitHeight + Style.space(10))
    radius: Math.max(4, Style.cornerRadius - 2)
    color: rowHover.containsMouse
      ? Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.05)
      : "transparent"

    Column {
      id: textCol
      anchors.left: parent.left
      anchors.leftMargin: Style.space(6)
      anchors.right: toggleSwitch.left
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
              parent.width - (badgeRect.visible ? badgeRect.width + parent.spacing : 0)
            )
          )
          textFormat: Text.PlainText
          anchors.verticalCenter: parent.verticalCenter
          text: rowRoot.label
          color: root.fgColor
          font.family: Style.font.family
          font.pixelSize: Style.font.bodySmall
          font.weight: Font.Medium
          elide: Text.ElideRight
        }

        Rectangle {
          id: badgeRect
          visible: rowRoot.badgeText !== ""
          anchors.verticalCenter: parent.verticalCenter
          width: badgeLabel.implicitWidth + Style.space(10)
          height: Style.space(16)
          radius: height / 2
          color: Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.14)
          border.width: 1
          border.color: Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.35)

          Text {
            id: badgeLabel
            anchors.centerIn: parent
            textFormat: Text.PlainText
            text: rowRoot.badgeText
            color: root.accentColor
            font.family: Style.font.family
            font.pixelSize: Style.font.caption - 1
            font.weight: Font.DemiBold
          }
        }
      }

      Text {
        visible: rowRoot.description !== ""
        width: parent.width
        textFormat: Text.PlainText
        text: rowRoot.description
        color: root.subtleColor
        font.family: Style.font.family
        font.pixelSize: Style.font.caption
        elide: Text.ElideRight
      }
    }

    Ui.ToggleSwitch {
      id: toggleSwitch
      anchors.right: parent.right
      anchors.rightMargin: Style.space(6)
      anchors.verticalCenter: parent.verticalCenter
      checked: rowRoot.checked
      foreground: root.fgColor
      accent: root.accentColor
      onToggled: rowRoot.toggled(!rowRoot.checked)
    }

    MouseArea {
      id: rowHover
      anchors.left: parent.left
      anchors.top: parent.top
      anchors.bottom: parent.bottom
      anchors.right: toggleSwitch.left
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onClicked: rowRoot.toggled(!rowRoot.checked)
    }
  }

  Column {
    id: settingsColumn
    width: parent.width
    spacing: Style.space(10)

    SectionCard {
      title: "EXECUTION & AGGREGATION"
      subtitle: "Multi-host or localhost collection with optional multi-module rollups."

      ToggleRow {
        label: "Localhost-only collection"
        badgeText: (root.usage && root.usage.localhostOnly) ? "localhost" : "5 nodes"
        description: "When enabled, restrict collection to this host only (disables multi-host SSH fan-out)"
        checked: root.usage ? root.usage.localhostOnly : false
        onToggled: function(val) {
          if (root.usage) root.usage.setSetting("localhostOnly", val)
        }
      }

      Rectangle {
        width: parent.width
        implicitHeight: quotaCol.implicitHeight + Style.space(12)
        radius: Math.max(4, Style.cornerRadius - 2)
        color: "transparent"

        Column {
          id: quotaCol
          anchors.left: parent.left
          anchors.right: parent.right
          anchors.margins: Style.space(6)
          anchors.verticalCenter: parent.verticalCenter
          spacing: Style.space(6)

          Column {
            width: parent.width
            spacing: Style.space(6)

            Column {
              width: parent.width
              spacing: Style.space(2)

              Row {
                spacing: Style.space(6)

                Text {
                  anchors.verticalCenter: parent.verticalCenter
                  textFormat: Text.PlainText
                  text: "Daily Cost Quota"
                  color: root.fgColor
                  font.family: Style.font.family
                  font.pixelSize: Style.font.bodySmall
                  font.weight: Font.Medium
                }

                Rectangle {
                  anchors.verticalCenter: parent.verticalCenter
                  width: qBadgeLbl.implicitWidth + Style.space(10)
                  height: Style.space(16)
                  radius: height / 2
                  color: (root.usage && root.usage.isOverDailyQuota)
                    ? Qt.rgba(1.0, 0.24, 0.24, 0.20)
                    : Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.14)
                  border.width: 1
                  border.color: (root.usage && root.usage.isOverDailyQuota)
                    ? "#ff4d4d"
                    : Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.35)

                  Text {
                    id: qBadgeLbl
                    anchors.centerIn: parent
                    textFormat: Text.PlainText
                    text: (!root.usage || root.usage.dailyQuotaUsd <= 0)
                      ? "Off"
                      : ("$" + Math.round(root.usage.dailyQuotaUsd) + "/day" + (root.usage && root.usage.isOverDailyQuota ? (" · Today " + root.usage.formatUsd(root.usage.aggregatedTotalTodayCost, true)) : ""))
                    color: (root.usage && root.usage.isOverDailyQuota) ? "#ff4d4d" : root.accentColor
                    font.family: Style.font.family
                    font.pixelSize: Style.font.caption - 1
                    font.weight: Font.DemiBold
                  }
                }
              }

              Text {
                width: parent.width
                textFormat: Text.PlainText
                text: "Highlights status bar pill, Today card, and daily chart bars in red when daily spend meets quota"
                color: root.subtleColor
                font.family: Style.font.family
                font.pixelSize: Style.font.caption
                elide: Text.ElideRight
              }
            }

            Row {
              id: stepperRow
              spacing: Style.space(6)

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
                  readonly property real curQuota: root.usage ? Number(root.usage.dailyQuotaUsd || 0) : 50
                  readonly property bool isSelected: modelData.preset >= 0 && Math.round(curQuota) === modelData.preset
                  width: chipTxt.implicitWidth + Style.space(10)
                  height: Style.space(22)
                  radius: height / 2
                  color: isSelected
                    ? Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.22)
                    : (chipMouse.containsMouse
                      ? Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.12)
                      : Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.06))
                  border.width: 1
                  border.color: isSelected
                    ? root.accentColor
                    : Qt.rgba(root.fgColor.r, root.fgColor.g, root.fgColor.b, 0.18)

                  Text {
                    id: chipTxt
                    anchors.centerIn: parent
                    textFormat: Text.PlainText
                    text: modelData.label
                    color: isSelected ? root.accentColor : root.fgColor
                    font.family: Style.font.family
                    font.pixelSize: Style.font.caption
                    font.weight: isSelected ? Font.Bold : Font.Medium
                  }

                  MouseArea {
                    id: chipMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                      if (!root.usage) return
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

      ToggleRow {
        label: "Show aggregated totals banner"
        badgeText: "Overview"
        description: "Display combined AGY + Claude spend and token rollup across enabled modules at top of panel"
        checked: root.usage ? root.usage.showAggregatedSummary : true
        onToggled: function(val) {
          if (root.usage) root.usage.setSetting("showAggregatedSummary", val)
        }
      }

      ToggleRow {
        label: "Show cost in status bar"
        badgeText: root.usage && root.usage.barDisplayMode === "active" ? "Active Module" : (root.usage && root.usage.barCostWindow === "30d" ? "30d $" : "Today $")
        description: "Render live " + (root.usage && root.usage.barCostWindow === "30d" ? "30d" : "daily (Today)") + " USD spend next to the AI Agents status bar icon (turns red ≥ $" + (root.usage ? root.usage.dailyQuotaUsd : 50) + "/day)"
        checked: root.usage ? root.usage.showBarCost : true
        onToggled: function(val) {
          if (root.usage) root.usage.setSetting("showBarCost", val)
        }
      }

      ToggleRow {
        label: "Show current daily cost"
        badgeText: root.usage && root.usage.barCostWindow === "30d" ? "30d Window" : ("Today ($" + (root.usage ? root.usage.dailyQuotaUsd : 50) + " budget)")
        description: "Default to current daily (Today) cost in the status bar, tabs, and summary strips instead of 30-day cumulative cost"
        checked: root.usage ? (root.usage.barCostWindow !== "30d") : true
        onToggled: function(val) {
          if (root.usage) root.usage.setSetting("barCostWindow", val ? "today" : "30d")
        }
      }

      ToggleRow {
        label: "Bar widget displays aggregated total"
        badgeText: root.usage && root.usage.barCostWindow === "30d" ? "30d Rollup" : "Daily Rollup"
        description: "When enabled, bar cost shows combined spend across enabled modules; otherwise shows active tab"
        checked: root.usage ? (root.usage.barDisplayMode !== "active") : true
        onToggled: function(val) {
          if (root.usage) root.usage.setSetting("barDisplayMode", val ? "aggregated" : "active")
        }
      }
    }

    SectionCard {
      title: "AGY MODULES (PERSONAL, ORG & ENTERPRISE VERTEX AI)"
      subtitle: "Enable Antigravity profiles across Personal (Homelab), Org (Cloud), and Enterprise (Work / Sandbox)."

      Repeater {
        model: root.usage ? root.usage.providersByGroup("agy") : []
        delegate: ToggleRow {
          required property var modelData
          label: modelData.displayName
          badgeText: modelData.badge
          description: modelData.description
          checked: modelData.enabled
          onToggled: function(val) {
            if (root.usage) root.usage.setProviderEnabled(modelData.id, val)
          }
        }
      }
    }

    SectionCard {
      title: "CLAUDE MODULES (WORK / ENTERPRISE & PERSONAL)"
      subtitle: "Enable secondary/work Claude profile and/or primary personal Claude (~/.claude)."

      Repeater {
        model: root.usage ? root.usage.providersByGroup("claude") : []
        delegate: ToggleRow {
          required property var modelData
          label: modelData.displayName
          badgeText: modelData.badge
          description: modelData.description
          checked: modelData.enabled
          onToggled: function(val) {
            if (root.usage) root.usage.setProviderEnabled(modelData.id, val)
          }
        }
      }
    }

    SectionCard {
      title: "OTHER AI CODING PROVIDERS"
      subtitle: "Optional local CLI and IDE coding assistants."

      Repeater {
        model: root.usage ? root.usage.providersByGroup("other") : []
        delegate: ToggleRow {
          required property var modelData
          label: modelData.displayName
          badgeText: modelData.badge
          description: modelData.description
          checked: modelData.enabled
          onToggled: function(val) {
            if (root.usage) root.usage.setProviderEnabled(modelData.id, val)
          }
        }
      }
    }
  }
}
