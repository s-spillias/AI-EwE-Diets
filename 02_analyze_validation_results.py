import os
import sys
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
from scripts.validation_visualizations import generate_validation_figures
from scripts.analyze_timing import generate_timing_summary
from collections import Counter, defaultdict

def extract_species_assignments(group_dict):
    """Extract species to group assignments from nested dictionary structure"""
    species_to_group = {}
    
    def recurse_dict(d, group):
        for k, v in d.items():
            if isinstance(v, dict):
                if 'specCode' in v:  # This is a leaf node (species)
                    species_to_group[k] = group
                else:  # This is an internal node
                    recurse_dict(v, group)
            
    for group, species_data in group_dict.items():
        recurse_dict(species_data, group)
    
    return species_to_group

def analyze_group_consistency(iteration_dirs):
    """Analyze consistency of species groupings across iterations"""
    species_assignments = defaultdict(list)
    group_members = defaultdict(list)
    group_sizes = defaultdict(list)
    
    # Process each iteration
    valid_iterations = 0
    for dir_path in iteration_dirs:
        assignments_path = os.path.join(dir_path, '03_grouped_species_assignments.json')
        if os.path.exists(assignments_path):
            try:
                with open(assignments_path, 'r') as f:
                    group_dict = json.load(f)
                
                # Extract species to group assignments
                species_to_group = extract_species_assignments(group_dict)
                
                if not species_to_group:
                    print(f"    Warning: No species assignments found in {assignments_path}")
                    continue
                
                # Record assignments and track group sizes
                iteration_groups = defaultdict(set)
                for species, group in species_to_group.items():
                    species_assignments[species].append(group)
                    iteration_groups[group].add(species)
                
                # Record group memberships and sizes
                for group, members in iteration_groups.items():
                    group_members[group].append(members)
                    group_sizes[group].append(len(members))
                
                valid_iterations += 1
            except json.JSONDecodeError:
                print(f"    Warning: Invalid JSON in {assignments_path}")
            except Exception as e:
                print(f"    Warning: Error processing {assignments_path}: {str(e)}")
    
    if valid_iterations == 0:
        raise ValueError("No valid species assignments found in any iteration")
    
    # Analyze species consistency and group complexity
    consistency_metrics = {}
    for species, groups in species_assignments.items():
        unique_groups = list(set(groups))
        group_counts = Counter(groups)
        most_common = max(group_counts.items(), key=lambda x: x[1])
        consistency = most_common[1] / len(groups)
        
        consistency_metrics[species] = {
            'most_common_group': most_common[0],
            'consistency_score': consistency,
            'unique_groups': unique_groups,
            'group_counts': dict(group_counts),
            'num_different_groups': len(unique_groups),
            'total_iterations': len(groups)
        }
    
    # Analyze group stability and complexity
    group_stability = {}
    for group, member_sets in group_members.items():
        num_iterations = len(member_sets)
        if num_iterations < 2:
            continue
        
        # Calculate Jaccard similarities for all combinations of iterations
        similarities = []
        for i in range(num_iterations):
            for j in range(i+1, num_iterations):
                jaccard = len(member_sets[i] & member_sets[j]) / len(member_sets[i] | member_sets[j])
                similarities.append(jaccard)
        
        # Calculate group size statistics
        sizes = group_sizes[group]
        
        group_stability[group] = {
            'avg_jaccard_similarity': np.mean(similarities) if similarities else 1.0,
            'total_unique_members': len(set().union(*member_sets)),
            'min_size': min(sizes),
            'max_size': max(sizes),
            'avg_size': np.mean(sizes),
            'size_std': np.std(sizes),
            'member_sets': member_sets
        }
    
    return consistency_metrics, group_stability

def calculate_stability_score(values):
    """Calculate stability score for a set of values.
    
    The score is based on 1 minus the average normalized absolute deviation from the mean.
    A score of 1 indicates perfect stability (all values identical),
    while a score approaching 0 indicates high instability.
    """
    if not values or all(v == 0 for v in values):
        return 1.0
        
    mean_val = np.mean(values)
    max_val = max(values)
    
    if max_val == 0:
        return 1.0
        
    # Calculate normalized deviations from mean
    deviations = [abs(v - mean_val) / max_val for v in values]
    
    # Average the deviations and invert so 1 = stable
    return 1 - np.mean(deviations)

