import os
import pandas as pd
import numpy as np

def get_mean_diet_matrix(base_name):
    """Calculate mean diet matrix from all iterations for a region"""
    models_dir = 'MODELS'
    matrices = []
    
    # Collect all diet matrices for this region
    for dir_name in os.listdir(models_dir):
        if dir_name.startswith(f"{base_name}_validation_"):
            matrix_path = os.path.join(models_dir, dir_name, '05_diet_matrix.csv')
            if os.path.exists(matrix_path):
                matrix = pd.read_csv(matrix_path, index_col=0)
                matrices.append(matrix)
    
    if not matrices:
        return None
        
    # Calculate mean values
    mean_matrix = sum(matrices) / len(matrices)
    
    # Add the three new columns
    new_cols = pd.DataFrame(index=mean_matrix.index, columns=['PA', 'Mag.', 'Notes'])
    
    # Combine the new columns with the mean matrix
    final_matrix = pd.concat([new_cols, mean_matrix], axis=1)
    
    return final_matrix

def main():
    # Create results directory if it doesn't exist
    os.makedirs('manuscript/results', exist_ok=True)
    
    # Process each region
    regions = ['NorthernTerritory', 'SouthEastInshore', 'SouthEastOffshore']
    writer = pd.ExcelWriter('manuscript/results/mean_diet_matrices.xlsx', engine='xlsxwriter')
    
    for region in regions:
        mean_matrix = get_mean_diet_matrix(region)
        if mean_matrix is not None:
            mean_matrix.to_excel(writer, sheet_name=region)
    
    writer.close()
    print("Mean diet matrices exported to: manuscript/results/mean_diet_matrices.xlsx")

if __name__ == "__main__":
    main()
