# Local web workspace accessibility review

Review date: 2026-08-03. Scope: the localhost-only workspace in
`runtime/lamf/web`, exercised with an empty synthetic LAMF instance. No real
memory, token, personal path, screenshot, or unrelated application was used.

## Reproduced barriers and narrow resolutions

- Keyboard users had no way to bypass the sticky header. A focus-revealed skip
  link now targets the main region.
- Navigation and library filters communicated selection only through color and
  CSS classes. The current view now uses `aria-current="page"`; filters expose
  and update `aria-pressed`.
- The search dialog referenced a missing `search-title`, leaving its accessible
  name incomplete. It now has a visually hidden heading and an explicitly named
  close button.
- Client-side view changes left focus on the navigation control. Each view now
  moves focus to its unique heading so the new context is announced.
- Search, library, review, and recent-memory updates were silent. Bounded polite
  live regions and `aria-busy` now expose loading and completion without
  interrupting the user.
- Several icon-only close controls and decorative glyphs had ambiguous spoken
  output. Close controls now have task-specific names and decorative glyphs are
  hidden from the accessibility tree.
- Keyboard focus depended on browser defaults. A consistent high-contrast
  `:focus-visible` outline was added while preserving reduced-motion behavior.
- Authentication and remember-form failures were not announced. Their existing
  inline errors now use alert semantics; the access field references its error.

## Verification

- Keyboard-only synthetic walkthrough: unlock, primary navigation, filters,
  search dialog, remember dialog, health dialog, and Escape/close behavior.
- Browser accessibility-tree inspection: named landmarks/dialogs, current and
  pressed states, focus targets, and live regions.
- `python runtime/tests/web_accessibility_test.py` on every CI operating system.
- Existing final, smoke, harness, and installer tests remain required.

## Limits

This is a basic screen-reader-oriented review, not certification against every
WCAG success criterion. Automated semantics and browser accessibility-tree
inspection do not replace testing with current NVDA, JAWS, VoiceOver, and
TalkBack releases. Native `<dialog>` focus behavior also depends on the browser;
future release reviews should repeat the keyboard walkthrough in supported
browsers with synthetic data.
