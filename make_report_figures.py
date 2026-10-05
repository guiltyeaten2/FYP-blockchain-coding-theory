"""
Builds docs/report_figures/ -- the curated subset for the written report.

    python3 make_report_figures.py

docs/figures/ holds all 19 figures the internal reports use. Most of those
earn their place in a document that already explains them in prose, but a
report has a figure budget and a different job: each figure has to carry one
claim on its own. This script selects the subset that does, renames them with
a leading number so they sort into reading order, and writes each one twice:

    .svg   vector, for LaTeX or anything that will be printed
    .png   300 dpi, for Word and Google Docs, which handle SVG badly

It also writes README.md into that folder, pairing each figure with the claim
it supports and the section it belongs in, so the folder is usable without
coming back to this file.

Nothing is re-measured. This reads the same committed JSON as make_figures.py.
"""
import json
import os
import shutil

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import make_figures as M

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "docs", "report_figures")

# Folders follow the order the report presents things: the coding benchmark
# first, then the network simulation. Methodology sits in its own folder
# because it is referenced from the method chapter, not the results.
FOLDERS = {
    "bench":  "01-benchmark",
    "net":    "02-network-sim",
    "method": "03-methodology",
}

# (order, source figure fn, data group, filename stem, folder, section, claim)
SELECTION = [
    # ---------------------------------------------------------- 01-benchmark
    (1, M.fig_success_curves, "bench", "fault-tolerance", "bench",
     "Results — fault tolerance",
     "Every scheme holds at 100% then falls off a cliff, so one threshold "
     "number fairly summarises each. The three lambda=2 rows land within a "
     "hundredth of each other (0.340, 0.341, 0.350) across a factor of four "
     "in block size."),
    (2, M.fig_bc_threshold_prediction, "bench", "bc-threshold-vs-theory",
     "bench", "Results — fault tolerance",
     "The block-circulant decoder's reach is set by lambda alone, and the "
     "measurements sit on the 1/(1+lambda) prediction at every point. This is "
     "the figure that shows theory and experiment agreeing."),
    (3, M.fig_tolerance_vs_guarantee, "bench", "tolerance-vs-guarantee",
     "bench", "Discussion — guarantees versus behaviour",
     "Measured tolerance against each code's own worst-case bound. 1D-RS sits "
     "on its bound because it is MDS; 2D-RS exceeds its own guarantee "
     "fourfold. Random erasure patterns are not adversarial ones."),
    (4, M.fig_decode_time, "bench", "decode-cost", "bench",
     "Results — computational cost",
     "Decode cost against erasure rate. 1D-RS is three to five times dearer "
     "than the dearest block-circulant row at every rate."),
    (5, M.fig_cost_per_erasure, "bench", "cost-per-erasure", "bench",
     "Discussion — why the costs differ",
     "The same data with the workload divided out. 1D-RS is flat, so its cost "
     "is linear in erasures; 2D-RS falls steeply, revealing a large fixed "
     "cost that amortises. This explains the shape of the previous figure."),
    (6, M.fig_encode_decode, "bench", "encode-vs-decode", "bench",
     "Discussion — asymmetry",
     "Encode is paid once by the proposer, decode by every reconstructing "
     "node. 1D-RS and the block-circulant family sit on opposite sides of "
     "that asymmetry, which the tolerance numbers alone do not show."),
    (7, M.fig_tolerance_vs_cost, "bench", "pareto-tolerance-vs-cost", "bench",
     "Discussion — the trade-off",
     "The synthesis figure: tolerance against the cost of achieving it, with "
     "the Pareto frontier. Only three of seven schemes are on it. If the "
     "report has one summary figure, this is it."),
    (8, M.fig_data_needed, "bench", "data-needed-per-blob", "bench",
     "Results — bandwidth",
     "Surviving data each scheme needs to rebuild one blob. 1D-RS is at the "
     "theoretical floor; every other scheme needs more."),

    # -------------------------------------------------------- 02-network-sim
    (1, M.fig_net_erasure, "netA", "erasure-vs-adversaries", "net",
     "Results — network layer",
     "Custody replication turns withholding into a much smaller erasure rate "
     "(roughly p^4), and all six schemes produce the same curve because this "
     "is a property of the network, not the code."),
    (2, M.fig_net_recovery, "netA", "recovery-vs-adversaries", "net",
     "Results — network layer",
     "Recovery against adversarial withholding. The schemes fail in the same "
     "order the coding benchmark predicted, through a completely different "
     "mechanism — the strongest cross-validation in the project."),
    (3, M.fig_net_gather_vs_decode, "netB", "gather-vs-decode", "net",
     "Discussion — the real bottleneck",
     "Gather takes about a second for every scheme; decode spans three orders "
     "of magnitude above it and misses the slot deadline. The bottleneck is "
     "arithmetic, not bandwidth."),
    (4, M.fig_net_peers, "netC", "scalability-peer-count", "net",
     "Results — scalability",
     "Realised erasure against network size, with the exact hypergeometric "
     "prediction computed rather than fitted. What protects a cell is the "
     "fraction of the network custodying it."),

    # ------------------------------------------------------- 03-methodology
    (1, M.fig_decoder_fix, "fix", "decoder-correctness-fix", "method",
     "Methodology — validation",
     "Before and after the decoder correctness fix: silent corruptions fell "
     "from 31 of 40 to zero. Justifies verifying bytes rather than trusting "
     "the decoder's own success flag."),
]