def analyze_diet_matrices(iteration_dirs):
    """Analyze diet matrices across iterations"""
    all_matrices = []
    predator_prey_pairs = set()
    
    # Collect all matrices and unique predator-prey pairs
    for dir_path in iteration_dirs:
        matrix_path = os.path.join(dir_path, '05_diet_matrix.csv')
        if os.path.exists(matrix_path):
            matrix = pd.read_csv(matrix_path, index_col=0)
            all_matrices.append(matrix)
            
            # Record non-zero predator-prey interactions
            for pred in matrix.index:
                for prey in matrix.columns:
                    if matrix.at[pred, prey] > 0:
                        predator_prey_pairs.add((pred, prey))
    
    if not all_matrices:
        raise ValueError("No diet matrices found in the iteration directories")
    
    # Analyze consistency of predator-prey relationships
    interaction_consistency = {}
    for pred, prey in predator_prey_pairs:
        values = []
        for matrix in all_matrices:
            if pred in matrix.index and prey in matrix.columns:
                values.append(matrix.at[pred, prey])
            else:
                values.append(0)
        
        if values:
            # Calculate stability score
            stability_score = calculate_stability_score(values)
            mean_val = np.mean(values)
            
            # Print analysis
            print(f"\nValues for {pred} -> {prey}:")
            print(f"Raw values: {values}")
            print(f"Mean: {mean_val:.3f}")
            print(f"Stability score: {stability_score:.3f} (1=stable, 0=unstable)")
            
            interaction_consistency[(pred, prey)] = {
                'mean': mean_val,
                'stability_score': stability_score,
                'raw_values': values
            }
    
    return interaction_consistency

def create_diet_interaction_heatmap(interaction_consistency, output_path, region_name=None):
    """Create a heatmap of diet interactions with mean values and stability-based colors"""
    # Extract unique predators and prey
    predators = set()
    prey = set()
    for (pred, pr) in interaction_consistency.keys():
        predators.add(pred)
        prey.add(pr)
    
    # Create matrices for mean values and stability scores
    predators = sorted(list(predators))
    prey = sorted(list(prey))
    mean_matrix = np.zeros((len(predators), len(prey)))
    stability_matrix = np.zeros((len(predators), len(prey)))
    
    # Fill matrices
    for i, pred in enumerate(predators):
        for j, pr in enumerate(prey):
            if (pred, pr) in interaction_consistency:
                stats = interaction_consistency[(pred, pr)]
                mean_matrix[i, j] = stats['mean']
                stability_matrix[i, j] = stats['stability_score']
    
    # Create figure and axis
    fig = plt.figure(figsize=(15, 10))
    ax = plt.gca()
    
    # Create heatmap
    sns.heatmap(mean_matrix, 
                xticklabels=prey, 
                yticklabels=predators,
                cmap='YlOrRd',  # Color based on mean values
                annot=True,     # Show mean values in cells
                fmt='.2f',      # Format mean values to 2 decimal places
                alpha=0.7,      # Make base colors slightly transparent
                cbar_kws={'label': 'Mean Diet Proportion'},
                ax=ax)
    
    # Add stability score through cell border colors
    if stability_matrix.any():
        norm = plt.Normalize(vmin=0, vmax=stability_matrix.max())
        
        # Add colored borders based on stability score
        for i in range(len(predators)):
            for j in range(len(prey)):
                if mean_matrix[i, j] > 0:
                    color = plt.cm.viridis(norm(stability_matrix[i, j]))
                    plt.plot([j, j+1], [i, i], color=color, linewidth=2)
                    plt.plot([j, j+1], [i+1, i+1], color=color, linewidth=2)
                    plt.plot([j, j], [i, i+1], color=color, linewidth=2)
                    plt.plot([j+1, j+1], [i, i+1], color=color, linewidth=2)
        
        # Add a second colorbar for stability
        ax2 = fig.add_axes([0.95, 0.15, 0.03, 0.7])
        cb2 = plt.colorbar(plt.cm.ScalarMappable(norm=norm, cmap='viridis'), 
                          cax=ax2, label='Stability Score (1=stable, 0=unstable)')
    
    if region_name:
        plt.title(f'Diet Interaction Matrix - {region_name}\nCell Values: Mean Diet Proportion\nCell Borders: Stability')
    else:
        plt.title('Diet Interaction Matrix\nCell Values: Mean Diet Proportion\nCell Borders: Stability')
    
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path, bbox_inches='tight', dpi=300)
        plt.close()
    
    return fig, ax

