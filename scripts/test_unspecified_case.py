import pandas as pd
import json
from diet_data_utils import normalize_category

# Test case from the real data
test_interaction = {
    'sourceTaxonName': 'Leodice antennata',
    'sourceTaxonPath': 'Animalia | Annelida | Polychaeta | Eunicida | Eunicidae | Leodice | Leodice antennata',
    'interactionTypeName': 'eats',
    'targetTaxonName': 'unspecified detritus',
    'targetTaxonPath': None,
    'sourceBodyPartName': None,
    'targetBodyPartName': None,
    'eventDate': None,
    'decimalLatitude': None,
    'decimalLongitude': None,
    'localityName': None,
    'referenceDoi': None,
    'referenceCitation': None,
    'studyTitle': None
}

def test_interaction_processing():
    print("\nTesting interaction processing:")
    print("-" * 50)
    
    # Create a DataFrame with the test interaction
    df = pd.DataFrame([test_interaction])
    
    # Process the target taxon name
    original_target = df['targetTaxonName'].iloc[0]
    normalized_target = normalize_category(original_target)
    
    print(f"Original target: {original_target}")
    print(f"Normalized target: {normalized_target}")
    
    # Verify the normalization worked as expected
    assert normalized_target == "detritus", f"Expected 'detritus' but got '{normalized_target}'"
    print("\nTest passed! ✓")
    print("Successfully normalized 'unspecified detritus' to 'detritus'")

if __name__ == "__main__":
    test_interaction_processing()
