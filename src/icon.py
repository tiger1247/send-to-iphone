"""Draws the app icon (a phone with a down arrow) with Pillow."""
from PIL import Image, ImageDraw

BLUE = (10, 132, 255, 255)
WHITE = (255, 255, 255, 255)


def make_icon(size=256, badge=False):
    s = size * 4  # supersample for smooth edges
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([s * .06, s * .06, s * .94, s * .94], radius=s * .22, fill=BLUE)
    # phone outline
    pw, ph = s * .40, s * .66
    x0, y0 = (s - pw) / 2, (s - ph) / 2
    d.rounded_rectangle([x0, y0, x0 + pw, y0 + ph], radius=s * .07, outline=WHITE, width=int(s * .045))
    # arrow into the phone
    cx = s / 2
    d.rectangle([cx - s * .03, y0 + ph * .2, cx + s * .03, y0 + ph * .55], fill=WHITE)
    d.polygon([(cx - s * .11, y0 + ph * .5), (cx + s * .11, y0 + ph * .5), (cx, y0 + ph * .7)], fill=WHITE)
    if badge:  # green dot = iPhone connected
        r = s * .17
        d.ellipse([s - r * 2 - s * .02, s - r * 2 - s * .02, s - s * .02, s - s * .02],
                  fill=(48, 209, 88, 255), outline=WHITE, width=int(s * .03))
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "app.ico"
    make_icon(256).save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", out)
