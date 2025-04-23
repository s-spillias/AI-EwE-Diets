import pandas as pd
import numpy as np
from scipy import stats
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
import seaborn as sns
from pathlib import Path

def standardize_group_names(name):
    """Standardize group names to match GAB grouping template"""
    if not isinstance(name, str):
        return name
        
    # Convert to lowercase for case-insensitive matching
    name_lower = name.lower()
    
    name_mapping = {
        # Marine mammals
        "bottlenose dolphins": "Bottlenose dolphins",
        "common dolphins": "Common dolphins",
        "long-nosed fur seal": "Long-nosed fur seal",
        "australian fur seal": "Australian fur seal",
        "australian sea lion": "Australian sea lion",
        "baleen whales": "Baleen whales",
        "toothed whales": "Toothed whales",
        
        # Birds
        "albatross": "Albatross",
        "shearwaters": "Shearwaters",
        "small petrels": "Small petrels",
        "gannets": "Gannets",
        "terns": "Terns",
        "shags and cormorants": "Shags and cormorants",
        "gulls": "Gulls",
        "little penguins": "Little Penguins",
        
        # Sharks and rays
        "shelf pelagic sharks": "Shelf pelagic sharks",
        "offshore pelagic sharks": "Offshore pelagic sharks",
        "shelf demersal piscivorous shark": "Shelf demersal piscivorous shark",
        "shelf demersal sharks": "Shelf demersal sharks",
        "deep demersal sharks": "Deep demersal sharks",
        "skates and rays": "Skates and rays",
        
        # Fish groups
        "southern bluefin tuna": "Southern Bluefin Tuna",
        "tunas and billfish": "Tunas and billfish",
        "offshore pelagic piscivores": "Offshore pelagic piscivores",
        "offshore pelagic invertivore large": "Offshore pelagic invertivore large",
        "shelf large pelagic piscivores": "Shelf large pelagic piscivores",
        "sardine": "Sardine",
        "anchovy and other small pelagics": "Anchovy and other small pelagics",
        "mackerels": "Mackerels",
        "redbait": "Redbait",
        
        # Demersal fish groups
        "shelf small demersal piscivores": "Shelf small demersal piscivores",
        "shelf small demersal omnivores": "Shelf small demersal omnivores",
        "shelf large demersal piscivores": "Shelf large demersal piscivores",
        "shelf large demersal omnivores": "Shelf large demersal omnivores",
        
        # Slope fish groups
        "slope small demersal invertivores": "Slope small demersal invertivores",
        "slope small demersal piscivores": "Slope small demersal piscivores",
        "slope small demersal piscivores ": "Slope small demersal piscivores",  # Handle extra space
        "slope large demersal piscivores": "Slope large demersal piscivores",
        "slope large demersal invertivores": "Slope large demersal invertivores",
        
        # Named fish species
        "king george whiting": "King George whiting",
        "garfish": "Garfish",
        "snapper": "Snapper",
        "deepwater flathead": "Deepwater flathead",
        "bight redfish": "Bight redfish",
        
        # Mesopelagic fish
        "migratory mesopelagics": "Migratory mesopelagics",
        "non-migrating mesopelagics": "Non-migrating mesopelagics",
        
        # Benthic groups
        "benthic grazers": "Benthic grazers",
        "abalone": "Abalone",
        "benthic detritivore": "Benthic detritivore",
        "benthic carnivores (infauna)": "Benthic carnivores (infauna)",
        "meiobenthos": "Meiobenthos",
        "shelf filter feeders": "Shelf filter feeders",
        "deep filter feeders": "Deep filter feeders",
        "shelf macrozoobenthos": "Shelf macrozoobenthos",
        
        # Cephalopods and crustaceans
        "squid & cuttlefish shelf": "Squid & cuttlefish shelf",
        "octopus shelf": "Octopus shelf",
        "rock lobster": "Rock lobster",
        "western king prawn": "Western king prawn",
        "crabs & bugs": "Crabs & bugs",
        "deep macrozoobenthos": "Deep macrozoobenthos",
        "deep  squid": "Deep squid",  # Handle double space
        
        # Plankton and primary producers
        "gelatinous zooplankton": "Gelatinous zooplankton",
        "large zooplankton": "Large zooplankton",
        "mesozooplankton": "Mesozooplankton",
        "microzooplankton": "Microzooplankton",
        "nanozooplankton": "Nanozooplankton",
        "pelagic bacteria": "Pelagic bacteria",
        
        # Additional mappings
        "farmed finfish": "Farmed finfish",
        "farmed crustacea": "Farmed crustacea",
        "large phytoplankton": "Large phytoplankton",
        "small phytoplankton": "Small phytoplankton",
        "small phytoplankton ": "Small phytoplankton",  # Handle extra space
        "microphytobenthos": "Microphytobenthos",
        "seagrass": "Seagrass",
        "macroalgae": "Macroalgae",
        "discards": "Discards",
        "detritus pom": "Detritus POM",
        "detritus": "Detritus",
        "import": "Import",
        
        # Additional case variations
        "ABALONE": "Abalone",
        "BIGHT REDFISH": "Bight redfish",
        "DEEPWATER FLATHEAD": "Deepwater flathead",
        "GARFISH": "Garfish",
        "KING GEORGE WHITING": "King George whiting",
        "MICROPHYTOBENTHOS": "Microphytobenthos",
        "MIGRATORY MESOPELAGICS": "Migratory mesopelagics",
        "NON-MIGRATING MESOPELAGICS": "Non-migrating mesopelagics",
        "SARDINE": "Sardine",
        "SHELF DEMERSAL PISCIVOROUS SHARK": "Shelf demersal piscivores shark",
        "SHELF LARGE DEMERSAL OMNIVORES": "Shelf large demersal omnivores",
        "SHELF LARGE DEMERSAL PISCIVORES": "Shelf large demersal piscivores",
        "SHELF SMALL DEMERSAL OMNIVORES": "Shelf small demersal omnivores",
        "SHELF SMALL DEMERSAL PISCIVORES": "Shelf small demersal piscivores",
        "SLOPE LARGE DEMERSAL INVERTIVORES": "Slope large demersal invertivores",
        "SLOPE LARGE DEMERSAL PISCIVORES": "Slope large demersal piscivores",
        "SLOPE SMALL DEMERSAL INVERTIVORES": "Slope small demersal invertivores",
        "SLOPE SMALL DEMERSAL PISCIVORES": "Slope small demersal piscivores",
        "SMALL PHYTOPLANKTON": "Small phytoplankton",
        "SNAPPER": "Snapper",
        "SOUTHERN BLUEFIN TUNA": "Southern Bluefin Tuna",
        "WESTERN KING PRAWN": "Western king prawn",
        "DETRITUS POM": "Detritus POM",
        "DETRITUS": "Detritus"
    }
    
    # Try to find a match using lowercase comparison
    standardized = name_mapping.get(name_lower, name)
    
    # If no match found and name ends with 's', try singular form
    if standardized == name and name_lower.endswith('s'):
        singular = name_lower[:-1]
        standardized = name_mapping.get(singular, name)
    
    return standardized

