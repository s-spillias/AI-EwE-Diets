import os
import sys
import logging
import json
from group_species_utils import (
    load_species_data, load_reference_groups, preprocess_data, create_hierarchical_json,
    assign_groups, save_assignments, load_assignments, write_json_to_file, read_research_focus,
    load_ai_config
)
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# ANSI escape codes for colors
GREEN = '\033[92m'
RED = '\033[91m'
RESET = '\033[0m'

def print_green(text):
    print(f"{GREEN}{text}{RESET}")

def print_red(text):
    print(f"{RED}{text}{RESET}")

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Get the absolute path of the EwE directory
EWE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def load_processed_taxa(file_path):
    try:
        with open(file_path, 'r') as f:
            assignments = json.load(f)
        processed_taxa = set()
        for group in assignments.values():
            processed_taxa.update(group.keys())
        return processed_taxa
    except FileNotFoundError:
        return set()

@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=4, max=60), retry=retry_if_exception_type(Exception))
def retry_assign_groups(taxa, level, reference_group_dict, is_leaf_level, research_focus=None, ai_model='claude'):
    return assign_groups(taxa, level, reference_group_dict, is_leaf_level, research_focus, ai_model)

def write_grouping_report(report_file, assignments):
    with open(report_file, 'a') as f:
        for taxon, functional_group in assignments.items():
            if functional_group != 'RESOLVE':
                f.write(f"Functional Group: {functional_group}\n")
                f.write(f"      Taxon: {taxon}\n\n")

def assign_groups_iteratively(hierarchical_json, reference_group_dict, assignments_file, extra_groups_file, output_dir, ai_model, force_grouping):
    assignments = load_assignments(assignments_file)
    extra_groups = load_assignments(extra_groups_file) if os.path.exists(extra_groups_file) else {}
    processed_taxa = load_processed_taxa(assignments_file)
    research_focus = read_research_focus(output_dir)
    report_file = os.path.join(output_dir, '03_grouping_report.txt')
    
    # Save reference groups before starting assignment
    grouping_file = os.path.join(output_dir, '03_grouping.json')
    try:
        with open(grouping_file, 'w') as f:
            json.dump(reference_group_dict, f, indent=2)
        logging.info(f"Saved reference groups to {grouping_file}")
    except Exception as e:
        logging.error(f"Error saving reference groups: {e}")
    
    # Initialize the report file
    with open(report_file, 'w') as f:
        f.write("High-level Grouping Decisions Report\n")
        f.write("====================================\n\n")
    
    def process_level(level, path, reference_group_dict, is_leaf_level=False):
        taxa = [key for key in level.keys() if key not in ['specCode', 'ecology'] and key not in processed_taxa]
        if taxa:
            logging.info(f"Processing {len(taxa)} taxa at level {len(path)}")
            try:
                group_assignments = retry_assign_groups(taxa, len(path), reference_group_dict, is_leaf_level, research_focus, ai_model)
                processed_taxa.update(taxa)
                
                # Write non-RESOLVE assignments to the report file
                write_grouping_report(report_file, group_assignments)
                
                assigned_count = 0
                extra_assigned_count = 0
                for taxon, assignment in group_assignments.items():
                    if assignment != 'RESOLVE':
                        if assignment in reference_group_dict:
                            if assignment not in assignments:
                                assignments[assignment] = {}
                            assignments[assignment][taxon] = level[taxon]
                            assigned_count += 1
                        else:
                            if not force_grouping:
                                reference_group_dict[assignment] = f"AI-generated group for {taxon}"
                                if assignment not in assignments:
                                    assignments[assignment] = {}
                                assignments[assignment][taxon] = level[taxon]
                                assigned_count += 1
                                logging.info(f"Added new group '{assignment}' to reference groups.")
                            else:
                                if assignment not in extra_groups:
                                    extra_groups[assignment] = {}
                                extra_groups[assignment][taxon] = level[taxon]
                                extra_assigned_count += 1
                    else:
                        # If RESOLVE, continue processing the subtree
                        process_level(level[taxon], path + [str(taxon)], reference_group_dict, is_leaf_level)
                
                logging.info(f"Assigned {assigned_count} out of {len(taxa)} taxa at level {len(path)} to regular groups")
                if extra_assigned_count > 0:
                    logging.info(f"Assigned {extra_assigned_count} out of {len(taxa)} taxa at level {len(path)} to extra groups")
            except Exception as e:
                logging.error(f"Error assigning groups after multiple retries: {e}")
            
            # Save assignments and extra groups after processing each level
            save_assignments(assignments, assignments_file)
            save_assignments(extra_groups, extra_groups_file)
        return level

    taxonomic_ranks = ['Kingdom', 'Phylum', 'Class', 'Order', 'Family', 'Genus', 'Species']
    
    for rank_number, rank in enumerate(taxonomic_ranks):
        logging.info(f"Processing rank: {rank} ({rank_number + 1} of {len(taxonomic_ranks)})")
        is_leaf_level = rank == taxonomic_ranks[-1]
        hierarchical_json = process_level(hierarchical_json, [], reference_group_dict, is_leaf_level)
    
    # Add Detritus as a functional group
    if "Detritus" not in assignments:
        assignments["Detritus"] = {
            "Detritus": {
                "specCode": "DET",
                "ecology": {
                    "description": "Non-living organic matter that serves as a food source and represents the end point of the food web"
                }
            }
        }
        logging.info("Added Detritus to functional groups")
    
    return hierarchical_json, assignments, extra_groups

