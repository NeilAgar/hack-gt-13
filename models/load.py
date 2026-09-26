"""Load A's parquet tables when present; otherwise synthetic fixtures."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from models.config import PROCESSED_DIR
from models.synthetic import build_synthetic


def _pad_ccn_series(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)


def _read_parquet(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if "ccn" in df.columns:
        df["ccn"] = _pad_ccn_series(df["ccn"])
    return df


def load_inputs(processed_dir: Path | None = None, n_synthetic: int = 80) -> dict[str, pd.DataFrame]:
    processed_dir = processed_dir or PROCESSED_DIR
    fac = _read_parquet(processed_dir / "facilities.parquet")
    surveys = _read_parquet(processed_dir / "surveys.parquet")
    scores = _read_parquet(processed_dir / "scores.parquet")
    if fac is not None and surveys is not None and scores is not None and len(fac) and len(surveys):
        source = "parquet"
        data = {"facilities": fac, "surveys": surveys, "scores": scores, "source": source}
        return data
    syn = build_synthetic(n_homes=n_synthetic)
    syn["source"] = "synthetic"
    return syn
