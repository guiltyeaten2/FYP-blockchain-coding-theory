# Erasure coding schemes for Ethereum PeerDAS

Final-year project comparing three erasure coding schemes for Ethereum's
data-availability sampling, at matched storage cost, on real EIP-4844 blobs
over the real BLS12-381 scalar field.

**Start with [`docs/project_overview.pdf`](docs/project_overview.pdf)** — a
ten-page tour of the problem, the schemes and the measurements. Everything
below assumes it.

## The schemes

| | n | k | rate | measured tolerance |
|---|---|---|---|---|
| 1D-RS | 8192 | 4096 | 0.500 | 0.500 |
| 2D-RS (88×96 grid) | 8448 | 4096 | 0.485 | 0.401 |
| BC ω2048 λ2 | 8192 | 4096 | 0.500 | 0.337 |
| BC ω1024 λ2 | 8192 | 4096 | 0.500 | 0.342 |
| BC ω1024 λ3 | 8192 | 4096 | 0.500 | 0.255 |
| BC ω1024 λ4 | 8192 | 4096 | 0.500 | 0.202 |
| BC ω512 λ2 | 8192 | 4096 | 0.500 | 0.349 |

Tolerance is the erasure probability at which a scheme recovers half the
time, from a maximum-likelihood logistic fit to 1,184 dense trials across
each scheme's transition band (`threshold_refinement.py`); 95% intervals
are about ±0.002. 1D-RS checks the method: an MDS code with n = 2k has an
exact threshold of 0.50006, and it measures 0.4996.

## Install and run

```
pip install -r requirements.txt     # plus Chrome or Chromium, for make_docs.py

python3 benchmark_1D_2D_BC.py       # erasure sweep -> benchmark_results.json  (hours)
python3 benchmark_1D_2D_BC.py --quick   # smoke test, not a result            (minutes)
python3 network_sim.py              # P2P simulation                          (seconds)
python3 fft_benchmark.py            # NTT decoder measurements                (10-20 min)
python3 test_bc_fft.py              # structural checks on the BC decoder
python3 threshold_refinement.py     # dense trials for thresholds          (~3 h)

python3 make_figures.py             # every figure from committed JSON        (~3 s)
python3 make_docs.py                # every report to PDF
```

The two long sweeps write JSON; everything downstream reads that JSON rather
than re-measuring. So figures and reports regenerate in seconds without
re-running anything, and a figure cannot quietly disagree with the table
beside it — they come from the same file.

Figure output is deterministic: a diff in `docs/figures/` means the data
moved, not that the clock did.

## Layout

| file | |
|---|---|
| `blob_generator.py` | EIP-4844 blob packing; the shared field |
| `1D_RS_Galois.py`, `2D_RS_Galois.py` | the two Reed-Solomon schemes |
| `BCcodeEthereum.py` | block-circulant encoder and decoder |
| `benchmark_1D_2D_BC.py` | the seven-scheme erasure sweep |
| `network_sim.py` | SimPy peer-to-peer layer |
| `threshold_refinement.py`, `thresholds.py` | threshold measurement and estimation |
| `fft_benchmark.py`, `test_bc_fft.py` | NTT decoder measurement and checks |
| `make_figures.py`, `make_docs.py` | figures and PDFs |
| `RScode.py`, `2DRScode.py`, `BCcode.py` | earlier prototypes, kept for reference; not used by the benchmark |

## Reports

| | |
|---|---|
| `docs/project_overview.pdf` | start here — the whole project in ten pages |
| `docs/benchmark_1D_2D_BC_report.pdf` | the erasure sweep, in full |
| `docs/network_sim_report.pdf` | the P2P simulation |
| `docs/1D_vs_2D_RS_comparison.pdf` | the two Reed-Solomon schemes head to head |
| `docs/1D_2D_RS_code_walkthrough.pdf` | how the RS implementations work, line by line |
| `docs/coding_scheme_diagrams.pdf` | schematic diagrams of each construction |

## Known gaps

* **Block-circulant phase 2 does not apply to the benchmark's codes.** It
  implements the paper's auxiliary construction (Algorithm 1), which needs
  the paper's evaluation-point layout; the benchmark uses a shared layout so
  that all five rows stay comparable. Phase 2 engaged on 1% of refinement
  trials and moves no threshold by more than 0.003, so all five BC rows are
  measured as effectively single-phase decoders.
* **The NTT decoder path is slower than the solver it replaces**, by 7–23×.
  The transform is ~12% of the work; ~80% is a polynomial division
  implemented as a scalar loop. Replacing it with Newton iteration is the
  fix. It is switched off in the benchmark (`use_fft_phase1=False`).
* **One network topology.** The brief asks for several; `network_sim.py`
  models a single flat peer set.