def create_combined_heatmap(results, output_path):
    """Create a combined figure with heatmaps from multiple regions"""
    # Filter results to only those with diet interaction data
    diet_results = [r for r in results if 'interaction_consistency' in r]
    
    if not diet_results:
        print("No diet interaction data available for heatmap generation")
        return
        
    fig, axes = plt.subplots(1, len(diet_results), figsize=(24, 8))
    if len(diet_results) == 1:
        axes = [axes]  # Make axes iterable when only one subplot
    
    # Create matrices for all regions first to get global normalization
    all_matrices = []
    for result in diet_results:
        interaction_consistency = result['interaction_consistency']
        predators = sorted(list({pred for pred, _ in interaction_consistency.keys()}))
        prey = sorted(list({pr for _, pr in interaction_consistency.keys()}))
        stability_matrix = np.zeros((len(predators), len(prey)))
        
        for i, pred in enumerate(predators):
            for j, pr in enumerate(prey):
                if (pred, pr) in interaction_consistency:
                    stability_matrix[i, j] = interaction_consistency[(pred, pr)]['stability_score']
        
        # Print stability statistics
        region_name = result['name'].replace('_', ' ')
        print(f"\nStability statistics for {region_name}:")
        stability_values = stability_matrix[stability_matrix > 0]
        if len(stability_values) > 0:
            print(f"Min stability score: {np.min(stability_values):.3f}")
            print(f"Max stability score: {np.max(stability_values):.3f}")
            print(f"Mean stability score: {np.mean(stability_values):.3f}")
            print(f"Median stability score: {np.median(stability_values):.3f}")
            print("\nLeast stable interactions (highest scores):")
            high_scores = []
            for i, pred in enumerate(predators):
                for j, pr in enumerate(prey):
                    if stability_matrix[i, j] > 0:
                        high_scores.append((pred, pr, stability_matrix[i, j]))
            for pred, pr, score in sorted(high_scores, key=lambda x: x[2], reverse=True)[:5]:
                print(f"{pred} -> {pr}: stability score = {score:.3f}")
                stats = interaction_consistency[(pred, pr)]
                print(f"  Raw values: {stats['raw_values']}")
        
        if stability_matrix.any():
            all_matrices.append(stability_matrix[stability_matrix > 0])
    
    if all_matrices:
        stability_min = 0  # Start from 0 for better interpretation
        stability_max = max(np.max(m) for m in all_matrices)
        stability_norm = plt.Normalize(vmin=stability_min, vmax=stability_max)
    else:
        stability_norm = plt.Normalize(vmin=0, vmax=1)  # Default if no data
    
    # Create heatmaps
    for idx, result in enumerate(diet_results):
        ax = axes[idx]
        interaction_consistency = result['interaction_consistency']
        region_name = result['name'].replace('_', ' ')
        
        predators = sorted(list({pred for pred, _ in interaction_consistency.keys()}))
        prey = sorted(list({pr for _, pr in interaction_consistency.keys()}))
        mean_matrix = np.zeros((len(predators), len(prey)))
        stability_matrix = np.zeros((len(predators), len(prey)))
        
        for i, pred in enumerate(predators):
            for j, pr in enumerate(prey):
                if (pred, pr) in interaction_consistency:
                    stats = interaction_consistency[(pred, pr)]
                    mean_matrix[i, j] = stats['mean']
                    stability_matrix[i, j] = stats['stability_score']
        
        mask = (mean_matrix == 0) & (stability_matrix == 0)
        
        sns.heatmap(stability_matrix, 
                   xticklabels=prey, 
                   yticklabels=predators,
                   cmap='viridis',
                   norm=stability_norm,
                   mask=mask,
                   annot=False,
                   cbar_kws={'label': 'Stability Score (1=stable, 0=unstable)'},
                   ax=ax)
        
        ax.patch.set_facecolor('white')
        ax.set_title(f'Diet Interaction Matrix - {region_name}')
        plt.setp(ax.get_xticklabels(), rotation=45, ha='right')
    
    plt.tight_layout()
    plt.savefig(output_path, bbox_inches='tight', dpi=300)
    plt.close()

