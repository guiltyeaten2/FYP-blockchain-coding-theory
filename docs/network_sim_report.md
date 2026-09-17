# The P2P network simulation

`network_sim.py` puts the coding schemes into a simulated peer-to-peer
network and measures what happens to them there. It is the Phase 3 half of
the project: where `benchmark_1D_2D_BC.py` asks *what can this code
survive*, this asks *can a node actually get the data and rebuild the blob
before the slot ends*.

Those are genuinely different questions, and the second one cannot be
answered by the first. A decode time of 40 seconds is a fact about
arithmetic. Whether 40 seconds is acceptable is a fact about a system with
a 12-second slot, a deadline, a finite link and peers that may not answer.

## What the project brief asks for, and where it now stands

Phase 3 of the proposal specifies prototypes "deployed within a controlled
simulated peer-to-peer (P2P) network environment", evaluated "across
standard network architectures", capturing "bandwidth saturation, packet
propagation latency, and block processing throughput" under "varying
adversarial blockchain network conditions".

| Requirement | Status |
|---|---|
| Simulated P2P environment | done — SimPy discrete-event, 64 peers, custody assignment |
| Packet propagation latency | done — per-peer lognormal latency, reported as gather time |
| Bandwidth saturation | done — one contended downlink; saturates under multi-blob load |
| Block processing throughput | done — blobs reconstructed per slot |
| Varying adversarial conditions | done — swept 0–70% withholding peers |
| Randomly generated blob data | done — real EIP-4844 packing, shared blob |
| Data reconstruction success rate | done — per-trial, byte-verified |
| Scalability in node count | done — peer count is a swept dimension |
| **Standard network architectures (plural)** | **not done — one topology only** |

The remaining gap is listed again at the end rather than buried. Everything
above it is measured.

## How SimPy works, in the three concepts this uses

SimPy is a discrete-event simulator. Nothing in it runs in real time.

**The environment is a clock and an event queue.** `env.now` is the current
*simulated* time in seconds. `env.run(until=4.0)` processes every scheduled
event up to simulated t=4s and stops.

**A process is an ordinary Python generator.** `yield env.timeout(0.08)`
means "resume me 80 simulated milliseconds from now". The scheduler jumps
straight to the next event rather than waiting, so simulating a 12-second
slot across 64 peers costs microseconds of real CPU. This is what makes
sweeping hundreds of network configurations cheap.

**A resource models contention.** The node's downlink is a
`simpy.Resource` of capacity 1: a transfer acquires it, holds it for
`bytes / bandwidth` seconds, releases it. Because every transfer queues for
the same object, bandwidth saturation *emerges* from demand rather than
being asserted — ask for more than the link can carry before the deadline
and the queue backs up until the stragglers miss it.

## The one idea the design rests on

In the coding benchmark, the erasure mask is an **input**: `random_mask(rate,
rng)` invents one at a nominal rate. Here it is an **output** — whatever the
node failed to collect in time.

```
benchmark:    mask = adapter.random_mask(rate, rng)     # invented
network sim:  mask = <what did not arrive before the deadline>
```

Everything downstream of the mask — decode, extraction, byte-level
verification — is the *same adapter code* the benchmark already uses,
untouched. That single substitution is the entire integration surface,
which is why this file contains no coding logic of its own. A fix to
`2D_RS_Galois.py` changes these results automatically.

This buys something beyond convenience. The benchmark drops symbols
independently; real failures are not independent, because when a peer goes
offline *everything it custodied* vanishes at once. A peer-failure model
produces those **clustered** erasures for free, from the topology, rather
than having to inject correlation by hand — and the benchmark report
explicitly flags i.i.d.-only testing as a limitation.

## What is modelled

**Peers and custody.** 64 peers. Each cell is held by `custody_replication`
of them (default 4), so a cell is lost only if every custodian fails. This
is the *network's* redundancy, and it is separate from the code's — an
important distinction, because it turns out to absorb most peer failure
before the erasure code is asked to do anything.

**Cells.** The unit a node requests is a PeerDAS-shaped cell: 64 field
elements × 32 bytes, plus a 48-byte KZG proof, so 2096 bytes.

**Adversaries.** A fraction of peers never answer. The client burns its
request timeout before falling back to another custodian, so withholding
costs the victim *time* as well as data — which is the point of modelling
it rather than just deleting symbols.

**The deadline.** A 4-second sampling window inside a 12-second slot.
Anything not received by then is an erasure, full stop.

### How much a node actually has to download

This is the part worth dwelling on, because getting it wrong produced
nonsense on the first attempt.

The obvious answer is *k* symbols — the information-theoretic floor. That
is right only for an MDS code decoded optimally. In general a node must
fetch enough that what remains *missing* falls inside its own decoder's
tolerance:

> symbols needed = *n* × (1 − tolerance)

| | tolerance | must fetch | of |
|---|---|---|---|
| 1D-RS | 0.50 | 4096 | 8192 |
| 2D-RS | 0.35 | 5492 | 8448 |
| BC ω1024 λ2 | 0.33 | 5489 | 8192 |

So a weaker decoder forces a **larger download at identical storage cost**.
This is the benchmark report's "surviving data needed" figure, no longer
sitting in a table but actually driving a network transfer. Setting the
fetch target from *k* alone instead made every scheme sit at 42% erasure
even with a perfect network, and BC then "failed" at zero adversaries —
an artifact of the fetch policy, not a property of the code.

## Results

The figures below come from three sweeps, all with 30 trials per point:
**A** — one blob at 50 Mbps, six schemes, withholding swept 0–80%;
**B** — six blobs at 25 Mbps, the same schemes, 0–60%;
**C** — peer count 8→256 at 30% and 60% withholding. Raw rows are in the
accompanying JSON.

Decode times come from this project's Python/`galois` implementation and
are two to three orders of magnitude slower than production field
arithmetic. Absolute figures describe *this code*; comparisons between
schemes are the transferable part. `--speedup N` divides decode by N to ask
what production arithmetic would look like.