def load_diet_matrix(filepath):
    """Load a diet matrix CSV file and standardize group names"""
    df = pd.read_csv(filepath, index_col=0)
    
    # Standardize row and column names
    df.index = df.index.map(standardize_group_names)
    df.columns = df.columns.map(standardize_group_names)
    
    # Combine any duplicate rows/columns after standardization
    df = df.groupby(level=0).mean()
    df = df.T.groupby(level=0).mean().T
    
    return df

def calculate_matrix_difference(matrix1, matrix2):
    """Calculate element-wise difference between two matrices"""
    common_preds = matrix1.index.intersection(matrix2.index)
    common_prey = matrix1.columns.intersection(matrix2.columns)
    
    m1 = matrix1.loc[common_preds, common_prey]
    m2 = matrix2.loc[common_preds, common_prey]
    
    return m1 - m2

def calculate_kappa(binary1, binary2):
    """Calculate Cohen's Kappa for binary agreement"""
    n = binary1.size
    n_1 = np.sum(binary1)
    n_0 = n - n_1
    m_1 = np.sum(binary2)
    m_0 = n - m_1
    
    # Observed agreement
    p_o = np.sum((binary1 == 1) & (binary2 == 1) | (binary1 == 0) & (binary2 == 0)) / n
    
    # Expected agreement by chance
    p_e = (n_1 * m_1 + n_0 * m_0) / (n * n)
    
    # Calculate kappa
    if p_e == 1:  # Perfect expected agreement
        return 1.0 if p_o == 1 else 0.0
    
    kappa = (p_o - p_e) / (1 - p_e)
    return kappa

