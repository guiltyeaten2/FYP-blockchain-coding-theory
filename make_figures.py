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

# What a reader sees. The JSON keys are terse identifiers; the reports write
# these parameterisations as omega/lambda, and a figure that disagrees with
# the prose beside it makes the reader stop and translate.
DISPLAY = {
    "1D-RS": "1D-RS",
    "2D-RS": "2D-RS",
    "BC-2048-L2": "BC \u03c92048 \u03bb2",
    "BC-1024-L2": "BC \u03c91024 \u03bb2",
    "BC-1024-L3": "BC \u03c91024 \u03bb3",
    "BC-1024-L4": "BC \u03c91024 \u03bb4",
    "BC-512-L2":  "BC \u03c9512 \u03bb2",
}


def disp(name):
    """Display label for a scheme, falling back to the raw key."""
    return DISPLAY.get(name, name)

# Deterministic output. Without these two, every regeneration rewrites all
# 14 files: matplotlib stamps the SVG with the current time and salts its
# internal clip-path ids randomly. That turns "did the data change?" into an
# unanswerable question in a diff, so both are pinned and the date is
# dropped at save time below.
plt.rcParams["svg.hashsalt"] = "fyp-blockchain-coding-theory"

# Page geometry, because a figure that is wider than the text column gets
# scaled down by the browser and every font size in it shrinks with it. The
# reports are A4 with 16mm side margins, so the text column is 178mm =
# 7.01in. Nothing here is drawn wider than that, and the two-panel figures
# use exactly it rather than sprawling and being shrunk to fit.
FIGW = 7.0
HALF = 3.4          # one panel of a two-panel figure

plt.rcParams.update({
    "figure.dpi": 110,
    "savefig.bbox": "tight",
    # Sized against 10.5pt body text. The previous 9pt base put legends at
    # 8pt and tick labels lower still, which is not comfortably readable on
    # paper once a figure is placed in the column.
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linewidth": 0.6,
    "legend.frameon": False,
    "legend.fontsize": 9,
    "lines.linewidth": 1.8,
    "lines.markersize": 4,
})


def _label_ends(ax, series, fontsize=9):
    """Label each line at its right-hand end instead of in a legend.

    A seven-entry legend makes the reader hold seven colour-to-name pairings
    in their head and then find each one in a thicket of overlapping curves.
    Putting the name where the line ends removes that lookup entirely. Labels
    are pushed apart vertically when they would collide, so the nudged ones
    no longer sit exactly on their line -- which is why each is drawn in its
    line's own colour.

    `series` is [(name, xs, ys, colour)]; lines must already be plotted.
    """
    ends = sorted(((ys[-1], xs[-1], name, colour)
                   for name, xs, ys, colour in series if xs),
                  key=lambda t: t[0])
    if not ends:
        return
    y0, y1 = ax.get_ylim()
    log = ax.get_yscale() == "log"
    import math
    to = (lambda v: math.log10(v)) if log else (lambda v: v)
    fro = (lambda v: 10 ** v) if log else (lambda v: v)
    lo, hi = to(y0), to(y1)
    gap = (hi - lo) * 0.062          # minimum spacing in axis units
    placed = []
    for yv, xv, name, colour in ends:
        t = to(yv)
        if placed and t - placed[-1][0] < gap:
            t = placed[-1][0] + gap
        placed.append((t, xv, name, colour))
    # If the stack overflowed the top, slide the whole run back down.
    over = placed[-1][0] - hi
    if over > 0:
        placed = [(t - over, xv, n, c) for t, xv, n, c in placed]
    xr = ax.get_xlim()
    for t, xv, name, colour in placed:
        # Series end at different x, so a label can land on a NEIGHBOUR's
        # curve even after vertical de-collision. The white backing keeps it
        # legible wherever it lands, which is cheaper than solving the
        # general label-placement problem.
        ax.annotate(name, xy=(xv, fro(t)), xytext=(7, 0),
                    textcoords="offset points",
                    ha="left", va="center", fontsize=fontsize, color=colour,
                    bbox=dict(boxstyle="round,pad=0.18", fc="white",
                              ec="none", alpha=0.85))
    # Room on the right for the labels to live in.
    ax.set_xlim(xr[0], xr[1] + (xr[1] - xr[0]) * 0.22)


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


