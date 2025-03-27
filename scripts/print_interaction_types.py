import json
from collections import Counter

# Load the species data
with open('MODELS/Saleh_Bay/02_species_data.json', 'r') as f:
    species_data = json.load(f)

# Collect all interaction types
interaction_types = Counter()

# Go through each species
for species, data in species_data.items():
    if 'diet' in data and 'GLOBI' in data['diet']:
        if 'interactions' in data['diet']['GLOBI']:
            for interaction in data['diet']['GLOBI']['interactions']:
                if 'interactionTypeName' in interaction:
                    interaction_types[interaction['interactionTypeName']] += 1

# Print results
print("\nInteraction types and their counts:")
for itype, count in sorted(interaction_types.items()):
    print(f"{itype}: {count}")
