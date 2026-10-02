#!/usr/bin/env python3
# ============================================================================
#  BIRTHDAY BOOK — image baker
#  ---------------------------------------------------------------------------
#  Put your photos in /scratch/input, list them in SPREADS below (with the crop
#  and the page each one goes on), run this file, and it writes
#  birthday-book.html with every photo embedded (base64) in the file itself.
#  The result is ONE self-contained file you can share — no server, no uploads,
#  the photos travel with the file.
#
#  For each photo you choose:
#     "file"  : the path to the image
#     "crop"  : the part of the photo to use.
#                 None ............ use the whole photo (centred, cover-fit)
#                 [x0,y0,x1,y1] ... pixels, e.g. [120, 80, 980, 720]
#                 [.1,.1,.9,.9] ... fractions of width/height (0..1)
#     "space" : where it sits in the book
#                 "both"  = one photo across BOTH pages (a full spread)
#                 "left"  = the left page of a spread
#                 "right" = the right page of a spread
#               (a "left" and the next "right" share one spread)
#     "title" : optional caption shown under the book
#
#  Example:
#     SPREADS = [
#       {"space":"both",  "file":"/scratch/input/cover.png", "crop":None, "title":"Cover"},
#       {"space":"left",  "file":"/scratch/input/a.png",     "crop":[0,0,900,700]},
#       {"space":"right", "file":"/scratch/input/b.png",     "crop":[.1,.1,.9,.9]},
#     ]
# ============================================================================

import base64, io, re, os, sys
from PIL import Image, ImageDraw, ImageFilter, ImageChops

# ---------------------------------------------------------------------------
#  CONFIG
# ---------------------------------------------------------------------------
# the app (gate + letter + button). Tries these in order:
BASE_CANDIDATES = ['/scratch/work/base_v5.html', '/scratch/input/birthday-book.html']
OUT_HTML  = 'birthday-book.html'                  # the file it writes
OUT_DIR   = '/scratch/output'                     # where the finished file is left
SONG      = '/scratch/input/happy_birthday.mp3'   # plays when the balloon pops

SPREADS = [
    # 1. the current spread
    {"space":"both", "file":"/scratch/input/Nostalgic_Birthday_Spotlight_for_Renuka.png",
     "crop":None, "title":"Happy Birthday Renuka"},
    # 2. next spread — two images, one on each page
    {"space":"left",  "file":"/scratch/input/Vibrant_Watercolour_Portrait_with_Splashes-2.png",
     "crop":None, "title":""},
    {"space":"right", "file":"/scratch/input/Painterly_Portrait_of_an_Indian_Woman-2.png",
     "crop":[0.06, 0.0, 0.94, 1.0], "title":""},     # zoomed to keep the subject + the "R.Renuka" signature
    # 3. the collage across both pages — left pale area cropped out, "Happy Birthday Renuka" text and head-at-top kept
    {"space":"both",  "file":"/scratch/input/Happy_Birthday_Renuka_Collage_1.png",
     "crop":[205, 126, 1080, 512], "title":""},
    # 4. next spread — two images, one on each page
    {"space":"left",  "file":"/scratch/input/Sunlit_Garden_Bench_Portrait-3.png",
     "crop":None, "title":""},
    {"space":"right", "file":"/scratch/input/Vibrant_Guitarist_Beneath_the_Canopy-2.png",
     "crop":None, "title":""},
    # 5. the "HAPPY BIRTHDAY" portrait across both pages — the HAPPY letters kept at the top edge
    {"space":"both",  "file":"/scratch/input/Golden_Maharashtrian_Portrait_Elegance.png",
     "crop":[0, 26, 1672, 764], "title":""},
]

# ---------------------------------------------------------------------------
#  the book's own geometry (2200 x 1550 canvas)
# ---------------------------------------------------------------------------
BOOK_W, BOOK_H = 2200, 1550
ART   = (115, 340, 2085, 1210)    # one photo across both pages
LEFT  = (115, 340, 1100, 1210)    # left page
RIGHT = (1100, 340, 2085, 1210)   # right page
CORNER = 52                       # rounded paper corner (book px)
FOLD   = (40, 30, 18)             # the spine shadow colour


def parse_crop(crop, w, h):
    """None -> whole image; [..] -> pixels or fractions."""
    if not crop:
        return None
    x0, y0, x1, y1 = crop
    if max(x0, y0, x1, y1) <= 1.0001:          # fractions
        x0, y0, x1, y1 = x0 * w, y0 * h, x1 * w, y1 * h
    x0, y0, x1, y1 = (int(round(v)) for v in (x0, y0, x1, y1))
    return (max(0, x0), max(0, y0), min(w, x1), min(h, y1))