<figure>
<svg viewBox="0 0 430 240" role="img" aria-label="Realised erasure fraction against the fraction of withholding peers, compared with the p to the fourth prediction from custody replication four.">
<line x1="52" y1="24" x2="52" y2="186" stroke="currentColor" stroke-width="0.8"/>
<line x1="52" y1="186" x2="330" y2="186" stroke="currentColor" stroke-width="0.8"/>
<line x1="49" y1="186.0" x2="52" y2="186.0" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="186.0" x2="330" y2="186.0" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="188.5" text-anchor="end" font-size="7">0.00</text>
<line x1="49" y1="153.6" x2="52" y2="153.6" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="153.6" x2="330" y2="153.6" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="156.1" text-anchor="end" font-size="7">0.09</text>
<line x1="49" y1="121.2" x2="52" y2="121.2" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="121.2" x2="330" y2="121.2" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="123.7" text-anchor="end" font-size="7">0.18</text>
<line x1="49" y1="88.8" x2="52" y2="88.8" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="88.8" x2="330" y2="88.8" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="91.3" text-anchor="end" font-size="7">0.27</text>
<line x1="49" y1="56.4" x2="52" y2="56.4" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="56.4" x2="330" y2="56.4" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="58.9" text-anchor="end" font-size="7">0.36</text>
<line x1="49" y1="24.0" x2="52" y2="24.0" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="24.0" x2="330" y2="24.0" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="26.5" text-anchor="end" font-size="7">0.45</text>
<line x1="52.0" y1="186" x2="52.0" y2="189" stroke="currentColor" stroke-width="0.7"/>
<text x="52.0" y="198" text-anchor="middle" font-size="7">0%</text>
<line x1="121.5" y1="186" x2="121.5" y2="189" stroke="currentColor" stroke-width="0.7"/>
<text x="121.5" y="198" text-anchor="middle" font-size="7">20%</text>
<line x1="191.0" y1="186" x2="191.0" y2="189" stroke="currentColor" stroke-width="0.7"/>
<text x="191.0" y="198" text-anchor="middle" font-size="7">40%</text>
<line x1="260.5" y1="186" x2="260.5" y2="189" stroke="currentColor" stroke-width="0.7"/>
<text x="260.5" y="198" text-anchor="middle" font-size="7">60%</text>
<line x1="330.0" y1="186" x2="330.0" y2="189" stroke="currentColor" stroke-width="0.7"/>
<text x="330.0" y="198" text-anchor="middle" font-size="7">80%</text>
<text x="191" y="212" text-anchor="middle" font-size="7.6">fraction of peers withholding</text>
<text x="11" y="105" text-anchor="middle" font-size="7.6" transform="rotate(-90 11 105)">realised erasure fraction</text>
<polyline points="52.0,186.0 86.8,186.0 121.5,185.4 156.2,183.1 191.0,176.8 225.8,163.5 260.5,139.3 295.2,99.6 330.0,38.5" fill="none" stroke="#8d99a6" stroke-width="1.4" stroke-dasharray="4,2.5"/>
<polyline points="52.0,186.0 86.8,185.9 121.5,185.5 156.2,183.8 191.0,178.6 225.8,165.8 260.5,145.1 295.2,102.3 330.0,42.0" fill="none" stroke="#1546a0" stroke-width="1.6"/>
<circle cx="52.0" cy="186.0" r="2.3" fill="#1546a0"/>
<circle cx="86.8" cy="185.9" r="2.3" fill="#1546a0"/>
<circle cx="121.5" cy="185.5" r="2.3" fill="#1546a0"/>
<circle cx="156.2" cy="183.8" r="2.3" fill="#1546a0"/>
<circle cx="191.0" cy="178.6" r="2.3" fill="#1546a0"/>
<circle cx="225.8" cy="165.8" r="2.3" fill="#1546a0"/>
<circle cx="260.5" cy="145.1" r="2.3" fill="#1546a0"/>
<circle cx="295.2" cy="102.3" r="2.3" fill="#1546a0"/>
<circle cx="330.0" cy="42.0" r="2.3" fill="#1546a0"/>
<text x="60" y="34" font-size="7" fill="#8d99a6" font-weight="700">- - predicted p⁴ (all 4 custodians withhold)</text>
<text x="60" y="45" font-size="7" fill="#1546a0" font-weight="700">&#8212; measured, 30 trials per point</text>
</svg>
<figcaption><b>Custody replication, not the code, is what absorbs peer failure.</b> A cell is lost only when every one of its four custodians withholds, so the erasure the code actually sees is roughly the fourth power of the fraction of bad peers. The dashed line is that p⁴ prediction, computed from the model and not fitted; the solid line is what 30 trials per point produced. Measurement sits slightly below prediction throughout, because a node that gets an early refusal still has time to retry another custodian. The practical reading: 40% of peers withholding costs about 2% of the data.</figcaption>
</figure>