def main(species_data_file, output_file_hierarchy, output_file_assignments, output_file_extra_groups, output_dir, json_file_path):
    try:
        logging.info("Loading AI configuration...")
        ai_config = load_ai_config(output_dir)
        ai_model = ai_config.get('groupSpeciesAI', 'gemini')
        grouping_template = ai_config.get('groupingTemplate', {'type': 'default', 'path': '03_grouping_template.json'})
        force_grouping = ai_config.get('forceGrouping', False)
        logging.info(f"Using AI model: {ai_model} for group species task")
        logging.info(f"Using grouping template: {grouping_template['type']} from {grouping_template['path']}")
        logging.info(f"Force grouping: {force_grouping}")

        logging.info(f"Loading species data from {species_data_file}...")
        species_data = load_species_data(species_data_file)
        logging.info(f"Loaded {len(species_data)} species")
        
        logging.info("Loading reference groups...")
        
        # Load reference groups using the updated function from group_species_utils
        reference_groups, reference_group_dict = load_reference_groups(output_dir, json_file_path)
        
        logging.info(f"Loaded {len(reference_groups)} reference groups")
        
        if not reference_groups:
            logging.error("No groups found in reference data. Cannot proceed without reference groups.")
            sys.exit(1)
        
        logging.info("Preprocessing data...")
        processed_data = preprocess_data(species_data)
        logging.info(f"Preprocessed {len(processed_data)} species")
        
        logging.info("Creating initial hierarchical JSON...")
        hierarchical_json = create_hierarchical_json(processed_data)
        logging.info(f"Created hierarchical JSON with {len(hierarchical_json)} top-level keys")
        
        logging.info("Assigning groups iteratively...")
        grouped_hierarchical_json, assignments, extra_groups = assign_groups_iteratively(
            hierarchical_json, reference_group_dict, output_file_assignments, output_file_extra_groups,
            output_dir, ai_model, force_grouping
        )
        
        logging.info("Exporting results...")
        write_json_to_file(grouped_hierarchical_json, output_file_hierarchy)
        save_assignments(assignments, output_file_assignments)
        save_assignments(extra_groups, output_file_extra_groups)
        
        logging.info(f"Script completed successfully. Assigned {len(assignments)} groups.")
        logging.info(f"Extra AI groups saved: {len(extra_groups)}")
        print_green("Species grouping completed successfully.")
    except Exception as e:
        logging.error(f"An error occurred during script execution: {e}", exc_info=True)
        print_red(f"Error: An unexpected error occurred. Please check the log for details.")
        raise

if __name__ == "__main__":
    if len(sys.argv) < 3:
        logging.error("Usage: python 03_group_species.py [json_file_path] [output_dir]")
        sys.exit(1)
    
    json_file_path = sys.argv[1]
    output_dir = sys.argv[2]
    species_data_file = os.path.join(output_dir, "02_species_data.json")
    output_file_hierarchy = os.path.join(output_dir, "03_grouped_species_hierarchy.json")
    output_file_assignments = os.path.join(output_dir, "03_grouped_species_assignments.json")
    output_file_extra_groups = os.path.join(output_dir, "03_extra_ai_groups.json")
    
    if not os.path.exists(species_data_file):
        print_red(f"Error: Species data file not found at {species_data_file}")
        print_red("Please ensure that the previous step (02_download_data.py) has been run successfully.")
        sys.exit(1)
    
    main(species_data_file, output_file_hierarchy, output_file_assignments, output_file_extra_groups, output_dir, json_file_path)