def _subtitle(ax, text, width=95):
    """A small note under the figure saying what was actually measured.

    Placed at the BOTTOM, not under the title. Several titles here run to two
    lines, and anything positioned above the axes then has to know how tall
    the title happens to be or it lands on top of it. The foot of the figure
    is unoccupied, never collides, and matches the convention of a source
    line.

    Most titles here state a finding, which is what makes a figure useful in
    a report. A finding is not a definition, though -- nothing in "Decode
    cost against erasure rate" says whether the cost is a mean or a median,
    over which trials, at what size. That belongs here."""
    import textwrap
    fig = ax.get_figure()
    wrapped = "\n".join(textwrap.wrap(text, width))
    fig.text(0.5, -0.015, wrapped, ha="center", va="top",
             fontsize=8.2, color="#555", linespacing=1.35)


def _readable_log(ax, axis="y"):
    """Put plain numbers on a log axis.

    Matplotlib's default labels a log axis only at decades, so a chart
    spanning 0.2s to 40s is labelled "10^0, 10^1" and the reader cannot read
    a value off it. This places 1-2-5 ticks across the range and writes them
    as ordinary numbers."""
    a = ax.yaxis if axis == "y" else ax.xaxis
    lo, hi = (ax.get_ylim() if axis == "y" else ax.get_xlim())
    ticks, d = [], 1e-6
    while d <= hi * 10:
        for m in (1, 2, 5):
            v = m * d
            if lo <= v <= hi:
                ticks.append(v)
        d *= 10
    if len(ticks) < 2:
        return
    a.set_major_locator(matplotlib.ticker.FixedLocator(ticks))
    a.set_minor_locator(matplotlib.ticker.NullLocator())
    a.set_major_formatter(FuncFormatter(
        lambda v, _p: (f"{v:g}" if v >= 1 else f"{v:.2f}".rstrip("0").rstrip("."))))


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
    """Success rate against erasure rate -- the fault-tolerance result.

    Two panels. The left is the whole sweep; the right zooms on the band
    where everything actually happens. Both are needed because the three
    lambda=2 rows land on top of each other -- which IS the result, so the
    figure has to make them separable rather than hide the coincidence.
    Colour alone cannot do that when curves overlap exactly, so each scheme
    also gets its own marker and dash pattern, and the markers are open so
    that one sitting on another still reads as two."""
    STYLE = {
        "1D-RS":      ("o", "-",  8),
        "2D-RS":      ("s", "-",  7),
        "BC-2048-L2": ("^", "--", 7),
        "BC-1024-L2": ("v", "-.", 7),
        "BC-1024-L3": ("D", "-",  5.5),
        "BC-1024-L4": ("P", "-",  7),
        "BC-512-L2":  ("X", ":",  7),
    }
    # Stacked, not side by side. Two panels sharing 7in of column width left
    # each one about 3.4in, at which the titles collided and both legends sat
    # on top of the data. Full width each, one shared legend underneath.
    fig, (ax, axz) = plt.subplots(2, 1, figsize=(FIGW, 6.6))
    fig.subplots_adjust(hspace=0.42)

    def draw(a, schemes):
        for r in bench["results"]:
            if r["scheme"] not in schemes:
                continue
            m, ls, ms = STYLE[r["scheme"]]
            ts = sorted(r["trials"], key=lambda t: t["rate"])
            a.plot([t["rate"] for t in ts], [t["success_rate"] for t in ts],
                   marker=m, ms=ms, lw=1.4, ls=ls, label=disp(r["scheme"]),
                   color=COLOURS.get(r["scheme"]),
                   mfc="none", mew=1.2)
        a.axhline(0.5, color="#888", lw=0.8, ls=":")
        a.xaxis.set_major_formatter(FuncFormatter(_pct))
        a.yaxis.set_major_formatter(FuncFormatter(_pct))
        a.set_ylim(-0.06, 1.08)

    allsch = [r["scheme"] for r in bench["results"]]
    draw(ax, allsch)
    ax.set_xlabel("erasure rate (fraction of codeword symbols erased)")
    ax.set_ylabel("trials recovered byte-exact")
    ax.set_title("Fault tolerance across the full sweep")
    _subtitle(ax, "520 trials over one EIP-4844 blob; a trial counts as "
                  "recovered only if the bytes match the original exactly")
    handles, labels = ax.get_legend_handles_labels()

    # Zoom on the CLUSTER, not on the whole transition: the thresholds span
    # 0.21 to 0.51, so a window covering all of them is barely a zoom at all.
    # The thing a reader cannot resolve in the left panel is the group of
    # curves that coincide, so the window is the tightest one holding the
    # most thresholds, and only those schemes are drawn in it.
    pairs = [(r["scheme"], t) for r in bench["results"]
             if (t := _threshold(r["trials"])) is not None]
    width = 0.055
    centre = max((c for _, c in pairs),
                 key=lambda c: sum(abs(t - c) <= width for _, t in pairs))
    lo, hi = centre - width, centre + width
    inband = {n for n, t in pairs if lo <= t <= hi}
    draw(axz, inband)
    axz.set_xlim(lo, hi)
    axz.set_xlabel("erasure rate")
    axz.set_ylabel("fraction of trials recovered")
    axz.set_title(f"Zoom on the {len(inband)} schemes that land together "
                  f"({100 * lo:.0f}–{100 * hi:.0f}% erasure)")
    # Stagger the value labels: several thresholds sit within a thousandth
    # of each other, so stacking them at one height is unreadable.
    for k, (n, t) in enumerate(sorted((p_ for p_ in pairs if p_[0] in inband),
                                      key=lambda p_: p_[1])):
        axz.plot([t], [0.5], marker="|", ms=13, mew=1.8,
                 color=COLOURS.get(n))
        axz.annotate(f"{disp(n)}  {t:.3f}", xy=(t, 0.5),
                     xytext=(10, -26 - 17 * k), textcoords="offset points",
                     ha="left", fontsize=8.5, color=COLOURS.get(n),
                     bbox=dict(boxstyle="round,pad=0.2", fc="white",
                               ec="none", alpha=0.9),
                     arrowprops=dict(arrowstyle="-", lw=0.6,
                                     color=COLOURS.get(n), alpha=0.7))
    # One shared legend below both panels, so neither has one over its data.
    fig.legend(handles, labels, loc="lower center", ncol=4,
               bbox_to_anchor=(0.5, -0.02), fontsize=9)
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
    fig, ax = plt.subplots(figsize=(FIGW, 4.0))
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
    ax.set_xticklabels([disp(l) for l in labels], rotation=18, ha="right")
    ax.set_ylabel("erasure rate tolerated")
    ax.set_title("Measured tolerance against each code's own worst-case bound")
    ax.yaxis.set_major_formatter(FuncFormatter(_pct))
    _subtitle(ax, "storage matched at ~2x across every scheme; guarantee is "
                  "the minimum-distance bound, measured is the 50% threshold")
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
    fig, ax = plt.subplots(figsize=(FIGW, 4.0))
    x = range(len(rows))
    ax.bar(x, [t[3] for t in rows], 0.52,
           color=[COLOURS[t[0]] for t in rows], label="measured threshold")
    for i, t in enumerate(rows):
        ax.plot([i - 0.32, i + 0.32], [t[2], t[2]], color="#c1442e", lw=1.8,
                solid_capstyle="butt",
                label="prediction 1/(1+$\\lambda$)" if i == 0 else None)
        ax.text(i, t[3] + 0.006, f"{t[3]:.2f}", ha="center", fontsize=7)
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"{disp(t[0])}" for t in rows], fontsize=8.5)
    ax.set_ylabel("erasure rate tolerated")
    ax.set_title("Block-circulant threshold follows $1/(1+\\lambda)$, not $\\mu$ or $\\omega$")
    ax.yaxis.set_major_formatter(FuncFormatter(_pct))
    _subtitle(ax, "bars: erasure rate at 50% success. rules: the local code's "
                  "stopping rate $S_0=\\rho/n_0=1/(1+\\lambda)$")
    ax.legend(loc="upper right")
    return _save(fig, "bench_bc_threshold.svg")


