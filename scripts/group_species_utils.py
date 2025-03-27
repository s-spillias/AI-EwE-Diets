import json
import logging
import re
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import requests
import os
from ask_AI import ask_ai

# Optional import for EcoBase functionality
try:
    from ecobase_search import get_single_model_groups
    ECOBASE_AVAILABLE = True
except ImportError:
    ECOBASE_AVAILABLE = False
    def get_single_model_groups(*args, **kwargs):
        return None

def get_geojson_extents(geojson_path):
    """Extract the maximum extents (bounding box) from a geojson file."""
    with open(geojson_path, 'r') as f:
        geojson = json.load(f)
    
    # Initialize min/max values
    min_lon = float('inf')
    max_lon = float('-inf')
    min_lat = float('inf')
    max_lat = float('-inf')
    
    # Process all features
    for feature in geojson['features']:
        if feature['geometry']['type'] == 'Polygon':
            coordinates = feature['geometry']['coordinates'][0]  # First array contains exterior ring
            for lon, lat in coordinates:
                min_lon = min(min_lon, lon)
                max_lon = max(max_lon, lon)
                min_lat = min(min_lat, lat)
                max_lat = max(max_lat, lat)
    
    return {
        'min_lon': min_lon,
        'max_lon': max_lon,
        'min_lat': min_lat,
        'max_lat': max_lat
    }