def analyze_diet_relationships(matrix1, matrix2):
    """Analyze diet relationships between two matrices with per-predator statistics"""
    # Note: In the diet matrix, columns are predators and rows are prey
    common_prey = matrix1.index.intersection(matrix2.index)
    common_preds = matrix1.columns.intersection(matrix2.columns)
    
    m1 = matrix1.loc[common_prey, common_preds]
    m2 = matrix2.loc[common_prey, common_preds]
    
    # Convert to binary (presence/absence)
    binary1 = (m1 > 0).astype(int)
    binary2 = (m2 > 0).astype(int)
    
    # Overall binary statistics
    total_cells = binary1.size
    matching_zeros = int(((binary1 == 0) & (binary2 == 0)).values.sum())
    matching_ones = int(((binary1 == 1) & (binary2 == 1)).values.sum())
    only_in_human = int(((binary1 == 1) & (binary2 == 0)).values.sum())
    only_in_ai = int(((binary1 == 0) & (binary2 == 1)).values.sum())
    
    # Per-predator statistics
    predator_stats = {}
    for pred in common_preds:
        pred_binary1 = binary1[pred]  # Get predator column
        pred_binary2 = binary2[pred]  # Get predator column
        pred_m1 = m1[pred]  # Get predator column
        pred_m2 = m2[pred]  # Get predator column
        
        # Binary statistics
        pred_matching_zeros = int(((pred_binary1 == 0) & (pred_binary2 == 0)).sum())
        pred_matching_ones = int(((pred_binary1 == 1) & (pred_binary2 == 1)).sum())
        pred_only_in_human = int(((pred_binary1 == 1) & (pred_binary2 == 0)).sum())
        pred_only_in_ai = int(((pred_binary1 == 0) & (pred_binary2 == 1)).sum())
        
        # Non-zero correlation
        nonzero_mask = (pred_binary1 == 1) & (pred_binary2 == 1)
        if nonzero_mask.sum() > 1:  # Need at least 2 points for correlation
            try:
                nonzero_corr = stats.pearsonr(
                    pred_m1[nonzero_mask].values,
                    pred_m2[nonzero_mask].values
                )
            except (ValueError, stats.ConstantInputWarning):
                nonzero_corr = (np.nan, np.nan)
        else:
            nonzero_corr = (np.nan, np.nan)
            
        predator_stats[pred] = {
            'Binary Statistics': {
                'Total Prey': len(pred_binary1),
                'Matching Zeros': int(pred_matching_zeros),
                'Matching Diet Links': int(pred_matching_ones),
                'Only in Human': int(pred_only_in_human),
                'Only in AI': int(pred_only_in_ai),
                'Agreement Rate': float((pred_matching_zeros + pred_matching_ones) / len(pred_binary1)),
                'Kappa': float(calculate_kappa(pred_binary1.values, pred_binary2.values))
            },
            'Non-zero Statistics': {
                'Number of Common Links': int(nonzero_mask.sum()),
                'Correlation': float(nonzero_corr[0]),
                'P-value': float(nonzero_corr[1])
            }
        }
    
    # Overall statistics
    overall_stats = {
        'Binary Statistics': {
            'Total Cells': total_cells,
            'Matching Zeros': int(matching_zeros),
            'Matching Diet Links': int(matching_ones),
            'Only in Human': int(only_in_human),
            'Only in AI': int(only_in_ai),
            'Agreement Rate': float((matching_zeros + matching_ones) / total_cells),
            'Kappa': float(calculate_kappa(binary1.values.flatten(), binary2.values.flatten()))
        }
    }
    
    # Overall non-zero correlation
    nonzero_mask = (binary1.values == 1) & (binary2.values == 1)
    if nonzero_mask.sum() > 1:  # Need at least 2 points for correlation
        try:
            nonzero_corr = stats.pearsonr(
                m1.values[nonzero_mask],
                m2.values[nonzero_mask]
            )
        except (ValueError, stats.ConstantInputWarning):
            nonzero_corr = (np.nan, np.nan)
        overall_stats['Non-zero Statistics'] = {
            'Number of Common Links': int(nonzero_mask.sum()),
            'Correlation': float(nonzero_corr[0]),
            'P-value': float(nonzero_corr[1])
        }
    
    return overall_stats, predator_stats

def get_ordered_groups():
    """Get ordered list of groups from GAB grouping template"""
    import json
    with open('03_GAB_grouping.json', 'r') as f:
        groups = json.load(f)
    return [list(group.keys())[0] for group in groups]

def plot_mean_difference_heatmap(mean_matrix, original_matrix, output_path):
    """Create a detailed heatmap of differences between mean and original matrices"""
    ordered_groups = get_ordered_groups()
    
    # Filter and order the matrices
    common_groups = set(mean_matrix.index).intersection(original_matrix.index).intersection(ordered_groups)
    ordered_common_groups = [g for g in ordered_groups if g in common_groups]
    
    m1 = mean_matrix.loc[ordered_common_groups, ordered_common_groups]
    m2 = original_matrix.loc[ordered_common_groups, ordered_common_groups]
    
    diff = m1 - m2
    
    plt.figure(figsize=(15, 10))
    ax = sns.heatmap(diff, cmap='RdBu', center=0, 
                     xticklabels=True, yticklabels=True,
                     cbar_kws={'label': 'Difference (Mean - Original)'})
    
    # Set font sizes for tick labels
    ax.tick_params(axis='both', labelsize=8)
    
    plt.title('Difference Between Mean GAB Matrix and Original Matrix')
    plt.xlabel('Prey Groups')
    plt.ylabel('Predator Groups')
    
    # Move x-axis labels to top and rotate them
    ax.xaxis.set_ticks_position('top')
    plt.xticks(rotation=45, ha='left')
    plt.yticks(rotation=0)
    
    plt.tight_layout()
    plt.savefig(output_path, bbox_inches='tight', dpi=300)
    plt.close()

