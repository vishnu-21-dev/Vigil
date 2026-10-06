import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support, roc_auc_score
from sklearn.preprocessing import StandardScaler

def load(path):
    z = np.load(path, allow_pickle=False)
    d = {k: z[k] for k in z.files}
    d["y"] = (d["fam"] != "benign").astype(int)
    d["X"] = np.nan_to_num(np.where(np.isinf(d["X"]), np.nan, d["X"]), nan=0.0)  # same cleaning as pipeline
    return d

def fit(X, y):
    sc = StandardScaler().fit(X)
    m = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1, class_weight="balanced")
    m.fit(sc.transform(X), y)   # hyperparameters identical to ml/pipeline.py; no tuning
    return sc, m

def metrics(y, p):
    tn, fp, fn, tp = confusion_matrix(y, p, labels=[0, 1]).ravel()
    pr, rc, f1, _ = precision_recall_fscore_support(y, p, labels=[1], zero_division=0)
    return dict(tn=int(tn), fp=int(fp), fn=int(fn), tp=int(tp), precision=float(pr[0]), recall=float(rc[0]),
                f1=float(f1[0]), acc=float((tn + tp) / len(y)), fpr=float(fp / max(tn + fp, 1)))

def fmt(m):
    return (f"acc={m['acc']:.4f} P={m['precision']:.4f} R={m['recall']:.4f} F1={m['f1']:.4f} "
            f"FPR={m['fpr']:.4f}  [TN={m['tn']} FP={m['fp']} FN={m['fn']} TP={m['tp']}]")
