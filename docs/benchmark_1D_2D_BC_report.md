# Benchmarking 1D-RS, 2D-RS, and Block-Circulant codes

A controlled comparison of erasure-coding schemes as candidates for
Ethereum's data-availability sampling: one-dimensional Reed-Solomon (what
PeerDAS uses today), two-dimensional Reed-Solomon, and Block-Circulant
(BC) codes at five parameterisations. All of them run over the same
field, on the same blob, under the same erasure model, and are judged by
the same success criterion.

The question each scheme has to answer is the same: **if a fraction of the
encoded data goes missing, can the original blob still be reconstructed
exactly — and what did that cost in storage and in decode time?**

This revision changes two things, both following supervisor guidance of
2026-09-15 and both aimed at making the comparison fair rather than at
making any scheme look better.

**2D-RS moves from an 88×88 grid to 88×96**, putting its rate at 0.485
against the others' 0.500 — the closest any grid reachable in this field
gets to 0.5, and a correction of the previous 0.529. The natural-looking
90×90 turns out to be unbuildable here, for a reason worth stating up
front because it is easy to miss: a length-*n* NTT needs *n* to divide
*p*−1, and 90 = 2·3²·5 needs both a 3² (this field's *p*−1 carries only
3¹) and a 5 (absent entirely).

**The BC rows move from λ = μ to λ ∈ {2, 3}**, with one λ = 4 row kept as
an anchor. The previous set swept λ = μ at μ = 4, 8, 16, which measured
the same extreme three times and pushed the decoder's reach down to 0.059.
λ = 16 is not implementable, and the source paper's algorithms assume
λ = 2, so the sweep now sits where the construction actually lives. This
turns out to matter a great deal: the best BC row now tolerates 0.35
rather than 0.20.

The practical effect of both changes is that every scheme in the table
below stores within 3% of twice its blob, so differences in what they
tolerate are differences between the codes and their decoders, not
between their budgets.

## How the code works

The whole experiment is five moving parts. Each is a separate file, and
the benchmark drives them without reimplementing any of their logic.

**Packing a blob (`blob_generator.py`).** An Ethereum blob is 4096 field
elements of the BLS12-381 scalar field. Each element is 32 bytes on the
wire but only 31 are usable, because the value must stay below the field
modulus — so one blob carries 126,976 bytes of application data. This is
the unit everything else operates on: a list of 4096 field elements, and a
function to turn it back into the original bytes.

**1D-RS (`1D_RS_Galois.py`).** The key idea is that the blob's 4096
elements are not raw data to be copied — they are the *values of a single
polynomial* sampled at 4096 fixed points. Encoding recovers that
polynomial (an inverse NTT turns 4096 values into 4096 coefficients),
pads it with zeros, and evaluates it again at 8192 points (a forward NTT).
The result is 8192 symbols describing the same polynomial. Since a
polynomial of degree below 4096 is pinned down by *any* 4096 of its
values, any 4096 surviving symbols reconstruct everything. Decoding builds
an erasure-locator polynomial whose roots sit exactly at the missing
positions, multiplies through by it, inverts the transform, and divides
the locator back out — recovering the original polynomial in one pass.
Crucially it first checks whether the number of erasures exceeds `n-k`;
if so it gives up immediately rather than attempting anything.

**2D-RS (`2D_RS_Galois.py`).** The same interpolate-and-extend step,
applied twice. The blob is reshaped into a 64×64 grid; every row is
extended, then every column of that result is extended. Because the
original grid is a single bivariate polynomial, every row *and* every
column of the result is independently a valid 1D-RS codeword. Decoding
exploits this: it sweeps all columns, then all rows, repeatedly. A line
holding too many erasures to fix alone often becomes fixable once the
perpendicular sweep has repaired some of its cells, so repairs cascade
across the two axes until nothing more can be done.

What changed here is the extension factor, twice. A product code's rate is
the *product* of its two component rates, so doubling both axes — the
original 64→128 setting — gives rate 1/4 and 4× storage. That made the
first comparison unfair: 2D-RS was being judged at the same erasure rate
as codes spending half as much. The fix is to pick the component rate so
that its square lands on 0.5: each axis should extend 64 → 64/√0.5 = 90.5,
which is where the "64 × √2 ≈ 90, so use 90×90" suggestion comes from.
The reasoning is right; the number is unavailable.

A length-*n* NTT exists only if *n* divides *p*−1, and for the BLS12-381
scalar field

> *p* − 1 = 2³² · 3 · 11 · 19 · 10177 · 125527 · 859267 · 906349² · 2508409 · 2529403 · …

90 = 2 · 3² · 5 needs a 3² where only 3¹ is available, and a 5 that does
not appear at all. There is no length-90 NTT here, so no 90×90 grid. The
reachable lengths above 64 are 66, 76, 88, 96, 114, 128, 132, … — and 88
and 96 bracket the 90.5 target from either side, with geometric mean
√8448 = 91.9 sitting close to it. Component codes need not be equal, so
the grid is now **88 × 96**: component rates 64/96 = 0.667 and 64/88 =
0.727, overall 4096/8448 = **0.485** at 2.06× storage. That is the closest
to 0.5 of any reachable pair. The previous 88×88 gave 0.529 at 1.89×,
further off on both counts *and* cheaper than the codes it was compared
against.

Exactly 0.5 is unreachable regardless: it would need the codeword to be
8192 cells, a power of two forces both grid dimensions to be powers of
two, and each axis must at least double to carry any parity at all —
which lands on 16384, not 8192.

**Block-Circulant (`BCcodeEthereum.py`).** Structurally different: instead
of one global polynomial, the message is cut into μ small blocks of ω
symbols, and each block gets ρ parity symbols computed from its own
information plus that of λ consecutive neighbours, wrapped around a ring.
Overhead is 2×, the same as 1D-RS.

The parameterisation matters more than it first appears, and λ turns out
to be the parameter that matters. Two quantities move in *opposite*
directions as it changes:

- The **code's** guarantee. Minimum distance is *d* = λρ + 1, so the
  fraction of erasures it survives against *any* pattern is
  (*d*−1)/*n* = λρ/*n*. This **rises** with λ.
- The **decoder's** reach. `DecCBC[2]` resolves a local block when the
  erasures landing in its support of N₀ = λω + ρ symbols number at most
  ρ, i.e. while the erasure rate is under ρ/N₀ = 1/(1+λ) when ρ = ω.
  This **falls** with λ.

So a larger λ buys a better code and a worse decoder. λ = μ is the
extreme: *d* reaches 4097 = *n* − *k* + 1, the Singleton bound, making the
code MDS — exactly as good as Reed-Solomon — while the decoder's reach
bottoms out at 1/(1+μ).

That is what the previous revision swept, at μ = 4, 8, 16: three MDS codes
whose decoders reached 0.200, 0.111 and 0.059. It measured the same
extreme three times and never sampled the regime the construction is for.
Supervisor guidance is that `DecCBC` is practical only to λ = 3, that
λ = 16 is not implementable, and that analysis belongs at λ = 2 and 3 —
which is also where the source paper sits, as the next section shows. The
rows swept here follow that, keeping one λ = 4 row as the MDS anchor.

Note what that produces: **ω2048 λ2 and ω1024 λ4 are both MDS with
*d* = 4097 — identical as codes — yet their decoders reach 0.34 and 0.20.**
Same code quality, different reach, from λ alone. Separating the code from
the decoder is what this sweep measures, and that pair is the cleanest
statement of it.

### Checking the parameters against the source

The BC construction comes from Sasidharan, Viterbo and Feist, *Block
Circulant Codes for Ethereum PeerDAS* (ePrint 2026/708). Its notation
table matches this implementation exactly — [N₀, K₀] = [λω + ρ, λω],
[*n*, *k*] = [μ(ω+ρ), μω], *R* = ω/(ω+ρ), *S* = λρ/*n*, S₀ = ρ/N₀ — which
is worth recording, because two of those are the quantities this report
now reports and one of them was derived here independently before the
paper was consulted:

- The paper's **stopping rate** *S* = λρ/*n* is precisely the (*d*−1)/*n*
  erasure tolerance used throughout below.
- The paper's **local stopping rate** S₀ = ρ/N₀ is precisely the decoder
  reach predicted above. The prediction and the paper's definition are the
  same quantity, arrived at separately.

Two further points from it bear on the rows chosen here. First, the paper
**fixes λ = 2** for its encoding and reconstruction algorithms and for its
entire performance analysis, and states the λρ erasure-correction result
for **λ = 2, 3 only**. The λ = 2 rows therefore sit exactly where the
paper does, the λ = 3 row sits at the edge of its stated range, and the
λ = 4 row is outside it — its *d* = 4097 extrapolates a formula past where
it was proved, which is another reason to read it as an anchor rather than
a result.

Second, the paper's worked example is μ = 4, λ = 2, ρ = ω with **ω = 32
cells at stacking depth *D* = 64** — it counts ω and ρ in *cells*, not in
field symbols. Converting: a 4096-symbol blob at *D* = 64 is 64 cells, so
μ = 4 gives ω = 16 cells = **1024 field symbols**. The ω1024 λ2 row below
*is* the paper's worked configuration, expressed in symbols.

**The harness (`benchmark_1D_2D_BC.py`).** Each scheme is wrapped in a
small adapter exposing the same five operations — `encode`,
`random_mask`, `corrupt`, `decode`, `extract_message` — so the sweep loop
never needs to know that 2D-RS's codeword is a grid while BC's is a flat
vector. The adapters call the real functions in the files above; no coding
logic is duplicated, so fixing one of those files changes the benchmark's
results automatically.

## The experimental pipeline

Every measurement follows the same seven steps, and only two of them
differ between schemes:

1. **Generate** 126,976 random application bytes.
2. **Pack** them into one blob of 4096 field elements, the real EIP-4844
   way.
3. **Encode** — *scheme-specific* — expanding 4096 elements into a
   codeword of `n` elements.
4. **Erase** — withhold each codeword position independently with
   probability equal to the target rate, simulating samples that peers
   failed to provide.
5. **Decode** — *scheme-specific* — attempt to reconstruct the full
   codeword from what survived.
6. **Extract** the original 4096 elements back out of the recovered
   codeword.
7. **Verify** by unpacking to bytes and comparing against step 1.

Steps 1, 2, 4, 6 and 7 are byte-identical across every scheme. That is
what makes the comparison fair: any difference in the results has to come
from step 3 or step 5, which is precisely what is being compared.

Step 7 is the one worth dwelling on. Success is defined as *the recovered
bytes equal the original bytes* — not as "the decoder reported success",
and not even as "the field elements matched". That distinction is not
pedantry: one of these decoders turned out to report success on data it
had silently corrupted, and only the byte comparison caught it.

## What is held identical

- **Field** — the real BLS12-381 scalar field.
- **Message** — the same 4096 elements, packed from the same bytes, fed to
  every encoder. Not one random blob per scheme.
- **Erasure model** — independent per-position withholding at a shared
  target rate. 1D-RS and all five BC rows share `n = 8192`, so on each
  trial they are corrupted at the *same literal positions*, not merely the
  same rate. 2D-RS has `n = 8448` and draws its own masks at the same rate.
- **Success criterion** — the full byte-level round trip described above.

Storage is matched to within 3%: 2.00× for 1D-RS and every BC row, 2.06×
for 2D-RS. The small residual difference is reported rather than
controlled away, and it runs *against* 2D-RS rather than for it.

## Method

Erasure rates are swept from 2% to 55%. Trial counts vary by scheme and
rate: a scheme decoding against a formal budget check behaves
deterministically well away from its threshold, so one trial there is
representative, while near a threshold the outcome genuinely varies from
draw to draw and needs several. Trials are therefore concentrated around
each scheme's own transition — which is not the same rate for all of them.
Each success rate carries a 95% Wilson confidence interval.

## Code parameters and storage cost

All of them carry the same 124 KiB blob payload; they differ in how much
they store to protect it. `R = k/n` is the code rate, and `1-R` is the
largest erasure fraction *any* code of that rate could survive. The two
rows the supervisor asked for — **N₀ and K₀, the component (local) code
length and dimension** — are included: for 1D-RS the global code is the
only code, for 2D-RS the component is one axis (the row axis is shown;
the column axis is [88, 64]), and for BC it is one local block.

Note the gap between the last two rows for 2D-RS. Its minimum distance is
the *product* of its component distances, 33 × 25 = 825, so its guarantee
is 0.098 — nowhere near the 0.515 its rate would permit. A product code is
never MDS; that is the structural price of two-axis locality. Comparing
2D-RS against 1−*R*, as the previous revision did, measured it against a
bound its construction cannot reach.

|  | 1D-RS | 2D-RS | BC ω2048 λ2 | BC ω1024 λ2 | BC ω512 λ2 | BC ω1024 λ3 | BC ω1024 λ4 |
|---|---|---|---|---|---|---|---|
| Message *k* | 4096 | 4096 | 4096 | 4096 | 4096 | 4096 | 4096 |
| Codeword *n* | 8192 | 8448 | 8192 | 8192 | 8192 | 8192 | 8192 |
| Code rate *R* | 0.500 | 0.485 | 0.500 | 0.500 | 0.500 | 0.500 | 0.500 |
| Storage overhead | 2.00&times; | 2.06&times; | 2.00&times; | 2.00&times; | 2.00&times; | 2.00&times; | 2.00&times; |
| Stored per blob | 256 KiB | 264 KiB | 256 KiB | 256 KiB | 256 KiB | 256 KiB | 256 KiB |
| Component **N&#8320;** | 8192 | 96 | 6144 | 3072 | 1536 | 4096 | 5120 |
| Component **K&#8320;** | 4096 | 64 | 4096 | 2048 | 1024 | 3072 | 4096 |
| Min. distance *d* | 4097 | 825 | 4097 | 2049 | 1025 | 3073 | 4097 |
| Guarantee (*d*&minus;1)/*n* | 0.500 | 0.098 | 0.500 | 0.250 | 0.125 | 0.375 | 0.500 |
| Rate bound 1&minus;*R* | 0.500 | 0.515 | 0.500 | 0.500 | 0.500 | 0.500 | 0.500 |

The five Block-Circulant rows differ in how the same 4096 message symbols
are cut into blocks and in how far the blocks overlap. Every row sets
&rho; = &omega;, which fixes *n* = 2*k* = 8192 and rate 0.5 throughout, so
&lambda; and &mu; are the only things varying. Read the last three rows
together: the *predicted* decoder reach S&#8320; and what was *measured*
agree at every point, and both are governed by &lambda; rather than by
&omega; or &mu;.

| | BC ω2048 λ2 | BC ω1024 λ2 | BC ω512 λ2 | BC ω1024 λ3 | BC ω1024 λ4 |
|---|---|---|---|---|---|
| Information/block &omega; | 2048 | 1024 | 512 | 1024 | 1024 |
| Parity/block &rho; | 2048 | 1024 | 512 | 1024 | 1024 |
| Local blocks &mu; | 2 | 4 | 8 | 4 | 4 |
| Overlap &lambda; | 2 | 2 | 2 | 3 | 4 |
| Local length N&#8320; | 6144 | 3072 | 1536 | 4096 | 5120 |
| Local dim K&#8320; | 4096 | 2048 | 1024 | 3072 | 4096 |
| Local rate R&#8320; | 0.667 | 0.667 | 0.667 | 0.750 | 0.800 |
| Min. distance *d* | 4097 | 2049 | 1025 | 3073 | 4097 |
| Stopping rate *S* | 0.500 | 0.250 | 0.125 | 0.375 | 0.500 |
| Predicted S&#8320; = &rho;/N&#8320; | 0.333 | 0.333 | 0.333 | 0.250 | 0.200 |
| **Measured** | **0.34** | **0.35** | **0.35** | **0.28** | **0.20** |
| Local solve size | 2048&times;2048 | 1024&times;1024 | 512&times;512 | 1024&times;1024 | 1024&times;1024 |

Encode and decode cost, from the same run. Decode times are the mean
over trials that actually recovered the blob; a dash means nothing
recovered at that rate, so there is no decode time to report.

|  | 1D-RS | 2D-RS | BC ω2048 λ2 | BC ω1024 λ2 | BC ω512 λ2 | BC ω1024 λ3 | BC ω1024 λ4 |
|---|---|---|---|---|---|---|---|
| Encode | 0.46s | 2.65s | 14.16s | 6.65s | 3.56s | 7.86s | 9.00s |
| Decode @ 2% | 5.18s | 2.44s | 0.41s | 0.24s | 0.15s | 0.30s | 0.38s |
| Decode @ 5% | 11.10s | 3.11s | 0.98s | 0.54s | 0.32s | 0.69s | 0.85s |
| Decode @ 10% | 20.55s | 3.35s | 2.01s | 1.09s | 0.63s | 1.39s | 1.70s |
| Decode @ 20% | 40.36s | 5.08s | 4.43s | 2.33s | 1.32s | 2.96s | 3.61s |
| Decode @ 30% | 56.94s | 4.50s | 7.15s | 3.71s | 2.08s | &mdash; | &mdash; |
| Decode @ 35% | 63.25s | 5.85s | &mdash; | 4.30s | 2.43s | &mdash; | &mdash; |
| Decode @ 48% | 81.77s | &mdash; | &mdash; | &mdash; | &mdash; | &mdash; | &mdash; |

## Results

Recovered trials at each erasure rate. Trial counts differ by scheme
and by rate — more where a scheme is near its own threshold and the
outcome genuinely varies, fewer where it does not — so each cell shows
recovered/attempted rather than a bare percentage.

| erasure rate | 1D-RS | 2D-RS | BC ω2048 λ2 | BC ω1024 λ2 | BC ω512 λ2 | BC ω1024 λ3 | BC ω1024 λ4 |
|---|---|---|---|---|---|---|---|
| 2% | 1/1 | 3/3 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| 5% | 1/1 | 3/3 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| 8% | 1/1 | 3/3 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| 10% | 1/1 | 3/3 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| 12% | 1/1 | 3/3 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| 15% | 1/1 | 3/3 | 4/4 | 4/4 | 4/4 | 4/4 | 8/8 |
| 20% | 1/1 | 3/3 | 4/4 | 4/4 | 4/4 | 8/8 | 5/8 |
| 25% | 1/1 | 3/3 | 4/4 | 4/4 | 4/4 | 8/8 | 0/8 |
| 30% | 1/1 | 3/3 | 8/8 | 8/8 | 8/8 | 0/8 | 0/4 |
| 33% | 1/1 | 3/3 | 8/8 | 8/8 | 8/8 | 0/4 | 0/4 |
| 35% | 1/1 | 3/3 | 0/8 | 1/8 | 4/8 | 0/4 | 0/4 |
| 38% | 2/2 | 5/5 | 0/8 | 0/8 | 0/8 | 0/4 | 0/4 |
| 40% | 2/2 | 2/5 | 0/4 | 0/4 | 0/4 | 0/4 | 0/4 |
| 45% | 2/2 | 0/5 | 0/4 | 0/4 | 0/4 | 0/4 | 0/4 |
| 48% | 3/3 | 0/3 | 0/4 | 0/4 | 0/4 | 0/4 | 0/4 |
| 50% | 2/3 | 0/3 | 0/4 | 0/4 | 0/4 | 0/4 | 0/4 |
| 52% | 0/3 | 0/3 | 0/4 | 0/4 | 0/4 | 0/4 | 0/4 |
| 55% | 0/2 | 0/3 | 0/4 | 0/4 | 0/4 | 0/4 | 0/4 |

Across all 520 trials, no scheme returned corrupted data while reporting
success: silent corruption was zero everywhere (0/28 for 1D-RS, 0/60 for
2D-RS, and 0/88, 0/88, 0/88, 0/84, 0/84 across the five BC rows). Before
the decoder fix described below, BC's figure was 31 of 40.

<figure>
<svg viewBox="0 0 500 260" role="img" aria-label="Measured erasure tolerance for each scheme beside its own minimum-distance guarantee and the rate bound. 1D-RS reaches its bound; 2D-RS and the lambda=2 block circulant rows exceed their own guarantees.">
<line x1="52" y1="30" x2="52" y2="196" stroke="currentColor" stroke-width="0.8"/>
<line x1="52" y1="196" x2="492" y2="196" stroke="currentColor" stroke-width="0.8"/>
<line x1="49" y1="196.0" x2="52" y2="196.0" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="196.0" x2="492" y2="196.0" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="198.5" text-anchor="end" font-size="7">0.0</text>
<line x1="49" y1="168.3" x2="52" y2="168.3" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="168.3" x2="492" y2="168.3" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="170.8" text-anchor="end" font-size="7">0.1</text>
<line x1="49" y1="140.7" x2="52" y2="140.7" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="140.7" x2="492" y2="140.7" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="143.2" text-anchor="end" font-size="7">0.2</text>
<line x1="49" y1="113.0" x2="52" y2="113.0" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="113.0" x2="492" y2="113.0" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="115.5" text-anchor="end" font-size="7">0.3</text>
<line x1="49" y1="85.3" x2="52" y2="85.3" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="85.3" x2="492" y2="85.3" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="87.8" text-anchor="end" font-size="7">0.4</text>
<line x1="49" y1="57.7" x2="52" y2="57.7" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="57.7" x2="492" y2="57.7" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="60.2" text-anchor="end" font-size="7">0.5</text>
<line x1="49" y1="30.0" x2="52" y2="30.0" stroke="currentColor" stroke-width="0.7"/>
<line x1="52" y1="30.0" x2="492" y2="30.0" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="46" y="32.5" text-anchor="end" font-size="7">0.6</text>
<rect x="68.4" y="57.7" width="13" height="138.3" fill="none" stroke="#c62828" stroke-width="0.8" stroke-dasharray="2,1.6" opacity="0.8"/>
<rect x="68.4" y="57.7" width="13" height="138.3" fill="#c62828" opacity="0.22"/>
<rect x="84.4" y="57.7" width="13" height="138.3" fill="#c62828" opacity="0.9"/>
<text x="90.9" y="54.7" text-anchor="middle" font-size="7" font-weight="700" fill="#c62828">0.50</text>
<text x="83.4" y="207.0" text-anchor="middle" font-size="6.6" font-weight="700">1D-RS</text>
<text x="83.4" y="216.0" text-anchor="middle" font-size="6" fill="#5b6572">2.00×</text>
<rect x="131.3" y="53.5" width="13" height="142.5" fill="none" stroke="#1546a0" stroke-width="0.8" stroke-dasharray="2,1.6" opacity="0.8"/>
<rect x="131.3" y="169.0" width="13" height="27.0" fill="#1546a0" opacity="0.22"/>
<rect x="147.3" y="81.2" width="13" height="114.8" fill="#1546a0" opacity="0.9"/>
<text x="153.8" y="78.2" text-anchor="middle" font-size="7" font-weight="700" fill="#1546a0">0.42</text>
<text x="146.3" y="207.0" text-anchor="middle" font-size="6.6" font-weight="700">2D-RS</text>
<text x="146.3" y="216.0" text-anchor="middle" font-size="6" fill="#5b6572">2.06×</text>
<rect x="194.1" y="57.7" width="13" height="138.3" fill="none" stroke="#14532d" stroke-width="0.8" stroke-dasharray="2,1.6" opacity="0.8"/>
<rect x="194.1" y="57.7" width="13" height="138.3" fill="#14532d" opacity="0.22"/>
<rect x="210.1" y="101.9" width="13" height="94.1" fill="#14532d" opacity="0.9"/>
<text x="216.6" y="98.9" text-anchor="middle" font-size="7" font-weight="700" fill="#14532d">0.34</text>
<text x="209.1" y="207.0" text-anchor="middle" font-size="6.6" font-weight="700">BC 2048 λ2</text>
<text x="209.1" y="216.0" text-anchor="middle" font-size="6" fill="#5b6572">2.00×</text>
<rect x="257.0" y="57.7" width="13" height="138.3" fill="none" stroke="#1b7a34" stroke-width="0.8" stroke-dasharray="2,1.6" opacity="0.8"/>
<rect x="257.0" y="126.8" width="13" height="69.2" fill="#1b7a34" opacity="0.22"/>
<rect x="273.0" y="97.8" width="13" height="98.2" fill="#1b7a34" opacity="0.9"/>
<text x="279.5" y="94.8" text-anchor="middle" font-size="7" font-weight="700" fill="#1b7a34">0.35</text>
<text x="272.0" y="207.0" text-anchor="middle" font-size="6.6" font-weight="700">BC 1024 λ2</text>
<text x="272.0" y="216.0" text-anchor="middle" font-size="6" fill="#5b6572">2.00×</text>
<rect x="319.9" y="57.7" width="13" height="138.3" fill="none" stroke="#5aab74" stroke-width="0.8" stroke-dasharray="2,1.6" opacity="0.8"/>
<rect x="319.9" y="161.4" width="13" height="34.6" fill="#5aab74" opacity="0.22"/>
<rect x="335.9" y="97.8" width="13" height="98.2" fill="#5aab74" opacity="0.9"/>
<text x="342.4" y="94.8" text-anchor="middle" font-size="7" font-weight="700" fill="#5aab74">0.35</text>
<text x="334.9" y="207.0" text-anchor="middle" font-size="6.6" font-weight="700">BC 512 λ2</text>
<text x="334.9" y="216.0" text-anchor="middle" font-size="6" fill="#5b6572">2.00×</text>
<rect x="382.7" y="57.7" width="13" height="138.3" fill="none" stroke="#b45309" stroke-width="0.8" stroke-dasharray="2,1.6" opacity="0.8"/>
<rect x="382.7" y="92.2" width="13" height="103.8" fill="#b45309" opacity="0.22"/>
<rect x="398.7" y="119.9" width="13" height="76.1" fill="#b45309" opacity="0.9"/>
<text x="405.2" y="116.9" text-anchor="middle" font-size="7" font-weight="700" fill="#b45309">0.28</text>
<text x="397.7" y="207.0" text-anchor="middle" font-size="6.6" font-weight="700">BC 1024 λ3</text>
<text x="397.7" y="216.0" text-anchor="middle" font-size="6" fill="#5b6572">2.00×</text>
<rect x="445.6" y="57.7" width="13" height="138.3" fill="none" stroke="#7c2d92" stroke-width="0.8" stroke-dasharray="2,1.6" opacity="0.8"/>
<rect x="445.6" y="57.7" width="13" height="138.3" fill="#7c2d92" opacity="0.22"/>
<rect x="461.6" y="140.7" width="13" height="55.3" fill="#7c2d92" opacity="0.9"/>
<text x="468.1" y="137.7" text-anchor="middle" font-size="7" font-weight="700" fill="#7c2d92">0.20</text>
<text x="460.6" y="207.0" text-anchor="middle" font-size="6.6" font-weight="700">BC 1024 λ4</text>
<text x="460.6" y="216.0" text-anchor="middle" font-size="6" fill="#5b6572">2.00×</text>
<rect x="52" y="8" width="9" height="7" fill="#555" opacity="0.9"/>
<text x="65" y="14.5" font-size="6.4">measured</text>
<rect x="122" y="8" width="9" height="7" fill="#555" opacity="0.22"/>
<text x="135" y="14.5" font-size="6.4">its own guarantee (d−1)/n</text>
<rect x="272" y="8" width="9" height="7" fill="none" stroke="#555" stroke-width="0.8" stroke-dasharray="2,1.6"/>
<text x="285" y="14.5" font-size="6.4">rate bound 1−R</text>
<text x="11" y="113" text-anchor="middle" font-size="7.2" transform="rotate(-90 11 113)">erasure rate tolerated</text>
</svg>
<figcaption>What each scheme actually tolerated (solid), beside its own minimum-distance guarantee (pale) and the rate bound 1&minus;<em>R</em> that no code of that rate can beat (dashed). Storage is matched to within 3%, so the bars read against each other directly. 1D-RS lands exactly on its bound &mdash; that is what being MDS means. Three schemes sit <em>above</em> their own guarantee: 2D-RS at more than four times it, and both &lambda;=2 block-circulant rows with &mu;&gt;2. That is not a contradiction &mdash; a guarantee holds against every pattern including the adversarial worst case, while these trials draw patterns at random. Solid bars are the midpoint of the measured transition.</figcaption>
</figure>

<figure>
<svg viewBox="0 0 470 250" role="img" aria-label="Block circulant decoder threshold against the prediction one over one plus lambda. All three lambda equals two rows land together near 0.34 despite differing mu and omega, while lambda three and four fall to 0.27 and 0.20.">
<line x1="50" y1="34" x2="50" y2="186" stroke="currentColor" stroke-width="0.8"/>
<line x1="50" y1="186" x2="460" y2="186" stroke="currentColor" stroke-width="0.8"/>
<line x1="47" y1="186.0" x2="50" y2="186.0" stroke="currentColor" stroke-width="0.7"/>
<line x1="50" y1="186.0" x2="460" y2="186.0" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="44" y="188.5" text-anchor="end" font-size="7">0.0</text>
<line x1="47" y1="158.4" x2="50" y2="158.4" stroke="currentColor" stroke-width="0.7"/>
<line x1="50" y1="158.4" x2="460" y2="158.4" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="44" y="160.9" text-anchor="end" font-size="7">0.1</text>
<line x1="47" y1="130.7" x2="50" y2="130.7" stroke="currentColor" stroke-width="0.7"/>
<line x1="50" y1="130.7" x2="460" y2="130.7" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="44" y="133.2" text-anchor="end" font-size="7">0.2</text>
<line x1="47" y1="103.1" x2="50" y2="103.1" stroke="currentColor" stroke-width="0.7"/>
<line x1="50" y1="103.1" x2="460" y2="103.1" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="44" y="105.6" text-anchor="end" font-size="7">0.3</text>
<line x1="47" y1="75.5" x2="50" y2="75.5" stroke="currentColor" stroke-width="0.7"/>
<line x1="50" y1="75.5" x2="460" y2="75.5" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="44" y="78.0" text-anchor="end" font-size="7">0.4</text>
<line x1="47" y1="47.8" x2="50" y2="47.8" stroke="currentColor" stroke-width="0.7"/>
<line x1="50" y1="47.8" x2="460" y2="47.8" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="44" y="50.3" text-anchor="end" font-size="7">0.5</text>
<line x1="50" y1="47.8" x2="460" y2="47.8" stroke="#c62828" stroke-width="1" stroke-dasharray="3,2"/>
<text x="54" y="44.8" font-size="6.4" fill="#c62828" font-weight="700">0.50 — the rate bound</text>
<rect x="78.0" y="92.0" width="26" height="94.0" fill="#14532d" opacity="0.85"/>
<line x1="91.0" y1="94.8" x2="91.0" y2="89.3" stroke="#1b1f24" stroke-width="0.9"/>
<line x1="87.0" y1="94.8" x2="95.0" y2="94.8" stroke="#1b1f24" stroke-width="0.9"/>
<line x1="87.0" y1="89.3" x2="95.0" y2="89.3" stroke="#1b1f24" stroke-width="0.9"/>
<circle cx="91.0" cy="93.9" r="3.2" fill="#ffffff" stroke="#c62828" stroke-width="1.3"/>
<text x="91.0" y="83.3" text-anchor="middle" font-size="7" font-weight="700" fill="#14532d">0.34</text>
<text x="91.0" y="198.0" text-anchor="middle" font-size="7.2" font-weight="700">λ=2</text>
<text x="91.0" y="207.0" text-anchor="middle" font-size="6.2" fill="#5b6572">μ=2, ω=2048</text>
<text x="91.0" y="216.0" text-anchor="middle" font-size="6.2" fill="#5b6572">N₀=6144</text>
<rect x="160.0" y="87.9" width="26" height="98.1" fill="#1b7a34" opacity="0.85"/>
<line x1="173.0" y1="94.8" x2="173.0" y2="81.0" stroke="#1b1f24" stroke-width="0.9"/>
<line x1="169.0" y1="94.8" x2="177.0" y2="94.8" stroke="#1b1f24" stroke-width="0.9"/>
<line x1="169.0" y1="81.0" x2="177.0" y2="81.0" stroke="#1b1f24" stroke-width="0.9"/>
<circle cx="173.0" cy="93.9" r="3.2" fill="#ffffff" stroke="#c62828" stroke-width="1.3"/>
<text x="173.0" y="75.0" text-anchor="middle" font-size="7" font-weight="700" fill="#1b7a34">0.35</text>
<text x="173.0" y="198.0" text-anchor="middle" font-size="7.2" font-weight="700">λ=2</text>
<text x="173.0" y="207.0" text-anchor="middle" font-size="6.2" fill="#5b6572">μ=4, ω=1024</text>
<text x="173.0" y="216.0" text-anchor="middle" font-size="6.2" fill="#5b6572">N₀=3072</text>
<rect x="242.0" y="87.9" width="26" height="98.1" fill="#5aab74" opacity="0.85"/>
<line x1="255.0" y1="94.8" x2="255.0" y2="81.0" stroke="#1b1f24" stroke-width="0.9"/>
<line x1="251.0" y1="94.8" x2="259.0" y2="94.8" stroke="#1b1f24" stroke-width="0.9"/>
<line x1="251.0" y1="81.0" x2="259.0" y2="81.0" stroke="#1b1f24" stroke-width="0.9"/>
<circle cx="255.0" cy="93.9" r="3.2" fill="#ffffff" stroke="#c62828" stroke-width="1.3"/>
<text x="255.0" y="75.0" text-anchor="middle" font-size="7" font-weight="700" fill="#5aab74">0.35</text>
<text x="255.0" y="198.0" text-anchor="middle" font-size="7.2" font-weight="700">λ=2</text>
<text x="255.0" y="207.0" text-anchor="middle" font-size="6.2" fill="#5b6572">μ=8, ω=512</text>
<text x="255.0" y="216.0" text-anchor="middle" font-size="6.2" fill="#5b6572">N₀=1536</text>
<rect x="324.0" y="110.0" width="26" height="76.0" fill="#b45309" opacity="0.85"/>
<line x1="337.0" y1="116.9" x2="337.0" y2="103.1" stroke="#1b1f24" stroke-width="0.9"/>
<line x1="333.0" y1="116.9" x2="341.0" y2="116.9" stroke="#1b1f24" stroke-width="0.9"/>
<line x1="333.0" y1="103.1" x2="341.0" y2="103.1" stroke="#1b1f24" stroke-width="0.9"/>
<circle cx="337.0" cy="116.9" r="3.2" fill="#ffffff" stroke="#c62828" stroke-width="1.3"/>
<text x="337.0" y="97.1" text-anchor="middle" font-size="7" font-weight="700" fill="#b45309">0.28</text>
<text x="337.0" y="198.0" text-anchor="middle" font-size="7.2" font-weight="700">λ=3</text>
<text x="337.0" y="207.0" text-anchor="middle" font-size="6.2" fill="#5b6572">μ=4, ω=1024</text>
<text x="337.0" y="216.0" text-anchor="middle" font-size="6.2" fill="#5b6572">N₀=4096</text>
<rect x="406.0" y="130.7" width="26" height="55.3" fill="#7c2d92" opacity="0.85"/>
<line x1="419.0" y1="144.5" x2="419.0" y2="116.9" stroke="#1b1f24" stroke-width="0.9"/>
<line x1="415.0" y1="144.5" x2="423.0" y2="144.5" stroke="#1b1f24" stroke-width="0.9"/>
<line x1="415.0" y1="116.9" x2="423.0" y2="116.9" stroke="#1b1f24" stroke-width="0.9"/>
<circle cx="419.0" cy="130.7" r="3.2" fill="#ffffff" stroke="#c62828" stroke-width="1.3"/>
<text x="419.0" y="110.9" text-anchor="middle" font-size="7" font-weight="700" fill="#7c2d92">0.20</text>
<text x="419.0" y="198.0" text-anchor="middle" font-size="7.2" font-weight="700">λ=4</text>
<text x="419.0" y="207.0" text-anchor="middle" font-size="6.2" fill="#5b6572">μ=4, ω=1024</text>
<text x="419.0" y="216.0" text-anchor="middle" font-size="6.2" fill="#5b6572">N₀=5120</text>
<circle cx="56" cy="16" r="3.2" fill="#ffffff" stroke="#c62828" stroke-width="1.3"/>
<text x="64" y="18.5" font-size="6.4">predicted S₀ = ρ/N₀ = 1/(1+λ)</text>
<line x1="220" y1="10" x2="220" y2="22" stroke="#1b1f24" stroke-width="0.9"/>
<text x="228" y="18.5" font-size="6.4">measured transition band</text>
<text x="11" y="110" text-anchor="middle" font-size="7.2" transform="rotate(-90 11 110)">erasure rate tolerated</text>
<text x="255" y="244" text-anchor="middle" font-size="7" fill="#5b6572">λ sets the threshold; μ and ω barely move it</text>
</svg>
<figcaption>The block-circulant parameter sweep, and the clearest single result here. The decoder's reach is set by &lambda; alone: all three &lambda;=2 rows land together at 0.34&ndash;0.35 despite &mu; ranging over 2, 4, 8 and &omega; over 2048, 1024, 512 &mdash; a factor of four in block size that moves the threshold by nothing. Raising &lambda; to 3 drops it to 0.28, and to 4 drops it to 0.20. The open markers are the prediction S&#8320; = &rho;/N&#8320; = 1/(1+&lambda;), which is the local code's stopping rate in the source paper's own notation; the bars are what was measured, and the two agree at every point.</figcaption>
</figure>

<figure>
<svg viewBox="0 0 420 270" role="img" aria-label="Mean decode time of successful decodes against erasure rate on a log scale. 1D-RS is an order of magnitude more expensive than every block circulant row at every rate.">
<line x1="46" y1="20" x2="46" y2="214" stroke="currentColor" stroke-width="0.8"/>
<line x1="46" y1="214" x2="300" y2="214" stroke="currentColor" stroke-width="0.8"/>
<line x1="43" y1="214.0" x2="46" y2="214.0" stroke="currentColor" stroke-width="0.7"/>
<line x1="46" y1="214.0" x2="300" y2="214.0" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="40" y="216.5" text-anchor="end" font-size="7">0.1</text>
<line x1="43" y1="149.3" x2="46" y2="149.3" stroke="currentColor" stroke-width="0.7"/>
<line x1="46" y1="149.3" x2="300" y2="149.3" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="40" y="151.8" text-anchor="end" font-size="7">1</text>
<line x1="43" y1="84.7" x2="46" y2="84.7" stroke="currentColor" stroke-width="0.7"/>
<line x1="46" y1="84.7" x2="300" y2="84.7" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="40" y="87.2" text-anchor="end" font-size="7">10</text>
<line x1="43" y1="20.0" x2="46" y2="20.0" stroke="currentColor" stroke-width="0.7"/>
<line x1="46" y1="20.0" x2="300" y2="20.0" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="40" y="22.5" text-anchor="end" font-size="7">100</text>
<line x1="46.0" y1="214" x2="46.0" y2="217" stroke="currentColor" stroke-width="0.7"/>
<text x="46.0" y="225" text-anchor="middle" font-size="7">0.0</text>
<line x1="92.2" y1="214" x2="92.2" y2="217" stroke="currentColor" stroke-width="0.7"/>
<text x="92.2" y="225" text-anchor="middle" font-size="7">0.1</text>
<line x1="138.4" y1="214" x2="138.4" y2="217" stroke="currentColor" stroke-width="0.7"/>
<text x="138.4" y="225" text-anchor="middle" font-size="7">0.2</text>
<line x1="184.5" y1="214" x2="184.5" y2="217" stroke="currentColor" stroke-width="0.7"/>
<text x="184.5" y="225" text-anchor="middle" font-size="7">0.3</text>
<line x1="230.7" y1="214" x2="230.7" y2="217" stroke="currentColor" stroke-width="0.7"/>
<text x="230.7" y="225" text-anchor="middle" font-size="7">0.4</text>
<line x1="276.9" y1="214" x2="276.9" y2="217" stroke="currentColor" stroke-width="0.7"/>
<text x="276.9" y="225" text-anchor="middle" font-size="7">0.5</text>
<polyline points="55.2,103.2 69.1,81.7 82.9,67.7 92.2,64.4 101.4,60.1 115.3,53.8 138.4,45.5 161.5,40.8 184.5,35.8 198.4,34.3 207.6,32.9 221.5,31.3 230.7,30.1 253.8,26.5 267.7,25.7 276.9,25.1" fill="none" stroke="#c62828" stroke-width="1.3"/>
<circle cx="55.2" cy="103.2" r="1.8" fill="#c62828"/>
<circle cx="69.1" cy="81.7" r="1.8" fill="#c62828"/>
<circle cx="82.9" cy="67.7" r="1.8" fill="#c62828"/>
<circle cx="92.2" cy="64.4" r="1.8" fill="#c62828"/>
<circle cx="101.4" cy="60.1" r="1.8" fill="#c62828"/>
<circle cx="115.3" cy="53.8" r="1.8" fill="#c62828"/>
<circle cx="138.4" cy="45.5" r="1.8" fill="#c62828"/>
<circle cx="161.5" cy="40.8" r="1.8" fill="#c62828"/>
<circle cx="184.5" cy="35.8" r="1.8" fill="#c62828"/>
<circle cx="198.4" cy="34.3" r="1.8" fill="#c62828"/>
<circle cx="207.6" cy="32.9" r="1.8" fill="#c62828"/>
<circle cx="221.5" cy="31.3" r="1.8" fill="#c62828"/>
<circle cx="230.7" cy="30.1" r="1.8" fill="#c62828"/>
<circle cx="253.8" cy="26.5" r="1.8" fill="#c62828"/>
<circle cx="267.7" cy="25.7" r="1.8" fill="#c62828"/>
<circle cx="276.9" cy="25.1" r="1.8" fill="#c62828"/>
<polyline points="55.2,124.2 69.1,117.5 82.9,116.1 92.2,115.4 101.4,114.8 115.3,113.8 138.4,103.7 161.5,101.2 184.5,107.1 198.4,98.2 207.6,99.7 221.5,99.0 230.7,98.2" fill="none" stroke="#1546a0" stroke-width="1.3" stroke-dasharray="5,2.5"/>
<circle cx="55.2" cy="124.2" r="1.8" fill="#1546a0"/>
<circle cx="69.1" cy="117.5" r="1.8" fill="#1546a0"/>
<circle cx="82.9" cy="116.1" r="1.8" fill="#1546a0"/>
<circle cx="92.2" cy="115.4" r="1.8" fill="#1546a0"/>
<circle cx="101.4" cy="114.8" r="1.8" fill="#1546a0"/>
<circle cx="115.3" cy="113.8" r="1.8" fill="#1546a0"/>
<circle cx="138.4" cy="103.7" r="1.8" fill="#1546a0"/>
<circle cx="161.5" cy="101.2" r="1.8" fill="#1546a0"/>
<circle cx="184.5" cy="107.1" r="1.8" fill="#1546a0"/>
<circle cx="198.4" cy="98.2" r="1.8" fill="#1546a0"/>
<circle cx="207.6" cy="99.7" r="1.8" fill="#1546a0"/>
<circle cx="221.5" cy="99.0" r="1.8" fill="#1546a0"/>
<circle cx="230.7" cy="98.2" r="1.8" fill="#1546a0"/>
<polyline points="55.2,174.1 69.1,149.9 82.9,135.5 92.2,129.7 101.4,124.7 115.3,116.8 138.4,107.6 161.5,101.0 184.5,94.1 198.4,91.1" fill="none" stroke="#14532d" stroke-width="1.3" stroke-dasharray="1.6,1.8"/>
<circle cx="55.2" cy="174.1" r="1.8" fill="#14532d"/>
<circle cx="69.1" cy="149.9" r="1.8" fill="#14532d"/>
<circle cx="82.9" cy="135.5" r="1.8" fill="#14532d"/>
<circle cx="92.2" cy="129.7" r="1.8" fill="#14532d"/>
<circle cx="101.4" cy="124.7" r="1.8" fill="#14532d"/>
<circle cx="115.3" cy="116.8" r="1.8" fill="#14532d"/>
<circle cx="138.4" cy="107.6" r="1.8" fill="#14532d"/>
<circle cx="161.5" cy="101.0" r="1.8" fill="#14532d"/>
<circle cx="184.5" cy="94.1" r="1.8" fill="#14532d"/>
<circle cx="198.4" cy="91.1" r="1.8" fill="#14532d"/>
<polyline points="55.2,190.0 69.1,166.8 82.9,152.8 92.2,147.0 101.4,142.2 115.3,134.8 138.4,125.6 161.5,119.0 184.5,112.5 198.4,109.5 207.6,108.3" fill="none" stroke="#1b7a34" stroke-width="1.3" stroke-dasharray="3,1.6"/>
<circle cx="55.2" cy="190.0" r="1.8" fill="#1b7a34"/>
<circle cx="69.1" cy="166.8" r="1.8" fill="#1b7a34"/>
<circle cx="82.9" cy="152.8" r="1.8" fill="#1b7a34"/>
<circle cx="92.2" cy="147.0" r="1.8" fill="#1b7a34"/>
<circle cx="101.4" cy="142.2" r="1.8" fill="#1b7a34"/>
<circle cx="115.3" cy="134.8" r="1.8" fill="#1b7a34"/>
<circle cx="138.4" cy="125.6" r="1.8" fill="#1b7a34"/>
<circle cx="161.5" cy="119.0" r="1.8" fill="#1b7a34"/>
<circle cx="184.5" cy="112.5" r="1.8" fill="#1b7a34"/>
<circle cx="198.4" cy="109.5" r="1.8" fill="#1b7a34"/>
<circle cx="207.6" cy="108.3" r="1.8" fill="#1b7a34"/>
<polyline points="55.2,202.7 69.1,181.5 82.9,168.1 92.2,162.5 101.4,157.8 115.3,150.5 138.4,141.5 161.5,135.1 184.5,128.7 198.4,125.9 207.6,124.4" fill="none" stroke="#5aab74" stroke-width="1.3" stroke-dasharray="0.9,1.4"/>
<circle cx="55.2" cy="202.7" r="1.8" fill="#5aab74"/>
<circle cx="69.1" cy="181.5" r="1.8" fill="#5aab74"/>
<circle cx="82.9" cy="168.1" r="1.8" fill="#5aab74"/>
<circle cx="92.2" cy="162.5" r="1.8" fill="#5aab74"/>
<circle cx="101.4" cy="157.8" r="1.8" fill="#5aab74"/>
<circle cx="115.3" cy="150.5" r="1.8" fill="#5aab74"/>
<circle cx="138.4" cy="141.5" r="1.8" fill="#5aab74"/>
<circle cx="161.5" cy="135.1" r="1.8" fill="#5aab74"/>
<circle cx="184.5" cy="128.7" r="1.8" fill="#5aab74"/>
<circle cx="198.4" cy="125.9" r="1.8" fill="#5aab74"/>
<circle cx="207.6" cy="124.4" r="1.8" fill="#5aab74"/>
<polyline points="55.2,182.7 69.1,159.6 82.9,145.9 92.2,140.1 101.4,135.2 115.3,127.8 138.4,118.8 161.5,112.1" fill="none" stroke="#b45309" stroke-width="1.3" stroke-dasharray="4,1.5,1,1.5"/>
<circle cx="55.2" cy="182.7" r="1.8" fill="#b45309"/>
<circle cx="69.1" cy="159.6" r="1.8" fill="#b45309"/>
<circle cx="82.9" cy="145.9" r="1.8" fill="#b45309"/>
<circle cx="92.2" cy="140.1" r="1.8" fill="#b45309"/>
<circle cx="101.4" cy="135.2" r="1.8" fill="#b45309"/>
<circle cx="115.3" cy="127.8" r="1.8" fill="#b45309"/>
<circle cx="138.4" cy="118.8" r="1.8" fill="#b45309"/>
<circle cx="161.5" cy="112.1" r="1.8" fill="#b45309"/>
<polyline points="55.2,176.8 69.1,153.9 82.9,140.0 92.2,134.4 101.4,129.5 115.3,122.2 138.4,113.3" fill="none" stroke="#7c2d92" stroke-width="1.3" stroke-dasharray="2,2"/>
<circle cx="55.2" cy="176.8" r="1.8" fill="#7c2d92"/>
<circle cx="69.1" cy="153.9" r="1.8" fill="#7c2d92"/>
<circle cx="82.9" cy="140.0" r="1.8" fill="#7c2d92"/>
<circle cx="92.2" cy="134.4" r="1.8" fill="#7c2d92"/>
<circle cx="101.4" cy="129.5" r="1.8" fill="#7c2d92"/>
<circle cx="115.3" cy="122.2" r="1.8" fill="#7c2d92"/>
<circle cx="138.4" cy="113.3" r="1.8" fill="#7c2d92"/>
<text x="305" y="27.6" font-size="6.8" fill="#c62828" font-weight="700">1D-RS</text>
<text x="305" y="100.7" font-size="6.8" fill="#1546a0" font-weight="700">2D-RS</text>
<text x="305" y="109.6" font-size="6.8" fill="#14532d" font-weight="700">BC 2048 λ2</text>
<text x="305" y="118.8" font-size="6.8" fill="#1b7a34" font-weight="700">BC 1024 λ2</text>
<text x="305" y="126.9" font-size="6.8" fill="#5aab74" font-weight="700">BC 512 λ2</text>
<text x="305" y="138.6" font-size="6.8" fill="#b45309" font-weight="700">BC 1024 λ3</text>
<text x="305" y="147.8" font-size="6.8" fill="#7c2d92" font-weight="700">BC 1024 λ4</text>
<text x="173" y="262" text-anchor="middle" font-size="7.4">erasure rate</text>
<text x="10" y="117" text-anchor="middle" font-size="7.4" transform="rotate(-90 10 117)">decode time (s, log)</text>
</svg>
<figcaption>Mean decode time of the trials that actually recovered, against erasure rate, log scale. Failed trials are excluded: above its threshold a scheme rejects the pattern on a budget check in under a millisecond having attempted nothing, which is not a decode time. 1D-RS is an order of magnitude more expensive than everything else at every rate, because it divides one 8192-length polynomial while the others divide short ones. Every block-circulant row is cheaper than 1D-RS at the same rate, and cheaper than 2D-RS too below about 30%.</figcaption>
</figure>

<figure>
<svg viewBox="0 0 480 232" role="img" aria-label="Surviving data each scheme needs to rebuild one blob, as a multiple of the blob size. 1D-RS needs almost exactly one blob; the others need more.">
<line x1="50" y1="28" x2="50" y2="176" stroke="currentColor" stroke-width="0.8"/>
<line x1="50" y1="176" x2="472" y2="176" stroke="currentColor" stroke-width="0.8"/>
<line x1="47" y1="176.0" x2="50" y2="176.0" stroke="currentColor" stroke-width="0.7"/>
<line x1="50" y1="176.0" x2="472" y2="176.0" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="44" y="178.5" text-anchor="end" font-size="7">0.0</text>
<line x1="47" y1="142.4" x2="50" y2="142.4" stroke="currentColor" stroke-width="0.7"/>
<line x1="50" y1="142.4" x2="472" y2="142.4" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="44" y="144.9" text-anchor="end" font-size="7">0.5</text>
<line x1="47" y1="108.7" x2="50" y2="108.7" stroke="currentColor" stroke-width="0.7"/>
<line x1="50" y1="108.7" x2="472" y2="108.7" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="44" y="111.2" text-anchor="end" font-size="7">1.0</text>
<line x1="47" y1="75.1" x2="50" y2="75.1" stroke="currentColor" stroke-width="0.7"/>
<line x1="50" y1="75.1" x2="472" y2="75.1" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="44" y="77.6" text-anchor="end" font-size="7">1.5</text>
<line x1="47" y1="41.5" x2="50" y2="41.5" stroke="currentColor" stroke-width="0.7"/>
<line x1="50" y1="41.5" x2="472" y2="41.5" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="44" y="44.0" text-anchor="end" font-size="7">2.0</text>
<line x1="50" y1="108.7" x2="472" y2="108.7" stroke="#c62828" stroke-width="1" stroke-dasharray="3,2"/>
<text x="54" y="104.7" font-size="6.2" fill="#c62828">1.00 = theoretical minimum (no code rebuilds a blob from less than a blob)</text>
<rect x="69.1" y="108.7" width="22" height="67.3" fill="#c62828" opacity="0.85"/>
<text x="80.1" y="105.7" text-anchor="middle" font-size="7" font-weight="700" fill="#c62828">1.00×</text>
<text x="80.1" y="187.0" text-anchor="middle" font-size="6.6" font-weight="700">1D-RS</text>
<text x="80.1" y="196.0" text-anchor="middle" font-size="6" fill="#5b6572">128 KiB</text>
<rect x="129.4" y="94.8" width="22" height="81.2" fill="#1546a0" opacity="0.85"/>
<text x="140.4" y="91.8" text-anchor="middle" font-size="7" font-weight="700" fill="#1546a0">1.21×</text>
<text x="140.4" y="187.0" text-anchor="middle" font-size="6.6" font-weight="700">2D-RS</text>
<text x="140.4" y="196.0" text-anchor="middle" font-size="6" fill="#5b6572">154 KiB</text>
<rect x="189.7" y="87.2" width="22" height="88.8" fill="#14532d" opacity="0.85"/>
<text x="200.7" y="84.2" text-anchor="middle" font-size="7" font-weight="700" fill="#14532d">1.32×</text>
<text x="200.7" y="187.0" text-anchor="middle" font-size="6.6" font-weight="700">BC 2048 λ2</text>
<text x="200.7" y="196.0" text-anchor="middle" font-size="6" fill="#5b6572">169 KiB</text>
<rect x="250.0" y="89.2" width="22" height="86.8" fill="#1b7a34" opacity="0.85"/>
<text x="261.0" y="86.2" text-anchor="middle" font-size="7" font-weight="700" fill="#1b7a34">1.29×</text>
<text x="261.0" y="187.0" text-anchor="middle" font-size="6.6" font-weight="700">BC 1024 λ2</text>
<text x="261.0" y="196.0" text-anchor="middle" font-size="6" fill="#5b6572">165 KiB</text>
<rect x="310.3" y="89.2" width="22" height="86.8" fill="#5aab74" opacity="0.85"/>
<text x="321.3" y="86.2" text-anchor="middle" font-size="7" font-weight="700" fill="#5aab74">1.29×</text>
<text x="321.3" y="187.0" text-anchor="middle" font-size="6.6" font-weight="700">BC 512 λ2</text>
<text x="321.3" y="196.0" text-anchor="middle" font-size="6" fill="#5b6572">165 KiB</text>
<rect x="370.6" y="78.5" width="22" height="97.5" fill="#b45309" opacity="0.85"/>
<text x="381.6" y="75.5" text-anchor="middle" font-size="7" font-weight="700" fill="#b45309">1.45×</text>
<text x="381.6" y="187.0" text-anchor="middle" font-size="6.6" font-weight="700">BC 1024 λ3</text>
<text x="381.6" y="196.0" text-anchor="middle" font-size="6" fill="#5b6572">186 KiB</text>
<rect x="430.9" y="68.4" width="22" height="107.6" fill="#7c2d92" opacity="0.85"/>
<text x="441.9" y="65.4" text-anchor="middle" font-size="7" font-weight="700" fill="#7c2d92">1.60×</text>
<text x="441.9" y="187.0" text-anchor="middle" font-size="6.6" font-weight="700">BC 1024 λ4</text>
<text x="441.9" y="196.0" text-anchor="middle" font-size="6" fill="#5b6572">205 KiB</text>
<text x="11" y="102" text-anchor="middle" font-size="7.2" transform="rotate(-90 11 102)">surviving data needed (× blob)</text>
</svg>
<figcaption>How much surviving data each scheme needs to rebuild one blob, as a multiple of the blob itself. This is the question that matters for data-availability sampling, where a node has to actually fetch those symbols. 1D-RS needs essentially the theoretical floor &mdash; no code rebuilds 124 KiB from less than 124 KiB. Every other scheme needs more, and a scheme tolerating a lower erasure rate at the same storage cost necessarily needs more.</figcaption>
</figure>

## What the results show

**1D-RS behaves exactly as Reed-Solomon theory says it must.** It
recovers everything up to 48% and nothing from 50% upward.
The invariant is exact rather than approximate: across every 1D-RS trial
in the sweep, recovery succeeded if and only if the drawn erasure count
was at most n&minus;k = 4096, with no exceptions. The partial results at the
threshold are not the decoder being unreliable — they are the random mask
landing on either side of a hard line. Being MDS, 1D-RS extracts
essentially all of its theoretical budget.

**2D-RS comes second, and beats its own guarantee by a wide margin.** It
holds to 35% and fails from 45%, with the transition straddling 38–40%
(5/5 at 38%, 2/5 at 40%, 0/5 at 45%) — call it 0.42. Two reference points
matter and they are very far apart. Its rate would permit 0.515; its
*minimum distance* only guarantees 0.098, because a product code's
distance is the product of its component distances, 33 × 25 = 825. The
measured 0.42 is more than four times that guarantee.

That gap is the cross-axis cascade doing real work. A guarantee has to
hold against the worst pattern in existence — for a product code, an
adversary who concentrates erasures to kill whole rows and columns at
once. Random patterns are nothing like that, so lines that are
individually over budget keep getting rescued once their partner axis
repairs enough neighbours. The honest summary is that 2D-RS's *typical*
behaviour is far better than its *guaranteed* behaviour, and which of the
two matters depends entirely on whether the erasures are adversarial.
Against the 1−*R* bound it reaches 82%; against its own distance it is at
430%.

**The Block-Circulant rows separate the code from the decoder, and λ is
what moves the decoder.** This is the clearest result in the sweep:

- **ω2048 λ2** (μ=2, MDS, *d*=4097): recovers to 33%, fails from 35%; predicted S₀ = 0.333.
- **ω1024 λ2** (μ=4, *d*=2049): recovers to 33%, fails from 38%; predicted S₀ = 0.333.
- **ω512 λ2** (μ=8, *d*=1025): recovers to 33%, fails from 38%; predicted S₀ = 0.333.
- **ω1024 λ3** (μ=4, *d*=3073): recovers to 25%, fails from 30%; predicted S₀ = 0.250.
- **ω1024 λ4** (μ=4, MDS, *d*=4097): recovers to 15%, fails from 25%; predicted S₀ = 0.200.

Two things fall out of that list. First, **the prediction is right every
time** — S₀ = ρ/N₀ = 1/(1+λ), the source paper's local stopping rate,
lands inside the measured transition band for all five rows. The limit is
not mysterious; it is arithmetic about how many erasures fit inside one
local support.

Second, **λ is the only parameter that moves it.** The three λ=2 rows all
land at 0.34–0.35 while μ ranges over 2, 4, 8 and ω over 2048, 1024, 512 —
a factor of four in block size that changes the threshold by nothing at
all. Raising λ to 3 costs 7 points, and to 4 costs 14. This is the direct
answer to "which knob should we turn": not ω, not μ, but λ, and downward.

Third, and most useful for the construction's prospects, **two of these
rows decode past their own worst-case guarantee.** ω1024 λ2 is guaranteed
only 0.250 and reaches 0.35; ω512 λ2 is guaranteed 0.125 and also reaches
0.35, nearly three times its bound. These are *not* MDS codes and cannot
claim to be; against a worst-case adversary they would fail where the
table says they fail. But under random erasure — which is what a sampling
network actually produces absent a targeted attack — they perform like
codes with far better distance. That is the sense in which parameters
that are "not fully decodable" still demonstrate the construction's
potential.

Set against that, the λ=2 rows cost less decode time than anything except
each other, and every BC row is cheaper than 1D-RS at every rate measured.
The local system each solves is ρ×ρ, which generic elimination handles in
ρ³ — which is why the pairwise phase stays unaffordable while the
single-block phase does not, the latter's system being Vandermonde and so
dropping to ρ².

## Making these parameterisations runnable

The larger-ω BC rows could not be measured at all with the decoder as it
stood. The reason is worth recording, because it is the same wall anyone
re-running this will hit.

The original `gf_solve` is a Gauss-Jordan elimination written as a Python
loop over rows. Its cost grows as the cube of the matrix dimension, and
this field's arithmetic runs in `galois`' object mode at roughly 1.3
microseconds per element operation. At ω=ρ=2 the local systems are 2×2 and
none of that matters. At ω=ρ=1024 they are 1024×1024, which is about a
billion element operations — roughly 25 minutes for a single local solve,
with μ of them per decoding round.

Three changes brought it into range, none of which alters what is computed:

**The elimination step is now one broadcast update instead of a loop over
rows.** Same arithmetic, same element count, but the per-pivot dispatches
into object-mode arithmetic drop from *m* to one. Measured: 1.34 → 0.55
microseconds per element operation, a 2.4× speedup.

**The single-block solve now exploits the structure it always had.** The
local parity-check matrix is a GRS matrix, `H[r, c] = (c+1)^r`. Restricted
to the erased columns and to its first *e* rows it is a square Vandermonde
in distinct evaluation points — so it is always invertible, and it can be
solved in O(*e*²) by a node-polynomial argument rather than O(*e*³) by
elimination. Measured at *e* = 1024: 0.87 seconds against an extrapolated
1441, about 1650×. This is what makes ω=1024 tractable.

**The global parity-check matrix is no longer built.** It is
(μρ)×*n* = 4096×8192 = 33.5 million field elements, and every row the
decoder needs can be regenerated from (ρ, n₀) on demand.

A useful side effect: because the single-block system is provably square
Vandermonde in distinct nodes, it cannot be underdetermined, so the class
of bug described below cannot arise on that path at all.

## The pairwise phase does not get a turn

`DecCBC[2]`'s second phase stacks two adjacent blocks' parity checks and
solves them jointly. That system is *not* Vandermonde — the two row groups
assign different evaluation points to the same shared columns — so it
cannot use the fast solver and needs full elimination, at cubic cost.

Phase 2 only runs when phase 1 has stalled, which happens only once a
local support carries more than ρ erasures. Every row swept here has
ρ ≥ 256, so every pair that could possibly help carries more than 256
unknowns. The sweep applies a stated compute budget of 256 unknowns per
pairwise system, identically to all five rows, and above that budget a
pair is skipped, counted, and its positions left honestly flagged.

The consequence is that **all five rows are measured as single-phase
decoders**, and this is a limit of affordable computation rather than of
the code. The cost was measured directly on the 512-equation systems that
ω=ρ=256 produces:

| unknowns in the pair | erasure rate it corresponds to | per pair | per decoding round (16 pairs) |
|---|---|---|---|
| 276 | 6% | 21.7s | 5.8 min |
| 369 | 8% | 39.5s | 10.5 min |
| 461 | 10% | 61.7s | 16.4 min |

That is for the *smallest* local block swept here, and one decoding round is not
one decode — the loop repeats while it makes progress. At ω=ρ=1024 a full
pair is 2048 equations in 2048 unknowns; at the 0.57 microseconds per field
operation these timings imply, that is about 80 minutes for a single pair.
Lifting the cap enough to change any result would take days per sweep.

The honest reading of the BC numbers is therefore: this is what the
single-block phase of `DecCBC[2]` achieves. The pairwise phase would
roughly double the budget from ρ to 2ρ, which the same arithmetic puts at
0.333 for ω=1024, 0.200 for ω=512 and 0.111 for ω=256 — still short of
the 0.50 these codes permit.

## The Block-Circulant decoder fix

The BC results are from a corrected decoder. The version originally
benchmarked had two faults that together made its output untrustworthy
rather than merely weak. Both were found at the earlier ω=ρ=λ=2
parameterisation, and the before/after figure below is measured there.

**`gf_solve` fabricated values.** The Gaussian elimination routine returned
zero for any unknown whose column never received a pivot. To the caller
that is indistinguishable from having genuinely solved for zero, so an
underdetermined system silently produced a confident-looking wrong answer.
It now raises `GFSolveError` unless the system has exactly one solution —
every column pivoted, and no row reduced to `0 = nonzero`.

**`dec_cbc_2`'s pairwise phase accepted systems it had not solved.** Its
guard is `0 < erasures ≤ 2ρ`, which is necessary but not sufficient. The
equations it stacks are block *i*'s own ρ parity checks on top of block
*i+1*'s — not the auxiliary `[2(ω+ρ), 2ω, 2ρ+1]` GRS code over the union
of the two supports that the source paper's Algorithm 1 constructs. The
stacked form is not MDS, so a split such as "three erasures inside block
*i*'s support, one inside *i+1*'s" leaves two equations facing three
unknowns. Combined with the `gf_solve` fault, the decoder wrote zeros into
those positions *and cleared their erasure flags*, reporting success on
corrupted data. It now skips any pair it cannot uniquely solve, leaving
those positions honestly flagged.

The practical effect is stark. Measured before the fix, across 40 trials
spanning 5–45% erasure, `dec_cbc_2` claimed success **every single time**
and was wrong on 31 of them; it never once reported a failure. Its
`remaining` flag — the signal a caller would naturally trust — carried no
information about whether the data was correct. Had this benchmark trusted
that flag instead of checking bytes, it would have reported BC at 100%
success at every rate.

<figure>
<svg viewBox="0 0 320 214" role="img" aria-label="Block-circulant decoder before and after the correctness fix on the same 40 trials: correct recoveries rose from 9 to 16, and silent corruptions fell from 31 to 0."><line x1="44" y1="32" x2="44" y2="172" stroke="currentColor" stroke-width="0.8"/>
<line x1="44" y1="172" x2="306" y2="172" stroke="currentColor" stroke-width="0.8"/>
<line x1="41" y1="172.0" x2="44" y2="172.0" stroke="currentColor" stroke-width="0.7"/>
<line x1="44" y1="172.0" x2="306" y2="172.0" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="39" y="174.5" text-anchor="end" font-size="7.2">0</text>
<line x1="41" y1="137.0" x2="44" y2="137.0" stroke="currentColor" stroke-width="0.7"/>
<line x1="44" y1="137.0" x2="306" y2="137.0" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="39" y="139.5" text-anchor="end" font-size="7.2">10</text>
<line x1="41" y1="102.0" x2="44" y2="102.0" stroke="currentColor" stroke-width="0.7"/>
<line x1="44" y1="102.0" x2="306" y2="102.0" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="39" y="104.5" text-anchor="end" font-size="7.2">20</text>
<line x1="41" y1="67.0" x2="44" y2="67.0" stroke="currentColor" stroke-width="0.7"/>
<line x1="44" y1="67.0" x2="306" y2="67.0" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="39" y="69.5" text-anchor="end" font-size="7.2">30</text>
<line x1="41" y1="32.0" x2="44" y2="32.0" stroke="currentColor" stroke-width="0.7"/>
<line x1="44" y1="32.0" x2="306" y2="32.0" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>
<text x="39" y="34.5" text-anchor="end" font-size="7.2">40</text>
<rect x="80.5" y="140.5" width="26" height="31.5" fill="#8d99a6"/>
<text x="93.5" y="137.5" text-anchor="middle" font-size="7.2" fill="#8d99a6" font-weight="700">9</text>
<rect x="112.5" y="116.0" width="26" height="56.0" fill="#1b7a34" opacity="0.88"/>
<text x="125.5" y="113.0" text-anchor="middle" font-size="7.2" fill="#1b7a34" font-weight="700">16</text>
<text x="109.5" y="186" text-anchor="middle" font-size="7.4">recovered correctly</text>
<rect x="211.5" y="63.5" width="26" height="108.5" fill="#8d99a6"/>
<text x="224.5" y="60.5" text-anchor="middle" font-size="7.2" fill="#8d99a6" font-weight="700">31</text>
<rect x="243.5" y="172.0" width="26" height="0.0" fill="#1b7a34" opacity="0.88"/>
<text x="256.5" y="169.0" text-anchor="middle" font-size="7.2" fill="#1b7a34" font-weight="700">0</text>
<text x="240.5" y="186" text-anchor="middle" font-size="7.4">silently corrupted</text>
<rect x="44" y="12" width="11" height="8" fill="#8d99a6"/>
<text x="59" y="19" font-size="6.6">before fix</text>
<rect x="116" y="12" width="11" height="8" fill="#1b7a34" opacity="0.88"/>
<text x="131" y="19" font-size="6.6">after fix</text>
<text x="10" y="102.0" text-anchor="middle" font-size="7.4" transform="rotate(-90 10 102.0)">trials (of 40)</text></svg>
<figcaption>The decoder fix, measured on the parameterisation it was found at (&omega;=&rho;=&lambda;=2, &mu;=2048) &#8212; <em>not</em> the rows swept above. The same 40 trials (5%, 15%, 25% and 45% erasure, ten each) run through the decoder before and after. Correct recoveries rose from 9 to 16, because the old decoder poisoned positions with fabricated zeros that blocked later rounds from resolving them. Silent corruptions &#8212; cases where the decoder reported success on wrong data &#8212; fell from 31 to zero. The remaining failures are honest: the decoder reports the positions it could not resolve.</figcaption>
</figure>

A third change is a performance fix rather than a correctness one: the
pairwise phase used to `break` and restart the single-block phase after
every pair it repaired, paying a full scan of all local blocks per repair.
It now continues through the remaining pairs in the same pass.

**What none of this does** is restore the correction radius the paper
claims. Implementing the auxiliary GRS construction would let the pairwise
phase handle *any* ≤2ρ erasures across two adjacent blocks, rather than
only those solvable from the stacked parity checks — and, being a GRS code,
it would also be solvable in O(*e*²) rather than O(*e*³), which would
remove the compute wall described above. That is the single highest-value
piece of remaining work on this file.

## Reproducing

```
pip install galois numpy
python3 benchmark_1D_2D_BC.py
```

Per-trial results — erasure counts, decode times, success flags, and the
decoder's own claim separately from ground truth — are written to
`benchmark_results.json`.
