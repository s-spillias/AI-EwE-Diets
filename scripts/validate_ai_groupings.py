import os
import json
import argparse
from datetime import datetime
from collections import defaultdict
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import geopandas as gpd
import tempfile
import zipfile
from group_species_utils import get_ai_reference_groups

def shapefile_to_geojson(shapefile_path, geojson_path):
    """Convert shapefile to GeoJSON format."""
    try:
        gdf = gpd.read_file(shapefile_path)
        gdf.to_file(geojson_path, driver='GeoJSON')
        return True
    except Exception as e:
        print(f"Error converting shapefile to GeoJSON: {str(e)}")
        return False

def extract_and_convert_shapefile(zip_path, output_dir):
    """Extract shapefile from zip and convert to GeoJSON."""
    geojson_path = os.path.join(output_dir, 'user_input.geojson')
    
    with tempfile.TemporaryDirectory() as tmpdirname:
        # Extract zip file
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(tmpdirname)
        
        # Find the .shp file
        shp_file = next((f for f in os.listdir(tmpdirname) if f.endswith('.shp')), None)
        if shp_file:
            shapefile_path = os.path.join(tmpdirname, shp_file)
            if shapefile_to_geojson(shapefile_path, geojson_path):
                return geojson_path
    
    return None

def run_iterations(zip_path, output_dir, research_focus, n_iterations=5, ai_models=None):
    """Run multiple iterations of group generation with different AI models."""
    if ai_models is None:
        # Use all available models
        ai_models = ['claude', 'aws_claude', 'gemini', 'gemma2', 'gemma7', 'llama3', 'mixtral']
    
    results = defaultdict(list)
    ecosystem_descriptions = defaultdict(list)
    
    # Create timestamped report directory
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    report_dir = os.path.join(output_dir, 'reports', f'report_{timestamp}')
    os.makedirs(report_dir, exist_ok=True)
    
    # Convert shapefile to GeoJSON
    geojson_path = extract_and_convert_shapefile(zip_path, report_dir)
    if not geojson_path:
        print("Failed to convert shapefile to GeoJSON")
        return None, None, None
    
    # Run iterations for each AI model
    for ai_model in ai_models:
        print(f"\nRunning {n_iterations} iterations with {ai_model}...")
        for i in range(n_iterations):
            print(f"Iteration {i+1}/{n_iterations}")
            try:
                group_names, group_dict = get_ai_reference_groups(geojson_path, ai_model, research_focus)
                
                # Save the ecosystem description from the AI's first response
                if hasattr(get_ai_reference_groups, 'last_description'):
                    ecosystem_descriptions[ai_model].append({
                        'iteration': i+1,
                        'description': get_ai_reference_groups.last_description
                    })
                
                results[ai_model].append({
                    'iteration': i+1,
                    'groups': group_dict
                })
            except Exception as e:
                print(f"Error in iteration {i+1} with {ai_model}: {e}")
                continue
    
    return results, ecosystem_descriptions, report_dir

def analyze_consistency(results):
    """Analyze consistency of groupings across iterations and AI models."""
    if not results:
        return None, None
        
    # Collect all unique group names
    all_groups = set()
    for ai_model in results:
        for iteration in results[ai_model]:
            all_groups.update(iteration['groups'].keys())
    
    # Create a matrix to store group occurrence counts
    group_matrix = pd.DataFrame(0, 
                              index=sorted(all_groups),
                              columns=pd.MultiIndex.from_product([results.keys(), range(1, len(next(iter(results.values())))+1)],
                                                              names=['AI Model', 'Iteration']))
    
    # Fill the matrix
    for ai_model in results:
        for iteration in results[ai_model]:
            iter_num = iteration['iteration']
            for group in iteration['groups']:
                group_matrix.loc[group, (ai_model, iter_num)] = 1
    
    # Calculate consistency metrics
    consistency_data = []
    for group in all_groups:
        for ai_model in results:
            occurrences = sum(1 for iter_data in results[ai_model] if group in iter_data['groups'])
            consistency = occurrences / len(results[ai_model])
            consistency_data.append({
                'Group': group,
                'AI Model': ai_model,
                'Consistency': consistency
            })
    
    consistency_df = pd.DataFrame(consistency_data)
    
    return group_matrix, consistency_df

