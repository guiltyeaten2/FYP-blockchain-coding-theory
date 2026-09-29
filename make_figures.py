"""
Regenerates every figure in docs/ from the committed result JSON.

    python3 make_figures.py                 # all figures -> docs/figures/
    python3 make_figures.py --only fft      # just the FFT ones
    python3 make_figures.py --list          # what can be generated

The figures in these reports used to be hand-written inline SVG. That made
them precise but unmaintainable: re-running a sweep meant redrawing bar
heights by hand, and a figure could silently drift out of step with the
numbers in the table beside it. Everything here is instead computed from the
same JSON the prose quotes, so a figure cannot disagree with its own data.

INPUTS (all committed, so figures regenerate without re-running a sweep):
    benchmark_results.json   the seven-scheme erasure sweep
    fft_results.json         the FFT/NTT decoder measurements
    docs/runA.json           network sim, adversarial sweep, one blob
    docs/runB.json           network sim, adversarial sweep, six blobs
    docs/runC.json           network sim, peer-count sweep

A missing input is reported and skipped rather than fatal -- fft_results.json
in particular takes 10-20 minutes to produce (see fft_benchmark.py), so the
other figures should not be hostage to it.

OUTPUT is SVG. These end up in a PDF through a print-to-PDF path, and vector
text stays sharp at any zoom where a raster screenshot would not.
"""
import argparse
import json
import os

import matplotlib
matplotlib.use("Agg")           # no display in this environment; file output only
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(HERE, "docs")
FIGDIR = os.path.join(DOCS, "figures")

# One colour per scheme, used everywhere, so a reader who learns the palette
# in one figure keeps it in the next. Blues for the block-circulant family,
# distinct hues for the two Reed-Solomon baselines.
COLOURS = {
    "1D-RS":      "#c1442e",
    "2D-RS":      "#d98c1f",
    "BC-2048-L2": "#1f4e79",
    "BC-1024-L2": "#2e75b6",
    "BC-1024-L3": "#5b9bd5",
    "BC-1024-L4": "#9dc3e6",
    "BC-512-L2":  "#123c5a",
}
ORDER = ["1D-RS", "2D-RS", "BC-2048-L2", "BC-1024-L2",
         "BC-1024-L3", "BC-1024-L4", "BC-512-L2"]

# Deterministic output. Without these two, every regeneration rewrites all
# 14 files: matplotlib stamps the SVG with the current time and salts its
# internal clip-path ids randomly. That turns "did the data change?" into an
# unanswerable question in a diff, so both are pinned and the date is
# dropped at save time below.
plt.rcParams["svg.hashsalt"] = "fyp-blockchain-coding-theory"

plt.rcParams.update({
    "figure.dpi": 110,
    "savefig.bbox": "tight",
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linewidth": 0.6,
    "legend.frameon": False,
    "legend.fontsize": 8,
})


def _save(fig, name):
    os.makedirs(FIGDIR, exist_ok=True)
    path = os.path.join(FIGDIR, name)
    fig.savefig(path, format="svg", metadata={"Date": None})
    plt.close(fig)
    print(f"  wrote docs/figures/{name}")
    return path


def _load(path):
    if not os.path.exists(path):
        print(f"  SKIP: {os.path.relpath(path, HERE)} not found")
        return None
    with open(path) as f:
        return json.load(f)


def _pct(x, _pos=None):
    return f"{100 * x:.0f}%"


def _threshold(trials):
    """Erasure rate at which this scheme's success rate crosses 50%.

    Linear interpolation between the two swept rates that bracket the
    crossing. The sweep is fine-grained through the transition band, so this
    is a reasonable reading of the threshold rather than a fitted model --
    and it is stated here rather than eyeballed off a chart."""
    pts = sorted((t["rate"], t["success_rate"]) for t in trials)
    for (r0, s0), (r1, s1) in zip(pts, pts[1:]):
        if s0 >= 0.5 > s1:
            if s0 == s1:
                return r0
            return r0 + (s0 - 0.5) * (r1 - r0) / (s0 - s1)
    return None


