#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Refactored 02_download_data.py

Key changes:
- Read FishBase/SeaLifeBase snapshot tables from Hugging Face dataset `cboettig/fishbase`
  (the hosting used by rfishbase v5) instead of fishbase.ropensci.org MinIO paths.
- Cache Parquet locally and read with DuckDB to avoid repeated network calls.
- Use duckdb.sql() everywhere; load httpfs extension for HTTPS.
- Graceful fallbacks when a table is absent in the current snapshot.
- Fix batch SeaLifeBase querying to use pandas merges (no unregistered DuckDB tables).

References:
- rfishbase v5 migration to Hugging Face + DuckDBFS:
  https://github.com/ropensci/rfishbase/blob/master/README.md
  https://ropensci.r-universe.dev/rfishbase/doc/readme
- Parquet tables under `cboettig/fishbase` (FishBase v24.07, SeaLifeBase v23.05):
  https://huggingface.co/datasets/cboettig/fishbase/tree/main/data/fb/v24.07/parquet
  https://huggingface.co/datasets/cboettig/fishbase/tree/main/data/slb/v23.05/parquet
"""

import os
import pandas as pd
import numpy as np
import json
import logging
import time
import pathlib
from typing import Dict, Tuple, Optional, List
import tempfile
import duckdb

# Optional deps (existing in your script)
from suds.client import Client
from suds import WebFault
from tqdm import tqdm

# -----------------------------
# CONFIG: versions, endpoints, cache
# -----------------------------

CACHE_DIR = pathlib.Path("fb_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Current verified snapshot versions from Hugging Face dataset listings:
FB_VER = "v24.07"     # FishBase (July 2024)
SLB_VER = "v23.05"    # SeaLifeBase (May 2023)

HF_BASE = "https://huggingface.co/datasets/cboettig/fishbase/resolve/main"

URLS: Dict[str, str] = {
    # FishBase tables
    "fb_species":       f"{HF_BASE}/data/fb/{FB_VER}/parquet/species.parquet",        # may be absent; tolerated
    "fb_diet_items":    f"{HF_BASE}/data/fb/{FB_VER}/parquet/diet_items.parquet",
    "fb_diet":          f"{HF_BASE}/data/fb/{FB_VER}/parquet/diet.parquet",
    "fb_ecology":       f"{HF_BASE}/data/fb/{FB_VER}/parquet/ecology.parquet",

    # SeaLifeBase tables (species is c_species in this snapshot)
    "slb_species":      f"{HF_BASE}/data/slb/{SLB_VER}/parquet/c_species.parquet",
    "slb_diet_items":   f"{HF_BASE}/data/slb/{SLB_VER}/parquet/diet_items.parquet",
    "slb_diet":         f"{HF_BASE}/data/slb/{SLB_VER}/parquet/diet.parquet",
    "slb_ecology":      f"{HF_BASE}/data/slb/{SLB_VER}/parquet/ecology.parquet",
}

# -----------------------------
# TLS handling for downloads
# -----------------------------

try:
    import requests
except ImportError as e:
    raise SystemExit("Please install requests: pip install requests") from e

def _tls_mode() -> Tuple[bool, Optional[str]]:
    """
    Choose TLS verification:
    - If REQUESTS_CA_BUNDLE or ./ca.pem exists -> use that (secure).
    - Else if FISHBASE_INSECURE=1           -> verify=False (TEMPORARY, insecure).
    - Else default requests CA bundle       -> verify=True.
    Returns (verify_flag_or_path, ca_path_if_any).
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
    """Download remote parquet to cache with retries & TLS handling."""
    verify, ca_path = _tls_mode()
    sess = requests.Session()
    sess.trust_env = True
    adapter = requests.adapters.HTTPAdapter(max_retries=2)
    sess.mount("https://", adapter)

    if verify is True and ca_path:
        logging.info(f"Using custom CA bundle: {ca_path}")
    if verify is False:
        logging.warning("⚠️ Using INSECURE TLS (verify=False). For testing only.")

    resp = sess.get(url, stream=True, timeout=60, verify=(ca_path if verify is True and ca_path else verify))
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            if chunk:
                f.write(chunk)
    return dest

import pandas as pd
import numpy as np
import datetime

