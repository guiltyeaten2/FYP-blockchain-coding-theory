# The network simulation

The same schemes inside a simulated peer-to-peer network, where the erasure pattern is an output rather than an input. This follows the benchmark.

## 01-erasure-vs-adversaries

*Goes in: Results — network layer: fault tolerance*

Custody replication turns withholding into a much smaller erasure rate (roughly p^4), and all six schemes produce the same curve because this is a property of the network, not the code.

## 02-recovery-vs-adversaries

*Goes in: Results — network layer: fault tolerance*

Recovery against adversarial withholding. The schemes fail in the same order the coding benchmark predicted, through a completely different mechanism — the strongest cross-validation in the project.

## 03-latency-gather-time

*Goes in: Results — network layer: latency*

Gather time against adversarial fraction. Withholding costs the victim time as well as data, because the client burns its request timeout before falling back to another custodian. Covers the brief's 'packet propagation latency'.

## 04-bandwidth-fetched

*Goes in: Results — network layer: bandwidth*

Data actually pulled over the wire per slot. Measured rather than derived from code parameters, and it cross-validates the benchmark's surviving-data figure: 1D-RS fetches least, BC w1024 l4 most.

## 05-throughput-blobs-per-slot

*Goes in: Results — network layer: throughput*

Blobs reconstructed per slot out of six. The ordering inverts the tolerance ordering: the scheme that survives the most erasure rebuilds the fewest blobs. Covers the brief's 'block processing throughput'.

## 06-time-budget-vs-slot

*Goes in: Discussion — can any of this keep up?*

Gather plus decode against the 4s sampling deadline and the 12s slot. Only the two cheapest block-circulant rows fit at zero adversaries, and nothing fits once withholding passes 20%.

## 07-gather-vs-decode

*Goes in: Discussion — the real bottleneck*

Gather takes about a second for every scheme; decode spans three orders of magnitude above it. The bottleneck is arithmetic, not bandwidth.

## 08-scalability-peer-count

*Goes in: Results — network layer: scalability*

Realised erasure against network size, with the exact hypergeometric prediction computed rather than fitted. What protects a cell is the fraction of the network custodying it.

