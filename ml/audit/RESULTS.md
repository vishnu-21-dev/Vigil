# Accuracy audit (2026-10-06)

Checks whether the 99.99% figure for `ml/models/model.pkl` survives honest splits. The hyperparameters are the same as `ml/pipeline.py` (100 trees, `class_weight="balanced"`, seed 42) and nothing was tuned. "Attack" is the positive class.

## Reproduce

```bash
python ml/audit/build_cache.py <N-BaIoT dir> <cache dir>   # ~80s, reads all 89 traffic CSVs
python ml/audit/audit_a.py <cache dir>                     # reproduction + leakage
python ml/audit/audit_b.py <cache dir>                     # grouped holdouts
python ml/audit/audit_c.py <cache dir>                     # breakdowns
```

There are two samples:

- **orig**: the first 1,123 rows of each of the 89 CSVs (99,947 rows), which is exactly what `pipeline.py` trained on.
- **uniform**: 4,000 random rows from anywhere in each file (356,000 rows).

## 1. The original number reproduces, and the saved model is that model

The test set is the original random 80/20 split of `orig`.

| | Precision | Recall | F1 | Confusion `[TN FP; FN TP]` |
|---|---|---|---|---|
| saved `model.pkl` | 0.9999 | 1.0000 | 1.0000 | `[2020 1; 0 17969]` |

A retrain on sklearn 1.8.0 agrees with the saved model on 100% of predictions.

## 2. Leakage checks

| Check | Result | Verdict |
|---|---|---|
| Exact duplicate rows, train vs. test | 48.5% of test rows have an identical feature vector in train. None carry conflicting labels. | Leaky split |
| Temporal neighbours | 95.9% of test rows have the row immediately before or after them (same capture file) in train | Leaky split |
| Features that encode the label | Best single-feature AUC is 0.926 (`HpHp_L0.01_radius`), none above 0.99, and no ID, label or file columns | No direct label leak |
| Features encode the device | A classifier identifies which of the 9 devices sent benign traffic with 97.4% accuracy | Risk for unseen devices |
| Sampling bias | `pipeline.py` reads the **first** 1,123 rows of each file (the start of each capture), not a random sample. Benign is 10.1% of rows. | Biased sample |
| Label inference | `_infer_label_from_path` looks for "benign"/"normal" in the **whole path**, so a dataset folder named e.g. `normal_runs/` would label every row benign | Fragile, not triggered here |

Even with this leakage, training on the first rows and testing on rows later in the same files still gives P 0.9994, R 0.9998, FPR 0.54%. So the random split inflates the number only slightly **for devices and attack types the model has already seen**.

## 3. Honest splits (uniform sample)

| Split | Precision | Recall | F1 | Benign false-alarm rate | Pooled confusion `[TN FP; FN TP]` |
|---|---|---|---|---|---|
| Random rows (for comparison) | 1.0000 | 1.0000 | 1.0000 | 0.00% | `[7297 0; 3 63900]` |
| Leave one **device** out (9 folds) | 0.9990 | 1.0000 | 0.9995 | 0.89% | `[35679 321; 16 319984]` |
| Leave one **attack type** out (10 folds) | 0.9999 | 0.9979 | 0.9989 | 0.02% | `[109108 22; 665 319335]` |
| Unseen device **and** unseen attack type (6 pairs) | 0.9872 | 0.9980 | 0.9926 | 1.30% | `[23689 311; 48 23952]` |
| Train Gafgyt, test **Mirai** | 1.0000 | 0.9943 | 0.9971 | 0.02% | `[10911 2; 794 139206]` |
| Train Mirai, test **Gafgyt (BASHLITE)** | 1.0000 | **0.5990** | **0.7492** | 0.00% | `[10913 0; 72177 107823]` |

In the attack-type and family rows, benign traffic is split by time: the first 70% of each benign capture is used for training and the last 30% for testing.

Where it breaks:

- **New botnet family.** A model trained without BASHLITE catches **0%** of BASHLITE TCP floods and **0%** of BASHLITE UDP floods. BASHLITE combo, junk and scan are still above 99.5%. Missing attack *types* within a known family is fine (worst: `gafgyt.scan` at 98.3% recall). Missing a whole *family* is not.
- **New devices raise false alarms.** False alarms on benign traffic jump on some unseen devices: device 4 (Philips baby monitor) 2.9%, device 8 (SimpleHome XCS7-1002 camera) 4.7%. At the failsafe's 0.85 confidence threshold, device 8 still flags 3.5% of benign rows (139/4000), and Vigil auto-quarantines on those.

## What can honestly be claimed

- ~99.9% F1 **on N-BaIoT devices and botnet families seen in training**, including on held-out devices (0.9995) and held-out attack types (0.9989).
- **Not** "99.99% accuracy" as a general claim. The random-row split shares duplicate and adjacent rows across train and test.
- It does **not** generalize to a botnet family it wasn't trained on (recall 0.60, with 0% on two flood types), and on some unseen devices it raises benign false alarms of up to ~4.7% of rows.
- All of this is N-BaIoT only (9 devices, 2 botnets, lab captures). Nothing here measures performance on real deployed traffic.
