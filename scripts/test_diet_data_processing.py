import os
import json
from collections import Counter
from diet_data_utils import create_species_group_lookup, parse_globi_data, find_functional_group_from_path

# Get the absolute path of the EwE directory
EWE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def analyze_globi_interactions(raw_data):
    """Analyze GLOBI interactions to understand the data structure"""
    interaction_types = Counter()
    prey_items = Counter()
    predator_items = Counter()
    
    lines = [line for line in raw_data.split('\n') if line.strip()]
    if len(lines) <= 1:  # Skip if only header
        return
        
    print("\nAnalyzing GLOBI interactions:")
    for line in lines[1:]:  # Skip header row
        parts = line.strip('"').split('","')
        
        # Find interaction type and target species
        interaction_type = None
        if '"eats"' in line or '"preysOn"' in line:
            interaction_type = 'preys_on'
        elif '"eatenBy"' in line or '"preyedUponBy"' in line:
            interaction_type = 'preyed_on_by'
        elif '"hasPathogen"' in line:
            interaction_type = 'has_pathogen'
        elif '"hasParasite"' in line:
            interaction_type = 'has_parasite'
        elif '"hostOf"' in line:
            interaction_type = 'host_of'
        elif '"hasEctoparasite"' in line:
            interaction_type = 'has_ectoparasite'
        elif '"interactsWith"' in line:
            interaction_type = 'interacts_with'
        
        if interaction_type:
            interaction_types[interaction_type] += 1
            
            # Find target species column (should be 2 columns after interaction type)
            interaction_idx = None
            for i, part in enumerate(parts):
                if any(term in part for term in ['preysOn', 'eats', 'preyedUponBy', 'eatenBy', 'hasPathogen', 'hasParasite', 'hostOf', 'hasEctoparasite', 'interactsWith']):
                    interaction_idx = i
                    break
            
            if interaction_idx is not None and len(parts) > interaction_idx + 2:
                target_species = parts[interaction_idx + 2].strip().strip('"').strip(',')
                if target_species and not target_species.isdigit() and not target_species.endswith(',,,,,,,,,') and target_species != 'no:match':
                    if interaction_type == 'preys_on':
                        prey_items[target_species] += 1
                    elif interaction_type == 'preyed_on_by':
                        predator_items[target_species] += 1
    
    print("\nInteraction types found:")
    for itype, count in interaction_types.items():
        print(f"  {itype}: {count}")
    
    if prey_items:
        print("\nPrey items:")
        for prey, count in prey_items.items():
            print(f"  {prey}: {count}")
    
    if predator_items:
        print("\nPredator items:")
        for predator, count in predator_items.items():
            print(f"  {predator}: {count}")

def test_grouping_functions(grouped_species_data):
    """Test the grouping functionality specifically"""
    print("\nTesting grouping functions:")
    print("=" * 80)
    
    # Test create_species_group_lookup
    species_group_lookup = create_species_group_lookup(grouped_species_data)
    print("\n1. Testing species_group_lookup function:")
    test_species = list(grouped_species_data.keys())[:3]  # Get first 3 groups for testing
    for group in test_species:
        # Find a species in this group
        def find_species(tree):
            if isinstance(tree, dict):
                for key, value in tree.items():
                    if ' ' in key:  # This is a species name
                        return key
                    result = find_species(value)
                    if result:
                        return result
            return None
        
        species = find_species(grouped_species_data[group])
        if species:
            result = species_group_lookup(species)
            print(f"  Species: {species}")
            print(f"  Expected group: {group}")
            print(f"  Actual group: {result}")
            print(f"  Match: {result == group}")
            print()

