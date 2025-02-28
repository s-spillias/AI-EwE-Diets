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

# Create the plot
p <- ggplot() +
  # Add Australia base map in grey
  geom_sf(data = aus, fill = "grey90", color = "grey50") +
  # Add validation regions with different colors and transparency
  geom_sf(data = nt, fill = "#ff7800", alpha = 0.5, color = "#cc6000") +
  geom_sf(data = se_in, fill = "#2980b9", alpha = 0.5, color = "#1a5c8c") +
  geom_sf(data = se_off, fill = "#27ae60", alpha = 0.5, color = "#1e8449") +
  # Customize the theme
  theme_minimal() +
  # Add title
  labs(title = "Validation Regions") +
  # Add region labels with adjusted positions
  annotate("text", x = 132.5, y = -13, label = "Northern Territory", color = "#cc6000", fontface = "bold") +
  annotate("text", x = 143, y = -37, label = "South East\nInshore", color = "#1a5c8c", fontface = "bold") +
  annotate("text", x = 152, y = -42, label = "South East\nOffshore", color = "#1e8449", fontface = "bold") +
  # Set appropriate map bounds for Australia
  coord_sf(xlim = c(110, 155), ylim = c(-45, -10)) +
  # Customize theme
  theme(
    plot.title = element_text(hjust = 0.5, size = 14, face = "bold"),
    axis.title = element_text(size = 12),
    axis.text = element_text(size = 10),
    panel.grid.major = element_line(color = "gray95"),
    panel.grid.minor = element_blank()
  )

# Save the plot
ggsave("Validation/validation_regions.pdf", p, width = 8, height = 6, device = cairo_pdf)
ggsave("Validation/validation_regions.png", p, width = 8, height = 6, dpi = 300)
