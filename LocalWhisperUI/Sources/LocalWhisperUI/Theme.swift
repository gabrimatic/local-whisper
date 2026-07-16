import SwiftUI
import AppKit

// MARK: - Theme
//
// Single source of truth for the app's visual language: color palette,
// typography, spacing, radii, and semantic tones. Every surface (settings
// window, menu bar panel, overlay, onboarding, About) reads from here.
//
// Identity: graphite surfaces, mint as the one interactive accent, sky as a
// secondary informational hue. The settings sidebar is always graphite-dark
// regardless of system appearance; content areas adapt to light/dark.

extension Color {
    /// Appearance-resolving color (light/dark decided at draw time).
    static func dynamic(light: NSColor, dark: NSColor) -> Color {
        Color(nsColor: NSColor(name: nil) { appearance in
            appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? dark : light
        })
    }

    init(hex: UInt32) {
        self.init(
            red: Double((hex >> 16) & 0xFF) / 255.0,
            green: Double((hex >> 8) & 0xFF) / 255.0,
            blue: Double(hex & 0xFF) / 255.0
        )
    }
}

private func nsHex(_ hex: UInt32, _ alpha: CGFloat = 1.0) -> NSColor {
    NSColor(
        srgbRed: CGFloat((hex >> 16) & 0xFF) / 255.0,
        green: CGFloat((hex >> 8) & 0xFF) / 255.0,
        blue: CGFloat(hex & 0xFF) / 255.0,
        alpha: alpha
    )
}

enum Theme {

    // MARK: Palette

    enum Brand {
        // Graphite family (sidebar + dark surfaces).
        static let graphiteDeep = Color(hex: 0x0A0F14)
        static let graphite     = Color(hex: 0x10161D)
        static let graphiteEdge = Color(hex: 0x1C2530)

        // Mint — the single interactive accent.
        static let mintDark  = Color(hex: 0x75E3BE)
        static let mintLight = Color(hex: 0x00775A)
        static let accent = Color.dynamic(light: nsHex(0x00775A), dark: nsHex(0x75E3BE))

        // Sky — secondary informational hue.
        static let skyDark  = Color(hex: 0x8DDCFF)
        static let skyLight = Color(hex: 0x006491)
        static let sky = Color.dynamic(light: nsHex(0x006491), dark: nsHex(0x8DDCFF))

        // Legacy call sites resolve by scheme; both map to the dynamic colors.
        static func accent(for colorScheme: ColorScheme) -> Color {
            colorScheme == .dark ? mintDark : mintLight
        }

        static func sky(for colorScheme: ColorScheme) -> Color {
            colorScheme == .dark ? skyDark : skyLight
        }
    }

    // MARK: Surfaces

    enum Surface {
        /// Content-area window background.
        static let window = Color.dynamic(light: nsHex(0xF4F5F7), dark: nsHex(0x10161D))
        /// Raised card fill sitting on `window`.
        static let card = Color.dynamic(light: .white, dark: nsHex(0x171F29))
        /// Slightly recessed fill (search fields, key wells, code chips).
        static let well = Color.dynamic(light: nsHex(0xECEEF1), dark: nsHex(0x121922))
        /// Hairline stroke around cards.
        static let stroke = Color.dynamic(light: nsHex(0x000000, 0.10), dark: nsHex(0xFFFFFF, 0.08))
        /// Inset divider between card rows.
        static let divider = Color.dynamic(light: nsHex(0x000000, 0.07), dark: nsHex(0xFFFFFF, 0.06))
        /// Hover wash over interactive rows.
        static let hover = Color.dynamic(light: nsHex(0x000000, 0.045), dark: nsHex(0xFFFFFF, 0.05))

        // Sidebar is always graphite, independent of system appearance.
        static let sidebarTop = Brand.graphiteDeep
        static let sidebarBottom = Color(hex: 0x0E141B)
        static let sidebarStroke = Color.white.opacity(0.07)
        static let sidebarTextPrimary = Color.white.opacity(0.92)
        static let sidebarTextSecondary = Color.white.opacity(0.55)
        static let sidebarTextTertiary = Color.white.opacity(0.35)
    }

    // MARK: Typography

    enum Typography {
        /// Hero numbers (Activity stat cards) and About hero.
        static let display = Font.system(size: 28, weight: .semibold, design: .rounded)
        /// Panel page titles.
        static let pageTitle = Font.system(size: 22, weight: .bold, design: .rounded)
        /// Window-level titles (About heading, onboarding steps).
        static let title = Font.system(size: 20, weight: .semibold, design: .rounded)
        /// Card titles / section headers above cards.
        static let sectionHeader = Font.system(size: 13, weight: .semibold)
        /// Card titles inside panels.
        static let headline = Font.system(size: 15, weight: .semibold)
        /// Default body text.
        static let body = Font.system(size: 13, weight: .regular)
        static let bodyEmphasized = Font.system(size: 13, weight: .medium)
        /// Supporting text under a label.
        static let caption = Font.system(size: 11.5, weight: .regular)
        static let captionEmphasized = Font.system(size: 11.5, weight: .medium)
        /// Monospaced for numeric stats and key glyphs.
        static let mono = Font.system(size: 12, weight: .regular, design: .monospaced)
        static let monoLarge = Font.system(size: 17, weight: .semibold, design: .monospaced)
        static let monoSmall = Font.system(size: 11, weight: .regular, design: .monospaced)
    }

