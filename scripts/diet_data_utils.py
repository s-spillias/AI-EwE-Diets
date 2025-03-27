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

# Lookup table for malformed category names
CATEGORY_LOOKUP = {
    # Original mappings
    "unspecified detritus": "detritus",
    "unspecified organic matter": "detritus",
    "unspecified organic material": "detritus",
    "unspecified debris": "detritus",
    "unspecified sediment": "sediment",
    "unspecified plankton": "plankton",
    "unspecified algae": "algae",
    "unspecified plant material": "plants",
    "unspecified animal material": "animals",
    "unspecified crustaceans": "crustaceans",
    "unspecified hydroids": "hydroids",
    "unspecified zooplankton": "zooplankton",
    "unspecified small plank invertebrates": "small planktonic invertebrates"
}

def normalize_category(category_name):
    """
    Normalize category names by checking against known malformed categories.
    If no exact match is found but the name starts with 'unspecified',
    attempt to extract the meaningful part.
    
    Args:
        category_name (str): The category name to normalize
        
    Returns:
        str: The normalized category name
    """
    if pd.isna(category_name):
        return category_name
    
    category_name = str(category_name).lower().strip()
    
    # First try exact match in lookup table
    if category_name in CATEGORY_LOOKUP:
        return CATEGORY_LOOKUP[category_name]
    
    # If no match but starts with 'unspecified', try to extract meaningful part
    if category_name.startswith('unspecified'):
        # Remove 'unspecified' and clean up
        meaningful_part = category_name.replace('unspecified', '').strip()
        if meaningful_part:
            # Log the unhandled case for future reference
            logging.info(f"Unhandled 'unspecified' category normalized: '{category_name}' -> '{meaningful_part}'")
            return meaningful_part
    
    # If all else fails, return original
    return category_name

def clean_group_name(group_name):
    return re.sub(r'\s*\([^)]*\)', '', group_name).strip()

def create_species_group_lookup(grouped_species_data):
    """
    Create a lookup function that maps species to their functional groups based on the taxonomic structure.
    The grouped_species_data structure is expected to be:
    {
        "functional_group": {
            "taxonomy_level1": {
                "taxonomy_level2": {
                    ...,
                    "species_name": {
                        "specCode": ...,
                        ...
                    }
                }
            }
        }
    }
    """
    # Create a mapping of species to their functional groups
    species_to_group = {}
    for functional_group, taxonomy_tree in grouped_species_data.items():
        def traverse_tree(tree, group):
            if isinstance(tree, dict):
                for key, value in tree.items():
                    if ' ' in key:  # This is a species name
                        species_to_group[key.lower()] = group
                    traverse_tree(value, group)
        traverse_tree(taxonomy_tree, functional_group)

    # Create a mapping of genera to functional groups
    genus_to_group = {}
    for species, group in species_to_group.items():
        try:
            genus = species.split()[0]  # Get first word (genus)
            if genus not in genus_to_group:
                genus_to_group[genus] = group
            elif genus_to_group[genus] != group:
                logging.warning(f"Genus {genus} found in multiple groups: {genus_to_group[genus]} and {group}")
        except:
            logging.warning(f"Could not extract genus from {species}")

    def get_group(species_name):
        if not species_name:
            return None
            
        species_lower = species_name.lower()
        
        # First try exact species match
        if species_lower in species_to_group:
            return species_to_group[species_lower]
            
        # Then try genus match
        try:
            genus = species_lower.split()[0]
            if genus in genus_to_group:
                return genus_to_group[genus]
        except:
            logging.warning(f"Could not extract genus from {species_name}")
        
        return None

    return get_group

def find_functional_group_from_path(taxon_path, grouped_species_data):
    """
    Find the functional group by searching through taxonomic levels from most specific to least specific.
    
    Args:
        taxon_path: String of taxonomic levels separated by ' | '
        grouped_species_data: Dictionary of functional groups and their taxonomic hierarchies
    
    Returns:
        Tuple of (functional_group, matched_taxon) if found, (None, None) otherwise
    """
    if not taxon_path or pd.isna(taxon_path):
        return None, None
        
    try:
        # Split and clean the taxonomic path
        taxa = [t.strip().lower() for t in str(taxon_path).split('|')]
        # Remove any empty strings and 'root'
        taxa = [t for t in taxa if t and t != 'root']
    except Exception as e:
        logging.warning(f"Error processing taxonomic path: {str(e)}")
        return None, None
    
    # Search from most specific (end) to least specific (start)
    for taxon in reversed(taxa):
        for func_group, taxonomy_tree in grouped_species_data.items():
            def traverse_tree(tree):
                if isinstance(tree, dict):
                    # Skip species-level entries
                    if 'specCode' in tree:
                        return False
                        
                    for key, value in tree.items():
                        # Check for exact match (case-insensitive)
                        if key.lower() == taxon:
                            return True
                            
                        # Recursively search deeper
                        if traverse_tree(value):
                            return True
                return False
            
            if traverse_tree(taxonomy_tree):
                return func_group, taxon
                
    return None, None

def find_functional_group(taxon_name, grouped_species_data):
    """
    Find the functional group for a taxon by traversing the taxonomic hierarchy.
    Returns the functional group name if found, None otherwise.
    """
    # First try direct match with the taxon name
    for func_group, taxonomy_tree in grouped_species_data.items():
        def traverse_tree(tree):
            if isinstance(tree, dict):
                # Skip species-level entries
                if 'specCode' in tree:
                    return False
                    
                for key, value in tree.items():
                    # Check for exact match (case-insensitive)
                    if key.lower() == taxon_name.lower():
                        return True
                        
                    # Recursively search deeper
                    if traverse_tree(value):
                        return True
            return False
        
        if traverse_tree(taxonomy_tree):
            return func_group
            
    return None


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