# Deliberately left out of the report set, and why -- so the omissions are a
# decision rather than an oversight.
OMITTED = {
    "fft_vs_vandermonde": "NTT path; belongs in an implementation appendix, "
                          "not the empirical results",
    "fft_profile": "same",
    "fft_node_width": "same",
    "fft_grs_premise": "same",
    "net_throughput": "largely restates figure 10 through a different "
                      "measure; include only if throughput is discussed",
    "rs_decode_vs_erasure_count": "1D vs 2D only; figure 4 covers it across "
                                  "all seven schemes",
}


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    data = {}
    for g, (src, _) in M.GROUPS.items():
        path = os.path.join(M.HERE, src)
        if os.path.exists(path):
            with open(path) as f:
                data[g] = json.load(f)

    rows = []
    for n, fn, group, stem, folder, section, claim in SELECTION:
        if group not in data:
            print(f"  SKIP {stem}: {M.GROUPS[group][0]} not found")
            continue
        sub = FOLDERS[folder]
        os.makedirs(os.path.join(OUT, sub), exist_ok=True)
        name = f"{n:02d}-{stem}"
        saved = {}

        def grab(fig, _ignored, _n=name, _s=sub, _saved=saved):
            for ext in ("svg", "png"):
                path = os.path.join(OUT, _s, f"{_n}.{ext}")
                kw = {"dpi": 300} if ext == "png" else {"metadata": {"Date": None}}
                fig.savefig(path, format=ext, bbox_inches="tight", **kw)
                _saved[ext] = path
            plt.close(fig)

        real, M._save = M._save, grab
        try:
            fn(data[group])
        finally:
            M._save = real
        kb = os.path.getsize(saved["png"]) / 1024
        print(f"  {sub}/{name}  (svg + png, {kb:.0f} KiB)")
        rows.append((sub, n, name, section, claim))

    # One README at the top, plus one inside each folder, so the folder is
    # usable on its own without climbing back up.
    byfolder = {}
    for sub, n, name, section, claim in rows:
        byfolder.setdefault(sub, []).append((n, name, section, claim))

    TITLES = {
        "01-benchmark": ("The coding benchmark",
                         "Seven schemes over the same blob, same erasure "
                         "positions, at matched storage cost. This is the "
                         "first results chapter."),
        "02-network-sim": ("The network simulation",
                           "The same schemes inside a simulated peer-to-peer "
                           "network, where the erasure pattern is an output "
                           "rather than an input. This follows the benchmark."),
        "03-methodology": ("Methodology and validation",
                           "Referenced from the method chapter rather than "
                           "the results."),
    }

    with open(os.path.join(OUT, "README.md"), "w") as f:
        f.write("# Figures for the written report\n\n")
        f.write("Folders follow the order the report presents things: the "
                "coding benchmark first, then the network simulation.\n\n")
        f.write("Each figure comes as `.svg` for LaTeX or print and `.png` at "
                "300 dpi for Word and Google Docs. Numbering restarts inside "
                "each folder.\n\n")
        f.write("Regenerate with `python3 make_report_figures.py`.\n\n")
        for sub in FOLDERS.values():
            if sub not in byfolder:
                continue
            title, blurb = TITLES[sub]
            f.write(f"## `{sub}/` — {title}\n\n{blurb}\n\n")
            for n, name, section, claim in byfolder[sub]:
                f.write(f"* **{name}** — {claim}\n")
            f.write("\n")
        f.write("## Deliberately not included\n\n")
        f.write("These exist in `docs/figures/` and were left out on "
                "purpose:\n\n")
        for k, why in OMITTED.items():
            f.write(f"* `{k}` — {why}\n")

    for sub, items in byfolder.items():
        title, blurb = TITLES[sub]
        with open(os.path.join(OUT, sub, "README.md"), "w") as f:
            f.write(f"# {title}\n\n{blurb}\n\n")
            for n, name, section, claim in items:
                f.write(f"## {name}\n\n*Goes in: {section}*\n\n{claim}\n\n")

    print(f"\n{len(rows)} figures across {len(byfolder)} folders in "
          f"docs/report_figures/")


if __name__ == "__main__":
    main()
