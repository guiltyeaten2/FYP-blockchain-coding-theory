# Figures for the written report

Folders follow the order the report presents things: the coding benchmark first, then the network simulation.

Each figure comes as `.svg` for LaTeX or print and `.png` at 300 dpi for Word and Google Docs. Numbering restarts inside each folder.

Regenerate with `python3 make_report_figures.py`.

## `01-benchmark/` — The coding benchmark

Seven schemes over the same blob, same erasure positions, at matched storage cost. This is the first results chapter.

* **01-fault-tolerance** — Every scheme holds at 100% then collapses within a few percent, which is what makes a single threshold a fair summary. 1D-RS sits on its exact MDS curve, at 0.499. The three lambda=2 rows land within 0.013 of each other (0.336, 0.342, 0.349), far closer to one another than to lambda=3 (0.255) or lambda=4 (0.204): lambda sets the reach. Their intervals do not overlap, though, and they rise with mu - so mu has a small, real effect.
* **02-fault-tolerance-compact** — 1D-RS reaches 0.499, against the exact 0.50006 an MDS code with n = 2k can sustain. The three lambda=2 rows sit within 0.013 of each other (0.336, 0.342, 0.349) while lambda=3 and lambda=4 fall to 0.255 and 0.204. Intervals are +/-0.003 or narrower, so every difference shown is resolved.
* **03-bc-threshold-vs-theory** — Lambda sets the reach. Predicted 0.333/0.250/0.200 for lambda = 2/3/4 against measured 0.336-0.349, 0.255 and 0.204. Every measurement sits just above its prediction, as it should: the local stopping rate is what one block can repair alone, and the cascade across blocks can only add to it. At fixed lambda=2 the threshold also rises with mu (0.336, 0.342, 0.349 for mu = 2, 4, 8) - more blocks give that cascade more to work with.
* **04-tolerance-vs-guarantee** — 1D-RS sits on its bound at 0.499, which is what being MDS means and a useful check that the harness is sound. 2D-RS reaches 0.400 against a guarantee of 0.098 - four times its own bound.
* **05-decode-cost** — 1D-RS is the most expensive at every rate, three to five times the dearest block-circulant row, because it divides one 8192-length polynomial while the others divide short ones. Against 2D-RS the picture is mixed: below about 7% every BC row is cheaper; above it they cross one by one, and only omega512 lambda2 and omega1024 lambda4 stay at or below it.
* **06-cost-per-erasure** — 1D-RS sits near 11-13 ms per erasure (16 ms at 2%, easing to 10.5 ms near its threshold) - one long division's worth of work each. The BC rows sit at 0.85-3.7 ms and rise gently. 2D-RS falls steeply from 8 ms to 1 ms, revealing a large fixed cost, which is exactly why it looks expensive at 2% erasure and cheap at 30%.
* **07-encode-vs-decode** — The two families sit on opposite sides of the asymmetry. 1D-RS encodes in 0.23 s then costs 21 s to decode; BC omega2048 lambda2 spends 15.8 s encoding in order to decode in 5.8 s.
* **08-pareto-tolerance-vs-cost** — Only three of seven are on the frontier. BC omega512 lambda2 is the cheapest thing still surviving a third of the codeword; 2D-RS buys about five more points of tolerance for about 60% more decode time; 1D-RS buys the maximum and pays an order of magnitude. BC omega1024 lambda4 is dominated on both axes by omega512 lambda2, so the tolerance it gives up buys nothing.
* **09-data-needed-per-blob** — 1D-RS needs essentially the floor, 1.00x. Everything else needs 1.24x to 1.59x. A scheme tolerating a lower erasure rate at the same storage cost necessarily needs more.

## `02-network-sim/` — The network simulation

The same schemes inside a simulated peer-to-peer network, where the erasure pattern is an output rather than an input. This follows the benchmark.

* **01-erasure-vs-adversaries** — A cell is lost only if all four of its custodians withhold, so the erasure the code sees is roughly the fourth power of the bad-peer fraction: 50% of the network withholding yields about 5.6% erasure. Every scheme gives the same curve - 2D-RS, with 132 cells rather than 128, differs only in the fourth decimal - because this is a property of the network and custody, not the code.
* **02-recovery-vs-adversaries** — BC omega1024 lambda4 breaks first (17/30 at 70% withholding, erasure 0.233), with omega1024 lambda3 close behind (28/30). At 80% (erasure 0.400) the lambda2 rows outlast 2D-RS - omega1024 lambda2 18/30 and omega512 lambda2 14/30 against 2D-RS's 7/30 - the reverse of the coding benchmark's order. 1D-RS recovers every trial.
* **03-latency-gather-time** — Yes - it costs time. A peer that never answers cannot be routed around for free: the client burns its request timeout before falling back to another custodian. Gather climbs from 0.14 s to 2.76 s for 1D-RS across the sweep. The scheme needing the most cells hits the deadline first - omega1024 lambda4, at 60% withholding - while 1D-RS never reaches it.
* **04-bandwidth-fetched** — 1D-RS pulls least at 1.02 MiB and BC omega1024 lambda4 most at 1.54 MiB, the whole codeword. The ordering matches benchmark figure 09 by construction - the download target is set from the same measured tolerance - and what this figure adds is the real overhead on top: the over-request margin, requests already in flight, and re-requests after timeouts.
* **05-throughput-blobs-per-slot** — Tolerance does not buy throughput. 1D-RS tolerates the most erasure of any scheme and reconstructs the fewest blobs, about 0.5 of the six, because one 8192-length polynomial division costs about 23 s per blob. 2D-RS, omega512 lambda2, omega1024 lambda3 and lambda4 keep up with all six until 20% withholding; at zero withholding omega1024 lambda2 manages 5.3 and omega2048 lambda2, the slowest block-circulant decode, 2.8.
* **06-time-budget-vs-slot** — At zero adversaries 2D-RS (9.3 s), BC omega512 lambda2 (8.0 s), omega1024 lambda3 (5.8 s) and lambda4 (1.2 s) finish inside a slot, with omega1024 lambda2 just over at 13.6 s. By 40% withholding only lambda4 still averages under 12 s (11.7 s), and it recovers in only 21 of 30 trials. 1D-RS is not close at any setting - 140 s, roughly twelve slots of work for one slot of data.
* **07-gather-vs-decode** — Every scheme gathers in about one second. Decode runs from effectively zero - omega1024 lambda4, which ends up holding the whole codeword - to 140 s for 1D-RS. Apart from that one scheme, arithmetic rather than bandwidth or latency decides the outcome.
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
* `rs_decode_vs_erasure_count` — 1D vs 2D only; figure 05 covers it across all seven schemes
