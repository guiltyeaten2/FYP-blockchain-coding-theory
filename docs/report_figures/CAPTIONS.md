# Caption copy

IEEE figures carry no in-figure title: the caption describes the figure, and a title duplicates it. These figures are generated with titles and methods notes suppressed, and the text harvested here instead.

Each entry gives a short caption (the title, as a noun phrase) and a full caption (adds how to read it and the measurement conditions). IEEE style puts the figure number and caption *below* the figure.

---

## `01-benchmark/`

### 01-fault-tolerance

**Short.** Every scheme holds, then collapses within a few percent

**Full.** Every scheme holds, then collapses within a few percent. Top: fraction of trials recovered against erasure rate, one line per scheme, markers drawn only where a curve is partway down. Bottom: one row per scheme, the bar spanning the last rate where every trial recovered to the first where none did, with the 50% threshold ticked on it. 520 trials over one EIP-4844 blob; a trial counts as recovered only if the bytes match the original exactly.

**Panels.** (a) Every scheme holds, then collapses within a few percent; (b) Where each scheme falls over
bar: all trials recovered → none did.  tick: 50% threshold

```latex
\begin{figure}[t]
  \centering
  \includegraphics[width=\linewidth]{01-fault-tolerance}
  \caption{Every scheme holds, then collapses within a few percent.}
  \label{fig:01-fault-tolerance}
\end{figure}
```

### 02-fault-tolerance-compact

**Short.** 

**Full.** . One row per scheme, sorted by threshold. The bar spans the last rate at which every trial recovered to the first at which none did; the tick is the 50% threshold. Bar: last rate at which every trial recovered, to the first at which none did. tick: 50% threshold. 520 trials..

```latex
\begin{figure}[t]
  \centering
  \includegraphics[width=\linewidth]{02-fault-tolerance-compact}
  \caption{.}
  \label{fig:02-fault-tolerance-compact}
\end{figure}
```

### 03-bc-threshold-vs-theory

**Short.** Block-circulant threshold follows $1/(1+\lambda)$, not $\mu$ or $\omega$

**Full.** Block-circulant threshold follows $1/(1+\lambda)$, not $\mu$ or $\omega$. Bars are measured thresholds, one per parameterisation, sorted by lambda. Red rules are the predicted stopping rate S0 = rho/n0 = 1/(1+lambda). Bars: erasure rate at 50% success. rules: the local code's stopping rate $S_0=\rho/n_0=1/(1+\lambda)$.

```latex
\begin{figure}[t]
  \centering
  \includegraphics[width=\linewidth]{03-bc-threshold-vs-theory}
  \caption{Block-circulant threshold follows $1/(1+\lambda)$, not $\mu$ or $\omega$.}
  \label{fig:03-bc-threshold-vs-theory}
\end{figure}
```

### 04-tolerance-vs-guarantee

**Short.** Measured tolerance against each code's own worst-case bound

**Full.** Measured tolerance against each code's own worst-case bound. Blue is the measured 50% threshold, grey the worst-case guarantee from minimum distance, dashed red the rate bound 1-R that no code of that rate can beat. Storage matched at ~2x across every scheme; guarantee is the minimum-distance bound, measured is the 50% threshold.

```latex
\begin{figure}[t]
  \centering
  \includegraphics[width=\linewidth]{04-tolerance-vs-guarantee}
  \caption{Measured tolerance against each code's own worst-case bound.}
  \label{fig:04-tolerance-vs-guarantee}
\end{figure}
```

### 05-decode-cost

**Short.** Decode cost against erasure rate

**Full.** Decode cost against erasure rate. Log vertical axis in seconds, erasure rate horizontal, curves named at their right-hand ends. Mean over the trials that recovered; n$\approx$8192, k=4096, single-threaded Python over galois.

```latex
\begin{figure}[t]
  \centering
  \includegraphics[width=\linewidth]{05-decode-cost}
  \caption{Decode cost against erasure rate.}
  \label{fig:05-decode-cost}
\end{figure}
```

### 06-cost-per-erasure

**Short.** Cost per erasure repaired, with the workload divided out

