import pandas as pd
import numpy as np
import os
import duckdb
import json
import logging
import subprocess
import time
from suds.client import Client
from suds import WebFault
from tqdm import tqdm

# Import diet data functions
def load_sealifebase_fooditems_data():
    print("Loading SeaLifeBase food items data... This may take a while.")
    data = duckdb.read_parquet("https://fishbase.ropensci.org/sealifebase/fooditems.parquet")
    print("SeaLifeBase data loaded successfully.")
    return data

def load_fishbase_fooditems_data():
    print("Loading FishBase food items data... This may take a while.")
    data = duckdb.read_parquet("https://fishbase.ropensci.org/fishbase/fooditems.parquet")
    print("FishBase data loaded successfully.")
    return data

def get_food_items_for_speccodes(sealifebase_df, spec_codes):
    """Batch process multiple SpecCodes at once"""
    if not spec_codes:
        return pd.DataFrame()
    
    # Filter out invalid codes
    valid_codes = [code for code in spec_codes if code not in ("Unknown", None) and not pd.isna(code)]
    if not valid_codes:
        return pd.DataFrame()
    
    query = f"""
    SELECT 
        SpecCode, PreySpecCode, AlphaCode, 
        Foodgroup, Foodname, PreyStage, PredatorStage, FoodI, FoodII, FoodIII, 
        Commoness, CommonessII, PreyTroph, PreySeTroph
    FROM sealifebase_df
    WHERE SpecCode IN ({','.join(map(str, valid_codes))})
    AND PreyStage LIKE '%adult%'
    AND PredatorStage LIKE '%adult%'
    """
    try:
        result = duckdb.query(query).df()
        return result
    except Exception as e:
        print(f"Error querying food items for SpecCodes: {str(e)}")
        return pd.DataFrame()

# Set up logging
# logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Get the absolute path of the EwE directory
EWE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def load_json_with_lock(file_path, max_retries=5, retry_delay=1):
    """Load JSON file with file locking to handle concurrent access"""
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
    """Save JSON file with file locking to handle concurrent access"""
    retries = 0
    while retries < max_retries:
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                try:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    return True
                except Exception as e:
                    logging.error(f"Error writing JSON: {str(e)}")
                    return False
        except IOError as e:
            retries += 1
            if retries == max_retries:
                logging.error(f"Failed to save {file_path} after {max_retries} attempts: {str(e)}")
                return False
            time.sleep(retry_delay)
    return False

def load_species_list(file_path):
    df = pd.read_csv(file_path)
    # Filter out rows where scientificName is NA
    df = df.dropna(subset=['scientificName'])
    
    # Create a dictionary to store genus to species mappings
    genus_species_map = {}
    
    # Group species by their genus
    for _, row in df.iterrows():
        name = row['scientificName']
        genus = name.split()[0]  # Get the first word as genus
        if genus not in genus_species_map:
            genus_species_map[genus] = []
        genus_species_map[genus].append(name)
    
    # Filter out genus-level entries if species-level entries exist
    names_to_keep = []
    for genus, names in genus_species_map.items():
        # Check if there are any species-level entries (names with spaces)
        species_level_entries = [name for name in names if ' ' in name]
        if species_level_entries:
            # If species-level entries exist, only keep those
            names_to_keep.extend(species_level_entries)
        else:
            # If no species-level entries, keep the genus-level entry
            names_to_keep.extend([name for name in names if ' ' not in name])
    
    # Filter the dataframe to keep only the selected names
    df = df[df['scientificName'].isin(names_to_keep)]
    
    logging.info(f"Loaded species list with {len(df)} entries after filtering higher-level taxa")
    logging.debug(f"Species list columns: {df.columns}")
    return df

def load_database_data(species_df):
    """Load only necessary data from databases based on species list"""
    logging.info("Loading database data for species list...")
    
    # Extract unique genera from species list
    genera = set()
    for name in species_df['scientificName']:
        if pd.isna(name):
            continue
        parts = name.split()
        if len(parts) >= 1:
            genera.add(parts[0])
    
    genera_list = list(genera)
    genera_conditions = ",".join([f"'{g}'" for g in genera_list])
    
    # Load only relevant species from SeaLifeBase
    logging.info("Loading filtered SeaLifeBase data...")
    slb_query = f"""
    SELECT *
    FROM read_parquet('https://fishbase.ropensci.org/sealifebase/species.parquet')
    WHERE Genus IN ({genera_conditions})
    """
    sealifebase_data = duckdb.query(slb_query).df()
    # Load only relevant species from FishBase
    logging.info("Loading filtered FishBase data...")
    fb_query = f"""
    SELECT *
    FROM read_parquet('https://fishbase.ropensci.org/fishbase/species.parquet')
    WHERE Genus IN ({genera_conditions})
    """
    fishbase_data = duckdb.query(fb_query).df()
    
    return sealifebase_data, fishbase_data

