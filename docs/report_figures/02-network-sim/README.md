# The network simulation

The same schemes inside a simulated peer-to-peer network, where the erasure pattern is an output rather than an input. This follows the benchmark.

## 01-erasure-vs-adversaries

*Goes in: Results — network layer: fault tolerance*

**Question.** When peers withhold data, what erasure rate does the code actually end up facing?

**Data.** SimPy simulation, 64 peers, custody replication 4, one blob per slot at 50 Mbps, 4 s deadline, 30 trials per point, withholding swept 0 to 80%. docs/runA.json.

**Shows.** A cell is lost only if all four of its custodians withhold, so the erasure the code sees is roughly the fourth power of the bad-peer fraction: 50% of the network withholding yields about 5.6% erasure. Every scheme gives the identical curve, because this is a property of the network and custody, not the code.

## 02-recovery-vs-adversaries

*Goes in: Results — network layer: fault tolerance*

**Question.** Do the schemes fail in the same order when losses come from peer behaviour rather than an injected erasure rate?

**Data.** Same run. No erasure rate is injected here - losses are whatever failed to arrive before the 4 s deadline.

**Shows.** They fail in exactly the order the coding benchmark predicted, and at the withholding rates that produce their measured thresholds. BC omega1024 lambda4 breaks first (8/30 at 70% withholding, which yields 0.233 erasure against its 0.210 threshold); 1D-RS is still at 30/30 when 80% of peers refuse.

## 03-latency-gather-time

*Goes in: Results — network layer: latency*

**Question.** Does withholding cost the victim anything beyond the data itself?

**Data.** Same run. Gather time is network time only, excluding decode.

**Shows.** Yes - it costs time. A peer that never answers cannot be routed around for free: the client burns its request timeout before falling back to another custodian. Gather climbs from 0.14 s to 3.22 s for 1D-RS across the sweep. The scheme needing the most cells hits the deadline first, omega1024 lambda4 at 50% withholding against 1D-RS at 80%.

## 04-bandwidth-fetched

*Goes in: Results — network layer: bandwidth*

**Question.** How much data does a node actually pull over the wire, as opposed to how much the code theoretically needs?

**Data.** SimPy, 64 peers, replication 4, six blobs per slot at 25 Mbps - the bandwidth-pressure configuration. 30 trials per point. docs/runB.json.

**Shows.** 1D-RS pulls least at 1.04 MiB and BC omega1024 lambda4 most at 1.54 MiB - the same ordering benchmark figure 08 computes from code parameters, arrived at by completely independent means.

## 05-throughput-blobs-per-slot

*Goes in: Results — network layer: throughput*

**Question.** How many blobs can a node actually rebuild within one slot?

**Data.** Same six-blob run. Throughput implied by the measured time - blobs attempted, scaled by recovery rate and by whether the total fits the slot - not an independently measured rate.

**Shows.** The ordering inverts the tolerance ordering. 1D-RS tolerates the most erasure of any scheme and reconstructs the fewest blobs, about 0.2 of the six, because one 8192-length polynomial division costs roughly 59 s per blob. The three cheapest BC rows keep up with all six until 20% withholding.

## 06-time-budget-vs-slot

*Goes in: Discussion — can any of this keep up?*

**Question.** Does the whole job - fetch plus rebuild - fit inside an Ethereum slot?

**Data.** Same six-blob run. Gather plus decode summed per slot.

**Shows.** At zero adversaries only BC omega1024 lambda3 (6.4 s) and lambda4 (1.3 s) finish inside a slot. Past about 20% withholding nothing does. 1D-RS is not close at any setting - 354 s, roughly thirty slots of work for one slot of data.

## 07-gather-vs-decode

*Goes in: Discussion — the real bottleneck*

**Question.** Of the time a node spends, how much is network and how much is arithmetic?

**Data.** Same six-blob run, at zero adversaries so neither side is inflated by timeouts.

**Shows.** Every scheme gathers in about one second. Decode spans three orders of magnitude above that, from effectively zero to 354 s. At every setting tried, arithmetic rather than bandwidth or latency decides the outcome.

## 08-scalability-peer-count

*Goes in: Results — network layer: scalability*

**Question.** What happens to data availability as the network grows?

**Data.** SimPy peer sweep, 8 to 256 peers, replication fixed at 4, one blob at 50 Mbps, 30 trials per point, at 30% and 60% withholding. docs/runC.json.

**Shows.** Growing the network makes things slightly worse, up to a limit. Custodians are drawn without replacement, so in a small network it is combinatorially hard for all four to be adversarial - with 8 peers only 5 are bad. As the network grows that constraint relaxes and loss climbs toward p^4 = 0.130. Measurement sits on the computed prediction throughout.

