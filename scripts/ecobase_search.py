import requests
import json
import os
import xml.etree.ElementTree as ET
import re
from ask_AI import ask_ai
from rag_search import rag_search

# Set up logging
def log_info(msg):
    print(f"[INFO] {msg}")

def log_error(msg):
    print(f"[ERROR] {msg}")

# Create output directory
output_dir = "data/ecobase_models"
os.makedirs(output_dir, exist_ok=True)

def parse_xml_to_dict(element):
    """Parse XML element to dictionary, including attributes and handling mixed content"""
    result = {}
    if element.attrib:
        result["@attributes"] = element.attrib
    if element.text and element.text.strip():
        result["#text"] = element.text.strip()
    for child in element:
        child_data = parse_xml_to_dict(child)
        if child.tag in result:
            if type(result[child.tag]) is list:
                result[child.tag].append(child_data)
            else:
                result[child.tag] = [result[child.tag], child_data]
        else:
            result[child.tag] = child_data
    return result

def get_all_models():
    """Fetch all models and save as JSON"""
    try:
        log_info("Fetching list of all models...")
        response = requests.get('http://sirs.agrocampus-ouest.fr/EcoBase/php/webser/soap-client_3.php')
        response.raise_for_status()
        
        # Parse XML response
        root = ET.fromstring(response.content)
        models = [parse_xml_to_dict(model) for model in root.findall('.//model')]
        
        # Save full model list
        with open("data/all_models/all_models.json", 'w') as f:
            json.dump(models, f, indent=2)
        
        log_info(f"Found {len(models)} models. Saved to all_models.json")
        return models
    except Exception as e:
        log_error(f"Error getting models: {str(e)}")
        return None

def check_model_exists(model_id):
    """Check if the model exists in all_models.json"""
    try:
        with open("data/all_models/all_models.json", 'r') as f:
            all_models = json.load(f)
        
        return any(model["model_number"] == str(model_id) for model in all_models)
    except Exception as e:
        log_error(f"Error checking model existence: {str(e)}")
        return False

def get_model_data(model_id):
    """Fetch data for a specific model"""
    if not check_model_exists(model_id):
        log_error(f"Model {model_id} does not exist in all_models.json")
        return None

    try:
        log_info(f"Getting data for model {model_id}")
        response = requests.get(f'http://sirs.agrocampus-ouest.fr/EcoBase/php/webser/soap-client.php?no_model={model_id}')
        response.raise_for_status()
        
        # Parse XML response
        root = ET.fromstring(response.content)
        model_data = parse_xml_to_dict(root)
        
        # Create and save model data
        model_dir = os.path.join(output_dir, f"model_{model_id}")
        os.makedirs(model_dir, exist_ok=True)
        model_file_path = os.path.join(model_dir, f"model_{model_id}_data.json")
        with open(model_file_path, 'w') as f:
            json.dump(model_data, f, indent=2)
        log_info(f"Data for model {model_id} has been saved as JSON")
        return model_data
    except Exception as e:
        log_error(f"Error getting data for model {model_id}: {str(e)}")
        return None

def extract_group_names(model_data):
    return [group['group_name']['#text'] for group in model_data['group_descr']['group']]

def find_matching_groups(group_names, query):
    # Define prompt for the AI
    prompt = f"For the purpose of getting parameters for an EwE model, which of these group names are analogous to '{query}': {', '.join(group_names)}. Return the best matches as a list inside square brackets. If none match, return an empty list."
    
    # Get the AI response
    response = ask_ai(prompt)
    
    # Clean and parse the response for a list format, handling potential variations
    # Remove surrounding brackets and split by comma, then strip whitespace
    matches = re.findall(r'\[(.*?)\]', response)  # Extract content within square brackets
    if matches:
        cleaned_response = matches[0]  # Use the first bracketed match if available
        return [name.strip() for name in cleaned_response.split(',')]
    else:
        # Fallback: split the response directly if brackets are missing
        return [name.strip() for name in response.split(',')]

def extract_group_data(model_data, group_name):
    for group in model_data['group_descr']['group']:
        if group['group_name']['#text'] == group_name:
            return group
    return None

def extract_model_numbers(results):
    """Extract model numbers from RAG search results"""
    model_numbers = set()
    for result in results:
        # Try to find a list enclosed in square brackets
        list_match = re.search(r'\[([\d,\s]+)\]', result)
        if list_match:
            # If found, split the string into a list and convert to integers
            number_list = [int(num.strip()) for num in list_match.group(1).split(',') if num.strip().isdigit()]
            model_numbers.update(number_list)
        else:
            # If no list is found, fall back to extracting all numbers from the text
            numbers = [int(num) for num in re.findall(r'\b\d+\b', result)]
            model_numbers.update(numbers)
    return list(model_numbers)