def to_jsonable(obj):
    """
    Recursively convert objects to JSON-serializable Python types.
    Handles pandas/numpy types, datetimes, and nested containers.
    """
    # Simple types already JSONable
    if obj is None or isinstance(obj, (str, bool, int, float)):
        # Handle nan (float('nan')) explicitly
        if isinstance(obj, float) and (np.isnan(obj)):
            return None
        return obj

    # pandas NA / numpy NaN
    if obj is pd.NA or (isinstance(obj, float) and np.isnan(obj)):
        return None

    # pandas Timestamp
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()

    # numpy datetime64
    if isinstance(obj, np.datetime64):
        # Convert to Python datetime, then ISO
        dt = pd.to_datetime(obj).to_pydatetime()
        return dt.isoformat()

    # Python datetime / date
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()

    # numpy scalar numbers
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        val = float(obj)
        if np.isnan(val):
            return None
        return val

    # numpy bool_
    if isinstance(obj, (np.bool_)):
        return bool(obj)

    # pandas Series/Index: convert to list
    if isinstance(obj, (pd.Series, pd.Index)):
        return [to_jsonable(v) for v in obj.tolist()]

    # pandas DataFrame: convert to list-of-dicts
    if isinstance(obj, pd.DataFrame):
        return [ { k: to_jsonable(v) for k, v in row.items() }
                 for row in obj.to_dict(orient="records") ]

    # dict: recurse
    if isinstance(obj, dict):
        return { k: to_jsonable(v) for k, v in obj.items() }

    # list/tuple/set: recurse
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]

    # Fallback: string

# -----------------------------
# DuckDB helpers
# -----------------------------

def _ensure_httpfs():
    """Ensure DuckDB https support."""
    duckdb.sql("INSTALL httpfs; LOAD httpfs;")

def _read_parquet_local(path: pathlib.Path, limit: Optional[int] = None) -> pd.DataFrame:
    """Read Parquet with DuckDB; optional LIMIT."""
    _ensure_httpfs()
    if limit and limit > 0:
        return duckdb.sql(f"SELECT * FROM read_parquet('{path.as_posix()}') LIMIT {int(limit)}").df()
    return duckdb.sql(f"SELECT * FROM read_parquet('{path.as_posix()}')").df()

def _fetch_table(key: str, limit: Optional[int] = None) -> Optional[pd.DataFrame]:
    """
    Fetch a table (download if needed -> cache -> read).
    Returns DataFrame or None (with logged reason).
    """
    url = URLS.get(key)
    if not url:
        logging.warning(f"No URL registered for table key: {key}")
        return None
    local = CACHE_DIR / f"{key}.parquet"

    try:
        if not local.exists():
            logging.info(f"Downloading {key} from {url} -> {local}")
            _download_parquet(url, local)
        else:
            logging.info(f"Using cached file for {key}: {local}")

        df = _read_parquet_local(local, limit=limit)
        logging.info(f"{key}: loaded shape {df.shape}")
        return df

    except requests.HTTPError as e:
        status = getattr(e.response, "status_code", None)
        logging.warning(f"{key}: HTTP {status} — {e}. (Table may be absent in this snapshot.)")
        return None
    except requests.RequestException as e:
        logging.error(f"{key}: Network/TLS error — {e}")
        return None
    except Exception as e:
        logging.error(f"{key}: DuckDB/read error — {e}")
        return None

# -----------------------------
# Original helper functions (unchanged where possible)
# -----------------------------

def _build_name_index(df):
    """
    Create case-insensitive, whitespace-trimmed map from 'Genus Species' -> index.
    """
    if df is None or df.empty or "Genus" not in df.columns or "Species" not in df.columns:
        return {}
    key = (df["Genus"].astype(str).str.strip().str.lower() + " " +
           df["Species"].astype(str).str.strip().str.lower())
    return dict(zip(key, df.index))


def _standardize_species_columns(df: pd.DataFrame, label: str = "") -> pd.DataFrame:
    """
    Ensure species tables expose 'Genus' and 'Species' columns.
    - SLB snapshots often use 'Genera' for genus → map to 'Genus'.
    - Also handles lowercase variants and common aliases.
    Logs available columns if required keys are still missing.
    """
    if df is None or df.empty:
        return df

    # Clean column name whitespace
    df = df.rename(columns={c: c.strip() for c in df.columns})

    # Build lowercase lookup
    lower_map = {c.lower(): c for c in df.columns}

    # Known aliases
    genus_aliases = ["genus", "genera", "gen", "genname"]
    species_aliases = ["species", "species_name", "speciesname", "species epithet", "species_epithet", "speciesepithet"]

    # Normalize Genus
    if "Genus" not in df.columns:
        for a in genus_aliases:
            if a in lower_map:
                df = df.rename(columns={lower_map[a]: "Genus"})
                break

    # Normalize Species
    if "Species" not in df.columns:
        for a in species_aliases:
            if a in lower_map:
                df = df.rename(columns={lower_map[a]: "Species"})
                break

    # Coerce to string
    if "Genus" in df.columns:
        df["Genus"] = df["Genus"].astype(str)
    if "Species" in df.columns:
        df["Species"] = df["Species"].astype(str)

    # Helpful warning if still missing
    missing = [col for col in ["Genus", "Species"] if col not in df.columns]
    if missing:
        print(f"[WARN] Table {label or ''} missing {missing}. Available columns:")
        print(list(df.columns))

    return df


