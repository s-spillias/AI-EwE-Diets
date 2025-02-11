import os
import sys
import subprocess
import logging
from datetime import datetime

def setup_logging(output_dir):
    """Set up logging to both file and console"""
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    log_file = os.path.join(output_dir, 'validation.log')
    
    # Create a logger
    logger = logging.getLogger(output_dir)
    logger.setLevel(logging.INFO)
    
    # Prevent adding handlers multiple times
    if not logger.handlers:
        # Create file handler
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        # Create console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(message)s')
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    return logger

def run_validation(base_name, geojson_path, research_focus, num_iterations=5, num_processes=3, grouping_template='default', base_dir=None):
    """Run the complete validation process"""
    # Use provided base directory or create new one
    if base_dir is None:
        base_dir = f"MODELS/{base_name}/{base_name}_base"
        os.makedirs(base_dir, exist_ok=True)
    elif not os.path.exists(base_dir):
        raise ValueError(f"Base directory {base_dir} does not exist")
    
    logger = setup_logging(base_dir)
    
    logger.info(f"\nStarting validation process for {base_name}")
    logger.info(f"Number of iterations: {num_iterations}")
    logger.info(f"Number of parallel processes: {num_processes}")
    logger.info(f"Using grouping template: {grouping_template}")
    
    # Step 1: Run initial steps (steps 1-2)
    logger.info("\nRunning initial steps...")
    initial_cmd = [
        sys.executable,
        '01a_run_initial_steps.py',
        base_name,
        geojson_path,
        research_focus,
        grouping_template
    ]
    
    try:
        # Run initial steps and capture output
        process = subprocess.Popen(
            initial_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1  # Line buffered
        )
        
        # Capture and process output
        output, _ = process.communicate()
        
        # Log the output
        for line in output.splitlines():
            logger.info(line.rstrip())
        
        # Check for errors in output
        if "Failed to connect to the OBIS API" in output or "Error in main function:" in output:
            logger.error("Critical error detected in R script output")
            return False
        
        if process.returncode != 0:
            logger.error(f"Error in initial steps: Process returned {process.returncode}")
            return False
            
    except subprocess.CalledProcessError as e:
        logger.error(f"Error in initial steps: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error in initial steps: {e}")
        return False
        
    # Step 2: Run validation iterations (steps 3-7)
    logger.info("\nRunning validation iterations...")
    validation_cmd = [
        sys.executable,
        '01b_run_validation_iterations.py',
        base_name,
        str(num_iterations),
        str(num_processes)
    ]
    
    try:
        # Run validation iterations and capture output
        process = subprocess.Popen(
            validation_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1  # Line buffered
        )
        
        # Capture and process output
        output, _ = process.communicate()
        
        # Log the output
        for line in output.splitlines():
            logger.info(line.rstrip())
        
        if process.returncode != 0:
            logger.error(f"Error in validation iterations: Process returned {process.returncode}")
            return False
            
    except subprocess.CalledProcessError as e:
        logger.error(f"Error in validation iterations: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error in validation iterations: {e}")
        return False
        
    return True

def main():
    if len(sys.argv) < 4:
        print("Usage: python 01_run_validation_iterations.py <base_name> <geojson_path> <research_focus> [num_iterations] [num_processes] [grouping_template] [base_dir]")
        print("\nGrouping template options:")
        print("  default    - Use Default Grouping (default if not specified)")
        print("  upload     - Upload Custom Grouping JSON")
        print("  ecobase    - Search Ecobase for Template")
        print("  geojson    - Generate from Selected Area")
        sys.exit(1)
    
    base_name = sys.argv[1]
    geojson_path = sys.argv[2]
    research_focus = sys.argv[3]
    num_iterations = int(sys.argv[4]) if len(sys.argv) > 4 else 5
    num_processes = int(sys.argv[5]) if len(sys.argv) > 5 else 5
    grouping_template = sys.argv[6] if len(sys.argv) > 6 else 'default'
    base_dir = sys.argv[8] if len(sys.argv) > 8 else None

    
    # Validate grouping template choice
    valid_templates = ['default', 'upload', 'ecobase', 'geojson']
    if grouping_template not in valid_templates:
        print(f"Error: Invalid grouping template '{grouping_template}'")
        print("Valid options are:", ", ".join(valid_templates))
        sys.exit(1)
    
    # Set up logging using provided base_dir or default
    logger = setup_logging(base_dir or f"MODELS/{base_name}/{base_name}_base")
    logger.info(f"Starting complete validation workflow for {base_name}")
    
    success = run_validation(
        base_name=base_name,
        geojson_path=geojson_path,
        research_focus=research_focus,
        num_iterations=num_iterations,
        num_processes=num_processes,
        grouping_template=grouping_template,
        base_dir=base_dir
    )
    
    if success:
        logger.info("\nValidation workflow completed successfully")
        logger.info(f"Base model directory: {base_dir or f'MODELS/{base_name}_base'}")
        logger.info(f"Validation metadata: MODELS/{base_name}_validation/validation_metadata.json")
    else:
        logger.error("\nValidation workflow failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