def fig_decode_time(bench):
    """Decode cost against erasure rate, successes only, log axis."""
    fig, ax = plt.subplots(figsize=(FIGW, 4.0))
    series = []
    for r in bench["results"]:
        ts = [t for t in sorted(r["trials"], key=lambda t: t["rate"])
              if t["mean_decode_time_success_only_s"]]
        if not ts:
            continue
        xs = [t["rate"] for t in ts]
        ys = [t["mean_decode_time_success_only_s"] for t in ts]
        ax.plot(xs, ys, marker="o", color=COLOURS.get(r["scheme"]))
        series.append((disp(r["scheme"]), xs, ys, COLOURS.get(r["scheme"])))
    ax.set_yscale("log")
    ax.set_xlabel("erasure rate (fraction of codeword symbols erased)")
    ax.set_ylabel("mean decode time (s)")
    ax.set_title("Decode cost against erasure rate")
    _subtitle(ax, "mean over the trials that recovered; n$\\approx$8192, "
                  "k=4096, single-threaded Python over galois")
    ax.xaxis.set_major_formatter(FuncFormatter(_pct))
    _readable_log(ax)
    _label_ends(ax, series)          # named at the line end, not in a legend
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
    fig, ax = plt.subplots(figsize=(FIGW, 3.8))
    bars = ax.bar(range(len(labels)), mult, 0.55,
                  color=[COLOURS[l] for l in labels])
    ax.axhline(1.0, color="#c1442e", ls="--", lw=1.2,
               label="theoretical floor (1 blob)")
    for b_, m in zip(bars, mult):
        ax.text(b_.get_x() + b_.get_width() / 2, m + 0.015, f"{m:.2f}x",
                ha="center", fontsize=7.5)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=18, ha="right")
    ax.set_ylabel("surviving data needed (blobs)")
    ax.set_title("What a node must actually fetch to rebuild one blob")
    _subtitle(ax, "n(1-tolerance)/k: surviving symbols required, as a "
                  "multiple of one blob")
    ax.set_ylim(0, max(mult) * 1.18)
    ax.legend(loc="upper left")
    return _save(fig, "bench_data_needed.svg")


