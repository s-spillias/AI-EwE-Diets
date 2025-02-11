import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.gridspec import GridSpec

def create_regional_group_distribution(results, output_path):
    """
    Create a multi-panel figure showing group size distributions by region
    and their relationship with trophic levels and consistency.
    """
    # Set up the figure with a 2x2 grid
    fig = plt.figure(figsize=(15, 12))
    gs = GridSpec(2, 2, figure=fig)
    
    # Panel A: Group size distributions by region (top left)
    ax1 = fig.add_subplot(gs[0, 0])
    region_data = {}
    
    for result in results:
        region = result['name'].replace('_', ' ')
        sizes = []
        for stats in result['group_stability'].values():
            sizes.extend([stats['avg_size']] * len(stats['member_sets']))
        region_data[region] = sizes
    
    ax1.boxplot(region_data.values(), labels=region_data.keys())
    ax1.set_title('A) Functional Group Size Distribution')
    ax1.set_ylabel('Species Count per Group')
    ax1.set_xlabel('Region')
    plt.setp(ax1.get_xticklabels(), rotation=45, ha='right')
    ax1.grid(True)
    
    # Panel B: Consistency scores by region (top right)
    ax2 = fig.add_subplot(gs[0, 1])
    consistency_data = {}
    
    for result in results:
        region = result['name'].replace('_', ' ')
        scores = [m['consistency_score'] for m in result['consistency_metrics'].values()]
        consistency_data[region] = scores
    
    ax2.violinplot([data for data in consistency_data.values()], 
                   positions=range(1, len(consistency_data) + 1))
    ax2.set_xticks(range(1, len(consistency_data) + 1))
    ax2.set_xticklabels(consistency_data.keys())
    ax2.set_title('B) Species Classification Consistency')
    ax2.set_xlabel('Region')
    ax2.set_ylabel('Consistency Score (0-1)')
    plt.setp(ax2.get_xticklabels(), rotation=45, ha='right')
    ax2.grid(True)
    
    # Panel C: Group stability (Jaccard similarity) by region (bottom left)
    ax3 = fig.add_subplot(gs[1, 0])
    stability_data = {}
    
    for result in results:
        region = result['name'].replace('_', ' ')
        similarities = [stats['avg_jaccard_similarity'] 
                       for stats in result['group_stability'].values()]
        stability_data[region] = similarities
    
    ax3.boxplot(stability_data.values(), labels=stability_data.keys())
    ax3.set_title('C) Group Membership Stability')
    ax3.set_xlabel('Region')
    ax3.set_ylabel('Jaccard Similarity Index')
    plt.setp(ax3.get_xticklabels(), rotation=45, ha='right')
    ax3.grid(True)
    
    # Panel D: Group size variation (bottom right)
    ax4 = fig.add_subplot(gs[1, 1])
    variation_data = {}
    
    for result in results:
        region = result['name'].replace('_', ' ')
        variations = [stats['size_std'] for stats in result['group_stability'].values()]
        variation_data[region] = variations
    
    ax4.boxplot(variation_data.values(), labels=variation_data.keys())
    ax4.set_title('D) Group Size Variability')
    ax4.set_xlabel('Region')
    ax4.set_ylabel('Standard Deviation of Group Size')
    plt.setp(ax4.get_xticklabels(), rotation=45, ha='right')
    ax4.grid(True)
    
    # Adjust layout and save
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

def create_group_stability_heatmap(results, output_path):
    """
    Create a heatmap showing the stability of different functional groups
    across regions.
    """
    # Collect stability metrics for each group and region
    stability_data = {}
    all_groups = set()
    
    for result in results:
        region = result['name'].replace('_', ' ')
        stability_data[region] = {}
        
        for group, stats in result['group_stability'].items():
            stability_data[region][group] = stats['avg_jaccard_similarity']
            all_groups.add(group)
    
    # Create the matrix for the heatmap
    regions = list(stability_data.keys())
    groups = sorted(list(all_groups))
    matrix = np.zeros((len(regions), len(groups)))
    
    for i, region in enumerate(regions):
        for j, group in enumerate(groups):
            matrix[i, j] = stability_data[region].get(group, np.nan)
    
    # Create the heatmap
    fig, ax = plt.subplots(figsize=(15, 8))
    sns.heatmap(matrix,
                xticklabels=groups,
                yticklabels=regions,
                cmap='viridis',
                annot=False,
                cbar_kws={'label': 'Jaccard Similarity Index (0-1)'},
                ax=ax)
    
    plt.xticks(rotation=90, ha='right')
    plt.title('Classification Stability of Functional Groups Across Regions')
    plt.xlabel('Functional Group')
    plt.ylabel('Region')
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