def get_worms_data(species_names):
    logging.info("Fetching data from WoRMS...")
    cl = Client('https://www.marinespecies.org/aphia.php?p=soap&wsdl=1')
    
    worms_data = {}
    for species_name in species_names:
        try:
            # Get AphiaID
            aphia_id = cl.service.getAphiaID(species_name, marine_only=False)
            if aphia_id is None:
                logging.warning(f"No AphiaID found for {species_name}")
                continue
            
            # Get attributes using AphiaID
            attributes = cl.service.getAphiaAttributesByAphiaID(aphia_id, include_inherited=True)
            
            # Extract functional group
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

def get_globi_data_for_species(species_names, batch_size=10):
    """Fetch and clean GLOBI data for multiple species in parallel using requests"""
    import requests
    from concurrent.futures import ThreadPoolExecutor
    from io import StringIO
    
    def clean_globi_data(df):
        """Clean and format GLOBI interaction data"""
        if df.empty:
            return df
            
        # Remove rows with missing critical data
        df = df.dropna(subset=['sourceTaxonName', 'interactionTypeName', 'targetTaxonName'])
        
        # Clean interaction types
        df['interactionTypeName'] = df['interactionTypeName'].str.lower()
        
        # # Filter for relevant interactions (focusing on diet-related)
        # diet_interactions = ['eats', 'preys on', 'feeds on', 'preysOn']
        # df = df[df['interactionTypeName'].isin(diet_interactions)]
        
        # Clean species names and taxonomic paths
        for col in ['sourceTaxonName', 'targetTaxonName']:
            df[col] = df[col].str.strip()
        
        # Clean taxonomic paths by removing 'root |' prefix
        for col in ['sourceTaxonPath', 'targetTaxonPath']:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: x.replace('root | ', '').strip() if isinstance(x, str) else x)
        
        # Select relevant columns
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
                # Print raw data for debugging
                print(f"\nRaw GLOBI data for {species_name}:")
                print(response.text[:1000])  # Print first 500 chars to avoid flooding terminal
                # Check if response only contains header
                if len(response.text.strip().split('\n')) <= 1:
                    logging.info(f"No interaction data for {species_name} (header only)")
                    return species_name, {'interactions': [], 'metadata': {'total_interactions': 0, 'unique_prey': 0, 'data_sources': 0}}
                
                try:
                    # Parse CSV data
                    df = pd.read_csv(StringIO(response.text))
                    
                    # Map column names to match our expected format
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
                    
                    # Rename columns that exist in our data
                    existing_columns = [col for col in column_mapping.keys() if col in df.columns]
                    df = df.rename(columns={col: column_mapping[col] for col in existing_columns})
                    
                    # Add missing columns with None values
                    for new_col in column_mapping.values():
                        if new_col not in df.columns:
                            df[new_col] = None
                    
                    if not df.empty:
                        # Clean and format the data
                        cleaned_df = clean_globi_data(df)
                        if not cleaned_df.empty:
                            # Convert to dict format for JSON serialization
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
                except Exception as e:
                    logging.error(f"Error parsing CSV data for {species_name}: {str(e)}")
                    return species_name, {'interactions': [], 'metadata': {'total_interactions': 0, 'unique_prey': 0, 'data_sources': 0}}
                
                return species_name, {'interactions': [], 'metadata': {'total_interactions': 0, 'unique_prey': 0, 'data_sources': 0}}
            else:
                logging.info(f"No GLOBI data found for {species_name}")
                return species_name, {'interactions': [], 'metadata': {'total_interactions': 0, 'unique_prey': 0, 'data_sources': 0}}
        except Exception as e:
            logging.error(f"Exception while fetching GLOBI data for {species_name}: {str(e)}")
            return species_name, {'interactions': [], 'metadata': {'total_interactions': 0, 'unique_prey': 0, 'data_sources': 0}}
    
    results = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        # Process species in batches to avoid overwhelming the API
        for i in range(0, len(species_names), batch_size):
            batch = species_names[i:i + batch_size]
            futures = [executor.submit(fetch_single_species, name) for name in batch]
            for future in futures:
                species_name, data = future.result()
                results[species_name] = data
    
    return results