def _common_rate(bench):
    """Highest swept rate at which every scheme still has a decode time.

    Comparisons at a single rate need a rate every scheme actually reached;
    picking one by hand risks flattering whichever scheme happens to be
    cheap there, and silently breaks if the sweep changes."""
    per = {r["scheme"]: {t["rate"]: t["mean_decode_time_success_only_s"]
                         for t in r["trials"]} for r in bench["results"]}
    ok = [rate for rate in bench["rates"]
          if all(d.get(rate) for d in per.values())]
    return (max(ok) if ok else None), per


def fig_tolerance_vs_cost(bench):
    """What each scheme costs for the erasure tolerance it delivers.

    The report's central question is a trade-off, and a trade-off is badly
    served by two separate bar charts. Tolerance on one axis and decode cost
    on the other puts every scheme in one picture: down and to the right is
    better, and the schemes on the lower-right frontier are the ones not
    beaten on both counts at once."""
    rate, per = _common_rate(bench)
    if rate is None:
        print("  SKIP tolerance-vs-cost: no rate common to every scheme")
        return None
    pts = []
    for r in bench["results"]:
        th = _threshold(r["trials"])
        c = per[r["scheme"]].get(rate)
        if th and c:
            pts.append((r["scheme"], th, c))

    fig, ax = plt.subplots(figsize=(FIGW, 4.4))
    for name, th, c in pts:
        ax.scatter([th], [c], s=95, color=COLOURS.get(name), zorder=3,
                   edgecolor="white", linewidth=0.8)
        ax.annotate(disp(name), xy=(th, c), xytext=(7, 4),
                    textcoords="offset points", fontsize=7.6)

    # Pareto frontier: nothing tolerates more erasure AND decodes faster.
    front = sorted((p for p in pts
                    if not any(q[1] > p[1] and q[2] < p[2] for q in pts)),
                   key=lambda p: p[1])
    ax.plot([p[1] for p in front], [p[2] for p in front], ls="--", lw=1.1,
            color="#444", zorder=2,
            label=f"frontier — not beaten on both counts ({len(front)} schemes)")
    ax.set_yscale("log")
    ax.set_xlabel("erasure tolerated (rate at 50% success)")
    ax.set_ylabel(f"decode time at {100 * rate:.0f}% erasure (s), log scale")
    ax.set_title("Tolerance against the cost of achieving it\n"
                 "lower and further right is better", fontsize=10)
    ax.xaxis.set_major_formatter(FuncFormatter(_pct))
    _readable_log(ax)
    ax.legend(loc="upper left", fontsize=8)
    return _save(fig, "bench_tolerance_vs_cost.svg")