# --------------------------------------------------------------- benchmark
def fig_success_curves(bench):
    """Success rate against erasure rate -- the fault-tolerance result."""
    fig, ax = plt.subplots(figsize=(6.6, 3.6))
    for r in bench["results"]:
        ts = sorted(r["trials"], key=lambda t: t["rate"])
        ax.plot([t["rate"] for t in ts], [t["success_rate"] for t in ts],
                marker="o", ms=3.2, lw=1.5, label=r["scheme"],
                color=COLOURS.get(r["scheme"]))
    ax.axhline(0.5, color="#888", lw=0.8, ls=":")
    ax.set_xlabel("erasure rate")
    ax.set_ylabel("fraction of trials recovered")
    ax.set_title("Fault tolerance: recovery against erasure rate")
    ax.xaxis.set_major_formatter(FuncFormatter(_pct))
    ax.yaxis.set_major_formatter(FuncFormatter(_pct))
    ax.set_ylim(-0.04, 1.05)
    ax.legend(ncol=2, loc="lower left")
    return _save(fig, "bench_success_curves.svg")


def fig_tolerance_vs_guarantee(bench):
    """Measured threshold beside the worst-case guarantee each code carries.

    The gap matters: a minimum-distance bound is a guarantee against the
    WORST erasure pattern, while the sweep draws patterns at random. Codes
    whose measured threshold sits well above their own d_min bound are not
    beating a theorem -- they are being handed easier patterns than the bound
    contemplates."""
    labels, meas, guar = [], [], []
    for name in ORDER:
        r = next((x for x in bench["results"] if x["scheme"] == name), None)
        if not r:
            continue
        th = _threshold(r["trials"])
        if th is None:
            continue
        labels.append(name)
        meas.append(th)
        guar.append(r["params"]["worst_case_tolerance"])
    x = range(len(labels))
    fig, ax = plt.subplots(figsize=(6.8, 3.5))
    w = 0.38
    # One colour, not the per-scheme palette: a multi-coloured bar series
    # gives the legend a single swatch, which reads as "measured means 1D-RS".
    # The x labels already say which scheme each bar is.
    ax.bar([i - w / 2 for i in x], meas, w, label="measured threshold (50%)",
           color="#2e75b6")
    ax.bar([i + w / 2 for i in x], guar, w, label="worst-case guarantee",
           color="#bbbbbb", edgecolor="#888", linewidth=0.5)
    for i, (m, g) in enumerate(zip(meas, guar)):
        ax.text(i - w / 2, m + 0.008, f"{m:.2f}", ha="center", fontsize=7)
        ax.text(i + w / 2, g + 0.008, f"{g:.2f}", ha="center", fontsize=7,
                color="#555")
    for i, name in enumerate(labels):
        r = next(x for x in bench["results"] if x["scheme"] == name)
        bound = 1.0 - r["k"] / r["n"]          # Singleton: tolerance <= 1 - R
        ax.plot([i - 0.46, i + 0.46], [bound] * 2, ls="--", lw=1.1,
                color="#c1442e",
                label="rate bound 1$-$R" if i == 0 else None)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=18, ha="right")
    ax.set_ylabel("erasure rate")
    ax.set_title("Measured tolerance against each code's own worst-case bound")
    ax.yaxis.set_major_formatter(FuncFormatter(_pct))
    # Headroom so the legend clears the rate-bound rules and the value labels.
    ax.set_ylim(0, max(max(meas), max(guar)) * 1.55)
    ax.legend(loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.0))
    return _save(fig, "bench_tolerance_vs_guarantee.svg")


