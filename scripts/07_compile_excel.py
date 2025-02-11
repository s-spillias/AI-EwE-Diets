import sys
import os
import json
import logging
import pandas as pd
import openpyxl
import gc

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def compile_excel(model_dir):
    writer = None
    try:
        # Load the EwE parameters
        ewe_params_file = os.path.join(model_dir, "06_ewe_params.json")
        with open(ewe_params_file, 'r') as f:
            ewe_matrix = json.load(f)

        # Ensure all arrays in ewe_matrix have the same length
        max_length = max(len(v) for v in ewe_matrix.values())
        for key in ewe_matrix:
            ewe_matrix[key] = ewe_matrix[key] + [''] * (max_length - len(ewe_matrix[key]))

        # Read the diet matrix CSV file
        diet_matrix_file = os.path.join(model_dir, "05_diet_matrix.csv")
        diet_matrix = pd.read_csv(diet_matrix_file)

        # Create an Excel file with two sheets
        output_excel_file = os.path.join(model_dir, "07_raw_ewe.xlsx")
        
        # Convert ewe_matrix to DataFrame
        ewe_df = pd.DataFrame(ewe_matrix)
        
        # Use context manager for ExcelWriter
        with pd.ExcelWriter(output_excel_file, engine='openpyxl') as writer:
            # Write both sheets
            ewe_df.to_excel(writer, sheet_name='EwE Matrix', index=False)
            diet_matrix.to_excel(writer, sheet_name='Diet Matrix', index=False)
            
            # Ensure at least one sheet is visible
            writer.book.active = writer.book['EwE Matrix']
        
        # Clean up references
        del ewe_df
        del diet_matrix
        gc.collect()
        
        logging.info(f"EwE and Diet matrices compiled and saved to {output_excel_file}")
        return True
        
    except Exception as e:
        logging.error(f"An error occurred while compiling the Excel file: {str(e)}")
        if writer is not None:
            try:
                writer.close()
            except:
                pass
        raise
    finally:
        # Force garbage collection
        gc.collect()

if __name__ == "__main__":
    # The model directory should be passed as an argument when running the script
    if len(sys.argv) > 1:
        model_dir = sys.argv[1]
        compile_excel(model_dir)
    else:
        print("Please provide the model directory as an argument.")
