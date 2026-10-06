"""Leakage checks and reproduction of the original 99.99%.
Run from the repo root: python ml/audit/audit_a.py CACHE_DIR"""
from pathlib import Path
import sys, joblib, warnings
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.neighbors import NearestNeighbors
sys.path.insert(0, str(Path(__file__).parent)); from common import *
warnings.filterwarnings("ignore")
C = sys.argv[1]  # cache dir written by build_cache.py
o = load(f"{C}/orig.npz"); u = load(f"{C}/uniform.npz")
X, y = o["X"], o["y"]
print("== A1 composition of original 100k sample")
print(f"rows={len(y)} benign={int((y==0).sum())} ({(y==0).mean():.1%}) attack={int((y==1).sum())}")
print("rows per file: min/max", np.unique(o["row"], return_counts=False).max()+1)
idx = np.arange(len(y))
tr, te = train_test_split(idx, test_size=0.2, random_state=42, stratify=y)

print("\n== A2 reproduce the original headline (same sample, same random 80/20 split)")
sc, m = fit(X[tr], y[tr]); p = m.predict(sc.transform(X[te]))
print("retrained (sklearn 1.8.0):", fmt(metrics(y[te], p)))
saved = joblib.load("ml/models/model.pkl"); ssc = joblib.load("ml/models/scaler.pkl")
ps = saved.predict(ssc.transform(X[te]))
print("SAVED model.pkl         :", fmt(metrics(y[te], ps)))
print("saved vs retrained prediction agreement:", float((p == ps).mean()))

print("\n== A3 exact duplicates")
V = np.ascontiguousarray(X).view(np.dtype((np.void, X.dtype.itemsize * X.shape[1]))).ravel()
_, inv, cnt = np.unique(V, return_inverse=True, return_counts=True)
print(f"rows that have an exact twin elsewhere in the sample: {int((cnt[inv] > 1).sum())} ({(cnt[inv]>1).mean():.2%})")
trset = set(inv[tr]); in_tr = np.array([i in trset for i in inv[te]])
print(f"TEST rows whose exact feature vector also appears in TRAIN: {int(in_tr.sum())} ({in_tr.mean():.2%})")
# conflicting labels for identical vectors
lab = {}
for i, l in zip(inv, y): lab.setdefault(i, set()).add(l)
print("identical vectors carrying both labels:", sum(len(v) > 1 for v in lab.values()))
fp_ = in_tr & (p != y[te]); print("misclassified test rows that are train duplicates:", int(fp_.sum()))

print("\n== A4 temporal adjacency (rows are consecutive captures from the same file)")
fid = np.array([f"{d}.{k}" for d, k in zip(o["dev"], o["kind"])])
pos = {(f, r): i for i, (f, r) in enumerate(zip(fid, o["row"]))}
trs = set(tr.tolist())
adj = [any(pos.get((fid[i], o["row"][i] + dlt)) in trs for dlt in (-1, 1)) for i in te]
print(f"TEST rows with an immediate neighbour (row +-1, same file) in TRAIN: {np.mean(adj):.2%}")
Z = sc.transform(X); nn = NearestNeighbors(n_neighbors=1).fit(Z[tr]); dist, ind = nn.kneighbors(Z[te])
nbr_same_file = fid[tr][ind[:, 0]] == fid[te]
print(f"nearest TRAIN neighbour comes from the same file: {nbr_same_file.mean():.2%}; median NN distance {np.median(dist):.3f}")
close = np.abs(o["row"][tr][ind[:, 0]] - o["row"][te]) <= 5
print(f"...and within 5 rows of the test row: {(nbr_same_file & close).mean():.2%}")

print("\n== A5 do single features encode the label?")
auc = np.array([max(roc_auc_score(y, X[:, j]), 1 - roc_auc_score(y, X[:, j])) for j in range(X.shape[1])])
cols = o["cols"]; top = np.argsort(-auc)[:8]
print("top single-feature AUCs (orig sample):", [(str(cols[j]), round(float(auc[j]), 4)) for j in top])
print("features with AUC>0.99:", int((auc > 0.99).sum()), "of", len(auc))
imp = m.feature_importances_; ti = np.argsort(-imp)[:8]
print("top RF importances:", [(str(cols[j]), round(float(imp[j]), 3)) for j in ti])
print("any column name containing label/device/file info:", [c for c in map(str, cols) if any(s in c.lower() for s in ("label","dev","file","id"))])

print("\n== A6 do the features identify the DEVICE? (benign rows only, random split)")
b = np.where(y == 0)[0]; btr, bte = train_test_split(b, test_size=0.2, random_state=0, stratify=o["dev"][b])
from sklearn.ensemble import RandomForestClassifier as RF
dm = RF(n_estimators=50, n_jobs=-1, random_state=0).fit(Z[btr], o["dev"][btr])
print(f"device-id accuracy from traffic features alone: {dm.score(Z[bte], o['dev'][bte]):.4f}  (chance ~{1/9:.2f})")

print("\n== A7 same model, rows it never could have seen: later parts of the SAME files")
sc2, m2 = fit(X, y)   # train on ALL of the first-1123-rows sample
later = u["row"] >= 1123
pl = m2.predict(sc2.transform(u["X"][later]))
print(f"train=first 1123 rows/file (all of orig sample); test={int(later.sum())} rows from row>=1123 (uniform sample)")
print(fmt(metrics(u["y"][later], pl)))