def get_ai_reference_groups(geojson_path, ai_model='claude', researchFocus='', num_iterations=5):
    """Generate reference groups using AI based on the area defined in a geojson file.
    
    Runs multiple iterations and synthesizes the results into a final grouping.
    """
    # Get the extents
    extents = get_geojson_extents(geojson_path)
    output_dir = os.path.dirname(geojson_path)
    os.makedirs(output_dir, exist_ok=True)
    
    # Store all iteration results
    all_groups = []
    area_descriptions = []
    
    # First, get a description of the marine area
    area_prompt = f"""Given a marine area bounded by these coordinates:
Latitude: {extents['min_lat']}° to {extents['max_lat']}°
Longitude: {extents['min_lon']}° to {extents['max_lon']}°

Please analyze this marine area and provide a concise response in exactly this format:

REGION: [Name the specific marine regions covered by these coordinates]
ECOSYSTEM_TYPE: [List the primary ecosystem types present (e.g., tropical reef, temperate coastal)]
DESCRIPTION: [Provide a brief description focusing on key ecological characteristics]

Important:
- Keep each section concise and focused
- Use the exact format shown above with REGION:, ECOSYSTEM_TYPE:, and DESCRIPTION: labels
- Ensure each section is on its own line
- Do not include any other text or formatting"""

    area_description = ask_ai(area_prompt, ai_model)
    if isinstance(area_description, list) and len(area_description) > 0:
        area_description = area_description[0].text
        
    # Store the description as a class attribute
    get_ai_reference_groups.last_description = area_description

    # Load the expanded template as a reference
    try:
        with open('03_grouping_template_full.json', 'r') as f:
            expanded_template = json.load(f)
            expanded_groups = "\n".join([f"{list(group.keys())[0]}: {list(group.values())[0]}" for group in expanded_template])
    except:
        expanded_groups = ""

    # Parse the region and ecosystem type from the response
    region = ""
    ecosystem_type = ""
    if isinstance(area_description, str):
        region_match = re.search(r'REGION:\s*(.+?)\n', area_description)
        if region_match:
            region = region_match.group(1).strip()
        
        type_match = re.search(r'ECOSYSTEM_TYPE:\s*(.+?)\n', area_description)
        if type_match:
            ecosystem_type = type_match.group(1).strip()
            
        description_match = re.search(r'DESCRIPTION:\s*(.+?)$', area_description, re.DOTALL)
        if description_match:
            area_description = description_match.group(1).strip()

    # Run multiple iterations of group generation
    for i in range(num_iterations):
        logging.info(f"Running iteration {i+1}/{num_iterations}")
        
        groups_prompt = f"""Based on this marine area:
Region: {region}
Ecosystem Type: {ecosystem_type}
Description: {area_description}

I have an example template of marine functional groups. For this {ecosystem_type} ecosystem:

1. First, identify which of these template groups would be relevant:
{expanded_groups}

2. Then, considering the research focus: {researchFocus}

Please provide a refined list of forty to seventy functional groups that:
- Includes groups likely to exist in this ecosystem type
- If the research is focussed on specific species, these should have their own group
- Adds any location-specific groups not in the template
- Adjusts group descriptions to match local conditions
- Provides higher resolution for groups related to the research focus
- Ensures coverage of all major trophic levels and habitats
- Is as detailed as possible to not miss important ecological interactions

Aim to have 40 distinct groups and return the groups in this exact JSON format:
[
    {{"Group1": "Description1"}},
    {{"Group2": "Description2"}}
]

The descriptions should explain the group's specific role in this {ecosystem_type} ecosystem."""

        groups_response = ask_ai(groups_prompt, ai_model)
        if isinstance(groups_response, list) and len(groups_response) > 0:
            groups_response = groups_response[0].text

        # Extract JSON from the response
        json_match = re.search(r'\[.*\]', groups_response, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            try:
                groups = json.loads(json_str)
                all_groups.append(groups)
            except json.JSONDecodeError as e:
                logging.error(f"Error decoding JSON response in iteration {i+1}: {e}")
                continue

    # Now synthesize the results
    synthesis_prompt = f"""I have {num_iterations} different proposed groupings for an EwE model of this marine ecosystem:

{json.dumps(all_groups, indent=2)}

Please analyze these groupings and create a final consensus grouping that:
1. Identifies groups that appear consistently across iterations
2. Resolves any conflicts or variations in group definitions
3. Ensures comprehensive coverage of all trophic levels and habitats
4. Maintains appropriate resolution based on the research focus: {researchFocus}

Return the final consensus grouping in the exact same JSON format as the input groupings:
[
    {{"Group1": "Description1"}},
    {{"Group2": "Description2"}}
]"""

    # Try synthesis multiple times if needed
    max_synthesis_attempts = 3
    for attempt in range(max_synthesis_attempts):
        try:
            synthesis_response = ask_ai(synthesis_prompt, ai_model)
            if isinstance(synthesis_response, list) and len(synthesis_response) > 0:
                synthesis_response = synthesis_response[0].text

            # Extract JSON from the synthesis response
            json_match = re.search(r'\[.*\]', synthesis_response, re.DOTALL)
            if not json_match:
                if attempt < max_synthesis_attempts - 1:
                    logging.warning(f"No valid JSON found in synthesis response (attempt {attempt + 1}/{max_synthesis_attempts}). Retrying...")
                    continue
                logging.error("No valid JSON found in synthesis response after all attempts")
                raise ValueError("Failed to generate valid reference groups")

            json_str = json_match.group(0)
            try:
                final_groups = json.loads(json_str)
                
                # Save the ecosystem description to ai_config.json
                ai_config_path = os.path.join(output_dir, 'ai_config.json')
                with open(ai_config_path, 'w') as f:
                    json.dump({
                        'ecosystemDescription': area_description,
                        'groupSpeciesAI': ai_model,
                        'iterations': num_iterations,
                        'allGroupings': all_groups
                    }, f, indent=2)

                # Save the final groups to a file
                output_path = os.path.join(output_dir, 'ai_reference_groups.json')
                with open(output_path, 'w') as f:
                    json.dump(final_groups, f, indent=2)
                
                # Convert to the format expected by load_reference_groups
                group_names = []
                group_dict = {}
                for item in final_groups:
                    group_dict.update(item)
                    group_names.extend(item.keys())
                
                return group_names, group_dict
            except json.JSONDecodeError as e:
                if attempt < max_synthesis_attempts - 1:
                    logging.warning(f"Error decoding synthesis response (attempt {attempt + 1}/{max_synthesis_attempts}): {e}. Retrying...")
                    continue
                logging.error(f"Error decoding synthesis response after all attempts: {e}")
                raise

        except Exception as e:
            if attempt < max_synthesis_attempts - 1:
                logging.warning(f"Error in synthesis attempt {attempt + 1}/{max_synthesis_attempts}: {str(e)}. Retrying...")
                continue
            logging.error(f"Error in synthesis after all attempts: {str(e)}")
            raise

# Initialize the class attribute
get_ai_reference_groups.last_description = None

def load_species_data(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Remove or replace invalid control characters
    content = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', content)
    
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON: {str(e)}")
        raise

def load_json_reference_groups(file_path):
    encodings = ['utf-8', 'latin-1', 'ascii']
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                data = json.load(f)
            
            if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
                raise ValueError("JSON file should contain a list of dictionaries")
            
            group_dict = {}
            for item in data:
                group_dict.update(item)
            
            group_names = list(group_dict.keys())
            
            print(f"Number of groups: {len(group_names)}")
            print(f"Sample of group names: {group_names[:5]}")
            
            return group_names, group_dict
        except UnicodeDecodeError:
            continue
        except json.JSONDecodeError as e:
            logging.error(f"Error decoding JSON with {encoding} encoding: {str(e)}")
            continue
    
    raise ValueError(f"Unable to decode the JSON file {file_path} with any of the attempted encodings")

def load_ai_config(output_dir):
    config_path = os.path.join(output_dir, 'ai_config.json')
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.warning(f"AI config file not found at {config_path}. Using default settings.")
        return {
            'groupSpeciesAI': 'claude',
            'groupingTemplate': {
                'type': 'default',
                'path': '03_grouping_template.json'
            }
        }

def get_ecobase_groups(research_focus, ecobase_search_term):
    if not ECOBASE_AVAILABLE:
        logging.warning("EcoBase functionality not available")
        return None
        
    search_query = f"{research_focus} {ecobase_search_term}".strip()
    groups = get_single_model_groups(search_query)
    if groups:
        # Remove duplicates
        unique_groups = list(set(groups))
        logging.info(f"Found {len(unique_groups)} unique EcoBase groups for query: {search_query}")
        return unique_groups
    return None

def read_research_focus(model_dir):
    """Read research focus from ai_config.json"""
    ai_config_path = os.path.join(model_dir, 'ai_config.json')
    try:
        with open(ai_config_path, 'r') as f:
            config = json.load(f)
            return config.get('researchFocus', '')
    except FileNotFoundError:
        logging.warning(f"ai_config.json not found in {model_dir}")
        return ''

def load_reference_groups(output_dir, json_file_path):
    ai_config = load_ai_config(output_dir)
    grouping_template = ai_config.get('groupingTemplate', {})
    ai_model = ai_config.get('groupSpeciesAI', 'claude')
    researchFocus = ai_config.get('researchFocus', '')
    template_type = grouping_template.get('type', 'default')
    
    research_focus = read_research_focus(output_dir)
    
    if template_type == 'ecobase':
        ecobase_search_term = grouping_template.get('ecobase_search_term', '')
        ecobase_groups = get_ecobase_groups(research_focus, ecobase_search_term)
        if ecobase_groups:
            logging.info(f"Using EcoBase model with {len(ecobase_groups)} groups")
            return ecobase_groups
        else:
            logging.warning("No matching EcoBase groups found. Using JSON file as fallback.")
    elif template_type == 'geojson':
        # Use the user_input.geojson file from the model directory
        geojson_path = os.path.join(output_dir, 'user_input.geojson')
        if os.path.exists(geojson_path):
            try:
                logging.info(f"Generating reference groups from {geojson_path} using {ai_model}")
                return get_ai_reference_groups(geojson_path, ai_model, researchFocus)
            except Exception as e:
                logging.error(f"Error generating AI reference groups: {e}")
                logging.warning("Using JSON file as fallback.")
    
    logging.info("Using JSON file for reference groups.")
    group_names, group_dict = load_json_reference_groups(json_file_path)
    return group_names, group_dict

def preprocess_data(data):
    cleaned_data = []
    for species, info in data.items():
        # Get taxonomy data
        taxonomy = info.get('taxonomy', {})
        # Filter out None, NaN, and empty string values
        cleaned_item = {k: v for k, v in taxonomy.items() 
                      if v is not None 
                      and str(v).strip() != '' 
                      and str(v).lower() != 'nan'}
        
        if not cleaned_item:  # Skip if no valid taxonomy data
            logging.warning(f"Skipping species {species} - no valid taxonomy data")
            continue
            
        # Add species name
        cleaned_item['Species'] = species
        
        # Add ecology data if available
        ecology = info.get('ecology', {})
        if ecology:
            cleaned_item['Ecology'] = ecology
            
        # Add diet data if available
        diet = info.get('diet', {})
        if diet:
            cleaned_item['diet'] = diet
        
        cleaned_data.append(cleaned_item)
    return cleaned_data

def create_hierarchical_json(data):
    hierarchical = {}
    for item in data:
        current = hierarchical
        for level in ['Kingdom', 'Phylum', 'Class', 'Order', 'Family', 'Genus', 'Species']:
            if level in item and item[level] is not None and str(item[level]).lower() != 'nan':
                value = str(item[level]).strip()
                if value:  # Only process non-empty strings
                    if value not in current:
                        current[value] = {}
                    current = current[value]
        current['specCode'] = item.get('SpecCode', 'Unknown')
        if 'Ecology' in item:
            current['ecology'] = item['Ecology']
        if 'diet' in item:
            current['diet'] = item['diet']
    return hierarchical

@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=4, max=60), 
       retry=retry_if_exception_type((requests.exceptions.RequestException, json.JSONDecodeError, TypeError)))
