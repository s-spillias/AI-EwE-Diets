import os
import subprocess
import sys
import re
import json
import webbrowser
import time
import argparse
import shutil
from datetime import datetime
from scripts.serve_map_interface import shapefile_to_geojson

# ANSI escape codes for colors
GREEN = '\033[92m'
RED = '\033[91m'
RESET = '\033[0m'

def print_green(text):
    print(f"{GREEN}{text}{RESET}")

def print_red(text):
    print(f"{RED}{text}{RESET}")

def check_r_packages():
    required_packages = ['robis', 'sf', 'dplyr', 'R.utils']
    r_script = ';'.join([f"if (!require('{pkg}')) {{ quit(status=1) }}" for pkg in required_packages])
    result = subprocess.run(['Rscript', '-e', r_script], capture_output=True, text=True)
    if result.returncode != 0:
        print_red("Error: One or more required R packages are missing.")
        print_red(f"Please install the following R packages: {', '.join(required_packages)}")
        return False
    return True

def parse_r_error(error_message):
    error_match = re.search(r'Error.*', error_message, re.DOTALL)
    if error_match:
        return error_match.group(0)
    return error_message
def run_r_script(script_path, shapefile_path, output_file, coverage_threshold=None):
    if not check_r_packages():
        return False

    try:
        abs_shapefile_path = os.path.abspath(shapefile_path)
        abs_output_file = os.path.abspath(output_file)
        print(f"Running R script with shapefile: {abs_shapefile_path}")
        print(f"Output file: {abs_output_file}")
        
        if not os.path.exists(abs_shapefile_path):
            print_red(f"Error: Shapefile not found at {abs_shapefile_path}")
            print("Checking EwE directory contents:")
            list_directory_contents('EwE')
            return False

        cmd = ['Rscript', '--vanilla', script_path, abs_shapefile_path, abs_output_file]
        if coverage_threshold is not None:
            cmd.append(str(coverage_threshold))

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(result.stdout)
        
        # Check for OBIS API errors in the output
        if "Failed to connect to the OBIS API" in result.stdout or "Failed to connect to the OBIS API" in result.stderr:
            print_red("OBIS API connection error detected")
            raise RuntimeError("OBIS API connection failed")
            
        if result.stderr:
            print_red("Warnings or messages:")
            print(result.stderr)
            
        # Check if the output file was created and has content
        if not os.path.exists(abs_output_file) or os.path.getsize(abs_output_file) == 0:
            print_red("Error: Output file was not created or is empty")
            return False
            
        return True
    except subprocess.CalledProcessError as e:
        print_red(f"Error running R script: {e}")
        print_red("Standard output:")
        print(e.stdout)
        print_red("Standard error:")
        print(parse_r_error(e.stderr))
        return False


