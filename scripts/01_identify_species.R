# Load required libraries
library(robis)
library(sf)
library(dplyr)
library(jsonlite)

# Function to read GeoJSON and get bounding box
get_bounding_box <- function(geojson_path) {
  cat("Reading GeoJSON from:", geojson_path, "\n")
  geojson_data <- st_read(geojson_path, quiet = TRUE)
  bbox <- st_bbox(geojson_data)
  return(bbox)
}

# Function to create polygon string from bounding box
create_polygon_string <- function(bbox) {
  sprintf("POLYGON ((%s %s, %s %s, %s %s, %s %s, %s %s))",
          bbox["xmin"], bbox["ymin"],
          bbox["xmax"], bbox["ymin"],
          bbox["xmax"], bbox["ymax"],
          bbox["xmin"], bbox["ymax"],
          bbox["xmin"], bbox["ymin"])
}

# Function to fetch species data from OBIS using checklist function
fetch_species_data <- function(bbox, max_retries = 3, retry_delay = 5) {
  polygon_string <- create_polygon_string(bbox)
  cat("Fetching species data from OBIS...\n")
  cat("Using polygon:", polygon_string, "\n")
  
  for (attempt in 1:max_retries) {
    tryCatch({
      cat(sprintf("Attempt %d of %d...\n", attempt, max_retries))
      
      # Set timeout for the request
      options(timeout = 60)  # 60 second timeout
      
      species_data <- occurrence(geometry = polygon_string)
      
      if (is.null(species_data) || nrow(species_data) == 0) {
        stop("No data returned from OBIS API")
      }
      
      cat(sprintf("Total entries found: %d\n", nrow(species_data)))
      cat(sprintf("Total unique species found: %d\n", length(unique(species_data$scientificName))))
      return(species_data)
      
    }, error = function(e) {
      if (attempt == max_retries) {
        stop(paste("Failed to connect to the OBIS API after", max_retries, "attempts:", e$message))
      } else {
        cat(sprintf("Attempt %d failed: %s\nRetrying in %d seconds...\n", 
                   attempt, e$message, retry_delay))
        Sys.sleep(retry_delay)
      }
    })
  }
}

# Function to filter species by coverage threshold
filter_by_coverage <- function(species_data, coverage_threshold = 1.0) {
  # Count occurrences per species
  species_counts <- species_data %>%
    group_by(scientificName) %>%
    summarise(n = n(), .groups = 'drop')
  
  # Calculate total occurrences
  total_occurrences <- sum(species_counts$n)
  
  # Sort species by occurrence count in descending order
  sorted_species <- species_counts %>%
    arrange(desc(n))
  
  # Calculate cumulative percentage
  sorted_species$cumulative_sum <- cumsum(sorted_species$n)
  sorted_species$cumulative_percentage <- sorted_species$cumulative_sum / total_occurrences
  
  # Find threshold that gives desired coverage
  threshold_species <- sorted_species %>%
    filter(cumulative_percentage <= coverage_threshold) %>%
    summarise(
      min_occurrences = min(n),
      species_count = n(),
      total_species = nrow(sorted_species),
      coverage = sum(n) / total_occurrences
    )
  
  # Filter species data based on threshold
  filtered_species <- species_data %>%
    group_by(scientificName) %>%
    filter(n() >= threshold_species$min_occurrences) %>%
    ungroup()
  
  # Print filtering summary
  cat("\nCoverage-based filtering summary:\n")
  cat(sprintf("Original species count: %d\n", nrow(species_data)))
  cat(sprintf("Filtered species count: %d\n", nrow(filtered_species)))
  cat(sprintf("Occurrence threshold: >= %d\n", threshold_species$min_occurrences))
  cat(sprintf("Actual coverage achieved: %.2f%%\n", threshold_species$coverage * 100))
  
  return(filtered_species)
}

# Function to remove more general entries efficiently
remove_general_entries <- function(species_data) {
  cat("Removing more general entries...\n")
  
  # Define taxonomic ranks from most specific to most general
  ranks <- c("scientificName", "genus", "family", "order", "class", "phylum", "kingdom")
  
  # Function to determine the most specific rank for each entry
  get_rank_value <- function(row) {
    for (i in seq_along(ranks)) {
      if (!is.na(row[[ranks[i]]]) && row[[ranks[i]]] != "") {
        return(i)
      }
    }
    return(length(ranks) + 1)  # Return highest value if no rank is found
  }
  
  # Add rank value column
  species_data$rank_value <- apply(species_data, 1, get_rank_value)
  
  # Group by all taxonomic levels and keep only the most specific entry
  filtered_data <- species_data %>%
    group_by(across(all_of(ranks))) %>%
    slice_min(rank_value) %>%
    ungroup() %>%
    select(everything())  # Preserve all columns including occurrence_count
  
  cat(sprintf("Removed %d general entries\n", nrow(species_data) - nrow(filtered_data)))
  return(filtered_data)
}

