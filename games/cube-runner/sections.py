"""
Level sections: the level is a chain of sections (~10 s each) rather than a
chain of unrelated single obstacles. Two kinds:

* Theme sections (built from patterns.py): one family of obstacles (spikes,
  blocks, pits, pads & orbs, tunnels), on a steady rhythm, phrased like music
  -- a motif, a repeat, a variation, a climax -- e.g. A A B A B C.

* Drawn sections: hand-authored ASCII in sections/*.txt (format below). They
  give connected terrain (rooftops, caves, pillar hops) that random pieces
  can't. They're drawn at the starting speed and stretched horizontally to
  the current speed, so they feel the same at any speed.

Drawn section format (one file per section):

    title: Rooftops            display name (for reading the files and tests)
    min_d: 0.25                difficulty (0..1) at which it can appear
    variant: gravity           optional: only used when CUBE_VARIANT includes it
                               (ship, gravity, hold, ...)
                               (blank line ends the header)
         ^       ######
      ######     ######        one character = 1 cube; y is up
    ------   ----------        last line is the ground: '-' ground, ' ' pit

    #  block (sitting over a pit it becomes a pillar rising out of the pit)
    =  hatched ceiling: deadly to touch (run under it)
    ^  spike, v  hanging spike, J  jump pad, o  orb
    >  ship portal: from here on you fly (hold the laser to climb, release
       to sink; sliding along the floor or under a '#' roof is safe, a
       block's side, a hatched ceiling or a spike is not)
    <  cube portal: back to running and jumping
       (stack the portal character vertically to draw the gate's height;
       a portal triggers wherever you are in its column)
    c  coin (coins variant; without any, coins are placed automatically)
    ' ' or '.'  empty air

  Gravity flip (CUBE_VARIANT=gravity):
    u  gravity portal -> upside down. A vertical run of u's in one column is
       one gate; touching any part of it flips you. You fall up, run along
       the undersides of '#' blocks (draw a rail of them overhead), and
       jumping goes down. Hatched '=' stays deadly from below; flying off the
       top of the screen is a fall. 'v' spikes are the hazards on a rail.
    d  gravity portal -> back to normal (same gate rules)
    @  flip orb: touch it with the laser on to flip gravity either way

Start and end every drawing with at least 3 columns of flat ground, in normal
gravity and cube mode (put a '<' after every '>', with flat runway behind it).
"""
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .const import *
from . import patterns as pmod

SECTIONS_DIR = Path(__file__).resolve().parent / "sections"


# -- shared physics helpers (also used by World) --------------------------------

def speed_at(x: float) -> float:
    return min(SPEED_MAX, SPEED_START + x * SPEED_RAMP_PER_UNIT)


def _full_jump_air_s() -> float:
    if "hold" not in VARIANTS:
        return 2 * JUMP_VELOCITY / GRAVITY
    # hold variant: air time of a fully held jump
    t, y, v, dt = 0.0, 0.0, HOLD_JUMP_VELOCITY, 1 / 240
    while y >= 0.0:
        g = HOLD_GRAVITY if HOLD_GRACE_S <= t < MAX_HOLD_S else HOLD_VARIANT_GRAVITY
        v -= g * dt
        y += v * dt
        t += dt
    return t


FULL_JUMP_AIR_S = _full_jump_air_s()


def min_gap_at(x: float) -> float:
    """Shortest runway allowed between two obstacles at world x: one full jump at
    the speed you'll have there, plus landing room, so a jump over the end of one
    obstacle never lands you against the start of the next."""
    jump_len = speed_at(x) * FULL_JUMP_AIR_S
    return max(GAP_MIN, jump_len + GAP_LANDING_ROOM)


def parts_extent(parts) -> float:
    end = 0.0
    for p in parts:
        kind, dx = p[0], p[1]
        width = p[2] if kind in ("block", "pit", "ceiling") else 1.0
        end = max(end, dx + width)
    return end


# -- sections -----------------------------------------------------------------------

@dataclass
class Section:
    name: str          # unique id
    title: str         # shown in-game
    min_d: float
    # (rng, difficulty, world x of the section start) -> parts relative to the start
    build: Callable = field(repr=False)
    variant: Optional[str] = None   # experiment variant this needs (CUBE_VARIANT), or None

    def is_available(self, d: float) -> bool:
        return d >= self.min_d


# -- theme sections ------------------------------------------------------------