<figure>
<svg viewBox="0 0 430 250" role="img" aria-label="Fraction of trials that recovered the blob, against withholding peers, for each coding scheme.">
<line x1="52" y1="24" x2="52" y2="190" stroke="currentColor" stroke-width="0.8"/>
<line x1="52" y1="190" x2="320" y2="190" stroke="currentColor" stroke-width="0.8"/>
<line x1="49" y1="190.0" x2="52" y2="190.0" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="190.0" x2="320" y2="190.0" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="192.5" text-anchor="end" font-size="7">0.00</text>
<line x1="49" y1="156.8" x2="52" y2="156.8" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="156.8" x2="320" y2="156.8" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="159.3" text-anchor="end" font-size="7">0.20</text>
<line x1="49" y1="123.6" x2="52" y2="123.6" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="123.6" x2="320" y2="123.6" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="126.1" text-anchor="end" font-size="7">0.40</text>
<line x1="49" y1="90.4" x2="52" y2="90.4" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="90.4" x2="320" y2="90.4" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="92.9" text-anchor="end" font-size="7">0.60</text>
<line x1="49" y1="57.2" x2="52" y2="57.2" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="57.2" x2="320" y2="57.2" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="59.7" text-anchor="end" font-size="7">0.80</text>
<line x1="49" y1="24.0" x2="52" y2="24.0" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="24.0" x2="320" y2="24.0" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="26.5" text-anchor="end" font-size="7">1.00</text>
<line x1="52.0" y1="190" x2="52.0" y2="193" stroke="currentColor" stroke-width="0.7"/>
<text x="52.0" y="202" text-anchor="middle" font-size="7">0%</text>
<line x1="119.0" y1="190" x2="119.0" y2="193" stroke="currentColor" stroke-width="0.7"/>
<text x="119.0" y="202" text-anchor="middle" font-size="7">20%</text>
<line x1="186.0" y1="190" x2="186.0" y2="193" stroke="currentColor" stroke-width="0.7"/>
<text x="186.0" y="202" text-anchor="middle" font-size="7">40%</text>
<line x1="253.0" y1="190" x2="253.0" y2="193" stroke="currentColor" stroke-width="0.7"/>
<text x="253.0" y="202" text-anchor="middle" font-size="7">60%</text>
<line x1="320.0" y1="190" x2="320.0" y2="193" stroke="currentColor" stroke-width="0.7"/>
<text x="320.0" y="202" text-anchor="middle" font-size="7">80%</text>
<text x="186" y="216" text-anchor="middle" font-size="7.6">fraction of peers withholding</text>
<text x="11" y="107" text-anchor="middle" font-size="7.6" transform="rotate(-90 11 107)">trials recovered</text>
<polyline points="52.0,24.0 85.5,24.0 119.0,24.0 152.5,24.0 186.0,24.0 219.5,24.0 253.0,24.0 286.5,24.0 320.0,24.0" fill="none" stroke="#c62828" stroke-width="1.5"/>
<circle cx="52.0" cy="24.0" r="1.9" fill="#c62828"/>
<circle cx="85.5" cy="24.0" r="1.9" fill="#c62828"/>
<circle cx="119.0" cy="24.0" r="1.9" fill="#c62828"/>
<circle cx="152.5" cy="24.0" r="1.9" fill="#c62828"/>
<circle cx="186.0" cy="24.0" r="1.9" fill="#c62828"/>
<circle cx="219.5" cy="24.0" r="1.9" fill="#c62828"/>
<circle cx="253.0" cy="24.0" r="1.9" fill="#c62828"/>
<circle cx="286.5" cy="24.0" r="1.9" fill="#c62828"/>
<circle cx="320.0" cy="24.0" r="1.9" fill="#c62828"/>
<polyline points="52.0,24.0 85.5,24.0 119.0,24.0 152.5,24.0 186.0,24.0 219.5,24.0 253.0,24.0 286.5,24.0 320.0,79.3" fill="none" stroke="#1546a0" stroke-width="1.5"/>
<circle cx="52.0" cy="24.0" r="1.9" fill="#1546a0"/>
<circle cx="85.5" cy="24.0" r="1.9" fill="#1546a0"/>
<circle cx="119.0" cy="24.0" r="1.9" fill="#1546a0"/>
<circle cx="152.5" cy="24.0" r="1.9" fill="#1546a0"/>
<circle cx="186.0" cy="24.0" r="1.9" fill="#1546a0"/>
<circle cx="219.5" cy="24.0" r="1.9" fill="#1546a0"/>
<circle cx="253.0" cy="24.0" r="1.9" fill="#1546a0"/>
<circle cx="286.5" cy="24.0" r="1.9" fill="#1546a0"/>
<circle cx="320.0" cy="79.3" r="1.9" fill="#1546a0"/>
<polyline points="52.0,24.0 85.5,24.0 119.0,24.0 152.5,24.0 186.0,24.0 219.5,24.0 253.0,24.0 286.5,29.5 320.0,184.5" fill="none" stroke="#14532d" stroke-width="1.5"/>
<circle cx="52.0" cy="24.0" r="1.9" fill="#14532d"/>
<circle cx="85.5" cy="24.0" r="1.9" fill="#14532d"/>
<circle cx="119.0" cy="24.0" r="1.9" fill="#14532d"/>
<circle cx="152.5" cy="24.0" r="1.9" fill="#14532d"/>
<circle cx="186.0" cy="24.0" r="1.9" fill="#14532d"/>
<circle cx="219.5" cy="24.0" r="1.9" fill="#14532d"/>
<circle cx="253.0" cy="24.0" r="1.9" fill="#14532d"/>
<circle cx="286.5" cy="29.5" r="1.9" fill="#14532d"/>
<circle cx="320.0" cy="184.5" r="1.9" fill="#14532d"/>
<polyline points="52.0,24.0 85.5,24.0 119.0,24.0 152.5,24.0 186.0,24.0 219.5,24.0 253.0,24.0 286.5,29.5 320.0,178.9" fill="none" stroke="#1b7a34" stroke-width="1.5"/>
<circle cx="52.0" cy="24.0" r="1.9" fill="#1b7a34"/>
<circle cx="85.5" cy="24.0" r="1.9" fill="#1b7a34"/>
<circle cx="119.0" cy="24.0" r="1.9" fill="#1b7a34"/>
<circle cx="152.5" cy="24.0" r="1.9" fill="#1b7a34"/>
<circle cx="186.0" cy="24.0" r="1.9" fill="#1b7a34"/>
<circle cx="219.5" cy="24.0" r="1.9" fill="#1b7a34"/>
<circle cx="253.0" cy="24.0" r="1.9" fill="#1b7a34"/>
<circle cx="286.5" cy="29.5" r="1.9" fill="#1b7a34"/>
<circle cx="320.0" cy="178.9" r="1.9" fill="#1b7a34"/>
<polyline points="52.0,24.0 85.5,24.0 119.0,24.0 152.5,24.0 186.0,24.0 219.5,24.0 253.0,24.0 286.5,35.1 320.0,190.0" fill="none" stroke="#b45309" stroke-width="1.5"/>
<circle cx="52.0" cy="24.0" r="1.9" fill="#b45309"/>
<circle cx="85.5" cy="24.0" r="1.9" fill="#b45309"/>
<circle cx="119.0" cy="24.0" r="1.9" fill="#b45309"/>
<circle cx="152.5" cy="24.0" r="1.9" fill="#b45309"/>
<circle cx="186.0" cy="24.0" r="1.9" fill="#b45309"/>
<circle cx="219.5" cy="24.0" r="1.9" fill="#b45309"/>
<circle cx="253.0" cy="24.0" r="1.9" fill="#b45309"/>
<circle cx="286.5" cy="35.1" r="1.9" fill="#b45309"/>
<circle cx="320.0" cy="190.0" r="1.9" fill="#b45309"/>
<polyline points="52.0,24.0 85.5,24.0 119.0,24.0 152.5,24.0 186.0,24.0 219.5,24.0 253.0,29.5 286.5,145.7 320.0,190.0" fill="none" stroke="#7c2d92" stroke-width="1.5"/>
<circle cx="52.0" cy="24.0" r="1.9" fill="#7c2d92"/>
<circle cx="85.5" cy="24.0" r="1.9" fill="#7c2d92"/>
<circle cx="119.0" cy="24.0" r="1.9" fill="#7c2d92"/>
<circle cx="152.5" cy="24.0" r="1.9" fill="#7c2d92"/>
<circle cx="186.0" cy="24.0" r="1.9" fill="#7c2d92"/>
<circle cx="219.5" cy="24.0" r="1.9" fill="#7c2d92"/>
<circle cx="253.0" cy="29.5" r="1.9" fill="#7c2d92"/>
<circle cx="286.5" cy="145.7" r="1.9" fill="#7c2d92"/>
<circle cx="320.0" cy="190.0" r="1.9" fill="#7c2d92"/>
<text x="326" y="34" font-size="6.8" fill="#c62828" font-weight="700">1D-RS</text>
<text x="326" y="45" font-size="6.8" fill="#1546a0" font-weight="700">2D-RS</text>
<text x="326" y="56" font-size="6.8" fill="#14532d" font-weight="700">BC ω2048 λ2</text>
<text x="326" y="67" font-size="6.8" fill="#1b7a34" font-weight="700">BC ω1024 λ2</text>
<text x="326" y="78" font-size="6.8" fill="#b45309" font-weight="700">BC ω1024 λ3</text>
<text x="326" y="89" font-size="6.8" fill="#7c2d92" font-weight="700">BC ω1024 λ4</text>
</svg>
<figcaption><b>The benchmark's tolerance ordering reappears through a completely different mechanism.</b> No erasure rate is injected here — losses come from peers refusing to answer. Yet the schemes fail in exactly the order the coding benchmark predicted, and at the adversarial rates that produce their measured erasure thresholds. BC ω1024 λ4 breaks first (tolerance 0.20, and 70% withholding yields 0.233 erasure); 2D-RS and the λ2 rows hold until 80% withholding drives erasure to 0.400; 1D-RS, tolerating 0.50, never fails anywhere in this sweep. 30 trials per point.</figcaption>
</figure>

### One blob per slot, 50 Mbps (selected rates; full sweep in runA.json)