def get_taxonomic_classification(group_name, ai_model):
    """Get the most specific taxonomic classification that covers a functional group"""
    prompt = f"""For the marine functional group '{group_name}', determine the most specific taxonomic classification that:
1. Includes ALL species that would belong to this group
2. Excludes species that would NOT belong to this group
3. Uses standard taxonomic ranks (Kingdom, Phylum, Class, Order, Family, Genus)

For example:
- "Abalone" would return "Family: Haliotidae" as this family includes all abalone species and nothing else
- "Baleen whales" would return "Suborder: Mysticeti" as this includes all baleen whales
- "Piscivores" would return "None" as this is a feeding strategy that occurs across many unrelated taxa

Return ONLY the classification in this format:
"Rank: Name" (e.g., "Family: Haliotidae")
Or "None" if no single taxonomic group applies."""

    response = ask_ai(prompt, ai_model)
    if isinstance(response, list) and len(response) > 0:
        response = response[0].text.strip()
        if response.lower() == "none":
            return None
        if ":" in response:
            rank, name = response.split(":", 1)
            return {"rank": rank.strip(), "name": name.strip()}
    return None

@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=4, max=60), 
       retry=retry_if_exception_type((requests.exceptions.RequestException, json.JSONDecodeError, TypeError)))
def process_taxa_chunk(taxa_chunk, rank, reference_group_dict, research_focus, ai_model):
    """Process a small chunk of taxa and return their assignments"""
    logging.info(f"Starting to process chunk with taxa: {taxa_chunk}")
    newline = "\n"

    # First, get taxonomic classifications for all groups if not already cached
    if not hasattr(process_taxa_chunk, 'taxonomic_cache'):
        process_taxa_chunk.taxonomic_cache = {}
        for group in reference_group_dict.keys():
            if group not in process_taxa_chunk.taxonomic_cache:
                classification = get_taxonomic_classification(group, ai_model)
                process_taxa_chunk.taxonomic_cache[group] = classification
                logging.info(f"Group '{group}' taxonomic classification: {classification}")
    
    research_focus_guidance = ""
    if research_focus:
        research_focus_guidance = f"""
Special consideration for research focus:
The model's research focus is: {research_focus}
When classifying taxa that are related to this research focus:
- Consider creating more detailed, finer resolution groupings
- Keep species of particular interest as individual functional groups
- For taxa that interact significantly with the focal species/groups, maintain higher resolution groupings
- For other taxa, broader functional groups may be appropriate"""

    available_groups = "\n".join([f"{group}: {description}" for group, description in reference_group_dict.items()])

    prompt = f"""You are classifying marine organisms into functional groups for an Ecopath with Ecosim (EwE) model. Functional groups can be individual species or groups of species that perform a similar function in the ecosystem, i.e. have approximately the same growth rates, consumption rates, diets, habitats, and predators. They should be based on species that occupy similar niches, rather than of similar taxonomic groups.{research_focus_guidance}

Examine these taxa at the {rank} level and assign each to an ecological functional group.

Rules for assignment:
- If a taxon contains members with different feeding strategies or trophic levels, assign it to 'RESOLVE'
- Examples requiring 'RESOLVE':
  * A phylum containing both filter feeders and predators
  * An order with both herbivores and carnivores
  * A class with species across multiple trophic levels
- If all members of a taxon share similar ecological roles, assign to an appropriate group
- Only consider the adult phase of the organisms, larvae and juveniles will be organized separately
- Only assign a definite group if you are confident ALL members of that taxon belong to that group
- If the members of the taxon do not fit into any of the exising groups, assign them to a group that is not already present. 

Taxa to classify:
{newline.join(taxa_chunk)}

Available ecological groups (name: description):
{available_groups}

Return only a JSON object with taxa as keys and assigned groups as values. Example format:
{{
    "Taxon1": "Group1",
    "Taxon2": "RESOLVE",
    "Taxon3": "Group2"
}}"""

    try:
        logging.info("Sending request to AI model...")
        response = ask_ai(prompt, ai_model)
        logging.info(f"Received response type: {type(response)}")
        logging.info(f"Response length: {len(str(response))}")
        
        logging.info("Attempting to extract JSON from response...")
        json_match = re.search(r'\{.*\}', str(response), re.DOTALL)
        if not json_match:
            error_msg = f"No valid JSON found in the response: {response}"
            logging.error(error_msg)
            return {}
            
        json_str = json_match.group(0)
        logging.info(f"Extracted JSON string: {json_str}")
        
        try:
            result = json.loads(json_str)
            logging.info(f"Successfully parsed JSON with {len(result)} assignments")
            return result
        except json.JSONDecodeError as e:
            logging.error(f"JSON decode error: {str(e)}")
            raise
    except TypeError as e:
        logging.error(f"TypeError in process_taxa_chunk: {str(e)}")
        logging.error(f"Response type: {type(response)}")
        logging.error(f"Response content: {response}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error in process_taxa_chunk: {str(e)}")
        logging.error(f"Error type: {type(e)}")
        raise

