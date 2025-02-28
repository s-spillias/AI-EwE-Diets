import json
import os
from pathlib import Path
import pandas as pd
import numpy as np

def get_region_timing_data(region_path):
    """Extract timing data from a region's progress.json file."""
    progress_file = Path(region_path) / "progress.json"
    if not progress_file.exists():
        return None
    
    with open(progress_file) as f:
        progress = json.load(f)
    
    # Extract timing for each stage
    timing_data = {
        stage: data.get("timing", 0) 
        for stage, data in progress.items()
        if isinstance(data, dict)  # Ensure we only process valid stage entries
    }
    
    # Convert to hours for easier interpretation
    timing_data = {k: v/3600 for k, v in timing_data.items()}
    
    return timing_data

def analyze_regional_timing():
    """Analyze timing data across all validation regions."""
    models_dir = Path("MODELS")
    validation_dirs = []
    for region in ['v2_NorthernTerritory', 'v2_SouthEastInshore', 'v2_SouthEastOffshore']:
        base_dir = models_dir / region
        for i in range(1, 6):  # Validation runs 1 through 5
            validation_dir = base_dir / f"{region}_{i}"
            if validation_dir.exists():
                validation_dirs.append(validation_dir)
    
    timing_data = []
    
    for region_dir in validation_dirs:
        region_name = str(region_dir).split("\\")[-2]  # Get the parent directory name which contains the full region name
        timing = get_region_timing_data(region_dir)
        
        if timing:
            timing['region'] = region_name
            timing_data.append(timing)
    
    if not timing_data:
        return None
        
    # Convert to DataFrame for analysis
    df = pd.DataFrame(timing_data)
    
    # Calculate total processing time
    df['total_hours'] = df.drop(['region'], axis=1).sum(axis=1)
    
    # Group by region to get average timings
    region_stats = df.groupby('region').agg({
        'identify_species': 'mean',
        'harvest_sealifebase_data': 'mean',
        'group_species': 'mean',
        'gather_diet_data': 'mean',
        'construct_diet_matrix': 'mean',
        'generate_ewe_params': 'mean',
        'total_hours': ['mean', 'std']
    }).round(2)
    
    return df, region_stats

def format_time(value):
    """Format time values, handling NaN and missing values."""
    if pd.isna(value) or value == 0:
        return "---"
    elif value < 0.1:
        return f"{value:.2f}"
    else:
        return f"{value:.1f}"

def calculate_per_species_times(region_means, species_counts):
    """Calculate processing time per species for each stage and region."""
    per_species_times = {}
    for region in region_means.index:
        if region in species_counts:
            species_count = species_counts[region]
            per_species_times[region] = {
                stage: (value / species_count) * 3600 if value > 0 else 0  # Convert to seconds per species
                for stage, value in region_means.loc[region].items()
            }
    return per_species_times

def generate_timing_table(df, region_stats, species_counts):
    """Generate a LaTeX table with timing details for each region."""
    # Calculate means for each stage by region, filling NaN with 0
    region_means = df.groupby('region').mean().fillna(0)
    
    # Calculate per-species processing times
    per_species_times = calculate_per_species_times(region_means, species_counts)
    
    # Create the LaTeX table
    table = (
        "\\begin{table}[htbp]\n"
        "\\centering\n"
        "\\footnotesize\n"
        "\\caption{Computational requirements by region and processing stage}\n"
        "\\label{tab:timing_analysis}\n"
        "\\begin{tabular}{lccccccc}\n"
        "\\hline\n"
        "Region & Species & \\multicolumn{6}{c}{Processing Time (hours)} \\\\\n"
        "\\cline{3-8}\n"
        " & Count & Identification & Data & Grouping & Diet & Matrix & Parameter \\\\\n"
        " & & & Download & & Collection & Construction & Estimation \\\\\n"
        "\\hline\n"
    )
    
    # Add a row for each region in a specific order
    region_order = ['v2_NorthernTerritory', 'v2_SouthEastInshore', 'v2_SouthEastOffshore']
    for region in region_order:
        if region in region_means.index:
            species_count = species_counts.get(region, 0)
            # Add asterisk to download time for SouthEastInshore
            download_time = format_time(region_means.loc[region, 'harvest_sealifebase_data'])

            
            row = (
                f"{region.replace('_', ' ')} & "
                f"{species_count:,d} & "
                f"{format_time(region_means.loc[region, 'identify_species'])} & "
                f"{download_time} & "
                f"{format_time(region_means.loc[region, 'group_species'])} & "
                f"{format_time(region_means.loc[region, 'gather_diet_data'])} & "
                f"{format_time(region_means.loc[region, 'construct_diet_matrix'])} & "
                f"{format_time(region_means.loc[region, 'generate_ewe_params'])} \\\\\n"
            )
            table += row
    
    table += (
        "\\hline\n"
        "\\end{tabular}\n"
        "\\vspace{1ex}\n"
        "\\end{table}\n"
    )
    
    return table

