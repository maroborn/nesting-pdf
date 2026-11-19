# nesting-pdf

Dispone le pagine di uno o più PDF su un unico foglio largo quanto il rotolo del plotter, consumando meno materiale possibile (le pagine possono essere ruotate di 90°).

- Filetto di margine automatico sui pezzi a sfondo bianco (`--no-segni` per disattivarlo)
- Bordo vuoto a destra e a sinistra per il taglio del RIP (`--margine`, default 0,5 cm)
- Esclusione di singole pagine (`--escludi "file.pdf:N"`)

```bash
pip install pymupdf
python nesting_pdf.py "cartella o file.pdf" --larghezza 137 [--spazio 0.5] [--copie N] [-o out.pdf]
```
Misure in cm. L'output predefinito è `NESTING_<larghezza>cm.pdf` nella cartella del primo PDF.
