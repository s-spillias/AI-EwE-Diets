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
      
      species_data <- checklist(geometry = polygon_string)
      
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

# Function to remove more general entries efficiently
remove_general_entries <- function(species_data) {
  cat("Removing more general entries...\n")
  
  # Define taxonomic ranks from most specific to most general
  ranks <- c("scientificName", "genus", "family", "order", "class", "phylum", "kingdom")
  
  # Function to determine the most specific rank for each entry
  get_rank_value <- function(row) {
    # First check if scientificName matches any of the higher taxonomic ranks
    scientific_name <- row[["scientificName"]]
    for (rank in ranks[-1]) {  # Exclude scientificName from the check
      if (!is.na(row[[rank]]) && !is.na(scientific_name) && 
          row[[rank]] != "" && scientific_name != "" && 
          scientific_name == row[[rank]]) {
        # If scientificName matches a higher rank, return that rank's position
        return(which(ranks == rank))
      }
    }
    
    # If no match found with higher ranks, count the number of words in scientificName
    if (!is.na(scientific_name) && scientific_name != "") {
      word_count <- length(strsplit(scientific_name, " ")[[1]])
      if (word_count == 2) {
        return(1)  # Species level (two words)
      } else if (word_count == 1) {
        return(2)  # Genus level (one word)
      }
    }
    
    # If scientificName is NA or empty, find the most specific filled rank
    for (i in seq_along(ranks)) {
      if (!is.na(row[[ranks[i]]]) && row[[ranks[i]]] != "") {
        return(i)
      }
    }
    
    return(length(ranks) + 1)  # Return highest value if no rank is found
  }
  
  # Add rank value column
  species_data$rank_value <- apply(species_data, 1, get_rank_value)
  
  # Keep only rank 1 entries (species level)
  filtered_data <- species_data %>%
    filter(rank_value == 1)
  
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
process_and_save_species <- function(species_data, output_file) {
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
    
  }, error = function(e) {
    stop(paste("Error saving species list:", e$message))
  })
}

# Main function
main <- function(geojson_path, output_file) {
  cat("Starting main function...\n")
  cat("GeoJSON path:", geojson_path, "\n")
  cat("Output file:", output_file, "\n")
  
  bbox <- get_bounding_box(geojson_path)
  cat("Bounding Box:", bbox, "\n")
  
  tryCatch({
    species_data <- fetch_species_data(bbox)
    if (!is.null(species_data) && nrow(species_data) > 0) {
      cat("Processing and saving species data...\n")
      process_and_save_species(species_data, output_file)
    } else {
      stop("No species data available to process")
    }
  }, error = function(e) {
    stop(paste("Error in main function:", e$message))
  })
}

# Get command-line arguments
args <- commandArgs(trailingOnly = TRUE)

if (length(args) != 2) {
  stop("Usage: Rscript 01_identify_species.R <geojson_path> <output_file>")
}

geojson_path <- args[1]
output_file <- args[2]

# Run the script with error handling
tryCatch({
  main(geojson_path, output_file)
}, error = function(e) {
  cat("\nFatal error occurred:\n")
  cat(e$message, "\n")
  quit(status = 1)
})