@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=4, max=60), 
       retry=retry_if_exception_type((requests.exceptions.RequestException, json.JSONDecodeError, TypeError)))
def assign_groups_with_retry(taxa, rank, reference_group_dict, is_leaf_level, research_focus=None, ai_model='claude'):
    """Process taxa in chunks of 5 elements"""
    # Filter out None and NaN values
    filtered_taxa = [t for t in taxa if t is not None and str(t).lower() != 'nan']
    if len(filtered_taxa) != len(taxa):
        logging.info(f"Filtered out {len(taxa) - len(filtered_taxa)} invalid taxa entries")
    
    if not filtered_taxa:
        logging.warning("No valid taxa to process after filtering")
        return {}
    
    chunk_size = 5
    all_assignments = {}
    
    total_chunks = (len(filtered_taxa) + chunk_size - 1) // chunk_size
    logging.info(f"Starting to process {len(filtered_taxa)} taxa in {total_chunks} chunks")
    
    # Process taxa in chunks
    for i in range(0, len(filtered_taxa), chunk_size):
        chunk = filtered_taxa[i:i + chunk_size]
        chunk_num = i//chunk_size + 1
        logging.info(f"Processing chunk {chunk_num} of {total_chunks} ({len(chunk)} taxa)")
        
        try:
            chunk_assignments = process_taxa_chunk(chunk, rank, reference_group_dict, research_focus, ai_model)
            logging.info(f"Successfully processed chunk {chunk_num} with {len(chunk_assignments)} assignments")
            all_assignments.update(chunk_assignments)
        except Exception as e:
            logging.error(f"Error processing chunk {chunk_num}: {str(e)}")
            logging.error(f"Chunk content: {chunk}")
            raise
    
    return all_assignments

