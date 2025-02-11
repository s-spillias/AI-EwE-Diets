#!/usr/bin/env python3
import os
import json
import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multicomp import pairwise_tukeyhsd
from statsmodels.multivariate.manova import MANOVA
import matplotlib.pyplot as plt
import seaborn as sns
from collections import defaultdict

def load_validation_data(base_names=['NorthernTerritory', 'SouthEastInshore', 'SouthEastOffshore']):
    """Load validation data from all regions"""
    data = {}
    for base_name in base_names:
        region_data = defaultdict(list)
        model_dir = 'MODELS'
        
        # Find validation iteration directories
        iteration_dirs = []
        for dir_name in os.listdir(model_dir):
            if dir_name.startswith(f"{base_name}_validation_"):
                full_path = os.path.join(model_dir, dir_name)
                if os.path.isdir(full_path):
                    iteration_dirs.append(full_path)
        
        # Load data from each iteration
        for dir_path in iteration_dirs:
            # Load species assignments
            assignments_path = os.path.join(dir_path, '03_grouped_species_assignments.json')
            if os.path.exists(assignments_path):
                with open(assignments_path, 'r') as f:
                    assignments = json.load(f)
                    region_data['assignments'].append(assignments)
            
            # Load diet matrix
            matrix_path = os.path.join(dir_path, '05_diet_matrix.csv')
            if os.path.exists(matrix_path):
                matrix = pd.read_csv(matrix_path, index_col=0)
                region_data['diet_matrices'].append(matrix)
        
        data[base_name] = region_data
    
    return data

def analyze_group_consistency(data):
    """Analyze statistical significance of group consistency across regions"""
    results = {}
    
    for region, region_data in data.items():
        assignments = region_data['assignments']
        if not assignments:
            continue
        
        # Count species per group across iterations
        group_counts = defaultdict(list)
        for iteration in assignments:
            counts = defaultdict(int)
            for group, group_data in iteration.items():
                species_count = 0
                def count_species(data):
                    count = 0
                    if isinstance(data, dict):
                        if 'specCode' in data:
                            return 1
                        for value in data.values():
                            count += count_species(value)
                    return count
                
                species_count = count_species(group_data)
                if species_count > 0:
                    counts[group] += species_count
            for group, count in counts.items():
                group_counts[group].append(count)
        
        # Calculate chi-square test for consistency
        observed = np.array([counts for counts in group_counts.values()])
        # Calculate expected frequencies based on overall proportions
        total_counts = observed.sum(axis=1, keepdims=True)
        overall_props = observed.sum(axis=0) / observed.sum()
        expected = total_counts * overall_props
        
        # Calculate chi-square statistic
        valid_mask = expected > 0
        chi2 = np.sum(((observed[valid_mask] - expected[valid_mask])**2) / expected[valid_mask])
        df = (observed.shape[0] - 1) * (observed.shape[1] - 1)
        p_value = 1 - stats.chi2.cdf(chi2, df)
        
        # Calculate coefficient of variation for each group
        cv_values = {group: stats.variation(counts) for group, counts in group_counts.items()}
        
        results[region] = {
            'chi_square': chi2,
            'p_value': p_value,
            'cv_values': cv_values,
            'mean_cv': np.mean(list(cv_values.values())),
            'std_cv': np.std(list(cv_values.values()))
        }
    
    return results

def analyze_regional_differences(data):
    """Analyze statistical significance of differences between regions"""
    # Prepare data for analysis
    region_metrics = defaultdict(list)
    for region, region_data in data.items():
        assignments = region_data['assignments']
        if not assignments:
            continue
        
        # Calculate consistency metrics for each iteration
        for iteration in assignments:
            # Count species per group
            group_sizes = defaultdict(int)
            for group, group_data in iteration.items():
                def count_species(data):
                    count = 0
                    if isinstance(data, dict):
                        if 'specCode' in data:
                            return 1
                        for value in data.values():
                            count += count_species(value)
                    return count
                
                species_count = count_species(group_data)
                if species_count > 0:
                    group_sizes[group] += species_count
            
            # Calculate summary statistics
            sizes = list(group_sizes.values())
            if sizes:
                region_metrics['mean_size'].append(np.mean(sizes))
                region_metrics['std_size'].append(np.std(sizes))
                region_metrics['regions'].append(region)
    
    # Convert to numpy arrays for analysis
    means = np.array(region_metrics['mean_size'])
    stds = np.array(region_metrics['std_size'])
    regions = np.array(region_metrics['regions'])
    
    # Normalize data before analysis
    means_norm = (means - np.mean(means)) / np.std(means)
    
    # Perform statistical tests
    region_means = [means_norm[regions == region] for region in set(regions)]
    f_stat, anova_p = stats.f_oneway(*region_means)
    
    # Calculate effect size (Cohen's f)
    n = len(means_norm)
    k = len(set(regions))
    
    # Calculate MSE (within-group variance)
    mse = 0
    for region in set(regions):
        group_data = means_norm[regions == region]
        mse += np.sum((group_data - np.mean(group_data))**2)
    mse = mse / (n - k) if n > k else 1
    
    # Calculate MSB (between-group variance)
    msb = 0
    for region in set(regions):
        group_data = means_norm[regions == region]
        msb += len(group_data) * (np.mean(group_data) - np.mean(means_norm))**2
    msb = msb / (k - 1) if k > 1 else 0
    
    # Calculate Cohen's f
    cohens_f = np.sqrt(msb / mse) if mse > 0 else 0
    
    return {
        'anova_f': f_stat,
        'anova_p': anova_p,
        'cohens_f': cohens_f,
        'region_stats': {
            region: {
                'mean': np.mean(means[regions == region]),
                'std': np.mean(stds[regions == region])
            }
            for region in set(regions)
        }
    }