# Function to create occurrence histogram
create_histogram <- function(species_data, filename, title_suffix = "") {
  tryCatch({
    # Initialize PNG device
    png(filename = filename, width = 800, height = 600)
    
    # Count occurrences per species
    hist_data <- species_data %>%
      group_by(scientificName) %>%
      summarise(n = n(), .groups = 'drop') %>%
      pull(n)
    
    hist(hist_data, 
         main = paste0("Distribution of Species Occurrences in Northern Territory", title_suffix),
         xlab = "Number of Occurrences",
         ylab = "Number of Species",
         breaks = "FD")  # Using Freedman-Diaconis rule for bin width
    
    # Add summary statistics
    legend_text <- sprintf(
      "Total Species: %d\nMean Occurrences: %.1f\nMedian Occurrences: %.1f",
      length(hist_data),
      mean(hist_data),
      median(hist_data)
    )
    legend("topright", legend = legend_text, bty = "n")
    
    # Print frequency distribution
    freq_table <- sort(table(hist_data))
    cat("\nFrequency distribution of species occurrences:\n")
    cat("Number of occurrences | Number of species\n")
    cat(paste(rep("-", 40), collapse = ""), "\n")
    print(freq_table)
    
  }, error = function(e) {
    cat(sprintf("Warning: Failed to create histogram: %s\n", e$message))
  }, finally = {
    # Always close the device
    if (dev.cur() > 1) dev.off()
  })
}

# Function to process and save species list
process_and_save_species <- function(species_data, output_file, coverage_threshold = 1.0) {
  if (is.null(species_data) || nrow(species_data) == 0) {
    cat("No species data to process.\n")
    stop("No species data available to process")
  }
  
  cat("Processing species data...\n")
  
  # Create figures directory if it doesn't exist
  if (!dir.exists("manuscript/figures")) {
    dir.create("manuscript/figures", recursive = TRUE)
  }
  
  # Filter marine species
  marine_species <- species_data #%>% filter(is_marine)
  
  # Create histogram before filtering
  create_histogram(marine_species, "manuscript/figures/species_occurrence_histogram_raw.png", " (Raw)")
  
  # Apply coverage-based filtering if threshold < 1.0
  if (coverage_threshold < 1.0) {
    marine_species <- filter_by_coverage(marine_species, coverage_threshold)
    create_histogram(marine_species, "manuscript/figures/species_occurrence_histogram_filtered.png", " (Filtered)")
  }
  
  # Group and count occurrences
  unique_species <- marine_species %>%
    group_by(scientificName, kingdom, phylum, class, order, family, genus) %>%
    summarise(
      occurrence_count = n(),
      .groups = 'drop'
    ) %>%
    arrange(kingdom, phylum, class, order, family, genus, scientificName) %>%
    select(scientificName, occurrence_count, everything())  # Ensure occurrence_count is preserved and near the front
  
  # Remove more general entries
  unique_species <- remove_general_entries(unique_species)
  
  tryCatch({
    write.csv(unique_species, file = output_file, row.names = FALSE)
    
    # Verify file was created and has content
    if (!file.exists(output_file) || file.size(output_file) == 0) {
      stop("Failed to create species list CSV file or file is empty")
    }
    
    cat(sprintf("Species list saved to %s\n", output_file))
    cat(sprintf("Total unique species: %d\n", nrow(unique_species)))
    
    # Print summary of species
    cat("\nSpecies summary:\n")
    print(head(unique_species))
  }, error = function(e) {
    stop(paste("Error saving species list:", e$message))
  })
}

# Main function
main <- function(geojson_path, output_file, coverage_threshold = 1.0) {
  cat("Starting main function...\n")
  cat("GeoJSON path:", geojson_path, "\n")
  cat("Output file:", output_file, "\n")
  cat("Coverage threshold:", coverage_threshold, "\n")
  
  bbox <- get_bounding_box(geojson_path)
  cat("Bounding Box:", bbox, "\n")
  
  tryCatch({
    species_data <- fetch_species_data(bbox)
    if (!is.null(species_data) && nrow(species_data) > 0) {
      cat("Processing and saving species data...\n")
      process_and_save_species(species_data, output_file, coverage_threshold)
    } else {
      stop("No species data available to process")
    }
  }, error = function(e) {
    stop(paste("Error in main function:", e$message))
  })
}

# Get command-line arguments
args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 2 || length(args) > 3) {
  stop("Usage: Rscript 01_identify_species.R <geojson_path> <output_file> [coverage_threshold]")
}

geojson_path <- args[1]
output_file <- args[2]
coverage_threshold <- if (length(args) == 3) as.numeric(args[3]) else 1.0

if (coverage_threshold <= 0 || coverage_threshold > 1) {
  stop("Coverage threshold must be between 0 and 1")
}

# Run the script with error handling
tryCatch({
  main(geojson_path, output_file, coverage_threshold)
}, error = function(e) {
  cat("\nFatal error occurred:\n")
  cat(e$message, "\n")
  quit(status = 1)
})
