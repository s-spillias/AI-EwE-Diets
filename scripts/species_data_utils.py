import json
from collections import defaultdict

def create_nested_dict():
    return defaultdict(create_nested_dict)

def organize_species_data(species_data):
    hierarchical_data = create_nested_dict()
    taxonomic_levels = ['Kingdom', 'Phylum', 'Class', 'Order', 'Family', 'Genus', 'Species']

    for species, info in species_data.items():
        current_level = hierarchical_data
        for level in taxonomic_levels[:-1]:  # Exclude 'Species' from iteration
            if level in info:
                current_level = current_level[info[level]]
        
        # Add the species as the final level
        if 'Species' in info:
            current_level[info['Species']] = species

    # Convert defaultdict to regular dict for JSON serialization
    def dict_to_regular(d):
        if isinstance(d, defaultdict):
            d = {k: dict_to_regular(v) for k, v in d.items()}
        return d

    return dict_to_regular(hierarchical_data)