def fig_bc_threshold_prediction(bench):
    """BC thresholds against the 1/(1+lambda) local-reach prediction."""
    rows = []
    for r in bench["results"]:
        if not r["scheme"].startswith("BC"):
            continue
        th = _threshold(r["trials"])
        if th is not None:
            rows.append((r["scheme"], r["params"]["lambda"],
                         r["params"]["predicted_local_reach"], th))
    rows.sort(key=lambda t: (t[1], t[0]))
    fig, ax = plt.subplots(figsize=(6.2, 3.5))
    x = range(len(rows))
    ax.bar(x, [t[3] for t in rows], 0.52,
           color=[COLOURS[t[0]] for t in rows], label="measured threshold")
    for i, t in enumerate(rows):
        ax.plot([i - 0.32, i + 0.32], [t[2], t[2]], color="#c1442e", lw=1.8,
                solid_capstyle="butt",
                label="prediction 1/(1+$\\lambda$)" if i == 0 else None)
        ax.text(i, t[3] + 0.006, f"{t[3]:.2f}", ha="center", fontsize=7)
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"{t[0]}\n$\\lambda$={t[1]}" for t in rows], fontsize=8)
    ax.set_ylabel("erasure rate")
    ax.set_title("Block-circulant threshold follows $1/(1+\\lambda)$, not $\\mu$ or $\\omega$")
    ax.yaxis.set_major_formatter(FuncFormatter(_pct))
    ax.legend(loc="upper right")
    return _save(fig, "bench_bc_threshold.svg")


def fig_decode_time(bench):
    """Decode cost against erasure rate, successes only, log axis."""
    fig, ax = plt.subplots(figsize=(6.6, 3.6))
    for r in bench["results"]:
        ts = [t for t in sorted(r["trials"], key=lambda t: t["rate"])
              if t["mean_decode_time_success_only_s"]]
        if not ts:
            continue
        ax.plot([t["rate"] for t in ts],
                [t["mean_decode_time_success_only_s"] for t in ts],
                marker="o", ms=3.2, lw=1.5, label=r["scheme"],
                color=COLOURS.get(r["scheme"]))
    ax.set_yscale("log")
    ax.set_xlabel("erasure rate")
    ax.set_ylabel("mean decode time, successes only (s)")
    ax.set_title("Decode cost against erasure rate")
    ax.xaxis.set_major_formatter(FuncFormatter(_pct))
    ax.legend(ncol=2, loc="upper left")
    return _save(fig, "bench_decode_time.svg")


def fig_data_needed(bench):
    """Surviving data required to rebuild one blob, as a multiple of the blob.

    This is the question that matters for data-availability sampling, where
    a node has to fetch those symbols over the wire. A scheme that tolerates
    a lower erasure rate at the same storage cost necessarily needs more
    surviving data, and 1 blob is the floor nothing can beat."""
    labels, mult = [], []
    for name in ORDER:
        r = next((x for x in bench["results"] if x["scheme"] == name), None)
        if not r:
            continue
        th = _threshold(r["trials"])
        if th is None:
            continue
        labels.append(name)
        mult.append(r["n"] * (1.0 - th) / r["k"])
    fig, ax = plt.subplots(figsize=(6.4, 3.3))
    bars = ax.bar(range(len(labels)), mult, 0.55,
                  color=[COLOURS[l] for l in labels])
    ax.axhline(1.0, color="#c1442e", ls="--", lw=1.2,
               label="theoretical floor (1 blob)")
    for b_, m in zip(bars, mult):
        ax.text(b_.get_x() + b_.get_width() / 2, m + 0.015, f"{m:.2f}x",
                ha="center", fontsize=7.5)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=18, ha="right")
    ax.set_ylabel("surviving data needed / blob size")
    ax.set_title("What a node must actually fetch to rebuild one blob")
    ax.set_ylim(0, max(mult) * 1.18)
    ax.legend(loc="upper left")
    return _save(fig, "bench_data_needed.svg")