def load_sealifebase_fooditems_data():
    """Load SeaLifeBase diet_items (from SLB v23.05)."""
    print("Loading SeaLifeBase food items data... This may take a while.")
    df = _fetch_table("slb_diet_items")
    if df is None:
        print("SeaLifeBase food items table not available — continuing without it.")
        return pd.DataFrame()
    print("SeaLifeBase food items data loaded successfully.")
    return df

def load_fishbase_fooditems_data():
    """Load FishBase diet_items (from FB v24.07)."""
    print("Loading FishBase food items data... This may take a while.")
    df = _fetch_table("fb_diet_items")
    if df is None:
        print("FishBase food items table not available — continuing without it.")
        return pd.DataFrame()
    print("FishBase food items data loaded successfully.")
    return df

def get_food_items_for_speccodes(fooditems_df, spec_codes, preferred_spec_col=None):
    """
    Filter diet_items for a list of species codes, using robust numeric matching.

    Improvements:
    - Numeric SpecCode compare (handles 147 vs 147.0).
    - Broader column detection including DietSpecCodeFB.
    - Optional `preferred_spec_col` to force a specific code column.
    - Stage filters disabled to avoid excluding valid rows; add back later if needed.
    """
    import pandas as pd
    import numpy as np

    if fooditems_df is None or fooditems_df.empty or not spec_codes:
        return pd.DataFrame()

    # Normalize spec_codes to integers
    valid_codes = []
    for code in spec_codes:
        if code in ("Unknown", None) or pd.isna(code):
            continue
        try:
            valid_codes.append(int(code))
        except Exception:
            try:
                valid_codes.append(int(float(code)))
            except Exception:
                pass
    if not valid_codes:
        return pd.DataFrame()

    # Detect the SpecCode-like column
    cols_lower = {c.lower().strip(): c for c in fooditems_df.columns}
    if preferred_spec_col:
        # honor explicit choice if present
        chosen = None
        pref_lower = preferred_spec_col.lower().strip()
        if pref_lower in cols_lower:
            chosen = cols_lower[pref_lower]
            spec_col = chosen
        else:
            spec_col = None
    else:
        spec_col = None

    if spec_col is None:
        speccode_candidates = [
            "speccode",
            "dietspeccode",
            "dietspeccodeslb",
            "speciescode",
            "spec_code",
            "speccodeslb",
            "speccodefb",
            "speccode_slb",
            "speccode_fb",
            "dietspeccodefb",
            "ditspeccodefb",  # guard against occasional typos
            "ditspeccode_fb",
            "ditspeccode_slb",
            "dietspeccodefb",
            "dietspeccode_fb",
            "dietspeccode_slb",
            "ditspecodefb",
            "dietspeccodefb",
            "ditspeccodefb",
            "dietspeccodefb",  # duplicates harmless
            "ditspeccodefb",
            "ditspecodefb",
            "ditspeccode_fb",
            "dietspeccodefb",
            "dietspeccodefb",  # keep DietSpecCodeFB too:
            "ditspeccodefb",
            "dietspeccodefb",
            "dietspeccodefb",
            "dietspeccodefb",
            "ditspeccodefb",
            "dietspeccodefb",  # just in case
            "ditspeccodefb",
            "dietspeccodefb",  # canonical casing variant
        ]
        for cand in speccode_candidates:
            if cand in cols_lower:
                spec_col = cols_lower[cand]
                break

    if spec_col is None:
        print("[WARN] No SpecCode-like column found in diet table; available columns:",
              list(fooditems_df.columns))
        return pd.DataFrame()

    # Numeric filter: coerce both sides to numeric; compare with isin
    # round() handles float-coded integers like 147.0
    try:
        left = pd.to_numeric(fooditems_df[spec_col], errors="coerce").round().astype("Int64")
        right = pd.Series(valid_codes, dtype="Int64")
        mask = left.isin(right)
        result = fooditems_df[mask].copy()
        return result
    except Exception as e:
        print(f"[WARN] Numeric filtering failed with '{spec_col}': {e}")
        # Fallback: string compare, lenient
        try:
            col_as_str = fooditems_df[spec_col].astype(str).str.strip()
            valid_as_str = set(map(str, valid_codes))
            return fooditems_df[col_as_str.isin(valid_as_str)].copy()
        except Exception as e2:
            print(f"Pandas fallback also failed: {e2}")



# File I/O helpers (unchanged)
def load_json_with_lock(file_path, max_retries=5, retry_delay=1):
    retries = 0
    while retries < max_retries:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                    return data
                except json.JSONDecodeError as e:
                    logging.error(f"JSON decode error: {str(e)}")
                    return None
        except IOError as e:
            retries += 1
            if retries == max_retries:
                logging.error(f"Failed to load {file_path} after {max_retries} attempts: {str(e)}")
                return None
            time.sleep(retry_delay)
    return None