def convert_int32(obj):
    if isinstance(obj, np.int32):
        return int(obj)
    elif isinstance(obj, np.float64):
        return float(obj)
    elif isinstance(obj, pd.Timestamp):  # Handle Timestamp objects
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: convert_int32(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_int32(v) for v in obj]
    return obj

def get_species_info(species_df, sealifebase_df, fishbase_df, sealifebase_fooditems_df, fishbase_fooditems_df, output_file):
    logging.info("Processing species in batches")
    
    print("\nProcessing Species Info:")
    print("SeaLifeBase DataFrame shape:", sealifebase_df.shape)
    print("FishBase DataFrame shape:", fishbase_df.shape)
    
    # Load existing data if available
    species_data = {}
    if os.path.exists(output_file):
        species_data = load_json_with_lock(output_file) or {}
        print(f"\nLoaded existing data for {len(species_data)} species")
    
    # Filter out already processed species
    unprocessed_species = []
    for idx, row in species_df.iterrows():
        species_name = row['scientificName']
        if pd.isna(species_name) or (species_name in species_data and is_species_complete(species_data[species_name])):
            continue
        unprocessed_species.append((species_name, row))
    
    if not unprocessed_species:
        logging.info("All species already processed")
        return None, None, species_data
    
    # Process species in batches
    BATCH_SIZE = 50
    total_batches = (len(unprocessed_species) + BATCH_SIZE - 1) // BATCH_SIZE
    
    for batch_idx in range(total_batches):
        start_idx = batch_idx * BATCH_SIZE
        end_idx = min((batch_idx + 1) * BATCH_SIZE, len(unprocessed_species))
        batch = unprocessed_species[start_idx:end_idx]
        
        # Prepare batch queries
        genus_species_pairs = []
        spec_codes = []
        
        for species_name, row in batch:
            # Initialize species data if not exists
            if species_name not in species_data:
                species_data[species_name] = {
                    'taxonomy': {},
                    'ecology': {'SeaLifeBase': {}, 'FishBase': {}, 'WoRMS': {}},
                    'diet': {'SeaLifeBase': [], 'FishBase': [], 'GLOBI': {'raw_data': None}}
                }
            
            # Extract taxonomy data
            species_data[species_name]['taxonomy'].update({
                'Kingdom': row.get('kingdom'),
                'Phylum': row.get('phylum'),
                'Class': row.get('class'),
                'Order': row.get('order'),
                'Family': row.get('family'),
                'Genus': row.get('genus')
            })
            
            genus_species = species_name.split()
            if len(genus_species) == 2:
                genus_species_pairs.append((genus_species[0], genus_species[1]))
        
        # Batch query SeaLifeBase
        if genus_species_pairs:
            conditions = " OR ".join([f"(Genus = '{g}' AND Species = '{s}')" for g, s in genus_species_pairs])
            slb_query = f"SELECT * FROM sealifebase_df WHERE {conditions}"
            slb_results = duckdb.query(slb_query).df()
            
            # Process SeaLifeBase results
            for _, slb_row in slb_results.iterrows():
                species_name = f"{slb_row['Genus']} {slb_row['Species']}"
                # Only process species that are in our input list
                if species_name not in [name for name, _ in batch]:
                    continue
                    
                if not pd.isna(slb_row['SpecCode']):
                    spec_codes.append(slb_row['SpecCode'])
                
                ecology_data = {
                    'habitat': {
                        'Fresh': slb_row.get('Fresh'),
                        'Brack': slb_row.get('Brack'),
                        'Saltwater': slb_row.get('Saltwater'),
                        'Land': slb_row.get('Land'),
                        'DemersPelag': slb_row.get('DemersPelag')
                    },
                    'depth': {
                        'DepthRangeShallow': slb_row.get('DepthRangeShallow'),
                        'DepthRangeDeep': slb_row.get('DepthRangeDeep')
                    },
                    'characteristics': {
                        'Length': slb_row.get('Length'),
                        'LTypeMaxM': slb_row.get('LTypeMaxM'),
                        'Importance': slb_row.get('Importance'),
                        'Comments': slb_row.get('Comments')
                    },
                    'specCode': slb_row.get('SpecCode'),
                    'author': slb_row.get('Author'),
                    'commonName': slb_row.get('FBname'),
                    'source': 'SeaLifeBase'
                }
                species_data[species_name]['ecology']['SeaLifeBase'] = ecology_data
        
        # Batch get diet data
        if spec_codes:
            diet_items = get_food_items_for_speccodes(sealifebase_fooditems_df, spec_codes)
            if not diet_items.empty:
                for _, diet_row in diet_items.iterrows():
                    spec_code = diet_row['SpecCode']
                    # Find species name for this SpecCode
                    for species_name in species_data:
                        if species_data[species_name].get('ecology', {}).get('SeaLifeBase', {}).get('specCode') == spec_code:
                            if 'SeaLifeBase' not in species_data[species_name]['diet']:
                                species_data[species_name]['diet']['SeaLifeBase'] = []
                            species_data[species_name]['diet']['SeaLifeBase'].append(diet_row.to_dict())
        
        # Batch get GLOBI data
        species_names = [name for name, _ in batch]
        globi_results = get_globi_data_for_species(species_names)
        for species_name, globi_data in globi_results.items():
            if globi_data['interactions']:
                species_data[species_name]['diet']['GLOBI'] = globi_data
            else:
                species_data[species_name]['diet']['GLOBI'] = {
                    'interactions': [],
                    'metadata': {'total_interactions': 0, 'unique_prey': 0, 'data_sources': 0}
                }
        
        # Save after each batch
        save_json_with_lock(species_data, output_file)
        logging.info(f"Completed batch {batch_idx + 1}/{total_batches}")
    
    return None, None, species_data

