import http.server
import socketserver
import os
import json
import cgi
import shutil
import logging
import geopandas as gpd
import tempfile
import zipfile
import requests

PORT = 8000

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def shapefile_to_geojson(shapefile_path, geojson_path):
    try:
        gdf = gpd.read_file(shapefile_path)
        gdf.to_file(geojson_path, driver='GeoJSON')
        logger.info(f"Converted shapefile to GeoJSON: {geojson_path}")
        return True
    except Exception as e:
        logger.error(f"Error converting shapefile to GeoJSON: {str(e)}")
        return False

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.dirname(os.path.dirname(os.path.abspath(__file__))), **kwargs)

    def do_GET(self):
        if self.path == '/scripts/00_map_interface.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            with open(os.path.join(self.directory, 'scripts', '00_map_interface.html'), 'rb') as file:
                self.wfile.write(file.read())
        elif self.path == '/list_directories':
            # Get all directories in the MODELS folder
            models_dir = os.path.join(self.directory, 'MODELS')
            try:
                if not os.path.exists(models_dir):
                    os.makedirs(models_dir)
                dirs = [d for d in os.listdir(models_dir) 
                       if os.path.isdir(os.path.join(models_dir, d)) 
                       and not d.startswith('__') 
                       and not d.startswith('.')]
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(dirs).encode())
            except Exception as e:
                logger.error(f"Error in listing directories: {str(e)}")
                self.send_error(500, str(e))
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == '/generate_model':
            try:
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={'REQUEST_METHOD': 'POST',
                             'CONTENT_TYPE': self.headers['Content-Type'],
                             })

                logger.info("Received POST request for /generate_model")

                # Use specified output directory or default to 'outputs'
                output_dir = form.getvalue('outputDirectory', 'outputs')
                if not output_dir:
                    output_dir = 'outputs'
                logger.info(f"Output directory: {output_dir}")
                
                # Create full path under MODELS directory and ensure it exists
                models_dir = os.path.join(self.directory, 'MODELS')
                outputs_dir = os.path.join(models_dir, output_dir)
                os.makedirs(outputs_dir, exist_ok=True)
                logger.info(f"Created output directory: {outputs_dir}")
                
                geojson_path = os.path.join(outputs_dir, 'user_input.geojson')
                
                # Handle shapefile upload
                if 'shapefile' in form:
                    shapefile = form['shapefile']
                    if shapefile.filename:
                        # Create a temporary directory to store the uploaded file
                        with tempfile.TemporaryDirectory() as tmpdirname:
                            file_path = os.path.join(tmpdirname, shapefile.filename)
                            with open(file_path, 'wb') as f:
                                shutil.copyfileobj(shapefile.file, f)
                            
                            # Check if the file is a zip file
                            if zipfile.is_zipfile(file_path):
                                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                                    zip_ref.extractall(tmpdirname)
                                
                                # Find the .shp file
                                shp_file = next((f for f in os.listdir(tmpdirname) if f.endswith('.shp')), None)
                                if shp_file:
                                    shapefile_path = os.path.join(tmpdirname, shp_file)
                                    if shapefile_to_geojson(shapefile_path, geojson_path):
                                        logger.info(f"Shapefile converted to GeoJSON: {geojson_path}")
                                    else:
                                        logger.error("Failed to convert shapefile to GeoJSON")
                                        raise ValueError("Failed to convert shapefile to GeoJSON")
                                else:
                                    logger.error("No .shp file found in the uploaded zip file")
                                    raise ValueError("No .shp file found in the uploaded zip file")
                            else:
                                logger.error("Uploaded file is not a zip file")
                                raise ValueError("Uploaded file must be a zip file containing shapefile components")
                    else:
                        logger.warning("Shapefile field present but filename is empty")
                else:
                    logger.info("No shapefile uploaded")
                
                # Handle GeoJSON
                geojson = form.getvalue('geojson')
                if geojson:
                    with open(geojson_path, 'w') as f:
                        json.dump(json.loads(geojson), f)
                    logger.info(f"GeoJSON saved: {geojson_path}")
                elif not os.path.exists(geojson_path):
                    logger.warning("No GeoJSON data received and no shapefile converted")
                
                # Get research focus
                research_focus = form.getvalue('researchFocus', '')
                logger.info(f"Research focus received: {research_focus}")
                
                # Handle grouping template
                grouping_template = form.getvalue('groupingTemplate', 'default')
                grouping_path = os.path.join(outputs_dir, 'grouping_template.json')
                
                if grouping_template == 'default':
                    # Copy default grouping template
                    default_template_path = os.path.join(self.directory, '03_grouping_template.json')
                    shutil.copy(default_template_path, grouping_path)
                    logger.info(f"Default grouping template copied to: {grouping_path}")
                elif grouping_template == 'upload':
                    # Handle uploaded JSON file
                    if 'groupingJsonUpload' in form:
                        uploaded_file = form['groupingJsonUpload']
                        if uploaded_file.filename:
                            with open(grouping_path, 'wb') as f:
                                shutil.copyfileobj(uploaded_file.file, f)
                            logger.info(f"Uploaded grouping template saved to: {grouping_path}")
                        else:
                            logger.warning("Grouping JSON upload field present but filename is empty")
                    else:
                        logger.warning("No grouping JSON file uploaded")
                elif grouping_template == 'ecobase':
                    # Handle Ecobase search
                    ecobase_search_term = form.getvalue('ecobaseSearchInput', '')
                    if ecobase_search_term:
                        # Save the search term to the grouping template file
                        with open(grouping_path, 'w') as f:
                            json.dump({"ecobase_search_term": ecobase_search_term}, f)
                        logger.info(f"Ecobase search term saved to: {grouping_path}")
                    else:
                        logger.warning("No Ecobase search term provided")
                elif grouping_template == 'geojson':
                    # For geojson template, we'll use the user_input.geojson file
                    if os.path.exists(geojson_path):
                        logger.info(f"Using geojson file for generating functional groups: {geojson_path}")
                    else:
                        logger.error("No geojson file available for generating functional groups")
                        raise ValueError("No geojson file available for generating functional groups")
                
                # Save AI model selections, research focus, and grouping template info to a configuration file
                ai_config = {
                    'groupSpeciesAI': form.getvalue('groupSpeciesAI', 'gemini'),
                    'constructDietMatrixAI': form.getvalue('constructDietMatrixAI', 'gemini'),
                    'eweParamsAI': form.getvalue('eweParamsAI', 'gemini'),
                    'ragSearchAI': form.getvalue('ragSearchAI', 'aws_claude'),
                    'groupingTemplate': {
                        'type': grouping_template,
                        'path': 'user_input.geojson' if grouping_template == 'geojson' else os.path.relpath(grouping_path, outputs_dir)
                    },
                    'forceGrouping': form.getvalue('forceGrouping', 'false').lower() == 'true',
                    'researchFocus': research_focus
                }
                
                # Add Ecobase search term to ai_config if it exists
                if grouping_template == 'ecobase' and ecobase_search_term:
                    ai_config['groupingTemplate']['ecobase_search_term'] = ecobase_search_term
                
                ai_config_path = os.path.join(outputs_dir, 'ai_config.json')
                with open(ai_config_path, 'w') as f:
                    json.dump(ai_config, f, indent=2)
                logger.info(f"AI configuration saved: {ai_config_path}")
                
                # Update state file to indicate completion with path relative to MODELS
                state_file = os.path.join(self.directory, 'interface_state.json')
                state_data = {
                    "status": "complete",
                    "output_directory": os.path.join('MODELS', output_dir),
                    "geojson": "user_input.geojson",
                    "ai_config": "ai_config.json"
                }
                
                with open(state_file, 'w') as f:
                    json.dump(state_data, f)
                logger.info(f"State file updated: {state_file}")
                
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b"Model generation started")
                logger.info("Model generation process completed successfully")
            except Exception as e:
                logger.error(f"Error in generate_model: {str(e)}", exc_info=True)
                self.send_error(500, str(e))
        else:
            super().do_POST()

def serve_map_interface():
    handler = Handler
    handler.extensions_map['.js'] = 'application/javascript'

    with socketserver.TCPServer(("", PORT), handler) as httpd:
        logger.info(f"Serving at port {PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    serve_map_interface()
