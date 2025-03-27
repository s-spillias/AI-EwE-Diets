# EwE with AI


This repository contains tools for automating the creation of Ecopath with Ecosim (EwE) models using AI and various data sources.

## Introduction to Ecopath with Ecosim (EwE)

Ecopath with Ecosim (EwE) is a free ecosystem modeling software suite for personal computers. It has been developed for more than 30 years and can be used to:

1. Address ecological questions
2. Evaluate ecosystem effects of fishing
3. Explore management policy options
4. Analyze impact and placement of marine protected areas
5. Evaluate effect of environmental changes

This project aims to automate many of the time-consuming steps in creating an EwE model, using AI and various data sources to streamline the process.

## Prerequisites

Before you begin, ensure you have met the following requirements:

- Python 3.7 or higher
- R 4.0 or higher
- Required Python libraries (install via `pip install -r requirements.txt`):
  - pandas
  - numpy
  - requests
  - tqdm
  - suds-py3
  - duckdb
  - openpyxl
- Required R libraries:
  - robis
  - sf
  - dplyr
  - jsonlite

## Virtual Environment

It is recommended to use a virtual environment for this project. This will help isolate the project dependencies from your system-wide Python installation. Here's how you can set up and use a virtual environment:

1. Create a virtual environment:
```bash
python -m venv venv
```

2. Activate the virtual environment:
- On Windows:
```bash
venv\Scripts\activate
```
- On macOS and Linux:
```bash
source venv/bin/activate
```

3. Install the required dependencies within the virtual environment:
```bash
pip install -r requirements.txt
```

4. When you're done working on the project, you can deactivate the virtual environment:
```bash
deactivate
```

Remember to activate the virtual environment each time you work on this project.

## Setup

1. Clone this repository
2. Install required dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file in the root directory with the following API keys:
```
OPENAI_API_KEY=your_openai_api_key
SEALIFEBASE_API_KEY=your_sealifebase_api_key
GLOBI_API_KEY=your_globi_api_key
```

## Usage

The main script `main.py` can be used in four modes:

### 1. Interactive Mode

To start a new model using the interactive interface:

```bash
python main.py 
```

This will:
- Launch a web browser to guide you through the initial setup process
- Note: When selecting a region or uploading a shapefile, larger regions will take considerably longer to process due to containing more species.
- Begin gathering species and diet data

### 2. Resume Processing an Existing Model

To resume processing for a specific model:

```bash
python main.py --resume --model_name <model_name>
```

This will:
- Load the existing model data from the MODELS/<model_name> directory
- Continue processing from the last completed step
- Use the previously set configurations and AI models

Example:
```bash
python main.py --resume --model_name your_model_name
```

This mode is useful when you need to resume a model that was interrupted or when you want to continue processing after making manual adjustments to intermediate files.

### 3. Command-Line Mode

To start a new model or update an existing one using command-line arguments:

```bash
python main.py --model_name <model_name> --geojson_path <path_to_geojson> --research_focus "<research_focus>" --grouping_template <template> --group_species_ai <ai_model> --construct_diet_matrix_ai <ai_model> --ewe_params_ai <ai_model> --rag_search_ai <ai_model> [--force_grouping]
```

Example:
```bash
python main.py --model_name your_model_name --geojson_path MODELS\hobart_model\user_input.geojson --research_focus "Marine ecosystem dynamics in Jurien Bay" --grouping_template default --group_species_ai gemini --construct_diet_matrix_ai gemini --ewe_params_ai gemini --rag_search_ai aws_claude --force_grouping
```

Command-line arguments:
- `--model_name`: Name of the model directory in MODELS/
- `--geojson_path`: Path to the GeoJSON or ZIP file defining the study area
- `--research_focus`: Research focus for the model (in quotes)
- `--coverage_threshold`: Value between 0 and 1 to filter species by occurrence coverage (e.g., 0.95 keeps the most common species accounting for 95% of occurrences)
- `--grouping_template`: Choice of grouping template (default, upload, or ecobase)
- `--group_species_ai`: AI model for grouping species
- `--construct_diet_matrix_ai`: AI model for constructing the diet matrix
- `--ewe_params_ai`: AI model for estimating EwE parameters
- `--rag_search_ai`: AI model for RAG search
- `--force_grouping`: (Optional) If included, forces the use of only template groups