def plot_detailed_comparison(matrix1, matrix2, title, output_path):
    """Create a detailed comparison showing presence/absence and non-zero differences"""
    ordered_groups = get_ordered_groups()
    
    # Filter and order the matrices
    common_groups = set(matrix1.index).intersection(matrix2.index).intersection(ordered_groups)
    ordered_common_groups = [g for g in ordered_groups if g in common_groups]
    
    # Create numbered labels
    numbered_labels = [f"{i+1}. {g}" for i, g in enumerate(ordered_common_groups)]
    short_labels = [str(i+1) for i, g in enumerate(ordered_common_groups)]
    
    m1 = matrix1.loc[ordered_common_groups, ordered_common_groups]
    m2 = matrix2.loc[ordered_common_groups, ordered_common_groups]
    
    # Create binary matrices
    binary1 = (m1 > 0).astype(int)
    binary2 = (m2 > 0).astype(int)
    
    # Create presence/absence comparison matrix
    presence_comparison = np.zeros_like(binary1.values)
    presence_comparison[(binary1.values == 1) & (binary2.values == 1)] = 2  # Present in both
    presence_comparison[(binary1.values == 1) & (binary2.values == 0)] = 1  # Only in Human
    presence_comparison[(binary1.values == 0) & (binary2.values == 1)] = -1  # Only in AI
    
    # Calculate absolute differences and mask non-matching cells
    diff = np.abs(m1 - m2)
    diff_matrix = diff.copy()
    diff_matrix[~((binary1.values == 1) & (binary2.values == 1))] = np.nan
    
    # Create the plot with gridspec for custom subplot layout
    fig = plt.figure(figsize=(20, 12))
    gs = plt.GridSpec(3, 80, height_ratios=[4, 1, 1], width_ratios=[1]*80)

    # First row, two equal subplots (50% each)
    ax1 = fig.add_subplot(gs[0, 0:36])  # Top left subplot (50% width)
    ax2 = fig.add_subplot(gs[0, 47:80])  # Top right subplot (50% width)

    # Second row, one subplot taking up only 30% from the left
    ax3 = fig.add_subplot(gs[1, 0:29])  # Bottom subplot (30% width)
    
    # Third row, histogram with same width as ax3
    ax4 = fig.add_subplot(gs[1, 47:80])  # Histogram subplot

    ax1.text(-0.1, 1.05, 'a', transform=ax1.transAxes, fontsize=16, fontweight='bold')
    ax2.text(-0.1, 1.05, 'b', transform=ax2.transAxes, fontsize=16, fontweight='bold')
    ax3.text(-0.1, 1.05, 'c', transform=ax3.transAxes, fontsize=16, fontweight='bold')
    ax4.text(-0.1, 1.05, 'd', transform=ax4.transAxes, fontsize=16, fontweight='bold')
    
    # Create custom colormap for presence/absence using colorblind-friendly colors
    colors = ['#21918C',  # Teal for present in both
            '#F5F5F5',   # Light grey for absent in both
            '#FDE725',   # Yellow for only in Human
            '#440154']  # Deep purple for only in AI
    presence_cmap = ListedColormap(colors)
    
    # Plot presence/absence comparison
    bounds = np.array([-1.5, -0.5, 0.5, 1.5, 2.5])
    norm = BoundaryNorm(bounds, presence_cmap.N)
    
    hm = sns.heatmap(presence_comparison, ax=ax1, cmap=presence_cmap, norm=norm,
                     xticklabels=short_labels, yticklabels=numbered_labels,
                     cbar_kws={'ticks': [-1, 0, 1, 2]})
    
    # Set font sizes for tick labels and move x-axis to top
    ax1.tick_params(axis='both', labelsize=5)
    ax1.xaxis.set_ticks_position('top')
    ax1.xaxis.set_label_position('top')
    plt.sca(ax1)
    plt.xticks(rotation=0, ha='center')
    
    # Update colorbar labels
    colorbar = hm.collections[0].colorbar
    colorbar.set_ticklabels(['Only in AI', 'Absent in both',
                            'Only in Human', 'Present in both'])
    
    # Plot absolute differences with viridis colormap
    sns.heatmap(diff_matrix, ax=ax2, cmap='viridis', vmin=0, vmax=1,
                xticklabels=short_labels, yticklabels=numbered_labels,
                cbar_kws={'label': 'Absolute Difference |Human - AI|'})
    
    # Set font sizes for tick labels and move x-axis to top
    ax2.tick_params(axis='both', labelsize=6)
    ax2.xaxis.set_ticks_position('top')
    ax2.xaxis.set_label_position('top')
    plt.sca(ax2)
    plt.xticks(rotation=0, ha='center')
    
    # Update axis labels
    ax1.set_xlabel('Predator Groups')
    ax1.set_ylabel('Prey Groups')
    ax2.set_xlabel('Predator Groups')
    ax2.set_ylabel('')
    
    # Set label rotation
    for ax in [ax1, ax2]:
        plt.sca(ax)
        plt.xticks(rotation=0, ha='center')
        plt.yticks(rotation=0)
    
    # Calculate proportions for each column
    column_stats = []
    for col in range(presence_comparison.shape[1]):
        col_data = presence_comparison[:, col]
        stats = {
            'Only in AI': np.sum(col_data == -1) / len(col_data),
            'Absent in both': np.sum(col_data == 0) / len(col_data),
            'Only in Human': np.sum(col_data == 1) / len(col_data),
            'Present in both': np.sum(col_data == 2) / len(col_data)
        }
        column_stats.append(stats)
    
    # Create stacked bar plot
    categories = ['Present in both', 'Absent in both', 'Only in Human', 'Only in AI']
    category_colors = [colors[3], colors[1], colors[2], colors[0]]
    x = np.arange(len(ordered_common_groups))
    bottom = np.zeros(len(ordered_common_groups))
    width = 0.9
    
    for i, category in enumerate(categories):
        values = [stats[category] for stats in column_stats]
        ax3.bar(x, values, width, bottom=bottom, color=category_colors[i])
        bottom += values
    
    # Configure stacked bar plot
    ax3.set_xticks(x)
    ax3.set_xticklabels(short_labels)
    ax3.set_ylabel('Proportion')
    ax3.set_ylim(0, 1)
    ax3.set_yticks([0, 1])
    ax3.tick_params(axis='both', labelsize=5)
    
    # Remove frame from bar plot
    for spine in ax3.spines.values():
        spine.set_visible(False)
    
    # Set the bar plot limits
    ax3.set_xlim(-0.5, len(ordered_common_groups) - 0.5)
    
    # Create histogram of differences where both matrices have data
    common_mask = (binary1.values == 1) & (binary2.values == 1)
    differences = np.abs(m1.values[common_mask] - m2.values[common_mask])
    
    # Plot histogram
    ax4.hist(differences, bins=20, color='#440154', alpha=0.7)
    ax4.set_xlabel('Absolute Difference in Diet Proportions')
    ax4.set_ylabel('Frequency')
    ax4.tick_params(axis='both', labelsize=5)
    
    # Remove frame from histogram
    for spine in ax4.spines.values():
        spine.set_visible(False)
    
    plt.tight_layout()
    plt.savefig(output_path, bbox_inches='tight', dpi=300)
    plt.close()
    
    # Return statistics about the differences
    return {
        'mean_difference': float(np.mean(differences)),
        'median_difference': float(np.median(differences)),
        'std_difference': float(np.std(differences)),
        'min_difference': float(np.min(differences)),
        'max_difference': float(np.max(differences)),
        'q1_difference': float(np.percentile(differences, 25)),
        'q3_difference': float(np.percentile(differences, 75))
    }