    // MARK: Spacing (multiples of 4)

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

    // MARK: Motion

    enum Motion {
        static let panelSwitch = Animation.snappy(duration: 0.20)
        static let hover = Animation.easeOut(duration: 0.12)
        static let state = Animation.smooth(duration: 0.18)
    }

    // MARK: Status tones (semantic colors used by StatusPill, badges, dots)

    enum Tone {
        case neutral
        case success
        case warning
        case danger
        case info
        case accent

        @MainActor
        var color: Color {
            switch self {
            case .neutral: return .secondary
            case .success: return Color.dynamic(light: nsHex(0x1E7D45), dark: nsHex(0x4CD97B))
            case .warning: return Color.dynamic(light: nsHex(0xA05A00), dark: nsHex(0xFFB454))
            case .danger:  return Color.dynamic(light: nsHex(0xB3261E), dark: nsHex(0xFF6B5E))
            case .info:    return Brand.sky
            case .accent:  return Brand.accent
            }
        }

        @MainActor
        func color(for colorScheme: ColorScheme) -> Color {
            color
        }
    }
}

// MARK: - View helpers built on Theme

extension View {

    /// Card surface used for grouped content blocks.
    func cardSurface(radius: CGFloat = Theme.Radius.large) -> some View {
        background(Theme.Surface.card, in: RoundedRectangle(cornerRadius: radius))
            .overlay(
                RoundedRectangle(cornerRadius: radius)
                    .strokeBorder(Theme.Surface.stroke, lineWidth: 1)
            )
    }

    /// Tinted card surface (highlighted action cards).
    func tintedCard(_ color: Color, radius: CGFloat = Theme.Radius.large) -> some View {
        background(color.opacity(0.08), in: RoundedRectangle(cornerRadius: radius))
            .overlay(
                RoundedRectangle(cornerRadius: radius)
                    .strokeBorder(color.opacity(0.20), lineWidth: 1)
            )
    }
}

// MARK: - Section icon chip (rounded-square, brand-consistent)

struct SectionIcon: View {
    let symbol: String
    let tint: Color
    var diameter: CGFloat = 32
    var fontSize: CGFloat = 14
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: diameter * 0.3, style: .continuous)
                .fill(tint.opacity(colorScheme == .dark ? 0.16 : 0.12))
                .frame(width: diameter, height: diameter)
                .overlay(
                    RoundedRectangle(cornerRadius: diameter * 0.3, style: .continuous)
                        .strokeBorder(tint.opacity(colorScheme == .dark ? 0.22 : 0.24), lineWidth: 1)
                )
            Image(systemName: symbol)
                .font(.system(size: fontSize, weight: .semibold))
                .foregroundStyle(tint)
                .symbolRenderingMode(.hierarchical)
        }
        .accessibilityHidden(true)
    }
}

// MARK: - Keyboard-glyph rendering

enum KeyboardGlyph {
    /// Convert "ctrl+shift+g" / "alt+t" / "cmd+,"  into ["⌃","⇧","G"] / ["⌥","T"] / ["⌘",","]
    static func tokens(for raw: String) -> [String] {
        raw.split(separator: "+").map { piece -> String in
            let token = piece.trimmingCharacters(in: .whitespaces)
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

    /// Trigger keys are physical key sides ("alt_r"), not modifier combos —
    /// render them with the side qualifier next to the symbol.
    static func triggerTokens(for key: String) -> [String] {
        switch key {
        case "alt_r":   return ["⌥", "Right"]
        case "alt_l":   return ["⌥", "Left"]
        case "ctrl_r":  return ["⌃", "Right"]
        case "ctrl_l":  return ["⌃", "Left"]
        case "cmd_r":   return ["⌘", "Right"]
        case "cmd_l":   return ["⌘", "Left"]
        case "shift_r": return ["⇧", "Right"]
        case "shift_l": return ["⇧", "Left"]
        case "caps_lock": return ["⇪"]
        default:        return [key.uppercased()]
        }
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
            .padding(.vertical, 2.5)
            .background(Theme.Surface.well, in: RoundedRectangle(cornerRadius: 5))
            .overlay(
                RoundedRectangle(cornerRadius: 5)
                    .strokeBorder(Theme.Surface.stroke, lineWidth: 1)
                    .opacity(emphasis ? 1.5 : 1)
            )
            .foregroundStyle(.primary)
    }
}
