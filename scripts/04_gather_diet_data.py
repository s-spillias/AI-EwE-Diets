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
    clean_group_name, extract_species_names, parse_ai_response, format_diet_description,
    create_species_group_lookup, find_functional_group_from_path, find_functional_group, normalize_category
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

def get_representative_species(species_list_df, group_data):
    """Get representative species from the most common genera in the group"""
    try:
        # Extract species names from nested structure
        group_species_names = list(set(extract_species_from_nested(group_data)))
        
        if not group_species_names:
            return []
        
        # Get genus counts from species_list_df
        genus_counts = {}
        species_by_genus = {}
        for species in group_species_names:
            species_info = species_list_df[species_list_df['scientificName'] == species]
            if len(species_info) > 0:
                genus = species_info['genus'].iloc[0]
                if genus and not pd.isna(genus):  # Check if genus is valid
                    if genus not in genus_counts:
                        genus_counts[genus] = 0
                        species_by_genus[genus] = []
                    genus_counts[genus] += 1
                    species_by_genus[genus].append(species)
        
        # Get top 3 genera by number of species
        top_genera = sorted(genus_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        
        # Get one example species from each top genus
        representative_species = []
        for genus, count in top_genera:
            if species_by_genus[genus]:
                representative_species.append(f"{species_by_genus[genus][0]} (1 of {count} species in genus {genus})")
        
        return representative_species
    except Exception as e:
        logging.warning(f"Error getting representative species: {str(e)}")
        return []

def remove_empty_fields(data):
    if isinstance(data, dict):
        return {k: remove_empty_fields(v) for k, v in data.items() if v not in (None, "", {}, [])}
    elif isinstance(data, list):
        return [remove_empty_fields(item) for item in data if item not in (None, "", {}, [])]
    else:
        return data

def compress_food_categories(species_data, species_group_lookup=None):
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
        
        # Process GLOBI data
        if 'globi_data' in data:
            # Add prey items with their counts
            for prey, count in data['globi_data'].get('prey_items', {}).items():
                # If we have a species_group_lookup function, use it to get the functional group
                if species_group_lookup is not None:
                    prey_group = species_group_lookup(prey)
                    if prey_group is None:
                        prey_group = clean_group_name(prey)
                    food_categories[f"GLOBI > {prey_group}"] = count
                else:
                    food_categories[f"GLOBI > {prey}"] = count
            
            # Add predator items with their counts (for reference)
            for predator, count in data['globi_data'].get('predator_items', {}).items():
                # If we have a species_group_lookup function, use it to get the functional group
                if species_group_lookup is not None:
                    predator_group = species_group_lookup(predator)
                    if predator_group is None:
                        predator_group = clean_group_name(predator)
                    food_categories[f"GLOBI_predators > {predator_group}"] = count
                else:
                    food_categories[f"GLOBI_predators > {predator}"] = count
    
    return dict(food_categories)

def gather_all_diet_data(directory, grouped_species_data, species_data, output_file, output_dir):
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

    # Initialize or load intermediate group diet data
    group_diet_file = os.path.join(EWE_DIR, output_dir, '04a_group_diet_data.json')
    group_diet_data = {}
    if os.path.exists(group_diet_file):
        group_diet_data = load_json_with_lock(group_diet_file) or {}
    group_desc_file = os.path.join(os.path.dirname(output_file), '03_grouping.json')
    group_descriptions = {}
    if os.path.exists(group_desc_file):
        group_descriptions = load_json_with_lock(group_desc_file) or {}


    # Load species list for occurrence counts
    species_list_file = os.path.join(os.path.dirname(output_file), '01_species_list.csv')
    species_list_df = pd.read_csv(species_list_file) if os.path.exists(species_list_file) else pd.DataFrame()
    
    unique_groups = list(grouped_species_data.keys())
    logging.info(f"Found {len(unique_groups)} unique groups to process.")
    
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
            'top_species': get_representative_species(species_list_df, grouped_species_data[group])
        }
    
    # Add Detritus to available groups
    available_groups['Detritus'] = {
        'name': 'Detritus',
        'description': 'Dead organic matter and associated bacteria, crucial in nutrient cycling',
        'top_species': []
    }
    
    for group in tqdm(unique_groups, desc="Processing groups"):
        clean_group_str = clean_group_name(group)
        print(f"Processing {clean_group_str}..............................")
        if clean_group_str not in all_diet_data:
            all_diet_data[clean_group_str] = {
                'diet_proportions': {},
                'source_data': {
                    'globi': {},
                    'rag': [],
                    'fishbase': {},
                    'sealifebase': {}
                }
            }
        
        species_in_group = extract_species_names(json.dumps(grouped_species_data[group]))
        top_species = available_groups[clean_group_str]['top_species']
        species_examples = "; ".join(top_species) if top_species else clean_group_str
        rag_query = f"What do {clean_group_str} (for example: {species_examples}) eat?"
        try:
            rag_results, _ = rag_search(rag_query, directory)
            all_diet_data[clean_group_str]['source_data']['rag'] = rag_results
        except Exception as e:
            logging.error(f"Error during RAG search for group {clean_group_str}: {str(e)}")
            all_diet_data[clean_group_str]['source_data']['rag'] = ["No RAG search results available due to an error."]
        
        # Initialize group in intermediate data if not exists
        if clean_group_str not in group_diet_data:
            group_diet_data[clean_group_str] = {
                "species_data": {},
                "group_summary": {
                    "rag_results": rag_results,
                    "total_prey_interactions": 0,
                    "total_predator_interactions": 0,
                    "prey_items": {},
                    "predator_items": {}
                }
            }
        
        # Initialize group-level database data
        fishbase_data = {}
        sealifebase_data = {}
        
        for species in tqdm(species_in_group, desc=f"Processing species in {clean_group_str}"):
            print(species)
            # Initialize diet data structure
            species_diet_data = {
                "sealifebase_data": [],
                "fishbase_data": [],
                "globi_data": {
                    "prey_items": {},  # Will store counts of prey items
                    "predator_items": {}  # Will store counts of predators
                }
            }
            if species in species_data and 'diet' in species_data[species]:
                print("SPECIES DATA...........")
                diet_data = species_data[species]['diet']
                print(diet_data)
                # Handle SeaLifeBase and FishBase data
                if 'SeaLifeBase' in diet_data:
                    print("SeaLifeBase...........")
                    species_diet_data["sealifebase_data"] = diet_data['SeaLifeBase']
                    sealifebase_data[species] = diet_data['SeaLifeBase']
                if 'FishBase' in diet_data:
                    print("FishBase..........")
                    species_diet_data["fishbase_data"] = diet_data['FishBase']
                    fishbase_data[species] = diet_data['FishBase']
                
                # Process GLOBI data
                if 'GLOBI' in diet_data and 'interactions' in diet_data['GLOBI']:
                    print("GLOBI..........")
                    interactions = diet_data['GLOBI']['interactions']
                    for interaction in interactions:
                        print(species)
                        print(interaction)
                        # Check interaction type
                        interaction_type = interaction.get('interactionTypeName', '').lower()
                        
                        # Print full interaction details for debugging
                        logging.debug(f"\nSpecies: {species}")
                        logging.debug(f"Interaction type: {interaction_type}")
                        logging.debug(f"Source: {interaction.get('sourceTaxonName')} ({interaction.get('sourceTaxonPath', '')})")
                        logging.debug(f"Target: {interaction.get('targetTaxonName')} ({interaction.get('targetTaxonPath', '')})")
                        
                        # Handle both predator and prey interactions
                        is_predator = interaction_type in ['eats', 'preyson']
                        is_prey = interaction_type in ['eatenby', 'preyeduponby']
                        
                        if is_predator or is_prey:
                            source_species = interaction.get('sourceTaxonName')
                            source_path = interaction.get('sourceTaxonPath')
                            target_species = interaction.get('targetTaxonName')
                            target_path = interaction.get('targetTaxonPath')
                            
                            def find_group_from_interaction(species_name, taxon_path, is_normalized=False):
                                """Helper function to find functional group using consistent lookup chain"""
                                try:
                                    if not species_name or species_name == 'no:match':
                                        return None
                                        
                                    # First normalize if not already normalized
                                    if not is_normalized:
                                        species_name = normalize_category(species_name)
                                    
                                    # Try lookup chain:
                                    # 1. Direct functional group lookup
                                    group = find_functional_group(species_name, grouped_species_data)
                                    if group:
                                        return group
                                        
                                    # 2. Path-based lookup
                                    if taxon_path:
                                        group, _ = find_functional_group_from_path(taxon_path, grouped_species_data)
                                        if group:
                                            return group
                                    
                                    # 3. Fallback to cleaned species name
                                    return clean_group_name(species_name)
                                    
                                except Exception as e:
                                    logging.warning(f"Error in group lookup chain: {str(e)}")
                                    return None
                            
                            if is_predator and target_species and target_species != 'no:match':
                                # This species is eating something
                                normalized_target = normalize_category(target_species)
                                prey_group = find_group_from_interaction(normalized_target, target_path, is_normalized=True)
                                
                                # Update prey counts
                                if prey_group:
                                    species_diet_data["globi_data"]["prey_items"][prey_group] = \
                                        species_diet_data["globi_data"]["prey_items"].get(prey_group, 0) + 1
                            
                            elif is_prey and source_species and source_species != 'no:match':
                                # Something is eating this species
                                normalized_source = normalize_category(source_species)
                                predator_group = find_group_from_interaction(normalized_source, source_path, is_normalized=True)
                                
                                # Update predator counts
                                if predator_group:
                                    species_diet_data["globi_data"]["predator_items"][predator_group] = \
                                        species_diet_data["globi_data"]["predator_items"].get(predator_group, 0) + 1
 
            
            # Add species diet data to group data structure
            if clean_group_str not in group_diet_data:
                group_diet_data[clean_group_str] = {
                    "species_data": {},
                    "group_summary": {
                        "total_prey_interactions": 0,
                        "total_predator_interactions": 0,
                        "prey_items": {},
                        "predator_items": {},
                        "rag_results": all_diet_data[clean_group_str]['source_data'].get('rag', [])
                    }
                }
            
            # Store species data
            group_diet_data[clean_group_str]["species_data"][species] = species_diet_data
            stats['processed'] += 1
            
        # Process group-level summaries
        collapsed_species_data = remove_empty_fields(group_diet_data[clean_group_str]["species_data"])
        compressed_food_categories = compress_food_categories(collapsed_species_data, species_group_lookup)
        
        # Aggregate GLOBI data at group level
        total_prey_interactions = 0
        total_predator_interactions = 0
        group_prey_items = {}
        group_predator_items = {}
        
        # Sum up all interactions from species level
        for species_data_points in collapsed_species_data.values():
            if 'globi_data' in species_data_points:
                # Sum prey interactions
                for prey, count in species_data_points['globi_data'].get('prey_items', {}).items():
                    group_prey_items[prey] = group_prey_items.get(prey, 0) + count
                    total_prey_interactions += count
                
                # Sum predator interactions
                for predator, count in species_data_points['globi_data'].get('predator_items', {}).items():
                    group_predator_items[predator] = group_predator_items.get(predator, 0) + count
                    total_predator_interactions += count
        
        # Update group summary
        group_diet_data[clean_group_str]["group_summary"].update({
            "total_prey_interactions": total_prey_interactions,
            "total_predator_interactions": total_predator_interactions,
            "prey_items": group_prey_items,
            "predator_items": group_predator_items,
            "compressed_food_categories": compressed_food_categories
        })

        # Prepare the prompt for ask_ai with the processed data
        combined_data = {
            "rag_results": group_diet_data[clean_group_str]["group_summary"]["rag_results"],
            "compressed_food_categories": compressed_food_categories,
            "globi_data": {
                "prey_items": group_diet_data[clean_group_str]["group_summary"]["prey_items"],
                "predator_items": group_diet_data[clean_group_str]["group_summary"]["predator_items"],
                "total_prey_interactions": group_diet_data[clean_group_str]["group_summary"]["total_prey_interactions"],
                "total_predator_interactions": group_diet_data[clean_group_str]["group_summary"]["total_predator_interactions"]
            }
        }
        combined_data_json = json.dumps(combined_data, indent=2)
        
        # Save intermediate group diet data
        save_json_with_lock(group_diet_data, group_diet_file)
        
        ai_prompt = f"""Based on the following information about the diet composition of the group '{clean_group_str}', 
        provide a summary of their diet. Include the prey items and their estimated proportions in the diet. 
        
        Available functional groups and their details:
        {json.dumps(available_groups, indent=2)}

        Here is the diet data for {clean_group_str}:

        {remove_empty_fields(group_diet_data[clean_group_str])}

        Format your response as a list, with each item on a new line in the following format:
        Prey Item: Percentage

        For example:
        Small fish: 40%
        Zooplankton: 30%
        Algae: 20%
        Detritus: 10%

        Important Guidelines:
        1. Assign reasonable proportions based on the available information - if data is limited, use your best ecological judgement to make estimates.
        2. Ensure that all percentages add up to approximately 100%.
        3. Consider that some species may feed on juvenile or larval forms of other species, these proportions should only consider adult forms.
        """

        try:
            # Get AI response and parse it
            ai_response = ask_ai(ai_prompt, 'claude')
            parsed_diet_proportions = parse_ai_response(ai_response)
            
            # Store the parsed diet proportions in all_diet_data
            all_diet_data[clean_group_str]['diet_proportions'] = parsed_diet_proportions
            
        except Exception as e:
            logging.error(f"Error processing diet data for group {clean_group_str}: {str(e)}")
            # Save what we have so far
            all_diet_data[clean_group_str]['source_data']['error'] = str(e)
            save_json_with_lock(all_diet_data, output_file)
            continue
        
        try:
            # Debug logging
            logging.info(f"Saving diet data for group: {clean_group_str}")
            logging.info(f"Available groups in group_diet_data: {list(group_diet_data.keys())}")
            
            # Ensure group exists in both dictionaries
            if clean_group_str not in group_diet_data:
                logging.error(f"Group {clean_group_str} not found in group_diet_data")
                group_diet_data[clean_group_str] = {
                    "group_summary": {
                        "total_prey_interactions": 0,
                        "total_predator_interactions": 0,
                        "prey_items": {},
                        "predator_items": {}
                    }
                }
            
            # Update final output structure with source data
            all_diet_data[clean_group_str]['source_data'].update({
                'globi': group_diet_data[clean_group_str]["group_summary"],
                'rag': rag_results,
                'fishbase': fishbase_data,
                'sealifebase': sealifebase_data
            })
            
            logging.info(f"Successfully saved diet data for group: {clean_group_str}")
            
        except Exception as e:
            logging.error(f"Error saving diet data for group {clean_group_str}")
            logging.error(f"Error details: {str(e)}")
            logging.error(f"Group diet data structure: {json.dumps(group_diet_data.get(clean_group_str, {}), indent=2)}")
            all_diet_data[clean_group_str]['source_data']['error'] = str(e)

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
               
        try:
            diet_data = gather_all_diet_data(directory, grouped_species_data, species_data, output_file, output_dir)

            if diet_data is not None:
                readable_output = os.path.join(EWE_DIR, output_dir, '04e_diet_summaries_readable.txt')
                with open(readable_output, 'w', encoding='utf-8') as f:
                    for group, data in diet_data.items():
                        if 'diet_proportions' in data and data['diet_proportions']:
                            f.write(f"{group}:\n")
                            f.write(format_diet_description(data['diet_proportions']) + "\n\n")
        except KeyboardInterrupt:
            logging.warning("\nProcess interrupted by user. Partial results have been saved.")
        except Exception as e:
            logging.error(f"An error occurred: {str(e)}")
    
    logging.info("Diet data gathering process completed.")
