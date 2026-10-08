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

# Report figures are for an IEEE-format document: no in-figure titles, no
# methods note under the artwork. Both are harvested into caption copy
# instead -- see CAPTIONS.md, written alongside the figures.
M.IEEE = True

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
# Each entry: (order, figure fn, data group, filename stem, folder, section,
# {question, data, reading, shows, caveat}). The dict is what the catalogue
# renders; a one-line claim was not enough to tell a reader what they are
# looking at or where it came from.
SELECTION = [
    # ---------------------------------------------------------- 01-benchmark
    (1, M.fig_success_curves, "bench", "fault-tolerance", "bench",
     "Results — fault tolerance", dict(
      question="How much of the codeword can each scheme lose and still "
               "rebuild the blob exactly?",
      data="The erasure sweep: 520 trials over one real EIP-4844 blob, 7 "
           "schemes x 18 erasure rates from 2% to 55%, fixed seed 20260827. "
           "benchmark_results.json.",
      reading="Top: fraction of trials recovered against erasure rate, one "
              "line per scheme, markers drawn only where a curve is partway "
              "down. Bottom: one row per scheme, the bar spanning the last "
              "rate where every trial recovered to the first where none did, "
              "with the 50% threshold ticked on it.",
      shows="Every scheme holds at 100% then collapses within a few percent, "
            "which is what makes a single threshold a fair summary. The "
            "three lambda=2 rows land at 0.340, 0.341 and 0.350 despite mu "
            "ranging 2 to 8 and omega 512 to 2048 - a factor of four in "
            "block size moving the threshold by nothing.",
      caveat="Erasures are drawn i.i.d., so these are upper bounds on "
             "performance against an adversary choosing the worst pattern.")),

    (2, M.fig_threshold_bands, "bench", "fault-tolerance-compact", "bench",
     "Results — fault tolerance (space-saving alternative to 01)", dict(
      question="Where does each scheme fall over, and how close together are "
               "those points?",
      data="The same erasure sweep as figure 01: 520 trials, 7 schemes, 18 "
           "rates. benchmark_results.json.",
      reading="Horizontal bars, one per scheme, sorted by threshold. Bar "
              "length is the 50% success threshold; the whisker spans the "
              "last rate at which every trial recovered to the first at "
              "which none did. The whisker is a measured range, not a "
              "confidence interval.",
      shows="The three lambda=2 rows cluster at 0.340, 0.341 and 0.350 "
            "across a factor of four in block size. The bar width also shows "
            "what a bare threshold hides: lambda=4 collapses over a much "
            "wider range of erasure rates than the lambda=2 rows do.",
      caveat="A standalone, single-column alternative to figure 01. Use one "
             "or the other, not both: they are the same data. This one "
             "carries the comparison and is readable without its caption; "
             "figure 01 adds the shape of each transition, which matters "
             "only if the prose leans on it.")),

    (3, M.fig_bc_threshold_prediction, "bench", "bc-threshold-vs-theory",
     "bench", "Results — fault tolerance", dict(
      question="Does the block-circulant decoder behave as the source paper "
               "predicts?",
      data="Same sweep. Thresholds derived from the success curves; the "
           "prediction is the local code's stopping rate from Sasidharan, "
           "Viterbo & Feist (ePrint 2026/708).",
      reading="Bars are measured thresholds, one per parameterisation, "
              "sorted by lambda. Red rules are the predicted stopping rate "
              "S0 = rho/n0 = 1/(1+lambda).",
      shows="Reach is set by lambda alone. Predicted 0.333/0.250/0.200 for "
            "lambda = 2/3/4 against measured 0.34/0.28/0.21. Theory and "
            "experiment agree at every point, and mu and omega do not enter.",
      caveat=None)),

    (4, M.fig_tolerance_vs_guarantee, "bench", "tolerance-vs-guarantee",
     "bench", "Discussion — guarantees versus behaviour", dict(
      question="How does what each code actually tolerated compare with what "
               "its minimum distance guarantees?",
      data="Same sweep for the measured bars; guarantees computed from each "
           "code's d_min, and the rate bound from 1 - R.",
      reading="Blue is the measured 50% threshold, grey the worst-case "
              "guarantee from minimum distance, dashed red the rate bound "
              "1-R that no code of that rate can beat.",
      shows="1D-RS sits on its bound (0.505 against 0.500), which is what "
            "being MDS means and a useful check that the harness is sound. "
            "2D-RS reaches 0.397 against a guarantee of 0.098 - four times "
            "its own bound.",
      caveat="Not a contradiction. A minimum-distance guarantee holds "
             "against every pattern including the adversarial worst case; "
             "these trials draw patterns at random.")),

    (5, M.fig_decode_time, "bench", "decode-cost", "bench",
     "Results — computational cost", dict(
      question="What does each scheme cost to decode, and how does that grow "
               "with damage?",
      data="Same sweep. Mean over the trials that actually recovered; failed "
           "trials are excluded because a scheme above its threshold rejects "
           "the pattern on a budget check in under a millisecond, which is "
           "not a decode time.",
      reading="Log vertical axis in seconds, erasure rate horizontal, curves "
              "named at their right-hand ends.",
      shows="1D-RS is the most expensive at every rate, three to five times "
            "the dearest block-circulant row, because it divides one "
            "8192-length polynomial while the others divide short ones. "
            "Against 2D-RS the picture is mixed: below about 8% every BC row "
            "is cheaper, above it only the two smallest stay below.",
      caveat="Single-threaded Python over galois. Relative comparisons hold; "
             "absolute seconds would not survive an optimised build.")),

    (6, M.fig_cost_per_erasure, "bench", "cost-per-erasure", "bench",
     "Discussion — why the costs differ", dict(
      question="Is one scheme dearer because it does more work per repair, "
               "or because it carries a fixed overhead?",
      data="The same decode times divided by the number of symbols actually "
           "erased in that trial.",
      reading="Milliseconds per erased symbol, log axis. A flat line means "
              "cost is linear in the number of erasures; a falling line "
              "means a fixed cost is being amortised over more repairs.",
      shows="1D-RS is flat at 10-13 ms per erasure - one long division's "
            "worth of work each. The BC rows sit at 1-3.5 ms and rise "
            "gently. 2D-RS falls steeply from 8 ms to 1 ms, revealing a "
            "large fixed cost, which is exactly why it looks expensive at 2% "
            "erasure and cheap at 30%.",
      caveat=None)),

    (7, M.fig_encode_decode, "bench", "encode-vs-decode", "bench",
     "Discussion — asymmetry", dict(
      question="Encoding and decoding are not paid by the same party. How do "
               "the schemes differ on each?",
      data="Encode time measured once per scheme on the shared blob; decode "
           "at the highest rate every scheme still recovers.",
      reading="Paired bars per scheme, log axis in seconds.",
      shows="The two families sit on opposite sides of the asymmetry. 1D-RS "
            "encodes in 0.23 s then costs 20 s to decode; BC omega2048 "
            "lambda2 spends 15.7 s encoding in order to decode in 5.5 s.",
      caveat="A blob is encoded once by the proposer and decoded by every "
             "node reconstructing it, so an expensive encode amortises "
             "across the network and an expensive decode does not. For DAS "
             "the second shape is the useful one - an argument for "
             "block-circulant the tolerance numbers alone do not make.")),

    (8, M.fig_tolerance_vs_cost, "bench", "pareto-tolerance-vs-cost", "bench",
     "Discussion — the trade-off", dict(
      question="Which schemes are actually worth considering once tolerance "
               "and cost are weighed together?",
      data="Thresholds and decode times from the same sweep, at the highest "
           "rate every scheme reached.",
      reading="One point per scheme: tolerance horizontal, decode cost "
              "vertical on a log axis. Down and to the right is better. The "
              "dashed line is the Pareto frontier - schemes not beaten on "
              "both counts at once.",
      shows="Only three of seven are on the frontier. BC omega512 lambda2 is "
            "the cheapest thing still surviving a third of the codeword; "
            "2D-RS buys about five more points of tolerance for roughly "
            "double the decode; 1D-RS buys the maximum and pays an order of "
            "magnitude. BC omega1024 lambda4 is dominated on both axes by "
            "omega512 lambda2, so the tolerance it gives up buys nothing.",
      caveat="If the report has one summary figure, this is it.")),

    (9, M.fig_data_needed, "bench", "data-needed-per-blob", "bench",
     "Results — bandwidth", dict(
      question="How much surviving data must a node obtain to rebuild one "
               "blob?",
      data="Derived from each scheme's measured threshold as "
           "n(1-threshold)/k, expressed as a multiple of one blob.",
      reading="Bars per scheme against a dashed line at 1.0, the theoretical "
              "floor - nothing rebuilds 124 KiB from less than 124 KiB.",
      shows="1D-RS needs essentially the floor at 0.99x. Everything else "
            "needs 1.24x to 1.58x. A scheme tolerating a lower erasure rate "
            "at the same storage cost necessarily needs more.",
      caveat="Computed from code parameters. Network figure 04 measures the "
             "same quantity independently and agrees on the ordering.")),

    # -------------------------------------------------------- 02-network-sim
    (1, M.fig_net_erasure, "netA", "erasure-vs-adversaries", "net",
     "Results — network layer: fault tolerance", dict(
      question="When peers withhold data, what erasure rate does the code "
               "actually end up facing?",
      data="SimPy simulation, 64 peers, custody replication 4, one blob per "
           "slot at 50 Mbps, 4 s deadline, 30 trials per point, withholding "
           "swept 0 to 80%. docs/runA.json.",
      reading="Realised erasure against the fraction of peers refusing to "
              "serve, with the p^4 prediction dashed. All six schemes are "
              "drawn; they coincide.",
      shows="A cell is lost only if all four of its custodians withhold, so "
            "the erasure the code sees is roughly the fourth power of the "
            "bad-peer fraction: 50% of the network withholding yields about "
            "5.6% erasure. Every scheme gives the identical curve, because "
            "this is a property of the network and custody, not the code.",
      caveat="Deflating for the coding schemes: replication absorbs most "
             "peer failure before the erasure code is asked to do anything.")),

    (2, M.fig_net_recovery, "netA", "recovery-vs-adversaries", "net",
     "Results — network layer: fault tolerance", dict(
      question="Do the schemes fail in the same order when losses come from "
               "peer behaviour rather than an injected erasure rate?",
      data="Same run. No erasure rate is injected here - losses are whatever "
           "failed to arrive before the 4 s deadline.",
      reading="Fraction of 30 trials that rebuilt the blob byte-exactly, "
              "against withholding.",
      shows="They fail in exactly the order the coding benchmark predicted, "
            "and at the withholding rates that produce their measured "
            "thresholds. BC omega1024 lambda4 breaks first (8/30 at 70% "
            "withholding, which yields 0.233 erasure against its 0.210 "
            "threshold); 1D-RS is still at 30/30 when 80% of peers refuse.",
      caveat="This is the project's strongest evidence: two independent "
             "methods agreeing is far better than either alone.")),

    (3, M.fig_net_latency, "netA", "latency-gather-time", "net",
     "Results — network layer: latency", dict(
      question="Does withholding cost the victim anything beyond the data "
               "itself?",
      data="Same run. Gather time is network time only, excluding decode.",
      reading="Seconds to collect the cells, against withholding, with the "
              "4 s sampling deadline marked. A curve reaching 4.00 has run "
              "out of time.",
      shows="Yes - it costs time. A peer that never answers cannot be routed "
            "around for free: the client burns its request timeout before "
            "falling back to another custodian. Gather climbs from 0.14 s to "
            "3.22 s for 1D-RS across the sweep. The scheme needing the most "
            "cells hits the deadline first, omega1024 lambda4 at 50% "
            "withholding against 1D-RS at 80%.",
      caveat="Covers the brief's 'packet propagation latency'. Invisible in "
             "any figure measured only at zero adversaries.")),

    (4, M.fig_net_bandwidth, "netB", "bandwidth-fetched", "net",
     "Results — network layer: bandwidth", dict(
      question="How much data does a node actually pull over the wire, as "
               "opposed to how much the code theoretically needs?",
      data="SimPy, 64 peers, replication 4, six blobs per slot at 25 Mbps - "
           "the bandwidth-pressure configuration. 30 trials per point. "
           "docs/runB.json.",
      reading="MiB fetched per slot against withholding, with a dashed line "
              "at the actual payload (six blobs = 0.73 MiB). Includes the "
              "over-request margin and anything re-requested after a "
              "timeout.",
      shows="1D-RS pulls least at 1.04 MiB and BC omega1024 lambda4 most at "
            "1.54 MiB - the same ordering benchmark figure 08 computes from "
            "code parameters, arrived at by completely independent means.",
      caveat="Read the fall at high withholding carefully: that is cells "
             "that never arrived, not a saving.")),

    (5, M.fig_net_throughput, "netB", "throughput-blobs-per-slot", "net",
     "Results — network layer: throughput", dict(
      question="How many blobs can a node actually rebuild within one slot?",
      data="Same six-blob run. Throughput implied by the measured time - "
           "blobs attempted, scaled by recovery rate and by whether the "
           "total fits the slot - not an independently measured rate.",
      reading="Blobs reconstructed per slot out of six, against withholding, "
              "with a dashed line at six.",
      shows="The ordering inverts the tolerance ordering. 1D-RS tolerates "
            "the most erasure of any scheme and reconstructs the fewest "
            "blobs, about 0.2 of the six, because one 8192-length polynomial "
            "division costs roughly 59 s per blob. The three cheapest BC "
            "rows keep up with all six until 20% withholding.",
      caveat="Covers the brief's 'block processing throughput'.")),

    (6, M.fig_net_time_budget, "netB", "time-budget-vs-slot", "net",
     "Discussion — can any of this keep up?", dict(
      question="Does the whole job - fetch plus rebuild - fit inside an "
               "Ethereum slot?",
      data="Same six-blob run. Gather plus decode summed per slot.",
      reading="Log seconds against withholding, with the 4 s sampling "
              "deadline and the 12 s slot both marked. Anything above the "
              "12 s line cannot keep up with the chain.",
      shows="At zero adversaries only BC omega1024 lambda3 (6.4 s) and "
            "lambda4 (1.3 s) finish inside a slot. Past about 20% "
            "withholding nothing does. 1D-RS is not close at any setting - "
            "354 s, roughly thirty slots of work for one slot of data.",
      caveat="The figure that reframes the comparison: erasure tolerance is "
             "not the binding constraint, decode throughput is.")),

    (7, M.fig_net_gather_vs_decode, "netB", "gather-vs-decode", "net",
     "Discussion — the real bottleneck", dict(
      question="Of the time a node spends, how much is network and how much "
               "is arithmetic?",
      data="Same six-blob run, at zero adversaries so neither side is "
           "inflated by timeouts.",
      reading="Gather and decode as separate bars per scheme on a log axis - "
              "separate rather than stacked, because stacking on a log axis "
              "would misrepresent the sum. The slot deadline is marked.",
      shows="Every scheme gathers in about one second. Decode spans three "
            "orders of magnitude above that, from effectively zero to 354 s. "
            "At every setting tried, arithmetic rather than bandwidth or "
            "latency decides the outcome.",
      caveat="Bandwidth was the constraint this project expected to find "
             "binding. It is not close.")),

    (8, M.fig_net_peers, "netC", "scalability-peer-count", "net",
     "Results — network layer: scalability", dict(
      question="What happens to data availability as the network grows?",
      data="SimPy peer sweep, 8 to 256 peers, replication fixed at 4, one "
           "blob at 50 Mbps, 30 trials per point, at 30% and 60% "
           "withholding. docs/runC.json.",
      reading="Realised erasure against peer count on a log-2 axis. Open "
              "markers are the exact hypergeometric probability that all "
              "four custodians of a cell are adversarial, C(A,4)/C(n,4), "
              "computed from the model rather than fitted. Dotted lines are "
              "the p^4 independent-sampling limits.",
      shows="Growing the network makes things slightly worse, up to a limit. "
            "Custodians are drawn without replacement, so in a small network "
            "it is combinatorially hard for all four to be adversarial - "
            "with 8 peers only 5 are bad. As the network grows that "
            "constraint relaxes and loss climbs toward p^4 = 0.130. "
            "Measurement sits on the computed prediction throughout.",
      caveat="The lesson for scalability claims: what protects a cell is the "
             "fraction of the network custodying it, so peer count cannot be "
             "varied without saying what replication does too.")),

    # ------------------------------------------------------- 03-methodology
    (1, M.fig_decoder_fix, "fix", "decoder-correctness-fix", "method",
     "Methodology — validation", dict(
      question="Why does this project verify recovered bytes rather than "
               "trusting the decoder's own success flag?",
      data="A historical run at omega=rho=lambda=2, mu=2048 - a "
           "parameterisation the main sweep does not cover - with the same "
           "40 trials (ten each at 5%, 15%, 25% and 45% erasure) put through "
           "the decoder before and after a correctness fix. "
           "decoder_fix_results.json.",
      reading="Outcome counts for the same 40 trials, before the fix in pale "
              "and after in solid. Three outcomes: correct recovery, silent "
              "corruption, honest failure.",
      shows="Before the fix the decoder claimed success on all 40 trials and "
            "was wrong on 31 of them; it never once reported a failure. "
            "After, silent corruption is zero and correct recoveries rose "
            "from 9 to 16 - the old decoder had been poisoning positions "
            "with fabricated zeros that blocked later rounds from resolving "
            "them.",
      caveat="Had the harness trusted the decoder's 'remaining' flag it "
             "would have reported 100% success at every erasure rate. The "
             "strongest validation argument the project has.")),

]

