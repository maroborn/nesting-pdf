"""
PDF nesting for roll plotters: lays out every page of the given PDFs on a
single sheet as wide as the roll, minimizing the length of material used.
Pages may be rotated by 90 degrees.

Usage:
  python nesting_pdf.py <file.pdf | folder> [...] --width 137 [--gap 0.5] [--copies N] [-o out.pdf]

All measurements in cm. Requires: pip install pymupdf
"""
import argparse, glob, os, random, sys
import pymupdf

PT_CM = 72 / 2.54


def white_background(pg, threshold=0.9):
    """True if the page border is almost entirely white."""
    pm = pg.get_pixmap(dpi=5)
    w, h = pm.width, pm.height
    px = [pm.pixel(x, y) for x in range(w) for y in (0, h - 1)] + \
         [pm.pixel(x, y) for y in range(h) for x in (0, w - 1)]
    return sum(min(c[:3]) > 240 for c in px) / len(px) >= threshold


def margin_outline(page, x0, y0, x1, y1):
    """Thin hairline on the piece edge, so the trim line is visible on white (cm)."""
    s = page.new_shape()
    s.draw_rect(pymupdf.Rect(x0 * PT_CM, y0 * PT_CM, x1 * PT_CM, y1 * PT_CM))
    s.finish(color=(0, 0, 0), width=0.25)
    s.commit()


def collect(paths):
    files = []
    for p in paths:
        if os.path.isdir(p):
            files += sorted(glob.glob(os.path.join(p, "*.pdf")))
        else:
            files.append(p)
    return [f for f in files if "NESTING" not in os.path.basename(f).upper()]


def pack(items, W, gap, order):
    """MaxRects on an infinite strip, bottom-left placement. Returns (length, placements)."""
    free = [(0.0, 0.0, W, 1e9)]
    placed = []
    for idx in order:
        w0, h0 = items[idx]["w"] + gap, items[idx]["h"] + gap
        best = None
        for (fx, fy, fw, fh) in free:
            for rot, (w, h) in ((False, (w0, h0)), (True, (h0, w0))):
                if w <= fw + 1e-6 and h <= fh + 1e-6:
                    key = (fy + h, fx)  # lowest top edge first, then leftmost
                    if best is None or key < best[0]:
                        best = (key, fx, fy, w, h, rot)
        if best is None:
            return None
        _, x, y, w, h, rot = best
        placed.append((idx, x, y, rot))
        # split the free rectangles
        nf = []
        for (fx, fy, fw, fh) in free:
            if x >= fx + fw or x + w <= fx or y >= fy + fh or y + h <= fy:
                nf.append((fx, fy, fw, fh)); continue
            if x > fx: nf.append((fx, fy, x - fx, fh))
            if x + w < fx + fw: nf.append((x + w, fy, fx + fw - x - w, fh))
            if y > fy: nf.append((fx, fy, fw, y - fy))
            if y + h < fy + fh: nf.append((fx, y + h, fw, fy + fh - y - h))
        # drop free rectangles contained in another one
        free = [a for i, a in enumerate(nf) if not any(
            i != j and a[0] >= b[0] - 1e-6 and a[1] >= b[1] - 1e-6 and
            a[0] + a[2] <= b[0] + b[2] + 1e-6 and a[1] + a[3] <= b[1] + b[3] + 1e-6 and
            (a != b or j < i) for j, b in enumerate(nf))]
    L = max(y + (items[i]["w"] if r else items[i]["h"]) + gap for i, x, y, r in placed)
    return L, placed


def main():
    ap = argparse.ArgumentParser(description="Nest PDF pages on a roll to save material.")
    ap.add_argument("input", nargs="+", help="PDF files and/or folders")
    ap.add_argument("--width", type=float, required=True, help="usable roll width (cm)")
    ap.add_argument("--gap", type=float, default=0.5, help="space between pieces (cm)")
    ap.add_argument("--margin", type=float, default=0.5,
                    help="empty strip on left and right that the RIP crops (cm)")
    ap.add_argument("--exclude", action="append", default=[],
                    help='page to skip, e.g. "poster.pdf:1" (repeatable)')
    ap.add_argument("--copies", type=int, default=1, help="copies of every page")
    ap.add_argument("--tries", type=int, default=3000, help="number of orderings to try")
    ap.add_argument("--no-outline", dest="outline", action="store_false",
                    help="don't draw the margin outline on white-background pieces")
    ap.add_argument("-o", "--output")
    a = ap.parse_args()

    excluded = {e.lower() for e in a.exclude}
    files = collect(a.input)
    items = []
    for f in files:
        doc = pymupdf.open(f)
        for pn, pg in enumerate(doc):
            if f"{os.path.basename(f)}:{pn+1}".lower() in excluded:
                continue
            r = pg.rect
            white = a.outline and white_background(pg)
            for _ in range(a.copies):
                items.append(dict(file=f, page=pn, w=r.width / PT_CM, h=r.height / PT_CM, white=white))
    if not items:
        sys.exit("No pages to nest.")

    usable = a.width - 2 * a.margin
    for it in items:
        if min(it["w"], it["h"]) > usable:
            sys.exit(f"Piece too large: {it['file']} p.{it['page']+1}")
    W = usable + a.gap  # no gap needed after the rightmost piece

    n = len(items)
    base = [sorted(range(n), key=k, reverse=True) for k in (
        lambda i: items[i]["w"] * items[i]["h"],
        lambda i: max(items[i]["w"], items[i]["h"]),
        lambda i: min(items[i]["w"], items[i]["h"]),
        lambda i: items[i]["w"] + items[i]["h"])]
    best = None
    rnd = random.Random(1)
    for t in range(a.tries):
        order = base[t] if t < len(base) else rnd.sample(range(n), n)
        res = pack(items, W, a.gap, order)
        if res and (best is None or res[0] < best[0]):
            best = res
    L, placed = best
    L -= a.gap

    out = pymupdf.open()
    page = out.new_page(width=a.width * PT_CM, height=L * PT_CM)
    srcs = {}
    area = 0
    for idx, x, y, rot in placed:
        it = items[idx]
        src = srcs.setdefault(it["file"], pymupdf.open(it["file"]))
        w, h = (it["h"], it["w"]) if rot else (it["w"], it["h"])
        x += a.margin
        rect = pymupdf.Rect(x * PT_CM, y * PT_CM, (x + w) * PT_CM, (y + h) * PT_CM)
        page.show_pdf_page(rect, src, it["page"], rotate=90 if rot else 0, keep_proportion=False)
        if it["white"]:
            margin_outline(page, x, y, x + w, y + h)
        area += it["w"] * it["h"]
        print(f"{os.path.basename(it['file'])} p.{it['page']+1} {it['w']:.0f}x{it['h']:.0f}"
              f" -> x={x:.1f} y={y:.1f}{' ROTATED' if rot else ''}{' +OUTLINE' if it['white'] else ''}")

    o = a.output or os.path.join(os.path.dirname(files[0]), f"NESTING_{a.width:g}cm.pdf")
    out.save(o, deflate=True, garbage=3)
    print(f"\nRoll {a.width:g} cm  ->  length {L:.1f} cm  "
          f"| yield {100*area/(a.width*L):.0f}%\nSaved: {o}")
    if L > 508:
        print("WARNING: over 508 cm, some RIPs/Acrobat can't handle pages this long.")


if __name__ == "__main__":
    main()
