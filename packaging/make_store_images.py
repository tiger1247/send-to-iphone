"""Builds the 1920x1080 Microsoft Store screenshots from the raw captures in store-assets/src."""
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "store-assets", "src")
OUT = os.path.join(HERE, "store-assets")
W, H = 1920, 1080
FONTS = r"C:\Windows\Fonts"


def font(bold, size):
    return ImageFont.truetype(os.path.join(FONTS, "segoeuib.ttf" if bold else "segoeui.ttf"), size)


def background():
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    top, bottom = (10, 92, 220), (88, 70, 215)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3)))
    # soft glow
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse([1000, -300, 2300, 900], fill=90)
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    img.paste(Image.new("RGB", (W, H), (120, 190, 255)), (0, 0), glow)
    return img


def rounded(im, r):
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, im.size[0] - 1, im.size[1] - 1], radius=r, fill=255)
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    out.paste(im.convert("RGBA"), (0, 0), mask)
    return out


def shadow_paste(canvas, im, xy, blur=40, offset=(0, 24), opacity=110):
    sh = Image.new("RGBA", (im.size[0] + blur * 4, im.size[1] + blur * 4), (0, 0, 0, 0))
    alpha = im.split()[-1].point(lambda a: opacity if a else 0)
    sh.paste((0, 0, 0, 255), (blur * 2, blur * 2), alpha)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(sh, (xy[0] - blur * 2 + offset[0], xy[1] - blur * 2 + offset[1]))
    canvas.alpha_composite(im, xy)


def window(scale_w):
    win = Image.open(os.path.join(SRC, "desktop.png")).convert("RGB")
    win = win.crop((2, 2, win.size[0] - 2, win.size[1] - 2))
    h = int(win.size[1] * scale_w / win.size[0])
    return rounded(win.resize((scale_w, h), Image.LANCZOS), 14)


def phone(name, screen_h):
    shot = Image.open(os.path.join(SRC, name)).convert("RGB")
    sw = int(shot.size[0] * screen_h / shot.size[1])
    status_h = int(screen_h * 0.065)  # room for the camera notch, like a real status bar
    page = shot.resize((sw, screen_h), Image.LANCZOS)
    screen = Image.new("RGB", (sw, screen_h), shot.getpixel((3, 3)))
    screen.paste(page.crop((0, 0, sw, screen_h - status_h)), (0, status_h))
    screen = rounded(screen, 44)
    bezel = 16
    body = Image.new("RGBA", (sw + bezel * 2, screen_h + bezel * 2), (0, 0, 0, 0))
    ImageDraw.Draw(body).rounded_rectangle([0, 0, body.size[0] - 1, body.size[1] - 1], radius=60, fill=(18, 18, 22, 255))
    body.alpha_composite(screen, (bezel, bezel))
    # dynamic island
    iw = int(sw * 0.3)
    ImageDraw.Draw(body).rounded_rectangle([(body.size[0] - iw) // 2, bezel + 14, (body.size[0] + iw) // 2, bezel + 44],
                                           radius=15, fill=(18, 18, 22, 255))
    return body


def text_block(canvas, title, sub, bullets=(), x=110, y=260):
    d = ImageDraw.Draw(canvas)
    d.text((x, y - 70), "PhoneDrop", font=font(True, 34), fill=(200, 225, 255))
    ty = y
    for line in title.split("\n"):
        d.text((x, ty), line, font=font(True, 76), fill="white")
        ty += 92
    ty += 18
    for line in sub.split("\n"):
        d.text((x, ty), line, font=font(False, 36), fill=(225, 235, 255))
        ty += 50
    ty += 30
    for b in bullets:
        d.ellipse([x, ty + 16, x + 14, ty + 30], fill=(140, 220, 160))
        d.text((x + 32, ty), b, font=font(False, 32), fill="white")
        ty += 54


def save(canvas, name):
    canvas.convert("RGB").save(os.path.join(OUT, name), optimize=True)
    print("wrote", name)


def main():
    # 1 — hero
    c = background().convert("RGBA")
    text_block(c, "Send files from\nyour PC to iPhone", "Nothing to install on the iPhone.\nScan the QR code once — done.",
               ["Drag & drop or right-click → Share", "Full-quality photos and videos", "Over your own Wi-Fi"])
    win = window(900)
    shadow_paste(c, win, (900, 190))
    ph = phone("phone-files.jpg", 700)
    shadow_paste(c, ph, (1500, 300))
    save(c, "1-send-to-iphone.png")

    # 2 — iPhone to PC
    c = background().convert("RGBA")
    text_block(c, "Photos from iPhone\nto PC in seconds", "Pick photos, videos or files on your\niPhone — they land in Downloads.",
               ["Big videos with progress bars", "No cable, no cloud, no account", "Shared clipboard both ways"])
    ph = phone("phone-upload.jpg", 860)
    shadow_paste(c, ph, (1250, 95))
    save(c, "2-iphone-to-pc.png")

    # 3 — privacy
    c = background().convert("RGBA")
    text_block(c, "Private by design", "Files go straight over your Wi-Fi.\nThey never touch the internet.",
               ["Only your paired iPhone can connect", "No ads, no tracking, no sign-up", "Starts with Windows, lives in the tray"],
               y=300)
    win = window(1000)
    shadow_paste(c, win, (840, 160))
    save(c, "3-private.png")


if __name__ == "__main__":
    main()