def cover_fit(im, w, h):
    """Scale+crop the image so it fills w x h, centred (like the app)."""
    sw, sh = im.size
    s = max(w / sw, h / sh)
    nw, nh = max(1, int(round(sw * s))), max(1, int(round(sh * s)))
    im = im.resize((nw, nh), Image.LANCZOS)
    x = (nw - w) // 2
    y = (nh - h) // 2
    return im.crop((x, y, x + w, y + h))


def rounded_mask(w, h, r, feather=3):
    m = Image.new('L', (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    if feather:
        m = m.filter(ImageFilter.GaussianBlur(feather))
    return m


def sheet_mask(rects):
    m = Image.new('L', (BOOK_W, BOOK_H), 0)
    d = ImageDraw.Draw(m)
    for (x0, y0, x1, y1) in rects:
        d.rounded_rectangle([x0, y0, x1, y1], radius=CORNER, fill=255)
    return m


def build_spread(items):
    """items: list of (image, rect) -> one 2200x1550 spread."""
    rects = [r for _, r in items]
    canvas = Image.new('RGBA', (BOOK_W, BOOK_H), (0, 0, 0, 0))

    # 1. soft shadow under the sheet (offset down, halo only)
    sh = Image.new('L', (BOOK_W, BOOK_H), 0)
    d = ImageDraw.Draw(sh)
    for (x0, y0, x1, y1) in rects:
        d.rounded_rectangle([x0, y0 + 12, x1, y1 + 12], radius=CORNER, fill=int(0.17 * 255))
    sh = sh.filter(ImageFilter.GaussianBlur(16))
    sh = ImageChops.subtract(sh, sheet_mask(rects))
    shadow = Image.new('RGBA', (BOOK_W, BOOK_H), (58, 44, 26, 0))
    shadow.putalpha(sh)
    canvas.alpha_composite(shadow)

    # 2. the photos, each with the soft rounded paper edge, clipped to its page
    for im, (x0, y0, x1, y1) in items:
        w, h = x1 - x0, y1 - y0
        photo = cover_fit(im, w, h)
        mask = rounded_mask(w, h, CORNER)
        canvas.paste(photo, (x0, y0), mask)

    # 3. the fold, clipped to the sheet so it can't spill onto the margins
    fold = Image.new('L', (BOOK_W, BOOK_H), 0)
    d = ImageDraw.Draw(fold)
    spine, half = BOOK_W // 2, 170
    for x in range(spine - half, spine + half):
        t = 1 - abs(x - spine) / half
        d.line([(x, 0), (x, BOOK_H)], fill=int(80 * t * t))
    fold = ImageChops.multiply(fold, sheet_mask(rects))
    fl = Image.new('RGBA', (BOOK_W, BOOK_H), FOLD + (0,))
    fl.putalpha(fold)
    canvas.alpha_composite(fl)

    return canvas


def load_image(path):
    im = Image.open(path)
    if im.mode not in ('RGB', 'RGBA'):
        im = im.convert('RGB')
    return im.convert('RGB')


def build_pages(specs):
    """Turn the spec list into the app's PAGES entries (base64 data URIs)."""
    pages, pending = [], None
    for sp in specs:
        path, crop, space = sp['file'], sp.get('crop'), sp['space'].lower()
        title = sp.get('title', '')
        im = load_image(path)
        w, h = im.size
        c = parse_crop(crop, w, h)
        if c:
            im = im.crop(c)
        if space == 'both':
            canvas = build_spread([(im, ART)])
            pages.append((canvas, title)); pending = None
        elif space == 'left':
            if pending:                       # an unpaired left -> flush it alone
                canvas = build_spread(pending['items'])
                pages.append((canvas, pending['title']))
            pending = {'items': [(im, LEFT)], 'title': title}
        elif space == 'right':
            if pending:
                pending['items'].append((im, RIGHT))
                canvas = build_spread(pending['items'])
                pages.append((canvas, pending['title'] or title))
                pending = None
            else:
                canvas = build_spread([(im, RIGHT)])
                pages.append((canvas, title))
        else:
            raise ValueError('space must be both/left/right, got %r' % space)
    if pending:
        canvas = build_spread(pending['items'])
        pages.append((canvas, pending['title']))
    return pages


def data_uri(canvas):
    buf = io.BytesIO()
    canvas.save(buf, 'WEBP', quality=86, method=6)
    return 'data:image/webp;base64,' + base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------------------
#  THE SURPRISE — a big balloon that greets you when you come back from the
#  book; tap it and it pops, revealing the HAPPY BIRTHDAY RENO message.
# ---------------------------------------------------------------------------
SURPRISE_CSS = (
    '#bdaySurprise{position:fixed;inset:0;z-index:1400;display:none;align-items:center;justify-content:center;'
    'background:radial-gradient(120% 90% at 50% 38%,rgba(250,246,238,.97),rgba(236,231,220,.99));'
    '-webkit-backdrop-filter:blur(3px);backdrop-filter:blur(3px);}'
    'body.surprise #bdaySurprise{display:flex}'
    '.surprise-inner{position:relative;display:flex;flex-direction:column;align-items:center;gap:16px;text-align:center;padding:24px}'
    '.surprise-hint{font-family:var(--font);font-size:12px;letter-spacing:.2em;text-transform:uppercase;color:rgba(43,39,33,.5);margin:0}'
    '.balloon{position:relative;width:min(48vw,230px);aspect-ratio:1/1.22;cursor:pointer;'
    'border-radius:50% 50% 47% 47%/44% 44% 56% 56%;'
    'background:radial-gradient(circle at 34% 26%,#ff9aa8,#e83b52 56%,#ad0f28);'
    'box-shadow:0 30px 44px rgba(120,20,40,.28),inset -16px -22px 36px rgba(120,10,30,.34);'
    'animation:bal-float 3.4s ease-in-out infinite;transition:transform .12s ease;-webkit-tap-highlight-color:transparent}'
    '.balloon:hover{transform:scale(1.03)}'
    '.balloon:before{content:"";position:absolute;left:19%;top:13%;width:28%;height:22%;border-radius:50%;'
    'background:radial-gradient(circle,rgba(255,255,255,.85),rgba(255,255,255,0) 72%)}'
    '.balloon:after{content:"";position:absolute;left:50%;bottom:-7px;transform:translateX(-50%);'
    'width:18px;height:14px;background:#ad0f28;border-radius:40% 40% 50% 50%}'
    '.balloon .string{position:absolute;left:50%;top:100%;transform:translateX(-50%);width:2px;height:14vh;'
    'background:linear-gradient(180deg,rgba(60,50,40,.45),rgba(60,50,40,0))}'
    '.balloon.pop{animation:bal-pop .42s ease forwards}'
    '@keyframes bal-float{0%,100%{transform:translateY(0) rotate(-1.5deg)}50%{transform:translateY(-14px) rotate(1.5deg)}}'
    '@keyframes bal-pop{0%{transform:scale(1)}55%{transform:scale(1.35)}100%{transform:scale(1.75);opacity:0}}'
    '.surprise-msg{display:none;flex-direction:column;align-items:center;gap:12px}'
    '#bdaySurprise.revealed .surprise-msg{display:flex;animation:msg-in .6s cubic-bezier(.2,.7,.2,1) both}'
    '#bdaySurprise.revealed .balloon,#bdaySurprise.revealed .surprise-hint{display:none}'
    '@keyframes msg-in{from{opacity:0;transform:translateY(16px) scale(.96)}to{opacity:1;transform:none}}'
    '.surprise-emoji{font-size:clamp(34px,9vw,58px);letter-spacing:.08em;line-height:1}'
    '.surprise-emoji span{display:inline-block;animation:bal-bob 2.6s ease-in-out infinite}'
    '.surprise-emoji span:nth-child(2){animation-delay:.35s}'
    '.surprise-emoji span:nth-child(3){animation-delay:.7s}'
    '@keyframes bal-bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-12px)}}'
    '.surprise-msg h2{font-family:var(--display);font-weight:400;font-size:clamp(30px,8vw,76px);line-height:1.06;'
    'margin:0;color:var(--ink);letter-spacing:.02em}'
    '.surprise-lines{display:flex;flex-direction:column;gap:.3em;margin:10px 0 0}'
    '.surprise-lines span{font-family:var(--display);font-weight:400;font-size:clamp(19px,4.6vw,40px);'
    'line-height:1.16;color:rgba(43,39,33,.9);opacity:0;transform:translateY(14px);'
    'transition:opacity .8s ease,transform .8s ease}'
    '#bdaySurprise.lines .surprise-lines span{opacity:1;transform:none}'
    '#bdaySurprise.lines .surprise-lines span:nth-child(2){transition-delay:.5s}'
    '#bdaySurprise.lines .surprise-lines span:nth-child(3){transition-delay:1s}'
    '#bdaySurprise .surprise-close{position:fixed;top:12px;right:14px;display:none;font-family:var(--font);'
    'font-size:12.5px;letter-spacing:.14em;text-transform:uppercase;padding:10px 16px;border-radius:999px;cursor:pointer;'
    'border:1px solid rgba(43,39,33,.4);background:rgba(250,246,238,.94);color:#2b2721}'
    '#bdaySurprise.revealed .surprise-close{display:inline-block}'
    '@media (prefers-reduced-motion:reduce){.balloon,.surprise-emoji span{animation:none}}'
)

def surprise_html(song_uri):
    return (
        '<div id="bdaySurprise" aria-hidden="true">'
        '<button class="surprise-close" id="bdaySurpriseClose" aria-label="Close">\u2715 Close</button>'
        '<audio id="bdaySong" preload="auto" src="' + song_uri + '"></audio>'
        '<div class="surprise-inner">'
        '<p class="surprise-hint">Tap the balloon</p>'
        '<div class="balloon" id="bdayBalloon" role="button" tabindex="0" aria-label="Pop the balloon">'
        '<span class="string"></span></div>'
        '<div class="surprise-msg">'
        '<div class="surprise-emoji" aria-hidden="true"><span>\U0001F388</span><span>\U0001F382</span><span>\U0001F388</span></div>'
        '<h2>HAPPY BIRTHDAY RENUKA</h2>'
        '<p class="surprise-lines">'
        '<span>BE HAPPY</span><span>MAKE EVERYONE HAPPY</span><span>KEEP THAT SMILE ON THE FACE</span>'
        '</p>'
        '</div></div></div>'
    )

SURPRISE_JS = (
    '(function(){'
    'var s=document.getElementById("bdaySurprise"),b=document.getElementById("bdayBalloon"),'
    'c=document.getElementById("bdaySurpriseClose"),song=document.getElementById("bdaySong");'
    'if(!s||!b)return;var wasOpen=false,popped=false;'
    'function check(){var open=document.body.classList.contains("beauty-open");'
    'if(open){wasOpen=true;}else if(wasOpen){wasOpen=false;show();}}'
    'new MutationObserver(check).observe(document.body,{attributes:true,attributeFilter:["class"]});'
    'function show(){s.setAttribute("aria-hidden","false");document.body.classList.add("surprise");}'
    'function pop(){if(popped)return;popped=true;b.classList.add("pop");'
    'try{if(song){song.currentTime=0;var p=song.play();if(p&&p.catch)p.catch(function(){});}}catch(e){}'
    'setTimeout(function(){s.classList.add("revealed");'
    'setTimeout(function(){s.classList.add("lines");},2000);},420);}'
    'function close(){document.body.classList.remove("surprise");s.setAttribute("aria-hidden","true");'
    'try{if(song){song.pause();song.currentTime=0;}}catch(e){}'
    'setTimeout(function(){s.classList.remove("revealed");s.classList.remove("lines");'
    'b.classList.remove("pop");popped=false;},300);}'
    'b.addEventListener("click",pop);'
    'b.addEventListener("keydown",function(e){if(e.key==="Enter"||e.key===" ")pop();});'
    'if(c)c.addEventListener("click",close);'
    '})();'
)


def main():
    if not SPREADS:
        print('No images listed in SPREADS yet — add them, then run again.')
        return 1
    base = next((p for p in BASE_CANDIDATES if os.path.exists(p)), None)
    if not base:
        print('Base file not found. Looked in:', BASE_CANDIDATES); return 1

    print('building %d spread(s)...' % len(build_pages(SPREADS)))
    pages = build_pages(SPREADS)
    entries = []
    for canvas, title in pages:
        entries.append("  {file:'%s', title:%s, place:''}" %
                       (data_uri(canvas), repr(title)))
    new_pages = 'const PAGES=[\n' + ',\n'.join(entries) + '\n];'

    html = open(base, encoding='utf-8').read()
    # drop the zoom toolbar ("100%") and make the book fill the window in the beauty view
    html = html.replace('</head>',
        '<style>'
        '.sb-tools{display:none !important}'
        'body.beauty-open{overflow:hidden}'
        'body.beauty-open .hero{padding:0;overflow:hidden}'
        'body.beauty-open .sb-wrap{width:100vw;max-width:100vw}'
        'body.beauty-open .sb-3d{max-width:min(117.6vw,158.4vh)}'
        'body.beauty-open .sb-hint{display:none}'
        '.letter-card{width:100%;max-width:680px}'
        '#pbAddMore,#pbReset{display:none !important}'
        + SURPRISE_CSS +
        '</style>\n</head>', 1)
    html, n = re.subn(r"const PAGES=\[.*?\];", lambda m: new_pages, html, count=1, flags=re.S)
    assert n == 1, 'PAGES array not found in the base file'
    html = html.replace('const LAND=6;', 'const LAND=0;')

    # the surprise balloon + message, and its wiring
    song_uri = ''
    if os.path.exists(SONG):
        song_uri = 'data:audio/mpeg;base64,' + base64.b64encode(open(SONG, 'rb').read()).decode()
    else:
        print('warning: song not found at', SONG)
    html = html.replace('</body>',
                        surprise_html(song_uri) + '<script>' + SURPRISE_JS + '</script>\n</body>', 1)

    out = os.path.join(OUT_DIR, OUT_HTML)
    os.makedirs(OUT_DIR, exist_ok=True)
    open(out, 'w', encoding='utf-8').write(html)
    print('wrote %s  (%d pages, %.2f MB)' % (out, len(pages), len(html) / 1048576))
    return 0


if __name__ == '__main__':
    sys.exit(main())
