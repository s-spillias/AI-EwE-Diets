import logging
import json
from ecobase_search import main as ecobase_search

def test_ecobase_search(research_focus):
    logging.info(f"Testing ecobase_search with research focus: {research_focus}")
    results = ecobase_search(query=research_focus)
    
    if results:
        logging.info("EcoBase search results:")
        logging.info(json.dumps(results, indent=2))
        
        if 'search_results' in results:
            group_names = []
            for result in results['search_results']:
                if isinstance(result, dict) and 'group_name' in result:
                    if isinstance(result['group_name'], dict) and '#text' in result['group_name']:
                        group_names.append(result['group_name']['#text'])
                    elif isinstance(result['group_name'], str):
                        group_names.append(result['group_name'])
            
            logging.info(f"Extracted group names: {group_names}")
        else:
            logging.warning("No 'search_results' found in the ecobase_search output")
    else:
        logging.warning("No results returned from ecobase_search")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_ecobase_search("Marine ecosystem in the Mediterranean Sea")