# --------------------------------------------------------------------- FFT
def fig_fft_vs_vandermonde(fft):
    """The headline: FFT against the fallback it was meant to replace."""
    rows = fft["ab"]
    rates = sorted({r["rate"] for r in rows})
    schemes = [s for s in ORDER if any(r["scheme"] == s for r in rows)]
    fig, axes = plt.subplots(1, len(rates), figsize=(3.1 * len(rates), 3.6),
                             sharey=True)
    axes = [axes] if len(rates) == 1 else list(axes)
    for ax, rate in zip(axes, rates):
        sub = [next(r for r in rows if r["scheme"] == s and r["rate"] == rate)
               for s in schemes]
        x = range(len(sub))
        w = 0.38
        ax.bar([i - w / 2 for i in x], [r["fft_s"] for r in sub], w,
               color="#c1442e", label="FFT / NTT path")
        ax.bar([i + w / 2 for i in x], [r["vandermonde_s"] for r in sub], w,
               color="#2e75b6", label="Vandermonde fallback")
        for i, r in enumerate(sub):
            if r["ratio"] and r["ratio"] > 1.2:
                ax.text(i, max(r["fft_s"], r["vandermonde_s"]) * 1.15,
                        f"{r['ratio']:.0f}x", ha="center", fontsize=7,
                        color="#c1442e")
            elif not r["fft_eligible"]:
                ax.text(i, max(r["fft_s"], r["vandermonde_s"]) * 1.15,
                        "no NTT", ha="center", fontsize=6.5, color="#666")
        ax.set_yscale("log")
        # Headroom above the tallest bar so the ratio labels are not clipped
        # by the axes or hidden behind the legend.
        top = max(max(r["fft_s"], r["vandermonde_s"]) for r in sub)
        ax.set_ylim(top=top * 3.2)
        ax.set_xticks(list(x))
        ax.set_xticklabels([s.replace("BC-", "") for s in schemes],
                           rotation=40, ha="right", fontsize=7.5)
        ax.set_title(f"{100 * rate:.0f}% erased")
    axes[0].set_ylabel("mean decode time (s), log scale")
    axes[0].legend(loc="lower left")
    fig.suptitle("The NTT decoder is slower than the path it replaces", y=1.02)
    return _save(fig, "fft_vs_vandermonde.svg")


def fig_fft_profile(fft):
    """Where the FFT path's time goes -- the transform is the small part."""
    b = fft["profile"]["buckets"]
    order = ["polynomial division", "NTT / inverse NTT",
             "erasure locator build", "everything else"]
    items = [(k, b[k]) for k in order if k in b]
    total = fft["profile"]["total_s"]
    fig, ax = plt.subplots(figsize=(6.4, 1.9))
    left = 0.0
    shades = {"polynomial division": "#c1442e", "NTT / inverse NTT": "#2e75b6",
              "erasure locator build": "#9dc3e6", "everything else": "#cccccc"}
    for k, v in items:
        ax.barh([0], [v], left=left, height=0.5, color=shades[k],
                label=f"{k} — {100 * v / total:.0f}%")
        if v / total > 0.06:
            ax.text(left + v / 2, 0, f"{100 * v / total:.0f}%", ha="center",
                    va="center", fontsize=8,
                    color="white" if k != "everything else" else "#444")
        left += v
    ax.set_xlim(0, total)
    ax.set_ylim(-0.5, 0.5)
    ax.set_yticks([])
    ax.set_xlabel(f"seconds in one local-block decode (n$_0$={fft['profile']['n0']})")
    ax.set_title("The NTT is not what the NTT decoder spends its time on")
    ax.grid(False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.55), ncol=2)
    return _save(fig, "fft_profile.svg")


def fig_node_width(fft):
    """The cost of defining the code over roots of unity at all."""
    n = fft["nodes"]
    keys = ["small integers", "roots of unity"]
    fig, ax = plt.subplots(figsize=(4.4, 3.0))
    bars = ax.bar(keys, [n[k] for k in keys], 0.5,
                  color=["#2e75b6", "#c1442e"])
    for b_, k in zip(bars, keys):
        ax.text(b_.get_x() + b_.get_width() / 2, n[k] * 1.02,
                f"{n[k]:.3f}s", ha="center", fontsize=8)
    ax.set_ylabel(f"vandermonde_solve, {n['n_nodes']} nodes (s)")
    ax.set_title(f"Evaluation-point width costs {n['ratio']:.1f}x\n"
                 "— paid even when the NTT never runs", fontsize=9)
    ax.set_ylim(0, max(n[k] for k in keys) * 1.25)
    return _save(fig, "fft_node_width.svg")


