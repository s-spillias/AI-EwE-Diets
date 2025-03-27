# Load required packages
library(sf)
library(ggplot2)
library(dplyr)
library(rnaturalearth)
library(rnaturalearthdata)

# Get Australia map
aus <- ne_countries(scale = "medium", country = "australia", returnclass = "sf")

# Read shapefiles
nt <- st_read("Validation/NT.shp")
se_in <- st_read("Validation/SE.In.shp")
se_off <- st_read("Validation/SE.Off.shp")

# Read and process GAB shapefile
gab_lines <- st_read("Validation/GAB/GAB.shp")
# Process GAB with extra smoothing steps
gab <- gab_lines %>%
  st_union() %>%
  st_simplify(dTolerance = 0.01) %>%  # Simplify geometry
  st_buffer(dist = 0.1) %>%           # Create larger buffer
  st_convex_hull() %>%                # Smooth the shape
  st_as_sf()

# Create the plot
p <- ggplot() +
  # Add validation regions first
  geom_sf(data = nt, fill = "#ff7800", alpha = 0.5, color = NA) +
  geom_sf(data = se_in, fill = "#2980b9", alpha = 0.5, color = NA) +
  geom_sf(data = se_off, fill = "#27ae60", alpha = 0.5, color = NA) +
  geom_sf(data = gab, fill = "#9b59b6", alpha = 0.5, color = NA) +
  # Add Australia map on top to mask overlaps
  geom_sf(data = aus, fill = "grey90", color = "grey50") +
  # Customize the theme
  theme_minimal() +
  # Add title
  labs(title = "", x = '', y = '') +
  # Add region labels at the very top
  annotate("text", x = 131, y = -17, label = "Northern Territory", color = "#cc6000", fontface = "bold") +
  annotate("text", x = 144, y = -36, label = "South East\nShelf", color = "#1a5c8c", fontface = "bold") +
  annotate("text", x = 152.2, y = -43, label = "South East\nOffshore", color = "#1e8449", fontface = "bold") +
  annotate("text", x = 122, y = -31, label = "Great Australian\nBight*", color = "#8e44ad", fontface = "bold") +
  # Set appropriate map bounds for Australia
  coord_sf(xlim = c(110, 155), ylim = c(-45, -10)) +  # Current bounds cover GAB region well
  # Customize theme
  theme(
    plot.title = element_text(hjust = 0.5, size = 14, face = "bold"),
    axis.title = element_text(size = 12),
    axis.text = element_text(size = 10),
    panel.grid.major = element_line(color = "gray95"),
    panel.grid.minor = element_blank()
  )

# Save the plot
ggsave("manuscript/figures/validation_regions.pdf", p, width = 8, height = 6, device = cairo_pdf)
ggsave("manuscript/figures/validation_regions.png", p, width = 8, height = 6, dpi = 300)