def create_diet_matrices_heatmap(results, output_path):
    """Create a combined figure with diet matrices heatmaps from multiple regions"""
    # Filter results to only those with diet interaction data
    diet_results = [r for r in results if 'interaction_consistency' in r]
    
    if not diet_results:
        print("No diet interaction data available for heatmap generation")
        return
    
    # Get all unique predators and prey across all regions
    all_predators = set()
    all_prey = set()
    for result in diet_results:
        interaction_consistency = result['interaction_consistency']
        all_predators.update(pred for pred, _ in interaction_consistency.keys())
        all_prey.update(pr for _, pr in interaction_consistency.keys())
    
    # Sort the complete lists
    all_predators = sorted(list(all_predators))
    all_prey = sorted(list(all_prey))
    
    # Create figure with shared y-axis
    fig, axes = plt.subplots(1, len(diet_results), figsize=(24, 12), sharey=True)
    if len(diet_results) == 1:
        axes = [axes]
    
    # Get global normalization values
    all_stability_values = []
    for result in diet_results:
        interaction_consistency = result['interaction_consistency']
        for stats in interaction_consistency.values():
            if stats['stability_score'] > 0:
                all_stability_values.append(stats['stability_score'])
    
    stability_min = 0
    stability_max = max(all_stability_values) if all_stability_values else 1
    stability_norm = plt.Normalize(vmin=stability_min, vmax=stability_max)
    
    # Create heatmaps
    for idx, result in enumerate(diet_results):
        ax = axes[idx]
        interaction_consistency = result['interaction_consistency']
        region_name = result['name'].replace('_', ' ')
        
        # Create matrices using complete predator/prey lists
        mean_matrix = np.zeros((len(all_predators), len(all_prey)))
        stability_matrix = np.zeros((len(all_predators), len(all_prey)))
        
        # Fill matrices
        for i, pred in enumerate(all_predators):
            for j, pr in enumerate(all_prey):
                if (pred, pr) in interaction_consistency:
                    stats = interaction_consistency[(pred, pr)]
                    mean_matrix[i, j] = stats['mean']
                    stability_matrix[i, j] = stats['stability_score']
        
        # Create mask for empty cells
        mask = (mean_matrix == 0) & (stability_matrix == 0)
        
        # Create heatmap
        sns.heatmap(stability_matrix,
                   xticklabels=all_prey,
                   yticklabels=all_predators,  # Show y labels on all plots
                   cmap='viridis',
                   norm=stability_norm,
                   mask=mask,
                   annot=mean_matrix,
                   fmt='.2f',
                   annot_kws={'size': 4},
                   cbar_kws={'label': 'Stability Score (0=stable, 1=unstable)'},
                   ax=ax)
        
        # Hide y-axis labels for all but the first plot
        if idx > 0:
            ax.yaxis.set_visible(False)
        
        ax.patch.set_facecolor('white')
        ax.set_title(f'{region_name}')
        plt.setp(ax.get_xticklabels(), rotation=45, ha='right')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