def extract_model_metadata(model_id):
    """Extract metadata for a specific model from all_models.json"""
    try:
        with open("data/all_models/all_models.json", 'r') as f:
            all_models = json.load(f)
        
        for model in all_models:
            if model["model_number"] == str(model_id):
                return model
        
        log_error(f"Model {model_id} not found in all_models.json")
        return None
    except Exception as e:
        log_error(f"Error extracting metadata for model {model_id}: {str(e)}")
        return None

def main(query=None, model_id=None):
    log_info("Starting EcoBase model data retrieval...")
    
    # Get all models if not already fetched
    if not os.path.exists("data/all_models/all_models.json"):
        all_models = get_all_models()
        if all_models is None:
            return
    
    if model_id and query:
        # If both model_id and query are provided, extract group names and find matches
        model_data = get_model_data(model_id)
        if model_data:
            group_names = extract_group_names(model_data)
            matching_groups = find_matching_groups(group_names, query)
            results = []
            for group_name in matching_groups:
                group_data = extract_group_data(model_data, group_name)
                if group_data:
                    results.append(group_data)
            metadata = extract_model_metadata(model_id)
            return {
                "search_results": results,
                "citations": [f"EcoBase Model {model_id}"],
                "metadata": metadata
            }
    elif model_id:
        # If only model_id is provided, just get data for that model
        model_data = get_model_data(model_id)
        if model_data:
            log_info(f"Data for model {model_id} has been retrieved")
            metadata = extract_model_metadata(model_id)
            return {"model_data": model_data, "metadata": metadata}
    elif query:
        # If only query is provided, perform the RAG search on all models
        try:
            initial_results, initial_citations = rag_search(f"Please identify the most relevant model numbers that could be used to inform parameter values for an EwE model focussed on the following query (loose fits are ok), return a list in square brackets in the response: '{query}'", 'data/all_models')
            
            if initial_results:
                log_info(f"Initial search complete. Results found.")
                model_numbers = extract_model_numbers(initial_results)
                log_info(f"Extracted model numbers: {model_numbers}")
                
                all_results = []
                all_citations = []
                all_metadata = []
                
                for model_num in model_numbers:
                    if check_model_exists(model_num):
                        print(f"Model {model_num} EXISTS!")
                        model_data = get_model_data(str(model_num))
                        try:
                            no_data = model_data['Description']['#text']
                            print("Data not Available")
                            continue
                        except:
                            print("Data Available")
                    if model_data:
                        group_names = extract_group_names(model_data)
                        matching_groups = find_matching_groups(group_names, query)
                        for group_name in matching_groups:
                            group_data = extract_group_data(model_data, group_name)
                            if group_data:
                                all_results.append(group_data)
                                all_citations.append(f"EcoBase Model {model_num}")
                                all_metadata.append(extract_model_metadata(model_num))
                    else:
                        log_error(f"Model {model_num} does not exist in all_models.json")
                
                if all_results:
                    log_info(f"Search complete on extracted models. Results found.")
                    return {
                        "search_results": all_results,
                        "citations": all_citations,
                        "metadata": all_metadata
                    }
                else:
                    log_info("No results found in extracted models.")
                    return None
            else:
                log_info("Initial search complete. No results found.")
                return None
        except Exception as e:
            log_error(f"Error during RAG search: {str(e)}")
            return None
    else:
        log_error("Either a query or a model ID must be provided.")
    
    return None

def get_single_model_groups(query):
    """
    Find a single relevant model based on the query, download its data,
    and extract all group names from this model.
    """
    log_info(f"Searching for a relevant EcoBase model for query: {query}")
    
    # Use rag_search to find the most relevant model
    results, citations = rag_search(f"Please identify the most relevant model number that could be used to inform parameter values for an EwE model focussed on the following query: '{query}'", 'data/all_models')
    
    if not results:
        log_error("No relevant model found")
        return []

    # Extract the model number from the results
    model_numbers = re.findall(r'\b\d+\b', results[0])
    if not model_numbers:
        log_error("No model number found in the search results")
        return []

    model_number = model_numbers[0]
    log_info(f"Selected model {model_number} as most relevant")
    
    # Download the model data
    model_data = get_model_data(model_number)
    
    if not model_data:
        log_error(f"Failed to retrieve data for model {model_number}")
        return []
    
    # Extract group names from the model data
    groups = []
    if 'group_descr' in model_data and 'group' in model_data['group_descr']:
        groups = [group['group_name']['#text'] for group in model_data['group_descr']['group']]
        log_info(f"Extracted {len(groups)} groups from model {model_number}")
    else:
        log_info(f"No groups found in model {model_number}")
    
    return groups

# ... (keep the rest of the file unchanged)

if __name__ == "__main__":
    # Example usage of the new function:
    query = 'Marine ecosystem in the Mediterranean Sea'
    relevant_groups = get_single_model_groups(query)
    print(f"Groups from the most relevant model for '{query}':")
    for group in relevant_groups:
        print(f"- {group}")
