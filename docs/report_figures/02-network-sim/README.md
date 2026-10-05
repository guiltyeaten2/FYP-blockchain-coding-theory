# The network simulation

The same schemes inside a simulated peer-to-peer network, where the erasure pattern is an output rather than an input. This follows the benchmark.

## 01-erasure-vs-adversaries

*Goes in: Results — network layer*

Custody replication turns withholding into a much smaller erasure rate (roughly p^4), and all six schemes produce the same curve because this is a property of the network, not the code.

## 02-recovery-vs-adversaries

*Goes in: Results — network layer*

Recovery against adversarial withholding. The schemes fail in the same order the coding benchmark predicted, through a completely different mechanism — the strongest cross-validation in the project.

## 03-gather-vs-decode

*Goes in: Discussion — the real bottleneck*

Gather takes about a second for every scheme; decode spans three orders of magnitude above it and misses the slot deadline. The bottleneck is arithmetic, not bandwidth.

## 04-scalability-peer-count

*Goes in: Results — scalability*

Realised erasure against network size, with the exact hypergeometric prediction computed rather than fitted. What protects a cell is the fraction of the network custodying it.

