import os
import json
import pandas as pd
import argparse
import re
from ask_AI import ask_ai
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Get the absolute path of the EwE directory
EWE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def load_ai_config(output_dir):
    config_path = os.path.join(output_dir, 'ai_config.json')
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"AI config file not found at {config_path}. Using default 'gemini' for all tasks.")
        return {
            'constructDietMatrixAI': 'gemini'
        }

def load_species_list(filename):
    with open(filename, 'r') as f:
        data = json.load(f)
    return list(data.keys())

def load_diet_data(filename):
    with open(filename, 'r') as f:
        data = json.load(f)
    return {species: group_data.get('diet_proportions', {}) for species, group_data in data.items()}

def extract_proportions_from_ai_response(response):
    """Extract diet proportions from AI response, handling both direct JSON and text formats"""
    # First try to find JSON object in the response
    json_match = re.search(r'\{.*\}', response, re.DOTALL)
    if json_match:
        try:
            proportions = json.loads(json_match.group(0))
            if isinstance(proportions, dict):
                # Convert any string percentages to float decimals
                cleaned_proportions = {}
                for prey, value in proportions.items():
                    if isinstance(value, str):
                        # Extract number from percentage string (e.g., "40%" -> 0.4)
                        match = re.search(r'(\d+(?:\.\d+)?)', value)
                        if match:
                            cleaned_proportions[prey] = float(match.group(1)) / 100
                    elif isinstance(value, (int, float)):
                        cleaned_proportions[prey] = float(value)
                    elif isinstance(value, dict):
                        # Skip nested dictionaries
                        continue
                return cleaned_proportions
        except json.JSONDecodeError:
            pass

    # If JSON parsing fails, try to extract percentages from text format
    proportions = {}
    lines = response.split('\n')
    for line in lines:
        # Match patterns like "Prey: 40%" or "Prey - 40%" or "Prey 40%"
        match = re.search(r'([^:]+?)(?::|-)?\s*(\d+(?:\.\d+)?)\s*%', line)
        if match:
            prey = match.group(1).strip()
            percentage = float(match.group(2)) / 100
            proportions[prey] = percentage

    return proportions

def get_diet_proportions(ai_summary, species_list, ai_model):
    prompt = f"""
    Given the following AI summary of a species' diet:
    {json.dumps(ai_summary, indent=2)}
    
    Please convert this summary into a JSON object where the keys are the prey items and the values are the 
    numeric proportions of the diet (as decimals between 0 and 1). Only use the names for the groups provided here:
    
    {species_list + ["Detritus"]}
    
    If a range of proportions is given, use the average. 
    Estimate any items that don't have clear numeric values. The sum of all proportions should not exceed 1.

    If a prey item isn't present in the list of groups provided above, interpret as the closest likely functional group.
    
    Format your response as a simple JSON object with prey items as keys and decimal numbers as values, like this:
    {{"Prey1": 0.4, "Prey2": 0.3, "Prey3": 0.3}}
    """
    
    try:
        response = ask_ai(prompt, ai_model)
        proportions = extract_proportions_from_ai_response(response)
        return scale_proportions(proportions)
    except Exception as e:
        logging.error(f"Error getting diet proportions: {str(e)}")
        return {}

def scale_proportions(proportions):
    """Scale proportions to sum to 1 while handling empty or invalid inputs"""
    if not proportions:
        return {}
        
    try:
        total = sum(float(v) for v in proportions.values() if isinstance(v, (int, float)))
        if total > 0:
            return {k: float(v) / total for k, v in proportions.items() if isinstance(v, (int, float))}
    except (TypeError, ValueError) as e:
        logging.error(f"Error scaling proportions: {str(e)}")
    return proportions

def load_intermediate_results(filename):
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            return json.load(f)
    return {}

def save_intermediate_results(filename, data):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)