# Replace the original assign_groups function with this new one
assign_groups = assign_groups_with_retry

def save_assignments(assignments, file_path):
    # Get the directory path to locate species data file
    output_dir = os.path.dirname(file_path)
    species_data_file = os.path.join(output_dir, "02_species_data.json")
    
    try:
        # Load the complete species data
        with open(species_data_file, 'r') as f:
            all_species_data = json.load(f)
        
        # Create new assignments with complete species data
        complete_assignments = {}
        for group, group_species in assignments.items():
            complete_assignments[group] = {}
            for species_name, current_data in group_species.items():
                # If this species exists in the species data file, use that data
                if species_name in all_species_data:
                    # Ensure we preserve the complete data structure including all diet information
                    species_data = all_species_data[species_name]
                    # Make sure we have all the necessary keys
                    if 'taxonomy' not in species_data:
                        species_data['taxonomy'] = {}
                    if 'ecology' not in species_data:
                        species_data['ecology'] = {}
                    if 'diet' not in species_data:
                        species_data['diet'] = {
                            'SeaLifeBase': [],
                            'FishBase': [],
                            'GLOBI': {'interactions': []}
                        }
                    elif 'GLOBI' not in species_data['diet']:
                        species_data['diet']['GLOBI'] = {'interactions': []}
                    
                    complete_assignments[group][species_name] = species_data
                else:
                    # If not found, keep whatever data we currently have
                    complete_assignments[group][species_name] = current_data
        
        # Save the complete assignments
        with open(file_path, 'w') as f:
            json.dump(complete_assignments, f, indent=2)
            
    except FileNotFoundError:
        logging.warning(f"Species data file not found at {species_data_file}, saving assignments without complete species data")
        with open(file_path, 'w') as f:
            json.dump(assignments, f, indent=2)

def load_assignments(file_path):
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def write_json_to_file(data, file_path):
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2)