def fig_encode_decode(bench):
    """Encode cost against decode cost.

    These are not symmetric in a data-availability system and should not be
    read as one number. A blob is encoded once, by the proposer; it is
    decoded by every node that has to reconstruct it. An expensive encode
    amortises over the network, an expensive decode does not."""
    rate, per = _common_rate(bench)
    if rate is None:
        return None
    names = [s for s in ORDER if any(r["scheme"] == s
                                     for r in bench["results"])]
    enc = {r["scheme"]: r["encode_time_s"] for r in bench["results"]}
    fig, ax = plt.subplots(figsize=(FIGW, 4.0))
    x = range(len(names))
    w = 0.38
    ax.bar([i - w / 2 for i in x], [enc[n] for n in names], w,
           color="#9dc3e6", label="encode, once per blob")
    ax.bar([i + w / 2 for i in x], [per[n][rate] for n in names], w,
           color="#c1442e", label=f"decode at {100 * rate:.0f}%, per node")
    ax.set_yscale("log")
    ax.set_xticks(list(x))
    ax.set_xticklabels([disp(n) for n in names], rotation=20, ha="right", fontsize=8)
    ax.set_ylabel("time for one blob (s)")
    ax.set_title("Encode is paid once; decode is paid by everyone")
    _subtitle(ax, "one 128 KiB blob; decode measured at the highest rate "
                  "every scheme still recovers")
    _readable_log(ax)
    ax.legend(fontsize=8)
    return _save(fig, "bench_encode_decode.svg")


def fig_cost_per_erasure(bench):
    """Decode time per erased symbol -- cost with the workload divided out.

    Raw decode time rises with erasure rate for every scheme, which tells
    you mostly that there is more to repair. Dividing by the number of
    symbols actually erased removes that and leaves the algorithmic
    difference: a flat line is linear work per erasure, a rising one is
    superlinear."""
    fig, ax = plt.subplots(figsize=(FIGW, 4.0))
    series = []
    for r in bench["results"]:
        xs, ys = [], []
        for t in sorted(r["trials"], key=lambda t: t["rate"]):
            c, e = t["mean_decode_time_success_only_s"], t["n_erased_mean"]
            if c and e:
                xs.append(t["rate"])
                ys.append(1e3 * c / e)          # milliseconds per erasure
        if xs:
            ax.plot(xs, ys, marker="o", color=COLOURS.get(r["scheme"]))
            series.append((r["scheme"], xs, ys, COLOURS.get(r["scheme"])))
    ax.set_yscale("log")
    ax.set_xlabel("erasure rate (fraction of codeword symbols erased)")
    ax.set_ylabel("decode time per erased symbol (ms)")
    ax.set_title("Cost per erasure repaired, with the workload divided out")
    _subtitle(ax, "decode time divided by the number of symbols actually "
                  "erased in that trial")
    ax.xaxis.set_major_formatter(FuncFormatter(_pct))
    _readable_log(ax)
    _label_ends(ax, series)
    return _save(fig, "bench_cost_per_erasure.svg")


def fig_decode_vs_erasure_count(bench):
    """Decode time against the absolute number of erasures, 1D-RS vs 2D-RS.

    Plotted against erasure COUNT rather than rate because the two codes
    have different lengths (8192 against 8448), so the same rate is not the
    same amount of repair work. This is the figure in the 1D-vs-2D
    comparison document, regenerated from the current sweep."""
    fig, ax = plt.subplots(figsize=(FIGW, 4.0))
    for name in ("1D-RS", "2D-RS"):
        r = next((x for x in bench["results"] if x["scheme"] == name), None)
        if not r:
            continue
        pts = sorted((t["n_erased_mean"], t["mean_decode_time_success_only_s"])
                     for t in r["trials"]
                     if t["mean_decode_time_success_only_s"])
        ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", ms=3.5,
                lw=1.6, label=f"{disp(name)}  (n={r['n']})", color=COLOURS[name])
    ax.set_xlabel("total erasures in the codeword")
    ax.set_ylabel("mean decode time, successes only (s)")
    ax.set_title("One long division against many short ones")
    ax.legend()
    return _save(fig, "rs_decode_vs_erasure_count.svg")


