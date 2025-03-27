import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.gridspec import GridSpec

# Mapping for region display names
REGION_DISPLAY_NAMES = {
    'v2_NorthernTerritory': 'Northern Territory',
    'v2_SouthEastInshore': 'South East Shelf',
    'v2_SouthEastOffshore': 'South East Offshore'
}

def get_display_name(region_name):
    """Convert region name to its display name"""
    return REGION_DISPLAY_NAMES.get(region_name, region_name)

def create_regional_group_distribution(results, output_path):
    """
    Create a multi-panel figure showing group size distributions by region
    and their relationship with trophic levels and consistency.
    """
    # Set up the figure
    fig = plt.figure(figsize=(8, 6))
    
    # Group stability (Jaccard similarity) by region
    ax3 = fig.add_subplot(111)
    
    # Prepare data for seaborn boxplot
    plot_data = []
    for result in results:
        region = get_display_name(result['name'])
        for group, stats in result['group_stability'].items():
            plot_data.append({
                'Region': region,
                'Similarity': stats['avg_jaccard_similarity'],
                'Group': group
            })
    
    df = pd.DataFrame(plot_data)
    
    # Create boxplot with region-specific colors
    palette = {
        'Northern Territory': '#f9ba7b',
        'South East Shelf': '#99bfdd',
        'South East Offshore': '#9ad6ae'
    }
    sns.boxplot(data=df, x='Region', y='Similarity', ax=ax3, palette=palette)
    
    # Add outlier labels
    for i, region in enumerate(df['Region'].unique()):
        region_data = df[df['Region'] == region]
        
        # Calculate outlier thresholds
        q1 = region_data['Similarity'].quantile(0.25)
        q3 = region_data['Similarity'].quantile(0.75)
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        # Find outliers
        outliers = region_data[
            (region_data['Similarity'] < lower_bound) | 
            (region_data['Similarity'] > upper_bound)
        ]
        
        # Sort outliers by similarity value
        outliers = outliers.sort_values('Similarity', ascending=True)
        
        # Add labels with smart placement
        for j, (_, outlier) in enumerate(outliers.iterrows()):
            # Alternate between left and right, above and below
            side = -1 if j % 2 == 0 else 1  # -1 for left, 1 for right
            vert = -1 if outlier['Similarity'] > 0.95 else 1  # -1 for below, 1 for above
            
            x_offset = 15 * side
            y_offset = 10 * vert
            
            ax3.annotate(
                outlier['Group'],
                xy=(i, outlier['Similarity']),
                xytext=(x_offset, y_offset),
                textcoords='offset points',
                ha='right' if side < 0 else 'left',
                va='top' if vert < 0 else 'bottom',
                fontsize=8,
                arrowprops=dict(
                    arrowstyle='-',
                    connectionstyle='arc3,rad=0.2',
                    color='gray',
                    alpha=0.6
                )
            )
    
    ax3.set_title('Group Membership Stability')
    ax3.set_xlabel('Region')
    ax3.set_ylabel('Jaccard Similarity Index')
    plt.setp(ax3.get_xticklabels(), rotation=45, ha='right')
    
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
        region = get_display_name(result['name'])
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
    # Create custom colormap from white to pastel blue
    colors = ['#ffffff', '#99bfdd']
    custom_cmap = sns.light_palette('#99bfdd', as_cmap=True)
    
    sns.heatmap(matrix,
                xticklabels=groups,
                yticklabels=regions,
                cmap=custom_cmap,
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
    
    # Create figure with GridSpec for better control over spacing
    fig = plt.figure(figsize=(24, 12))
    gs = GridSpec(1, len(diet_results), figure=fig, wspace=0)
    # Add more top margin for subplot labels
    gs.update(top=0.95)
    axes = [fig.add_subplot(gs[0, i]) for i in range(len(diet_results))]
    if len(diet_results) == 1:
        axes = [axes]
    
    # Get global normalization values
    all_stability_values = []
    for result in diet_results:
        interaction_consistency = result['interaction_consistency']
        for stats in interaction_consistency.values():
            if stats['stability_score'] > 0:
                all_stability_values.append(stats['stability_score'])
    
    stability_norm = plt.Normalize(vmin=0, vmax=1)
    
    # Create heatmaps
    for idx, result in enumerate(diet_results):
        ax = axes[idx]
        interaction_consistency = result['interaction_consistency']
        region_name = get_display_name(result['name'])
        
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
        
        # Create heatmap with custom colormap
        custom_cmap = sns.light_palette('#99bfdd', as_cmap=True)
        
        sns.heatmap(stability_matrix,
                   xticklabels=all_prey,
                   yticklabels=all_predators,  # Show y labels on all plots
                   cmap=custom_cmap,
                   norm=stability_norm,
                   mask=mask,
                   annot=mean_matrix,
                   fmt='.2f',
                   annot_kws={'size': 4},
                   cbar_kws={'label': 'Stability Score (1=stable, 0=unstable)'},
                   ax=ax)
        
        # Hide y-axis labels for all but the first plot
        if idx > 0:
            ax.yaxis.set_visible(False)
        
        ax.patch.set_facecolor('white')
        # Add subplot label (a, b, etc.)
        ax.text(-0.1, 1.05, chr(97 + idx), transform=ax.transAxes, 
                size=10, weight='bold')
        plt.setp(ax.get_xticklabels(), rotation=45, ha='right')
        ax.set_xlabel('')  # Remove x-axis label
    
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

def create_stability_score_distribution(results, output_path):
    """Create half-violin plot showing distribution of stability scores across all interactions"""
    # Collect stability scores
    stability_data = []
    for result in results:
        if 'interaction_consistency' not in result:
            continue
        region = get_display_name(result['name'])
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
    
    # Create half violin plot with box plot using region-specific colors
    palette = {
        'Northern Territory': '#f9ba7b',
        'South East Shelf': '#99bfdd',
        'South East Offshore': '#9ad6ae'
    }
    sns.violinplot(data=df, x='region', y='stability', ax=ax,
                  inner='box',  # Show box plot inside violin
                  cut=0,  # Cut off at the bounds of the data
                  split=True,  # Only show right half of violin
                  density_norm='width',  # Scale each violin to same width
                  palette=palette)
    
    # Add individual points
    sns.stripplot(data=df, x='region', y='stability', color='black', 
                 size=4, alpha=0.4, jitter=True, ax=ax)
    
    # Set y-axis to start at 0
    ax.set_ylim(bottom=0)
    
    # Customize plot
    ax.set_title('Distribution of Diet Interaction Stability Scores')
    ax.set_xlabel('Region')
    ax.set_ylabel('Stability Score (1=stable, 0=unstable)')
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
        region = get_display_name(result['name'])
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
    
    # Create box plot with region-specific colors
    palette = {
        'Northern Territory': '#f9ba7b',
        'South East Shelf': '#99bfdd',
        'South East Offshore': '#9ad6ae'
    }
    sns.boxplot(data=df, x='stability', y='predator', hue='region',
                order=sorted_predators, ax=ax, palette=palette)
    
    # Customize plot
    ax.set_title('Diet Stability Scores by Predator')
    ax.set_xlabel('Stability Score (1=stable, 0=unstable)')
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