def construct_diet_matrix(species_list, diet_data, intermediate_file, ai_model):
    intermediate_results = load_intermediate_results(intermediate_file)
    
    # Combine species_list with keys from intermediate_results
    all_species = list(set(species_list + list(intermediate_results.keys())))
    
    matrix = pd.DataFrame(0, index=all_species, columns=all_species)
    
    for predator in all_species:
        logging.info(predator)
        try:
            if predator in intermediate_results:
                proportions = intermediate_results[predator]
            elif predator in diet_data:
                ai_summary = diet_data[predator]
                proportions = get_diet_proportions(ai_summary, species_list, ai_model)
                if proportions:  # Only save if we got valid proportions
                    intermediate_results[predator] = proportions
                    save_intermediate_results(intermediate_file, intermediate_results)
            else:
                continue
            
            # Only process if we have valid proportions
            if proportions and isinstance(proportions, dict):
                for prey, proportion in proportions.items():
                    if not isinstance(proportion, (int, float)):
                        continue
                    if prey in all_species:
                        matrix.at[predator, prey] = float(proportion)
                    else:
                        # Handle cases where the prey item doesn't exactly match a species in the list
                        for species in all_species:
                            if prey.lower() in species.lower():
                                matrix.at[predator, species] = float(proportion)
                                break
                        else:
                            logging.warning(f"No match found for prey '{prey}' of predator '{predator}'")
        except Exception as e:
            logging.error(f"Error processing predator {predator}: {str(e)}")
            continue
    
    return matrix

def main(species_file, diet_file, output_file, intermediate_file, output_dir):
    print("Loading AI configuration...")
    ai_config = load_ai_config(output_dir)
    ai_model = ai_config.get('constructDietMatrixAI', 'gemini')
    print(f"Using AI model: {ai_model} for constructing diet matrix")

    print(f"Loading species list from {species_file}")
    species_list = load_species_list(species_file)
    
    print(f"Loading diet data from {diet_file}")
    diet_data = load_diet_data(diet_file)
    
    print("Constructing diet matrix")
    try:
        diet_matrix = construct_diet_matrix(species_list, diet_data, intermediate_file, ai_model)
        
        print("Diet Matrix:")
        print(diet_matrix)
        
        # Ensure numeric data for the diet matrix
        diet_matrix = diet_matrix.astype(float)

        # Save the transposed diet matrix to CSV with a label clarifying predators are columns
        diet_matrix_t = diet_matrix.T
        diet_matrix_t.index.name = "Prey_rows/Predator_columns"  # This will appear in the top-left cell
        diet_matrix_t.to_csv(output_file, index=True)
        print(f"\nDiet matrix saved to '{output_file}'")
        return True
    except Exception as e:
        logging.error(f"Error constructing diet matrix: {str(e)}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Construct diet matrix from species list and diet data")
    parser.add_argument("--output_dir", default="outputs", help="Output directory for all files")
    parser.add_argument("--species_file", help="Path to the species list file")
    parser.add_argument("--diet_file", help="Path to the diet data file")
    parser.add_argument("--output_file", help="Path to save the output diet matrix")
    parser.add_argument("--intermediate_file", help="Path to save/load intermediate results")
    
    args = parser.parse_args()
    
    # Set default paths based on output_dir if not provided
    if not args.species_file:
        args.species_file = os.path.join(EWE_DIR, args.output_dir, "03_grouped_species_assignments.json")
    if not args.diet_file:
        args.diet_file = os.path.join(EWE_DIR, args.output_dir, "04d_diet_summaries.json")
    if not args.output_file:
        args.output_file = os.path.join(EWE_DIR, args.output_dir, "05_diet_matrix.csv")
    if not args.intermediate_file:
        args.intermediate_file = os.path.join(EWE_DIR, args.output_dir, "05_intermediate_results.json")
    
    success = main(args.species_file, args.diet_file, args.output_file, args.intermediate_file, args.output_dir)
    if not success:
        sys.exit(1)