| scheme | adversarial | recovered | erasure | KiB | gather | decode | total | blobs/slot |
|---|---|---|---|---|---|---|---|---|
| 1D-RS | 0% | 30/30 | 0.000 | 262 | 0.14s | 0.00s | 0.14s | 1.00 |
| 1D-RS | 20% | 30/30 | 0.001 | 262 | 0.19s | 0.86s | 1.05s | 1.00 |
| 1D-RS | 40% | 30/30 | 0.021 | 257 | 0.43s | 5.92s | 6.34s | 1.00 |
| 1D-RS | 60% | 30/30 | 0.114 | 232 | 0.78s | 23.36s | 24.13s | 0.50 |
| 1D-RS | 70% | 30/30 | 0.233 | 201 | 1.22s | 45.19s | 46.41s | 0.26 |
| 1D-RS | 80% | 30/30 | 0.400 | 157 | 3.22s | 70.33s | 73.55s | 0.16 |
| 2D-RS | 0% | 30/30 | 0.000 | 270 | 0.17s | 0.00s | 0.17s | 1.00 |
| 2D-RS | 20% | 30/30 | 0.001 | 270 | 0.25s | 0.41s | 0.66s | 1.00 |
| 2D-RS | 40% | 30/30 | 0.021 | 265 | 0.57s | 2.46s | 3.03s | 1.00 |
| 2D-RS | 60% | 30/30 | 0.114 | 239 | 1.02s | 3.44s | 4.46s | 1.00 |
| 2D-RS | 70% | 30/30 | 0.234 | 207 | 1.72s | 5.22s | 6.94s | 1.00 |
| 2D-RS | 80% | 20/30 | 0.400 | 162 | 4.00s | 6.03s | 10.03s | 0.67 |
| BC ω2048 λ2 | 0% | 30/30 | 0.000 | 262 | 0.18s | 0.00s | 0.18s | 1.00 |
| BC ω2048 λ2 | 20% | 30/30 | 0.001 | 262 | 0.32s | 0.07s | 0.39s | 1.00 |
| BC ω2048 λ2 | 40% | 30/30 | 0.021 | 257 | 0.65s | 0.49s | 1.14s | 1.00 |
| BC ω2048 λ2 | 60% | 30/30 | 0.114 | 232 | 1.16s | 2.33s | 3.49s | 1.00 |
| BC ω2048 λ2 | 70% | 29/30 | 0.233 | 201 | 2.72s | 5.10s | 7.78s | 0.97 |
| BC ω2048 λ2 | 80% | 1/30 | 0.400 | 157 | 4.00s | 7.90s | 11.90s | 0.03 |
| BC ω1024 λ2 | 0% | 30/30 | 0.000 | 262 | 0.18s | 0.00s | 0.18s | 1.00 |
| BC ω1024 λ2 | 20% | 30/30 | 0.001 | 262 | 0.32s | 0.04s | 0.36s | 1.00 |
| BC ω1024 λ2 | 40% | 30/30 | 0.021 | 257 | 0.65s | 0.27s | 0.93s | 1.00 |
| BC ω1024 λ2 | 60% | 30/30 | 0.114 | 232 | 1.16s | 1.25s | 2.41s | 1.00 |
| BC ω1024 λ2 | 70% | 29/30 | 0.233 | 201 | 2.72s | 2.68s | 5.36s | 0.97 |
| BC ω1024 λ2 | 80% | 2/30 | 0.400 | 157 | 4.00s | 4.21s | 8.21s | 0.07 |
| BC ω1024 λ3 | 0% | 30/30 | 0.000 | 262 | 0.21s | 0.00s | 0.21s | 1.00 |
| BC ω1024 λ3 | 20% | 30/30 | 0.001 | 262 | 0.50s | 0.05s | 0.55s | 1.00 |
| BC ω1024 λ3 | 40% | 30/30 | 0.021 | 257 | 0.90s | 0.35s | 1.25s | 1.00 |
| BC ω1024 λ3 | 60% | 30/30 | 0.114 | 232 | 2.00s | 1.60s | 3.60s | 1.00 |
| BC ω1024 λ3 | 70% | 28/30 | 0.233 | 201 | 4.00s | 3.34s | 7.34s | 0.93 |
| BC ω1024 λ3 | 80% | 0/30 | 0.400 | 157 | 4.00s | &mdash; | &mdash; | 0.00 |
| BC ω1024 λ4 | 0% | 30/30 | 0.000 | 262 | 0.33s | 0.00s | 0.33s | 1.00 |
| BC ω1024 λ4 | 20% | 30/30 | 0.001 | 262 | 0.98s | 0.06s | 1.04s | 1.00 |
| BC ω1024 λ4 | 40% | 30/30 | 0.021 | 257 | 2.75s | 0.44s | 3.19s | 1.00 |
| BC ω1024 λ4 | 60% | 29/30 | 0.114 | 232 | 4.00s | 1.92s | 5.92s | 0.97 |
| BC ω1024 λ4 | 70% | 8/30 | 0.233 | 201 | 4.00s | 3.50s | 7.50s | 0.27 |
| BC ω1024 λ4 | 80% | 0/30 | 0.400 | 157 | 4.00s | &mdash; | &mdash; | 0.00 |

### Six blobs per slot, 25 Mbps — where bandwidth starts to bite

| scheme | adversarial | recovered | erasure | KiB | gather | decode | total | blobs/slot |
|---|---|---|---|---|---|---|---|---|
| 1D-RS | 0% | 30/30 | 0.320 | 1068 | 0.80s | 354.07s | 354.87s | 0.20 |
| 1D-RS | 20% | 30/30 | 0.321 | 1068 | 1.62s | 354.39s | 356.01s | 0.20 |
| 1D-RS | 40% | 30/30 | 0.333 | 1051 | 3.21s | 363.70s | 366.91s | 0.20 |
| 1D-RS | 60% | 15/30 | 0.514 | 754 | 4.00s | 470.10s | 474.10s | 0.08 |
| 2D-RS | 0% | 30/30 | 0.212 | 1277 | 0.95s | 31.15s | 32.10s | 2.24 |
| 2D-RS | 20% | 30/30 | 0.213 | 1276 | 1.98s | 31.19s | 33.18s | 2.17 |
| 2D-RS | 40% | 30/30 | 0.248 | 1222 | 3.72s | 32.38s | 36.10s | 1.99 |
| 2D-RS | 60% | 2/30 | 0.517 | 769 | 4.00s | 36.44s | 40.44s | 0.12 |
| BC ω2048 λ2 | 0% | 30/30 | 0.156 | 1326 | 0.99s | 20.05s | 21.04s | 3.42 |
| BC ω2048 λ2 | 20% | 30/30 | 0.157 | 1325 | 2.03s | 20.13s | 22.16s | 3.25 |
| BC ω2048 λ2 | 40% | 29/30 | 0.214 | 1242 | 3.79s | 28.02s | 31.80s | 2.19 |
| BC ω2048 λ2 | 60% | 1/30 | 0.511 | 756 | 4.00s | 40.87s | 44.87s | 0.05 |
| BC ω1024 λ2 | 0% | 30/30 | 0.156 | 1326 | 0.99s | 10.55s | 11.54s | 6.00 |
| BC ω1024 λ2 | 20% | 30/30 | 0.157 | 1325 | 2.03s | 10.59s | 12.62s | 5.70 |
| BC ω1024 λ2 | 40% | 29/30 | 0.214 | 1242 | 3.79s | 14.71s | 18.49s | 3.76 |
| BC ω1024 λ2 | 60% | 1/30 | 0.511 | 756 | 4.00s | 21.26s | 25.26s | 0.10 |
| BC ω1024 λ3 | 0% | 30/30 | 0.062 | 1474 | 1.10s | 5.26s | 6.35s | 6.00 |
| BC ω1024 λ3 | 20% | 30/30 | 0.063 | 1473 | 2.23s | 5.30s | 7.53s | 6.00 |
| BC ω1024 λ3 | 40% | 24/30 | 0.186 | 1292 | 3.93s | 13.65s | 17.56s | 3.28 |
| BC ω1024 λ3 | 60% | 0/30 | 0.511 | 756 | 4.00s | &mdash; | &mdash; | 0.00 |
| BC ω1024 λ4 | 0% | 30/30 | 0.000 | 1572 | 1.26s | 0.00s | 1.26s | 6.00 |
| BC ω1024 λ4 | 20% | 30/30 | 0.001 | 1570 | 2.72s | 0.38s | 3.10s | 6.00 |
| BC ω1024 λ4 | 40% | 16/30 | 0.179 | 1304 | 4.00s | 12.46s | 16.46s | 2.33 |
| BC ω1024 λ4 | 60% | 0/30 | 0.511 | 756 | 4.00s | &mdash; | &mdash; | 0.00 |