THEMES = {
    # name: (title, pattern names roughly easiest -> hardest)
    "spikes": ("Spike Rhythm", ["single_spike", "double_spike", "spaced_spikes",
                                "triple_spike", "pad_over_spikes"]),
    "blocks": ("Blocks", ["low_block", "two_blocks", "spike_then_block", "stairs_two",
                          "platform_with_spike", "floating_platform_over_spikes",
                          "stairs_three", "pyramid", "spike_gauntlet", "tower"]),
    "pits": ("Pits", ["small_pit", "pad_over_pit", "pit_then_spike", "stepping_stones",
                      "triple_pit", "rising_pillars", "block_over_pit_edge"]),
    "air": ("Pads & Orbs", ["pad_onto_wall", "orb_over_wide_pit", "pad_over_pit",
                            "pad_to_floating_ledge", "pad_over_spikes", "orb_spike_field",
                            "pad_on_block", "orb_to_high_block", "orb_chain_over_pit"]),
    "tunnels": ("Tunnels", ["low_tunnel", "single_spike", "double_spike", "tunnel_then_spike",
                            "spiked_ceiling_over_platform", "tunnel_spike_tunnel"]),
}

if "hold" in VARIANTS:   # staccato hop patterns (see the end of patterns.py)
    THEMES["spikes"][1].insert(1, "hop_train")
    THEMES["tunnels"][1][1:1] = ["hang_row_hops", "hops_then_wall"]
    THEMES["morse"] = ("Morse Code", ["single_spike", "hop_train", "hang_row_hops",
                                      "hops_then_wall"])

# A = an easy motif, B = a harder one, C = the hardest unlocked (the climax)
PHRASES = ["AABABC", "ABABCC", "AABBAC", "ABACBC"]
RHYTHM_EXTRA = [0.0, 0.5, 1.5]     # runway added to the minimum gap: tight / medium / relaxed


def _by_name():
    return {name: (mind, fn) for mind, name, fn in pmod.PATTERNS}


def theme_motifs(theme: str, d: float):
    """Patterns of the theme unlocked at difficulty d, easiest first."""
    lib = _by_name()
    avail = [(lib[n][0], n, lib[n][1]) for n in THEMES[theme][1] if lib[n][0] <= d]
    return sorted(avail, key=lambda t: t[0])


