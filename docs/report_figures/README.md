# Figures for the written report

Folders follow the order the report presents things: the coding benchmark first, then the network simulation.

Each figure comes as `.svg` for LaTeX or print and `.png` at 300 dpi for Word and Google Docs. Numbering restarts inside each folder.

Regenerate with `python3 make_report_figures.py`.

## `01-benchmark/` — The coding benchmark

Seven schemes over the same blob, same erasure positions, at matched storage cost. This is the first results chapter.

* **01-fault-tolerance** — Every scheme holds at 100% then falls off a cliff, so one threshold number fairly summarises each. The three lambda=2 rows land within a hundredth of each other (0.340, 0.341, 0.350) across a factor of four in block size.
* **02-bc-threshold-vs-theory** — The block-circulant decoder's reach is set by lambda alone, and the measurements sit on the 1/(1+lambda) prediction at every point. This is the figure that shows theory and experiment agreeing.
* **03-tolerance-vs-guarantee** — Measured tolerance against each code's own worst-case bound. 1D-RS sits on its bound because it is MDS; 2D-RS exceeds its own guarantee fourfold. Random erasure patterns are not adversarial ones.
* **04-decode-cost** — Decode cost against erasure rate. 1D-RS is three to five times dearer than the dearest block-circulant row at every rate.
* **05-cost-per-erasure** — The same data with the workload divided out. 1D-RS is flat, so its cost is linear in erasures; 2D-RS falls steeply, revealing a large fixed cost that amortises. This explains the shape of the previous figure.
* **06-encode-vs-decode** — Encode is paid once by the proposer, decode by every reconstructing node. 1D-RS and the block-circulant family sit on opposite sides of that asymmetry, which the tolerance numbers alone do not show.
* **07-pareto-tolerance-vs-cost** — The synthesis figure: tolerance against the cost of achieving it, with the Pareto frontier. Only three of seven schemes are on it. If the report has one summary figure, this is it.
* **08-data-needed-per-blob** — Surviving data each scheme needs to rebuild one blob. 1D-RS is at the theoretical floor; every other scheme needs more.

## `02-network-sim/` — The network simulation

The same schemes inside a simulated peer-to-peer network, where the erasure pattern is an output rather than an input. This follows the benchmark.

* **01-erasure-vs-adversaries** — Custody replication turns withholding into a much smaller erasure rate (roughly p^4), and all six schemes produce the same curve because this is a property of the network, not the code.
* **02-recovery-vs-adversaries** — Recovery against adversarial withholding. The schemes fail in the same order the coding benchmark predicted, through a completely different mechanism — the strongest cross-validation in the project.
* **03-gather-vs-decode** — Gather takes about a second for every scheme; decode spans three orders of magnitude above it and misses the slot deadline. The bottleneck is arithmetic, not bandwidth.
* **04-scalability-peer-count** — Realised erasure against network size, with the exact hypergeometric prediction computed rather than fitted. What protects a cell is the fraction of the network custodying it.

## `03-methodology/` — Methodology and validation

Referenced from the method chapter rather than the results.

* **01-decoder-correctness-fix** — Before and after the decoder correctness fix: silent corruptions fell from 31 of 40 to zero. Justifies verifying bytes rather than trusting the decoder's own success flag.

## Deliberately not included

These exist in `docs/figures/` and were left out on purpose:

* `fft_vs_vandermonde` — NTT path; belongs in an implementation appendix, not the empirical results
* `fft_profile` — same
* `fft_node_width` — same
* `fft_grs_premise` — same
* `net_throughput` — largely restates figure 10 through a different measure; include only if throughput is discussed
* `rs_decode_vs_erasure_count` — 1D vs 2D only; figure 4 covers it across all seven schemes
