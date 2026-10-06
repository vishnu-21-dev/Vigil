"""Build two cached samples of N-BaIoT. usage: build_cache.py DATA_DIR OUT_DIR"""
import re, sys, time
from pathlib import Path
import numpy as np, pandas as pd

data_dir, out = Path(sys.argv[1]), Path(sys.argv[2])
files = sorted(f for f in data_dir.rglob("*.csv") if re.search(r"\.(benign|mirai|gafgyt)", f.name))
assert len(files) == 89, len(files)
summary = pd.read_csv(data_dir / "data_summary.csv")
summary.columns = [c.strip() for c in summary.columns]
counts = dict(zip(summary["File Name"], summary["Data Count"]))
FIRST = 100000 // len(files)   # 1052, identical to ml/pipeline.py
UNI = 4000
rng = np.random.default_rng(0)

def meta(f):
    dev, *kind = f.stem.split(".")
    kind = ".".join(kind)
    fam = "benign" if kind == "benign" else kind.split(".")[0]
    return int(dev), kind, fam

cols = None
orig = {k: [] for k in "X dev kind fam row".split()}
uni = {k: [] for k in "X dev kind fam row".split()}
t0 = time.time()
for f in files:
    dev, kind, fam = meta(f)
    n = counts[f.name]
    pick = np.sort(rng.choice(n, size=min(UNI, n), replace=False))
    seen = 0
    for chunk in pd.read_csv(f, dtype=np.float32, chunksize=250_000):
        if cols is None: cols = list(chunk.columns)
        assert list(chunk.columns) == cols
        lo, hi = seen, seen + len(chunk)
        if lo < FIRST:
            part = chunk.iloc[: FIRST - lo]
            orig["X"].append(part.to_numpy()); k = len(part)
            orig["dev"] += [dev]*k; orig["kind"] += [kind]*k; orig["fam"] += [fam]*k
            orig["row"] += list(range(lo, lo + k))
        sel = pick[(pick >= lo) & (pick < hi)]
        uni["X"].append(chunk.iloc[sel - lo].to_numpy())
        uni["dev"] += [dev]*len(sel); uni["kind"] += [kind]*len(sel); uni["fam"] += [fam]*len(sel)
        uni["row"] += sel.tolist()
        seen = hi
    assert seen == n, (f.name, seen, n)   # summary counts match the real files
    print(f"{f.name} rows={n} {time.time()-t0:.0f}s", flush=True)

for name, d in (("orig", orig), ("uniform", uni)):
    np.savez_compressed(out / f"{name}.npz", X=np.vstack(d["X"]), dev=np.array(d["dev"]),
        kind=np.array(d["kind"]), fam=np.array(d["fam"]), row=np.array(d["row"]), cols=np.array(cols))
    print(name, len(d["dev"]))