def fig_decoder_fix(data):
    """The decoder correctness fix, before and after.

    The only figure here whose data is not produced by a script in this
    repo: it measures a historical run at a parameterisation the current
    sweep does not cover, so the counts live in decoder_fix_results.json
    with their provenance recorded alongside them."""
    cats = ["correct recovery", "silent corruption", "honest failure"]
    keys = ["correct", "silent_corruption", "honest_failure"]
    cols = ["#1a7f37", "#c1442e", "#999999"]
    fig, ax = plt.subplots(figsize=(FIGW, 3.9))
    x = range(len(cats))
    w = 0.38
    for off, phase, shade in ((-w / 2, "before", 0.45), (w / 2, "after", 1.0)):
        vals = [data[phase][k] for k in keys]
        ax.bar([i + off for i in x], vals, w,
               color=[c for c in cols], alpha=shade,
               edgecolor="#333", linewidth=0.6)
        for i, v in enumerate(vals):
            ax.text(i + off, v + 0.6, str(v), ha="center", fontsize=8)
    ax.set_xticks(list(x))
    ax.set_xticklabels(cats)
    ax.set_ylabel(f"trials (of {data['trials']})")
    ax.set_xlabel("outcome")
    ax.set_title("The decoder fix: silent corruption eliminated,\n"
                 "correct recoveries up", fontsize=11)
    _subtitle(ax, f"the same {data['trials']} trials at "
                  f"{data['parameterisation']}, spanning "
                  f"{100 * min(data['rates']):.0f}-"
                  f"{100 * max(data['rates']):.0f}% erasure, re-run through "
                  "both decoders")
    ax.set_ylim(0, data["trials"] * 1.05)
    # Neutral proxies: before/after is carried by shade and position, while
    # colour carries the outcome category. Letting the legend take a bar's
    # own colour would say the pairing is colour-coded, which it is not.
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(facecolor="#777", alpha=0.45, edgecolor="#333",
                             label="before the fix"),
                       Patch(facecolor="#777", alpha=1.0, edgecolor="#333",
                             label="after the fix")], fontsize=8)
    return _save(fig, "bench_decoder_fix.svg")


# --------------------------------------------------------------------- FFT
def fig_fft_vs_vandermonde(fft):
    """The headline: FFT against the fallback it was meant to replace."""
    rows = fft["ab"]
    rates = sorted({r["rate"] for r in rows})
    schemes = [s for s in ORDER if any(r["scheme"] == s for r in rows)]
    fig, axes = plt.subplots(1, len(rates), figsize=(FIGW, 4.4),
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
        ax.set_xticklabels([disp(s) for s in schemes],
                           rotation=45, ha="right", fontsize=8)
        ax.set_title(f"{100 * rate:.0f}% erased")
    axes[0].set_ylabel("mean decode time (s), log scale")
    # Legend below the panels: inside the first one it covered the bars it
    # was labelling.
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.06))
    fig.suptitle("The NTT decoder is slower than the path it replaces", y=1.0)
    return _save(fig, "fft_vs_vandermonde.svg")


