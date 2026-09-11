/**
 * ASCII hull for the console hero, generated rather than hand-drawn.
 *
 * Every line must be the same length and the character set is restricted to
 * ASCII, box drawing and the U+2580 blocks -- rarer glyphs render as tofu in
 * fonts that lack them, which destroys the alignment the art exists for.
 *
 * `block()` re-pads at render time so an edit here cannot leave the arrays
 * ragged.
 */

const CORE = [
  '                                      ·                                       ',
  '                                      |                                       ',
  '                                     /|\\                                      ',
  '                                    / | \\                                     ',
  '                    ▒▒▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒▒                   ',
  '                ░▒▓█   ·                               ·   █▓▒░               ',
  '             ░▒▓█   ·   ░                             ░   ·   █▓▒░            ',
  '           ░▒▓█   ·   ░                                 ░   ·   █▓▒░          ',
  '         ░▒▓█   ·   ░                                     ░   ·   █▓▒░        ',
  '        ░▒▓█   ·   ░                                       ░   ·   █▓▒░       ',
  '       ░▒▓█   ·   ░                                         ░   ·   █▓▒░      ',
  '      ░▒▓█   ·   ░        ┌─────────────────────────┐        ░   ·   █▓▒░     ',
  '     ░▒▓█   ·   ░         │  o───o───o───o───o───o  │         ░   ·   █▓▒░    ',
  '   ══░▒▓█   ·   ░         │  │\\ /│\\ /│\\ /│\\ /│\\ /│  │         ░   ·   █▓▒░══  ',
  '  ═══░▒▓█   ·   ░         │  o───█───█───█───█───o  │         ░   ·   █▓▒░═══ ',
  '   ══░▒▓█   ·   ░         │  │/ \\│/ \\│/ \\│/ \\│/ \\│  │         ░   ·   █▓▒░══  ',
  '     ░▒▓█   ·   ░         │  o───o───o───o───o───o  │         ░   ·   █▓▒░    ',
  '      ░▒▓█   ·   ░        └─────────────────────────┘        ░   ·   █▓▒░     ',
  '       ░▒▓█   ·   ░                                         ░   ·   █▓▒░      ',
  '        ░▒▓█   ·   ░                                       ░   ·   █▓▒░       ',
  '         ░▒▓█   ·   ░                                     ░   ·   █▓▒░        ',
  '           ░▒▓█   ·   ░                                 ░   ·   █▓▒░          ',
  '             ░▒▓█   ·   ░                             ░   ·   █▓▒░            ',
  '                ░▒▓█   ·                               ·   █▓▒░               ',
  '                    ▒▒▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒▒                   ',
  '                                    \\ | /                                     ',
  '                                     \\|/                                      ',
  '                                      |                                       ',
  '                                      ·                                       ',
]

/** Small screens: the full hull needs ~78 columns to stay legible. */
const CORE_COMPACT = [
  '                      ·                       ',
  '                      |                       ',
  '                     /|\\                      ',
  '                    / | \\                     ',
  '            ▒▒▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒▒           ',
  '        ░▒▓█                       █▓▒░       ',
  '      ░▒▓█                           █▓▒░     ',
  '     ░▒▓█      ┌───────────────┐      █▓▒░    ',
  '    ░▒▓█       │   o───o───o   │       █▓▒░   ',
  ' ══░▒▓█  ·     │   │\\ /│\\ /│   │     ·  █▓▒░══',
  '═══░▒▓█  ·     │   o───█───o   │     ·  █▓▒░══',
  ' ══░▒▓█  ·     │   │/ \\│/ \\│   │     ·  █▓▒░══',
  '    ░▒▓█       │   o───o───o   │       █▓▒░   ',
  '     ░▒▓█      └───────────────┘      █▓▒░    ',
  '      ░▒▓█                           █▓▒░     ',
  '        ░▒▓█                       █▓▒░       ',
  '            ▒▒▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒▒           ',
  '                    \\ | /                     ',
  '                     \\|/                      ',
  '                      |                       ',
  '                      ·                       ',
]

export { CORE, CORE_COMPACT }

/** Pad to a common width so a ragged edit cannot skew the drawing. */
export function block(lines) {
  const width = Math.max(...lines.map((l) => l.length))
  return lines.map((l) => l.padEnd(width)).join('\n')
}
