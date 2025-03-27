import sys
import os
import json
import logging
from ask_AI import ask_ai
import re

# Set up logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.ecobase_search import main as ecobase_search

# Define the structure of the EwE parameter matrix
ewe_matrix = {
    "No.": [],
    "Trophic group": [],
    "Habitat area (fraction)": [],
    "Biomass in habitat area (t/km²)": [],
    "Biomass ref": [],
    "P/B (year⁻¹)": [],
    "P/B ref": [],
    "Q/B (year⁻¹)": [],
    "Q/B ref": [],
    "EE": [],
    "Diet": [],
    "Representative taxa": []
}

def load_ai_config(output_dir):
    config_path = os.path.join(output_dir, 'ai_config.json')
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.warning(f"AI config file not found at {config_path}. Using default 'gemini' for all tasks.")
        return {
            'eweParamsAI': 'gemini'
        }

def load_grouped_species_assignments(model_dir):
    file_path = os.path.join(model_dir, "03_grouped_species_assignments.json")
    with open(file_path, 'r') as f:
        return list(json.load(f).keys())

def assign_parameter(group, parameter, all_values, all_metadata, ai_model):
    prompt_dict = {
        "group": group,
        "parameter": parameter,
        "all_values": all_values,
        "all_metadata": all_metadata,
        "instructions": """
        Analyze the provided values and metadata to determine the most appropriate value for the parameter.
        Consider the following:
        1. The relevance of each model to the group in question.
        2. The consistency of values across different models.
        3. Any trends or patterns in the data that might indicate a more suitable value.
        4. The ecological context provided by the metadata.

        If a clear consensus emerges, use that value. If there's significant variation, suggest a value that best represents the group based on the available information.

        Provide a detailed explanation for your decision, including your reasoning and any assumptions made.

        Return your response in the following JSON format:
        {
            "value": "your suggested value",
            "explanation": "your detailed explanation",
            "reference": "the reference from the metadata of the model you used for this value"
        }
        """
    }
    
    prompt = json.dumps(prompt_dict, indent=2)
    response = ask_ai(prompt, ai_model)
    
    # Parse the response using regex to find content within curly braces
    json_match = re.search(r'\{.*\}', response, re.DOTALL)
    
    if json_match:
        try:
            result = json.loads(json_match.group())
            return result.get('value', 'N/A'), result.get('explanation', 'No explanation provided'), result.get('reference', 'No reference provided')
        except json.JSONDecodeError:
            logging.warning(f"Failed to parse JSON from AI response for {group}, {parameter}")
            return "N/A", "No explanation provided", "No reference provided"
    else:
        logging.warning(f"No JSON found in AI response for {group}, {parameter}")
        return "N/A", "No explanation provided", "No reference provided"

def fill_matrix(ewe_matrix, grouped_species, model_dir, ai_model):
    for i, group in enumerate(grouped_species):
        print(group)
        query = f"Western Australian shelf species in {group}"
        # Search for the group in EcoBase
        results = ecobase_search(query=query)
        
        if results and 'search_results' in results and 'metadata' in results:
            all_group_data = results['search_results']
            all_metadata = results['metadata']
            
            ewe_matrix["No."].append(i + 1)
            ewe_matrix["Trophic group"].append(group)
            
            # Assign parameters using AI
            for param, key, ref_key in [
                ('habitat_area', "Habitat area (fraction)", None),
                ('biomass', "Biomass in habitat area (t/km²)", "Biomass ref"),
                ('pb', "P/B (year⁻¹)", "P/B ref"),
                ('qb', "Q/B (year⁻¹)", "Q/B ref"),
                ('ee', "EE", None)
            ]:
                all_values = [group_data.get(param, {}).get('#text', 'N/A') for group_data in all_group_data]
                assigned_value, explanation, reference = assign_parameter(group, param, all_values, all_metadata, ai_model)
                ewe_matrix[key].append(assigned_value)
                if ref_key:
                    ewe_matrix[ref_key].append(reference)
                logging.info(f"{group} - {param}: {assigned_value} ({explanation})")
            
            ewe_matrix["Diet"].append("N/A")  # Diet information might require additional processing
            ewe_matrix["Representative taxa"].append("N/A")  # Placeholder for representative taxa
        else:
            logging.warning(f"No matching group found for {group}")
            # Add placeholder values for all columns to maintain consistent length
            for key in ewe_matrix.keys():
                if key not in ["No.", "Trophic group"]:
                    ewe_matrix[key].append("N/A")

def main(model_dir):
    # Load AI configuration
    ai_config = load_ai_config(model_dir)
    ai_model = ai_config.get('eweParamsAI', 'gemini')
    logging.info(f"Using AI model: {ai_model} for EwE parameters")

    # Load grouped species assignments
    grouped_species = load_grouped_species_assignments(model_dir)

    # Fill the matrix
    fill_matrix(ewe_matrix, grouped_species, model_dir, ai_model)

    # Save the results to a JSON file
    output_json_file = os.path.join(model_dir, "06_ewe_params.json")
    with open(output_json_file, 'w') as f:
        json.dump(ewe_matrix, f, indent=2)

    logging.info(f"EwE parameters saved to {output_json_file}")

if __name__ == "__main__":
    # The model directory should be passed as an argument when running the script
    if len(sys.argv) > 1:
        model_dir = sys.argv[1]
        main(model_dir)
    else:
        print("Please provide the model directory as an argument.")
