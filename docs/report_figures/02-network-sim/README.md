# The network simulation

The same schemes inside a simulated peer-to-peer network, where the erasure pattern is an output rather than an input. This follows the benchmark.

## 01-erasure-vs-adversaries

*Goes in: Results — network layer: fault tolerance*

**Question.** When peers withhold data, what erasure rate does the code actually end up facing?

**Data.** SimPy simulation, 64 peers, custody replication 4, one blob per slot at 50 Mbps, 4 s deadline, 30 trials per point, withholding swept 0 to 80%. docs/runA.json.

**Shows.** A cell is lost only if all four of its custodians withhold, so the erasure the code sees is roughly the fourth power of the bad-peer fraction: 50% of the network withholding yields about 5.6% erasure. Every scheme gives the same curve - 2D-RS, with 132 cells rather than 128, differs only in the fourth decimal - because this is a property of the network and custody, not the code.

## 02-recovery-vs-adversaries

*Goes in: Results — network layer: fault tolerance*

**Question.** At what level of peer withholding does each scheme stop recovering the blob?

**Data.** Same run. No erasure rate is injected here - losses are whatever failed to arrive before the 4 s deadline. Whether a realised erasure is survivable is read from the coding benchmark's measured recovery curve (calibrated mode).

**Shows.** BC omega1024 lambda4 breaks first (5/30 at 70% withholding, which yields 0.233 erasure against its 0.204 threshold), with omega1024 lambda3 close behind (21/30). 2D-RS and the lambda2 rows hold until 80%, where erasure reaches 0.400; 1D-RS is still at 30/30 when 80% of peers refuse.

## 03-latency-gather-time

*Goes in: Results — network layer: latency*

**Question.** Does withholding cost the victim anything beyond the data itself?

**Data.** Same run. Gather time is network time only, excluding decode.

**Shows.** Yes - it costs time. A peer that never answers cannot be routed around for free: the client burns its request timeout before falling back to another custodian. Gather climbs from 0.14 s to 2.76 s for 1D-RS across the sweep. The scheme needing the most cells hits the deadline first - omega1024 lambda4, at 60% withholding - while 1D-RS never reaches it.

## 04-bandwidth-fetched

*Goes in: Results — network layer: bandwidth*

**Question.** How much data does a node actually pull over the wire, as opposed to how much the code theoretically needs?

**Data.** SimPy, 64 peers, replication 4, six blobs per slot at 25 Mbps - the bandwidth-pressure configuration. 30 trials per point. docs/runB.json.

**Shows.** 1D-RS pulls least at 1.02 MiB and BC omega1024 lambda4 most at 1.54 MiB, the whole codeword. The ordering matches benchmark figure 09 by construction - the download target is set from the same measured tolerance - and what this figure adds is the real overhead on top: the over-request margin, requests already in flight, and re-requests after timeouts.

## 05-throughput-blobs-per-slot

*Goes in: Results — network layer: throughput*

**Question.** How many blobs can a node actually rebuild within one slot?

**Data.** Same six-blob run. Throughput implied by the measured time - blobs attempted, scaled by recovery rate and by the share of the work that fits in the 12 s slot - not an independently measured rate.

**Shows.** The ordering broadly inverts the tolerance ordering. 1D-RS tolerates the most erasure of any scheme and reconstructs the fewest blobs, about 0.4 of the six, because one 8192-length polynomial division costs about 31 s per blob. BC omega1024 lambda3 and lambda4 keep up with all six until 20% withholding, and so does omega512 lambda2; at zero withholding omega1024 lambda2 manages 5.3, 2D-RS 4.3 and omega2048 lambda2 2.8. Two rows break a clean inversion: omega2048 lambda2, whose large blocks are slow to decode, and omega512 lambda2, which keeps up with all six while being the most tolerant block-circulant row.

## 06-time-budget-vs-slot

*Goes in: Discussion — can any of this keep up?*

**Question.** Does the whole job - fetch plus rebuild - fit inside an Ethereum slot?

**Data.** Same six-blob run. Gather plus decode summed per slot.

**Shows.** At zero adversaries only BC omega512 lambda2 (7.8 s), omega1024 lambda3 (5.9 s) and lambda4 (1.2 s) finish inside a slot, with omega1024 lambda2 just over at 13.7 s. By 40% withholding only lambda4 still averages under 12 s, and it recovers in only 19 of 30 trials. 1D-RS is not close at any setting - 187 s, roughly fifteen slots of work for one slot of data.

## 07-gather-vs-decode

*Goes in: Discussion — the real bottleneck*

**Question.** Of the time a node spends, how much is network and how much is arithmetic?

**Data.** Same six-blob run, at zero adversaries so neither side is inflated by timeouts.

**Shows.** Every scheme gathers in about one second. Decode runs from effectively zero - omega1024 lambda4, which ends up holding the whole codeword - to 186 s for 1D-RS. Apart from that one scheme, arithmetic rather than bandwidth or latency decides the outcome.

## 08-scalability-peer-count

*Goes in: Results — network layer: scalability*

**Question.** What happens to data availability as the network grows?

**Data.** SimPy peer sweep, 8 to 256 peers, replication fixed at 4, one blob at 50 Mbps, 30 trials per point, at 30% and 60% withholding. docs/runC.json.

**Shows.** Growing the network makes things slightly worse, up to a limit. Custodians are drawn without replacement, so in a small network it is combinatorially hard for all four to be adversarial - with 8 peers only 5 are bad. As the network grows that constraint relaxes and loss climbs toward p^4 = 0.130. Measurement sits on the computed prediction throughout.

