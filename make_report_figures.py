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

# (order, source figure fn, data group, filename stem, section, the claim it carries)
SELECTION = [
    (1, M.fig_success_curves, "bench", "fault-tolerance",
     "Results — fault tolerance",
     "Every scheme holds at 100% then falls off a cliff, so one threshold "
     "number fairly summarises each. The three lambda=2 rows land within a "
     "hundredth of each other (0.340, 0.341, 0.350) across a factor of four "
     "in block size."),
    (2, M.fig_bc_threshold_prediction, "bench", "bc-threshold-vs-theory",
     "Results — fault tolerance",
     "The block-circulant decoder's reach is set by lambda alone, and the "
     "measurements sit on the 1/(1+lambda) prediction at every point. This is "
     "the figure that shows theory and experiment agreeing."),
    (3, M.fig_tolerance_vs_guarantee, "bench", "tolerance-vs-guarantee",
     "Discussion — guarantees versus behaviour",
     "Measured tolerance against each code's own worst-case bound. 1D-RS sits "
     "on its bound because it is MDS; 2D-RS exceeds its own guarantee "
     "fourfold. Random erasure patterns are not adversarial ones."),
    (4, M.fig_decode_time, "bench", "decode-cost",
     "Results — computational cost",
     "Decode cost against erasure rate. 1D-RS is three to five times dearer "
     "than the dearest block-circulant row at every rate."),
    (5, M.fig_cost_per_erasure, "bench", "cost-per-erasure",
     "Discussion — why the costs differ",
     "The same data with the workload divided out. 1D-RS is flat, so its cost "
     "is linear in erasures; 2D-RS falls steeply, revealing a large fixed "
     "cost that amortises. This explains the shape of the previous figure."),
    (6, M.fig_encode_decode, "bench", "encode-vs-decode",
     "Discussion — asymmetry",
     "Encode is paid once by the proposer, decode by every reconstructing "
     "node. 1D-RS and the block-circulant family sit on opposite sides of "
     "that asymmetry, which the tolerance numbers alone do not show."),
    (7, M.fig_tolerance_vs_cost, "bench", "pareto-tolerance-vs-cost",
     "Discussion — the trade-off",
     "The synthesis figure: tolerance against the cost of achieving it, with "
     "the Pareto frontier. Only three of seven schemes are on it. If the "
     "report has one summary figure, this is it."),
    (8, M.fig_data_needed, "bench", "data-needed-per-blob",
     "Results — bandwidth",
     "Surviving data each scheme needs to rebuild one blob. 1D-RS is at the "
     "theoretical floor; every other scheme needs more."),
    (9, M.fig_net_erasure, "netA", "network-erasure-vs-adversaries",
     "Results — network layer",
     "Custody replication turns withholding into a much smaller erasure rate "
     "(roughly p^4), and all six schemes produce the same curve because this "
     "is a property of the network, not the code."),
    (10, M.fig_net_recovery, "netA", "network-recovery",
     "Results — network layer",
     "Recovery against adversarial withholding. The schemes fail in the same "
     "order the coding benchmark predicted, through a completely different "
     "mechanism — the strongest cross-validation in the project."),
    (11, M.fig_net_gather_vs_decode, "netB", "gather-vs-decode",
     "Discussion — the real bottleneck",
     "Gather takes about a second for every scheme; decode spans three orders "
     "of magnitude above it and misses the slot deadline. The bottleneck is "
     "arithmetic, not bandwidth."),
    (12, M.fig_net_peers, "netC", "scalability-peer-count",
     "Results — scalability",
     "Realised erasure against network size, with the exact hypergeometric "
     "prediction computed rather than fitted. What protects a cell is the "
     "fraction of the network custodying it."),
    (13, M.fig_decoder_fix, "fix", "decoder-correctness-fix",
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
    for n, fn, group, stem, section, claim in SELECTION:
        if group not in data:
            print(f"  SKIP {stem}: {M.GROUPS[group][0]} not found")
            continue
        name = f"{n:02d}-{stem}"
        saved = {}

        def grab(fig, _ignored, _name=name, _saved=saved):
            for ext, kw in (("svg", {}), ("png", {"dpi": 300})):
                p = os.path.join(OUT, f"{_name}.{ext}")
                fig.savefig(p, format=ext, bbox_inches="tight",
                            **({} if ext == "png" else {"metadata": {"Date": None}}),
                            **kw)
                _saved[ext] = p
            plt.close(fig)

        real, M._save = M._save, grab
        try:
            fn(data[group])
        finally:
            M._save = real
        kb = os.path.getsize(saved["png"]) / 1024
        print(f"  {name}.svg + .png ({kb:.0f} KiB)")
        rows.append((n, name, section, claim))

    with open(os.path.join(OUT, "README.md"), "w") as f:
        f.write("# Figures for the written report\n\n")
        f.write("Each figure in two formats: `.svg` for LaTeX or print, "
                "`.png` at 300 dpi for Word and Google Docs.\n\n")
        f.write("Regenerate with `python3 make_report_figures.py`. "
                "Numbers are reading order, not importance — though if you "
                "only have room for one, use 07.\n\n")
        cur = None
        for n, name, section, claim in rows:
            if section != cur:
                f.write(f"\n## {section}\n\n")
                cur = section
            f.write(f"**{n:02d}. {name}**\n\n{claim}\n\n")
        f.write("\n## Deliberately not included\n\n")
        f.write("These exist in `docs/figures/` and were left out on "
                "purpose:\n\n")
        for k, why in OMITTED.items():
            f.write(f"* `{k}` — {why}\n")
    print(f"\n{len(rows)} figures + README.md in docs/report_figures/")


if __name__ == "__main__":
    main()