def analyze_matrices(original_matrix, gab_matrices):
    """Analyze matrices and create detailed JSON output"""
    original_groups = set(original_matrix.index)
    gab_groups = set(gab_matrices[0].index)  # Use first GAB matrix as reference
    
    # Find common and unique groups
    common_groups = original_groups.intersection(gab_groups)
    only_in_original = original_groups - gab_groups
    only_in_gab = gab_groups - original_groups
    
    # Create analysis results dictionary
    analysis_results = {
        'Group Statistics': {
            'Total Groups in Human': len(original_groups),
            'Total Groups in AI': len(gab_groups),
            'Number of Matched Groups': len(common_groups),
            'Groups Only in Human': sorted(list(only_in_original)),
            'Groups Only in AI': sorted(list(only_in_gab))
        },
        'Individual Matrices': {},
        'Mean Matrix': {}
    }
    
    # Analyze individual matrices
    for i, matrix in enumerate(gab_matrices, 1):
        matrix_name = f'AI_{i}'
        overall_stats, predator_stats = analyze_diet_relationships(original_matrix, matrix)
        analysis_results['Individual Matrices'][matrix_name] = {
            'Overall Statistics': overall_stats,
            'Per-predator Statistics': predator_stats
        }
    
    # Analyze mean matrix
    mean_matrix = pd.concat(gab_matrices).groupby(level=0).mean()
    overall_stats, predator_stats = analyze_diet_relationships(original_matrix, mean_matrix)
    analysis_results['Mean Matrix'] = {
        'Overall Statistics': overall_stats,
        'Per-predator Statistics': predator_stats
    }
    
    return analysis_results

