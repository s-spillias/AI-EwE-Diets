import os
import argparse
from group_species_utils import get_ai_reference_groups, read_research_focus

def main():
    parser = argparse.ArgumentParser(description='Generate AI reference groups from geojson')
    parser.add_argument('--output_dir', required=True, help='Output directory path')
    args = parser.parse_args()

    # Get paths
    geojson_path = os.path.join(args.output_dir, 'user_input.geojson')
    if not os.path.exists(geojson_path):
        print(f"Error: GeoJSON file not found at {geojson_path}")
        return False

    # Get research focus from ai_config.json
    research_focus = read_research_focus(args.output_dir)

    # Get AI model from ai_config.json
    ai_config_path = os.path.join(args.output_dir, 'ai_config.json')
    ai_model = 'gemini'  # default
    config = {}
    if os.path.exists(ai_config_path):
        import json
        with open(ai_config_path, 'r') as f:
            config = json.load(f)
            ai_model = config.get('groupSpeciesAI', 'gemini')

    try:
        # Generate AI reference groups
        print(f"Generating AI reference groups using {ai_model}...")
        group_names, group_dict = get_ai_reference_groups(geojson_path, ai_model, research_focus)
        
        # Save to 03_grouping_template.json in the output directory
        output_path = os.path.join(args.output_dir, '03_grouping_template.json')
        groups_list = [{k: v} for k, v in group_dict.items()]
        import json
        with open(output_path, 'w') as f:
            json.dump(groups_list, f, indent=2)
        
        # Save the ecosystem description to ai_config.json if available
        if hasattr(get_ai_reference_groups, 'last_description'):
            config['ecosystemDescription'] = get_ai_reference_groups.last_description
            with open(ai_config_path, 'w') as f:
                json.dump(config, f, indent=2)
            print("Ecosystem description saved to ai_config.json")
        
        print(f"Successfully generated {len(group_names)} groups")
        print(f"Groups saved to: {output_path}")
        return True
    except Exception as e:
        print(f"Error generating AI reference groups: {e}")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