def test_diet_processing():
    # Load the species data and grouped species assignments
    species_data_path = os.path.join(EWE_DIR, "MODELS/v2_NorthernTerritory/v2_NorthernTerritory_1/02_species_data.json")
    grouped_species_path = os.path.join(EWE_DIR, "MODELS/v2_NorthernTerritory/v2_NorthernTerritory_1/03_grouped_species_assignments.json")
    
    with open(species_data_path, 'r') as f:
        species_data = json.load(f)
    
    with open(grouped_species_path, 'r') as f:
        grouped_species_data = json.load(f)
    
    # First test the grouping functions
    test_grouping_functions(grouped_species_data)
    
    # Now process species with GLOBI data
    species_group_lookup = create_species_group_lookup(grouped_species_data)
    
    # Track statistics
    total_species = 0
    species_with_globi = 0
    grouping_methods = {'direct': 0, 'taxonomic_path': 0, 'genus': 0, 'failed': 0}
    
    print("\nProcessing species with GLOBI data:")
    print("=" * 80)
    
    for species_name, species_info in species_data.items():
        if 'diet' not in species_info or 'GLOBI' not in species_info['diet']:
            continue
            
        total_species += 1
        species_with_globi += 1
        
        # Try direct species lookup first
        group = species_group_lookup(species_name)
        if group:
            grouping_methods['direct'] += 1
            method = "Direct species match"
        else:
            # Try taxonomic path
            if 'diet' in species_info and 'GLOBI' in species_info['diet'] and 'raw_data' in species_info['diet']['GLOBI']:
                raw_data = species_info['diet']['GLOBI']['raw_data']
                if raw_data:
                    lines = raw_data.strip().split('\n')
                    if len(lines) > 1:
                        fields = lines[1].strip('"').split('","')
                        if len(fields) > 2:
                            source_path = fields[2]  # source_taxon_path
                            group, matched_taxon = find_functional_group_from_path(source_path, grouped_species_data)
                            if group:
                                grouping_methods['taxonomic_path'] += 1
                                method = f"Taxonomic path match on {matched_taxon}"
            
            # If still no group, try genus
            if not group:
                try:
                    genus = species_name.split()[0]
                    group = f"Other_{genus}"
                    grouping_methods['genus'] += 1
                    method = "Genus-based temporary group"
                except:
                    grouping_methods['failed'] += 1
                    method = "Failed to group"
                    group = None
        
        print(f"\nProcessing {species_name}")
        print(f"Group: {group}")
        print(f"Method: {method}")
        
        raw_data = species_info['diet']['GLOBI'].get('raw_data')
        if raw_data:
            print("\nAnalyzing raw GLOBI data:")
            lines = raw_data.strip().split('\n')
            if len(lines) > 1:
                # Print header analysis
                header = lines[0].strip('"').split('","')
                print("\nHeader fields:")
                for i, field in enumerate(header):
                    print(f"{i}: {field}")
                
                # Print first data line analysis
                print("\nFirst data line:")
                fields = lines[1].strip('"').split('","')
                print(f"Number of fields: {len(fields)}")
                for i, field in enumerate(fields):
                    print(f"{i}: {field}")
                
                # Show taxonomic paths
                if len(fields) > 12:
                    source_path = fields[2]  # source_taxon_path
                    target_path = fields[12]  # target_taxon_path
                    print("\nTaxonomic paths:")
                    print(f"Source path: {source_path}")
                    print(f"Target path: {target_path}")
                    
                    # Try to find groups for each taxon in paths
                    print("\nSource path analysis:")
                    source_taxa = [t.strip() for t in source_path.split('|') if t.strip() and t.strip() != 'root']
                    print(f"Found {len(source_taxa)} taxa in source path:")
                    for taxon in reversed(source_taxa):
                        group, matched = find_functional_group_from_path(taxon, grouped_species_data)
                        print(f"  Taxon: {taxon}")
                        print(f"  Found group: {group}")
                        print(f"  Matched on: {matched}")
                    
                    print("\nTarget path analysis:")
                    target_taxa = [t.strip() for t in target_path.split('|') if t.strip() and t.strip() != 'root']
                    print(f"Found {len(target_taxa)} taxa in target path:")
                    for taxon in reversed(target_taxa):
                        group, matched = find_functional_group_from_path(taxon, grouped_species_data)
                        print(f"  Taxon: {taxon}")
                        print(f"  Found group: {group}")
                        print(f"  Matched on: {matched}")
                        
                    # Look for interaction type
                    print("\nInteraction type analysis:")
                    interaction_type = None
                    for i, field in enumerate(fields):
                        if any(term in field for term in ['preysOn', 'eats', 'preyedUponBy', 'eatenBy']):
                            interaction_type = field
                            print(f"Found interaction type in field {i}: {field}")
                            break
                    if not interaction_type:
                        print("No interaction type found in fields")
        
        # Process GLOBI data for this species
        output_file = os.path.join(EWE_DIR, "MODELS/v2_NorthernTerritory/v2_NorthernTerritory_1/test_globi_interactions.json")
        interaction_data = parse_globi_data({species_name: species_info}, grouped_species_data, output_file)
            
        if group and group in interaction_data:
            group_data = interaction_data[group]
            print(f"\nInteractions summary for {group}:")
            print(f"Total prey interactions: {group_data['total_prey_interactions']}")
            print(f"Total predator interactions: {group_data['total_predator_interactions']}")
            
            if group_data['preys_on']:
                print("\nPrey interactions (showing up to 5):")
                for prey, data in list(group_data['preys_on'].items())[:5]:
                    print(f"  {prey}: {data}")
                
            if group_data['is_preyed_on_by']:
                print("\nPredator interactions (showing up to 5):")
                for predator, data in list(group_data['is_preyed_on_by'].items())[:5]:
                    print(f"  {predator}: {data}")
        else:
            print(f"No interaction data found for group {group}")
        # if total_species == 200:
        #     break
    print(f"\n{'='*80}")
    print(f"Processing complete!")
    print(f"Total species processed: {total_species}")
    print(f"Species with GLOBI data: {species_with_globi}")
    print("\nGrouping method statistics:")
    for method, count in grouping_methods.items():
        print(f"  {method}: {count}")

if __name__ == "__main__":
    test_diet_processing()
