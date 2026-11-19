# nesting-pdf

Lays out the pages of one or more PDFs on a single sheet as wide as the plotter roll, using as little material as possible (pages can be rotated by 90°).

- Automatic hairline outline on white-background pieces (`--no-outline` to disable)
- Empty strip on left and right for RIP cropping (`--margin`, default 0.5 cm)
- Skip individual pages (`--exclude "file.pdf:N"`, repeatable)

```bash
pip install pymupdf
python nesting_pdf.py "folder or file.pdf" --width 137 [--gap 0.5] [--copies N] [-o out.pdf]
```

All measurements in cm. Default output is `NESTING_<width>cm.pdf` in the folder of the first PDF.

## License

MIT, see [LICENSE](LICENSE).
