import os
import json
import logging
from diet_data_utils import load_globi_data, parse_globi_data, create_species_group_lookup

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_with_abtest_data():
    """Test diet_data_utils functions using actual data from abtest model"""
    # Get the absolute path of the EwE directory
    EWE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    
    # Load the required input files
    species_data_json = os.path.join(EWE_DIR, "MODELS/abtest/02_species_data.json")
    grouped_species_json = os.path.join(EWE_DIR, "MODELS/abtest/03_grouped_species_assignments.json")
    output_file = os.path.join(EWE_DIR, "MODELS/abtest/test_globi_interactions.json")
    
    # Delete existing output file if it exists
    if os.path.exists(output_file):
        os.remove(output_file)
    
    print("\nTesting with abtest model data...")
    
    # Test loading species data
    print("\nLoading species data...")
    with open(species_data_json, 'r', encoding='utf-8') as f:
        species_data = json.load(f)
    print(f"Loaded data for {len(species_data)} species")
    
    # Test loading grouped species data
    print("\nLoading grouped species data...")
    with open(grouped_species_json, 'r', encoding='utf-8') as f:
        grouped_species_data = json.load(f)
    print(f"Loaded data for {len(grouped_species_data)} groups")
    
    # Test load_globi_data function
    print("\nTesting load_globi_data function...")
    globi_data = load_globi_data(species_data_json)
    print(f"Found GLOBI interactions for {len(globi_data)} species")
    
    # Print sample of GLOBI data
    if globi_data:
        print("\nSample of GLOBI interactions:")
        sample_species = next(iter(globi_data))
        print(f"\nSpecies: {sample_species}")
        print("Interactions:")
        for interaction in globi_data[sample_species]['interactions'][:3]:  # Show first 3 interactions
            print(f"  {interaction['interaction_type']} -> {interaction['target_species']}")
    
    # Test parse_globi_data function
    print("\nTesting parse_globi_data function...")
    interaction_data = parse_globi_data(globi_data, grouped_species_data, output_file)
    
    # Print summary of interaction data
    print("\nInteraction data summary:")
    for group in interaction_data:
        prey_count = len(interaction_data[group]['preys_on'])
        predator_count = len(interaction_data[group]['is_preyed_on_by'])
        total_prey = interaction_data[group]['total_prey_interactions']
        total_pred = interaction_data[group]['total_predator_interactions']
        print(f"\nGroup: {group}")
        print(f"  Preys on {prey_count} groups (total interactions: {total_prey})")
        print(f"  Preyed on by {predator_count} groups (total interactions: {total_pred})")
        
        if prey_count > 0:
            print("\n  Sample prey interactions:")
            for prey, data in list(interaction_data[group]['preys_on'].items())[:3]:  # Show first 3
                print(f"    -> {prey}: {data['count']} interactions ({data['proportion']*100:.1f}%)")

if __name__ == "__main__":
    test_with_abtest_data()
