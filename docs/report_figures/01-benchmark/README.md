# The coding benchmark

Seven schemes over the same blob, same erasure positions, at matched storage cost. This is the first results chapter.

## 01-fault-tolerance

*Goes in: Results — fault tolerance*

**Question.** How much of the codeword can each scheme lose and still rebuild the blob exactly?

**Data.** The erasure sweep: 520 trials over one real EIP-4844 blob, 7 schemes x 18 erasure rates from 2% to 55%, fixed seed 20260827. benchmark_results.json.

**Shows.** Every scheme holds at 100% then collapses within a few percent, which is what makes a single threshold a fair summary. The three lambda=2 rows land at 0.340, 0.341 and 0.350 despite mu ranging 2 to 8 and omega 512 to 2048 - a factor of four in block size moving the threshold by nothing.

## 02-fault-tolerance-compact

*Goes in: Results — fault tolerance (space-saving alternative to 01)*

**Question.** Where does each scheme fall over, and how close together are those points?

**Data.** The same erasure sweep as figure 01: 520 trials, 7 schemes, 18 rates. benchmark_results.json.

**Shows.** The three lambda=2 rows cluster at 0.340, 0.341 and 0.350 across a factor of four in block size. The bar width also shows what a bare threshold hides: lambda=4 collapses over a much wider range of erasure rates than the lambda=2 rows do.

## 03-bc-threshold-vs-theory

*Goes in: Results — fault tolerance*

**Question.** Does the block-circulant decoder behave as the source paper predicts?

**Data.** Same sweep. Thresholds derived from the success curves; the prediction is the local code's stopping rate from Sasidharan, Viterbo & Feist (ePrint 2026/708).

**Shows.** Reach is set by lambda alone. Predicted 0.333/0.250/0.200 for lambda = 2/3/4 against measured 0.34/0.28/0.21. Theory and experiment agree at every point, and mu and omega do not enter.

## 04-tolerance-vs-guarantee

*Goes in: Discussion — guarantees versus behaviour*

**Question.** How does what each code actually tolerated compare with what its minimum distance guarantees?

**Data.** Same sweep for the measured bars; guarantees computed from each code's d_min, and the rate bound from 1 - R.

**Shows.** 1D-RS sits on its bound (0.505 against 0.500), which is what being MDS means and a useful check that the harness is sound. 2D-RS reaches 0.397 against a guarantee of 0.098 - four times its own bound.

## 05-decode-cost

*Goes in: Results — computational cost*

**Question.** What does each scheme cost to decode, and how does that grow with damage?

**Data.** Same sweep. Mean over the trials that actually recovered; failed trials are excluded because a scheme above its threshold rejects the pattern on a budget check in under a millisecond, which is not a decode time.

**Shows.** 1D-RS is the most expensive at every rate, three to five times the dearest block-circulant row, because it divides one 8192-length polynomial while the others divide short ones. Against 2D-RS the picture is mixed: below about 8% every BC row is cheaper, above it only the two smallest stay below.

## 06-cost-per-erasure

*Goes in: Discussion — why the costs differ*

**Question.** Is one scheme dearer because it does more work per repair, or because it carries a fixed overhead?

**Data.** The same decode times divided by the number of symbols actually erased in that trial.

**Shows.** 1D-RS is flat at 10-13 ms per erasure - one long division's worth of work each. The BC rows sit at 1-3.5 ms and rise gently. 2D-RS falls steeply from 8 ms to 1 ms, revealing a large fixed cost, which is exactly why it looks expensive at 2% erasure and cheap at 30%.

## 07-encode-vs-decode

*Goes in: Discussion — asymmetry*

**Question.** Encoding and decoding are not paid by the same party. How do the schemes differ on each?

**Data.** Encode time measured once per scheme on the shared blob; decode at the highest rate every scheme still recovers.

**Shows.** The two families sit on opposite sides of the asymmetry. 1D-RS encodes in 0.23 s then costs 20 s to decode; BC omega2048 lambda2 spends 15.7 s encoding in order to decode in 5.5 s.

## 08-pareto-tolerance-vs-cost

*Goes in: Discussion — the trade-off*

**Question.** Which schemes are actually worth considering once tolerance and cost are weighed together?

**Data.** Thresholds and decode times from the same sweep, at the highest rate every scheme reached.

**Shows.** Only three of seven are on the frontier. BC omega512 lambda2 is the cheapest thing still surviving a third of the codeword; 2D-RS buys about five more points of tolerance for roughly double the decode; 1D-RS buys the maximum and pays an order of magnitude. BC omega1024 lambda4 is dominated on both axes by omega512 lambda2, so the tolerance it gives up buys nothing.

## 09-data-needed-per-blob

*Goes in: Results — bandwidth*

**Question.** How much surviving data must a node obtain to rebuild one blob?

**Data.** Derived from each scheme's measured threshold as n(1-threshold)/k, expressed as a multiple of one blob.

**Shows.** 1D-RS needs essentially the floor at 0.99x. Everything else needs 1.24x to 1.58x. A scheme tolerating a lower erasure rate at the same storage cost necessarily needs more.

