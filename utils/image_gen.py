"""
Matchup card — clean pill-row esports template.
1400 × 787 px (16:9), gold border, red/blue pill rows, VS centre.
"""

import io
from pathlib import Path
from typing import NamedTuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from config import GAME_NAME
try:
    from data.classes import ICON_MAP as SUB_ROLE_ICONS
except ImportError:
    SUB_ROLE_ICONS = {}

# Canvas
W, H = 1400, 787

# Palette
BG          = (14,  13,  28)
GOLD        = (220, 175,  50)
GOLD_DIM    = (140, 110,  30)
T1_PILL     = (245, 185,  66)   # Gold  #F5B942
T1_DARK     = (160, 115,  20)
T2_PILL     = (124,  58, 237)   # Purple #7C3AED
T2_DARK     = ( 72,  28, 160)
WHITE       = (245, 245, 255)
GREY        = (160, 160, 180)
CHIP_BG     = (0,   0,   0,  90)

# Layout
BORDER      = 6
TITLE_H     = 70
FOOTER_H    = 40
INNER_PAD   = 28

ROW_COUNT   = 6
ROW_GAP     = 10
VS_W        = 120

USABLE_W    = W - BORDER * 2 - INNER_PAD * 2
PILL_W      = (USABLE_W - VS_W) // 2
ROW_AREA_Y  = TITLE_H + BORDER + INNER_PAD
ROW_AREA_H  = H - ROW_AREA_Y - FOOTER_H - BORDER - INNER_PAD
ROW_H       = (ROW_AREA_H - ROW_GAP * (ROW_COUNT - 1)) // ROW_COUNT

L_X         = BORDER + INNER_PAD
R_X         = W - BORDER - INNER_PAD - PILL_W
VS_X        = L_X + PILL_W

CIRCLE_D    = ROW_H - 6
CHIP_H      = 40
CHIP_R      = 8

ASSETS      = Path(__file__).parent.parent / "assets"
FONT_DIR    = ASSETS / "fonts"
ICONS_DIR   = Path(__file__).parent.parent / "data" / "icons"
ICON_SIZE   = CIRCLE_D - 8


# Icon cache
_icon_cache: dict[str, Image.Image | None] = {}

def _load_icon(sub_role: str) -> Image.Image | None:
    key = sub_role.upper()
    if key in _icon_cache:
        return _icon_cache[key]
    filename = SUB_ROLE_ICONS.get(key)
    if not filename:
        _icon_cache[key] = None
        return None
    path = ICONS_DIR / filename
    if not path.exists():
        _icon_cache[key] = None
        return None
    try:
        icon = Image.open(path).convert("RGBA")
        icon = icon.resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS)
        _icon_cache[key] = icon
        return icon
    except Exception:
        _icon_cache[key] = None
        return None


