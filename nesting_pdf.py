"""
Nesting PDF per plotter a rotolo: dispone tutte le pagine dei PDF su un
unico foglio largo quanto il rotolo, minimizzando la lunghezza consumata.
Le pagine possono essere ruotate di 90°.

Uso:
  python nesting_pdf.py <file.pdf | cartella> [...] --larghezza 137 [--spazio 0.5] [--copie N] [-o out.pdf]

Misure in cm. Richiede: pip install pymupdf
"""
import argparse, glob, os, random, sys
import pymupdf

PT_CM = 72 / 2.54
SEGNI = 0.0  # spazio extra attorno ai pezzi bianchi (il filetto sta sul bordo)


def sfondo_bianco(pg, soglia=0.9):
    """True se il bordo della pagina e' quasi tutto bianco."""
    pm = pg.get_pixmap(dpi=5)
    w, h = pm.width, pm.height
    px = [pm.pixel(x, y) for x in range(w) for y in (0, h - 1)] +          [pm.pixel(x, y) for y in range(h) for x in (0, w - 1)]
    return sum(min(c[:3]) > 240 for c in px) / len(px) >= soglia


def segni_margine(page, x0, y0, x1, y1):
    """Filetto sottile sul bordo del pezzo, per vedere il margine sul bianco (cm)."""
    s = page.new_shape()
    s.draw_rect(pymupdf.Rect(x0 * PT_CM, y0 * PT_CM, x1 * PT_CM, y1 * PT_CM))
    s.finish(color=(0, 0, 0), width=0.25)
    s.commit()


def raccogli(percorsi):
    files = []
    for p in percorsi:
        if os.path.isdir(p):
            files += sorted(glob.glob(os.path.join(p, "*.pdf")))
        else:
            files.append(p)
    return [f for f in files if "NESTING" not in os.path.basename(f).upper()]


