import SwiftUI

// MARK: - Settings component library
//
// The building blocks all settings panels are made of. A panel is a
// `PanelScaffold` containing `SettingsCard`s; each card stacks `SettingRow`s
// (label + control) and `WideRow`s (full-width content). Dividers between
// rows are inserted automatically. Descriptions live inline under titles so
// nothing important hides in hover tooltips.

// MARK: - Panel scaffold

struct PanelScaffold<Content: View>: View {
    let title: String
    var subtitle: String? = nil
    @ViewBuilder var content: () -> Content

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.xl) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(title)
                        .font(Theme.Typography.pageTitle)
                    if let subtitle {
                        Text(subtitle)
                            .font(Theme.Typography.body)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(.bottom, Theme.Spacing.xs)

                content()
            }
            .padding(.horizontal, Theme.Spacing.xxxl)
            .padding(.top, Theme.Spacing.xxl)
            .padding(.bottom, Theme.Spacing.xxxl)
            .frame(maxWidth: 720, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .center)
        }
        .scrollIndicators(.automatic)
    }
}

// MARK: - Card

struct SettingsCard<Content: View>: View {
    var icon: String? = nil
    var title: String? = nil
    var description: String? = nil
    var tint: Color = Theme.Brand.accent
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s + 2) {
            if title != nil || icon != nil {
                header
            }
            VStack(spacing: 0) {
                Group(subviews: content()) { subviews in
                    let lastID = subviews.last?.id
                    ForEach(subviews) { subview in
                        subview
                        if subview.id != lastID {
                            RowDivider()
                        }
                    }
                }
            }
            .cardSurface()
        }
    }

    @ViewBuilder
    private var header: some View {
        HStack(alignment: .firstTextBaseline, spacing: Theme.Spacing.s) {
            if let icon {
                Image(systemName: icon)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(tint)
                    .symbolRenderingMode(.hierarchical)
                    .frame(width: 16)
            }
            VStack(alignment: .leading, spacing: 2) {
                if let title {
                    Text(title)
                        .font(Theme.Typography.sectionHeader)
                        .foregroundStyle(.primary)
                }
                if let description {
                    Text(description)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(.leading, 2)
    }
}

// MARK: - Rows

/// Divider between card rows, inset like the row content.
struct RowDivider: View {
    var body: some View {
        Rectangle()
            .fill(Theme.Surface.divider)
            .frame(height: 1)
            .padding(.leading, Theme.Spacing.l)
    }
}

/// Label (+ optional inline description) on the left, control on the right.
struct SettingRow<Control: View>: View {
    let title: String
    var subtitle: String? = nil
    @ViewBuilder var control: () -> Control

    var body: some View {
        HStack(alignment: .center, spacing: Theme.Spacing.l) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(Theme.Typography.bodyEmphasized)
                if let subtitle {
                    Text(subtitle)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: Theme.Spacing.l)
            control()
                .labelsHidden()
        }
        .padding(.horizontal, Theme.Spacing.l)
        .padding(.vertical, 11)
    }
}

/// Toggle row: switch on the right, label + description on the left.
struct ToggleRow: View {
    let title: String
    var subtitle: String? = nil
    let isOn: Bool
    let onChange: (Bool) -> Void

    var body: some View {
        SettingRow(title: title, subtitle: subtitle) {
            Toggle(title, isOn: Binding(get: { isOn }, set: onChange))
                .toggleStyle(.switch)
                .controlSize(.small)
                .labelsHidden()
        }
    }
}

/// Full-width row for editors, notices, progress bars, and charts.
struct WideRow<Content: View>: View {
    var verticalPadding: CGFloat = 11
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            content()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, Theme.Spacing.l)
        .padding(.vertical, verticalPadding)
    }
}

// MARK: - Empty state

struct EmptyStateView: View {
    let icon: String
    let title: String
    let message: String

    var body: some View {
        VStack(spacing: Theme.Spacing.xs + 2) {
            Image(systemName: icon)
                .font(.system(size: 22, weight: .regular))
                .foregroundStyle(.tertiary)
                .symbolRenderingMode(.hierarchical)
            Text(title)
                .font(Theme.Typography.bodyEmphasized)
            Text(message)
                .font(Theme.Typography.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, Theme.Spacing.xl)
    }
}

// MARK: - Selection card (radio-style choice used by Grammar / Onboarding)

struct ChoiceCard: View {
    let icon: String
    let tint: Color
    let title: String
    let subtitle: String
    let isSelected: Bool
    var badge: String? = nil
    let action: () -> Void

    @State private var hovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: Theme.Spacing.m) {
                SectionIcon(symbol: icon, tint: tint)
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: Theme.Spacing.xs + 2) {
                        Text(title).font(Theme.Typography.bodyEmphasized)
                        if let badge {
                            StatusPill(text: badge, tone: .accent)
                        }
                    }
                    Text(subtitle)
                        .font(Theme.Typography.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 16, weight: .medium))
                    .foregroundStyle(isSelected ? Theme.Brand.accent : Color.secondary.opacity(0.4))
                    .symbolRenderingMode(.hierarchical)
            }
            .padding(Theme.Spacing.m)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: Theme.Radius.medium, style: .continuous)
                    .fill(isSelected
                          ? Theme.Brand.accent.opacity(0.09)
                          : (hovering ? Theme.Surface.hover : Theme.Surface.card))
            )
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.medium, style: .continuous)
                    .strokeBorder(
                        isSelected ? Theme.Brand.accent.opacity(0.45) : Theme.Surface.stroke,
                        lineWidth: 1
                    )
            )
            .contentShape(RoundedRectangle(cornerRadius: Theme.Radius.medium))
        }
        .buttonStyle(.plain)
        .onHover { hovering = $0 }
        .animation(Theme.Motion.hover, value: hovering)
        .accessibilityAddTraits(isSelected ? [.isSelected] : [])
    }
}

// MARK: - Quick chip toggle (menu bar panel)

struct QuickToggleChip: View {
    let icon: String
    let title: String
    let isOn: Bool
    let action: () -> Void

    @State private var hovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .font(.system(size: 11, weight: .semibold))
                    .symbolRenderingMode(.hierarchical)
                Text(title)
                    .font(Theme.Typography.captionEmphasized)
                    .lineLimit(1)
                Spacer(minLength: 0)
                Circle()
                    .fill(isOn ? Theme.Brand.accent : Color.secondary.opacity(0.3))
                    .frame(width: 6, height: 6)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: Theme.Radius.small + 2, style: .continuous)
                    .fill(isOn ? Theme.Brand.accent.opacity(0.13) : Theme.Surface.well.opacity(hovering ? 1.0 : 0.7))
            )
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.small + 2, style: .continuous)
                    .strokeBorder(isOn ? Theme.Brand.accent.opacity(0.35) : Theme.Surface.stroke, lineWidth: 1)
            )
            .foregroundStyle(isOn ? .primary : .secondary)
            .contentShape(RoundedRectangle(cornerRadius: Theme.Radius.small + 2))
        }
        .buttonStyle(.plain)
        .onHover { hovering = $0 }
        .animation(Theme.Motion.hover, value: hovering)
        .accessibilityLabel("\(title), \(isOn ? "on" : "off")")
        .accessibilityAddTraits(.isToggle)
    }
}