<figure>
<svg viewBox="0 0 430 250" role="img" aria-label="Blobs reconstructed per slot out of six, against withholding peers, for each coding scheme.">
<line x1="52" y1="24" x2="52" y2="190" stroke="currentColor" stroke-width="0.8"/>
<line x1="52" y1="190" x2="316" y2="190" stroke="currentColor" stroke-width="0.8"/>
<line x1="49" y1="190.0" x2="52" y2="190.0" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="190.0" x2="316" y2="190.0" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="192.5" text-anchor="end" font-size="7">0.0</text>
<line x1="49" y1="156.8" x2="52" y2="156.8" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="156.8" x2="316" y2="156.8" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="159.3" text-anchor="end" font-size="7">1.2</text>
<line x1="49" y1="123.6" x2="52" y2="123.6" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="123.6" x2="316" y2="123.6" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="126.1" text-anchor="end" font-size="7">2.4</text>
<line x1="49" y1="90.4" x2="52" y2="90.4" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="90.4" x2="316" y2="90.4" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="92.9" text-anchor="end" font-size="7">3.6</text>
<line x1="49" y1="57.2" x2="52" y2="57.2" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="57.2" x2="316" y2="57.2" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="59.7" text-anchor="end" font-size="7">4.8</text>
<line x1="49" y1="24.0" x2="52" y2="24.0" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="24.0" x2="316" y2="24.0" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="26.5" text-anchor="end" font-size="7">6.0</text>
<line x1="52.0" y1="190" x2="52.0" y2="193" stroke="currentColor" stroke-width="0.7"/>
<text x="52.0" y="202" text-anchor="middle" font-size="7">0%</text>
<line x1="140.0" y1="190" x2="140.0" y2="193" stroke="currentColor" stroke-width="0.7"/>
<text x="140.0" y="202" text-anchor="middle" font-size="7">20%</text>
<line x1="228.0" y1="190" x2="228.0" y2="193" stroke="currentColor" stroke-width="0.7"/>
<text x="228.0" y="202" text-anchor="middle" font-size="7">40%</text>
<line x1="316.0" y1="190" x2="316.0" y2="193" stroke="currentColor" stroke-width="0.7"/>
<text x="316.0" y="202" text-anchor="middle" font-size="7">60%</text>
<text x="184" y="216" text-anchor="middle" font-size="7.6">fraction of peers withholding</text>
<text x="11" y="107" text-anchor="middle" font-size="7.6" transform="rotate(-90 11 107)">blobs reconstructed / slot</text>
<line x1="52" y1="24" x2="316" y2="24" stroke="#8d99a6" stroke-width="1" stroke-dasharray="3,2"/>
<text x="56" y="20" font-size="6.6" fill="#8d99a6">6 = keeping up with the block</text>
<polyline points="52.0,184.4 140.0,184.4 228.0,184.6 316.0,187.9" fill="none" stroke="#c62828" stroke-width="1.5"/>
<circle cx="52.0" cy="184.4" r="1.9" fill="#c62828"/>
<circle cx="140.0" cy="184.4" r="1.9" fill="#c62828"/>
<circle cx="228.0" cy="184.6" r="1.9" fill="#c62828"/>
<circle cx="316.0" cy="187.9" r="1.9" fill="#c62828"/>
<polyline points="52.0,128.0 140.0,130.0 228.0,134.8 316.0,186.7" fill="none" stroke="#1546a0" stroke-width="1.5"/>
<circle cx="52.0" cy="128.0" r="1.9" fill="#1546a0"/>
<circle cx="140.0" cy="130.0" r="1.9" fill="#1546a0"/>
<circle cx="228.0" cy="134.8" r="1.9" fill="#1546a0"/>
<circle cx="316.0" cy="186.7" r="1.9" fill="#1546a0"/>
<polyline points="52.0,95.3 140.0,100.1 228.0,129.5 316.0,188.5" fill="none" stroke="#14532d" stroke-width="1.5"/>
<circle cx="52.0" cy="95.3" r="1.9" fill="#14532d"/>
<circle cx="140.0" cy="100.1" r="1.9" fill="#14532d"/>
<circle cx="228.0" cy="129.5" r="1.9" fill="#14532d"/>
<circle cx="316.0" cy="188.5" r="1.9" fill="#14532d"/>
<polyline points="52.0,24.0 140.0,32.2 228.0,85.9 316.0,187.4" fill="none" stroke="#1b7a34" stroke-width="1.5"/>
<circle cx="52.0" cy="24.0" r="1.9" fill="#1b7a34"/>
<circle cx="140.0" cy="32.2" r="1.9" fill="#1b7a34"/>
<circle cx="228.0" cy="85.9" r="1.9" fill="#1b7a34"/>
<circle cx="316.0" cy="187.4" r="1.9" fill="#1b7a34"/>
<polyline points="52.0,24.0 140.0,24.0 228.0,99.3 316.0,190.0" fill="none" stroke="#b45309" stroke-width="1.5"/>
<circle cx="52.0" cy="24.0" r="1.9" fill="#b45309"/>
<circle cx="140.0" cy="24.0" r="1.9" fill="#b45309"/>
<circle cx="228.0" cy="99.3" r="1.9" fill="#b45309"/>
<circle cx="316.0" cy="190.0" r="1.9" fill="#b45309"/>
<polyline points="52.0,24.0 140.0,24.0 228.0,125.4 316.0,190.0" fill="none" stroke="#7c2d92" stroke-width="1.5"/>
<circle cx="52.0" cy="24.0" r="1.9" fill="#7c2d92"/>
<circle cx="140.0" cy="24.0" r="1.9" fill="#7c2d92"/>
<circle cx="228.0" cy="125.4" r="1.9" fill="#7c2d92"/>
<circle cx="316.0" cy="190.0" r="1.9" fill="#7c2d92"/>
<text x="322" y="34" font-size="6.8" fill="#c62828" font-weight="700">1D-RS</text>
<text x="322" y="45" font-size="6.8" fill="#1546a0" font-weight="700">2D-RS</text>
<text x="322" y="56" font-size="6.8" fill="#14532d" font-weight="700">BC ω2048 λ2</text>
<text x="322" y="67" font-size="6.8" fill="#1b7a34" font-weight="700">BC ω1024 λ2</text>
<text x="322" y="78" font-size="6.8" fill="#b45309" font-weight="700">BC ω1024 λ3</text>
<text x="322" y="89" font-size="6.8" fill="#7c2d92" font-weight="700">BC ω1024 λ4</text>
</svg>
<figcaption><b>Throughput at six blobs per slot and 25 Mbps — the ordering inverts.</b> 1D-RS tolerates the most erasure of any scheme here and reconstructs the fewest blobs, roughly 0.2 of the six, because one 8192-length polynomial division costs roughly 59s per blob. BC ω1024 λ2, λ3 and λ4 keep up with all six until 20% withholding. Note this is throughput <em>implied by</em> the measured time — blobs attempted, scaled by the measured recovery rate and by whether the total fits the 12s slot — not an independently measured rate.</figcaption>
</figure>