def fig_grs_premise(fft):
    """The premise each phase rests on, as coefficients that fail to vanish.

    Two panels with independent y scales, deliberately. Phase 1 moves from 1
    to 0 and phase 2 sits at 2048; drawn on one shared axis the phase-1 result
    -- which is the whole point of the fix -- is a flat line at zero that a
    reader cannot distinguish from no data. Each panel is annotated with how
    many coefficients were required to vanish, so the separate scales cannot
    mislead about the relative size of the two cases."""
    s_ = fft["structure"]
    panels = [("Phase 1 — single local block", s_["phase1"], "#1a7f37"),
              ("Phase 2 — union of two blocks", s_["phase2"], "#c1442e")]
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.3))
    for ax, (title, d, fixed_colour) in zip(axes, panels):
        bars = ax.bar(["as received", "after undoing\nGRS multipliers"],
                      [d["raw"], d["fixed"]], 0.55,
                      color=["#999999", fixed_colour])
        top = max(d["raw"], d["fixed"], 1)
        for b_, v in zip(bars, [d["raw"], d["fixed"]]):
            ax.text(b_.get_x() + b_.get_width() / 2, v + top * 0.04, str(v),
                    ha="center", fontsize=9,
                    fontweight="bold" if v == 0 else "normal",
                    color="#1a7f37" if v == 0 else "#333")
        ax.set_ylim(0, top * 1.35)
        ax.set_title(f"{title}\nn={d['n']}, {d['tail_len']} coefficients "
                     f"must vanish", fontsize=8.5)
    axes[0].set_ylabel("nonzero tail coefficients")
    verdict = ("premise HOLDS — this is a GRS code"
               if s_["phase1"]["fixed"] == 0 else "premise fails")
    axes[0].text(0.5, 0.93, verdict, transform=axes[0].transAxes,
                 ha="center", fontsize=8, color="#1a7f37")
    axes[1].text(0.5, 0.93, "premise FAILS — no multiplier fixes it",
                 transform=axes[1].transAxes, ha="center", fontsize=8,
                 color="#c1442e")
    return _save(fig, "fft_grs_premise.svg")


# ----------------------------------------------------------- network sim
def _net_series(rows, scheme, xkey, ykey):
    sub = sorted((r for r in rows if r["scheme"] == scheme),
                 key=lambda r: r[xkey])
    return [r[xkey] for r in sub], [r[ykey] for r in sub]


def fig_net_erasure(runA):
    fig, ax = plt.subplots(figsize=(6.0, 3.4))
    rows = runA["rows"]
    for s in ORDER:
        if not any(r["scheme"] == s for r in rows):
            continue
        x, y = _net_series(rows, s, "adversarial", "mean_erasure_fraction")
        ax.plot(x, y, marker="o", ms=3, lw=1.4, label=s, color=COLOURS[s])
    rep = runA["config"].get("custody_replication", 4)
    xs = [i / 20 for i in range(17)]
    ax.plot(xs, [p ** rep for p in xs], ls="--", lw=1.3, color="#444",
            label=f"$p^{{{rep}}}$ (custody replication {rep})")
    ax.set_xlabel("fraction of peers withholding")
    ax.set_ylabel("realised erasure fraction")
    ax.set_title("Custody replication turns withholding into a much smaller erasure rate")
    ax.annotate("all six schemes coincide: the erasure rate is set by the\n"
                "network and custody, not by the code being carried",
                xy=(0.03, 0.62), xycoords="axes fraction", fontsize=7.5,
                color="#555")
    ax.xaxis.set_major_formatter(FuncFormatter(_pct))
    ax.yaxis.set_major_formatter(FuncFormatter(_pct))
    ax.legend(ncol=2, loc="upper left")
    return _save(fig, "net_erasure_vs_adversarial.svg")


