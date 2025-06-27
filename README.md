# EwE with AI

This repository contains tools for automating the creation of food web models using AI and various data sources.

## Introduction

Food webs are complex networks that describe the trophic (feeding) relationships between species in an ecosystem. They are fundamental to understanding ecosystem dynamics, energy flow, and species interactions. Creating accurate food web models is traditionally time-consuming and labor-intensive, requiring extensive literature review and expert knowledge.

This project uses artificial intelligence to automate the creation of food web models compatible with Ecopath with Ecosim (EwE), a widely-used ecosystem modeling software. EwE can be used to address ecological questions, evaluate ecosystem effects of fishing, explore management policy options, analyze marine protected areas, and evaluate environmental changes.

## Preprint:
https://www.biorxiv.org/content/10.1101/2025.05.18.654761v1

## Prerequisites

- Python 3.7+ and R 4.0+
- Python libraries: Install via `pip install -r requirements.txt`
- R libraries: robis, sf, dplyr, jsonlite

It's recommended to use a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Setup

1. Clone this repository
2. Install dependencies: `pip install -r requirements.txt`
3. Create a `.env` file with API keys:
```
OPENAI_API_KEY=your_openai_api_key
SEALIFEBASE_API_KEY=your_sealifebase_api_key
GLOBI_API_KEY=your_globi_api_key
```

## Usage

### 1. Interactive Mode

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

Available AI models:
- For grouping, diet matrix, and EwE params: claude, aws_claude, gemini, gemma2, llama3, mixtral
- For RAG search: aws_claude, azure_openai, openai, anthropic

### Grouping Templates

- `default`: Standard set of functional groups for general marine ecosystem models
- `upload`: Custom grouping template from a JSON file
- `ecobase`: Search EcoBase for a suitable template
- `geojson`: Generate groups based on your study area using the grouping AI

## Validation

### Running Experimental Iterations

1. Initial Setup:
```bash
python 01a_run_initial_steps.py <base_name> <geojson_path> "<research_focus>" [grouping_template] [template_file] [--force_grouping]
```

2. Run Validation Iterations:
```bash
python 01b_run_validation_iterations.py <base_name> [num_iterations] [num_processes]
```

Parameters:
- `base_name`: Name for the validation run (same as used in step 1)
- `num_iterations`: Number of validation iterations to run (default: 5)
- `num_processes`: Number of parallel processes to use (default: 3)

Example:
```bash
python 01b_run_validation_iterations.py hobart_test 4 4
```

### Analyzing Validation Results

After running the validation iterations, analyze the results using:

```bash
python 02_analyze_validation_results.py
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

The validation process creates reports with species variability rankings, group stability rankings, statistical analyses of diet matrices, visualization plots, and a comprehensive text summary.

## Project Structure and Workflow

- `MODELS/` - Contains all model data organized by model name
- `scripts/` - Contains all processing scripts for each step of the workflow

The model creation follows these sequential steps:
1. Area Selection & Species Identification
2. Species Data Collection
3. Functional Group Assignment
4. Diet Data Collection
5. Diet Matrix Construction
6. EwE Parameter Estimation
7. Compilation of EwE and Diet Matrices

Each step saves outputs in the model directory, allowing for process resumption and result verification.
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