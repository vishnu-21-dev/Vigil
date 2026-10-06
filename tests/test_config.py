from __future__ import annotations

import importlib
from pathlib import Path

from api import config


ROOT_DIR = Path(__file__).resolve().parents[1]


def test_relative_model_dir_resolves_against_repo_root_not_cwd(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_DIR", "ml/models")
    monkeypatch.chdir(tmp_path)
    try:
        reloaded = importlib.reload(config)
        resolved = Path(reloaded.settings.model_dir)
        assert resolved.is_absolute()
        assert resolved == ROOT_DIR / "ml" / "models"
        assert resolved.resolve().is_relative_to(ROOT_DIR)
        assert not resolved.resolve().is_relative_to(tmp_path)
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_default_model_dir_is_inside_repo(monkeypatch):
    monkeypatch.delenv("MODEL_DIR", raising=False)
    try:
        reloaded = importlib.reload(config)
        assert Path(reloaded.settings.model_dir) == ROOT_DIR / "ml" / "models"
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_failsafe_timeout_defaults_to_120(monkeypatch):
    monkeypatch.delenv("FAILSAFE_TIMEOUT", raising=False)
    try:
        assert importlib.reload(config).settings.failsafe_timeout == 120
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_failsafe_timeout_reads_env(monkeypatch):
    monkeypatch.setenv("FAILSAFE_TIMEOUT", "30")
    try:
        assert importlib.reload(config).settings.failsafe_timeout == 30
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_failsafe_timeout_rejects_bad_values(monkeypatch):
    import pytest

    try:
        for bad in ("abc", "0", "-5"):
            monkeypatch.setenv("FAILSAFE_TIMEOUT", bad)
            with pytest.raises(ValueError, match="FAILSAFE_TIMEOUT"):
                importlib.reload(config)
    finally:
        monkeypatch.undo()
        importlib.reload(config)
