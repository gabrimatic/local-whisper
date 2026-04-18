import SwiftUI

// MARK: - Theme
//
// Single source of truth for typography, spacing, color tones, corner radii, and
// icon defaults. Every visible surface (overlay, menu bar, settings panels,
// onboarding, About) reads from here so the app stays internally consistent.

enum Theme {

    // MARK: Typography

    enum Typography {
        // Display: hero numbers and big counts (Activity stat cards, About hero).
        static let display = Font.system(size: 28, weight: .semibold, design: .rounded)
        // Title: window-level page titles (panel headers, About heading).
        static let title = Font.system(size: 20, weight: .semibold, design: .rounded)
        // Section header inside a Form / panel.
        static let sectionHeader = Font.system(size: 13, weight: .semibold)
        // Headline: card titles inside panels.
        static let headline = Font.system(size: 15, weight: .semibold)
        // Default body text.
        static let body = Font.system(size: 13, weight: .regular)
        // Body with emphasis (button labels, list item titles).
        static let bodyEmphasized = Font.system(size: 13, weight: .medium)
        // Caption: supporting text under a label.
        static let caption = Font.system(size: 11, weight: .regular)
        static let captionEmphasized = Font.system(size: 11, weight: .medium)
        // Monospaced for numeric stats and key glyphs.
        static let mono = Font.system(size: 12, weight: .regular, design: .monospaced)
        static let monoLarge = Font.system(size: 17, weight: .semibold, design: .monospaced)
        static let monoSmall = Font.system(size: 11, weight: .regular, design: .monospaced)
    }

    // MARK: Spacing (multiples of 4 for predictable rhythm)

    enum Spacing {
        static let xs: CGFloat = 4
        static let s: CGFloat = 8
        static let m: CGFloat = 12
        static let l: CGFloat = 16
        static let xl: CGFloat = 20
        static let xxl: CGFloat = 24
        static let xxxl: CGFloat = 32
    }

    // MARK: Corner radius

    enum Radius {
        static let small: CGFloat = 6
        static let medium: CGFloat = 10
        static let large: CGFloat = 14
        static let pill: CGFloat = 999
    }

    // MARK: Status tones (semantic colors used by StatusPill, badges, dots)

    enum Tone {
        case neutral
        case success
        case warning
        case danger
        case info

        @MainActor
        var color: Color {
            switch self {
            case .neutral: return .secondary
            case .success: return .green
            case .warning: return .orange
            case .danger:  return .red
            case .info:    return .accentColor
            }
        }
    }

    // MARK: Sidebar accents (per Settings section)

    enum SectionAccent {
        case recording, transcription, grammar, voice, vocabulary, output, shortcuts, activity, advanced, about

        @MainActor
        var color: Color {
            switch self {
            case .recording:    return .red
            case .transcription: return .blue
            case .grammar:      return .indigo
            case .voice:        return .teal
            case .vocabulary:   return .orange
            case .output:       return .purple
            case .shortcuts:    return .pink
            case .activity:     return .green
            case .advanced:     return .gray
            case .about:        return .secondary
            }
        }
    }
}

// MARK: - View modifiers and helpers built on Theme

extension View {

    /// Card surface used for stat cards, credits, and grouped content blocks.
    func cardSurface(radius: CGFloat = Theme.Radius.large) -> some View {
        background(Color.secondary.opacity(0.07), in: RoundedRectangle(cornerRadius: radius))
            .overlay(
                RoundedRectangle(cornerRadius: radius)
                    .strokeBorder(Color.secondary.opacity(0.10))
            )
    }

    /// Tinted card surface (used for highlighted action cards like "replay tutorial").
    func tintedCard(_ color: Color, radius: CGFloat = Theme.Radius.large) -> some View {
        background(color.opacity(0.08), in: RoundedRectangle(cornerRadius: radius))
            .overlay(
                RoundedRectangle(cornerRadius: radius)
                    .strokeBorder(color.opacity(0.18))
            )
    }
}

// MARK: - Stable section labels (icon + text with consistent metrics)

struct SectionIcon: View {
    let symbol: String
    let tint: Color
    var diameter: CGFloat = 32
    var fontSize: CGFloat = 14

    var body: some View {
        ZStack {
            Circle()
                .fill(tint.opacity(0.16))
                .frame(width: diameter, height: diameter)
            Image(systemName: symbol)
                .font(.system(size: fontSize, weight: .semibold))
                .foregroundStyle(tint)
                .symbolRenderingMode(.hierarchical)
        }
    }
}

// MARK: - Keyboard-glyph rendering

enum KeyboardGlyph {
    /// Convert "ctrl+shift+g" / "alt+t" / "cmd+,"  into ["⌃","⇧","G"] / ["⌥","T"] / ["⌘",","]
    static func tokens(for raw: String) -> [String] {
        raw.split(separator: "+").map { token -> String in
            switch token.lowercased() {
            case "cmd", "command":     return "⌘"
            case "ctrl", "control":    return "⌃"
            case "alt", "option", "opt": return "⌥"
            case "shift":              return "⇧"
            case "tab":                return "⇥"
            case "return", "enter":    return "↩"
            case "esc", "escape":      return "⎋"
            case "space":              return "␣"
            case "delete", "backspace": return "⌫"
            case "left":  return "←"
            case "right": return "→"
            case "up":    return "↑"
            case "down":  return "↓"
            default:
                return token.count == 1 ? token.uppercased() : token.capitalized
            }
        }
    }

    /// Joined display, e.g. "⌃⇧G".
    static func display(_ raw: String) -> String {
        tokens(for: raw).joined()
    }
}

// MARK: - KeyCap rendering (small key glyph chip)

struct KeyCap: View {
    let label: String
    var emphasis: Bool = false

    var body: some View {
        Text(label)
            .font(Theme.Typography.monoSmall)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(Color.secondary.opacity(emphasis ? 0.22 : 0.16),
                        in: RoundedRectangle(cornerRadius: 4))
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .strokeBorder(Color.secondary.opacity(0.18), lineWidth: 0.5)
            )
            .foregroundStyle(.primary)
    }
}