def fig_net_recovery(runA):
    fig, ax = plt.subplots(figsize=(6.0, 3.4))
    rows = runA["rows"]
    for s in ORDER:
        sub = sorted((r for r in rows if r["scheme"] == s),
                     key=lambda r: r["adversarial"])
        if not sub:
            continue
        ax.plot([r["adversarial"] for r in sub],
                [r["recovered"] / r["trials"] for r in sub],
                marker="o", ms=3, lw=1.4, label=s, color=COLOURS[s])
    ax.set_xlabel("fraction of peers withholding")
    ax.set_ylabel("fraction of trials recovered")
    ax.set_title("Recovery against adversarial withholding")
    ax.xaxis.set_major_formatter(FuncFormatter(_pct))
    ax.yaxis.set_major_formatter(FuncFormatter(_pct))
    ax.set_ylim(-0.04, 1.05)
    ax.legend(ncol=2, loc="lower left")
    return _save(fig, "net_recovery_vs_adversarial.svg")


def fig_net_gather_vs_decode(runB):
    """Gather against decode, per scheme. The whole point of the figure is
    the axis: decode is orders of magnitude above gather, so the bottleneck
    is arithmetic, not bandwidth."""
    rows = [r for r in runB["rows"] if r["adversarial"] == 0.0]
    schemes = [s for s in ORDER if any(r["scheme"] == s for r in rows)]
    g = [next(r for r in rows if r["scheme"] == s)["mean_gather_s"]
         for s in schemes]
    d = [next(r for r in rows if r["scheme"] == s)["mean_decode_s"]
         for s in schemes]
    x = range(len(schemes))
    w = 0.38
    fig, ax = plt.subplots(figsize=(6.2, 3.5))
    ax.bar([i - w / 2 for i in x], g, w, color="#2e75b6", label="gather (network)")
    ax.bar([i + w / 2 for i in x], d, w, color="#c1442e", label="decode (CPU)")
    deadline = runB["config"].get("deadline_s")
    if deadline:
        ax.axhline(deadline, color="#444", lw=1.1, ls="--",
                   label=f"slot deadline ({deadline:.0f}s)")
    ax.set_yscale("log")
    from matplotlib.transforms import blended_transform_factory
    tr = blended_transform_factory(ax.transData, ax.transAxes)
    for i, v in enumerate(d):
        if v <= 0:
            # Genuine zero, not missing data: custody replication left no
            # erasures at this adversary level, so no decode ran. Anchored in
            # axes fraction so it sits clear of the deadline rule.
            ax.text(i + w / 2, 0.04, "no erasures\nto decode", transform=tr,
                    ha="center", va="bottom", fontsize=6.5, color="#666")
    ax.set_xticks(list(x))
    ax.set_xticklabels(schemes, rotation=25, ha="right", fontsize=8)
    ax.set_ylabel("seconds per slot, log scale")
    ax.set_title(f"Decode dominates gather by orders of magnitude "
                 f"({runB['config'].get('blobs_per_slot', 6)} blobs, no adversary)")
    ax.legend()
    return _save(fig, "net_gather_vs_decode.svg")


def fig_net_throughput(runB):
    """Blobs actually reconstructed per slot, against withholding.

    The ordering here inverts the coding benchmark's tolerance ordering:
    the scheme that survives the most erasure rebuilds the fewest blobs,
    because its decode is too slow to fit the slot."""
    rows = runB["rows"]
    target = runB["config"].get("blobs_per_slot", 6)
    fig, ax = plt.subplots(figsize=(6.0, 3.4))
    for s_ in ORDER:
        sub = sorted((r for r in rows if r["scheme"] == s_),
                     key=lambda r: r["adversarial"])
        if not sub:
            continue
        ax.plot([r["adversarial"] for r in sub],
                [r["blobs_per_slot"] for r in sub],
                marker="o", ms=3.2, lw=1.5, label=s_, color=COLOURS[s_])
    ax.axhline(target, color="#444", ls="--", lw=1.1,
               label=f"blobs attempted ({target:.0f})")
    ax.set_xlabel("fraction of peers withholding")
    ax.set_ylabel("blobs reconstructed per slot")
    ax.set_title("Throughput inverts the tolerance ordering")
    ax.xaxis.set_major_formatter(FuncFormatter(_pct))
    ax.legend(ncol=2, loc="lower left")
    return _save(fig, "net_throughput.svg")