# Font helpers
def _font(name: str, size: int):
    path = FONT_DIR / name
    if path.exists():
        return ImageFont.truetype(str(path), size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


class Fonts(NamedTuple):
    title:  object
    team:   object
    role:   object
    name:   object
    vs:     object
    small:  object


def _get_fonts() -> Fonts:
    return Fonts(
        title = _font("black.ttf",        42),   # Lato Black — big esports title
        team  = _font("heavy.ttf",        20),   # Lato Heavy — team labels
        role  = _font("poppins_bold.ttf", 20), # Poppins Bold — role chip
        name  = _font("black.ttf",        34),   # Lato Black — player name
        vs    = _font("black.ttf",        88),   # Lato Black — VS
        small = _font("bold.ttf",         16),   # Lato Bold — footer
    )


def _cx(draw, cx, cy, text, font, fill):
    bb = font.getbbox(text)
    w, h = bb[2]-bb[0], bb[3]-bb[1]
    draw.text((cx - w/2, cy - h/2), text, font=font, fill=fill)


def _trunc(s: str, n: int = 16) -> str:
    return s if len(s) <= n else s[:n-1] + "..."


def _paste_circle(img: Image.Image, icon: Image.Image, cx: int, cy: int, d: int):
    """Paste icon centred at (cx,cy) with no black fringe using proper alpha compositing."""
    size = (d, d)
    x0, y0 = cx - d // 2, cy - d // 2
    icon_sq = icon.resize(size, Image.LANCZOS).convert("RGBA")
    # Build transparent RGBA layer and paste icon using its own alpha
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    layer.paste(icon_sq, (x0, y0), icon_sq)
    # Alpha-composite onto a snapshot of img, then write back
    base = img.convert("RGBA")
    composited = Image.alpha_composite(base, layer)
    img.paste(composited.convert("RGB"))


# Draw a single player pill
def _draw_pill(
    img: Image.Image, draw: ImageDraw.ImageDraw,
    x: int, y: int,
    slot: dict,
    is_left: bool,
    fonts: Fonts,
):
    pill_color = T1_PILL if is_left else T2_PILL
    r = ROW_H // 2

    # Shadow / glow
    shadow = Image.new("RGBA", (PILL_W + 20, ROW_H + 20), (0,0,0,0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((10,10, PILL_W+10, ROW_H+10), radius=r,
                          fill=(*pill_color, 60))
    shadow = shadow.filter(ImageFilter.GaussianBlur(8))
    img.paste(Image.new("RGB", shadow.size, BG), (x-10, y-10), shadow)

    # Pill body
    draw.rounded_rectangle((x, y, x+PILL_W, y+ROW_H), radius=r,
                            fill=pill_color)

    cy = y + ROW_H // 2
    icon = _load_icon(slot.get("sub_role", ""))

    if is_left:
        circle_cx = x + r
        if icon:
            _paste_circle(img, icon, circle_cx, cy, ICON_SIZE)
        else:
            _cx(draw, circle_cx, cy, slot.get("sub_role","")[:3], fonts.role, WHITE)

        chip_x = circle_cx + r + 10
        chip_w = max(88, len(slot["slot_role"]) * 13 + 24)
        draw.rounded_rectangle(
            (chip_x, cy-CHIP_H//2, chip_x+chip_w, cy+CHIP_H//2),
            radius=CHIP_R, fill=(0,0,0,120)
        )
        _cx(draw, chip_x + chip_w//2, cy, slot["slot_role"], fonts.role, WHITE)

        name_x = chip_x + chip_w + 12
        name_str_l = _trunc(slot["username"])
        n_bb_l = fonts.name.getbbox(name_str_l)
        n_h_l  = n_bb_l[3] - n_bb_l[1]
        draw.text((name_x, cy - n_h_l // 2), name_str_l, font=fonts.name, fill=WHITE)

    else:
        circle_cx = x + PILL_W - r
        if icon:
            _paste_circle(img, icon, circle_cx, cy, ICON_SIZE)
        else:
            _cx(draw, circle_cx, cy, slot.get("sub_role","")[:3], fonts.role, WHITE)

        chip_w = max(88, len(slot["slot_role"]) * 13 + 24)
        chip_x = circle_cx - r - 10 - chip_w
        draw.rounded_rectangle(
            (chip_x, cy-CHIP_H//2, chip_x+chip_w, cy+CHIP_H//2),
            radius=CHIP_R, fill=(0,0,0,120)
        )
        _cx(draw, chip_x + chip_w//2, cy, slot["slot_role"], fonts.role, WHITE)

        name_str = _trunc(slot["username"])
        n_bb = fonts.name.getbbox(name_str)
        n_w  = n_bb[2] - n_bb[0]
        n_h  = n_bb[3] - n_bb[1]
        name_x = chip_x - 12 - n_w
        draw.text((name_x, cy - n_h // 2), name_str, font=fonts.name, fill=WHITE)


# Public API
def generate_matchup_image(
    team1: list[dict],
    team2: list[dict],
    title: str = "G1",
    mode:  str = "Shuffle",
) -> bytes:
    fonts = _get_fonts()

    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img, "RGBA")

    # Background gradient
    for y in range(H):
        t = y/H
        r = int(14 + (22-14)*t)
        g = int(13 + (16-13)*t)
        b = int(28 + (40-28)*t)
        draw.line([(0,y),(W,y)], fill=(r,g,b))

    # Gold border frame
    draw.rectangle((0,0,W-1,H-1), outline=GOLD, width=BORDER)
    draw.rectangle((BORDER+2,BORDER+2,W-BORDER-3,H-BORDER-3),
                   outline=GOLD_DIM, width=1)

    # Title
    _cx(draw, W//2, TITLE_H//2 + BORDER, title.upper(), fonts.title, WHITE)

    # Team labels
    _cx(draw, L_X + PILL_W//2, ROW_AREA_Y - 16, "TEAM 1", fonts.team, T1_PILL)
    _cx(draw, R_X + PILL_W//2, ROW_AREA_Y - 16, "TEAM 2", fonts.team, T2_PILL)

    # Player rows
    for i, (s1, s2) in enumerate(zip(team1, team2)):
        ry = ROW_AREA_Y + i * (ROW_H + ROW_GAP)
        _draw_pill(img, draw, L_X, ry, s1, True,  fonts)
        _draw_pill(img, draw, R_X, ry, s2, False, fonts)

    # VS text
    vs_cx = VS_X + VS_W // 2
    vs_cy = ROW_AREA_Y + (ROW_COUNT * (ROW_H + ROW_GAP) - ROW_GAP) // 2

    glow = Image.new("RGBA", (160, 120), (0,0,0,0))
    gd   = ImageDraw.Draw(glow)
    gd.ellipse((0,0,160,120), fill=(*GOLD, 40))
    glow = glow.filter(ImageFilter.GaussianBlur(20))
    img.paste(Image.new("RGB",(160,120),BG),(vs_cx-80, vs_cy-60), glow)

    _cx(draw, vs_cx, vs_cy, "VS", fonts.vs, GOLD)

    # Footer
    footer_y = H - FOOTER_H
    draw.line([(BORDER+INNER_PAD, footer_y), (W-BORDER-INNER_PAD, footer_y)],
              fill=GOLD_DIM, width=1)
    _cx(draw, W//2, footer_y + FOOTER_H//2, GAME_NAME.upper(), fonts.small, GREY)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.read()