def analyze_region(base_name):
    """Analyze validation results for a specific region"""
    models_dir = 'MODELS'
    
    print(f"\nAnalyzing {base_name}...")
    
    # Find validation iteration directories
    group_iteration_dirs = []
    matrix_iteration_dirs = []
    incomplete_iterations = []
    
    region_dir = os.path.join(models_dir, base_name)
    if not os.path.exists(region_dir):
        print(f"  Error: Region directory {region_dir} not found")
        return None
        
    for dir_name in os.listdir(region_dir):
        if dir_name.startswith(base_name) and dir_name != f"{base_name}_base" and "_" in dir_name:
            full_path = os.path.join(region_dir, dir_name)
            if os.path.isdir(full_path):
                has_matrix = os.path.exists(os.path.join(full_path, '05_diet_matrix.csv'))
                has_groups = os.path.exists(os.path.join(full_path, '03_grouped_species_assignments.json'))
                
                if has_groups:
                    group_iteration_dirs.append(full_path)
                if has_matrix:
                    matrix_iteration_dirs.append(full_path)
                
                missing = []
                if not has_matrix:
                    missing.append("diet matrix")
                if not has_groups:
                    missing.append("species groups")
                if missing:
                    incomplete_iterations.append((dir_name, ", ".join(missing)))
    
    if not group_iteration_dirs:
        print(f"  Error: No iterations with species groupings found")
        if incomplete_iterations:
            print("  Incomplete iterations:")
            for name, missing in incomplete_iterations:
                print(f"    - {name}: missing {missing}")
        return None
    
    print(f"  Found {len(group_iteration_dirs)} iterations with species groupings")
    print(f"  Found {len(matrix_iteration_dirs)} iterations with diet matrices")
    if incomplete_iterations:
        print(f"  Found {len(incomplete_iterations)} incomplete iterations")
    
    result = {
        'name': base_name,
        'num_group_iterations': len(group_iteration_dirs),
        'num_matrix_iterations': len(matrix_iteration_dirs)
    }

    try:
        # Analyze group consistency
        print("  Analyzing group consistency...")
        consistency_metrics, group_stability = analyze_group_consistency(group_iteration_dirs)
        print(f"    Found {len(group_stability)} groups")
        print(f"    Analyzed {len(consistency_metrics)} species")
        result.update({
            'consistency_metrics': consistency_metrics,
            'group_stability': group_stability
        })
        
        # Analyze diet interactions if available
        if matrix_iteration_dirs:
            print("  Analyzing diet interactions...")
            interaction_consistency = analyze_diet_matrices(matrix_iteration_dirs)
            num_interactions = len(interaction_consistency)
            print(f"    Found {num_interactions} diet interactions")
            result['interaction_consistency'] = interaction_consistency
        
    except Exception as e:
        print(f"  Error during analysis: {str(e)}")
        return None
    
    return result


