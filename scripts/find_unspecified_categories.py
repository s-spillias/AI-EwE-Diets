import os
import json
import pandas as pd
from collections import Counter

def find_unspecified_categories(directory):
    """
    Search through species data files in the given directory for any 'unspecified' categories
    in GLOBI target taxon names.
    """
    unspecified_categories = Counter()
    
    # Walk through the directory
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file == '02_species_data.json':  # This file contains the GLOBI data
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        species_data = json.load(f)
                        
                        # Iterate through each species
                        for species_info in species_data.values():
                            if 'diet' in species_info and 'GLOBI' in species_info['diet']:
                                globi_data = species_info['diet']['GLOBI']
                                
                                # Check interactions
                                if 'interactions' in globi_data:
                                    for interaction in globi_data['interactions']:
                                        target_name = interaction.get('targetTaxonName', '')
                                        if target_name and 'unspecified' in target_name.lower():
                                            unspecified_categories[target_name.lower()] += 1
                except Exception as e:
                    print(f"Error processing {file_path}: {str(e)}")
    
    return unspecified_categories

if __name__ == "__main__":
    # Get the absolute path of the EwE directory
    EWE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    saleh_bay_dir = os.path.join(EWE_DIR, 'MODELS', 'Saleh_Bay')
    
    print("Searching for 'unspecified' categories in Saleh Bay data...")
    categories = find_unspecified_categories(saleh_bay_dir)
    
    if categories:
        print("\nFound the following 'unspecified' categories:")
        print("\nCategory : Occurrence count")
        print("-" * 50)
        for category, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
            print(f"{category} : {count}")
    else:
        print("No 'unspecified' categories found.")