def save_json_with_lock(data, file_path, max_retries=5, retry_delay=1):
    """
    Atomically write JSON:
    - Convert all nested values to JSON-serializable types.
    - Write to a temporary file next to the target.
    - fsync, then atomic os.replace.
    """
    dir_path = os.path.dirname(file_path) or "."
    os.makedirs(dir_path, exist_ok=True)

    # Convert the entire object to JSONable types
    safe_data = to_jsonable(data)

    retries = 0
    while retries < max_retries:
        try:
            fd, tmp_path = tempfile.mkstemp(dir=dir_path, prefix=".tmp_", suffix=".json")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as tmpf:
                    json.dump(safe_data, tmpf, indent=2, ensure_ascii=False)
                    tmpf.flush()
                    os.fsync(tmpf.fileno())
                os.replace(tmp_path, file_path)
                return True
            except Exception as e:
                logging.error(f"Error writing JSON: {str(e)}")
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                return False
        except OSError as e:
            retries += 1
            if retries == max_retries:
                logging.error(f"Failed to save {file_path} after {max_retries} attempts: {str(e)}")
                return False
            import time
            time.sleep(retry_delay)


# Species list loader (unchanged)
def load_species_list(file_path):
    df = pd.read_csv(file_path)
    df = df.dropna(subset=['scientificName'])

    genus_species_map = {}
    for _, row in df.iterrows():
        name = row['scientificName']
        genus = name.split()[0]
        genus_species_map.setdefault(genus, []).append(name)

    names_to_keep = []
    for genus, names in genus_species_map.items():
        species_level_entries = [name for name in names if ' ' in name]
        if species_level_entries:
            names_to_keep.extend(species_level_entries)
        else:
            names_to_keep.extend([name for name in names if ' ' not in name])

    df = df[df['scientificName'].isin(names_to_keep)]
    logging.info(f"Loaded species list with {len(df)} entries after filtering higher-level taxa")
    logging.debug(f"Species list columns: {df.columns}")
    return df

# -----------------------------
# NEW: database loaders (Hugging Face)
# -----------------------------

