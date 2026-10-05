# Figures for the written report

Each figure in two formats: `.svg` for LaTeX or print, `.png` at 300 dpi for Word and Google Docs.

Regenerate with `python3 make_report_figures.py`. Numbers are reading order, not importance — though if you only have room for one, use 07.


## Results — fault tolerance

**01. 01-fault-tolerance**

Every scheme holds at 100% then falls off a cliff, so one threshold number fairly summarises each. The three lambda=2 rows land within a hundredth of each other (0.340, 0.341, 0.350) across a factor of four in block size.

**02. 02-bc-threshold-vs-theory**

The block-circulant decoder's reach is set by lambda alone, and the measurements sit on the 1/(1+lambda) prediction at every point. This is the figure that shows theory and experiment agreeing.


## Discussion — guarantees versus behaviour

**03. 03-tolerance-vs-guarantee**

Measured tolerance against each code's own worst-case bound. 1D-RS sits on its bound because it is MDS; 2D-RS exceeds its own guarantee fourfold. Random erasure patterns are not adversarial ones.


## Results — computational cost

**04. 04-decode-cost**

Decode cost against erasure rate. 1D-RS is three to five times dearer than the dearest block-circulant row at every rate.


## Discussion — why the costs differ

**05. 05-cost-per-erasure**

The same data with the workload divided out. 1D-RS is flat, so its cost is linear in erasures; 2D-RS falls steeply, revealing a large fixed cost that amortises. This explains the shape of the previous figure.


## Discussion — asymmetry

**06. 06-encode-vs-decode**

Encode is paid once by the proposer, decode by every reconstructing node. 1D-RS and the block-circulant family sit on opposite sides of that asymmetry, which the tolerance numbers alone do not show.


## Discussion — the trade-off

**07. 07-pareto-tolerance-vs-cost**

The synthesis figure: tolerance against the cost of achieving it, with the Pareto frontier. Only three of seven schemes are on it. If the report has one summary figure, this is it.


## Results — bandwidth

**08. 08-data-needed-per-blob**

Surviving data each scheme needs to rebuild one blob. 1D-RS is at the theoretical floor; every other scheme needs more.


## Results — network layer

**09. 09-network-erasure-vs-adversaries**

Custody replication turns withholding into a much smaller erasure rate (roughly p^4), and all six schemes produce the same curve because this is a property of the network, not the code.

**10. 10-network-recovery**

Recovery against adversarial withholding. The schemes fail in the same order the coding benchmark predicted, through a completely different mechanism — the strongest cross-validation in the project.


## Discussion — the real bottleneck

**11. 11-gather-vs-decode**

Gather takes about a second for every scheme; decode spans three orders of magnitude above it and misses the slot deadline. The bottleneck is arithmetic, not bandwidth.


## Results — scalability

**12. 12-scalability-peer-count**

Realised erasure against network size, with the exact hypergeometric prediction computed rather than fitted. What protects a cell is the fraction of the network custodying it.


## Methodology — validation

**13. 13-decoder-correctness-fix**

Before and after the decoder correctness fix: silent corruptions fell from 31 of 40 to zero. Justifies verifying bytes rather than trusting the decoder's own success flag.


## Deliberately not included

These exist in `docs/figures/` and were left out on purpose:

* `fft_vs_vandermonde` — NTT path; belongs in an implementation appendix, not the empirical results
* `fft_profile` — same
* `fft_node_width` — same
* `fft_grs_premise` — same
* `net_throughput` — largely restates figure 10 through a different measure; include only if throughput is discussed
* `rs_decode_vs_erasure_count` — 1D vs 2D only; figure 4 covers it across all seven schemes
