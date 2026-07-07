"""Generate the app icons (studio.ico / editor.ico). Run once; requires Pillow."""
from PIL import Image, ImageDraw

SS = 4                      # supersample factor
S = 256 * SS               # working canvas
SIZES = [256, 128, 64, 48, 32, 16]

BG1 = (17, 22, 31, 255)     # dark tile
BG2 = (12, 17, 25, 255)
BORDER = (38, 50, 74, 255)
TEAL = (24, 180, 168, 255)
TEAL_LT = (46, 212, 197, 255)
TEAL_DK = (14, 143, 134, 255)
PAGE = (224, 237, 243, 255)
INK = (38, 50, 74, 255)


def tile():
    """Rounded dark square with a faint teal border + top sheen."""
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(46 * SS)
    m = int(14 * SS)
    box = [m, m, S - m, S - m]
    # vertical gradient body
    grad = Image.new("RGBA", (1, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / S
        gd.point((0, y), (int(BG1[0] * (1 - t) + BG2[0] * t),
                          int(BG1[1] * (1 - t) + BG2[1] * t),
                          int(BG1[2] * (1 - t) + BG2[2] * t), 255))
    grad = grad.resize((S, S))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=r, fill=255)
    img.paste(grad, (0, 0), mask)
    d.rounded_rectangle(box, radius=r, outline=BORDER, width=int(3 * SS))
    return img, d


def save(img, path):
    img = img.resize((256, 256), Image.LANCZOS)
    img.save(path, sizes=[(s, s) for s in SIZES])
    print("wrote", path)


def studio():
    img, d = tile()
    cx, cy = S // 2, int(S * 0.52)
    w = int(S * 0.30)      # iso half-width
    h = int(S * 0.17)      # iso half-height
    th = int(S * 0.20)     # cube body height
    top = [(cx, cy - h - th), (cx + w, cy - th), (cx, cy + h - th), (cx - w, cy - th)]
    left = [(cx - w, cy - th), (cx, cy + h - th), (cx, cy + h), (cx - w, cy)]
    right = [(cx + w, cy - th), (cx, cy + h - th), (cx, cy + h), (cx + w, cy)]
    ow = int(2.5 * SS)
    d.polygon(left, fill=TEAL_DK, outline=BG2, width=ow)
    d.polygon(right, fill=TEAL, outline=BG2, width=ow)
    d.polygon(top, fill=TEAL_LT, outline=BG2, width=ow)
    # a "band" line across the front faces to read as a package
    d.line([(cx - w, cy - int(th * 0.5)), (cx, cy + h - int(th * 0.5))], fill=BG2, width=ow)
    d.line([(cx + w, cy - int(th * 0.5)), (cx, cy + h - int(th * 0.5))], fill=BG2, width=ow)
    save(img, "studio.ico")


def editor():
    img, d = tile()
    # page (rounded rect with a folded corner)
    px0, py0, px1, py1 = int(S * 0.30), int(S * 0.26), int(S * 0.70), int(S * 0.78)
    fold = int(S * 0.12)
    pr = int(10 * SS)
    d.rounded_rectangle([px0, py0, px1, py1], radius=pr, fill=PAGE)
    # folded corner (top-right)
    d.polygon([(px1 - fold, py0), (px1, py0 + fold), (px1 - fold, py0 + fold)], fill=(190, 205, 214, 255))
    d.polygon([(px1 - fold, py0), (px1, py0 + fold), (px1, py0), ], fill=PAGE)
    # text lines
    lx0, lx1 = px0 + int(S * 0.06), px1 - int(S * 0.06)
    for i, yy in enumerate([0.40, 0.50, 0.60]):
        y = int(S * yy)
        x1 = lx1 if i != 2 else int((lx0 + lx1) / 2)
        d.line([(lx0, y), (x1, y)], fill=INK, width=int(4 * SS))
    # teal pencil across the lower-right
    import math
    ang = math.radians(-38)
    L = int(S * 0.34)
    bw = int(S * 0.052)
    bx, by = int(S * 0.40), int(S * 0.74)
    dx, dy = math.cos(ang), math.sin(ang)
    nx, ny = -dy, dx
    tip = (bx, by)
    base_c = (bx - dx * L, by - dy * L)
    # body quad
    p1 = (base_c[0] + nx * bw, base_c[1] + ny * bw)
    p2 = (base_c[0] - nx * bw, base_c[1] - ny * bw)
    neck = (bx - dx * bw * 2.2, by - dy * bw * 2.2)
    n1 = (neck[0] + nx * bw, neck[1] + ny * bw)
    n2 = (neck[0] - nx * bw, neck[1] - ny * bw)
    d.polygon([p1, p2, n2, n1], fill=TEAL)
    d.polygon([n1, n2, tip], fill=TEAL_LT)         # wood tip
    d.polygon([(tip[0] + (n1[0]-tip[0])*0.35, tip[1]+(n1[1]-tip[1])*0.35),
               (tip[0] + (n2[0]-tip[0])*0.35, tip[1]+(n2[1]-tip[1])*0.35), tip], fill=INK)  # graphite
    d.line([p1, p2], fill=TEAL_DK, width=int(2*SS))  # eraser end
    save(img, "editor.ico")


if __name__ == "__main__":
    studio()
    editor()
