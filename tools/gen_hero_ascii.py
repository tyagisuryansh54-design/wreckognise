"""Generate the hero's ASCII vessel.

Hand-padding a hull by eye produced a rectangle: the widest rows landed at the
top and bottom, so the silhouette squared off instead of tapering. Here the
half-width per row comes from a curve, so the hull is a lens by construction
and the shading follows the edge rather than being placed by hand.

Output is written as UTF-8 (the Windows console is cp1252 and cannot print box
drawing) and pasted into HeroAsciiCore.jsx.
"""

import math
from pathlib import Path

W = 78
CX = W // 2
ROWS = 21           # hull rows
HALF = 34           # half-width amidships

OUT = Path(__file__).with_name("art.txt")

# Edge shading, outermost first. Reads as a lit rim falling away into the hull.
RIM = "░▒▓█"


def hull_half(i: int) -> int:
    """Half-width of the hull at row i.

    A plain ellipse tapers to nothing at the ends, leaving two blank rows where
    the bow and stern should be. The flatter exponent keeps the hull full for
    longer and the floor gives the ends a real cap to draw.
    """
    # t is scaled short of +/-1 so the curve never reaches zero. Clamping a
    # curve that does reach zero leaves the cap 12 columns narrower than the
    # row beneath it, and the bow and stern read as bars floating clear of the
    # hull.
    t = 0.86 * (i - (ROWS - 1) / 2) / ((ROWS - 1) / 2)
    return int(round(HALF * (max(0.0, 1 - t * t) ** 0.42)))


# --- the neural lattice, drawn amidships --------------------------------------
# Every line is 27 columns. Uneven padding here reads on screen as a lattice
# that has slipped off the centreline of a hull that is itself symmetric.
LATTICE = [
    "┌─────────────────────────┐",
    "│  o───o───o───o───o───o  │",
    "│  │\\ /│\\ /│\\ /│\\ /│\\ /│  │",
    "│  o───█───█───█───█───o  │",
    "│  │/ \\│/ \\│/ \\│/ \\│/ \\│  │",
    "│  o───o───o───o───o───o  │",
    "└─────────────────────────┘",
]


def build() -> list[str]:
    grid = [[" "] * W for _ in range(ROWS)]

    for i in range(ROWS):
        h = hull_half(i)

        # Interior ribs: two faint arcs inboard of the rim, which give the hull
        # volume. Without them the lens is an outline and reads flat.
        for inset, ch in ((7, "·"), (11, "░")):
            for side in (-1, 1):
                x = CX + side * (h - inset)
                if 0 <= x < W and abs(x - CX) > 13:
                    grid[i][x] = ch

        for d, ch in enumerate(RIM):
            for side in (-1, 1):
                x = CX + side * (h - d)
                if 0 <= x < W:
                    grid[i][x] = ch

        # Close the bow and stern rather than leaving two loose pips.
        if i in (0, ROWS - 1):
            for x in range(CX - h, CX + h + 1):
                if 0 <= x < W:
                    grid[i][x] = "▒" if abs(x - CX) > h - 2 else "▓"

    # Outrigger fins amidships, so the silhouette reads as a craft rather than
    # an eye.
    mid = ROWS // 2
    for dy, arm in ((-1, "══"), (0, "═══"), (1, "══")):
        h = hull_half(mid + dy)
        for side in (-1, 1):
            for k, ch in enumerate(arm):
                x = CX + side * (h + 1 + k)
                if 0 <= x < W:
                    grid[mid + dy][x] = ch

    # lattice, centred
    top = (ROWS - len(LATTICE)) // 2
    for r, line in enumerate(LATTICE):
        start = CX - len(line) // 2
        for c, ch in enumerate(line):
            x = start + c
            if 0 <= x < W:
                grid[top + r][x] = ch

    body = ["".join(r) for r in grid]

    mast = [
        "·".center(W),
        "|".center(W),
        "/|\\".center(W),
        "/ | \\".center(W),
    ]
    rake = [
        "\\ | /".center(W),
        "\\|/".center(W),
        "|".center(W),
        "·".center(W),
    ]
    return mast + body + rake


if __name__ == "__main__":
    art = build()
    width = max(len(l) for l in art)
    art = [l.ljust(width) for l in art]
    OUT.write_text("\n".join(art), encoding="utf-8")
    print(f"  {len(art)} lines x {width} cols -> {OUT}")
