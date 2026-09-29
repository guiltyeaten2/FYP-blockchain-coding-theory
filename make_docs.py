"""
Renders the Markdown reports in docs/ to PDF.

    python3 make_docs.py                        # every .md in docs/
    python3 make_docs.py benchmark_1D_2D_BC_report
    python3 make_docs.py --keep-html            # leave the intermediate HTML

Markdown -> styled HTML -> Chrome headless print-to-PDF. Chrome is used
rather than a Python PDF library because these reports embed SVG figures and
HTML <figure>/<figcaption> blocks, and a browser is the only thing here that
lays those out correctly.

Run make_figures.py first if the figures have changed -- this script embeds
whatever is currently in docs/figures/ and does not regenerate it.

THREE THINGS THAT BREAK THIS, ALL LEARNED THE HARD WAY:

  Relative image paths. The intermediate HTML is written INTO docs/, beside
  the figures, so that <img src="figures/x.svg"> resolves. Rendering from a
  temporary directory silently produces a PDF with every figure missing.

  Absolute file:// URL. Chrome rejects a relative path with ERR_INVALID_URL
  and still exits 0, leaving a stale or empty PDF behind.

  text-transform on table headers. Uppercasing a header containing a Greek
  letter renders omega and lambda as capital forms, so a table of code
  parameters ends up claiming values the report never measured. Headers are
  bold, never uppercased. For the same reason `pre` wraps rather than
  scrolls: an overflow-x scrollbar simply clips in print.
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys

import markdown

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(HERE, "docs")

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
    shutil.which("chromium-browser") or "",
]

CSS = """
@page { size: A4; margin: 18mm 16mm; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  font-family: "Charter", "Georgia", "Times New Roman", serif;
  font-size: 10.5pt; line-height: 1.5; color: #1a1a1a; max-width: 100%;
}
h1 { font-size: 20pt; margin: 0 0 4pt; line-height: 1.2; }
h2 { font-size: 14pt; margin: 20pt 0 6pt; border-bottom: 0.6pt solid #ccc;
     padding-bottom: 3pt; break-after: avoid; }
h3 { font-size: 11.5pt; margin: 14pt 0 4pt; break-after: avoid; }
p { margin: 0 0 7pt; }
code, pre { font-family: "SF Mono", "Menlo", "Consolas", monospace; }
code { font-size: 9pt; background: #f2f2f2; padding: 0.5pt 2.5pt;
       border-radius: 2pt; }
pre {
  background: #f7f7f7; border: 0.5pt solid #e0e0e0; border-radius: 3pt;
  padding: 7pt 9pt; font-size: 8.6pt; line-height: 1.42;
  /* wrap, never scroll: an overflow-x scrollbar clips in print */
  white-space: pre-wrap; word-wrap: break-word; break-inside: avoid;
}
pre code { background: none; padding: 0; font-size: inherit; }
table { border-collapse: collapse; width: 100%; margin: 9pt 0;
        font-size: 8.8pt; break-inside: avoid; }
th, td { border: 0.5pt solid #ccc; padding: 3.5pt 5pt; text-align: left;
         vertical-align: top; }
/* Bold, NOT uppercased -- uppercasing turns omega into Omega. */
th { background: #f0f0f0; font-weight: 600; text-transform: none; }
blockquote { margin: 8pt 0; padding: 4pt 0 4pt 11pt;
             border-left: 2pt solid #ccc; color: #444; }
figure { margin: 12pt 0; text-align: center; break-inside: avoid; }
figure img, figure svg { max-width: 100%; height: auto; }
figcaption { font-size: 8.4pt; color: #444; text-align: left;
             margin-top: 5pt; line-height: 1.45; }
ul, ol { margin: 0 0 7pt; padding-left: 17pt; }
li { margin-bottom: 2.5pt; }
a { color: #1a4f8a; text-decoration: none; }
hr { border: none; border-top: 0.5pt solid #ccc; margin: 14pt 0; }
"""

EXTENSIONS = ["tables", "fenced_code", "attr_list", "md_in_html", "sane_lists"]


def find_chrome():
    for c in CHROME_CANDIDATES:
        if c and os.path.exists(c):
            return c
    return None


def render(md_path, chrome, keep_html):
    stem = os.path.splitext(os.path.basename(md_path))[0]
    with open(md_path) as f:
        text = f.read()
    body = markdown.markdown(text, extensions=EXTENSIONS)
    html = (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{stem}</title><style>{CSS}</style></head>"
            f"<body>{body}</body></html>")

    # Written into docs/ so that <img src="figures/..."> resolves. This is
    # load-bearing; a temp directory gives a PDF with no figures in it.
    html_path = os.path.join(DOCS, f"{stem}.html")
    with open(html_path, "w") as f:
        f.write(html)

    pdf_path = os.path.join(DOCS, f"{stem}.pdf")
    before = os.path.getmtime(pdf_path) if os.path.exists(pdf_path) else 0
    cmd = [chrome, "--headless", "--disable-gpu", "--no-sandbox",
           "--no-pdf-header-footer", "--virtual-time-budget=12000",
           f"--print-to-pdf={pdf_path}",
           # Absolute file:// URL: a relative path is ERR_INVALID_URL and
           # Chrome still exits 0, leaving the previous PDF in place.
           f"file://{os.path.abspath(html_path)}"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if not keep_html:
        os.remove(html_path)

    if not os.path.exists(pdf_path) or os.path.getmtime(pdf_path) <= before:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        print(f"  FAILED {stem}.pdf  " + " | ".join(tail))
        return False
    kb = os.path.getsize(pdf_path) / 1024
    print(f"  {stem}.pdf  ({kb:.0f} KiB)")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*",
                    help="report stems to build (default: all .md in docs/)")
    ap.add_argument("--keep-html", action="store_true",
                    help="leave the intermediate HTML in docs/ for inspection")
    args = ap.parse_args()

    chrome = find_chrome()
    if not chrome:
        sys.exit("no Chrome or Chromium found -- tried:\n  "
                 + "\n  ".join(c for c in CHROME_CANDIDATES if c))

    if args.names:
        paths = [os.path.join(DOCS, f"{n.removesuffix('.md')}.md")
                 for n in args.names]
        missing = [p for p in paths if not os.path.exists(p)]
        if missing:
            sys.exit("no such report(s): "
                     + ", ".join(os.path.basename(m) for m in missing))
    else:
        paths = sorted(glob.glob(os.path.join(DOCS, "*.md")))

    print(f"chrome: {chrome}")
    ok = sum(render(p, chrome, args.keep_html) for p in paths)
    print(f"\n{ok}/{len(paths)} PDF(s) written to docs/")
    if ok != len(paths):
        sys.exit(1)


if __name__ == "__main__":
    main()
