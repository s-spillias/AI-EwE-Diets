import json
from collections import Counter
from diet_data_utils import find_functional_group_from_path, find_functional_group, create_species_group_lookup

def print_section(title):
    """Helper to print formatted section headers"""
    print(f"\n{'-'*20} {title} {'-'*20}")

# Load the species data
with open('MODELS/Saleh_Bay/02_species_data.json', 'r') as f:
    species_data = json.load(f)

# Load the grouped species data
with open('MODELS/Saleh_Bay/03_grouped_species_assignments.json', 'r') as f:
    grouped_data = json.load(f)

def extract_species_names(data):
    """Recursively extract species names from nested dictionary structure"""
    species_names = []
    
    def traverse(d, parent_key=None):
        if isinstance(d, dict):
            if "specCode" in d and d["specCode"] == "Unknown":
                # Found a leaf node with specCode: Unknown
                if parent_key:
                    species_names.append(parent_key)
            else:
                # Continue traversing
                for key, value in d.items():
                    traverse(value, key)
    
    traverse(data)
    return species_names

# Get Hard_coral species from the nested structure
coral_data = grouped_data.get('Hard_coral', {})
coral_species = extract_species_names(coral_data)

print_section("Test Species List")
print(f"Found {len(coral_species)} Hard_coral species:")
print(json.dumps(coral_species, indent=2))

# Create species to group lookup function
species_group_lookup = create_species_group_lookup(grouped_data)

# Test group mapping
print_section("Testing Group Mapping")
for species in coral_species:
    if species in species_data and 'diet' in species_data[species]:
        diet_data = species_data[species]['diet']
        if 'GLOBI' in diet_data and 'interactions' in diet_data['GLOBI']:
            print(f"\nAnalyzing interactions for {species}:")
            
            for interaction in diet_data['GLOBI']['interactions']:
                interaction_type = interaction.get('interactionTypeName', '').lower()
                source_species = interaction.get('sourceTaxonName')
                source_path = interaction.get('sourceTaxonPath', '')
                target_species = interaction.get('targetTaxonName')
                target_path = interaction.get('targetTaxonPath', '')
                
                print(f"\nInteraction: {interaction_type}")
                print(f"Source: {source_species}")
                print(f"Source Path: {source_path}")
                print(f"Target: {target_species}")
                print(f"Target Path: {target_path}")
                
                # Test different group mapping methods
                if source_species and source_species != 'no:match':
                    print("\nSource species group mapping:")
                    # Method 1: Direct species lookup
                    group1 = species_group_lookup(source_species)
                    print(f"1. Direct species lookup: {group1}")
                    
                    # Method 2: Path-based lookup
                    group2, matched_taxon = find_functional_group_from_path(source_path, grouped_data)
                    print(f"2. Path-based lookup: {group2} (matched: {matched_taxon})")
                    
                    # Method 3: Direct functional group lookup
                    group3 = find_functional_group(source_species, grouped_data)
                    print(f"3. Direct functional group lookup: {group3}")
                
                if target_species and target_species != 'no:match':
                    print("\nTarget species group mapping:")
                    # Method 1: Direct species lookup
                    group1 = species_group_lookup(target_species)
                    print(f"1. Direct species lookup: {group1}")
                    
                    # Method 2: Path-based lookup
                    group2, matched_taxon = find_functional_group_from_path(target_path, grouped_data)
                    print(f"2. Path-based lookup: {group2} (matched: {matched_taxon})")
                    
                    # Method 3: Direct functional group lookup
                    group3 = find_functional_group(target_species, grouped_data)
                    print(f"3. Direct functional group lookup: {group3}")

# Collect all interactions
print_section("Interaction Summary")
prey_counter = Counter()
predator_counter = Counter()
unmapped_species = set()

for species in coral_species:
    if species in species_data and 'diet' in species_data[species]:
        diet_data = species_data[species]['diet']
        if 'GLOBI' in diet_data and 'interactions' in diet_data['GLOBI']:
            for interaction in diet_data['GLOBI']['interactions']:
                interaction_type = interaction.get('interactionTypeName', '').lower()
                source_species = interaction.get('sourceTaxonName')
                source_path = interaction.get('sourceTaxonPath')
                target_species = interaction.get('targetTaxonName')
                target_path = interaction.get('targetTaxonPath')
                
                # Track what corals eat
                if interaction_type in ['eats', 'preyson']:
                    if target_species and target_species != 'no:match':
                        # Try all mapping methods
                        group = None
                        
                        # 1. Try path-based lookup first
                        group, _ = find_functional_group_from_path(target_path, grouped_data)
                        
                        # 2. If no match, try direct species lookup
                        if not group:
                            group = species_group_lookup(target_species)
                        
                        # 3. If still no match, try direct functional group lookup
                        if not group:
                            group = find_functional_group(target_species, grouped_data)
                        
                        if group:
                            prey_counter[group] += 1
                        else:
                            unmapped_species.add(target_species)
                
                # Track what eats corals
                elif interaction_type in ['eatenby', 'preyeduponby']:
                    if source_species and source_species != 'no:match':
                        # Try all mapping methods
                        group = None
                        
                        # 1. Try path-based lookup first
                        group, _ = find_functional_group_from_path(source_path, grouped_data)
                        
                        # 2. If no match, try direct species lookup
                        if not group:
                            group = species_group_lookup(source_species)
                        
                        # 3. If still no match, try direct functional group lookup
                        if not group:
                            group = find_functional_group(source_species, grouped_data)
                        
                        if group:
                            predator_counter[group] += 1
                        else:
                            unmapped_species.add(source_species)

print("\nWhat Hard_coral eats (mapped to functional groups):")
for prey, count in prey_counter.most_common():
    print(f"- {prey}: {count}")

print("\nWhat eats Hard_coral (mapped to functional groups):")
for predator, count in predator_counter.most_common():
    print(f"- {predator}: {count}")

if unmapped_species:
    print("\nSpecies that couldn't be mapped to functional groups:")
    for species in sorted(unmapped_species):
        print(f"- {species}")