<figure>
<svg viewBox="0 0 430 216" role="img" aria-label="Gather time and decode time per scheme on a logarithmic axis, six blobs, showing decode exceeding gather by two to three orders of magnitude.">
<line x1="128" y1="28" x2="128" y2="186" stroke="currentColor" stroke-width="0.8"/>
<line x1="128" y1="186" x2="386" y2="186" stroke="currentColor" stroke-width="0.8"/>
<line x1="128.0" y1="186" x2="128.0" y2="189" stroke="currentColor" stroke-width="0.7"/>
<line x1="128.0" y1="28" x2="128.0" y2="186" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="128.0" y="197" text-anchor="middle" font-size="7">0.1</text>
<line x1="192.5" y1="186" x2="192.5" y2="189" stroke="currentColor" stroke-width="0.7"/>
<line x1="192.5" y1="28" x2="192.5" y2="186" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="192.5" y="197" text-anchor="middle" font-size="7">1</text>
<line x1="257.0" y1="186" x2="257.0" y2="189" stroke="currentColor" stroke-width="0.7"/>
<line x1="257.0" y1="28" x2="257.0" y2="186" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="257.0" y="197" text-anchor="middle" font-size="7">10</text>
<line x1="321.5" y1="186" x2="321.5" y2="189" stroke="currentColor" stroke-width="0.7"/>
<line x1="321.5" y1="28" x2="321.5" y2="186" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="321.5" y="197" text-anchor="middle" font-size="7">100</text>
<line x1="386.0" y1="186" x2="386.0" y2="189" stroke="currentColor" stroke-width="0.7"/>
<line x1="386.0" y1="28" x2="386.0" y2="186" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="386.0" y="197" text-anchor="middle" font-size="7">1000</text>
<text x="257" y="210" text-anchor="middle" font-size="7.4">seconds (log scale)</text>
<line x1="262.1" y1="28" x2="262.1" y2="186" stroke="#c62828" stroke-width="1" stroke-dasharray="3,2"/>
<text x="265.1" y="25" font-size="6.6" fill="#c62828" font-weight="700">12s slot</text>
<text x="122" y="45" text-anchor="end" font-size="7">1D-RS</text>
<rect x="128" y="35" width="58.1" height="7" fill="#9bb0c9"/>
<rect x="128" y="44" width="228.9" height="7" fill="#c62828" opacity="0.9"/>
<text x="189.1" y="41.5" font-size="6.2" fill="#5b6572">0.80s gather</text>
<text x="359.9" y="50.5" font-size="6.2" fill="#c62828">354.1s decode</text>
<text x="122" y="71" text-anchor="end" font-size="7">2D-RS</text>
<rect x="128" y="61" width="63.2" height="7" fill="#9bb0c9"/>
<rect x="128" y="70" width="160.8" height="7" fill="#1546a0" opacity="0.9"/>
<text x="194.2" y="67.5" font-size="6.2" fill="#5b6572">0.95s gather</text>
<text x="291.8" y="76.5" font-size="6.2" fill="#1546a0">31.2s decode</text>
<text x="122" y="97" text-anchor="end" font-size="7">BC ω2048 λ2</text>
<rect x="128" y="87" width="64.2" height="7" fill="#9bb0c9"/>
<rect x="128" y="96" width="148.5" height="7" fill="#14532d" opacity="0.9"/>
<text x="195.2" y="93.5" font-size="6.2" fill="#5b6572">0.99s gather</text>
<text x="279.5" y="102.5" font-size="6.2" fill="#14532d">20.1s decode</text>
<text x="122" y="123" text-anchor="end" font-size="7">BC ω1024 λ2</text>
<rect x="128" y="113" width="64.2" height="7" fill="#9bb0c9"/>
<rect x="128" y="122" width="130.5" height="7" fill="#1b7a34" opacity="0.9"/>
<text x="195.2" y="119.5" font-size="6.2" fill="#5b6572">0.99s gather</text>
<text x="261.5" y="128.5" font-size="6.2" fill="#1b7a34">10.6s decode</text>
<text x="122" y="149" text-anchor="end" font-size="7">BC ω1024 λ3</text>
<rect x="128" y="139" width="67.1" height="7" fill="#9bb0c9"/>
<rect x="128" y="148" width="111.0" height="7" fill="#b45309" opacity="0.9"/>
<text x="198.1" y="145.5" font-size="6.2" fill="#5b6572">1.10s gather</text>
<text x="242.0" y="154.5" font-size="6.2" fill="#b45309">5.3s decode</text>
<text x="122" y="175" text-anchor="end" font-size="7">BC ω1024 λ4</text>
<rect x="128" y="165" width="70.9" height="7" fill="#9bb0c9"/>
<rect x="128" y="174" width="0.8" height="7" fill="#7c2d92" opacity="0.9"/>
<text x="201.9" y="171.5" font-size="6.2" fill="#5b6572">1.26s gather</text>
<text x="131.0" y="180.5" font-size="6.2" fill="#7c2d92">0.0s decode</text>
</svg>
<figcaption><b>Where the time goes, six blobs, no adversaries, log scale.</b> Gather and decode are drawn as separate bars rather than stacked, because stacking on a log axis would misrepresent the sum. Every scheme gathers in about one second; decode spans three orders of magnitude above that. This is the central result of the network layer: at every setting tried, arithmetic rather than bandwidth or latency decides whether a scheme fits the slot. BC ω1024 λ4 shows no decode bar because it has the weakest decoder and therefore fetches the most (80% of the codeword); with nothing missing there is nothing to reconstruct. It buys its speed with bandwidth.</figcaption>
</figure>

