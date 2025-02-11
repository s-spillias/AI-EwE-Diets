import os
import json
import logging
from collections import Counter
import pandas as pd
from tqdm import tqdm
from rag_search import rag_search
from ask_AI import ask_ai
import time
from diet_data_utils import (
    clean_group_name, load_globi_data,
    parse_globi_data, extract_species_names, parse_ai_response, format_diet_description,
    create_species_group_lookup
)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Get the absolute path of the EwE directory
EWE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def extract_species_from_nested(data):
    """Recursively extract species names from nested dictionary structure"""
    species_names = []
    
    def traverse(d, parent_key=None):
        if isinstance(d, dict):
            if "specCode" in d:
                # This is a leaf node with species info
                if parent_key and parent_key != "Detritus":
                    species_names.append(parent_key)
            else:
                # Continue traversing
                for key, value in d.items():
                    traverse(value, key)
    
    traverse(data)
    return list(set(species_names))  # Remove duplicates

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
                    logging.error(f"JSON decode error in {file_path}: {str(e)}")
                    return None
                except UnicodeDecodeError as e:
                    logging.error(f"Unicode decode error in {file_path}: {str(e)}")
                    # Try with a different encoding as fallback
                    try:
                        with open(file_path, 'r', encoding='latin-1') as f2:
                            data = json.load(f2)
                            return data
                    except Exception as e2:
                        logging.error(f"Failed fallback encoding attempt: {str(e2)}")
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
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                try:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    return True
                except Exception as e:
                    logging.error(f"Error writing JSON to {file_path}: {str(e)}")
                    return False
        except IOError as e:
            retries += 1
            if retries == max_retries:
                logging.error(f"Failed to save {file_path} after {max_retries} attempts: {str(e)}")
                return False
            time.sleep(retry_delay)
    return False

def get_top_species_by_occurrence(species_list_df, group_data):
    """Get the top 3 species by occurrence count from species_list_df for a given group"""
    try:
        # Extract unique species names from nested structure
        group_species_names = list(set(extract_species_from_nested(group_data)))
        
        if not group_species_names:
            return []
        
        # Get occurrence counts from species_list_df
        species_occurrences = []
        for species in group_species_names:
            occurrence = species_list_df[species_list_df['scientificName'] == species]['occurrence_count'].iloc[0] if len(species_list_df[species_list_df['scientificName'] == species]) > 0 else 0
            species_occurrences.append((species, occurrence))
        
        # Sort by occurrence count and get top 3
        top_species = [s[0] for s in sorted(species_occurrences, key=lambda x: x[1], reverse=True)[:3]]
        
        return top_species
    except Exception as e:
        logging.warning(f"Error getting top species: {str(e)}")
        return []

def remove_empty_fields(data):
    if isinstance(data, dict):
        return {k: remove_empty_fields(v) for k, v in data.items() if v not in (None, "", {}, [])}
    elif isinstance(data, list):
        return [remove_empty_fields(item) for item in data if item not in (None, "", {}, [])]
    else:
        return data

def compress_food_categories(species_data):
    food_categories = Counter()
    for species, data in species_data.items():
        # Process SeaLifeBase and FishBase data
        for source in ['sealifebase_data', 'fishbase_data']:
            for item in data.get(source, []):
                if 'FoodCategories' in item:
                    categories = item['FoodCategories'].split(' > ')
                    for i in range(len(categories)):
                        food_categories[' > '.join(categories[:i+1])] += 1
                # If no FoodCategories, use FoodI > FoodII > FoodIII hierarchy
                elif all(k in item for k in ['FoodI', 'FoodII', 'FoodIII']):
                    categories = [item['FoodI'], item['FoodII'], item['FoodIII']]
                    categories = [c for c in categories if c and c.lower() != 'n.a./others']
                    for i in range(len(categories)):
                        food_categories[' > '.join(categories[:i+1])] += 1
    return dict(food_categories)