def fig_fft_profile(fft):
    """Where the FFT path's time goes -- the transform is the small part."""
    b = fft["profile"]["buckets"]
    order = ["polynomial division", "NTT / inverse NTT",
             "erasure locator build", "everything else"]
    items = [(k, b[k]) for k in order if k in b]
    total = fft["profile"]["total_s"]
    fig, ax = plt.subplots(figsize=(FIGW, 2.3))
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
    fig, ax = plt.subplots(figsize=(5.0, 3.4))
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
    fig, axes = plt.subplots(1, 2, figsize=(FIGW, 3.7))
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
    fig, ax = plt.subplots(figsize=(FIGW, 3.9))
    rows = runA["rows"]
    # Every scheme produces the SAME curve here -- the erasure rate is set by
    # the network and custody, not by the code. Six legend entries would
    # describe one visible line, so they are drawn in a common grey and
    # named once.
    names = [s for s in ORDER if any(r["scheme"] == s for r in rows)]
    for s in names:
        x, y = _net_series(rows, s, "adversarial", "mean_erasure_fraction")
        ax.plot(x, y, marker="o", lw=1.4, color="#2e75b6", alpha=0.55)
    ax.plot([], [], marker="o", lw=1.4, color="#2e75b6", alpha=0.55,
            label=f"all {len(names)} schemes (curves coincide)")
    rep = runA["config"].get("custody_replication", 4)
    xs = [i / 20 for i in range(17)]
    ax.plot(xs, [p ** rep for p in xs], ls="--", lw=1.6, color="#c1442e",
            label=f"$p^{{{rep}}}$ prediction (custody replication {rep})")
    ax.set_xlabel("fraction of peers refusing to serve")
    ax.set_ylabel("cells missing at the deadline")
    ax.set_title("Custody replication turns withholding into a much smaller\n"
                 "erasure rate — and the code carried makes no difference",
                 fontsize=11)
    cfg = runA["config"]
    _subtitle(ax, f"{cfg['n_peers']} peers, custody replication "
                  f"{cfg.get('custody_replication', 4)}, "
                  f"{runA['rows'][0]['trials']} trials per point; a cell is "
                  f"lost only if every custodian withholds it")
    ax.xaxis.set_major_formatter(FuncFormatter(_pct))
    ax.yaxis.set_major_formatter(FuncFormatter(_pct))
    ax.legend(loc="upper left")
    return _save(fig, "net_erasure_vs_adversarial.svg")


def fig_net_recovery(runA):
    fig, ax = plt.subplots(figsize=(FIGW, 3.9))
    rows = runA["rows"]
    series = []
    for s in ORDER:
        sub = sorted((r for r in rows if r["scheme"] == s),
                     key=lambda r: r["adversarial"])
        if not sub:
            continue
        xs = [r["adversarial"] for r in sub]
        ys = [r["recovered"] / r["trials"] for r in sub]
        ax.plot(xs, ys, marker="o", color=COLOURS[s])
        series.append((disp(s), xs, ys, COLOURS[s]))
    ax.set_xlabel("fraction of peers refusing to serve")
    ax.set_ylabel("trials recovered byte-exact")
    ax.set_title("Recovery against adversarial withholding")
    cfg = runA["config"]
    _subtitle(ax, f"{cfg['n_peers']} peers, replication "
                  f"{cfg.get('custody_replication', 4)}, "
                  f"{cfg.get('deadline_s', 4):.0f}s sampling deadline; "
                  "erasures are what failed to arrive, not injected")
    ax.xaxis.set_major_formatter(FuncFormatter(_pct))
    ax.yaxis.set_major_formatter(FuncFormatter(_pct))
    ax.set_ylim(-0.08, 1.08)
    _label_ends(ax, series)
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
    fig, ax = plt.subplots(figsize=(FIGW, 4.0))
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
    ax.set_xticklabels([disp(x) for x in schemes], rotation=25, ha="right", fontsize=8)
    ax.set_ylabel("seconds per slot")
    cfg = runB["config"]
    ax.set_title("Decode dominates gather by orders of magnitude")
    _subtitle(ax, f"{cfg.get('blobs_per_slot', 6)} blobs per slot, "
                  f"{cfg.get('downlink_mbps', 25):.0f} Mbps downlink, no "
                  f"adversaries; gather is network time, decode is CPU")
    _readable_log(ax)
    ax.legend()
    return _save(fig, "net_gather_vs_decode.svg")