# Deliberately left out of the report set, and why -- so the omissions are a
# decision rather than an oversight.
OMITTED = {
    "fft_vs_vandermonde": "NTT path; belongs in an implementation appendix, "
                          "not the empirical results",
    "fft_profile": "same",
    "fft_node_width": "same",
    "fft_grs_premise": "same",
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
    for n, fn, group, stem, folder, section, meta in SELECTION:
        if group not in data:
            print(f"  SKIP {stem}: {M.GROUPS[group][0]} not found")
            continue
        sub = FOLDERS[folder]
        os.makedirs(os.path.join(OUT, sub), exist_ok=True)
        name = f"{n:02d}-{stem}"
        saved = {}

        def grab(fig, fig_name, _n=name, _s=sub, _saved=saved):
            # _save is replaced here, so the IEEE harvest has to happen in
            # this wrapper rather than in make_figures._save.
            if M.IEEE:
                M._harvest_and_strip(fig, fig_name)
                fig.tight_layout()
            for ext in ("pdf", "svg", "png"):
                path = os.path.join(OUT, _s, f"{_n}.{ext}")
                kw = ({"dpi": 300} if ext == "png"
                      else {"metadata": {"Date": None}} if ext == "svg"
                      else {})
                fig.savefig(path, format=ext, bbox_inches="tight", **kw)
                _saved[ext] = path
            plt.close(fig)

        before = set(M.CAPTION_TEXT)
        real, M._save = M._save, grab
        try:
            fn(data[group])
        finally:
            M._save = real
        new_keys = set(M.CAPTION_TEXT) - before
        meta["_harvested"] = (M.CAPTION_TEXT[new_keys.pop()]
                              if new_keys else {})
        kb = os.path.getsize(saved["png"]) / 1024
        print(f"  {sub}/{name}  (svg + png, {kb:.0f} KiB)")
        rows.append((sub, n, name, section, meta))

    # One README at the top, plus one inside each folder, so the folder is
    # usable on its own without climbing back up.
    byfolder = {}
    for sub, n, name, section, meta in rows:
        byfolder.setdefault(sub, []).append((n, name, section, meta))

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
            for n, name, section, m in byfolder[sub]:
                f.write(f"* **{name}** — {m['shows']}\n")
            f.write("\n")
        f.write("## Deliberately not included\n\n")
        f.write("These exist in `docs/figures/` and were left out on "
                "purpose:\n\n")
        for k, why in OMITTED.items():
            f.write(f"* `{k}` — {why}\n")

    # A visual catalogue: every figure with the claim it carries, in one
    # document you can page through. Generated here rather than written by
    # hand so it cannot drift out of step with SELECTION.
    cat = os.path.join(HERE, "docs", "figure_catalogue.md")
    with open(cat, "w") as f:
        f.write("# Figure catalogue\n\n")
        f.write("Every figure in `docs/report_figures/`, with what it asks, "
                "where the data comes from, how to read it and what it "
                "shows. Folders follow the order the report presents "
                "things.\n\n")
        f.write("Generated by `make_report_figures.py` from the same list "
                "that writes the figures, so the two cannot disagree. Each "
                "figure also exists as a 300 dpi PNG beside the SVG.\n\n")
        n_tot = sum(len(v) for v in byfolder.values())
        f.write(f"**{n_tot} figures** — "
                + ", ".join(f"{len(v)} in `{k}`" for k, v in byfolder.items())
                + ".\n\n---\n")
        for sub in FOLDERS.values():
            if sub not in byfolder:
                continue
            title, blurb = TITLES[sub]
            f.write(f"\n## {title}\n\n*`{sub}/` — {blurb}*\n")
            for n, name, section, m in byfolder[sub]:
                pretty = name.split("-", 1)[1].replace("-", " ")
                f.write(f"\n### {n:02d}. {pretty}\n\n")
                f.write(f'<figure>\n<img src="report_figures/{sub}/{name}.svg" '
                        f'alt="{m["shows"][:120]}">\n</figure>\n\n')
                f.write(f"**Goes in:** {section}\n\n")
                f.write(f"**The question.** {m['question']}\n\n")
                f.write(f"**Where the data comes from.** {m['data']}\n\n")
                f.write(f"**How to read it.** {m['reading']}\n\n")
                f.write(f"**What it shows.** {m['shows']}\n\n")
                if m.get("caveat"):
                    f.write(f"**Worth noting.** {m['caveat']}\n\n")
                f.write(f"<small>`{sub}/{name}.svg` and `.png` "
                        f"(300 dpi)</small>\n")
    print(f"  docs/figure_catalogue.md  ({n_tot} figures)")

    # Caption copy. The titles and methods notes stripped from the artwork
    # have to land somewhere, and in an IEEE document that somewhere is the
    # caption. Written as LaTeX \caption{} bodies, ready to paste.
    cap = os.path.join(OUT, "CAPTIONS.md")
    with open(cap, "w") as f:
        f.write("# Caption copy\n\n")
        f.write("IEEE figures carry no in-figure title: the caption "
                "describes the figure, and a title duplicates it. These "
                "figures are generated with titles and methods notes "
                "suppressed, and the text harvested here instead.\n\n")
        f.write("Each entry gives a short caption (the title, as a noun "
                "phrase) and a full caption (adds how to read it and the "
                "measurement conditions). IEEE style puts the figure number "
                "and caption *below* the figure.\n\n---\n")
        for sub in FOLDERS.values():
            if sub not in byfolder:
                continue
            f.write(f"\n## `{sub}/`\n")
            for n, name, section, m in byfolder[sub]:
                h = m.get("_harvested") or {}
                short = (h.get("title") or "").replace("\n", " ").strip()
                if not short:        # no title to harvest; fall back to the
                    short = m["shows"].split(".")[0].strip()   # first finding
                note = (h.get("note") or "").strip()
                panels = [p for p in h.get("panel_titles", []) if p]
                f.write(f"\n### {name}\n\n")
                f.write(f"**Short.** {short}\n\n")
                full = m["reading"].rstrip(".") + "."
                if note:
                    full += f" {note[0].upper()}{note[1:].rstrip('.')}."
                f.write(f"**Full.** {short.rstrip('.')}. {full}\n\n")
                if len(panels) > 1:
                    f.write("**Panels.** "
                            + "; ".join(f"({chr(97+i)}) {t}"
                                        for i, t in enumerate(panels))
                            + "\n\n")
                f.write("```latex\n")
                f.write("\\begin{figure}[t]\n  \\centering\n")
                f.write(f"  \\includegraphics[width=\\columnwidth]"
                        f"{{figures/{name}}}\n")
                f.write(f"  \\caption{{{short.rstrip('.')}.}}\n")
                f.write(f"  \\label{{fig:{name}}}\n")
                f.write("\\end{figure}\n```\n")
    print(f"  docs/report_figures/CAPTIONS.md")

    for sub, items in byfolder.items():
        title, blurb = TITLES[sub]
        with open(os.path.join(OUT, sub, "README.md"), "w") as f:
            f.write(f"# {title}\n\n{blurb}\n\n")
            for n, name, section, m in items:
                f.write(f"## {name}\n\n*Goes in: {section}*\n\n")
                f.write(f"**Question.** {m['question']}\n\n")
                f.write(f"**Data.** {m['data']}\n\n")
                f.write(f"**Shows.** {m['shows']}\n\n")

    print(f"\n{len(rows)} figures across {len(byfolder)} folders in "
          f"docs/report_figures/")


if __name__ == "__main__":
    main()