def plot_simplified_comparison(matrix1, matrix2, output_path):
    """Create a simplified comparison showing only the per-predator proportions and distribution plots"""
    ordered_groups = get_ordered_groups()
    
    # Filter and order the matrices
    common_groups = set(matrix1.index).intersection(matrix2.index).intersection(ordered_groups)
    ordered_common_groups = [g for g in ordered_groups if g in common_groups]
    
    # Create numbered labels
    numbered_labels = [f"{i+1}. {g}" for i, g in enumerate(ordered_common_groups)]
    short_labels = [str(i+1) for i, g in enumerate(ordered_common_groups)]
    
    m1 = matrix1.loc[ordered_common_groups, ordered_common_groups]
    m2 = matrix2.loc[ordered_common_groups, ordered_common_groups]
    
    # Create binary matrices
    binary1 = (m1 > 0).astype(int)
    binary2 = (m2 > 0).astype(int)
    
    # Create presence/absence comparison matrix
    presence_comparison = np.zeros_like(binary1.values)
    presence_comparison[(binary1.values == 1) & (binary2.values == 1)] = 2  # Present in both
    presence_comparison[(binary1.values == 1) & (binary2.values == 0)] = 1  # Only in Human
    presence_comparison[(binary1.values == 0) & (binary2.values == 1)] = -1  # Only in AI
    
    # Create the plot with two subplots side by side
    fig = plt.figure(figsize=(15, 8))
    gs = plt.GridSpec(1, 2, width_ratios=[1.5, 1])
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1])
    
    ax1.text(-0.1, 1.05, 'a', transform=ax1.transAxes, fontsize=16, fontweight='bold')
    ax2.text(-0.1, 1.05, 'b', transform=ax2.transAxes, fontsize=16, fontweight='bold')
    
    # Calculate proportions for each column
    column_stats = []
    for col in range(presence_comparison.shape[1]):
        col_data = presence_comparison[:, col]
        stats = {
            'Only in AI': np.sum(col_data == -1) / len(col_data),
            'Absent in both': np.sum(col_data == 0) / len(col_data),
            'Only in Human': np.sum(col_data == 1) / len(col_data),
            'Present in both': np.sum(col_data == 2) / len(col_data)
        }
        column_stats.append(stats)
    
    # Create horizontal stacked bar plot
    categories = ['Only in AI', 'Only in Human', 'Present in both', 'Absent in both']
    category_colors = ['#9ad6ae', '#f9ba7b', '#cbacdb', '#F5F5F5']
    # Reverse the order of groups for y-axis
    ordered_common_groups = ordered_common_groups[::-1]
    y = np.arange(len(ordered_common_groups))
    left = np.zeros(len(ordered_common_groups))
    height = 0.9
    
    for i, category in enumerate(categories):
        values = [stats[category] for stats in column_stats]
        ax1.barh(y, values, height, left=left, color=category_colors[i], label=category)
        left += values
    
    # Configure stacked bar plot
    ax1.set_yticks(y)
    ax1.set_yticklabels(ordered_common_groups)
    ax1.set_xlabel('Proportion')
    ax1.set_xlim(0, 1)
    ax1.legend(bbox_to_anchor=(0, 1.02), loc='lower left', ncol=4)
    ax1.tick_params(axis='both', labelsize=8)
    
    # Create histogram of differences where both matrices have data
    common_mask = (binary1.values == 1) & (binary2.values == 1)
    differences = np.abs(m1.values[common_mask] - m2.values[common_mask])
    
    # Plot histogram
    ax2.hist(differences, bins=20, color='#cbacdb', alpha=0.7)
    ax2.set_xlabel('Absolute Difference in Diet Proportions')
    ax2.set_ylabel('Frequency')
    ax2.tick_params(axis='both', labelsize=8)
    
    plt.tight_layout()
    plt.savefig(output_path, bbox_inches='tight', dpi=300)
    plt.close()
    
    return {
        'mean_difference': float(np.mean(differences)),
        'median_difference': float(np.median(differences)),
        'std_difference': float(np.std(differences)),
        'min_difference': float(np.min(differences)),
        'max_difference': float(np.max(differences)),
        'q1_difference': float(np.percentile(differences, 25)),
        'q3_difference': float(np.percentile(differences, 75))
    }

