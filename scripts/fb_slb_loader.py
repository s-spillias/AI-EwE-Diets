#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fb_slb_loader.py — robust test & loader for FishBase/SeaLifeBase tables.

Features:
- Uses Hugging Face dataset 'cboettig/fishbase' (current hosting used by rfishbase v5).
- Downloads Parquet with secure CA (REQUESTS_CA_BUNDLE) or temporary insecure mode.
- Caches files locally under ./fb_cache and reads with DuckDB.
- Provides functions compatible with your pipeline:
  * load_database_data(species_df)
  * load_sealifebase_fooditems_data()
  * load_fishbase_fooditems_data()
  * get_food_items_for_speccodes(sealifebase_df, spec_codes)

References:
- rfishbase v5: Hosting & access via Hugging Face datasets & DuckDBFS:
  https://github.com/ropensci/rfishbase/blob/master/README.md
  https://ropensci.r-universe.dev/rfishbase/doc/readme
- Hugging Face dataset 'cboettig/fishbase' listings (tables & versions):
  https://huggingface.co/datasets/cboettig/fishbase/tree/main/data/fb/v24.07/parquet
  https://huggingface.co/datasets/cboettig/fishbase/tree/main/data/slb/v23.05/parquet
"""

import os
import pathlib
import logging
from typing import Dict, Tuple, Optional, List

import duckdb
import pandas as pd

try:
    import requests
except ImportError as e:
    raise SystemExit("Please install requests: pip install requests") from e


# -----------------------------
# Configuration & URL registry
# -----------------------------

CACHE_DIR = pathlib.Path("fb_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# You can adjust versions here after checking the HF dataset listings
FB_VER = "v24.07"     # FishBase snapshot (July 2024)
SLB_VER = "v23.05"    # SeaLifeBase snapshot (May 2023)

HF_BASE = "https://huggingface.co/datasets/cboettig/fishbase/resolve/main"

URLS: Dict[str, str] = {
    # FishBase tables
    "fb_species":       f"{HF_BASE}/data/fb/{FB_VER}/parquet/species.parquet",       # may be absent; handled
    "fb_diet_items":    f"{HF_BASE}/data/fb/{FB_VER}/parquet/diet_items.parquet",
    "fb_diet":          f"{HF_BASE}/data/fb/{FB_VER}/parquet/diet.parquet",
    "fb_ecology":       f"{HF_BASE}/data/fb/{FB_VER}/parquet/ecology.parquet",

    # SeaLifeBase tables
    "slb_species":      f"{HF_BASE}/data/slb/{SLB_VER}/parquet/c_species.parquet",   # species variant present
    "slb_diet_items":   f"{HF_BASE}/data/slb/{SLB_VER}/parquet/diet_items.parquet",
    "slb_diet":         f"{HF_BASE}/data/slb/{SLB_VER}/parquet/diet.parquet",
    "slb_ecology":      f"{HF_BASE}/data/slb/{SLB_VER}/parquet/ecology.parquet",
}

# -----------------------------
# TLS / download helpers
# -----------------------------

def _tls_mode() -> Tuple[bool, Optional[str]]:
    """
    Decide TLS verification strategy:
    - If REQUESTS_CA_BUNDLE is set or ./ca.pem exists, use it (secure).
    - Else if FISHBASE_INSECURE=1, use verify=False (temporary, insecure).
    - Else default requests CA bundle (secure).
    Returns: (verify_bool_or_path, path_used_or_None)
    """
    ca_env = os.environ.get("REQUESTS_CA_BUNDLE")
    ca_local = pathlib.Path("ca.pem")
    insecure = os.environ.get("FISHBASE_INSECURE") == "1"

    if ca_env:
        return True, ca_env
    if ca_local.exists():
        return True, str(ca_local)
    if insecure:
        return False, None
    return True, None


def _download_parquet(url: str, dest: pathlib.Path) -> pathlib.Path:
    """Download a remote parquet to local cache with retries and TLS handling."""
    verify, ca_path = _tls_mode()
    sess = requests.Session()
    sess.trust_env = True  # respect proxies

    # Basic retry adapter
    adapter = requests.adapters.HTTPAdapter(max_retries=2)
    sess.mount("https://", adapter)

    if verify is True and ca_path:
        logging.info(f"Using custom CA bundle: {ca_path}")

    if verify is False:
        logging.warning("⚠️ Using INSECURE TLS (verify=False). For testing only.")

    resp = sess.get(url, stream=True, timeout=45, verify=(ca_path if verify is True and ca_path else verify))
    resp.raise_for_status()

    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            if chunk:
                f.write(chunk)
    return dest


def _ensure_httpfs():
    """Ensure DuckDB has httpfs extension loaded; harmless if repeated."""
    duckdb.sql("INSTALL httpfs; LOAD httpfs;")


def _read_parquet_local(path: pathlib.Path, limit: Optional[int] = None) -> pd.DataFrame:
    """Read a local parquet file with DuckDB, optionally limiting rows."""
    _ensure_httpfs()
    if limit and limit > 0:
        return duckdb.sql(f"SELECT * FROM read_parquet('{path.as_posix()}') LIMIT {int(limit)}").df()
    return duckdb.sql(f"SELECT * FROM read_parquet('{path.as_posix()}')").df()


def _fetch_table(key: str, limit: Optional[int] = None) -> Optional[pd.DataFrame]:
    """
    Fetch a table by registry key:
    - Downloads to cache (reuses if exists).
    - Reads with DuckDB.
    Returns DataFrame or None on failure (logs warning).
    """
    url = URLS.get(key)
    if not url:
        logging.warning(f"No URL registered for key: {key}")
        return None

    local = CACHE_DIR / f"{key}.parquet"
    try:
        # Reuse cached file if present
        if not local.exists():
            logging.info(f"Downloading {key} -> {local} from {url}")
            _download_parquet(url, local)
        else:
            logging.info(f"Using cached file for {key}: {local}")

        df = _read_parquet_local(local, limit=limit)
        logging.info(f"{key}: loaded shape {df.shape}")
        return df
    except requests.HTTPError as e:
        status = getattr(e.response, "status_code", None)
        logging.warning(f"{key}: HTTP error {status} — {e}. (URL may be absent or moved.)")
        return None
    except requests.RequestException as e:
        logging.error(f"{key}: Network/TLS error — {e}")
        return None
    except Exception as e:
        logging.error(f"{key}: DuckDB/read error — {e}")
        return None


# -----------------------------
# Public loader functions
# -----------------------------

def load_fishbase_fooditems_data() -> Optional[pd.DataFrame]:
    """Load FishBase diet_items table."""
    return _fetch_table("fb_diet_items")

def load_sealifebase_fooditems_data() -> Optional[pd.DataFrame]:
    """Load SeaLifeBase diet_items table."""
    return _fetch_table("slb_diet_items")

def load_database_data(species_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load species rows for the genera present in species_df.
    Gracefully tolerates missing remote objects by returning empty frames when absent.
    """
    # Get unique genera from species list
    genera = (
        species_df["scientificName"]
        .dropna()
        .apply(lambda s: str(s).split()[0] if isinstance(s, str) else None)
        .dropna()
        .unique()
        .tolist()
    )
    logging.info(f"Unique genera in input list: {len(genera)}")

    # Fetch species tables (FB may be absent at v24.07, SLB uses c_species)
    fb_species_df = _fetch_table("fb_species")
    slb_species_df = _fetch_table("slb_species")

    # If absent, create empty DataFrames with expected columns
    if fb_species_df is None:
        logging.warning("FishBase species table not available — proceeding with empty FB species frame.")
        fb_species_df = pd.DataFrame(columns=["Genus", "Species", "SpecCode"])
    if slb_species_df is None:
        logging.warning("SeaLifeBase species table not available — proceeding with empty SLB species frame.")
        slb_species_df = pd.DataFrame(columns=["Genus", "Species", "SpecCode"])

    # Filter to relevant genera
    def _filter_by_genera(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or "Genus" not in df.columns:
            return df
        return df[df["Genus"].isin(genera)].copy()

    fb_filtered = _filter_by_genera(fb_species_df)
    slb_filtered = _filter_by_genera(slb_species_df)

    logging.info(f"FB species filtered shape: {fb_filtered.shape}")
    logging.info(f"SLB species filtered shape: {slb_filtered.shape}")

    return slb_filtered, fb_filtered


def get_food_items_for_speccodes(fooditems_df: pd.DataFrame, spec_codes: List[int]) -> pd.DataFrame:
    """
    Batch filter food items for given SpecCodes with life-stage conditions like your original script.
    """
    if fooditems_df is None or fooditems_df.empty or not spec_codes:
        return pd.DataFrame()

    valid_codes = [int(c) for c in spec_codes if pd.notna(c)]
    if not valid_codes:
        return pd.DataFrame()

    # Register DF in DuckDB and query with conditions
    duckdb.register("fooditems_df", fooditems_df)

    query = f"""
        SELECT
            SpecCode, PreySpecCode, AlphaCode,
            Foodgroup, Foodname, PreyStage, PredatorStage,
            FoodI, FoodII, FoodIII,
            Commoness, CommonessII, PreyTroph, PreySeTroph
        FROM fooditems_df
        WHERE SpecCode IN ({','.join(map(str, valid_codes))})
          AND (PreyStage LIKE '%adult%' OR PreyStage LIKE '%juv%')
          AND (PredatorStage LIKE '%adult%' OR PredatorStage LIKE '%juv%')
    """

    try:
        return duckdb.sql(query).df()
    except Exception as e:
        logging.error(f"Error querying food items: {e}")
        return pd.DataFrame()


# -----------------------------
# CLI diagnostic (optional)
# -----------------------------

def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("DuckDB version:\n", duckdb.sql("PRAGMA version").fetchdf(), "\n")

    # Quick availability check & preview
    keys = [
        "fb_diet_items", "fb_diet", "fb_species",
        "slb_diet_items", "slb_diet", "slb_species"
    ]
    for key in keys:
        print(f"--- Testing '{key}'")
        df = _fetch_table(key, limit=5)
        if df is not None and not df.empty:
            print(df.head(), "\n")
        else:
            print(f"(not available or empty preview)\n")


if __name__ == "__main__":
    main()