Available AI models:
- For grouping, diet matrix, and EwE params: claude, aws_claude, gemini, gemma2, llama3, mixtral
- For RAG search: aws_claude, azure_openai, openai, anthropic

This command-line mode allows for easier integration with other scripts or automation processes.

### Choosing a Grouping Template

The `--grouping_template` parameter determines how species will be organized into functional groups. There are four options available:

1. `default`: Uses the built-in default grouping template
   - Best for: General marine ecosystem models
   - Provides a standard set of functional groups based on common marine ecosystem components
   - Includes groups like demersal fish, pelagic fish, benthic invertebrates, etc.
   - Recommended for first-time users or when you want consistent group structure

2. `upload`: Use a custom grouping template from a JSON file
   - Best for: When you have specific grouping requirements or want to match an existing model
   - Allows you to define your own functional groups and their hierarchies
   - Must provide a JSON file following the template structure (see 03_grouping_template.json for format)
   - Useful when you want full control over group definitions

3. `ecobase`: Search EcoBase for a suitable template
   - Best for: When you want to base your model on existing, published EwE models
   - Searches the EcoBase database for models in similar regions or with similar focus
   - Adapts the grouping structure from a matching model
   - Good for ensuring compatibility with published studies

4. `geojson`: Generate groups based on your study area using the grouping AI
   - Best for: Region-specific models
   - Analyzes the species composition in your defined area
   - Creates groups that reflect the local ecosystem structure
   - Particularly useful for unique or specialized ecosystems

Tips for choosing a template:
- Start with `default` if you're new to EwE modeling
- Use `upload` when you need to maintain specific group definitions
- Try `ecobase` if you want to compare your results with published models
- Choose `geojson` for highly specialized or localized studies

Example of using a custom template:
```bash
python main.py --model_name your_model_name --geojson_path MODELS\hobart_model\user_input.geojson --research_focus "Marine ecosystem dynamics in Jurien Bay" --coverage_threshold 0.95 --grouping_template default --group_species_ai gemini --construct_diet_matrix_ai gemini --ewe_params_ai gemini --rag_search_ai aws_claude --force_grouping
```

## Running Validation

The project includes validation scripts to assess the consistency and reliability of the AI-generated models. Here's how to run the validation process:

### Running Validation Iterations

To run validation for a specific study area, use:

```bash
python 01_run_validation_iterations.py <base_name> <shapefile.zip> "<research_focus>" [num_iterations] [num_processes] [grouping_template] [coverage_threshold]
```

Parameters:
- `base_name`: Name for the validation run (e.g., "hobart_test")
- `shapefile.zip`: Path to your zipped shapefile containing all related files (.shp, .shx, .dbf, etc.)
- `research_focus`: Description of your research focus (in quotes)
- `num_iterations`: Number of validation iterations to run (default: 5)
- `num_processes`: Number of parallel processes to use (default: 3)
- `grouping_template`: Template to use for grouping (options: default, upload, ecobase, geojson)
- `coverage_threshold`: Value between 0 and 1 to filter species by occurrence coverage (default: 1.0)

Example:
```bash
python 01_run_validation_iterations.py hobart_test study_area.zip "Marine ecosystem dynamics in Hobart" 4 4 geojson
```

### Analyzing Validation Results

After running the validation iterations, analyze the results using:

```bash
python 02_analyze_validation_results.py <base_name>
```

This will generate a comprehensive validation report including:

1. Species Assignment Analysis:
   - Identifies species with variable group assignments across iterations
   - Calculates consistency scores for each species
   - Provides detailed breakdown of group assignments

2. Group Stability Analysis:
   - Measures stability of functional groups across iterations
   - Calculates Jaccard similarity scores between iterations
   - Tracks member composition changes