<figure>
<svg viewBox="0 0 430 245" role="img" aria-label="Realised erasure fraction against peer count at sixty percent withholding, with the hypergeometric prediction and its p to the fourth asymptote.">
<line x1="52" y1="26" x2="52" y2="188" stroke="currentColor" stroke-width="0.8"/>
<line x1="52" y1="188" x2="322" y2="188" stroke="currentColor" stroke-width="0.8"/>
<line x1="49" y1="188.0" x2="52" y2="188.0" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="188.0" x2="322" y2="188.0" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="190.5" text-anchor="end" font-size="7">0.000</text>
<line x1="49" y1="155.6" x2="52" y2="155.6" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="155.6" x2="322" y2="155.6" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="158.1" text-anchor="end" font-size="7">0.030</text>
<line x1="49" y1="123.2" x2="52" y2="123.2" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="123.2" x2="322" y2="123.2" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="125.7" text-anchor="end" font-size="7">0.060</text>
<line x1="49" y1="90.8" x2="52" y2="90.8" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="90.8" x2="322" y2="90.8" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="93.3" text-anchor="end" font-size="7">0.090</text>
<line x1="49" y1="58.4" x2="52" y2="58.4" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="58.4" x2="322" y2="58.4" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="60.9" text-anchor="end" font-size="7">0.120</text>
<line x1="49" y1="26.0" x2="52" y2="26.0" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="26.0" x2="322" y2="26.0" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="28.5" text-anchor="end" font-size="7">0.150</text>
<line x1="52.0" y1="188" x2="52.0" y2="191" stroke="currentColor" stroke-width="0.7"/>
<text x="52.0" y="200" text-anchor="middle" font-size="7">8</text>
<line x1="106.0" y1="188" x2="106.0" y2="191" stroke="currentColor" stroke-width="0.7"/>
<text x="106.0" y="200" text-anchor="middle" font-size="7">16</text>
<line x1="160.0" y1="188" x2="160.0" y2="191" stroke="currentColor" stroke-width="0.7"/>
<text x="160.0" y="200" text-anchor="middle" font-size="7">32</text>
<line x1="214.0" y1="188" x2="214.0" y2="191" stroke="currentColor" stroke-width="0.7"/>
<text x="214.0" y="200" text-anchor="middle" font-size="7">64</text>
<line x1="268.0" y1="188" x2="268.0" y2="191" stroke="currentColor" stroke-width="0.7"/>
<text x="268.0" y="200" text-anchor="middle" font-size="7">128</text>
<line x1="322.0" y1="188" x2="322.0" y2="191" stroke="currentColor" stroke-width="0.7"/>
<text x="322.0" y="200" text-anchor="middle" font-size="7">256</text>
<text x="187" y="214" text-anchor="middle" font-size="7.6">peers in the network (log₂ scale)</text>
<text x="11" y="107" text-anchor="middle" font-size="7.6" transform="rotate(-90 11 107)">realised erasure fraction</text>
<line x1="52" y1="48.0" x2="322" y2="48.0" stroke="#c62828" stroke-width="1" stroke-dasharray="3,2"/>
<text x="319" y="58.0" text-anchor="end" font-size="6.6" fill="#c62828" font-weight="700">p⁴ = 0.130, the large-network limit</text>
<polyline points="52.0,110.9 106.0,63.4 160.0,71.6 214.0,62.5 268.0,51.0 322.0,48.8" fill="none" stroke="#8d99a6" stroke-width="1.4" stroke-dasharray="4,2.5"/>
<circle cx="52.0" cy="110.9" r="2" fill="none" stroke="#8d99a6" stroke-width="1.1"/>
<circle cx="106.0" cy="63.4" r="2" fill="none" stroke="#8d99a6" stroke-width="1.1"/>
<circle cx="160.0" cy="71.6" r="2" fill="none" stroke="#8d99a6" stroke-width="1.1"/>
<circle cx="214.0" cy="62.5" r="2" fill="none" stroke="#8d99a6" stroke-width="1.1"/>
<circle cx="268.0" cy="51.0" r="2" fill="none" stroke="#8d99a6" stroke-width="1.1"/>
<circle cx="322.0" cy="48.8" r="2" fill="none" stroke="#8d99a6" stroke-width="1.1"/>
<polyline points="52.0,114.1 106.0,68.0 160.0,71.5 214.0,65.0 268.0,54.9 322.0,55.5" fill="none" stroke="#1546a0" stroke-width="1.5"/>
<circle cx="52.0" cy="114.1" r="2.1" fill="#1546a0"/>
<circle cx="106.0" cy="68.0" r="2.1" fill="#1546a0"/>
<circle cx="160.0" cy="71.5" r="2.1" fill="#1546a0"/>
<circle cx="214.0" cy="65.0" r="2.1" fill="#1546a0"/>
<circle cx="268.0" cy="54.9" r="2.1" fill="#1546a0"/>
<circle cx="322.0" cy="55.5" r="2.1" fill="#1546a0"/>
<polyline points="52.0,112.3 106.0,68.2 160.0,71.6 214.0,65.4 268.0,54.7 322.0,56.1" fill="none" stroke="#1b7a34" stroke-width="1.5"/>
<circle cx="52.0" cy="112.3" r="2.1" fill="#1b7a34"/>
<circle cx="106.0" cy="68.2" r="2.1" fill="#1b7a34"/>
<circle cx="160.0" cy="71.6" r="2.1" fill="#1b7a34"/>
<circle cx="214.0" cy="65.4" r="2.1" fill="#1b7a34"/>
<circle cx="268.0" cy="54.7" r="2.1" fill="#1b7a34"/>
<circle cx="322.0" cy="56.1" r="2.1" fill="#1b7a34"/>
<text x="58" y="34" font-size="6.8" fill="#8d99a6" font-weight="700">○ hypergeometric prediction</text>
<text x="58" y="44" font-size="6.8" fill="#1546a0" font-weight="700">● measured (2D-RS, BC ω1024 λ2 overlap)</text>
</svg>
<figcaption><b>Growing the network makes things slightly worse, up to a limit.</b> At 60% withholding and fixed replication 4, custodians are drawn without replacement, so in a small network it is combinatorially hard for all four custodians of a cell to be adversarial — with 8 peers only 5 are bad and there are few ways to choose 4 of them. As the network grows this constraint relaxes and the loss rate climbs toward the independent-sampling limit p⁴ = 0.130. The open markers are the exact hypergeometric probability, again computed rather than fitted; both schemes sit on it. The lesson for scalability claims is that what protects a cell is the <em>fraction</em> of the network custodying it, so peer count cannot be varied without saying what replication does too.</figcaption>
</figure>

## What the results show

**Decode dominates; the network barely registers.** Gathering takes
0.14–3.0 seconds. Decoding takes up to 466. At every parameter setting
tried, the bottleneck is arithmetic, not the link or the latency. Cutting
bandwidth fivefold, from 25 Mbps to 5 Mbps, moved 2D-RS's total from 32.1s
to 33.1s — a 3% change, because the extra second of transfer disappeared
next to 31 seconds of decode. At six blobs the spread is starker still:
every scheme gathers in about one second, while decode ranges from 0.0s to
354.1s.