def generate_validation_report(results, output_file):
    """Generate a comprehensive validation report for all regions"""
    os.makedirs('manuscript/results', exist_ok=True)
    
    with open(output_file, 'w') as f:
        f.write("Validation Analysis Report\n")
        f.write("========================\n")
        f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("\nAnalysis Coverage:\n")
        
        for result in results:
            base_name = result['name']
            f.write(f"\n{base_name}:\n")
            f.write(f"  Species grouping iterations: {result['num_group_iterations']}\n")
            f.write(f"  Diet matrix iterations: {result['num_matrix_iterations']}\n\n")
            
            consistency_metrics = result['consistency_metrics']
            group_stability = result['group_stability']
            interaction_consistency = result.get('interaction_consistency')
            
            f.write(f"\n{base_name}\n")
            f.write("=" * len(base_name) + "\n\n")
            
            # Group Complexity Analysis
            f.write("1. Group Complexity Analysis\n")
            f.write("---------------------------\n")
            f.write(f"Total number of groups: {len(group_stability)}\n")
            
            # Overall consistency statistics
            all_consistencies = [m['consistency_score'] for m in consistency_metrics.values()]
            f.write("\nOverall Consistency Statistics:\n")
            f.write(f"Mean consistency across all species: {np.mean(all_consistencies):.3f}\n")
            f.write(f"Median consistency across all species: {np.median(all_consistencies):.3f}\n")
            
            # Distribution of number of different groups
            num_groups_dist = Counter([m['num_different_groups'] for m in consistency_metrics.values()])
            f.write("\nDistribution of number of different groups per species:\n")
            for num_groups in sorted(num_groups_dist.keys()):
                f.write(f"{num_groups} group(s): {num_groups_dist[num_groups]} species\n")
            
            # Detailed analysis of unstable species
            unstable_species = [(species, metrics) for species, metrics in consistency_metrics.items() 
                               if metrics['consistency_score'] < 0.95]
            f.write(f"\nSpecies with low stability (consistency < 0.95): {len(unstable_species)}\n")
            for species, metrics in sorted(unstable_species, key=lambda x: x[1]['consistency_score']):
                f.write(f"\n{species}:\n")
                f.write(f"  Consistency score: {metrics['consistency_score']:.2f}\n")
                f.write(f"  Number of different groups: {metrics['num_different_groups']}\n")
                f.write("  Group assignments and frequencies:\n")
                for group, count in sorted(metrics['group_counts'].items(), key=lambda x: x[1], reverse=True):
                    percentage = (count / metrics['total_iterations']) * 100
                    f.write(f"    - {group}: {count} times ({percentage:.1f}%)\n")
            
            # Group stability rankings
            f.write("\nGroup Stability Rankings (sorted by variation):\n")
            sorted_groups = sorted([(group, stats) for group, stats in group_stability.items()],
                                 key=lambda x: x[1]['size_std'], reverse=True)
            for group, stats in sorted_groups:
                if stats['size_std'] > 0:  # Only show groups with some variation
                    f.write(f"\n{group}:\n")
                    f.write(f"  Size variation: {stats['size_std']:.2f}\n")
                    f.write(f"  Size range: {stats['min_size']} - {stats['max_size']} species\n")
                    f.write(f"  Jaccard similarity: {stats['avg_jaccard_similarity']:.3f}\n")
            
            # Diet Interaction Analysis (if available)
            if interaction_consistency:
                interaction_df = pd.DataFrame([{
                    'predator': pred,
                    'prey': prey,
                    'mean_proportion': stats['mean'],
                    'stability_score': stats['stability_score']
                } for (pred, prey), stats in interaction_consistency.items()])
                
                unstable_interactions = interaction_df[interaction_df['stability_score'] > 0.3]
                
                f.write("\n2. Diet Interaction Analysis\n")
                f.write("--------------------------\n")
                f.write(f"Total interactions: {len(interaction_df)}\n")
                f.write(f"Unstable interactions (stability score > 0.3): {len(unstable_interactions)}\n")
                if len(unstable_interactions) > 0:
                    for _, row in unstable_interactions.iterrows():
                        f.write(f"\n{row['predator']} -> {row['prey']}:\n")
                        f.write(f"  Mean proportion: {row['mean_proportion']:.3f}\n")
                        f.write(f"  Stability score: {row['stability_score']:.3f}\n")
                        raw_values = interaction_consistency[(row['predator'], row['prey'])]['raw_values']
                        f.write(f"  Raw values: {raw_values}\n")
            else:
                f.write("\n2. Diet Interaction Analysis\n")
                f.write("--------------------------\n")
                f.write("No diet matrix data available for analysis\n")
                