**Full.** Cost per erasure repaired, with the workload divided out. Milliseconds per erased symbol, log axis. A flat line means cost is linear in the number of erasures; a falling line means a fixed cost is being amortised over more repairs. Decode time divided by the number of symbols actually erased in that trial.

```latex
\begin{figure}[t]
  \centering
  \includegraphics[width=\linewidth]{06-cost-per-erasure}
  \caption{Cost per erasure repaired, with the workload divided out.}
  \label{fig:06-cost-per-erasure}
\end{figure}
```

### 07-encode-vs-decode

**Short.** Encode is paid once; decode is paid by everyone

**Full.** Encode is paid once; decode is paid by everyone. Paired bars per scheme, log axis in seconds. One 128 KiB blob; decode measured at the highest rate every scheme still recovers.

```latex
\begin{figure}[t]
  \centering
  \includegraphics[width=\linewidth]{07-encode-vs-decode}
  \caption{Encode is paid once; decode is paid by everyone.}
  \label{fig:07-encode-vs-decode}
\end{figure}
```

### 08-pareto-tolerance-vs-cost

**Short.** Tolerance against the cost of achieving it lower and further right is better

**Full.** Tolerance against the cost of achieving it lower and further right is better. One point per scheme: tolerance horizontal, decode cost vertical on a log axis. Down and to the right is better. The dashed line is the Pareto frontier - schemes not beaten on both counts at once. BC ω512 λ2.

```latex
\begin{figure}[t]
  \centering
  \includegraphics[width=\linewidth]{08-pareto-tolerance-vs-cost}
  \caption{Tolerance against the cost of achieving it lower and further right is better.}
  \label{fig:08-pareto-tolerance-vs-cost}
\end{figure}
```

### 09-data-needed-per-blob

**Short.** What a node must actually fetch to rebuild one blob

**Full.** What a node must actually fetch to rebuild one blob. Bars per scheme against a dashed line at 1.0, the theoretical floor - nothing rebuilds 124 KiB from less than 124 KiB. N(1-tolerance)/k: surviving symbols required, as a multiple of one blob.

```latex
\begin{figure}[t]
  \centering
  \includegraphics[width=\linewidth]{09-data-needed-per-blob}
  \caption{What a node must actually fetch to rebuild one blob.}
  \label{fig:09-data-needed-per-blob}
\end{figure}
```

## `02-network-sim/`

### 01-erasure-vs-adversaries

**Short.** Custody replication turns withholding into a much smaller erasure rate — and the code carried makes no difference

**Full.** Custody replication turns withholding into a much smaller erasure rate — and the code carried makes no difference. Realised erasure against the fraction of peers refusing to serve, with the p^4 prediction dashed. All six schemes are drawn; they coincide. 64 peers, custody replication 4, 30 trials per point; a cell is lost only if every custodian withholds it.

```latex
\begin{figure}[t]
  \centering
  \includegraphics[width=\linewidth]{01-erasure-vs-adversaries}
  \caption{Custody replication turns withholding into a much smaller erasure rate — and the code carried makes no difference.}
  \label{fig:01-erasure-vs-adversaries}
\end{figure}
```

### 02-recovery-vs-adversaries

**Short.** Recovery against adversarial withholding

**Full.** Recovery against adversarial withholding. Fraction of 30 trials that rebuilt the blob byte-exactly, against withholding. 64 peers, replication 4, 4s sampling deadline; erasures are what failed to arrive, not injected.

```latex
\begin{figure}[t]
  \centering
  \includegraphics[width=\linewidth]{02-recovery-vs-adversaries}
  \caption{Recovery against adversarial withholding.}
  \label{fig:02-recovery-vs-adversaries}
\end{figure}
```

### 03-latency-gather-time

**Short.** Latency: withholding costs time, not just data

**Full.** Latency: withholding costs time, not just data. Seconds to collect the cells, against withholding, with the 4 s sampling deadline marked. A curve reaching 4.00 has run out of time. 64 peers, custody replication 4, one blob per slot; a withheld request is only abandoned after the client's timeout expires.