def generate_report(results, ecosystem_descriptions, group_matrix, consistency_df, report_dir):
    """Generate analysis report with visualizations."""
    # Save raw results
    with open(os.path.join(report_dir, 'raw_results.json'), 'w') as f:
        json.dump(results, f, indent=2)
    
    # Save ecosystem descriptions
    with open(os.path.join(report_dir, 'ecosystem_descriptions.json'), 'w') as f:
        json.dump(ecosystem_descriptions, f, indent=2)
    
    # Save consistency matrix
    group_matrix.to_csv(os.path.join(report_dir, 'group_matrix.csv'))
    consistency_df.to_csv(os.path.join(report_dir, 'grouping_consistency.csv'), index=False)
    
    # Create heatmap of group occurrences
    plt.figure(figsize=(15, 10))
    sns.heatmap(group_matrix, cmap='YlOrRd', cbar_kws={'label': 'Present (1) / Absent (0)'})
    plt.title('Group Occurrence Matrix')
    plt.tight_layout()
    plt.savefig(os.path.join(report_dir, 'group_matrix_heatmap.png'))
    plt.close()
    
    # Calculate summary statistics
    summary = {
        'total_unique_groups': len(group_matrix.index),
        'consistency_by_model': consistency_df.groupby('AI Model')['Consistency'].mean().to_dict(),
        'timestamp': datetime.now().isoformat()
    }
    
    with open(os.path.join(report_dir, 'summary.json'), 'w') as f:
        json.dump(summary, f, indent=2)
    
    return summary

def main():
    parser = argparse.ArgumentParser(description='Validate AI grouping consistency')
    parser.add_argument('--zip_path', help='Path to the shapefile zip file (optional, if not provided will run all regions)')
    parser.add_argument('--output_dir', help='Directory to store validation results (optional)')
    parser.add_argument('--iterations', type=int, default=5, help='Number of iterations per AI model')
    parser.add_argument('--research_focus', default='', help='Research focus for the model')
    parser.add_argument('--ai_models', nargs='+', 
                      default=['claude', 'aws_claude', 'gemini', 'gemma2', 'gemma7', 'llama3', 'mixtral'],
                      help='AI models to test')
    
    args = parser.parse_args()
    
    # Define regions to process
    regions = {
        'NorthernTerritory': 'Validation/NothernTerritory.zip',
        'SouthEastInshore': 'Validation/SouthEastInshore.zip',
        'SouthEastOffshore': 'Validation/SouthEastOffshore.zip'
    }
    
    # If no specific zip file is provided, process all regions
    if not args.zip_path:
        print("No specific shapefile provided. Processing all regions...")
        for region_name, zip_path in regions.items():
            print(f"\n=== Processing {region_name} ===")
            output_dir = args.output_dir or os.path.join('Validation', region_name)
            os.makedirs(output_dir, exist_ok=True)
            
            # Run iterations and analyze results
            results, ecosystem_descriptions, report_dir = run_iterations(
                zip_path,
                output_dir,
                args.research_focus,
                args.iterations,
                args.ai_models
            )
            
            if not results:
                print(f"No results generated for {region_name}. Skipping analysis.")
                continue
            
            # Analyze consistency
            group_matrix, consistency_df = analyze_consistency(results)
            
            if group_matrix is None or consistency_df is None:
                print(f"Error analyzing results for {region_name}. Skipping report generation.")
                continue
            
            # Generate report
            summary = generate_report(results, ecosystem_descriptions, group_matrix, consistency_df, report_dir)
            
            print(f"\nValidation complete for {region_name}!")
            print(f"Results saved in: {report_dir}")
            print("\nSummary:")
            print(f"Total unique groups: {summary['total_unique_groups']}")
            print("\nConsistency by model:")
            for model, score in summary['consistency_by_model'].items():
                print(f"{model}: {score:.2f}")
    else:
        # Process single specified zip file
        output_dir = args.output_dir or 'Validation'
        os.makedirs(output_dir, exist_ok=True)
        
        print(f"Starting validation with {args.iterations} iterations per AI model")
        print(f"AI models: {', '.join(args.ai_models)}")
        
        # Run iterations and analyze results
        results, ecosystem_descriptions, report_dir = run_iterations(
            args.zip_path,
            output_dir,
            args.research_focus,
            args.iterations,
            args.ai_models
        )
        
        if not results:
            print("No results generated. Exiting.")
            return
        
        # Analyze consistency
        group_matrix, consistency_df = analyze_consistency(results)
        
        if group_matrix is None or consistency_df is None:
            print("Error analyzing results. Exiting.")
            return
        
        # Generate report
        summary = generate_report(results, ecosystem_descriptions, group_matrix, consistency_df, report_dir)
        
        print("\nValidation complete!")
        print(f"Results saved in: {report_dir}")
        print("\nSummary:")
        print(f"Total unique groups: {summary['total_unique_groups']}")
        print("\nConsistency by model:")
        for model, score in summary['consistency_by_model'].items():
            print(f"{model}: {score:.2f}")

if __name__ == "__main__":
    main()