3. Diet Matrix Analysis:
   - Generates mean diet matrix across all iterations
   - Calculates standard deviation and coefficient of variation
   - Identifies highly variable diet relationships

### Validation Outputs

The validation process creates the following outputs in the `Validation/<base_name>/` directory:

1. Reports Directory:
   - `species_variability_rankings.csv`: Rankings of species by assignment variability
   - `group_stability_rankings.csv`: Rankings of groups by stability scores
   - `mean_matrix.csv`, `std_matrix.csv`, `cv_matrix.csv`: Statistical analyses of diet matrices
   - Various visualization plots (`.png` files)
   - `validation_summary.txt`: Comprehensive text summary of findings

2. Metadata Directory:
   - `validation_metadata.json`: Details about the validation run

### Interpreting Validation Results

1. Species Assignment Consistency:
   - Higher consistency scores (closer to 1.0) indicate more stable species assignments
   - Species with multiple group assignments across iterations may need manual review

2. Group Stability:
   - Higher stability scores indicate more consistent group composition
   - Groups with low stability might need refinement in their definitions

3. Diet Matrix Consistency:
   - Coefficient of Variation (CV) values indicate diet relationship stability
   - CV > 0.25 suggests high variability in the diet relationship
   - Lower CV values indicate more consistent diet matrix construction

## Project Structure

- `MODELS/` - Contains all model data organized by model name
  - Each model directory contains:
    - `01_species_list.csv` - Initial species list
    - `02_species_data.json` - Collected species information
    - `03_grouped_species_assignments.json` - Functional group assignments
    - `03_extra_ai_groups.json` - Additional groups suggested by AI (when using --force_grouping)
    - `04_diet_data.json` - Diet composition data
    - `05_diet_matrix.csv` - Final diet matrix
    - `06_ewe_params.json` - Estimated EwE parameters
    - `07_raw_ewe.xlsx` - Excel file containing EwE matrix and diet matrix
    - `progress.json` - Tracks the progress of model creation
    - Other supporting files

- `scripts/` - Contains all processing scripts
  - `00_map_interface.html` - Web interface for area selection
  - `00_serve_map_interface.py` - Server for the map interface
  - `01_identify_species.R` - Species identification script
  - `02_download_data.py` - Data collection from SeaLifeBase
  - `03_group_species.py` - Species grouping logic
  - `04_gather_diet_data.py` - Diet data collection
  - `05_construct_diet_matrix.py` - Diet matrix construction
  - `06_ewe_params.py` - EwE parameter estimation

## Model Processing Steps

1. Area Selection & Species Identification
2. Species Data Collection
3. Functional Group Assignment
4. Diet Data Collection
5. Diet Matrix Construction
6. EwE Parameter Estimation
7. Compilation of EwE and Diet Matrices

Each step saves its outputs in the model directory, allowing for process resumption and result verification.

## Output Files

The key output files in each model directory include:

- `01_species_list.csv`: Initial species list for the area
- `02_species_data.json`: Detailed species information
- `03_grouped_species_assignments.json`: Functional group assignments
- `03_extra_ai_groups.json`: Additional groups suggested by AI (when using --force_grouping)
- `04_diet_data.json`: Collected diet information
- `05_diet_matrix.csv`: Final diet matrix for EwE
- `06_ewe_params.json`: Estimated EwE parameters
- `07_raw_ewe.xlsx`: Excel file containing EwE matrix and diet matrix
- `progress.json`: Tracks which steps have been completed

These files represent the progression of data processing and can be used to resume processing or verify results at each step.

## Detailed Script Descriptions

### 00_serve_map_interface.py

This script sets up a local server to serve the map interface for area selection. It handles the following tasks:

1. Serves the `00_map_interface.html` file, which provides a web-based interface for users to select their study area.
2. Handles GET requests to list existing model directories.
3. Processes POST requests to save user inputs (selected area and research focus) when a new model is generated.
4. Creates necessary directories and files for new models.
5. Updates the interface state to indicate completion of the area selection step.

