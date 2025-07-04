import os
import sys
import json
import shutil
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

def run_initial_steps(base_name, geojson_path, research_focus, grouping_template='default', template_file=None, force_grouping=False):
    """Run steps 1-2 of the model workflow"""
    output_dir = f"MODELS/{base_name}/{base_name}_base"
    os.makedirs(output_dir, exist_ok=True)
    
    # Set up logging
    logger = setup_logging(output_dir)
    logger.info(f"\nStarting initial steps for {base_name}")
    
    # Save AI configuration
    ai_config = {
        'groupingTemplate': {
            'type': grouping_template,
            'path': template_file if grouping_template == 'upload' else ('03_grouping_template.json' if grouping_template == 'default' else None)
        },
        'groupSpeciesAI': 'claude',
        'constructDietMatrixAI': 'claude',
        'eweParamsAI': 'claude',
        'ragSearchAI': 'aws_claude',
        'forceGrouping': force_grouping,
        'researchFocus': research_focus
    }
    
    ai_config_file = os.path.join(output_dir, 'ai_config.json')
    with open(ai_config_file, 'w') as f:
        json.dump(ai_config, f, indent=2)
    logger.info(f"Saved AI configuration to {ai_config_file}")
    
    # Run main.py for steps 1-2
    cmd_args = [
        sys.executable,
        'main.py',
        '--model_name', f"{base_name}/{base_name}_base",
        '--geojson_path', geojson_path,
        '--research_focus', research_focus,
        '--grouping_template', grouping_template,
        '--early_stop', '2'
    ]
    
    if force_grouping:
        cmd_args.append('--force_grouping')
    
    if template_file and grouping_template == 'upload':
        cmd_args.extend(['--template_file', template_file])
    
    try:
        # Run the command and capture output
        process = subprocess.Popen(
            cmd_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1  # Line buffered
        )
        
        output, _ = process.communicate()  # No timeout
        
        # Log the output
        for line in output.splitlines():
            logger.info(line.rstrip())
            
        # Check for errors in output
        if "Failed to connect to the OBIS API" in output or "Error in main function:" in output:
            logger.error("Critical error detected in R script output")
            raise RuntimeError("R script failed with critical error")
            
        if process.returncode != 0:
            logger.error(f"Error running initial steps: Process returned {process.returncode}")
            raise RuntimeError(f"Initial steps failed with return code {process.returncode}")
            
        logger.info("Initial steps completed successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running initial steps: {e}")
        raise RuntimeError(str(e))
    except Exception as e:
        logger.error(f"Unexpected error running initial steps: {e}")
        raise RuntimeError(str(e))

def main():
    if len(sys.argv) < 4:
        print("Usage: python 01a_run_initial_steps.py <base_name> <geojson_path> <research_focus> [grouping_template] [template_file] [--force_grouping]")
        print("\nGrouping template options:")
        print("  default    - Use Default Grouping (default if not specified)")
        print("  upload     - Upload Custom Grouping JSON (specify template file path)")
        print("  ecobase    - Search Ecobase for Template")
        print("  geojson    - Generate from Selected Area")
        sys.exit(1)
    
    base_name = sys.argv[1]
    geojson_path = sys.argv[2]
    research_focus = sys.argv[3]
    grouping_template = sys.argv[4] if len(sys.argv) > 4 else 'default'
    template_file = sys.argv[5] if len(sys.argv) > 5 else None
    force_grouping = '--force_grouping' in sys.argv
    
    # Validate grouping template choice
    valid_templates = ['default', 'upload', 'ecobase', 'geojson']
    if grouping_template not in valid_templates:
        print(f"Error: Invalid grouping template '{grouping_template}'")
        print("Valid options are:", ", ".join(valid_templates))
        sys.exit(1)
    
    
    # Set up base directory and logging
    base_dir = f"MODELS/{base_name}/{base_name}_base"
    logger = setup_logging(base_dir)
    logger.info(f"Starting initial steps workflow for {base_name}")
    
    try:
        success = run_initial_steps(
            base_name=base_name,
            geojson_path=geojson_path,
            research_focus=research_focus,
            grouping_template=grouping_template,
            template_file=template_file,
            force_grouping=force_grouping
        )
        
        if not success:
            logger.error("\nInitial steps failed")
            sys.exit(1)
            
        logger.info("\nInitial steps completed successfully")
        logger.info(f"Base model directory: {base_dir}")
    except Exception as e:
        logger.error(f"\nCritical error occurred: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
