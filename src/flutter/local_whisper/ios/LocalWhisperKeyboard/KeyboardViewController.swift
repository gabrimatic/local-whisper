import UIKit

final class KeyboardViewController: UIInputViewController {
  private let appGroup = "group.com.gabrimatic.localWhisperFlutter"
  private let verificationToken = "[[LOCAL_WHISPER_KEYBOARD_VERIFIED]]"
  private let accent = UIColor(red: 117 / 255, green: 227 / 255, blue: 190 / 255, alpha: 1.0)
  private let panel = UIColor(red: 22 / 255, green: 26 / 255, blue: 29 / 255, alpha: 1.0)
  private let surface = UIColor(red: 44 / 255, green: 50 / 255, blue: 57 / 255, alpha: 1.0)
  private let raised = UIColor(red: 58 / 255, green: 66 / 255, blue: 74 / 255, alpha: 1.0)
  private var hapticsEnabled: Bool {
    UserDefaults(suiteName: appGroup)?.object(forKey: "keyboard.haptics") as? Bool ?? true
  }
  private var quickInsertEnabled: Bool {
    UserDefaults(suiteName: appGroup)?.object(forKey: "keyboard.quickInsert") as? Bool ?? true
  }

  override func loadView() {
    let keyboardView = UIInputView(frame: .zero, inputViewStyle: .keyboard)
    keyboardView.allowsSelfSizing = true
    view = keyboardView
  }

  override func viewDidLoad() {
    super.viewDidLoad()
    view.backgroundColor = panel
    view.isOpaque = true
    view.clipsToBounds = true
    buildKeyboard()
  }