def packing(items, W, gap, order):
    """MaxRects su striscia infinita, posizionamento bottom-left. Ritorna (lunghezza, piazzamenti)."""
    free = [(0.0, 0.0, W, 1e9)]
    placed = []
    for idx in order:
        p = 2 * items[idx]["pad"]
        w0, h0 = items[idx]["w"] + p + gap, items[idx]["h"] + p + gap
        best = None
        for (fx, fy, fw, fh) in free:
            for rot, (w, h) in ((False, (w0, h0)), (True, (h0, w0))):
                if w <= fw + 1e-6 and h <= fh + 1e-6:
                    key = (fy + h, fx)  # minimizza il bordo superiore, poi a sinistra
                    if best is None or key < best[0]:
                        best = (key, fx, fy, w, h, rot)
        if best is None:
            return None
        _, x, y, w, h, rot = best
        placed.append((idx, x, y, rot))
        # dividi i rettangoli liberi
        nf = []
        for (fx, fy, fw, fh) in free:
            if x >= fx + fw or x + w <= fx or y >= fy + fh or y + h <= fy:
                nf.append((fx, fy, fw, fh)); continue
            if x > fx: nf.append((fx, fy, x - fx, fh))
            if x + w < fx + fw: nf.append((x + w, fy, fx + fw - x - w, fh))
            if y > fy: nf.append((fx, fy, fw, y - fy))
            if y + h < fy + fh: nf.append((fx, y + h, fw, fy + fh - y - h))
        free = [a for i, a in enumerate(nf) if not any(
            i != j and a[0] >= b[0] - 1e-6 and a[1] >= b[1] - 1e-6 and
            a[0] + a[2] <= b[0] + b[2] + 1e-6 and a[1] + a[3] <= b[1] + b[3] + 1e-6 and
            (a != b or j < i) for j, b in enumerate(nf))]
    L = max(y + (items[i]["w"] if r else items[i]["h"]) + 2 * items[i]["pad"] + gap for i, x, y, r in placed)
    return L, placed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="+")
    ap.add_argument("--larghezza", type=float, required=True, help="larghezza utile rotolo (cm)")
    ap.add_argument("--spazio", type=float, default=0.5, help="spazio tra i pezzi (cm)")
    ap.add_argument("--margine", type=float, default=0.5,
                    help="bordo vuoto a destra e sinistra che il RIP taglia (cm)")
    ap.add_argument("--escludi", action="append", default=[],
                    help='pagina da saltare, es. "70x50 - produzione.pdf:1" (ripetibile)')
    ap.add_argument("--copie", type=int, default=1)
    ap.add_argument("--tentativi", type=int, default=3000)
    ap.add_argument("--no-segni", dest="segni", action="store_false",
                    help="non mettere il filetto di margine sui pezzi a sfondo bianco")
    ap.add_argument("-o", "--output")
    a = ap.parse_args()

    files = raccogli(a.input)
    items = []
    for f in files:
        doc = pymupdf.open(f)
        for pn, pg in enumerate(doc):
            if f"{os.path.basename(f)}:{pn+1}".lower() in [e.lower() for e in a.escludi]:
                continue
            r = pg.rect
            bianco = a.segni and sfondo_bianco(pg)
            pad = SEGNI if bianco else 0.0
            for _ in range(a.copie):
                items.append(dict(file=f, page=pn, w=r.width / PT_CM, h=r.height / PT_CM, pad=pad, bianco=bianco))
    W = a.larghezza - 2 * a.margine + a.spazio  # il gap a destra dell'ultimo pezzo non serve
    for it in items:
        if min(it["w"], it["h"]) + 2 * it["pad"] > a.larghezza - 2 * a.margine:
            sys.exit(f"Pezzo troppo grande: {it['file']} p.{it['page']+1}")

    n = len(items)
    base = [sorted(range(n), key=k, reverse=True) for k in (
        lambda i: items[i]["w"] * items[i]["h"],
        lambda i: max(items[i]["w"], items[i]["h"]),
        lambda i: min(items[i]["w"], items[i]["h"]),
        lambda i: items[i]["w"] + items[i]["h"])]
    best = None
    rnd = random.Random(1)
    for t in range(a.tentativi):
        order = base[t] if t < len(base) else rnd.sample(range(n), n)
        res = packing(items, W, a.spazio, order)
        if res and (best is None or res[0] < best[0]):
            best = res
    L, placed = best
    L -= a.spazio

    out = pymupdf.open()
    page = out.new_page(width=a.larghezza * PT_CM, height=L * PT_CM)
    srcs = {}
    area = 0
    for idx, x, y, rot in placed:
        it = items[idx]
        src = srcs.setdefault(it["file"], pymupdf.open(it["file"]))
        w, h = (it["h"], it["w"]) if rot else (it["w"], it["h"])
        x, y = x + it["pad"] + a.margine, y + it["pad"]
        rect = pymupdf.Rect(x * PT_CM, y * PT_CM, (x + w) * PT_CM, (y + h) * PT_CM)
        page.show_pdf_page(rect, src, it["page"], rotate=90 if rot else 0, keep_proportion=False)
        if it["bianco"]:
            segni_margine(page, x, y, x + w, y + h)
        area += it["w"] * it["h"]
        print(f"{os.path.basename(it['file'])} p.{it['page']+1} {it['w']:.0f}x{it['h']:.0f}"
              f" -> x={x:.1f} y={y:.1f}{' RUOTATO' if rot else ''}{' +MARGINE' if it['bianco'] else ''}")

    o = a.output or os.path.join(os.path.dirname(files[0]), f"NESTING_{a.larghezza:g}cm.pdf")
    out.save(o, deflate=True, garbage=3)
    print(f"\nRotolo {a.larghezza:g} cm  ->  lunghezza {L:.1f} cm  "
          f"| resa {100*area/(a.larghezza*L):.0f}%\nSalvato: {o}")
    if L > 508:
        print("ATTENZIONE: oltre 508 cm, alcuni RIP/Acrobat non gestiscono pagine così lunghe.")


if __name__ == "__main__":
    main()
