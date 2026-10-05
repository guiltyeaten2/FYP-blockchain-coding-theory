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
| 1D-RS | 8192 | 4096 | 0.500 | 0.505 |
| 2D-RS (88×96 grid) | 8448 | 4096 | 0.485 | 0.397 |
| BC ω2048 λ2 | 8192 | 4096 | 0.500 | 0.340 |
| BC ω1024 λ2 | 8192 | 4096 | 0.500 | 0.341 |
| BC ω1024 λ3 | 8192 | 4096 | 0.500 | 0.275 |
| BC ω1024 λ4 | 8192 | 4096 | 0.500 | 0.210 |
| BC ω512 λ2 | 8192 | 4096 | 0.500 | 0.350 |

Tolerance is the erasure rate at which the success rate crosses 50%,
interpolated between swept points. Storage overhead is held at ~2× across
every row so the comparison is about what each scheme buys for the same
price.

## Install and run

```
pip install -r requirements.txt     # plus Chrome or Chromium, for make_docs.py

python3 benchmark_1D_2D_BC.py       # erasure sweep -> benchmark_results.json  (hours)
python3 benchmark_1D_2D_BC.py --quick   # smoke test, not a result            (minutes)
python3 network_sim.py              # P2P simulation                          (seconds)
python3 fft_benchmark.py            # NTT decoder measurements                (10-20 min)
python3 test_bc_fft.py              # structural checks on the BC decoder

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

* **Block-circulant phase 2** does not implement the source paper's auxiliary
  GRS construction. It stacks two blocks' parity checks instead, which is a
  weaker system solved at cubic cost. All five BC rows are therefore measured
  as single-phase decoders.
* **The NTT decoder path is slower than the solver it replaces**, by 7–23×.
  The transform is ~12% of the work; ~80% is a polynomial division
  implemented as a scalar loop. Replacing it with Newton iteration is the
  fix. It is switched off in the benchmark (`use_fft_phase1=False`).
* **One network topology.** The brief asks for several; `network_sim.py`
  models a single flat peer set.
