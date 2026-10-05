"""
Times the block-circulant decoder across three versions of itself.

    python3 decoder_version_benchmark.py     # -> decoder_version_results.json

Why this exists. The block-circulant decode times reported in
docs/benchmark_1D_2D_BC_report.md carry an implementation penalty that is not
a property of block-circulant codes, and a reader comparing those numbers
against 1D-RS or 2D-RS deserves to know its size.

The penalty comes from making the local code FFT-capable. An NTT needs its
evaluation points to be roots of unity, and the evaluation points *define the
code* -- the encoder uses the same ones -- so the fallback solver ends up
working over 255-bit field elements where it previously used the small
integers 1..n0. In pure-Python modular arithmetic operand width is not free.
The cost is paid whether or not the transform ever runs, and it falls only on
the block-circulant rows: 1D-RS and 2D-RS are untouched.

Three versions are measured, each in its own process against its own git
worktree, so the comparison is free of machine drift:

    pre-NTT   8d93ae3  before the NTT decoder was added; small-integer nodes
    main      main     the NTT decoder as merged; attempts the transform,
                       fails on every call, falls back -- paying for both
    current   HEAD     transform fixed and switched off; roots of unity kept

Takes a few minutes. Requires a clean working tree, since it creates git
worktrees of other commits and removes them afterwards.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRE_NTT_COMMIT = "8d93ae3"

# (label, git ref or None for the working tree)
VERSIONS = [("pre-NTT", PRE_NTT_COMMIT), ("main", "main"), ("current", None)]

WORKER = r'''
import sys, os, time, json, inspect, random
repo, tag, out = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, repo); os.chdir(repo)
import numpy as np, blob_generator as bg, BCcodeEthereum as bc
GF, K = bg.GF, bg.FIELD_ELEMENTS_PER_BLOB
rnd = random.Random(20260929)
blob = bg.bytes_to_blobs(
    bytes(rnd.randrange(256) for _ in range(bg.USABLE_BYTES_PER_BLOB)))[0]
# Only the current version has the switches; the older two predate them.
has_switch = "use_fft_phase1" in inspect.signature(bc.dec_cbc_2).parameters
res = {}
for om, lam in [(2048, 2), (1024, 2), (1024, 3), (512, 2)]:
    rh = om; mu = K // om; n = mu * (rh + om)
    c = bc.encode_bc_structured(GF, GF(blob), mu, lam, om, rh)
    for rate in (0.10, 0.20):
        best, ok = None, None
        for t in range(3):                     # min of 3, robust to CPU spikes
            m = np.random.default_rng(1000 + t).random(n) < rate
            cc = c.copy(); cc[m] = GF(0)
            kw = dict(pair_unknown_cap=256)
            if has_switch:
                kw.update(use_fft_phase1=False, use_fft_phase2=False)
            t0 = time.time()
            rec, rem = bc.dec_cbc_2(None, cc, m.copy(), mu, lam, om, rh, **kw)
            dt = time.time() - t0
            good = (not np.any(rem)) and [int(v) for v in rec[:K]] == list(blob)
            if best is None or dt < best:
                best, ok = dt, good
        res[f"om{om}-L{lam}@{rate}"] = dict(t=round(best, 3), ok=bool(ok))
        print(f"  {tag:<9} om={om:<5} lam={lam} rate={rate}: "
              f"{best:7.3f}s ok={good}", flush=True)
json.dump(res, open(out, "w"), indent=2)
'''


def main():
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=HERE,
                           capture_output=True, text=True).stdout.strip()
    if dirty:
        sys.exit("working tree is not clean -- commit or stash first, because "
                 "this creates git worktrees of other commits")

    tmp = tempfile.mkdtemp(prefix="decoder-versions-")
    worker = os.path.join(tmp, "_worker.py")
    with open(worker, "w") as f:
        f.write(WORKER)

    out = {}
    try:
        for label, ref in VERSIONS:
            if ref is None:
                repo = HERE
            else:
                repo = os.path.join(tmp, label.replace("-", "_"))
                subprocess.run(["git", "worktree", "add", "-q", repo, ref],
                               cwd=HERE, check=True)
            jf = os.path.join(tmp, f"{label}.json")
            print(f"[{label}]")
            subprocess.run([sys.executable, worker, repo, label, jf], check=True)
            with open(jf) as f:
                out[label] = json.load(f)
    finally:
        for label, ref in VERSIONS:
            if ref is None:
                continue
            repo = os.path.join(tmp, label.replace("-", "_"))
            if os.path.isdir(repo):
                subprocess.run(["git", "worktree", "remove", repo, "--force"],
                               cwd=HERE, capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)

    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=HERE,
                          capture_output=True, text=True).stdout.strip()
    payload = {
        "_what": "Block-circulant decode time across three versions of the "
                 "decoder, same machine, same erasure patterns, min of 3.",
        "_why": "The BC decode times in the benchmark report carry an "
                "implementation penalty from defining the local code over "
                "255-bit roots of unity rather than small integers. It is "
                "paid whether or not the NTT runs, and falls only on the BC "
                "rows. This measures its size so the report can state it.",
        "versions": {"pre-NTT": PRE_NTT_COMMIT, "main": "main", "current": head},
        "results": out,
    }
    path = os.path.join(HERE, "decoder_version_results.json")
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\nwrote {os.path.basename(path)}")

    pre, cur = out["pre-NTT"], out["current"]
    rs = sorted(cur[k]["t"] / pre[k]["t"] for k in pre)
    med = rs[len(rs) // 2] if len(rs) % 2 else (rs[len(rs) // 2 - 1]
                                                + rs[len(rs) // 2]) / 2
    print(f"median current/pre-NTT = {med:.2f}x")


if __name__ == "__main__":
    main()