def generate_timing_summary(species_counts=None):
    """Generate a summary of timing analysis for the manuscript."""
    result = analyze_regional_timing()
    if result is None:
        return "Insufficient timing data available for analysis."
    
    df, region_stats = result
    
    # Filter for completed runs and calculate means
    def safe_mean(series, min_threshold=0.001):  # Ignore very small values that might be errors
        valid = series[series > min_threshold]
        return valid.mean() if not valid.empty else 0
    
    # Get runs with at least species identification and data download completed
    completed_runs = df[
        (df['identify_species'] > 0) & 
        (df['harvest_sealifebase_data'] > 0)
    ]
    
    if completed_runs.empty:
        return "Insufficient timing data available for analysis."
    
    # Calculate means for each stage by region and create DataFrame
    region_means = pd.DataFrame(index=completed_runs['region'].unique())
    for stage in ['identify_species', 'harvest_sealifebase_data', 'group_species',
                 'gather_diet_data', 'construct_diet_matrix', 'generate_ewe_params']:
        region_means[stage] = completed_runs.groupby('region')[stage].apply(safe_mean)
    
    # Calculate per-species processing times
    per_species_times = {}
    for region in region_means.index:
        if region in species_counts:
            species_count = species_counts[region]
            per_species_times[region] = {
                stage: (value / species_count) * 3600 if value > 0 else 0  # Convert to hours/species to seconds/species
                for stage, value in region_means.loc[region].items()
            }
    
    # Calculate overall statistics
    region_totals = region_means.sum(axis=1)
    min_total = region_totals.min()
    max_total = region_totals.max()
    
    # Calculate percentage for downloading data
    total_download = region_means['harvest_sealifebase_data'].sum()
    total_time = region_totals.sum()
    download_percentage = (total_download / total_time * 100) if total_time > 0 else 0
    
    # Calculate overall means for the summary text
    stage_means = {
        stage: region_means[stage][region_means[stage] > 0].mean()
        for stage in region_means.columns
    }
    
    # Calculate average per-species processing times for key stages
    avg_download_time = np.mean([times['harvest_sealifebase_data']
                               for times in per_species_times.values()
                               if times['harvest_sealifebase_data'] > 0])
    avg_diet_time = np.mean([times['gather_diet_data'] 
                            for times in per_species_times.values() 
                            if times['gather_diet_data'] > 0])
    
    # Generate prose summary
    summary = (
        "The computational requirements of the AI framework varied across regions. "
        f"Total processing time ranged from {min_total:.1f} to {max_total:.1f} hours "
        f"across regions. The most time-intensive stage was the downloading of biological data from online databases, "
        f"accounting for approximately {download_percentage:.0f}\\% "
        "of the total processing time. Species identification typically required "
        f"{stage_means['identify_species']:.2f} hours, while the AI-driven species grouping process averaged "
        f"{stage_means['group_species']:.2f} hours. Diet data collection and matrix construction required "
        f"{stage_means['gather_diet_data']:.1f} and {stage_means['construct_diet_matrix']:.2f} hours respectively, "
        f"with final parameter estimation taking {stage_means['generate_ewe_params']:.2f} hours. "
        f"On average, the framework required {avg_download_time:.1f} seconds per species for data downloading and "
        f"{avg_diet_time:.1f} seconds per species for diet data collection, though these rates varied considerably "
        "between regions due to differences in data availability and species complexity."
    )
    
    # Generate detailed table
    if species_counts:
        table = generate_timing_table(completed_runs, region_stats, species_counts)
        return summary, table
    
    return summary

if __name__ == "__main__":
    # Example species counts - these should be provided by the analysis script
    species_counts = {
        'v2_NorthernTerritory': 11362,
        'v2_SouthEastInshore': 13901,
        'v2_SouthEastOffshore': 15821
    }
    summary, table = generate_timing_summary(species_counts)
    print("\nSummary:")
    print(summary)
    print("\nTable:")
    print(table)
