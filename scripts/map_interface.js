document.addEventListener('DOMContentLoaded', () => {
    // Initialize the map
    const map = L.map('map').setView([0, 0], 2);

    // Add OpenStreetMap tile layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    // Initialize draw control
    const drawnItems = new L.FeatureGroup();
    map.addLayer(drawnItems);

    const drawControl = new L.Control.Draw({
        edit: {
            featureGroup: drawnItems
        },
        draw: {
            polygon: true,
            polyline: false,
            rectangle: true,
            circle: false,
            marker: false,
            circlemarker: false
        }
    });
    map.addControl(drawControl);

    // Event listener for draw:created
    map.on('draw:created', (e) => {
        drawnItems.clearLayers();
        const layer = e.layer;
        drawnItems.addLayer(layer);
    });

    // Fetch and populate directories
    async function loadDirectories() {
        try {
            const response = await fetch('/list_directories');
            const directories = await response.json();
            const select = document.getElementById('outputDirectory');
            select.innerHTML = ''; // Clear loading option
            
            // Add existing directories
            directories.forEach(dir => {
                const option = document.createElement('option');
                option.value = dir;
                option.textContent = dir;
                select.appendChild(option);
            });
            
            // Add custom option
            const customOption = document.createElement('option');
            customOption.value = 'custom';
            customOption.textContent = 'Custom Directory';
            select.appendChild(customOption);
        } catch (error) {
            console.error('Error loading directories:', error);
            updateStatus('Error loading directories. Please refresh the page.', true);
        }
    }

    // Load directories when page loads
    loadDirectories();

    // Toggle custom directory input
    document.getElementById('outputDirectory').addEventListener('change', () => {
        const select = document.getElementById('outputDirectory');
        const customInput = document.getElementById('customDirectory');
        customInput.style.display = select.value === 'custom' ? 'block' : 'none';
        if (select.value !== 'custom') {
            customInput.value = ''; // Clear custom input when not selected
        }
    });

    // Get selected directory
    function getSelectedDirectory() {
        const select = document.getElementById('outputDirectory');
        if (select.value === 'custom') {
            const customDir = document.getElementById('customDirectory').value.trim();
            return customDir || 'outputs'; // fallback to 'outputs' if custom is empty
        }
        return select.value;
    }

    // Status update function
    function updateStatus(message, isError = false) {
        const statusDiv = document.getElementById('status');
        statusDiv.textContent = message;
        statusDiv.style.color = isError ? 'red' : 'black';
    }

    // Generate Model function
    document.getElementById('generateModel').addEventListener('click', async () => {
        const researchFocus = document.getElementById('researchFocus').value;
        if (!researchFocus) {
            updateStatus('Please enter a research focus.', true);
            return;
        }

        const outputDirectory = getSelectedDirectory();
        if (!outputDirectory) {
            updateStatus('Please select or enter an output directory.', true);
            return;
        }

        const shapefileInput = document.getElementById('shapefileUpload');
        const formData = new FormData();

        if (shapefileInput.files.length > 0) {
            for (let i = 0; i < shapefileInput.files.length; i++) {
                formData.append('shapefile', shapefileInput.files[i]);
            }
        } else if (drawnItems.getLayers().length === 0) {
            updateStatus('Please draw a shape or upload a shapefile.', true);
            return;
        } else {
            const geojson = drawnItems.toGeoJSON();
            formData.append('geojson', JSON.stringify(geojson));
        }

        formData.append('researchFocus', researchFocus);
        formData.append('outputDirectory', outputDirectory);

        // Append selected AI models
        formData.append('groupSpeciesAI', document.getElementById('groupSpeciesAI').value);
        formData.append('constructDietMatrixAI', document.getElementById('constructDietMatrixAI').value);
        formData.append('eweParamsAI', document.getElementById('eweParamsAI').value);
        formData.append('ragSearchAI', document.getElementById('ragSearchAI').value);

        // Append grouping template information
        const groupingTemplate = document.getElementById('groupingTemplate').value;
        formData.append('groupingTemplate', groupingTemplate);

        if (groupingTemplate === 'upload') {
            const groupingJsonUpload = document.getElementById('groupingJsonUpload').files[0];
            if (groupingJsonUpload) {
                formData.append('groupingJsonUpload', groupingJsonUpload);
            } else {
                updateStatus('Please upload a grouping JSON file.', true);
                return;
            }
        } else if (groupingTemplate === 'ecobase') {
            const ecobaseSearchInput = document.getElementById('ecobaseSearchInput').value;
            if (ecobaseSearchInput) {
                formData.append('ecobaseSearchInput', ecobaseSearchInput);
            } else {
                updateStatus('Please enter an Ecobase search term.', true);
                return;
            }
        } else if (groupingTemplate === 'geojson') {
            // For geojson template, we'll use the drawn area or uploaded shapefile
            // to generate functional groups, so no additional input is needed
            if (drawnItems.getLayers().length === 0 && shapefileInput.files.length === 0) {
                updateStatus('Please draw a shape or upload a shapefile to generate functional groups.', true);
                return;
            }
        }

        // Append force_grouping checkbox value
        formData.append('forceGrouping', document.getElementById('forceGrouping').checked);

        try {
            const response = await fetch('/generate_model', {
                method: 'POST',
                body: formData,
            });
            const data = await response.text();
            console.log('Success:', data);
            updateStatus('Model generation started. You can close this window.');
        } catch (error) {
            console.error('Error:', error);
            updateStatus('An error occurred while generating the model. Please check the console for details.', true);
        }
    });
});