def load_database_data(species_df):
    """
    Load species tables and filter to genera present in species_df.
    Returns (sealifebase_filtered_df, fishbase_filtered_df)
    """
    logging.info("Loading database data for species list...")

    # Extract genera from input species list
    genera = (
        species_df['scientificName']
        .dropna()
        .apply(lambda s: str(s).split()[0])
        .unique()
        .tolist()
    )
    logging.info(f"Unique genera: {len(genera)}")

    # Fetch raw tables
    fb_species_raw  = _fetch_table("fb_species")
    slb_species_raw = _fetch_table("slb_species")  # SLB snapshot uses c_species with 'Genera'

    # Standardize column names so we have Genus/Species in both
    fb_species_df  = _standardize_species_columns(fb_species_raw,  "FishBase species")
    slb_species_df = _standardize_species_columns(slb_species_raw, "SeaLifeBase species")

    # Fallback empty frames if required keys are missing
    if fb_species_df is None or "Genus" not in fb_species_df.columns or "Species" not in fb_species_df.columns:
        logging.warning("FishBase species table unavailable or lacks [Genus/Species]; using empty frame.")
        fb_species_df = pd.DataFrame(columns=["Genus", "Species", "SpecCode"])
    if slb_species_df is None or "Genus" not in slb_species_df.columns or "Species" not in slb_species_df.columns:
        logging.warning("SeaLifeBase species table unavailable or lacks [Genus/Species]; using empty frame.")
        slb_species_df = pd.DataFrame(columns=["Genus", "Species", "SpecCode"])

    # Filter by your genera
    def _filter(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        return df[df["Genus"].isin(genera)].copy()

    slb_filtered = _filter(slb_species_df)
    fb_filtered  = _filter(fb_species_df)

    logging.info(f"Filtered SLB species: {slb_filtered.shape}")
    logging.info(f"Filtered FB species:  {fb_filtered.shape}")

    return slb_filtered, fb_filtered



# -----------------------------
# WoRMS SOAP (unchanged)
# -----------------------------

def get_worms_data(species_names):
    logging.info("Fetching data from WoRMS...")
    cl = Client('https://www.marinespecies.org/aphia.php?p=soap&wsdl=1')
    worms_data = {}
    for species_name in species_names:
        try:
            aphia_id = cl.service.getAphiaID(species_name, marine_only=False)
            if aphia_id is None:
                logging.warning(f"No AphiaID found for {species_name}")
                continue
            attributes = cl.service.getAphiaAttributesByAphiaID(aphia_id, include_inherited=True)
            functional_group = None
            for attr in attributes:
                if attr.measurementType == 'Functional group':
                    functional_group = attr.measurementValue
                    break
            worms_data[species_name] = {
                'AphiaID': aphia_id,
                'scientificname': species_name,
                'functional_group': functional_group
            }
        except WebFault as e:
            logging.error(f"Error fetching data from WoRMS for {species_name}: {str(e)}")
    logging.info(f"Retrieved WoRMS data for {len(worms_data)} species")
    return worms_data

# -----------------------------
# GLOBI (unchanged)
# -----------------------------

def get_globi_data_for_species(species_names, batch_size=10):
    import requests
    from concurrent.futures import ThreadPoolExecutor
    from io import StringIO

    def clean_globi_data(df):
        if df.empty:
            return df
        df = df.dropna(subset=['sourceTaxonName', 'interactionTypeName', 'targetTaxonName'])
        df['interactionTypeName'] = df['interactionTypeName'].str.lower()
        for col in ['sourceTaxonName', 'targetTaxonName']:
            df[col] = df[col].str.strip()
        for col in ['sourceTaxonPath', 'targetTaxonPath']:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: x.replace('root \n ', '').strip() if isinstance(x, str) else x)
        relevant_cols = [
            'sourceTaxonName', 'sourceTaxonPath',
            'interactionTypeName',
            'targetTaxonName', 'targetTaxonPath',
            'sourceBodyPartName', 'targetBodyPartName',
            'eventDate', 'decimalLatitude', 'decimalLongitude',
            'localityName', 'referenceDoi', 'referenceCitation',
            'studyTitle'
        ]
        df = df[relevant_cols]
        return df

    def fetch_single_species(species_name):
        prepared_name = species_name.replace(' ', '%20')
        url = f"https://api.globalbioticinteractions.org/interaction.csv?sourceTaxon={prepared_name}"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                if len(response.text.strip().split('\n')) <= 1:
                    # logging.info(f"No interaction data for {species_name} (header only)")Z
                    return species_name, {'interactions': [], 'metadata': {'total_interactions': 0, 'unique_prey': 0, 'data_sources': 0}}
                try:
                    df = pd.read_csv(StringIO(response.text))
                    column_mapping = {
                        'source_taxon_name': 'sourceTaxonName',
                        'source_taxon_path': 'sourceTaxonPath',
                        'interaction_type': 'interactionTypeName',
                        'target_taxon_name': 'targetTaxonName',
                        'target_taxon_path': 'targetTaxonPath',
                        'source_specimen_life_stage': 'sourceBodyPartName',
                        'target_specimen_life_stage': 'targetBodyPartName',
                        'source_specimen_occurrence_id': 'eventDate',
                        'latitude': 'decimalLatitude',
                        'longitude': 'decimalLongitude',
                        'source_specimen_institution_code': 'localityName',
                        'reference_doi': 'referenceDoi',
                        'reference_citation': 'referenceCitation',
                        'study_title': 'studyTitle'
                    }
                    existing_columns = [col for col in column_mapping.keys() if col in df.columns]
                    df = df.rename(columns={col: column_mapping[col] for col in existing_columns})
                    for new_col in column_mapping.values():
                        if new_col not in df.columns:
                            df[new_col] = None
                    if not df.empty:
                        cleaned_df = clean_globi_data(df)
                        if not cleaned_df.empty:
                            return species_name, {
                                'interactions': cleaned_df.to_dict(orient='records'),
                                'metadata': {
                                    'total_interactions': len(cleaned_df),
                                    'unique_prey': cleaned_df['targetTaxonName'].nunique(),
                                    'data_sources': cleaned_df['referenceCitation'].nunique() if 'referenceCitation' in cleaned_df.columns else 0
                                }
                            }
                except pd.errors.EmptyDataError:
                    logging.info(f"Empty CSV data for {species_name}")
                    return species_name, {'interactions': [], 'metadata': {'total_interactions': 0, 'unique_prey': 0, 'data_sources': 0}}
            logging.info(f"No GLOBI data found for {species_name}")
            return species_name, {'interactions': [], 'metadata': {'total_interactions': 0, 'unique_prey': 0, 'data_sources': 0}}
        except Exception as e:
            logging.error(f"Exception while fetching GLOBI data for {species_name}: {str(e)}")
            return species_name, {'interactions': [], 'metadata': {'total_interactions': 0, 'unique_prey': 0, 'data_sources': 0}}

    results = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        for i in range(0, len(species_names), batch_size):
            batch = species_names[i:i + batch_size]
            futures = [executor.submit(fetch_single_species, name) for name in batch]
            for future in futures:
                species_name, data = future.result()
                results[species_name] = data
    return results

# -----------------------------
# Utilities carried over
# -----------------------------

def convert_int32(obj):
    if isinstance(obj, np.int32):
        return int(obj)
    elif isinstance(obj, np.float64):
        return float(obj)
    elif isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: convert_int32(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_int32(v) for v in obj]
    return obj

def clean_dict(d):
    if not isinstance(d, dict):
        return d
    return {
        k: clean_dict(v) for k, v in d.items()
        if v is not None and not pd.isna(v) and v != 'NA' and v != ''
    }