def gather_all_diet_data(directory, grouped_species_data, species_data, globi_data, output_file, output_dir):
    logging.info(f"Starting to gather diet data from directory: {directory}")
    
    if not os.path.exists(directory):
        logging.error(f"Error: Directory '{directory}' does not exist.")
        logging.info(f"Current working directory: {os.getcwd()}")
        logging.info("Contents of current directory:")
        for item in os.listdir():
            logging.info(f"  {'[DIR]' if os.path.isdir(item) else '[FILE]'} {item}")
        return None

    # Load existing diet data with file locking
    all_diet_data = {}
    if os.path.exists(output_file):
        all_diet_data = load_json_with_lock(output_file) or {}


    # Load or create species diet cache with file locking
    species_diet_file = os.path.join(EWE_DIR, output_dir, '04a_species_diet_cache.json')
    species_diet_cache = {}
    if os.path.exists(species_diet_file):
        species_diet_cache = load_json_with_lock(species_diet_file) or {}


    # Load or create combined diet data with file locking
    combined_diet_file = os.path.join(EWE_DIR, output_dir, '04b_raw_diet_sources.json')
    combined_diet_data = load_json_with_lock(combined_diet_file) if os.path.exists(combined_diet_file) else {}
    group_desc_file = os.path.join(os.path.dirname(output_file), '03_grouping.json')
    group_descriptions = {}
    if os.path.exists(group_desc_file):
        group_descriptions = load_json_with_lock(group_desc_file) or {}


    # Load species list for occurrence counts
    species_list_file = os.path.join(os.path.dirname(output_file), '01_species_list.csv')
    species_list_df = pd.read_csv(species_list_file) if os.path.exists(species_list_file) else pd.DataFrame()
    
    unique_groups = list(grouped_species_data.keys())
    logging.info(f"Found {len(unique_groups)} unique groups to process.")
    
    globi_output_file = os.path.join(EWE_DIR, output_dir, '04c_globi_interactions.json')
    globi_interaction_data = parse_globi_data(globi_data, grouped_species_data, globi_output_file)
    
    # Create species to group lookup
    species_group_lookup = create_species_group_lookup(grouped_species_data)
    
    # Track statistics
    stats = {'processed': 0, 'cached': 0}

    # Create enhanced available_groups object
    available_groups = {}
    for group in unique_groups:
        clean_group_name_str = clean_group_name(group)
        available_groups[clean_group_name_str] = {
            'name': group,
            'description': group_descriptions.get(group, ''),
            'top_species': get_top_species_by_occurrence(species_list_df, grouped_species_data[group])
        }
    
    # Add Detritus to available groups
    available_groups['Detritus'] = {
        'name': 'Detritus',
        'description': 'Dead organic matter and associated bacteria, crucial in nutrient cycling',
        'top_species': []
    }
    
    for group in tqdm(unique_groups, desc="Processing groups"):
        clean_group_str = clean_group_name(group)
        
        if clean_group_str not in all_diet_data:
            all_diet_data[clean_group_str] = {'raw_data': {}, 'ai_summary': [], 'completed': False}
        
        species_in_group = extract_species_names(json.dumps(grouped_species_data[group]))
        top_species = available_groups[clean_group_str]['top_species']
        species_examples = ", ".join(top_species) if top_species else clean_group_str
        rag_query = f"What do {clean_group_str} (for example: {species_examples}) eat?"
        try:
            rag_results, _ = rag_search(rag_query, directory)
            all_diet_data[clean_group_str]['raw_data']['rag_results'] = rag_results
        except Exception as e:
            logging.error(f"Error during RAG search for group {clean_group_str}: {str(e)}")
            all_diet_data[clean_group_str]['raw_data']['rag_results'] = ["No RAG search results available due to an error."]
        
        all_diet_data[clean_group_str]['raw_data']['species_data'] = {}
        
        for species in tqdm(species_in_group, desc=f"Processing species in {clean_group_str}"):
            # Use pre-collected diet data including GLOBI interactions
            species_diet_data = {
                "sealifebase_data": [],
                "fishbase_data": [],
                "globi_interactions": []
            }
            
            if species in species_data and 'diet' in species_data[species]:
                diet_data = species_data[species]['diet']
                if 'SeaLifeBase' in diet_data:
                    species_diet_data["sealifebase_data"] = diet_data['SeaLifeBase']
                if 'FishBase' in diet_data:
                    species_diet_data["fishbase_data"] = diet_data['FishBase']
                if 'GLOBI' in diet_data:
                    species_diet_data["globi_interactions"] = diet_data['GLOBI'].get('interactions', [])
 
            
            # Cache the species diet data
            species_diet_cache[species] = species_diet_data
            all_diet_data[clean_group_str]['raw_data']['species_data'][species] = species_diet_data
            stats['processed'] += 1
            
        # Save species diet cache and collapse/compress the species_data
        save_json_with_lock(species_diet_cache, species_diet_file)
        collapsed_species_data = remove_empty_fields(all_diet_data[clean_group_str]['raw_data']['species_data'])
        compressed_food_categories = compress_food_categories(collapsed_species_data)

        # Load the processed GLOBI interaction data from 04c_globi_interactions.json
        globi_interactions_file = os.path.join(EWE_DIR, output_dir, '04c_globi_interactions.json')
        if os.path.exists(globi_interactions_file):
            with open(globi_interactions_file, 'r') as f:
                processed_globi_data = json.load(f)
            group_globi_data = processed_globi_data.get(group, {})
        else:
            group_globi_data = {}
            logging.warning(f"GLOBI interactions file not found: {globi_interactions_file}")

        # Prepare the prompt for ask_ai with the processed GLOBI data
        combined_data = {
            "rag_results": all_diet_data[clean_group_str]['raw_data']['rag_results'],
            "compressed_food_categories": compressed_food_categories,
            "globi_data": {
                "prey_interactions": group_globi_data.get('preys_on', {}),
                # "predator_interactions": group_globi_data.get('is_preyed_on_by', {}),
                "total_prey_interactions": group_globi_data.get('total_prey_interactions', 0),
                # "total_predator_interactions": group_globi_data.get('total_predator_interactions', 0)
            }
        }
        combined_data_json = json.dumps(combined_data, indent=2)
        
        combined_diet_data[clean_group_str] = json.loads(combined_data_json)
        save_json_with_lock(combined_diet_data, combined_diet_file)
        
        ai_prompt = f"""Based on the following information about the diet composition of the group '{clean_group_str}', 
        provide a summary of their diet. Include the prey items and their estimated proportions in the diet. 
        
        Available functional groups and their details:
        {json.dumps(available_groups, indent=2)}

        Here is the diet data for {clean_group_str}:

        {remove_empty_fields(combined_diet_data)}

        Format your response as a list, with each item on a new line in the following format:
        Prey Item: Percentage

        For example:
        Small fish: 40%
        Zooplankton: 30%
        Algae: 20%
        Detritus: 10%

        Important Guidelines:
        1. Use the GLOBI interaction data as your primary source for diet proportions. The 'proportion' values in the GLOBI data represent the frequency of observed interactions.
        2. Adjust these proportions based on the RAG search results and compressed food categories to account for sampling bias.
        3. If a prey group appears in the GLOBI data, use its proportion as a starting point and adjust if needed based on other evidence.
        4. For groups not in the GLOBI data but mentioned in other sources, assign reasonable proportions based on the available information.
        5. Ensure that all percentages add up to approximately 100%.
        6. Consider that some species may feed on juvenile or larval forms of other species, which are often classified in different functional groups than the adults.
        7. If the GLOBI data shows very few total interactions, rely more heavily on the RAG search results and compressed food categories."""

        try:
            ai_response = ask_ai(ai_prompt, 'claude')
            group_diet_data = parse_ai_response(ai_response)
        except Exception as e:
            logging.error(f"Error processing diet data for group {clean_group_str}: {str(e)}")
            # Save what we have so far
            all_diet_data[clean_group_str]['error'] = str(e)
            all_diet_data[clean_group_str]['completed'] = False
            save_json_with_lock(all_diet_data, output_file)
            continue
        
        try:
            all_diet_data[clean_group_str]['combined_data'] = combined_data_json
            all_diet_data[clean_group_str]['ai_summary'] = group_diet_data
            all_diet_data[clean_group_str]['completed'] = True
        except Exception as e:
            logging.error(f"Error saving diet data for group {clean_group_str}: {str(e)}")
            all_diet_data[clean_group_str]['error'] = str(e)
            all_diet_data[clean_group_str]['completed'] = False

        # Save progress and print status
        save_json_with_lock(all_diet_data, output_file)
        total_species = sum(len(extract_species_names(json.dumps(grouped_species_data[g]))) for g in unique_groups)
        remaining = total_species - (stats['processed'] + stats['cached'])
        print(f"\nSpecies progress: {stats['processed']} processed, {stats['cached']} from cache, {remaining} remaining")

    print(f"\nProcessing complete: {stats['processed']} species processed, {stats['cached']} from cache")
    return all_diet_data

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python 04_gather_diet_data.py [output_dir]")
        sys.exit(1)
    
    output_dir = sys.argv[1] if len(sys.argv) > 1 else 'outputs'
    logging.info("Starting diet data gathering process...")
    
    directory = os.path.join(EWE_DIR, "SW_Atlantis_Diets_of_Functional_Groups")
    grouped_species_json = os.path.join(EWE_DIR, output_dir, "03_grouped_species_assignments.json")
    species_data_json = os.path.join(EWE_DIR, output_dir, "02_species_data.json")
    globi_data_json = os.path.join(EWE_DIR, output_dir, "02_species_data.json")
    output_file = os.path.join(EWE_DIR, output_dir, '04d_diet_summaries.json')
    
    if not os.path.exists(grouped_species_json) or not os.path.exists(species_data_json):
        logging.error(f"Error: Required input files not found.")
        logging.info(f"Current working directory: {os.getcwd()}")
        logging.info("Contents of EwE directory:")
        for item in os.listdir(EWE_DIR):
            logging.info(f"  {'[DIR]' if os.path.isdir(os.path.join(EWE_DIR, item)) else '[FILE]'} {item}")
    else:
        with open(grouped_species_json, 'r', encoding='utf-8') as f:
            grouped_species_data = json.load(f)
        
        with open(species_data_json, 'r', encoding='utf-8') as f:
            species_data = json.load(f)
        
        globi_data = load_globi_data(globi_data_json)
        
        try:
            diet_data = gather_all_diet_data(directory, grouped_species_data, species_data, globi_data, output_file, output_dir)

            if diet_data is not None:
                readable_output = os.path.join(EWE_DIR, output_dir, '04e_diet_summaries_readable.txt')
                with open(readable_output, 'w', encoding='utf-8') as f:
                    for group, data in diet_data.items():
                        if data['completed']:
                            f.write(f"{group}:\n")
                            f.write(format_diet_description(data['ai_summary']) + "\n\n")
        except KeyboardInterrupt:
            logging.warning("\nProcess interrupted by user. Partial results have been saved.")
        except Exception as e:
            logging.error(f"An error occurred: {str(e)}")
    
    logging.info("Diet data gathering process completed.")