```latex
\begin{figure}[t]
  \centering
  \includegraphics[width=\linewidth]{03-latency-gather-time}
  \caption{Latency: withholding costs time, not just data.}
  \label{fig:03-latency-gather-time}
\end{figure}
```

### 04-bandwidth-fetched

**Short.** Bandwidth: what each scheme pulls over the wire

**Full.** Bandwidth: what each scheme pulls over the wire. MiB fetched per slot against withholding, with a dashed line at the actual payload (six blobs = 0.73 MiB). Includes the over-request margin and anything re-requested after a timeout. 6 blobs per slot, 25 Mbps downlink, 64 peers. the fall at high withholding is cells that never arrived, not a saving.

```latex
\begin{figure}[t]
  \centering
  \includegraphics[width=\linewidth]{04-bandwidth-fetched}
  \caption{Bandwidth: what each scheme pulls over the wire.}
  \label{fig:04-bandwidth-fetched}
\end{figure}
```

### 05-throughput-blobs-per-slot

**Short.** Throughput inverts the tolerance ordering

**Full.** Throughput inverts the tolerance ordering. Blobs reconstructed per slot out of six, against withholding, with a dashed line at six.

```latex
\begin{figure}[t]
  \centering
  \includegraphics[width=\linewidth]{05-throughput-blobs-per-slot}
  \caption{Throughput inverts the tolerance ordering.}
  \label{fig:05-throughput-blobs-per-slot}
\end{figure}
```

### 06-time-budget-vs-slot

**Short.** Does the whole job fit inside a slot?

**Full.** Does the whole job fit inside a slot?. Log seconds against withholding, with the 4 s sampling deadline and the 12 s slot both marked. Anything above the 12 s line cannot keep up with the chain. 6 blobs per slot, 25 Mbps; anything above the 12s line cannot keep up with the chain.

```latex
\begin{figure}[t]
  \centering
  \includegraphics[width=\linewidth]{06-time-budget-vs-slot}
  \caption{Does the whole job fit inside a slot?.}
  \label{fig:06-time-budget-vs-slot}
\end{figure}
```

### 07-gather-vs-decode

**Short.** Decode dominates gather by orders of magnitude

**Full.** Decode dominates gather by orders of magnitude. Gather and decode as separate bars per scheme on a log axis - separate rather than stacked, because stacking on a log axis would misrepresent the sum. The slot deadline is marked. 6 blobs per slot, 25 Mbps downlink, no adversaries; gather is network time, decode is CPU.

```latex
\begin{figure}[t]
  \centering
  \includegraphics[width=\linewidth]{07-gather-vs-decode}
  \caption{Decode dominates gather by orders of magnitude.}
  \label{fig:07-gather-vs-decode}
\end{figure}
```

### 08-scalability-peer-count

**Short.** Realised erasure rises with peer count, then plateaus

**Full.** Realised erasure rises with peer count, then plateaus. Realised erasure against peer count on a log-2 axis. Open markers are the exact hypergeometric probability that all four custodians of a cell are adversarial, C(A,4)/C(n,4), computed from the model rather than fitted. Dotted lines are the p^4 independent-sampling limits. Custody replication 4, drawn without replacement; markers are the exact probability that all custodians of a cell withhold.

```latex
\begin{figure}[t]
  \centering
  \includegraphics[width=\linewidth]{08-scalability-peer-count}
  \caption{Realised erasure rises with peer count, then plateaus.}
  \label{fig:08-scalability-peer-count}
\end{figure}
```

## `03-methodology/`

### 01-decoder-correctness-fix

**Short.** The decoder fix: silent corruption eliminated, correct recoveries up

**Full.** The decoder fix: silent corruption eliminated, correct recoveries up. Outcome counts for the same 40 trials, before the fix in pale and after in solid. Three outcomes: correct recovery, silent corruption, honest failure. The same 40 trials at omega = rho = lambda = 2, mu = 2048, spanning 5-45% erasure, re-run through both decoders.

```latex
\begin{figure}[t]
  \centering
  \includegraphics[width=\linewidth]{01-decoder-correctness-fix}
  \caption{The decoder fix: silent corruption eliminated, correct recoveries up.}
  \label{fig:01-decoder-correctness-fix}
\end{figure}
```
