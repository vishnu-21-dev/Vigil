"""Follow-up experiments: sampling fix, benign-only per-device detector, false-alarm confidence.
Run from the repo root: python ml/audit/audit_d.py CACHE_DIR"""
from pathlib import Path
import sys, warnings
import numpy as np, pandas as pd
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
sys.path.insert(0, str(Path(__file__).parent)); from common import *
warnings.filterwarnings("ignore")
C = sys.argv[1]
o = load(f"{C}/orig.npz"); u = load(f"{C}/uniform.npz")
X, y = u["X"], u["y"]
summ = pd.read_csv("data/data_summary.csv"); summ.columns = [c.strip() for c in summ.columns]
n_of = dict(zip(summ["File Name"].str.replace(".csv", "", regex=False), summ["Data Count"]))
flen = np.array([n_of[f"{d}.{k}"] for d, k in zip(u["dev"], u["kind"])])
benign = y == 0; early = u["row"] < 0.7 * flen

print("### D1. Does fixing the sampling help? Leave-one-device-out, test = uniform rows of the held-out device")
rng = np.random.default_rng(3)
fid = np.array([f"{d}.{k}" for d, k in zip(u["dev"], u["kind"])])
sub = np.concatenate([rng.choice(np.where(fid == f)[0], size=min(1123, (fid == f).sum()), replace=False)
                      for f in np.unique(fid)])  # same size as pipeline.py's sample, but random rows
for label, (Xs, ys, ds) in {
    "first 1123 rows/file (pipeline.py today)": (o["X"], o["y"], o["dev"]),
    "random 1123 rows/file (same size)": (X[sub], y[sub], u["dev"][sub]),
    "random 4000 rows/file": (X, y, u["dev"]),
}.items():
    ys_all, ps_all = [], []
    for d in range(1, 10):
        sc, m = fit(Xs[ds != d], ys[ds != d])
        te = u["dev"] == d
        ys_all.append(y[te]); ps_all.append(m.predict(sc.transform(X[te])))
    print(f"  {label:42s} " + fmt(metrics(np.concatenate(ys_all), np.concatenate(ps_all))), flush=True)

print("\n### D2. Per-device detector trained on that device's BENIGN traffic only (no attack labels at all)")
print("    threshold = 99.5th percentile of scores on a held-back slice of training benign (not tuned on test)")
for name in ("pca_recon", "isolation_forest"):
    rows = []
    for d in range(1, 10):
        dev = u["dev"] == d
        btr = np.where(dev & benign & early)[0]
        bte = np.where(dev & benign & ~early)[0]
        att = np.where(dev & ~benign)[0]
        fit_idx, cal_idx = btr[: int(0.8 * len(btr))], btr[int(0.8 * len(btr)):]
        sc = StandardScaler().fit(X[fit_idx])
        Z = lambda idx: sc.transform(X[idx])
        if name == "pca_recon":
            pca = PCA(n_components=0.99, random_state=0).fit(Z(fit_idx))
            score = lambda idx: ((Z(idx) - pca.inverse_transform(pca.transform(Z(idx)))) ** 2).mean(1)
        else:
            iso = IsolationForest(n_estimators=200, random_state=0, n_jobs=-1).fit(Z(fit_idx))
            score = lambda idx: -iso.score_samples(Z(idx))
        thr = np.percentile(score(cal_idx), 99.5)
        fpr = (score(bte) > thr).mean()
        hit = score(att) > thr
        for k in np.unique(u["kind"][att]):
            rows.append((d, k, hit[u["kind"][att] == k].mean()))
        rows.append((d, "benign_fpr", fpr))
    df = pd.DataFrame(rows, columns=["dev", "kind", "rate"])
    by_kind = df.groupby("kind")["rate"].mean()
    print(f"  [{name}] recall per attack type (mean over devices):")
    print("   " + "  ".join(f"{k}={v:.3f}" for k, v in by_kind.drop("benign_fpr").items()))
    per_dev_fpr = df[df.kind == "benign_fpr"].set_index("dev")["rate"]
    print(f"   benign false-alarm rate on later traffic: mean={per_dev_fpr.mean():.4f} worst={per_dev_fpr.max():.4f} (device {per_dev_fpr.idxmax()})", flush=True)

print("\n### D3. Device 8 false alarms: how confident is the classifier? (leave-device-8-out)")
sc, m = fit(X[u["dev"] != 8], y[u["dev"] != 8])
b8 = (u["dev"] == 8) & benign
pr = m.predict_proba(sc.transform(X[b8]))[:, 1]
for t in (0.5, 0.85, 0.9, 0.95, 0.99):
    print(f"  benign rows with attack prob >= {t}: {(pr >= t).mean():.4f}")
a8 = (u["dev"] == 8) & ~benign
pa = m.predict_proba(sc.transform(X[a8]))[:, 1]
for t in (0.85, 0.95, 0.99):
    print(f"  attack recall at >= {t}: {(pa >= t).mean():.4f}")

print("\n### D4. Failsafe threshold across ALL held-out devices (leave-one-device-out, pooled)")
print("    alerts still fire at 0.5 for a human; only auto-quarantine uses this threshold")
probs, labels, devs = [], [], []
for d in range(1, 10):
    tr = u["dev"] != d
    sc, m = fit(X[tr], y[tr])
    probs.append(m.predict_proba(sc.transform(X[~tr]))[:, 1]); labels.append(y[~tr]); devs.append(u["dev"][~tr])
probs, labels, devs = map(np.concatenate, (probs, labels, devs))
for t in (0.85, 0.9, 0.95, 0.99):
    auto = probs >= t
    fpr = auto[labels == 0].mean(); rec = auto[labels == 1].mean()
    worst = max((auto[(labels == 0) & (devs == d)].mean(), d) for d in range(1, 10))
    print(f"  >= {t}: benign auto-quarantine rate={fpr:.4f} (worst device {worst[1]}: {worst[0]:.4f})  attack auto-quarantine recall={rec:.4f}")
