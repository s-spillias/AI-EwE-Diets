import os
import pandas as pd
import duckdb
import json
import re
from functools import lru_cache
from tqdm import tqdm
import logging

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

def get_food_items_for_speccode(sealifebase_df, spec_code):
    if spec_code == "Unknown" or spec_code is None:
        return pd.DataFrame()  # Return an empty DataFrame if SpecCode is unknown
    query = f"""
    SELECT 
        SpecCode, PreySpecCode, AlphaCode, 
        Foodgroup, Foodname, PreyStage, PredatorStage, FoodI, FoodII, FoodIII, 
        Commoness, CommonessII, PreyTroph, PreySeTroph
    FROM sealifebase_df
    WHERE SpecCode = {spec_code}
    AND PreyStage LIKE '%adult%'
    AND PredatorStage LIKE '%adult%'
    """
    try:
        result = duckdb.query(query).df()
        return result
    except Exception as e:
        print(f"Error querying food items for SpecCode {spec_code}: {str(e)}")
        return pd.DataFrame()

def clean_group_name(group_name):
    return re.sub(r'\s*\([^)]*\)', '', group_name).strip()

def load_globi_data(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        try:
            raw_data = json.load(f)
            # logging.info(f"Loaded raw data with {len(raw_data)} species")
            
            # Convert to expected format with 'interactions' key
            formatted_data = {}
            print(len(raw_data.items()))
            for species, info in raw_data.items():
                # logging.info(f"Processing species: {species}")                
                if 'diet' in info and 'GLOBI' in info['diet']:
                    # logging.info(f"Found GLOBI data for {species}")
                    raw_data = info['diet']['GLOBI'].get('raw_data')
                    if raw_data:
                        # logging.info(f"Found raw_data for {species}")
                        interactions = []
                        lines = [line for line in raw_data.split('\n') if line.strip()]
                        # logging.info(f"Found {len(lines)} lines of GLOBI data for {species}")
                        if len(lines) > 1:  # Skip if only header
                            header = lines[0].strip('"').split('","')
                            for line in lines[1:]:
                                parts = line.strip('"').split('","')
                                # Find the interaction type and target species in the raw line
                                if '"preysOn"' in line or '"eats"' in line:
                                    interaction_type = 'preysOn'
                                elif '"preyedUponBy"' in line or '"eatenBy"' in line:
                                    interaction_type = 'preyedUponBy'
                                else:
                                    continue  # Skip other interaction types
                                
                                # Find the interaction column index
                                interaction_idx = None
                                for i, part in enumerate(parts):
                                    if 'preysOn' in part or 'eats' in part or 'preyedUponBy' in part or 'eatenBy' in part:
                                        interaction_idx = i
                                        break
                                
                                if interaction_idx is not None and len(parts) > interaction_idx + 2:
                                    target_species = parts[interaction_idx + 2].strip()
                                    # Clean up the target species string
                                    target_species = target_species.strip('"').strip(',').strip()
                                    # Skip if target species is empty or just a number
                                    if target_species and not target_species.isdigit() and not target_species.endswith(',,,,,,,,,'):
                                        interactions.append({
                                            'source_species': species,
                                            'interaction_type': interaction_type,
                                            'target_species': target_species
                                        })
                                        # logging.info(f"Added interaction: {species} {interaction_type} {target_species}")
                        if interactions:
                            formatted_data[species] = {'interactions': interactions}
                            # logging.info(f"Added {len(interactions)} interactions for {species}")
            # logging.info(f"Total species with interactions: {len(formatted_data)}")
            if len(formatted_data) == 0:
                logging.warning("No interactions found in any species")
                # Log a sample of the raw data structure
                sample_species = list(raw_data.keys())[0] if raw_data else None
                # if sample_species:
                #     logging.warning(f"Sample species data structure: {json.dumps(raw_data[sample_species], indent=2)}")
            
            return formatted_data
        except UnicodeDecodeError:
            # Fallback to latin-1 if UTF-8 fails
            with open(file_path, 'r', encoding='latin-1') as f2:
                return load_globi_data(file_path)  # Recursive call with latin-1 encoding

def create_species_group_lookup(grouped_species_data):
    lookup = {}
    genus_group_map = {}  # Map to store genus -> group mappings
    
    # logging.info(f"Creating species lookup from {len(grouped_species_data)} groups")
    for group, species_list in grouped_species_data.items():
        # logging.info(f"Processing group: {group}")
        species_names = extract_species_names(json.dumps(species_list))  # Convert to JSON string
        # logging.info(f"Found {len(species_names)} species in group {group}: {species_names}")
        
        for species in species_names:
            # Add full species name to lookup
            species_lower = species.lower()
            lookup[species_lower] = group
            
            # Extract and store genus mapping
            genus = species_lower.split()[0]  # Get first word (genus)
            if genus not in genus_group_map:
                genus_group_map[genus] = group
            elif genus_group_map[genus] != group:
                logging.warning(f"Genus {genus} found in multiple groups: {genus_group_map[genus]} and {group}")
    
    # Create a function to get group by species or genus
    def get_group(species_name):
        species_lower = species_name.lower()
        
        # First try exact species match
        if species_lower in lookup:
            return lookup[species_lower]
            
        # Then try genus match
        try:
            genus = species_lower.split()[0]
            if genus in genus_group_map:
                return genus_group_map[genus]
        except:
            logging.warning(f"Could not extract genus from {species_name}")
        
        return None
    
    # Create final lookup that includes both species and genus matches
    final_lookup = {}
    for species in lookup:
        final_lookup[species] = get_group(species)
    
    # Log some sample mappings
    sample_size = min(5, len(final_lookup))
    if sample_size > 0:
        sample_items = list(final_lookup.items())[:sample_size]
        # logging.info(f"Sample species mappings: {dict(sample_items)}")
    
    # Log genus mappings
    # logging.info(f"Created {len(genus_group_map)} genus mappings")
    sample_genera = list(genus_group_map.items())[:5]
    # logging.info(f"Sample genus mappings: {dict(sample_genera)}")
    
    return get_group  # Return the function instead of the lookup dict

def parse_globi_data(globi_data, grouped_species_data, output_file_path):
    if os.path.exists(output_file_path):
        # logging.info(f"Loading existing interaction data from {output_file_path}")
        try:
            with open(output_file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except UnicodeDecodeError:
            # Fallback to latin-1 if UTF-8 fails
            with open(output_file_path, 'r', encoding='latin-1') as f2:
                return json.load(f2)

    # logging.info("Parsing GLOBI data...")
    species_group_lookup = create_species_group_lookup(grouped_species_data)
    interaction_data = {group: {
        'preys_on': {},
        'is_preyed_on_by': {},
        'total_prey_interactions': 0,
        'total_predator_interactions': 0
    } for group in grouped_species_data}
    
    # Convert interactions to DataFrame for efficient processing
    globi_records = []
    total_species = len(globi_data)
    for i, (species, info) in enumerate(tqdm(globi_data.items(), total=total_species, desc="Processing GLOBI data")):
        if 'interactions' in info:
            globi_records.extend(info['interactions'])
        else: 
            logging.info("No interactions...")
    
    # logging.info("Creating DataFrame from GLOBI records...")
    if not globi_records:  # If no records were found
        # logging.warning("No GLOBI interaction records found. Creating empty interaction data.")
        return interaction_data
        
    globi_df = pd.DataFrame(globi_records)
    
    # Log data statistics
    # logging.info(f"Found {len(globi_records)} total interaction records")
    unique_interactions = globi_df['interaction_type'].unique()
    # logging.info(f"Found interaction types: {unique_interactions}")
    unique_sources = globi_df['source_species'].unique()
    unique_targets = globi_df['target_species'].unique()
    # logging.info(f"Found {len(unique_sources)} unique source species and {len(unique_targets)} unique target species")
    
    logging.info("Mapping species to groups...")
    # Log the lookup table contents
    # Get unique species first to avoid duplicate lookups
    unique_source_species = globi_df['source_species'].unique()
    unique_target_species = globi_df['target_species'].unique()
    
    # Create species to group mapping dictionaries
    source_group_map = {species: species_group_lookup(species) for species in unique_source_species}
    target_group_map = {species: species_group_lookup(species) for species in unique_target_species}
    
    # Map using the dictionaries
    globi_df['source_group'] = globi_df['source_species'].map(source_group_map)
    globi_df['target_group'] = globi_df['target_species'].map(target_group_map)
    
    # Log the unique groups found
    unique_source_groups = globi_df['source_group'].dropna().unique()
    unique_target_groups = globi_df['target_group'].dropna().unique()
    all_groups = set(unique_source_groups) | set(unique_target_groups)
    # logging.info(f"Found interactions involving {len(all_groups)} groups: {sorted(all_groups)}")
    
    # Log unmapped species after mapping
    unmapped_sources = globi_df[globi_df['source_group'].isna()]['source_species'].unique()
    unmapped_targets = globi_df[globi_df['target_group'].isna()]['target_species'].unique()
    # Log mapping results
    mapped_sources = globi_df[globi_df['source_group'].notna()]['source_species'].unique()
    mapped_targets = globi_df[globi_df['target_group'].notna()]['target_species'].unique()
    # logging.info(f"Successfully mapped {len(mapped_sources)} source species and {len(mapped_targets)} target species to groups")
    
    # logging.info("Processing 'eats' and 'preysOn' interactions...")
    preys_on = globi_df[globi_df['interaction_type'].isin(['eats', 'preysOn'])]
    # logging.info(f"Found {len(preys_on)} predator-prey interactions")
    preys_on_counts = preys_on.groupby(['source_group', 'target_group']).size().reset_index(name='count')
    for _, row in tqdm(preys_on_counts.iterrows(), total=len(preys_on_counts), desc="Processing 'preys on' interactions"):
        if pd.notna(row['source_group']) and pd.notna(row['target_group']):
            interaction_data[row['source_group']]['preys_on'][row['target_group']] = {
                'count': row['count'],
                'proportion': 0.0  # Will calculate later
            }
            interaction_data[row['target_group']]['is_preyed_on_by'][row['source_group']] = {
                'count': row['count'],
                'proportion': 0.0  # Will calculate later
            }
            interaction_data[row['source_group']]['total_prey_interactions'] += row['count']
            interaction_data[row['target_group']]['total_predator_interactions'] += row['count']
    
    # logging.info("Processing 'eatenBy' and 'preyedUponBy' interactions...")
    is_preyed_on = globi_df[globi_df['interaction_type'].isin(['eatenBy', 'preyedUponBy'])]
    is_preyed_on_counts = is_preyed_on.groupby(['source_group', 'target_group']).size().reset_index(name='count')
    for _, row in tqdm(is_preyed_on_counts.iterrows(), total=len(is_preyed_on_counts), desc="Processing 'is preyed on' interactions"):
        if pd.notna(row['source_group']) and pd.notna(row['target_group']):
            interaction_data[row['source_group']]['is_preyed_on_by'][row['target_group']] = {
                'count': row['count'],
                'proportion': 0.0  # Will calculate later
            }
            interaction_data[row['target_group']]['preys_on'][row['source_group']] = {
                'count': row['count'],
                'proportion': 0.0  # Will calculate later
            }
            interaction_data[row['source_group']]['total_predator_interactions'] += row['count']
            interaction_data[row['target_group']]['total_prey_interactions'] += row['count']
    
    # Calculate proportions
    # logging.info("Calculating interaction proportions...")
    for group in interaction_data:
        # Calculate prey proportions
        total_prey = interaction_data[group]['total_prey_interactions']
        if total_prey > 0:
            for prey_group in interaction_data[group]['preys_on']:
                count = interaction_data[group]['preys_on'][prey_group]['count']
                interaction_data[group]['preys_on'][prey_group]['proportion'] = count / total_prey
        
        # Calculate predator proportions
        total_pred = interaction_data[group]['total_predator_interactions']
        if total_pred > 0:
            for pred_group in interaction_data[group]['is_preyed_on_by']:
                count = interaction_data[group]['is_preyed_on_by'][pred_group]['count']
                interaction_data[group]['is_preyed_on_by'][pred_group]['proportion'] = count / total_pred
    
    # logging.info(f"Saving interaction data to {output_file_path}")
    with open(output_file_path, 'w', encoding='utf-8') as f:
        json.dump(interaction_data, f, indent=2, ensure_ascii=False)
    
    # logging.info("GLOBI data parsing completed")
    return interaction_data

@lru_cache(maxsize=None)
def extract_species_names(group_data):
    data = json.loads(group_data)  # Convert JSON string back to Python object
    if data is None:
        return []
    
    species_names = []
    def traverse(data, parent_key=None):
        if isinstance(data, dict):
            for key, value in data.items():
                if ' ' in key:
                    species_names.append(key)
                if isinstance(value, dict):
                    if 'specCode' in value:
                        if key not in species_names:
                            species_names.append(key)
                    traverse(value, key)
                elif isinstance(value, list):
                    for item in value:
                        traverse(item, key)
        elif isinstance(data, list):
            for item in data:
                traverse(item, parent_key)
    
    traverse(data)
    species_names_filtered = [s for s in species_names if " " in s]
    return species_names_filtered

def get_spec_code(group_data, species_name):
    def traverse(data):
        if isinstance(data, dict):
            if 'specCode' in data and list(data.keys())[0] == species_name:
                return data['specCode']
            for value in data.values():
                result = traverse(value)
                if result:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = traverse(item)
                if result:
                    return result
        return None
    return traverse(group_data)

def parse_ai_response(result):
    diet_data = {}
    
    for line in result.split('\n'):
        line = line.strip()
        if ':' in line:
            prey, proportion = line.split(':', 1)
            prey = prey.strip()
            proportion = proportion.strip()
            try:
                if proportion.endswith('%'):
                    proportion = float(proportion.rstrip('%')) / 100
                else:
                    proportion = float(proportion)
                diet_data[prey] = proportion
            except ValueError:
                diet_data[prey] = proportion
    
    return diet_data

def format_diet_description(diet):
    description = []
    for prey, proportion in diet.items():
        if isinstance(proportion, float):
            description.append(f"{prey}: {proportion:.2%}")
        else:
            description.append(f"{prey}: {proportion}")
    return ", ".join(description)