def fig_net_peers(runC):
    fig, ax = plt.subplots(figsize=(6.0, 3.4))
    rows = runC["rows"]
    styles = {0.3: "-", 0.6: "--"}
    for s in sorted({r["scheme"] for r in rows}):
        for adv in sorted({r["adversarial"] for r in rows}):
            sub = sorted((r for r in rows
                          if r["scheme"] == s and r["adversarial"] == adv),
                         key=lambda r: r["peers"])
            if not sub:
                continue
            ax.plot([r["peers"] for r in sub],
                    [r["mean_erasure_fraction"] for r in sub],
                    marker="o", ms=3, lw=1.4, color=COLOURS.get(s),
                    ls=styles.get(adv, "-"),
                    label=f"{s}, {100 * adv:.0f}% withholding")
    from math import comb
    rep = runC["config"].get("custody_replication", 4)
    peers = sorted({r["peers"] for r in rows})
    for adv in sorted({r["adversarial"] for r in rows}):
        hyp = [comb(round(adv * n), rep) / comb(n, rep) if n >= rep else 0.0
               for n in peers]
        ax.plot(peers, hyp, ls="none", marker="o", ms=7, mfc="none",
                mec="#333", mew=1.0,
                label=f"hypergeometric, {100 * adv:.0f}% (computed)")
        ax.axhline(adv ** rep, color="#888", lw=0.9, ls=":")
        ax.annotate(f"$p^{{{rep}}}$ = {adv ** rep:.3f}",
                    xy=(peers[-1], adv ** rep), fontsize=7, color="#666",
                    ha="right", va="bottom")
    ax.set_xscale("log", base=2)
    ax.set_xlabel("peers in the sampled network")
    ax.set_ylabel("realised erasure fraction")
    ax.set_title("Realised erasure rises with peer count, then plateaus")
    ax.yaxis.set_major_formatter(FuncFormatter(_pct))
    ax.legend(loc="best")
    return _save(fig, "net_peers.svg")


# --------------------------------------------------------------------- main
GROUPS = {
    "bench": ("benchmark_results.json",
              [fig_success_curves, fig_tolerance_vs_guarantee,
               fig_bc_threshold_prediction, fig_decode_time,
               fig_data_needed]),
    "fft":   ("fft_results.json",
              [fig_fft_vs_vandermonde, fig_fft_profile, fig_node_width,
               fig_grs_premise]),
    "netA":  (os.path.join("docs", "runA.json"),
              [fig_net_erasure, fig_net_recovery]),
    "netB":  (os.path.join("docs", "runB.json"),
              [fig_net_gather_vs_decode, fig_net_throughput]),
    "netC":  (os.path.join("docs", "runC.json"), [fig_net_peers]),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", choices=sorted(GROUPS),
                    help="generate only these groups")
    ap.add_argument("--list", action="store_true",
                    help="list groups and their inputs, then exit")
    args = ap.parse_args()

    if args.list:
        for g, (src, fns) in GROUPS.items():
            print(f"{g:<6} from {src:<24} -> {len(fns)} figure(s)")
        return

    wanted = args.only or list(GROUPS)
    made = 0
    for g in wanted:
        src, fns = GROUPS[g]
        print(f"[{g}] {src}")
        data = _load(os.path.join(HERE, src))
        if data is None:
            continue
        for fn in fns:
            fn(data)
            made += 1
    print(f"\n{made} figure(s) in {os.path.relpath(FIGDIR, HERE)}/")
    if made == 0:
        print("nothing generated -- check the inputs listed above")


if __name__ == "__main__":
    main()