def generate_supplementary_table(results):
    """Generate a detailed LaTeX table of unstable species for the supplement"""
    table_content = [
        r"\begin{longtable}{llcll}",
        r"\caption{Complete List of Species with Low Classification Stability (Consistency < 0.95)} \label{tab:supp_unstable_species} \\",
        r"\hline",
        r"Region & Species & Consistency & Group & Assignment \% \\",
        r"\hline",
        r"\endhead",
        ""
    ]

    for result in results:
        region_name = result['name'].replace('v2_', '')
        consistency_metrics = result['consistency_metrics']
        
        # Get unstable species
        unstable_species = [(species, metrics) for species, metrics in consistency_metrics.items() 
                           if metrics['consistency_score'] < 0.95]
        
        # Sort by consistency score
        unstable_species.sort(key=lambda x: (x[1]['consistency_score'], x[0]))
        
        # Add region header
        table_content.append(r"\multicolumn{5}{l}{\textbf{" + region_name + r"}} \\")
        table_content.append(r"\hline")
        
        # Add species data
        for species, metrics in unstable_species:
            first_row = True
            for group, count in sorted(metrics['group_counts'].items(), key=lambda x: x[1], reverse=True):
                percentage = (count / metrics['total_iterations']) * 100
                if first_row:
                    table_content.append(f"{region_name} & {species} & {metrics['consistency_score']:.2f} & {group} & {percentage:.1f}\\% \\\\")
                    first_row = False
                else:
                    table_content.append(f"& & & {group} & {percentage:.1f}\\% \\\\")
            table_content.append(r"\hline")
        
        table_content.append(r"\hline")
    
    # Close the table
    table_content.extend([
        r"\end{longtable}"
    ])
    
    # Write to file
    table_file = 'manuscript/results/supplementary_unstable_species.tex'
    with open(table_file, 'w') as f:
        f.write('\n'.join(table_content))
    
    print(f"Supplementary table generated: {table_file}")

def main():
    # Create output directories
    os.makedirs('manuscript/results', exist_ok=True)
    os.makedirs('manuscript/figures', exist_ok=True)
    
    # Analyze all regions
    base_names = ['v2_NorthernTerritory', 'v2_SouthEastInshore', 'v2_SouthEastOffshore']
    results = []
    
    for base_name in base_names:
        result = analyze_region(base_name)
        if result:
            results.append(result)
    
    if not results:
        print("No validation results to analyze")
        return
    
    # Generate combined report
    report_file = 'manuscript/results/validation_analysis.txt'
    generate_validation_report(results, report_file)
    print(f"\nValidation report generated: {report_file}")
    
    # Generate supplementary table
    generate_supplementary_table(results)
    
    # Create combined heatmap
    heatmap_file = 'manuscript/figures/diet_interaction_heatmap.png'
    create_combined_heatmap(results, heatmap_file)
    print(f"Combined heatmap generated: {heatmap_file}")
    
    # Generate additional validation figures
    generate_validation_figures(results)
    print("Additional validation figures generated")
    
    # Generate timing analysis
    species_counts = {
        'v2_NorthernTerritory': 11362,
        'v2_SouthEastInshore': 13901,
        'v2_SouthEastOffshore': 15821
    }
    timing_summary, timing_table = generate_timing_summary(species_counts)
    
    # Save timing analysis text
    timing_file = 'manuscript/results/timing_analysis.tex'
    with open(timing_file, 'w') as f:
        f.write(timing_summary)
    print(f"Timing analysis generated: {timing_file}")
    
    # Save timing analysis table
    table_file = 'manuscript/results/timing_table.tex'
    with open(table_file, 'w') as f:
        f.write(timing_table)
    print(f"Timing table generated: {table_file}")

if __name__ == "__main__":
    main()
