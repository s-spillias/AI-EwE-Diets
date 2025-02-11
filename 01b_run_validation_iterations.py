import os
import sys
import json
import shutil
import subprocess
import logging
from multiprocessing import Pool
from datetime import datetime
import signal

def init_worker():
    """Initialize worker process to ignore SIGINT"""
    signal.signal(signal.SIGINT, signal.SIG_IGN)

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

def run_model_iteration(args):
    """Run a single iteration of the model starting from step 3 (grouping)"""
    base_name, iteration, base_dir = args
    output_dir = f"MODELS/{base_name}/{base_name}_{iteration}"
    
    # Set up logging for this iteration
    logger = setup_logging(output_dir)
    logger.info(f"\nStarting iteration {iteration}")
    
    # Copy entire base directory to create new iteration directory
    shutil.copytree(base_dir, output_dir, dirs_exist_ok=True)
    
    # Run main.py with resume flag to continue from step 3
    cmd_args = [
        sys.executable,
        'main.py',
        '--resume',
        '--model_name', f"{base_name}/{base_name}_{iteration}",
    ]
    
    try:
        # Run the command and capture output
        process = subprocess.Popen(
            cmd_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1  # Line buffered
        )
        
        # Capture and process output with timeout
        try:
            output, _ = process.communicate(timeout=300)  # 5 minute timeout
            
            # Log the output
            for line in output.splitlines():
                logger.info(line.rstrip())
                
            # Check for errors in output
            if "Failed to connect to the OBIS API" in output or "Error in main function:" in output:
                logger.error(f"Critical error detected in iteration {iteration}")
                raise RuntimeError(f"Iteration {iteration} failed with critical error")
                
            if process.returncode != 0:
                logger.error(f"Error in iteration {iteration}: Process returned {process.returncode}")
                raise RuntimeError(f"Iteration {iteration} failed with return code {process.returncode}")
                
            logger.info(f"Completed iteration {iteration}")
            return output_dir
            
        except subprocess.TimeoutExpired:
            process.kill()
            logger.error(f"Iteration {iteration} timed out after 5 minutes")
            raise RuntimeError(f"Iteration {iteration} timed out")
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Error in iteration {iteration}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in iteration {iteration}: {e}")
        raise
    finally:
        # Ensure any subprocess resources are cleaned up
        try:
            subprocess._cleanup()
        except:
            pass

def main():
    if len(sys.argv) < 2:
        print("Usage: python 01b_run_validation_iterations.py <base_name> [num_iterations] [num_processes]")
        sys.exit(1)
    
    base_name = sys.argv[1]
    num_iterations = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    num_processes = int(sys.argv[3]) if len(sys.argv) > 3 else 3  # Default to 3 parallel processes
    
    base_dir = f"MODELS/{base_name}/{base_name}_base"
    if not os.path.exists(base_dir):
        print(f"Error: Base model directory not found: {base_dir}")
        print("Please run 01a_run_initial_steps.py first")
        sys.exit(1)
        
    # Check if initial steps completed successfully by looking for required files
    required_files = ['01_species_list.csv']
    missing_files = [f for f in required_files if not os.path.exists(os.path.join(base_dir, f))]
    if missing_files:
        print(f"Error: Initial steps did not complete successfully. Missing files: {', '.join(missing_files)}")
        print("Please run 01a_run_initial_steps.py again")
        sys.exit(1)
    
    # Create validation directory for metadata
    validation_dir = f"MODELS/{base_name}"
    os.makedirs(validation_dir, exist_ok=True)
    
    # Set up logging for the main validation process
    logger = setup_logging(validation_dir)
    logger.info(f"Starting validation process for {base_name}")
    logger.info(f"Number of iterations: {num_iterations}")
    logger.info(f"Number of parallel processes: {num_processes}")
    
    # Prepare arguments for each iteration
    iteration_args = [
        (base_name, i+1, base_dir)
        for i in range(num_iterations)
    ]
    
    pool = None
    try:
        # Run iterations in parallel with proper initialization
        pool = Pool(processes=num_processes, initializer=init_worker)
        output_dirs = pool.map(run_model_iteration, iteration_args)
        
        # Save iteration metadata
        metadata = {
            'base_name': base_name,
            'base_dir': base_dir,
            'num_iterations': num_iterations,
            'successful_iterations': len(output_dirs),
            'iteration_dirs': output_dirs,
            'timestamp': datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        }
        
        metadata_file = os.path.join(validation_dir, 'validation_metadata.json')
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"\nValidation iterations complete:")
        logger.info(f"All {num_iterations} iterations completed successfully")
        logger.info(f"Metadata saved to: {metadata_file}")
        
    except (RuntimeError, subprocess.CalledProcessError) as e:
        logger.error(f"\nCritical error occurred: {str(e)}")
        if pool:
            pool.terminate()
            pool.join()
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("\nCaught KeyboardInterrupt, terminating workers")
        if pool:
            pool.terminate()
            pool.join()
        sys.exit(1)
    finally:
        # Ensure pool is properly closed
        if pool:
            pool.close()
            pool.join()

if __name__ == "__main__":
    main()
