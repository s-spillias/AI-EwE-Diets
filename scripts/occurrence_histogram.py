import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# Read the data
df = pd.read_csv('MODELS/test_model1/01_species_list.csv')

# Get the occurrence counts directly from the CSV
species_counts = df['occurrence_count']

# Print frequency distribution
value_counts = species_counts.value_counts().sort_index()
print("\nFrequency distribution of species occurrences:")
print("Number of occurrences | Number of species")
print("-" * 40)
for count, freq in value_counts.items():
    print(f"{count:>19} | {freq:>16}")
print("\nTotal unique species:", len(species_counts))

# Create figure with custom size
plt.figure(figsize=(12, 7))

# Create log-spaced bins
min_count = species_counts.min()
max_count = species_counts.max()
bins = np.logspace(np.log10(min_count), np.log10(max_count), 50)

plt.hist(species_counts, bins=bins, edgecolor='black', alpha=0.7)
plt.xscale('log')
plt.yscale('log')  # Log scale for y-axis too since counts vary widely

# Add labels and title
plt.xlabel('Number of Occurrences (log scale)')
plt.ylabel('Number of Species')
plt.title('Distribution of Species Occurrences in Northern Territory')

# Add grid
plt.grid(True, alpha=0.3)

# Add summary statistics text box
# Calculate additional statistics
percentile_95 = np.percentile(species_counts, 95)
percentile_99 = np.percentile(species_counts, 99)

stats_text = f'Total Species: {len(species_counts):,}\n'
stats_text += f'Mean Occurrences: {species_counts.mean():.1f}\n'
stats_text += f'Median Occurrences: {species_counts.median():.1f}\n'
stats_text += f'95th Percentile: {percentile_95:.1f}\n'
stats_text += f'99th Percentile: {percentile_99:.1f}\n'
stats_text += f'Max Occurrences: {int(species_counts.max()):,}'

# Print summary of the distribution
print("\nDistribution Summary:")
print(f"Single occurrence species: {len(species_counts[species_counts == 1]):,} ({len(species_counts[species_counts == 1])/len(species_counts)*100:.1f}%)")
print(f"Species with >100 occurrences: {len(species_counts[species_counts > 100]):,} ({len(species_counts[species_counts > 100])/len(species_counts)*100:.1f}%)")
print(f"Species with >1000 occurrences: {len(species_counts[species_counts > 1000]):,} ({len(species_counts[species_counts > 1000])/len(species_counts)*100:.1f}%)")

# Print frequency distribution
value_counts = species_counts.value_counts().sort_index()
print("\nFrequency distribution of species occurrences:")
print("Number of occurrences | Number of species")
print("-" * 40)
for count, freq in value_counts.items():
    print(f"{count:>19} | {freq:>16}")
plt.text(0.95, 0.95, stats_text,
         transform=plt.gca().transAxes,
         verticalalignment='top',
         horizontalalignment='right',
         bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

# Adjust layout to prevent text cutoff
plt.tight_layout()

# Save the plot
plt.savefig('manuscript/figures/species_occurrence_histogram.png', dpi=300, bbox_inches='tight')
plt.close()