def main():
    """Main function to analyze matrices and save results"""
    import json
    
    # Create output directory
    output_dir = Path('manuscript/figures/diet_matrix_validation')
    output_dir.mkdir(exist_ok=True, parents=True)
    
    # Load original matrix
    original_matrix = load_diet_matrix('Validation/GAB_diet/original_diet_matrix_from_Cathy.csv')
    
    # Load all GAB matrices
    gab_matrices = []
    for i in range(1, 6):
        matrix = load_diet_matrix(f'MODELS/GAB/GAB_{i}/05_diet_matrix.csv')
        gab_matrices.append(matrix)
    
    # Analyze matrices
    analysis_results = analyze_matrices(original_matrix, gab_matrices)
    
    # Save results as JSON
    with open(output_dir / 'matrix_analysis.json', 'w') as f:
        json.dump(analysis_results, f, indent=2)
    
    # Calculate mean GAB matrix for plots
    mean_matrix = pd.concat(gab_matrices).groupby(level=0).mean()
    
    # Create both detailed and simplified comparison plots
    diff_stats = plot_detailed_comparison(
        original_matrix,  # Human matrix first
        mean_matrix,     # AI matrix second
        f'Mean GAB Matrix vs Original Matrix',
        output_dir / 'detailed_comparison.png'
    )
    
    # Create simplified version for main text
    plot_simplified_comparison(
        original_matrix,
        mean_matrix,
        output_dir / 'simplified_comparison.png'
    )
    
    # Generate report.txt with key findings
    with open('manuscript/results/GAB_analysis_report.txt', 'w') as f:
            # 1. Groups present in one matrix and not the other
            f.write("1. Groups Present in One Matrix but Not the Other\n")
            f.write("==============================================\n\n")
            f.write("Groups only in Human matrix:\n")
            for group in sorted(analysis_results['Group Statistics']['Groups Only in Human']):
                f.write(f"- {group}\n")
            f.write("\nGroups only in AI matrix:\n")
            for group in sorted(analysis_results['Group Statistics']['Groups Only in AI']):
                f.write(f"- {group}\n")
            f.write("\n\n")
            
            # 2. Overall kappa for mean matrix comparison
            f.write("2. Overall Kappa for Mean Matrix Comparison\n")
            f.write("=====================================\n\n")
            kappa = analysis_results['Mean Matrix']['Overall Statistics']['Binary Statistics']['Kappa']
            f.write(f"Overall Kappa coefficient: {kappa:.3f}\n\n")
            
            # 3. Distribution of errors in diet interactions
            f.write("3. Distribution of Errors in Diet Interactions\n")
            f.write("=========================================\n\n")
            
            # Get statistics from mean matrix comparison
            mean_stats = analysis_results['Mean Matrix']['Overall Statistics']['Binary Statistics']
            total_cells = mean_stats['Total Cells']
            matching_zeros = mean_stats['Matching Zeros']
            matching_ones = mean_stats['Matching Diet Links']
            only_human = mean_stats['Only in Human']
            only_ai = mean_stats['Only in AI']
            
            f.write("Overall Agreement Statistics:\n")
            f.write(f"- Total number of potential interactions: {total_cells}\n")
            f.write(f"- Matching absence of interaction: {matching_zeros} ({(matching_zeros/total_cells)*100:.1f}%)\n")
            f.write(f"- Matching presence of interaction: {matching_ones} ({(matching_ones/total_cells)*100:.1f}%)\n")
            f.write(f"- Interactions only in Human matrix: {only_human} ({(only_human/total_cells)*100:.1f}%)\n")
            f.write(f"- Interactions only in AI matrix: {only_ai} ({(only_ai/total_cells)*100:.1f}%)\n\n")
            
            # Add information about magnitude of differences where both have data
            if 'Non-zero Statistics' in analysis_results['Mean Matrix']['Overall Statistics']:
                nonzero_stats = analysis_results['Mean Matrix']['Overall Statistics']['Non-zero Statistics']
                common_links = nonzero_stats['Number of Common Links']
                correlation = nonzero_stats['Correlation']
                p_value = nonzero_stats['P-value']
                
                f.write("For interactions present in both matrices:\n")
                f.write(f"- Number of common diet links: {common_links}\n")
                f.write(f"- Correlation coefficient: {correlation:.3f}\n")
                f.write(f"- Correlation p-value: {p_value:.3f}\n\n")
            
            # Additional summary statistics
            f.write("4. Additional Summary Statistics\n")
            f.write("============================\n\n")
            
            # Calculate total matches and non-matches
            total_matches = matching_zeros + matching_ones
            total_non_matches = only_human + only_ai
            
            f.write("Match/Non-match Summary:\n")
            f.write(f"- Total matching cells: {total_matches} ({(total_matches/total_cells)*100:.1f}%)\n")
            f.write(f"  * Matching zeros (both absent): {matching_zeros} ({(matching_zeros/total_cells)*100:.1f}%)\n")
            f.write(f"  * Matching ones (both present): {matching_ones} ({(matching_ones/total_cells)*100:.1f}%)\n")
            f.write(f"- Total non-matching cells: {total_non_matches} ({(total_non_matches/total_cells)*100:.1f}%)\n")
            f.write(f"  * Only in Human: {only_human} ({(only_human/total_cells)*100:.1f}%)\n")
            f.write(f"  * Only in AI: {only_ai} ({(only_ai/total_cells)*100:.1f}%)\n\n")
            
            # Calculate ratios and rates
            true_positive_rate = matching_ones / (matching_ones + only_human) if (matching_ones + only_human) > 0 else 0
            true_negative_rate = matching_zeros / (matching_zeros + only_ai) if (matching_zeros + only_ai) > 0 else 0
            precision = matching_ones / (matching_ones + only_ai) if (matching_ones + only_ai) > 0 else 0
            
            f.write("Agreement Rates:\n")
            f.write(f"- Overall agreement rate: {(total_matches/total_cells):.3f}\n")
            f.write(f"- True positive rate (sensitivity): {true_positive_rate:.3f}\n")
            f.write(f"- True negative rate (specificity): {true_negative_rate:.3f}\n")
            f.write(f"- Precision: {precision:.3f}\n")
            f.write("\n5. Distribution of Differences in Common Diet Links\n")
            f.write("==========================================\n\n")
            f.write("For interactions present in both matrices, the distribution of absolute differences:\n")
            f.write(f"- Mean difference: {diff_stats['mean_difference']:.3f}\n")
            f.write(f"- Median difference: {diff_stats['median_difference']:.3f}\n")
            f.write(f"- Standard deviation: {diff_stats['std_difference']:.3f}\n")
            f.write(f"- Minimum difference: {diff_stats['min_difference']:.3f}\n")
            f.write(f"- Maximum difference: {diff_stats['max_difference']:.3f}\n")
            f.write(f"- 25th percentile: {diff_stats['q1_difference']:.3f}\n")
            f.write(f"- 75th percentile: {diff_stats['q3_difference']:.3f}\n\n")
            
            # 6. Quantitative Summary of Group Agreement
            f.write("\n6. Quantitative Summary of Group Agreement\n")
            f.write("====================================\n\n")
            
            total_human_groups = analysis_results['Group Statistics']['Total Groups in Human']
            total_ai_groups = analysis_results['Group Statistics']['Total Groups in AI']
            matched_groups = analysis_results['Group Statistics']['Number of Matched Groups']
            only_human_groups = len(analysis_results['Group Statistics']['Groups Only in Human'])
            only_ai_groups = len(analysis_results['Group Statistics']['Groups Only in AI'])
            
            # Calculate group-level statistics
            total_unique_groups = total_human_groups + only_ai_groups
            total_shared_groups = matched_groups
            total_different_groups = only_human_groups + only_ai_groups
            
            # Calculate Jaccard similarity for groups
            jaccard_similarity = matched_groups / (total_human_groups + only_ai_groups - matched_groups)
            
            f.write("Group Coverage Statistics:\n")
            f.write(f"- Total groups in Human matrix: {total_human_groups}\n")
            f.write(f"- Total groups in AI matrix: {total_ai_groups}\n")
            f.write(f"- Number of matched groups: {matched_groups}\n")
            f.write(f"- Groups only in Human matrix: {only_human_groups}\n")
            f.write(f"- Groups only in AI matrix: {only_ai_groups}\n")
            f.write(f"- Total unique groups across both matrices: {total_unique_groups}\n")
            f.write(f"- Total different groups between matrices: {total_different_groups}\n\n")
            
            # Calculate percentages
            human_coverage = matched_groups / total_human_groups * 100
            ai_coverage = matched_groups / total_ai_groups * 100
            overall_agreement = matched_groups / (total_human_groups + only_ai_groups) * 100
            
            f.write("Group Agreement Rates:\n")
            f.write(f"- Percentage of Human groups matched in AI: {human_coverage:.1f}%\n")
            f.write(f"- Percentage of AI groups matched in Human: {ai_coverage:.1f}%\n")
            f.write(f"- Overall group agreement rate: {overall_agreement:.1f}%\n")
            f.write(f"- Jaccard similarity coefficient: {jaccard_similarity:.3f}\n")
            f.write(f"- Percentage of groups that differ: {(total_different_groups/total_unique_groups)*100:.1f}%\n")

if __name__ == '__main__':
    main()