def build_theme(theme: str, rng, d: float, x0: float):
    motifs = theme_motifs(theme, d)
    easy = motifs[:max(1, (len(motifs) + 1) // 2)]
    a = rng.choice(easy)
    rest = [m for m in motifs if m is not a] or [a]
    b = rng.choice(rest[:-1] or rest)
    c = motifs[-1]
    # each motif is built once and repeated verbatim: repetition is what makes it a rhythm
    phrase = rng.choice(PHRASES)
    est_len = 6 * (6 + min_gap_at(x0))
    v = speed_at(x0 + est_len)          # the fastest it will be played at
    built = {k: m[2](rng, d, v=v) for k, m in (("A", a), ("B", b), ("C", c))}

    gap = min_gap_at(x0 + est_len) + rng.choice(RHYTHM_EXTRA)   # fixed: a steady beat
    parts, x = [], 0.0
    for i, letter in enumerate(phrase):
        motif = built[letter]
        parts += [(p[0], p[1] + x) + tuple(p[2:]) for p in motif]
        x += parts_extent(motif) + (gap if i < len(phrase) - 1 else 0.0)
    return with_coins(parts)


def theme_sections() -> List[Section]:
    out = []
    for theme, (title, names) in THEMES.items():
        lib = _by_name()
        # needs two motifs to make a phrase
        min_d = sorted(lib[n][0] for n in names)[1]
        out.append(Section(
            name=f"theme:{theme}", title=title, min_d=min_d,
            build=lambda rng, d, x0, t=theme: build_theme(t, rng, d, x0)))
    return out


# -- drawn (ASCII) sections -------------------------------------------------------------

def parse_drawing(text: str, name: str = "?"):
    """ASCII drawing -> parts (at the starting speed)."""
    lines = [ln.rstrip("\n") for ln in text.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        raise ValueError(f"{name}: empty drawing")
    width = len(lines[-1].rstrip())
    if width == 0 or any(len(ln.rstrip()) > width for ln in lines):
        raise ValueError(f"{name}: the ground line (last line) must be the longest line")
    lines = [ln.ljust(width) for ln in lines]
    ground, rows = lines[-1], lines[:-1][::-1]      # rows[0] is y = 0..1

    bad = set(ground) - set("- .")
    if bad:
        raise ValueError(f"{name}: ground line may only contain '-' and ' ' (found {bad})")
    pit = [ch != "-" for ch in ground]
    for edge in (ground[:3], ground[-3:]):
        if edge != "---":
            raise ValueError(f"{name}: start and end with at least 3 columns of ground")

    parts = []
    # pits
    c = 0
    while c < width:
        if pit[c]:
            s = c
            while c < width and pit[c]:
                c += 1
            parts.append(("pit", s, c - s))
        else:
            c += 1

    # ship/cube gates: one per column, spanning the rows the character is drawn in
    portal_cols: Dict[int, list] = {}
    for y, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch in "<>":
                mode = "ship" if ch == ">" else "cube"
                g = portal_cols.setdefault(c, [mode, y, y + 1])
                if g[0] != mode:
                    raise ValueError(f"{name}: column {c} mixes '<' and '>'")
                g[1], g[2] = min(g[1], y), max(g[2], y + 1)
    for c, (mode, y0, y1) in sorted(portal_cols.items()):
        if y1 - y0 == 1:
            y1 = y0 + PORTAL_HEIGHT
        parts.append(("gate", c, mode, float(y0), float(y1)))

    # single-cell things
    for y, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch == "^":
                parts.append(("spike", c, float(y)))
            elif ch == "v":
                parts.append(("hang", c, float(y + 1)))
            elif ch == "J":
                parts.append(("pad", c, float(y)))
            elif ch == "o":
                parts.append(("orb", c, y + 0.5))
            elif ch == "@":
                parts.append(("fliporb", c, y + 0.5))
            elif ch in "ud":
                if y > 0 and rows[y - 1][c] == ch:
                    continue        # part of the gate started below
                top = y
                while top < len(rows) and rows[top][c] == ch:
                    top += 1
                parts.append(("portal", c, float(y), float(top), -1.0 if ch == "u" else 1.0))
            elif ch == "c":
                parts.append(("coin", c, y + 0.5))
            elif ch not in " .#=<>":
                raise ValueError(f"{name}: unknown character {ch!r} at column {c}")

    # blocks and ceilings: vertical runs per column, merged across columns
    def col_runs(c):
        runs = set()
        y = 0
        while y < len(rows):
            ch = rows[y][c]
            if ch in "#=":
                s = y
                while y < len(rows) and rows[y][c] == ch:
                    y += 1
                bottom = float(s)
                if ch == "#" and s == 0 and pit[c]:
                    bottom = pmod.PILLAR
                runs.add((ch, bottom, float(y)))
            else:
                y += 1
        return runs

    open_runs: Dict[tuple, int] = {}

    def close(key, end):
        ch, bottom, top = key
        start = open_runs.pop(key)
        if ch == "#":
            parts.append(("block", start, end - start, top, bottom))
        else:
            parts.append(("ceiling", start, end - start, bottom, top))

    for c in range(width + 1):
        runs = col_runs(c) if c < width else set()
        for key in [k for k in open_runs if k not in runs]:
            close(key, c)
        for key in runs:
            open_runs.setdefault(key, c)
    return parts, float(width)


def stretch(parts, k: float):
    """Stretch a drawing horizontally by k (= current speed / starting speed) so it
    takes the same time to play at any speed. Point objects keep their size and
    are centred in their stretched cell; a run of n spikes becomes floor(n*k)
    spikes; pits keep the same air time for the 1-wide player ((w-1)*k + 1)."""
    if abs(k - 1.0) < 1e-9:
        return list(parts)
    out = []
    spikes = {}
    for p in parts:
        kind = p[0]
        if kind in ("block", "ceiling"):
            out.append((kind, p[1] * k, p[2] * k) + tuple(p[3:]))
        elif kind == "pit":
            x, w = p[1], p[2]
            nw = (w - 1) * k + 1
            out.append(("pit", (x + w / 2) * k - nw / 2, nw))
        elif kind in ("spike", "hang"):
            spikes.setdefault((kind, p[2]), []).append(p[1])
        else:  # pad, orb, coin: centre in the stretched cell
            out.append((kind, (p[1] + 0.5) * k - 0.5) + tuple(p[2:]))
    for (kind, base), xs in spikes.items():
        xs.sort()
        i = 0
        while i < len(xs):
            j = i
            while j + 1 < len(xs) and xs[j + 1] == xs[j] + 1:
                j += 1
            n = j - i + 1
            n2 = max(1, math.floor(n * k + 1e-9))
            start = xs[i] * k + (n * k - n2) / 2
            out += [(kind, start + m, base) for m in range(n2)]
            i = j + 1
    return out


def parse_section_file(path: Path) -> Section:
    text = path.read_text(encoding="utf-8")
    header, _, drawing = text.partition("\n\n")
    meta = {}
    for line in header.splitlines():
        key, sep, value = line.partition(":")
        if not sep:
            raise ValueError(f"{path.name}: bad header line {line!r} (header ends at the first blank line)")
        meta[key.strip()] = value.strip()
    parts, length = parse_drawing(drawing, path.name)
    parts = with_coins(parts)   # placed on the unstretched drawing, stretched with it
    name = path.stem
    return Section(
        name=f"drawn:{name}", title=meta.get("title", name.replace("_", " ").title()),
        min_d=float(meta.get("min_d", 0.0)), variant=meta.get("variant") or None,
        build=lambda rng, d, x0, parts=parts, length=length: _place_drawing(parts, length, x0))


def _place_drawing(parts, length, x0):
    # stretch for the speed at the section's end (speed only grows) -> never harder than drawn
    k = speed_at(x0) / DRAW_SPEED
    k = speed_at(x0 + length * k) / DRAW_SPEED
    return stretch(parts, k)


def drawn_sections(directory: Path = SECTIONS_DIR) -> List[Section]:
    return [parse_section_file(p) for p in sorted(directory.glob("*.txt"))]


# -- coins (CUBE_VARIANT=coins) -----------------------------------------------------------

def with_coins(parts):
    """Coins variant: keep hand-placed coins, or place some automatically if there are
    none. Otherwise strip them, so the level is exactly as without the variant."""
    if "coins" not in VARIANTS:
        return [p for p in parts if p[0] != "coin"]
    if any(p[0] == "coin" for p in parts):
        return list(parts)
    return list(parts) + auto_coins(parts)


def auto_coins(parts):
    """Coins where taking them costs something: high over spikes (a well-timed or late
    jump), over a pit's far side, up on a platform (needs a jump from it), or just under
    a jumpable ceiling. They never change the physics, so a section stays beatable
    whether or not you go for them."""
    blocks = [(p[1], p[1] + p[2], p[4], p[3]) for p in parts if p[0] == "block"]
    solids = blocks + [(p[1], p[1] + p[2], p[3], p[4] if len(p) > 4 else p[3] + CEILING_THICKNESS)
               for p in parts if p[0] == "ceiling"]
    hazards = [(p[1], p[2], p[0] == "hang") for p in parts if p[0] in ("spike", "hang")]

    def overhead(cx, y):
        """Lowest solid underside above height y around column cx (or None)."""
        bs = [b for (l, r, b, t) in solids if l < cx + 1.0 and r > cx and b >= y - 1e-6]
        return min(bs) if bs else None

    def free(cx, cy):
        for (l, r, b, t) in solids:
            if l - 0.4 < cx < r + 0.4 and b - 0.4 < cy < t + 0.4:
                return False
        for (x, base, down) in hazards:
            sy = base - 0.5 if down else base + 0.5
            if abs(x + 0.5 - cx) < 1.0 and abs(sy - cy) < 1.0:
                return False
        return True

    cands = []   # (x of the cell, y)
    # spikes: high over a lone spike (a jump peaking right over it), low over the last
    # spike of a group (a late, tight jump)
    ups = sorted((p[1], p[2]) for p in parts if p[0] == "spike")
    i = 0
    while i < len(ups):
        j = i
        while j + 1 < len(ups) and ups[j + 1][1] == ups[i][1] and ups[j + 1][0] - ups[j][0] < 1.5:
            j += 1
        x, base = ups[j]
        y = base + (3.0 if i == j else 2.0)
        top = overhead(x + 0.5, base + 1.0)
        if top is not None:
            y = min(y, top - 1.0)
        cands.append((x, y))
        i = j + 1
    # platforms: a coin you need to jump up from the platform for
    for (l, r, b, t) in blocks:
        if r - l >= 3 and t >= 1.0:
            cx = (l + r) / 2
            top = overhead(cx, t + 0.5)
            y = t + 2.8 if top is None else top - 1.0
            if y > t + 0.9:
                cands.append((cx - 0.5, y))
    # pits: high over the middle (jump right at the edge to peak there)
    for p in parts:
        if p[0] == "pit" and p[2] >= 3:
            cands.append((p[1] + p[2] / 2 - 0.5, 3.0))
    # jumpable ceilings: just under them
    for p in parts:
        if p[0] == "ceiling" and p[3] >= 3.0:
            cands.append((p[1] + p[2] / 2 - 0.5, p[3] - 1.0))

    out, last = [], -1e9
    for x, y in sorted(cands):
        if x - last >= COIN_SPACING and free(x + 0.5, y):
            out.append(("coin", x, y))
            last = x
    return out


def all_sections() -> List[Section]:
    return theme_sections() + drawn_sections()


INTRO = "drawn:00_warmup"     # always the first section
