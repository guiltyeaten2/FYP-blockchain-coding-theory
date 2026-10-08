# Figures for the written report

Folders follow the order the report presents things: the coding benchmark first, then the network simulation.

Each figure comes as `.svg` for LaTeX or print and `.png` at 300 dpi for Word and Google Docs. Numbering restarts inside each folder.

Regenerate with `python3 make_report_figures.py`.

## `01-benchmark/` — The coding benchmark

Seven schemes over the same blob, same erasure positions, at matched storage cost. This is the first results chapter.

* **01-fault-tolerance** — Every scheme holds at 100% then collapses within a few percent, which is what makes a single threshold a fair summary. The three lambda=2 rows land at 0.340, 0.341 and 0.350 despite mu ranging 2 to 8 and omega 512 to 2048 - a factor of four in block size moving the threshold by nothing.
* **02-fault-tolerance-compact** — The three lambda=2 rows cluster at 0.340, 0.341 and 0.350 across a factor of four in block size. The bar width also shows what a bare threshold hides: lambda=4 collapses over a much wider range of erasure rates than the lambda=2 rows do.
* **03-bc-threshold-vs-theory** — Reach is set by lambda alone. Predicted 0.333/0.250/0.200 for lambda = 2/3/4 against measured 0.34/0.28/0.21. Theory and experiment agree at every point, and mu and omega do not enter.
* **04-tolerance-vs-guarantee** — 1D-RS sits on its bound (0.505 against 0.500), which is what being MDS means and a useful check that the harness is sound. 2D-RS reaches 0.397 against a guarantee of 0.098 - four times its own bound.
* **05-decode-cost** — 1D-RS is the most expensive at every rate, three to five times the dearest block-circulant row, because it divides one 8192-length polynomial while the others divide short ones. Against 2D-RS the picture is mixed: below about 8% every BC row is cheaper, above it only the two smallest stay below.
* **06-cost-per-erasure** — 1D-RS is flat at 10-13 ms per erasure - one long division's worth of work each. The BC rows sit at 1-3.5 ms and rise gently. 2D-RS falls steeply from 8 ms to 1 ms, revealing a large fixed cost, which is exactly why it looks expensive at 2% erasure and cheap at 30%.
* **07-encode-vs-decode** — The two families sit on opposite sides of the asymmetry. 1D-RS encodes in 0.23 s then costs 20 s to decode; BC omega2048 lambda2 spends 15.7 s encoding in order to decode in 5.5 s.
* **08-pareto-tolerance-vs-cost** — Only three of seven are on the frontier. BC omega512 lambda2 is the cheapest thing still surviving a third of the codeword; 2D-RS buys about five more points of tolerance for roughly double the decode; 1D-RS buys the maximum and pays an order of magnitude. BC omega1024 lambda4 is dominated on both axes by omega512 lambda2, so the tolerance it gives up buys nothing.
* **09-data-needed-per-blob** — 1D-RS needs essentially the floor at 0.99x. Everything else needs 1.24x to 1.58x. A scheme tolerating a lower erasure rate at the same storage cost necessarily needs more.

## `02-network-sim/` — The network simulation

The same schemes inside a simulated peer-to-peer network, where the erasure pattern is an output rather than an input. This follows the benchmark.

* **01-erasure-vs-adversaries** — A cell is lost only if all four of its custodians withhold, so the erasure the code sees is roughly the fourth power of the bad-peer fraction: 50% of the network withholding yields about 5.6% erasure. Every scheme gives the identical curve, because this is a property of the network and custody, not the code.
* **02-recovery-vs-adversaries** — They fail in exactly the order the coding benchmark predicted, and at the withholding rates that produce their measured thresholds. BC omega1024 lambda4 breaks first (8/30 at 70% withholding, which yields 0.233 erasure against its 0.210 threshold); 1D-RS is still at 30/30 when 80% of peers refuse.
* **03-latency-gather-time** — Yes - it costs time. A peer that never answers cannot be routed around for free: the client burns its request timeout before falling back to another custodian. Gather climbs from 0.14 s to 3.22 s for 1D-RS across the sweep. The scheme needing the most cells hits the deadline first, omega1024 lambda4 at 50% withholding against 1D-RS at 80%.
* **04-bandwidth-fetched** — 1D-RS pulls least at 1.04 MiB and BC omega1024 lambda4 most at 1.54 MiB - the same ordering benchmark figure 08 computes from code parameters, arrived at by completely independent means.
* **05-throughput-blobs-per-slot** — The ordering inverts the tolerance ordering. 1D-RS tolerates the most erasure of any scheme and reconstructs the fewest blobs, about 0.2 of the six, because one 8192-length polynomial division costs roughly 59 s per blob. The three cheapest BC rows keep up with all six until 20% withholding.
* **06-time-budget-vs-slot** — At zero adversaries only BC omega1024 lambda3 (6.4 s) and lambda4 (1.3 s) finish inside a slot. Past about 20% withholding nothing does. 1D-RS is not close at any setting - 354 s, roughly thirty slots of work for one slot of data.
* **07-gather-vs-decode** — Every scheme gathers in about one second. Decode spans three orders of magnitude above that, from effectively zero to 354 s. At every setting tried, arithmetic rather than bandwidth or latency decides the outcome.
* **08-scalability-peer-count** — Growing the network makes things slightly worse, up to a limit. Custodians are drawn without replacement, so in a small network it is combinatorially hard for all four to be adversarial - with 8 peers only 5 are bad. As the network grows that constraint relaxes and loss climbs toward p^4 = 0.130. Measurement sits on the computed prediction throughout.

## `03-methodology/` — Methodology and validation

Referenced from the method chapter rather than the results.

* **01-decoder-correctness-fix** — Before the fix the decoder claimed success on all 40 trials and was wrong on 31 of them; it never once reported a failure. After, silent corruption is zero and correct recoveries rose from 9 to 16 - the old decoder had been poisoning positions with fabricated zeros that blocked later rounds from resolving them.

## Deliberately not included

These exist in `docs/figures/` and were left out on purpose:

* `fft_vs_vandermonde` — NTT path; belongs in an implementation appendix, not the empirical results
* `fft_profile` — same
* `fft_node_width` — same
* `fft_grs_premise` — same
* `rs_decode_vs_erasure_count` — 1D vs 2D only; figure 4 covers it across all seven schemes