def analyze_trophic_patterns(data):
    """Analyze statistical significance of trophic level patterns"""
    results = {}
    
    for region, region_data in data.items():
        matrices = region_data['diet_matrices']
        if not matrices:
            continue
        
        # Calculate trophic levels for each iteration
        trophic_levels = defaultdict(list)
        for matrix in matrices:
            # Simple trophic level calculation (could be enhanced)
            tl = pd.Series(index=matrix.index, dtype=float)
            tl[:] = 1.0  # Initialize all to 1
            
            # Iterate to calculate trophic levels
            for _ in range(10):  # Usually converges within 10 iterations
                new_tl = 1 + matrix.dot(tl)
                if np.allclose(tl, new_tl):
                    break
                tl = new_tl
            
            for group in matrix.index:
                trophic_levels[group].append(tl[group])
        
        # Perform Kruskal-Wallis H-test
        h_stat, p_value = stats.kruskal(*[levels for levels in trophic_levels.values()])
        
        # Calculate mean and variation for each group
        group_stats = {
            group: {
                'mean_tl': np.mean(levels),
                'std_tl': np.std(levels),
                'cv': stats.variation(levels)
            }
            for group, levels in trophic_levels.items()
        }
        
        results[region] = {
            'kruskal_h': h_stat,
            'p_value': p_value,
            'group_stats': group_stats
        }
    
    return results

def analyze_diet_matrix_reliability(data):
    """Analyze statistical significance of diet matrix reliability"""
    results = {}
    
    for region, region_data in data.items():
        matrices = region_data['diet_matrices']
        if not matrices:
            continue
        
        # Calculate pairwise correlations between iterations
        correlations = []
        for i in range(len(matrices)):
            for j in range(i + 1, len(matrices)):
                # Focus on significant interactions (>0.05)
                mask = (matrices[i].values > 0.05) | (matrices[j].values > 0.05)
                if mask.any():
                    flat_i = matrices[i].values[mask]
                    flat_j = matrices[j].values[mask]
                    if len(flat_i) > 1:  # Need at least 2 points for correlation
                        # Use Spearman correlation for robustness
                        corr, p_value = stats.spearmanr(flat_i, flat_j)
                        if not np.isnan(corr):  # Only include valid correlations
                            correlations.append(corr)
        
        # Calculate mean correlation and confidence interval
        mean_corr = np.mean(correlations)
        ci = stats.t.interval(0.95, len(correlations)-1,
                            loc=mean_corr,
                            scale=stats.sem(correlations))
        
        results[region] = {
            'mean_correlation': mean_corr,
            'ci_lower': ci[0],
            'ci_upper': ci[1],
            'sample_size': len(correlations)
        }
    
    return results

def generate_statistical_report(output_file):
    """Generate comprehensive statistical analysis report"""
    # Load data
    print("Loading validation data...")
    data = load_validation_data()
    
    # Perform analyses
    print("Analyzing group consistency...")
    consistency_results = analyze_group_consistency(data)
    
    print("Analyzing regional differences...")
    regional_results = analyze_regional_differences(data)
    
    print("Analyzing trophic patterns...")
    trophic_results = analyze_trophic_patterns(data)
    
    print("Analyzing diet matrix reliability...")
    diet_results = analyze_diet_matrix_reliability(data)
    
    # Generate report
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("Statistical Analysis Report\n")
        f.write("=========================\n\n")
        
        # Group Consistency Results
        f.write("1. Group Consistency Analysis\n")
        f.write("--------------------------\n")
        for region, results in consistency_results.items():
            f.write(f"\n{region}:\n")
            f.write(f"Chi-square test: X^2 = {results['chi_square']:.1f}, p = {results['p_value']:.3f}\n")
            f.write(f"Mean coefficient of variation: {results['mean_cv']:.3f} (SD: {results['std_cv']:.3f})\n")
        
        # Regional Differences
        f.write("\n2. Regional Differences Analysis\n")
        f.write("-----------------------------\n")
        f.write(f"One-way ANOVA: F = {regional_results['anova_f']:.1f}, p = {regional_results['anova_p']:.3f}\n")
        f.write(f"Effect size (Cohen's f): {regional_results['cohens_f']:.3f}\n\n")
        f.write("Regional Statistics:\n")
        for region, stats in regional_results['region_stats'].items():
            f.write(f"{region}:\n")
            f.write(f"  Mean group size: {stats['mean']:.1f} (SD: {stats['std']:.1f})\n")
        
        # Trophic Patterns
        f.write("\n3. Trophic Level Analysis\n")
        f.write("----------------------\n")
        for region, results in trophic_results.items():
            f.write(f"\n{region}:\n")
            f.write(f"Kruskal-Wallis H-test: H = {results['kruskal_h']:.1f}, p = {results['p_value']:.3f}\n")
        
        # Diet Matrix Reliability
        f.write("\n4. Diet Matrix Reliability Analysis\n")
        f.write("--------------------------------\n")
        for region, results in diet_results.items():
            f.write(f"\n{region}:\n")
            f.write(f"Mean correlation: {results['mean_correlation']:.3f}\n")
            f.write(f"95% CI: [{results['ci_lower']:.3f}, {results['ci_upper']:.3f}]\n")
            f.write(f"Sample size: {results['sample_size']}\n")

def main():
    """Main execution function"""
    os.makedirs('manuscript/results', exist_ok=True)
    output_file = 'manuscript/results/statistical_analysis.txt'
    
    try:
        generate_statistical_report(output_file)
        print(f"\nStatistical analysis report generated: {output_file}")
    except Exception as e:
        print(f"Error generating statistical report: {str(e)}")

if __name__ == "__main__":
    main()