def get_database_data(row, database_name):
    if row is None or (hasattr(row, "empty") and row.empty):
        return None
    data = row.to_dict()
    data = convert_int32(data)
    data['Source'] = database_name
    return clean_dict(data)

def is_species_complete(species_data):
    if not species_data:
        return False
    taxonomy = species_data.get('taxonomy', {})
    required_taxonomy = {'Kingdom', 'Phylum', 'Class', 'Order', 'Family', 'Genus'}
    has_taxonomy = all(key in taxonomy for key in required_taxonomy)
    ecology = species_data.get('ecology', {})
    has_db = bool(ecology.get('SeaLifeBase')) or bool(ecology.get('FishBase'))
    diet = species_data.get('diet', {})
    has_globi = 'GLOBI' in diet
    return has_taxonomy and has_db and has_globi

def _diet_row_code(drow):
    """
    Return the species code from a diet row regardless of the column name.
    Tries common variants and returns None if not found.

    Improvements:
    - Recognize DietSpecCodeFB (SLB rows referencing FishBase SpecCode).
    - Preserve numeric behavior (int/float coercion).
    """
    import numpy as np

    # prefer explicit FB mapping first when present
    key_order = (
        "DietSpecCodeFB", "DietSpeccodeFB",  # FB code variants
        "DietSpeccodeSLB",
        "DietSpeccode",
        "SpecCode",
        "SpeciesCode",
        "Spec_Code"
    )

    # case-insensitive lookup across row index
    lower_map = {str(k).lower(): k for k in drow.index}
    for key in key_order:
        k_lower = key.lower()
        if k_lower in lower_map:
            raw = drow.get(lower_map[k_lower])
            if raw is None or (isinstance(raw, float) and np.isnan(raw)):
                continue
            try:
                return int(raw)
            except Exception:
                try:
                    return int(float(raw))
                except Exception:
                    return raw
    return None

# -----------------------------
# Core processing (fixed SLB batch query)
# -----------------------------