  private func buildKeyboard() {
    let root = UIStackView()
    root.axis = .vertical
    root.spacing = 6
    root.translatesAutoresizingMaskIntoConstraints = false
    root.layoutMargins = UIEdgeInsets(top: 6, left: 6, bottom: 6, right: 6)
    root.isLayoutMarginsRelativeArrangement = true

    root.addArrangedSubview(actionRow())
    root.addArrangedSubview(buttonRow([
      key("Clean", action: #selector(insertCleanMarker), style: .mode),
      key("Message", action: #selector(insertMessageMarker), style: .mode),
      key("Notes", action: #selector(insertNotesMarker), style: .mode),
      key("Prompt", action: #selector(insertPromptMarker), style: .mode),
    ]))
    if quickInsertEnabled {
      root.addArrangedSubview(buttonRow([
        key(",", text: ", "),
        key(".", text: ". "),
        key("?", text: "? "),
        key("!", text: "! "),
        key("return", text: "\n"),
      ]))
    }
    let bottomButtons = needsInputModeSwitchKey
      ? [
        key("next", action: #selector(advanceKeyboard), style: .utility),
        key("space", text: " ", weight: 2.6),
        key("delete", action: #selector(deleteBackward), style: .utility),
      ]
      : [
        key("space", text: " ", weight: 2.6),
        key("delete", action: #selector(deleteBackward), style: .utility),
      ]
    root.addArrangedSubview(weightedButtonRow(bottomButtons))

    view.addSubview(root)
    NSLayoutConstraint.activate([
      root.leadingAnchor.constraint(equalTo: view.leadingAnchor),
      root.trailingAnchor.constraint(equalTo: view.trailingAnchor),
      root.topAnchor.constraint(equalTo: view.topAnchor),
      root.bottomAnchor.constraint(equalTo: view.bottomAnchor),
      view.heightAnchor.constraint(equalToConstant: quickInsertEnabled ? 196 : 152),
    ])
  }

  private func actionRow() -> UIStackView {
    let title = UILabel()
    title.text = "Local Whisper"
    title.font = .systemFont(ofSize: 14, weight: .semibold)
    title.textColor = .white

    let subtitle = UILabel()
    subtitle.text = "offline dictation"
    subtitle.font = .systemFont(ofSize: 10, weight: .medium)
    subtitle.textColor = UIColor.white.withAlphaComponent(0.66)
    subtitle.adjustsFontSizeToFitWidth = true
    subtitle.minimumScaleFactor = 0.82

    let labels = UIStackView(arrangedSubviews: [title, subtitle])
    labels.axis = .vertical
    labels.spacing = 2
    labels.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)

    let verifyButton = key("Verify", action: #selector(verifySetup), style: .accent)
    verifyButton.widthAnchor.constraint(equalToConstant: 108).isActive = true

    let row = UIStackView(arrangedSubviews: [labels, verifyButton])
    row.axis = .horizontal
    row.alignment = .center
    row.distribution = .fill
    row.spacing = 12
    return row
  }

  private func buttonRow(_ buttons: [UIButton]) -> UIStackView {
    let row = UIStackView(arrangedSubviews: buttons)
    row.axis = .horizontal
    row.distribution = .fillEqually
    row.spacing = 6
    return row
  }

  private func weightedButtonRow(_ buttons: [UIButton]) -> UIStackView {
    let row = UIStackView(arrangedSubviews: buttons)
    row.axis = .horizontal
    row.distribution = .fillProportionally
    row.spacing = 6
    return row
  }

  private enum KeyStyle {
    case normal
    case mode
    case utility
    case accent
  }

  private func key(
    _ title: String,
    text: String? = nil,
    action: Selector? = nil,
    style: KeyStyle = .normal,
    weight: CGFloat = 1
  ) -> UIButton {
    let button = UIButton(type: .system)
    button.setTitle(title, for: .normal)
    button.titleLabel?.font = .systemFont(
      ofSize: title.count > 7 ? 12 : 14,
      weight: style == .accent ? .bold : .semibold
    )
    button.titleLabel?.adjustsFontSizeToFitWidth = true
    button.titleLabel?.minimumScaleFactor = 0.75
    button.setTitleColor(style == .accent ? .black : .white, for: .normal)
    button.backgroundColor = switch style {
    case .accent:
      accent
    case .utility:
      raised
    case .mode, .normal:
      surface
    }
    button.contentEdgeInsets = UIEdgeInsets(top: 0, left: 4, bottom: 0, right: 4)
    button.layer.cornerRadius = 7
    button.layer.cornerCurve = .continuous
    button.heightAnchor.constraint(equalToConstant: style == .accent ? 34 : 38).isActive = true
    button.accessibilityLabel = title
    if let text {
      button.accessibilityValue = text
      button.addTarget(self, action: #selector(insertButtonText(_:)), for: .touchUpInside)
    } else if let action {
      button.addTarget(self, action: action, for: .touchUpInside)
    }
    button.widthAnchor.constraint(greaterThanOrEqualToConstant: 37 * weight).isActive = true
    return button
  }

  private func tapFeedback() {
    guard hapticsEnabled else { return }
    UIImpactFeedbackGenerator(style: .light).impactOccurred()
  }

  @objc private func insertCleanMarker() {
    tapFeedback()
    textDocumentProxy.insertText("[Clean] ")
  }

  @objc private func insertButtonText(_ sender: UIButton) {
    guard let text = sender.accessibilityValue else { return }
    tapFeedback()
    textDocumentProxy.insertText(text)
  }

  @objc private func insertMessageMarker() {
    tapFeedback()
    textDocumentProxy.insertText("[Message] ")
  }

  @objc private func insertNotesMarker() {
    tapFeedback()
    textDocumentProxy.insertText("[Notes]\n")
  }

  @objc private func insertPromptMarker() {
    tapFeedback()
    textDocumentProxy.insertText("[Prompt] ")
  }

  @objc private func deleteBackward() {
    tapFeedback()
    textDocumentProxy.deleteBackward()
  }

  @objc private func advanceKeyboard() {
    advanceToNextInputMode()
  }

  @objc private func verifySetup() {
    tapFeedback()
    textDocumentProxy.insertText(verificationToken)
  }
}