def run_python_script(script_path, *args):
    if not os.path.exists(script_path):
        print_red(f"Error: {script_path} not found.")
        print_red(f"Current working directory: {os.getcwd()}")
        print_red(f"Full path of script: {os.path.abspath(script_path)}")
        return False
    try:
        abs_args = [os.path.abspath(arg) if os.path.exists(arg) else arg for arg in args]
        print(f"Running Python script: {script_path}")
        print(f"With arguments: {abs_args}")
        
        # Create log file in the output directory
        script_name = os.path.basename(os.path.splitext(script_path)[0]) + '.log'
        # For functions that take output_dir as an argument, it will be the last arg
        output_dir = next((arg for arg in reversed(abs_args) if os.path.isdir(arg)), os.path.dirname(script_path))
        log_file = os.path.join(output_dir, script_name)
        print(f"Output will be logged to: {log_file}")
        
        # Open log file and process
        with open(log_file, 'w') as log:
            process = subprocess.Popen(
                [sys.executable, script_path] + abs_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Function to handle output streams
            def handle_output(stream):
                for line in iter(stream.readline, ''):
                    print(line, end='')  # Print to console
                    log.write(line)      # Write to log
                    log.flush()          # Ensure immediate write
            
            # Create threads to handle stdout and stderr
            from threading import Thread
            stdout_thread = Thread(target=handle_output, args=(process.stdout,))
            stderr_thread = Thread(target=handle_output, args=(process.stderr,))
            
            # Start threads
            stdout_thread.start()
            stderr_thread.start()
            
            # Wait for process to complete
            return_code = process.wait()
            
            # Wait for output threads to complete
            stdout_thread.join()
            stderr_thread.join()
            
            # Check return code
            if return_code != 0:
                print_red(f"Error running Python script {script_path}")
                print_red(f"Return code: {return_code}")
                return False
                
            return True
            
    except Exception as e:
        print_red(f"Error running Python script {script_path}: {e}")
        return False


def identify_species(geojson_path, output_file, coverage_threshold=None):
    script_path = os.path.join('scripts', '01_identify_species.R')
    if not os.path.exists(script_path):
        print_red(f"Error: {script_path} not found.")
        print_red(f"Current working directory: {os.getcwd()}")
        print_red(f"Full path of script: {os.path.abspath(script_path)}")
        return False
    
    return run_r_script(script_path, geojson_path, output_file, coverage_threshold)


def harvest_sealifebase_data(species_file, output_dir):
    script_path = os.path.join('scripts', '02_download_data.py')
    return run_python_script(script_path, species_file, output_dir)

def group_species(excel_file, output_dir, force_grouping):
    script_path = os.path.join('scripts', '03_group_species.py')
    success = run_python_script(script_path, excel_file, output_dir, '--force_grouping' if force_grouping else '')
    # Check if output files were created to determine success
    output_files = [
        os.path.join(output_dir, "03_grouped_species_hierarchy.json"),
        os.path.join(output_dir, "03_grouped_species_assignments.json")
    ]
    return success and all(os.path.exists(f) for f in output_files)

def gather_diet_data(output_dir):
    script_path = os.path.join('scripts', '04_gather_diet_data.py')
    success = run_python_script(script_path, output_dir)
    # Check if output file was created to determine success
    output_file = os.path.join(output_dir, "04d_diet_summaries.json")
    return success and os.path.exists(output_file)

def construct_diet_matrix(output_dir):
    script_path = os.path.join('scripts', '05_construct_diet_matrix.py')
    success = run_python_script(script_path, '--output_dir', output_dir)
    # Check if output file was created to determine success
    output_file = os.path.join(output_dir, "05_diet_matrix.csv")
    return success and os.path.exists(output_file)

def generate_ewe_params(output_dir):
    script_path = os.path.join('scripts', '06_ewe_params.py')
    success = run_python_script(script_path, output_dir)
    # Check if output file was created to determine success
    output_file = os.path.join(output_dir, "06_ewe_params.json")
    return success and os.path.exists(output_file)

def compile_excel(output_dir):
    script_path = os.path.join('scripts', '07_compile_excel.py')
    success = run_python_script(script_path, output_dir)
    # Check if output file was created to determine success
    output_file = os.path.join(output_dir, "07_ewe_model.xlsx")
    return success and os.path.exists(output_file)

def read_research_focus(output_dir):
    ai_config_path = os.path.join(output_dir, 'ai_config.json')
    if os.path.exists(ai_config_path):
        with open(ai_config_path, 'r') as f:
            config = json.load(f)
            return config.get('researchFocus', '')
    return ''

def wait_for_user_input():
    """Wait for user input and return the output directory name"""
    print_green("Waiting for user to select output directory and draw region...")
    
    # Create state file indicating we're waiting for input
    state_file = 'interface_state.json'
    with open(state_file, 'w') as f:
        json.dump({"status": "waiting"}, f)
    
    # Start the server
    server_script = os.path.join('scripts', 'serve_map_interface.py')
    server_process = subprocess.Popen([sys.executable, server_script])
    
    # Wait a moment for server to start
    time.sleep(2)
    
    # Open in default browser
    webbrowser.open('http://localhost:8000/scripts/00_map_interface.html')
    
    try:
        # Wait for state file to be updated
        while True:
            try:
                with open(state_file, 'r') as f:
                    state = json.load(f)
                    if state["status"] == "complete":
                        output_dir = state["output_directory"]
                        print_green(f"Received input in directory: {output_dir}")
                        return output_dir
            except (json.JSONDecodeError, KeyError):
                pass  # File might be in the middle of being written
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        print_red("\nProcess interrupted by user")
        return None
    finally:
        # Clean up
        server_process.terminate()
        if os.path.exists(state_file):
            os.remove(state_file)
        time.sleep(1)

def update_progress(output_dir, step, success, timing=None):
    progress_file = os.path.join(output_dir, 'progress.json')
    progress = {}
    if os.path.exists(progress_file):
        with open(progress_file, 'r') as f:
            progress = json.load(f)
    
    # Update step status
    progress[step] = {
        'success': success,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Add timing if provided
    if timing is not None:
        progress[step]['timing'] = timing
    
    with open(progress_file, 'w') as f:
        json.dump(progress, f, indent=2)

def read_progress(output_dir):
    progress_file = os.path.join(output_dir, 'progress.json')
    if os.path.exists(progress_file):
        with open(progress_file, 'r') as f:
            return json.load(f)
    return {}

def parse_arguments():
    parser = argparse.ArgumentParser(description='EwE Workflow')
    parser.add_argument('--model_name', help='Name of the model directory in MODELS/')
    parser.add_argument('--geojson_path', help='Path to the GeoJSON or ZIP file')
    parser.add_argument('--research_focus', help='Research focus for the model')
    parser.add_argument('--coverage_threshold', type=float, default=1.0,
                      help='Value between 0 and 1 to filter species by occurrence coverage (default: 1.0)')
    parser.add_argument('--grouping_template', choices=['default', 'upload', 'ecobase', 'geojson'], default='default', 
                      help='Grouping template option (default: generate from area, upload: custom JSON, ecobase: search template)')
    parser.add_argument('--ecobase_search', help='Ecobase search term (if grouping_template is "ecobase")')
    parser.add_argument('--group_species_ai', choices=['claude', 'aws_claude', 'gemini', 'gemma2', 'llama3', 'mixtral'], default='claude', help='AI model for Group Species')
    parser.add_argument('--construct_diet_matrix_ai', choices=['claude', 'aws_claude', 'gemini', 'gemma2', 'llama3', 'mixtral'], default='claude', help='AI model for Construct Diet Matrix')
    parser.add_argument('--ewe_params_ai', choices=['claude', 'aws_claude', 'gemini', 'gemma2', 'llama3', 'mixtral'], default='claude', help='AI model for EwE Parameters')
    parser.add_argument('--rag_search_ai', choices=['aws_claude', 'azure_openai', 'openai', 'anthropic'], default='aws_claude', help='AI model for RAG Search')
    parser.add_argument('--resume', action='store_true', help='Resume processing from last successful step')
    parser.add_argument('--early_stop', type=int, help='Stop after specified step number (0-7)')
    parser.add_argument('--force_grouping', action='store_true', help='Force grouping without adding new groups to reference groups')
    return parser.parse_args()

def process_input_file(input_path, output_dir):
    geojson_path = os.path.join(output_dir, 'user_input.geojson')
    success = shapefile_to_geojson(input_path, geojson_path)
    return geojson_path if success else None

def main():
    args = parse_arguments()

    if args.coverage_threshold <= 0 or args.coverage_threshold > 1:
        print_red("Error: Coverage threshold must be between 0 and 1")
          # Change to the EwE directory
    ewe_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(ewe_dir)

    print_green("Starting EwE Workflow...")
    print(f"Current working directory: {os.getcwd()}")

    # Check if resuming an existing model
    if args.resume:
        if not args.model_name:
            print_red("Error: --model_name is required when using --resume")
            return
        output_dir = os.path.join('MODELS', args.model_name)
        if not os.path.exists(output_dir):
            print_red(f"Error: Model directory '{args.model_name}' not found in MODELS/")
            return
        print_green(f"Resuming model from directory: {output_dir}")
        geojson_path = os.path.join(output_dir, 'user_input.geojson')
    # Check if arguments were provided for a new model
    elif args.model_name and args.geojson_path and args.research_focus:
        # Use command-line arguments
        output_dir = os.path.join('MODELS', args.model_name)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        geojson_path = process_input_file(args.geojson_path, output_dir)
        if not geojson_path:
            print_red(f"Error: Failed to process the input file {args.geojson_path}")
            return
        
        # Save AI configuration
        ai_config = {
            'groupingTemplate': {
                'type': args.grouping_template,
                'path': '03_grouping_template.json' if args.grouping_template == 'default' else None
            },
            'groupSpeciesAI': args.group_species_ai,
            'constructDietMatrixAI': args.construct_diet_matrix_ai,
            'eweParamsAI': args.ewe_params_ai,
            'ragSearchAI': args.rag_search_ai,
            'forceGrouping': args.force_grouping,
            'researchFocus': args.research_focus
        }
        
        if args.grouping_template == 'ecobase' and args.ecobase_search:
            ai_config['groupingTemplate']['ecobase_search_term'] = args.ecobase_search
        
        with open(os.path.join(output_dir, 'ai_config.json'), 'w') as f:
            json.dump(ai_config, f, indent=2)
    else:
        # Use the interface
        output_dir = wait_for_user_input()
        if not output_dir:
            return
        geojson_path = os.path.join(output_dir, 'user_input.geojson')

    print_green(f"Using output directory: {output_dir}")
    print(f"GeoJSON path: {os.path.abspath(geojson_path)}")

    # Read AI configuration
    ai_config_path = os.path.join(output_dir, 'ai_config.json')
    if not os.path.exists(ai_config_path):
        print_red(f"Error: AI configuration file not found at {ai_config_path}")
        return
        
    try:
        with open(ai_config_path, 'r') as f:
            ai_config = json.load(f)
    except json.JSONDecodeError as e:
        print_red(f"Error reading AI configuration: {e}")
        return
    except Exception as e:
        print_red(f"Unexpected error reading AI configuration: {e}")
        return

    print(f"Grouping Template: {ai_config['groupingTemplate']['type']}")
    print(f"Group Species AI: {ai_config['groupSpeciesAI']}")
    print(f"Construct Diet Matrix AI: {ai_config['constructDietMatrixAI']}")
    print(f"EwE Parameters AI: {ai_config['eweParamsAI']}")
    print(f"RAG Search AI: {ai_config['ragSearchAI']}")
    print(f"Force Grouping: {ai_config.get('forceGrouping', False)}")
    print(f"Research Focus: {ai_config.get('researchFocus', '')}")

    species_output = os.path.join(output_dir, '01_species_list.csv')

    # Read progress
    progress = read_progress(output_dir)



    # Step 1: Identify Species (R version)
    if not progress.get('identify_species', {}).get('success'):
        print_green("\nStep 1: Identifying Species (R version)")
        start_time = time.time()

        success = identify_species(geojson_path, species_output, args.coverage_threshold)

        timing = time.time() - start_time
        update_progress(output_dir, 'identify_species', success, timing)
        if not success:
            return
    else:
        print_green("\nStep 1: Identifying Species (Already completed)")

    if args.early_stop == 1:
        print_green("Stopping after step 1 as requested")
        return

    # Step 2: Harvest SeaLifeBase Data
    if not progress.get('harvest_sealifebase_data', {}).get('success'):
        print_green("Step 2: Harvesting Databases")
        start_time = time.time()
        success = harvest_sealifebase_data(species_output, output_dir)
        timing = time.time() - start_time
        update_progress(output_dir, 'harvest_sealifebase_data', success, timing)
        if not success:
            return
    else:
        print_green("Step 2: Harvesting SeaLifeBase Data (Already completed)")

    if args.early_stop == 2:
        print_green("Stopping after step 2 as requested")
        return

    # Step 3: Group Species
    if not progress.get('group_species', {}).get('success'):
        print_green("Step 3: Grouping Species")
        start_time = time.time()
                # Determine reference groups path based on template type
        if ai_config['groupingTemplate']['type'] == 'geojson':
            # Step 0: Generate AI Groups
            if not progress.get('generate_ai_groups', {}).get('success'):
                print_green("\nStep 0: Generating AI Groups")
                start_time = time.time()
                success = generate_ai_groups(output_dir)
                timing = time.time() - start_time
                update_progress(output_dir, 'generate_ai_groups', success, timing)
                if not success:
                    return
            else:
                print_green("\nStep 0: Generating AI Groups (Already completed)")

            if args.early_stop == 0:
                print_green("Stopping after step 0 as requested")
                return
            
            # Use the generated groups file
            reference_groups = os.path.join(output_dir, '03_grouping_template.json')
        else:
            # Use the appropriate template based on the configuration
            if ai_config['groupingTemplate']['type'] == 'default':
                reference_groups = '03_grouping_template.json'
            elif ai_config['groupingTemplate']['type'] == 'upload':
                # For uploaded templates, the path should be specified in the config
                reference_groups = ai_config['groupingTemplate'].get('path', '03_grouping_template.json')
            elif ai_config['groupingTemplate']['type'] == 'ecobase':
                # For ecobase, we'll use the default template as fallback
                reference_groups = '03_grouping_template.json'
            else:
                print_red(f"Unknown grouping template type: {ai_config['groupingTemplate']['type']}")
                return
        success = group_species(reference_groups, output_dir, ai_config.get('forceGrouping', False))
        timing = time.time() - start_time
        update_progress(output_dir, 'group_species', success, timing)
        if not success:
            return
    else:
        print_green("Step 3: Grouping Species (Already completed)")

    if args.early_stop == 3:
        print_green("Stopping after step 3 as requested")
        return

    # Step 4: Gather Diet Data
    if not progress.get('gather_diet_data', {}).get('success'):
        print_green("Step 4: Gathering Diet Data")
        start_time = time.time()
        success = gather_diet_data(output_dir)
        timing = time.time() - start_time
        update_progress(output_dir, 'gather_diet_data', success, timing)
        if not success:
            return
    else:
        print_green("Step 4: Gathering Diet Data (Already completed)")

    if args.early_stop == 4:
        print_green("Stopping after step 4 as requested")
        return

    # Step 5: Construct Diet Matrix
    if not progress.get('construct_diet_matrix', {}).get('success'):
        print_green("Step 5: Constructing Diet Matrix")
        start_time = time.time()
        success = construct_diet_matrix(output_dir)
        timing = time.time() - start_time
        update_progress(output_dir, 'construct_diet_matrix', success, timing)
        if not success:
            return
    else:
        print_green("Step 5: Constructing Diet Matrix (Already completed)")

    if args.early_stop == 5:
        print_green("Stopping after step 5 as requested")
        return

    # Step 6: Generate EwE Parameters
    if not progress.get('generate_ewe_params', {}).get('success'):
        print_green("Step 6: Generating EwE Parameters")
        start_time = time.time()
        success = generate_ewe_params(output_dir)
        timing = time.time() - start_time
        update_progress(output_dir, 'generate_ewe_params', success, timing)
        if not success:
            return
    else:
        print_green("Step 6: Generating EwE Parameters (Already completed)")

    if args.early_stop == 6:
        print_green("Stopping after step 6 as requested")
        return

    # Step 7: Compile Excel
    if not progress.get('compile_excel', {}).get('success'):
        print_green("Step 7: Compiling Excel")
        start_time = time.time()
        success = compile_excel(output_dir)
        timing = time.time() - start_time
        update_progress(output_dir, 'compile_excel', success, timing)
        if not success:
            return
    else:
        print_green("Step 7: Compiling Excel (Already completed)")

    print_green("EwE Workflow completed.")

if __name__ == "__main__":
    main()