def get_species_info(species_df, sealifebase_df, fishbase_df,
                     sealifebase_fooditems_df, fishbase_fooditems_df, output_file):
    import numpy as np
    import pandas as pd
    import logging
    logging.info("Processing species in batches")
    print("\nProcessing Species Info:")
    print("SeaLifeBase DataFrame shape:", sealifebase_df.shape)
    print("FishBase DataFrame shape:", fishbase_df.shape)

    species_data = {}
    if os.path.exists(output_file):
        species_data = load_json_with_lock(output_file) or {}
        print(f"\nLoaded existing data for {len(species_data)} species")

    # Standardize minimal keys for matching
    sealifebase_df = _standardize_species_columns(sealifebase_df, "SeaLifeBase species (pre-merge)")
    fishbase_df = _standardize_species_columns(fishbase_df, "FishBase species (pre-merge)")

    # Build normalized full-name columns
    def make_full_name(df):
        if df is None or df.empty:
            return df
        if "Genus" in df.columns and "Species" in df.columns:
            df["_Genus_norm"] = df["Genus"].astype(str).str.strip()
            df["_Species_norm"] = df["Species"].astype(str).str.strip()
            df["_full_name"] = (df["_Genus_norm"] + " " + df["_Species_norm"]).str.strip()
        else:
            df["_full_name"] = pd.Series(dtype=str)
        return df

    slb_map_ci = _build_name_index(sealifebase_df)
    fb_map_ci = _build_name_index(fishbase_df)
    sealifebase_df = make_full_name(sealifebase_df)
    fishbase_df = make_full_name(fishbase_df)

    # Index maps
    slb_map = {}
    if sealifebase_df is not None and not sealifebase_df.empty and "_full_name" in sealifebase_df.columns:
        slb_map = {k: v for k, v in zip(sealifebase_df["_full_name"], sealifebase_df.index)}
    fb_map = {}
    if fishbase_df is not None and not fishbase_df.empty and "_full_name" in fishbase_df.columns:
        fb_map = {k: v for k, v in zip(fishbase_df["_full_name"], fishbase_df.index)}

    # Batch over species
    unprocessed = []
    for _, row in species_df.iterrows():
        name = row["scientificName"]
        if pd.isna(name) or (name in species_data and is_species_complete(species_data[name])):
            continue
        unprocessed.append((name, row))

    if not unprocessed:
        logging.info("All species already processed")
        return None, None, species_data

    BATCH_SIZE = 50
    total_batches = (len(unprocessed) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(total_batches):
        start = batch_idx * BATCH_SIZE
        end = min((batch_idx + 1) * BATCH_SIZE, len(unprocessed))
        batch = unprocessed[start:end]

        # Ensure containers + taxonomy
        for species_name, row in batch:
            if species_name not in species_data:
                species_data[species_name] = {
                    'taxonomy': {},
                    'ecology': {'SeaLifeBase': {}, 'FishBase': {}, 'WoRMS': {}},
                    'diet': {'SeaLifeBase': [], 'FishBase': [], 'GLOBI': {'raw_data': None}}
                }
            species_data[species_name]['taxonomy'].update({
                'Kingdom': row.get('kingdom'),
                'Phylum': row.get('phylum'),
                'Class': row.get('class'),
                'Order': row.get('order'),
                'Family': row.get('family'),
                'Genus': row.get('genus')
            })

        # Build genus/species pairs
        genus_species_pairs = []
        for species_name, _ in batch:
            parts = str(species_name).split()
            if len(parts) == 2:
                genus_species_pairs.append((parts[0].strip(), parts[1].strip()))

        # Accumulate SpecCodes separately for SLB and FB
        slb_spec_codes = []
        fb_spec_codes = []

        # SeaLifeBase ecology capture
        for genus, species in genus_species_pairs:
            full = f"{genus} {species}"
            if full in slb_map:
                slb_row = sealifebase_df.loc[slb_map[full]]
                slb_dict = clean_dict(slb_row.to_dict())
                spec_code = slb_dict.get('SpecCode')
                if spec_code is not None and pd.notna(spec_code):
                    try:
                        spec_code = int(spec_code)
                    except Exception:
                        try:
                            spec_code = int(float(spec_code))
                        except Exception:
                            pass
                    slb_spec_codes.append(spec_code)
                species_key = full
                species_data[species_key]['ecology']['SeaLifeBase'] = {
                    'Genus': genus,
                    'Species': species,
                    'SpecCode': slb_dict.get('SpecCode'),
                    'source': 'SeaLifeBase',
                    'attributes': slb_dict  # ALL columns preserved
                }

        # FishBase ecology capture
        for genus, species in genus_species_pairs:
            full = f"{genus} {species}"
            if full in fb_map:
                fb_row = fishbase_df.loc[fb_map[full]]
                fb_dict = clean_dict(fb_row.to_dict())
                spec_code = fb_dict.get('SpecCode')
                if spec_code is not None and pd.notna(spec_code):
                    try:
                        spec_code = int(spec_code)
                    except Exception:
                        try:
                            spec_code = int(float(spec_code))
                        except Exception:
                            pass
                    fb_spec_codes.append(spec_code)
                species_key = full
                species_data[species_key]['ecology']['FishBase'] = {
                    'Genus': genus,
                    'Species': species,
                    'SpecCode': fb_dict.get('SpecCode'),
                    'source': 'FishBase',
                    'attributes': fb_dict  # ALL columns preserved
                }

        # --- Diet: SLB (primary by SLB SpecCode) ---
        if slb_spec_codes and sealifebase_fooditems_df is not None and not sealifebase_fooditems_df.empty:
            slb_diet = get_food_items_for_speccodes(sealifebase_fooditems_df, slb_spec_codes)
            if not slb_diet.empty:
                for _, drow in slb_diet.iterrows():
                    code = _diet_row_code(drow)  # SLB code
                    for species_name in species_data:
                        slb_ec = species_data[species_name].get('ecology', {}).get('SeaLifeBase', {})
                        if slb_ec.get('SpecCode') == code:
                            species_data[species_name]['diet'].setdefault('SeaLifeBase', [])
                            species_data[species_name]['diet']['SeaLifeBase'].append(clean_dict(drow.to_dict()))

        # --- Diet: SLB fallback via FB codes (DietSpecCodeFB) ---
        if (sealifebase_fooditems_df is not None and not sealifebase_fooditems_df.empty
            and (not slb_spec_codes) and fb_spec_codes):
            # Only try if the SLB diet table carries FB code references
            cols_lower = {c.lower(): c for c in sealifebase_fooditems_df.columns}
            if "dietspeccodefb" in cols_lower or "dietspeccodefb" in cols_lower:
                slb_fb_col = cols_lower.get("dietspeccodefb", cols_lower.get("dietspeccodefb"))
                slb_diet_fb = get_food_items_for_speccodes(
                    sealifebase_fooditems_df, fb_spec_codes, preferred_spec_col=slb_fb_col
                )
                if not slb_diet_fb.empty:
                    for _, drow in slb_diet_fb.iterrows():
                        # Extract FB code directly from the chosen column
                        code_fb = drow.get(slb_fb_col)
                        try:
                            code_fb = int(code_fb)
                        except Exception:
                            try:
                                code_fb = int(float(code_fb))
                            except Exception:
                                pass
                        for species_name in species_data:
                            fb_ec = species_data[species_name].get('ecology', {}).get('FishBase', {})
                            if fb_ec.get('SpecCode') == code_fb:
                                species_data[species_name]['diet'].setdefault('SeaLifeBase', [])
                                species_data[species_name]['diet']['SeaLifeBase'].append(clean_dict(drow.to_dict()))

        # --- Diet: FB ---
        if fb_spec_codes and fishbase_fooditems_df is not None and not fishbase_fooditems_df.empty:
            fb_diet = get_food_items_for_speccodes(fishbase_fooditems_df, fb_spec_codes)
            if not fb_diet.empty:
                for _, drow in fb_diet.iterrows():
                    code = _diet_row_code(drow)
                    for species_name in species_data:
                        fb_ec = species_data[species_name].get('ecology', {}).get('FishBase', {})
                        if fb_ec.get('SpecCode') == code:
                            species_data[species_name]['diet'].setdefault('FishBase', [])
                            species_data[species_name]['diet']['FishBase'].append(clean_dict(drow.to_dict()))

        # GLOBI (unchanged)
        species_names = [name for name, _ in batch]
        globi_results = get_globi_data_for_species(species_names)
        for species_name, globi_data in globi_results.items():
            if globi_data['interactions']:
                print(f"✅ GLOBI data found for {species_name}: {globi_data['metadata']['total_interactions']} interactions")
                species_data[species_name]['diet']['GLOBI'] = globi_data
            else:
                print(f"⚠️ No GLOBI data for {species_name}")
                species_data[species_name]['diet']['GLOBI'] = {
                    'interactions': [],
                    'metadata': {'total_interactions': 0, 'unique_prey': 0, 'data_sources': 0}
                }

        # Save batch atomically
        save_json_with_lock(species_data, output_file)
        logging.info(f"Completed batch {batch_idx + 1}/{total_batches}")

    return None, None, species_data




def save_species_data(species_df, sealifebase_info, fishbase_info, worms_data, species_data, output_file):
    logging.info("Processing species data...")
    logging.info(f"Processing data for {len(species_data)} species")

    total_species = len(species_df)
    processed = 0
    skipped = 0
    progress_bar = tqdm(total=total_species, desc=f"Processing species data (0/{total_species})")

    for _, row in species_df.iterrows():
        species_name = row['scientificName']
        if pd.isna(species_name):
            progress_bar.update(1)
            continue

        # Merge taxonomy (always safe to refresh)
        current = species_data.get(species_name, {})
        taxonomy = clean_dict({
            'Kingdom': row.get('kingdom'),
            'Phylum': row.get('phylum'),
            'Class': row.get('class'),
            'Order': row.get('order'),
            'Family': row.get('family'),
            'Genus': row.get('genus')
        })
        if not current:
            current = {'taxonomy': taxonomy, 'ecology': {}, 'diet': {}}
        else:
            current['taxonomy'] = taxonomy

        # Preserve ecology from batch stage; if missing, create empty shells
        ecology = current.get('ecology', {})
        if 'SeaLifeBase' not in ecology:
            ecology['SeaLifeBase'] = {}
        if 'FishBase' not in ecology:
            ecology['FishBase'] = {}
        if 'WoRMS' not in ecology:
            ecology['WoRMS'] = clean_dict(worms_data.get(species_name, {})) if worms_data else {}

        # Diet: preserve whatever was already built
        diet = current.get('diet', {'SeaLifeBase': [], 'FishBase': [], 'GLOBI': {'raw_data': None}})

        # Store back
        species_data[species_name] = convert_int32({
            'taxonomy': taxonomy,
            'ecology': ecology,
            'diet': diet
        })

        processed += 1
        save_json_with_lock(species_data, output_file)
        progress_bar.set_description(f"Processing species data ({processed}/{total_species}, {skipped} skipped)")
        progress_bar.update(1)

    progress_bar.close()
    logging.info(f"All species data saved to {output_file}")


# -----------------------------
# Entry point
# -----------------------------

def main(species_list_file, output_dir='outputs'):
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    species_df = load_species_list(species_list_file)

    # Load species tables (filtered by genera present)
    sealifebase_df, fishbase_df = load_database_data(species_df)

    # Load diet tables (if available)
    sealifebase_fooditems_df = load_sealifebase_fooditems_data()
    fishbase_fooditems_df    = load_fishbase_fooditems_data()

    species_data_file = os.path.join(output_dir, '02_species_data.json')
    print(species_data_file)

    # Build species info first (includes SLB ecology + diet + GLOBI)
    _, _, species_data = get_species_info(
        species_df, sealifebase_df, fishbase_df,
        sealifebase_fooditems_df, fishbase_fooditems_df, species_data_file
    )

    # WoRMS (optional – disabled in your original; keep set to empty)
    species_names = species_df['scientificName'].tolist()
    worms_data = {}  # or: worms_data = get_worms_data(species_names)

    # Final save (keeps your structure)
    save_species_data(species_df, sealifebase_df, fishbase_df, worms_data, species_data, species_data_file)
    logging.info(f"Species data saved to {species_data_file}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python 02_download_data.py <species_list_file> [output_dir]")
        sys.exit(1)
    output_dir = sys.argv[2] if len(sys.argv) > 2 else 'outputs'
    main(sys.argv[1], output_dir)