That single finding reframes the comparison. The coding benchmark reported
decode cost as one column among several; placed in a slot budget it becomes
the only column that decides anything.

**1D-RS tolerates the most and delivers the least.** At 80% of peers
withholding — a realised erasure fraction of 0.400 — it is the only scheme
still recovering every trial, 30/30, where 2D-RS manages 20/30 and the
block-circulant rows collapse to 2/30 or worse. It needed 73.5 seconds to
do it, six times the slot. At six blobs it reconstructs 0.20 of them per
slot. Best fault tolerance in the study, worst throughput, and the two facts
have the same cause: one enormous polynomial division.

**Three block-circulant rows keep up with six blobs; nothing else does.**
The ω1024 rows at λ2, λ3 and λ4 all reconstruct all six, against
BC ω2048 λ2's 3.42, 2D-RS's 2.24 and 1D-RS's 0.20. Their decoders are the
weakest in the study — λ2 tolerates 0.33 where 1D-RS tolerates 0.50 — but
λ2 decodes roughly 33× faster (10.6s against 354.1s for the same six blobs),
and inside a deadline that trade is strongly favourable.

There is a visible progression inside those three rows, and it is a
bandwidth-for-compute trade. λ2 fetches 1326 KiB and decodes for 10.6s;
λ3 fetches 1474 KiB and decodes for 5.3s; λ4 fetches 1572 KiB and decodes
for 0.0s, because its tolerance is so low that it must fetch essentially the
whole codeword and then has nothing left to reconstruct. The weakest decoder
ends up doing no decoding at all — by paying for it on the wire.

**Network-level custody replication absorbs most peer failure before the
code is involved.** At 70% adversarial peers the realised erasure fraction
is only 0.237, because a cell dies only when all four of its custodians do.
The erasure code's tolerance is not the binding constraint until the
adversarial fraction is very high — which suggests custody replication and
code strength are substitutes, and that the cheaper one should be bought
first.

**More peers is not automatically safer, and can be worse.** Sweeping peer
count at fixed custody replication produced a result worth stating because
it runs against intuition. Custodians are drawn without replacement, so in a
small network it is combinatorially hard for all four custodians of a cell to
be adversarial: with 8 peers and 60% withholding only 5 peers are bad, and
there are just 5 ways to choose 4 of them out of 70. As the network grows
that constraint relaxes and the loss rate climbs toward the
independent-sampling limit p⁴. Measured erasure at 60% withholding runs
0.068 at 8 peers, 0.111 at 16, 0.114 at 64 and 0.123 at 256, against the
exact hypergeometric values 0.071, 0.115, 0.116 and 0.129 — agreement within
0.006 at every point. At 30% withholding 2D-RS took 0.33s with 8 peers and
1.73s with 64, entirely because the larger network lost more cells and
therefore had more to decode.

The lesson is that what protects a cell is not the peer count but the
*fraction of the network custodying it*. Growing the network while holding
replication fixed quietly dilutes that fraction. Any scalability claim about
node count has to say what happens to replication at the same time, or it is
not saying anything.

**A weaker decoder costs bandwidth as well as tolerance.** BC fetched
1326 KiB where 1D-RS fetched 1068 KiB for the same six blobs, because it
needs a larger surviving fraction to decode at all. At equal storage, the
scheme with the weaker decoder pays on the wire too — a cost the isolated
coding benchmark could not show.

## Validation, and two bugs it caught

The calibrated decode-cost model was checked against `--real-decode`, which
hands the emergent clustered mask to the actual decoders:

| point | calibrated | real |
|---|---|---|
| 2D-RS @ 40% adversarial | 3.18s | 2.28s |
| 2D-RS @ 60% | 4.80s | 2.65s |
| BC ω1024 λ2 @ 40% | 0.72s | 0.58s |
| BC ω1024 λ2 @ 60% | 2.21s | 2.02s |

Same order of magnitude, real slightly faster, and every trial recovered —
so clustered erasures at these levels decode as cleanly as i.i.d. ones.

Two errors surfaced this way and are fixed:

1. **Zero-erasure rounds invented work.** The cost curve was held flat at
   its lowest *measured* rate (0.02), so a round with nothing missing was
   charged several seconds of decoding. `--real-decode` reported 0.00s and
   exposed it.
2. **Gather time was reporting the deadline back.** The first version ran
   the environment to the deadline and reported `env.now`, which is the
   deadline by construction. It now records the moment the node actually
   held enough cells to start decoding.

## Limitations

**One topology.** The brief asks for "standard network architectures",
plural. This models a flat network with uniform random custody. Structured
overlays, clustered or geographically correlated latency, and churn are not
represented. This is the largest remaining gap.

**One-hop fetches only.** A node requests cells directly from custodians.
There is no gossip propagation, no forwarding, no upload-side cost — so
this measures a node's *download* experience, not network-wide load.

**Decode cost is Python-speed.** Stated above and worth restating: absolute
timings are two to three orders of magnitude off production, which is what
`--speedup` exists for. Relative comparisons hold.

**Statistical treatment is lighter than the coding benchmark's.** 8–10
trials per point with no confidence intervals, against the benchmark's
Wilson intervals and per-scheme trial budgets. Adequate for the size of the
effects being reported here — a 30× throughput gap does not need a
confidence interval — but it should be tightened before any close call is
claimed.

## Running it

```
pip install simpy galois numpy

python3 network_sim.py                                   # defaults
python3 network_sim.py --blobs 6 --downlink 25           # bandwidth pressure
python3 network_sim.py --peers 8,16,64,256               # sweep network size
python3 network_sim.py --real-decode --trials 3          # ground truth
python3 network_sim.py --speedup 100                     # production arithmetic
python3 network_sim.py --figures figs.md                 # SVG, docs-styled
python3 network_sim.py --json results.json               # machine-readable
python3 network_sim.py --no-visuals                      # table only
```

`--peers` and `--adversarial` both accept comma-separated lists and are
swept as a cross product with the scheme list, so a single invocation can
cover scheme x network size x adversarial pressure.

### What it draws

Every run prints three terminal views beneath the results table, because
the table alone buries the one thing that matters:

* **Throughput** — a bar per configuration, blobs reconstructed per slot.
* **Where the time goes** — gather and decode as one stacked bar per
  configuration, with a marker showing where the 12-second slot falls. This
  is the figure that makes the central finding obvious at a glance: the
  network segment is a sliver and the arithmetic segment is everything. A
  segment that rounds to zero width is still drawn one cell wide, so
  "too small to see" stays distinguishable from "absent".
* **Recovery grid** — scheme x peer count against adversarial fraction,
  marked ● all trials recovered, ◐ some, ○ none.

`--figures out.md` writes the first two as inline SVG in the same style as
the rest of `docs/`, so they can be pasted into the write-up directly.

Scheme names match `benchmark_results.json`, so every parameterisation the
coding benchmark measured can be driven through the network layer without
touching either file.
