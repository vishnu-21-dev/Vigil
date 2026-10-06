"""Per-type breakdown of the family miss, and false alarms at the failsafe threshold.
Run from the repo root: python ml/audit/audit_c.py CACHE_DIR"""
from pathlib import Path
import sys, warnings
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent)); from common import *
warnings.filterwarnings("ignore")
u = load(f"{sys.argv[1]}/uniform.npz"); X, y = u["X"], u["y"]
summ = pd.read_csv("data/data_summary.csv"); summ.columns = [c.strip() for c in summ.columns]
n_of = dict(zip(summ["File Name"].str.replace(".csv", "", regex=False), summ["Data Count"]))
flen = np.array([n_of[f"{d}.{k}"] for d, k in zip(u["dev"], u["kind"])])
benign = y == 0; early = u["row"] < 0.7 * flen

print("### C1. Mirai-trained model on BASHLITE: recall per attack type")
tr = np.where((u["fam"] != "gafgyt") & (~benign | early))[0]
sc, m = fit(X[tr], y[tr])
for k in sorted(k for k in set(u["kind"]) if k.startswith("gafgyt")):
    te = u["kind"] == k
    print(f"  {k:14s} recall={m.predict(sc.transform(X[te])).mean():.4f}")

print("\n### C2. Leave-one-device-out at the FAILSAFE threshold (attack prob >= 0.85 => auto-quarantine)")
tot = np.zeros(4, int)
for d in range(1, 10):
    tr = u["dev"] != d; te = ~tr
    sc, m = fit(X[tr], y[tr]); pr = m.predict_proba(sc.transform(X[te]))[:, 1]
    yt = y[te]; p = (pr >= 0.85).astype(int); r = metrics(yt, p)
    tot += [r["tn"], r["fp"], r["fn"], r["tp"]]
    print(f"  device_{d}: FPR@0.85={r['fpr']:.4f}  recall@0.85={r['recall']:.4f}  FP={r['fp']}/{r['fp']+r['tn']}")
tn, fp, fn, tp = tot
print(f"  POOLED @0.85: P={tp/(tp+fp):.4f} R={tp/(tp+fn):.4f} FPR={fp/(fp+tn):.4f} [TN={tn} FP={fp} FN={fn} TP={tp}]")
