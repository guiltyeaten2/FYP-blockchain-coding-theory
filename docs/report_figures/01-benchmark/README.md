# The coding benchmark

Seven schemes over the same blob, same erasure positions, at matched storage cost. This is the first results chapter.

## 01-fault-tolerance

*Goes in: Results — fault tolerance*

**Question.** How much of the codeword can each scheme lose and still rebuild the blob exactly?

**Data.** The erasure sweep: one run over one real EIP-4844 blob, covering 2% to 55% erasure, with dense trials on a fine grid across each scheme's own transition band (benchmark_results.json).

**Shows.** Every scheme holds at 100% then collapses within a few percent, which is what makes a single threshold a fair summary. 1D-RS sits on its exact MDS curve, at 0.499. The three lambda=2 rows land within 0.013 of each other (0.336, 0.342, 0.349), far closer to one another than to lambda=3 (0.255) or lambda=4 (0.204): lambda sets the reach. Their intervals do not overlap, though, and they rise with mu - so mu has a small, real effect.

## 02-fault-tolerance-compact

*Goes in: Results — fault tolerance (space-saving alternative to 01)*

**Question.** Where does each scheme fall over, and how close together are those points?

**Data.** The erasure sweep's dense trials across each scheme's transition band, 12-20 per rate (benchmark_results.json).

**Shows.** 1D-RS reaches 0.499, against the exact 0.50006 an MDS code with n = 2k can sustain. The three lambda=2 rows sit within 0.013 of each other (0.336, 0.342, 0.349) while lambda=3 and lambda=4 fall to 0.255 and 0.204. Intervals are +/-0.003 or narrower, so every difference shown is resolved.

## 03-bc-threshold-vs-theory

*Goes in: Results — fault tolerance*

**Question.** Does the block-circulant decoder behave as the source paper predicts?

**Data.** Thresholds from the erasure sweep, with 95% intervals; the prediction is the local code's stopping rate from Sasidharan, Viterbo & Feist (ePrint 2026/708).

**Shows.** Lambda sets the reach. Predicted 0.333/0.250/0.200 for lambda = 2/3/4 against measured 0.336-0.349, 0.255 and 0.204. Every measurement sits just above its prediction, as it should: the local stopping rate is what one block can repair alone, and the cascade across blocks can only add to it. At fixed lambda=2 the threshold also rises with mu (0.336, 0.342, 0.349 for mu = 2, 4, 8) - more blocks give that cascade more to work with.

## 04-tolerance-vs-guarantee

*Goes in: Discussion — guarantees versus behaviour*

**Question.** How does what each code actually tolerated compare with what its minimum distance guarantees?

**Data.** Same sweep for the measured bars; guarantees computed from each code's d_min, and the rate bound from 1 - R.

**Shows.** 1D-RS sits on its bound at 0.499, which is what being MDS means and a useful check that the harness is sound. 2D-RS reaches 0.400 against a guarantee of 0.098 - four times its own bound.

## 05-decode-cost

*Goes in: Results — computational cost*

**Question.** What does each scheme cost to decode, and how does that grow with damage?

**Data.** Same sweep. Mean over the trials that actually recovered; failed trials are excluded because a scheme above its threshold rejects the pattern on a budget check in under a millisecond, which is not a decode time.

**Shows.** 1D-RS is the most expensive at every rate, three to five times the dearest block-circulant row, because it divides one 8192-length polynomial while the others divide short ones. Against 2D-RS the picture is mixed: below about 7% every BC row is cheaper; above it they cross one by one, and only omega512 lambda2 and omega1024 lambda4 stay at or below it.

## 06-cost-per-erasure

*Goes in: Discussion — why the costs differ*

**Question.** Is one scheme dearer because it does more work per repair, or because it carries a fixed overhead?

**Data.** The same decode times divided by the number of symbols actually erased in that trial.

**Shows.** 1D-RS sits near 11-13 ms per erasure (16 ms at 2%, easing to 10.5 ms near its threshold) - one long division's worth of work each. The BC rows sit at 0.85-3.7 ms and rise gently. 2D-RS falls steeply from 8 ms to 1 ms, revealing a large fixed cost, which is exactly why it looks expensive at 2% erasure and cheap at 30%.

## 07-encode-vs-decode

*Goes in: Discussion — asymmetry*

**Question.** Encoding and decoding are not paid by the same party. How do the schemes differ on each?

**Data.** Encode time measured once per scheme on the shared blob; decode at the highest rate every scheme still recovers.

**Shows.** The two families sit on opposite sides of the asymmetry. 1D-RS encodes in 0.23 s then costs 21 s to decode; BC omega2048 lambda2 spends 15.8 s encoding in order to decode in 5.8 s.

## 08-pareto-tolerance-vs-cost

*Goes in: Discussion — the trade-off*

**Question.** Which schemes are actually worth considering once tolerance and cost are weighed together?

**Data.** Thresholds and decode times from the same sweep, at the highest rate every scheme reached.

**Shows.** Only three of seven are on the frontier. BC omega512 lambda2 is the cheapest thing still surviving a third of the codeword; 2D-RS buys about five more points of tolerance for about 60% more decode time; 1D-RS buys the maximum and pays an order of magnitude. BC omega1024 lambda4 is dominated on both axes by omega512 lambda2, so the tolerance it gives up buys nothing.

## 09-data-needed-per-blob

*Goes in: Results — bandwidth*

**Question.** How much surviving data must a node obtain to rebuild one blob?

**Data.** Derived from each scheme's measured threshold as n(1-threshold)/k, expressed as a multiple of one blob.

**Shows.** 1D-RS needs essentially the floor, 1.00x. Everything else needs 1.24x to 1.59x. A scheme tolerating a lower erasure rate at the same storage cost necessarily needs more.

