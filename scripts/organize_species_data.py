import json
from collections import defaultdict

def create_nested_dict():
    return defaultdict(create_nested_dict)

def organize_species_data(input_file, output_file):
    # Read the input JSON file
    with open(input_file, 'r') as f:
        species_data = json.load(f)

    # Create a nested dictionary to represent the hierarchical structure
    hierarchical_data = create_nested_dict()

    # Organize the data
    for species, info in species_data.items():
        current_level = hierarchical_data
        for level in ['Kingdom', 'Phylum', 'Class', 'Order', 'Family', 'Genus']:
            if level in info:
                current_level = current_level[info[level]]
        
        # Add the species layer
        current_level = current_level["Species"]
        
        # Add the species information at the lowest level
        current_level[species] = info

    # Convert defaultdict to regular dict for JSON serialization
    def dict_to_regular(d):
        if isinstance(d, defaultdict):
            d = {k: dict_to_regular(v) for k, v in d.items()}
        return d

    hierarchical_data = dict_to_regular(hierarchical_data)

    # Write the organized data to the output file
    with open(output_file, 'w') as f:
        json.dump(hierarchical_data, f, indent=2)

if __name__ == "__main__":
    input_file = 'EwE/outputs/02_species_data.json'
    output_file = 'EwE/outputs/02_species_data_hierarchical.json'
    organize_species_data(input_file, output_file)
    print(f"Hierarchical species data has been saved to {output_file}")