def fig_net_throughput(runB):
    """Blobs actually reconstructed per slot, against withholding.

    The ordering here inverts the coding benchmark's tolerance ordering:
    the scheme that survives the most erasure rebuilds the fewest blobs,
    because its decode is too slow to fit the slot."""
    rows = runB["rows"]
    target = runB["config"].get("blobs_per_slot", 6)
    fig, ax = plt.subplots(figsize=(FIGW, 3.9))
    series = []
    for s_ in ORDER:
        sub = sorted((r for r in rows if r["scheme"] == s_),
                     key=lambda r: r["adversarial"])
        if not sub:
            continue
        xs = [r["adversarial"] for r in sub]
        ys = [r["blobs_per_slot"] for r in sub]
        ax.plot(xs, ys, marker="o", color=COLOURS[s_])
        series.append((disp(s_), xs, ys, COLOURS[s_]))
    ax.axhline(target, color="#444", ls="--", lw=1.1)
    # Labelled on the line: the legend that used to carry this was removed in
    # favour of naming each curve at its end.
    ax.annotate(f"blobs attempted ({target:.0f})", xy=(0.0, target),
                xytext=(2, 4), textcoords="offset points",
                fontsize=8.5, color="#444")
    ax.set_xlabel("fraction of peers withholding")
    ax.set_ylabel("blobs reconstructed per slot")
    ax.set_title("Throughput inverts the tolerance ordering")
    ax.xaxis.set_major_formatter(FuncFormatter(_pct))
    _label_ends(ax, series)
    return _save(fig, "net_throughput.svg")


def fig_net_peers(runC):
    """Realised erasure against peer count, at two withholding levels.

    The two schemes coincide exactly at each level -- as they must, since
    the erasure rate is a property of the network rather than the code -- so
    a four-entry legend would describe two visible curves. Each withholding
    level is drawn as one band and named beside it, leaving the legend to
    carry only the computed prediction."""
    from math import comb
    rows = runC["rows"]
    rep = runC["config"].get("custody_replication", 4)
    peers = sorted({r["peers"] for r in rows})
    levels = sorted({r["adversarial"] for r in rows})
    shade = {levels[0]: "#9dc3e6", levels[-1]: "#1f4e79"}

    fig, ax = plt.subplots(figsize=(FIGW, 4.0))
    for adv in levels:
        col = shade.get(adv, "#2e75b6")
        for sc in sorted({r["scheme"] for r in rows}):
            sub = sorted((r for r in rows
                          if r["scheme"] == sc and r["adversarial"] == adv),
                         key=lambda r: r["peers"])
            if sub:
                ax.plot([r["peers"] for r in sub],
                        [r["mean_erasure_fraction"] for r in sub],
                        marker="o", lw=1.6, color=col, alpha=0.85)
        hyp = [comb(round(adv * n), rep) / comb(n, rep) if n >= rep else 0.0
               for n in peers]
        ax.plot(peers, hyp, ls="none", marker="o", ms=9, mfc="none",
                mec="#333", mew=1.1,
                label="exact hypergeometric (computed, not fitted)"
                      if adv == levels[0] else None)
        ax.axhline(adv ** rep, color=col, lw=1.0, ls=":")
        # Name the band beside its own curve rather than in a legend.
        ax.annotate(f"{100 * adv:.0f}% of peers withholding\n"
                    f"$p^{{{rep}}}$ limit {adv ** rep:.3f}",
                    xy=(peers[-1], hyp[-1]), xytext=(9, 0),
                    textcoords="offset points", va="center",
                    fontsize=8.5, color=col)
    ax.set_xscale("log", base=2)
    ax.set_xlim(peers[0] * 0.85, peers[-1] * 3.6)
    ax.set_xlabel("peers in the sampled network")
    ax.set_ylabel("cells missing at the deadline")
    ax.set_title("Realised erasure rises with peer count, then plateaus")
    _subtitle(ax, f"custody replication {rep}, drawn without replacement; "
                  "markers are the exact probability that all custodians "
                  "of a cell withhold")
    ax.yaxis.set_major_formatter(FuncFormatter(_pct))
    # Below the axes: inside, it landed on the marker row it describes.
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.20))
    return _save(fig, "net_peers.svg")


# --------------------------------------------------------------------- main
GROUPS = {
    "bench": ("benchmark_results.json",
              [fig_success_curves, fig_tolerance_vs_guarantee,
               fig_bc_threshold_prediction, fig_decode_time,
               fig_data_needed, fig_tolerance_vs_cost, fig_encode_decode,
               fig_cost_per_erasure, fig_decode_vs_erasure_count]),
    "fix":   ("decoder_fix_results.json", [fig_decoder_fix]),
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
