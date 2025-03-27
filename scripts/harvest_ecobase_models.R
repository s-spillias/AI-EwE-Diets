library(httr)
library(jsonlite)
library(dplyr)
library(tidyr)
library(readr)

#' EcoBase Harvester Class
#' @description R6 class to harvest EwE model parameters from EcoBase database
EcoBaseHarvester <- R6::R6Class(
  "EcoBaseHarvester",
  public = list(
    base_url = "https://sirs.agrocampus-ouest.fr/EcoBase/api/v1",
    output_dir = "data/ecobase_models",
    
    initialize = function() {
      dir.create(self$output_dir, recursive = TRUE, showWarnings = FALSE)
    },
    
    #' Get list of available models
    get_model_list = function() {
      tryCatch({
        response <- GET(paste0(self$base_url, "/models"))
        if (status_code(response) == 200) {
          models <- fromJSON(rawToChar(response$content))
          models_df <- as.data.frame(models)
          write_csv(models_df, file.path(self$output_dir, "model_list.csv"))
          message(sprintf("Retrieved %d models", nrow(models_df)))
          return(models_df)
        } else {
          warning(sprintf("Failed to get model list: %d", status_code(response)))
          return(NULL)
        }
      }, error = function(e) {
        warning(sprintf("Error getting model list: %s", e$message))
        return(NULL)
      })
    },
    
    #' Get parameters for a specific model
    get_model_parameters = function(model_id) {
      tryCatch({
        response <- GET(sprintf("%s/models/%s/parameters", self$base_url, model_id))
        if (status_code(response) == 200) {
          params <- fromJSON(rawToChar(response$content))
          
          # Save raw parameters
          write_json(params, file.path(self$output_dir, 
                                     sprintf("model_%s_params.json", model_id)),
                    pretty = TRUE)
          
          # Create structured format for parameters
          structured_params <- list(
            biomass = list(),
            pb_ratio = list(),
            qb_ratio = list(),
            ee = list(),
            diet_matrix = list()
          )
          
          # Process parameters
          for (param in params) {
            param_type <- param$type
            if (!is.null(param_type) && param_type %in% names(structured_params)) {
              structured_params[[param_type]][[length(structured_params[[param_type]]) + 1]] <- 
                list(
                  group = param$group,
                  value = param$value,
                  unit = param$unit
                )
            }
          }
          
          # Convert to data frames and save
          for (param_type in names(structured_params)) {
            if (length(structured_params[[param_type]]) > 0) {
              df <- do.call(rbind, lapply(structured_params[[param_type]], as.data.frame))
              write_csv(df, file.path(self$output_dir,
                                    sprintf("model_%s_%s.csv", model_id, param_type)))
            }
          }
          
          message(sprintf("Successfully retrieved parameters for model %s", model_id))
          return(structured_params)
        } else {
          warning(sprintf("Failed to get parameters for model %s: %d", 
                        model_id, status_code(response)))
          return(NULL)
        }
      }, error = function(e) {
        warning(sprintf("Error getting parameters for model %s: %s", 
                      model_id, e$message))
        return(NULL)
      })
    },
    
    #' Search for models based on criteria
    search_models = function(ecosystem_type = NULL, region = NULL, year = NULL) {
      tryCatch({
        params <- list(
          ecosystem_type = ecosystem_type,
          region = region,
          year = year
        )
        params <- params[!sapply(params, is.null)]
        
        response <- GET(paste0(self$base_url, "/models/search"),
                       query = params)
        
        if (status_code(response) == 200) {
          models <- fromJSON(rawToChar(response$content))
          models_df <- as.data.frame(models)
          
          # Create filename based on search criteria
          search_desc <- paste(names(params), params, sep = "_", collapse = "_")
          output_file <- if (search_desc != "") {
            sprintf("model_search_%s.csv", search_desc)
          } else {
            "model_search_all.csv"
          }
          
          write_csv(models_df, file.path(self$output_dir, output_file))
          message(sprintf("Found %d models matching criteria", nrow(models_df)))
          return(models_df)
        } else {
          warning(sprintf("Search failed: %d", status_code(response)))
          return(NULL)
        }
      }, error = function(e) {
        warning(sprintf("Error searching models: %s", e$message))
        return(NULL)
      })
    }
  )
)

# Example usage
main <- function() {
  harvester <- EcoBaseHarvester$new()
  
  # Get list of all models
  models_df <- harvester$get_model_list()
  if (!is.null(models_df)) {
    message("Retrieved model list successfully")
    
    # Example: Search for marine models in a specific region
    marine_models <- harvester$search_models(
      ecosystem_type = "Marine",
      region = "Pacific Ocean"
    )
    
    if (!is.null(marine_models)) {
      # Get parameters for first 5 marine models
      for (model_id in head(marine_models$model_id, 5)) {
        params <- harvester$get_model_parameters(model_id)
        if (!is.null(params)) {
          message(sprintf("Retrieved parameters for model %s", model_id))
        }
      }
    }
  }
}

if (interactive()) {
  main()
}