def clean_dict(d):
    if not isinstance(d, dict):
        return d
    return {k: clean_dict(v) for k, v in d.items() 
            if v is not None and not pd.isna(v) and v != 'NA' and v != ''}

def get_database_data(row, database_name):
    if row is None or row.empty:
        return None
    
    # Convert row to dictionary and handle Timestamp objects
    data = row.to_dict()
    data = convert_int32(data)  # Convert any Timestamp objects to ISO format strings
    data['Source'] = database_name
    
    return clean_dict(data)

def is_species_complete(species_data):
    """Check if we have all possible data for a species"""
    if not species_data:
        return False
    
    # Check taxonomy data
    taxonomy = species_data.get('taxonomy', {})
    required_taxonomy = {'Kingdom', 'Phylum', 'Class', 'Order', 'Family', 'Genus'}
    has_taxonomy = all(key in taxonomy for key in required_taxonomy)
    
    # Check ecology data
    ecology = species_data.get('ecology', {})
    has_db = bool(ecology.get('SeaLifeBase')) or bool(ecology.get('FishBase'))
    
    # Check diet data
    diet = species_data.get('diet', {})
    has_globi = 'GLOBI' in diet
    
    return has_taxonomy and has_db and has_globi

def save_species_data(species_df, sealifebase_info, fishbase_info, worms_data, species_data, output_file):
    logging.info("Processing species data...")
    
    # Use the existing species_data passed in
    logging.info(f"Processing data for {len(species_data)} species")
    
    total_species = len(species_df)
    processed = 0
    skipped = 0
    
    # Process species with progress tracking
    progress_bar = tqdm(total=total_species, desc=f"Processing species data (0/{total_species})")
    for _, row in species_df.iterrows():
        species_name = row['scientificName']
        if pd.isna(species_name):
            continue
        
        # Check if species is already fully processed in current file
        if species_name in species_data and is_species_complete(species_data[species_name]):
            skipped += 1
            progress_bar.set_description(f"Processing species data ({processed}/{total_species}, {skipped} skipped)")
            progress_bar.update(1)
            continue
        
        # Get database rows by matching Genus and Species
        genus_species = species_name.split()
        if len(genus_species) == 2:
            genus, species = genus_species
            slb_row = sealifebase_info[(sealifebase_info['Genus'] == genus) & (sealifebase_info['Species'] == species)].iloc[0] if not sealifebase_info[(sealifebase_info['Genus'] == genus) & (sealifebase_info['Species'] == species)].empty else None
            fb_row = fishbase_info[(fishbase_info['Genus'] == genus) & (fishbase_info['Species'] == species)].iloc[0] if not fishbase_info[(fishbase_info['Genus'] == genus) & (fishbase_info['Species'] == species)].empty else None
        else:
            slb_row = None
            fb_row = None
        
        sealifebase_data = get_database_data(slb_row, 'SeaLifeBase') if slb_row is not None else None
        fishbase_data = get_database_data(fb_row, 'FishBase') if fb_row is not None else None
        worms_info = worms_data.get(species_name, None)
        
        # Get existing data or create new
        current_data = species_data.get(species_name, {})
        
        # Organize data into new structure
        species_info = {
            'taxonomy': clean_dict({
                'Kingdom': row.get('kingdom'),
                'Phylum': row.get('phylum'),
                'Class': row.get('class'),
                'Order': row.get('order'),
                'Family': row.get('family'),
                'Genus': row.get('genus')
            }),
            'ecology': {
                'SeaLifeBase': clean_dict({
                    'habitat': {
                        'Fresh': sealifebase_data.get('Fresh') if sealifebase_data else None,
                        'Brack': sealifebase_data.get('Brack') if sealifebase_data else None,
                        'Saltwater': sealifebase_data.get('Saltwater') if sealifebase_data else None,
                        'Land': sealifebase_data.get('Land') if sealifebase_data else None,
                        'DemersPelag': sealifebase_data.get('DemersPelag') if sealifebase_data else None
                    },
                    'depth': {
                        'DepthRangeShallow': sealifebase_data.get('DepthRangeShallow') if sealifebase_data else None,
                        'DepthRangeDeep': sealifebase_data.get('DepthRangeDeep') if sealifebase_data else None
                    },
                    'characteristics': {
                        'Length': sealifebase_data.get('Length') if sealifebase_data else None,
                        'LTypeMaxM': sealifebase_data.get('LTypeMaxM') if sealifebase_data else None,
                        'Importance': sealifebase_data.get('Importance') if sealifebase_data else None,
                        'Comments': sealifebase_data.get('Comments') if sealifebase_data else None
                    }
                }) if sealifebase_data else {},
                'FishBase': clean_dict({
                    'habitat': {},
                    'depth': {},
                    'characteristics': {}
                }) if fishbase_data else {},
                'WoRMS': clean_dict(worms_info) if worms_info else {}
            },
            'diet': current_data.get('diet', {
                'SeaLifeBase': [],
                'FishBase': [],
                'GLOBI': {'raw_data': None}
            })
        }
        
        if species_info:
            species_data[species_name] = convert_int32(species_info)
            processed += 1
            
            # Save after each species is processed
            save_json_with_lock(species_data, output_file)
        
        progress_bar.set_description(f"Processing species data ({processed}/{total_species}, {skipped} skipped)")
        progress_bar.update(1)
    
    progress_bar.close()
    logging.info(f"All species data saved to {output_file}")

def main(species_list_file, output_dir='outputs'):
    species_df = load_species_list(species_list_file)
    
    # Load only necessary database data
    sealifebase_df, fishbase_df = load_database_data(species_df)
    
    # Load diet data
    sealifebase_fooditems_df = load_sealifebase_fooditems_data()
    fishbase_fooditems_df = load_fishbase_fooditems_data()
    
    species_data_file = os.path.join(output_dir, '02_species_data.json')
    print(species_data_file)
    
    # Get species info first
    _, _, species_data = get_species_info(
        species_df, sealifebase_df, fishbase_df, sealifebase_fooditems_df, fishbase_fooditems_df, species_data_file
    )
    
    # Get WoRMS data
    species_names = species_df['scientificName'].tolist()
    worms_data = {}  # Disabled for now: worms_data = get_worms_data(species_names)
    
    # Pass the database DataFrames directly
    save_species_data(species_df, sealifebase_df, fishbase_df, worms_data, species_data, species_data_file)
    logging.info(f"Species data saved to {species_data_file}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python 02_download_data.py <species_list_file> [output_dir]")
        sys.exit(1)
    
    output_dir = sys.argv[2] if len(sys.argv) > 2 else 'outputs'
    main(sys.argv[1], output_dir)