def create_stability_score_distribution(results, output_path):
    """Create half-violin plot showing distribution of stability scores across all interactions"""
    # Collect stability scores
    stability_data = []
    for result in results:
        if 'interaction_consistency' not in result:
            continue
        region = result['name'].replace('_', ' ')
        for (pred, prey), stats in result['interaction_consistency'].items():
            if stats['mean'] > 0.05:  # Only include significant interactions
                stability_data.append({
                    'region': region,
                    'predator': pred,
                    'prey': prey,
                    'stability': stats['stability_score']
                })
    
    if not stability_data:
        print("No stability data available for visualization")
        return
    
    # Convert to DataFrame for easier plotting
    df = pd.DataFrame(stability_data)
    
    # Create figure
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Create half violin plot with box plot
    sns.violinplot(data=df, x='region', y='stability', ax=ax,
                  inner='box',  # Show box plot inside violin
                  cut=0,  # Cut off at the bounds of the data
                  split=True,  # Only show right half of violin
                  density_norm='width')  # Scale each violin to same width
    
    # Add individual points
    sns.stripplot(data=df, x='region', y='stability', color='black', 
                 size=4, alpha=0.4, jitter=True, ax=ax)
    
    # Set y-axis to start at 0
    ax.set_ylim(bottom=0)
    
    # Customize plot
    ax.set_title('Distribution of Diet Interaction Stability Scores')
    ax.set_xlabel('Region')
    ax.set_ylabel('Stability Score (0=stable, 1=unstable)')
    plt.xticks(rotation=45, ha='right')
    
    # Add horizontal line at mean
    mean_stability = df['stability'].mean()
    ax.axhline(y=mean_stability, color='r', linestyle='--', alpha=0.5)
    ax.text(ax.get_xlim()[1], mean_stability, f' Mean: {mean_stability:.3f}', 
            va='center', ha='left', color='r')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

def create_predator_stability_boxplots(results, output_path):
    """Create box plots of stability scores grouped by predator"""
    # Collect stability scores
    stability_data = []
    for result in results:
        if 'interaction_consistency' not in result:
            continue
        region = result['name'].replace('_', ' ')
        for (pred, prey), stats in result['interaction_consistency'].items():
            if stats['mean'] > 0.05:  # Only include significant interactions
                stability_data.append({
                    'region': region,
                    'predator': pred,
                    'prey': prey,
                    'stability': stats['stability_score']
                })
    
    if not stability_data:
        print("No stability data available for visualization")
        return
    
    # Convert to DataFrame
    df = pd.DataFrame(stability_data)
    
    # Calculate median stability for each predator for sorting
    predator_medians = df.groupby('predator')['stability'].median().sort_values()
    sorted_predators = predator_medians.index
    
    # Create figure (adjust height based on number of predators)
    fig_height = max(8, len(sorted_predators) * 0.3)
    fig, ax = plt.subplots(figsize=(12, fig_height))
    
    # Create box plot
    sns.boxplot(data=df, x='stability', y='predator', hue='region',
                order=sorted_predators, ax=ax)
    
    # Customize plot
    ax.set_title('Diet Stability Scores by Predator')
    ax.set_xlabel('Stability Score (0=stable, 1=unstable)')
    ax.set_ylabel('Predator')
    
    # Add vertical line at mean
    mean_stability = df['stability'].mean()
    ax.axvline(x=mean_stability, color='r', linestyle='--', alpha=0.5)
    ax.text(mean_stability, ax.get_ylim()[1], f'Mean: {mean_stability:.3f}', 
            va='bottom', ha='center', color='r', rotation=90)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

def generate_validation_figures(results):
    """
    Generate all validation figures from the analysis results.
    """
    os.makedirs('manuscript/figures', exist_ok=True)
    
    # Create the multi-panel figure
    create_regional_group_distribution(
        results,
        'manuscript/figures/regional_group_analysis.png'
    )
    
    # Create the stability heatmap
    create_group_stability_heatmap(
        results,
        'manuscript/figures/group_stability_heatmap.png'
    )
    
    # Create the diet matrices heatmap
    create_diet_matrices_heatmap(
        results,
        'manuscript/figures/diet_interaction_heatmap.png'
    )
    
    # Create stability score distributions
    create_stability_score_distribution(
        results,
        'manuscript/figures/stability_score_distribution.png'
    )
    
    # Create predator stability boxplots
    create_predator_stability_boxplots(
        results,
        'manuscript/figures/predator_stability_boxplots.png'
    )
