"""Grouped holdouts: by device, attack type, botnet family, and device+type.
Run from the repo root: python ml/audit/audit_b.py CACHE_DIR"""
from pathlib import Path
import sys, warnings, json
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent)); from common import *
warnings.filterwarnings("ignore")
C = sys.argv[1]  # cache dir written by build_cache.py
u = load(f"{C}/uniform.npz"); X, y = u["X"], u["y"]
summ = pd.read_csv("data/data_summary.csv"); summ.columns = [c.strip() for c in summ.columns]
n_of = dict(zip(summ["File Name"].str.replace(".csv", "", regex=False), summ["Data Count"]))
flen = np.array([n_of[f"{d}.{k}"] for d, k in zip(u["dev"], u["kind"])])
benign = y == 0
early = u["row"] < 0.7 * flen          # benign rows are split by time: first 70% train, last 30% test
results = {}

def run(name, tr, te):
    sc, m = fit(X[tr], y[tr]); p = m.predict(sc.transform(X[te]))
    r = metrics(y[te], p); results[name] = (r, y[te], p)
    print(f"{name:34s} n_test={len(te):6d} " + fmt(r), flush=True)

def pooled(prefix, title):
    ys = np.concatenate([v[1] for k, v in results.items() if k.startswith(prefix)])
    ps = np.concatenate([v[2] for k, v in results.items() if k.startswith(prefix)])
    print(f"--- {title} POOLED: " + fmt(metrics(ys, ps)), flush=True)

print("### 1. Random 80/20 on the uniform sample (what the old number does, on honest data)")
rng = np.random.default_rng(1); perm = rng.permutation(len(y)); cut = int(.8 * len(y))
run("random_rows", perm[:cut], perm[cut:])

print("\n### 2. Leave-one-DEVICE-out (train on 8 devices, test on the 9th, all of its traffic)")
for d in range(1, 10):
    run(f"device_{d}", np.where(u["dev"] != d)[0], np.where(u["dev"] == d)[0])
pooled("device_", "leave-one-device-out")

print("\n### 3. Leave-one-ATTACK-TYPE-out (benign split by time; test = held-out attack + unseen benign)")
kinds = sorted(set(u["kind"]) - {"benign"})
for k in kinds:
    tr = np.where((u["kind"] != k) & (~benign | early))[0]
    te = np.where((u["kind"] == k) | (benign & ~early))[0]
    run(f"attack_{k}", tr, te)
pooled("attack_", "leave-one-attack-type-out")

print("\n### 4. Leave-one-FAMILY-out (train on one botnet family, test on the other)")
for fam in ("mirai", "gafgyt"):
    tr = np.where((u["fam"] != fam) & (~benign | early))[0]
    te = np.where((u["fam"] == fam) | (benign & ~early))[0]
    run(f"family_{fam}", tr, te)

print("\n### 5. Hardest: unseen device AND unseen attack type together (leave device d + type k out, sampled)")
rng = np.random.default_rng(5)
for d, k in [(1, "mirai.udp"), (2, "gafgyt.tcp"), (4, "mirai.syn"), (5, "gafgyt.scan"), (6, "mirai.ack"), (8, "gafgyt.junk")]:
    tr = np.where((u["dev"] != d) & (u["kind"] != k))[0]
    te = np.where((u["dev"] == d) & ((u["kind"] == k) | benign))[0]
    run(f"both_dev{d}_{k}", tr, te)
pooled("both_", "device+attack-type")
json.dump({k: v[0] for k, v in results.items()}, open(f"{C}/audit_b.json", "w"), indent=1)
