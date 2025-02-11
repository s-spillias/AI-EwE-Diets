import requests
import pandas as pd
import json
from pathlib import Path
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EcoBaseHarvester:
    """Class to harvest EwE model parameters from EcoBase database"""
    
    def __init__(self):
        self.base_url = "https://sirs.agrocampus-ouest.fr/EcoBase/api/v1"
        self.output_dir = Path("data/ecobase_models")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def get_model_list(self):
        """Retrieve list of available models from EcoBase"""
        try:
            response = requests.get(f"{self.base_url}/models")
            if response.status_code == 200:
                models = response.json()
                df = pd.DataFrame(models)
                df.to_csv(self.output_dir / "model_list.csv", index=False)
                logger.info(f"Retrieved {len(models)} models")
                return df
            else:
                logger.error(f"Failed to get model list: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error getting model list: {str(e)}")
            return None

    def get_model_parameters(self, model_id):
        """Retrieve parameters for a specific model"""
        try:
            response = requests.get(f"{self.base_url}/models/{model_id}/parameters")
            if response.status_code == 200:
                params = response.json()
                
                # Save raw parameters
                with open(self.output_dir / f"model_{model_id}_params.json", 'w') as f:
                    json.dump(params, f, indent=2)
                
                # Extract key parameters into structured format
                structured_params = {
                    'biomass': [],
                    'pb_ratio': [],  # Production/Biomass ratio
                    'qb_ratio': [],  # Consumption/Biomass ratio
                    'ee': [],        # Ecotrophic efficiency
                    'diet_matrix': []
                }
                
                # Process parameters based on their type
                for param in params:
                    param_type = param.get('type')
                    if param_type in structured_params:
                        structured_params[param_type].append({
                            'group': param.get('group'),
                            'value': param.get('value'),
                            'unit': param.get('unit')
                        })
                
                # Convert to DataFrames and save
                for param_type, data in structured_params.items():
                    if data:
                        df = pd.DataFrame(data)
                        df.to_csv(self.output_dir / f"model_{model_id}_{param_type}.csv", 
                                index=False)
                
                logger.info(f"Successfully retrieved parameters for model {model_id}")
                return structured_params
            else:
                logger.error(f"Failed to get parameters for model {model_id}: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error getting parameters for model {model_id}: {str(e)}")
            return None

    def search_models(self, ecosystem_type=None, region=None, year=None):
        """Search for models based on criteria"""
        try:
            params = {
                'ecosystem_type': ecosystem_type,
                'region': region,
                'year': year
            }
            # Remove None values
            params = {k: v for k, v in params.items() if v is not None}
            
            response = requests.get(f"{self.base_url}/models/search", params=params)
            if response.status_code == 200:
                models = response.json()
                df = pd.DataFrame(models)
                search_desc = "_".join(f"{k}_{v}" for k, v in params.items())
                if search_desc:
                    output_file = f"model_search_{search_desc}.csv"
                else:
                    output_file = "model_search_all.csv"
                df.to_csv(self.output_dir / output_file, index=False)
                logger.info(f"Found {len(models)} models matching criteria")
                return df
            else:
                logger.error(f"Search failed: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error searching models: {str(e)}")
            return None

def main():
    harvester = EcoBaseHarvester()
    
    # Get list of all models
    models_df = harvester.get_model_list()
    if models_df is not None:
        logger.info("Retrieved model list successfully")
        
        # Example: Search for marine models in a specific region
        marine_models = harvester.search_models(
            ecosystem_type="Marine",
            region="Pacific Ocean"
        )
        
        if marine_models is not None:
            # Get parameters for first 5 marine models
            for model_id in marine_models['model_id'].head():
                params = harvester.get_model_parameters(model_id)
                if params:
                    logger.info(f"Retrieved parameters for model {model_id}")

if __name__ == "__main__":
    main()