Key features:
- Uses Python's `http.server` and `socketserver` modules to create a simple HTTP server.
- Serves files from the project's root directory.
- Handles JSON data for communication between the frontend and backend.
- Creates and updates files in the `MODELS` directory based on user input.
- Processes uploaded shapefiles (must be in zip format containing all necessary files).

This script is crucial for the initial step of model creation, allowing users to interactively define their study area and research focus.

Important Note: When uploading a shapefile, ensure that all related files (.shp, .shx, .dbf, etc.) are zipped together in a single file. The interface only accepts zipped shapefiles to ensure all necessary components are included.

### 01_identify_species.R

This R script is responsible for identifying species within the user-defined study area. It performs the following tasks:

1. Reads the GeoJSON file containing the user-selected area.
2. Extracts the bounding box from the GeoJSON.
3. Queries the Ocean Biodiversity Information System (OBIS) database to fetch species data within the defined area.
4. Processes the retrieved data to remove duplicate and more general entries.
5. Saves the final list of unique species to a CSV file.

Key features:
- Uses the `robis` library to interact with the OBIS database.
- Employs `sf` (Simple Features) for spatial data handling.
- Utilizes `dplyr` for efficient data manipulation.
- Implements a function to remove more general taxonomic entries, keeping only the most specific for each species.
- Provides detailed logging throughout the process for easy debugging and progress tracking.

This script is essential for creating the initial species list for the ecosystem model, ensuring a comprehensive and accurate representation of the biodiversity in the selected area.

### 02_harvest_sealifebase_data.py

This Python script is responsible for collecting detailed information about the species identified in the previous step. It gathers data from multiple sources to create a comprehensive profile for each species. The script performs the following tasks:

1. Loads the species list generated by the previous script.
2. Fetches data from SeaLifeBase and FishBase databases.
3. Retrieves information from the World Register of Marine Species (WoRMS) database.
4. Collects interaction data from the Global Biotic Interactions (GloBI) database.
5. Combines all the collected data into a single JSON file for each species.

Key features:
- Uses `pandas` for efficient data manipulation.
- Employs `duckdb` for fast querying of large datasets.
- Implements error handling and logging for robust execution.
- Utilizes the SOAP client (`suds`) for interacting with the WoRMS web service.
- Implements a caching mechanism to avoid redundant API calls and speed up subsequent runs.
- Processes species data incrementally, saving progress after each species to allow for easy resumption if interrupted.

This script is crucial for building a detailed understanding of each species in the ecosystem, including their taxonomic classification, biological characteristics, and ecological interactions. The collected data serves as a foundation for subsequent steps in the EwE model creation process.

### 03_group_species.py

This Python script is responsible for assigning species to functional groups based on their taxonomic and ecological characteristics. It performs the following tasks:

1. Loads the species data collected in the previous step.
2. Loads reference groups from a provided file.
3. Preprocesses the species data to create a hierarchical structure based on taxonomic ranks.
4. Iteratively assigns species to functional groups, starting from higher taxonomic ranks and moving to lower ranks.
5. Saves the grouped species in both a hierarchical JSON format and a flat assignments format.

Key features:
- Implements a recursive algorithm to process the hierarchical taxonomic structure.
- Uses a retry mechanism with exponential backoff for robust group assignment.
- Allows for the addition of new functional groups if needed (when not using --force_grouping).
- Considers the research focus of the project when assigning groups.
- Provides detailed logging and color-coded console output for easy progress tracking.
- Saves intermediate results to allow for process resumption if interrupted.
- When --force_grouping is used, it saves additional group suggestions in a separate file without using them in the model.

The grouping process considers both taxonomic relationships and ecological roles, ensuring that the resulting functional groups accurately represent the ecosystem's structure.

NB: 03_grouping_report.txt provides a simplified summary of how taxonomic groups are assigned to ecological roles and can be used to validate/verify the AI decisions. 

### 04_gather_diet_data.py

This Python script is responsible for collecting and synthesizing diet data for each functional group in the ecosystem model. It performs the following tasks:

1. Loads the grouped species data and individual species data from previous steps.
2. Retrieves diet information from multiple sources:
   - SeaLifeBase and FishBase databases
   - Global Biotic Interactions (GloBI) database
   - Custom RAG (Retrieval-Augmented Generation) search on provided documents
3. Processes and combines the diet data from all sources.
4. Uses AI to analyze the combined data and generate a summary of the diet composition for each functional group.
5. Saves the raw data, AI-generated summaries, and processed diet information for each group.

Key features:
- Implements efficient data loading and processing using pandas and tqdm for progress tracking.
- Utilizes custom RAG search functionality to extract relevant diet information from provided documents.
- Employs AI (likely using GPT or a similar model) to synthesize diet information from multiple sources.
- Handles large datasets by processing groups and species incrementally.
- Implements error handling and logging for robust execution.
- Saves intermediate results to allow for process resumption if interrupted.
- Generates both machine-readable (JSON) and human-readable outputs.

This script is crucial for determining the trophic relationships within the ecosystem. The diet composition data it generates is essential for constructing the diet matrix, which is a key component of the EwE model. By combining data from multiple sources and using AI for synthesis, this script aims to create a comprehensive and accurate representation of the feeding relationships in the ecosystem.

### 05_construct_diet_matrix.py

This Python script is responsible for constructing the diet matrix, a crucial component of the Ecopath with Ecosim (EwE) model. It performs the following tasks:

1. Loads the species list and diet data from previous steps.
2. Constructs a diet matrix where rows represent predators and columns represent prey.
3. Uses AI to interpret and convert the diet summaries into numerical proportions.
4. Handles cases where prey items don't exactly match species in the list.
5. Saves the constructed diet matrix as a CSV file.

Key features:
- Uses pandas for efficient data manipulation and matrix construction.
- Employs AI (via the `ask_ai` function) to interpret diet summaries and convert them into numerical proportions.
- Implements a scaling function to ensure diet proportions sum to 1 for each predator.
- Provides flexibility in input and output file paths through command-line arguments.
- Saves intermediate results to allow for process resumption and to avoid redundant AI queries.
- Handles potential mismatches between prey items in diet summaries and species in the list.

This script is essential for quantifying the trophic relationships in the ecosystem model. The resulting diet matrix provides a detailed representation of who eats whom and in what proportions, which is fundamental to the EwE modeling approach. By using AI to interpret qualitative diet descriptions, this script aims to create a more accurate and comprehensive diet matrix than might be possible through manual data entry alone.

### 06_ewe_params.py

This Python script is responsible for estimating the Ecopath with Ecosim (EwE) parameters for each functional group in the ecosystem model. It performs the following tasks:

1. Loads the grouped species assignments from previous steps.
2. For each functional group:
   - Searches the EcoBase database for similar species groups.
   - Retrieves relevant parameter values and metadata from EcoBase.
   - Uses AI to analyze and interpret the data, estimating appropriate parameter values.
3. Constructs an EwE parameter matrix with the following information for each group:
   - Habitat area (fraction)
   - Biomass in habitat area (t/km²)
   - Production/Biomass (P/B) ratio (year⁻¹)
   - Consumption/Biomass (Q/B) ratio (year⁻¹)
   - Ecotrophic efficiency (EE)
   - Production/Consumption (P/Q) ratio
   - Biomass accumulation rate (BA)
   - Unassimilated consumption (GS)
   - Detritus import rate
   - Migration rate (annual)
   - Other mortality rate
4. Saves the parameter estimates and supporting data in JSON format.

Key features:
- Implements efficient database querying using the EcoBase API.
- Uses AI to analyze parameter patterns and estimate values based on similar species groups.
- Handles missing data and uncertainty in parameter estimation.
- Provides detailed logging of the estimation process.
- Saves both the final estimates and the supporting data used to make those estimates.

This script is crucial for completing the EwE model by providing reasonable estimates for all required parameters. The AI-assisted approach helps ensure that parameter values are biologically reasonable and consistent with existing knowledge about similar species and ecosystems.
