# The coding benchmark

Seven schemes over the same blob, same erasure positions, at matched storage cost. This is the first results chapter.

## 01-fault-tolerance

*Goes in: Results — fault tolerance*

Every scheme holds at 100% then falls off a cliff, so one threshold number fairly summarises each. The three lambda=2 rows land within a hundredth of each other (0.340, 0.341, 0.350) across a factor of four in block size.

## 02-bc-threshold-vs-theory

*Goes in: Results — fault tolerance*

The block-circulant decoder's reach is set by lambda alone, and the measurements sit on the 1/(1+lambda) prediction at every point. This is the figure that shows theory and experiment agreeing.

## 03-tolerance-vs-guarantee

*Goes in: Discussion — guarantees versus behaviour*

Measured tolerance against each code's own worst-case bound. 1D-RS sits on its bound because it is MDS; 2D-RS exceeds its own guarantee fourfold. Random erasure patterns are not adversarial ones.

## 04-decode-cost

*Goes in: Results — computational cost*

Decode cost against erasure rate. 1D-RS is three to five times dearer than the dearest block-circulant row at every rate.

## 05-cost-per-erasure

*Goes in: Discussion — why the costs differ*

The same data with the workload divided out. 1D-RS is flat, so its cost is linear in erasures; 2D-RS falls steeply, revealing a large fixed cost that amortises. This explains the shape of the previous figure.

## 06-encode-vs-decode

*Goes in: Discussion — asymmetry*

Encode is paid once by the proposer, decode by every reconstructing node. 1D-RS and the block-circulant family sit on opposite sides of that asymmetry, which the tolerance numbers alone do not show.

## 07-pareto-tolerance-vs-cost

*Goes in: Discussion — the trade-off*

The synthesis figure: tolerance against the cost of achieving it, with the Pareto frontier. Only three of seven schemes are on it. If the report has one summary figure, this is it.

## 08-data-needed-per-blob

*Goes in: Results — bandwidth*

Surviving data each scheme needs to rebuild one blob. 1D-RS is at the theoretical floor; every other scheme needs more.

