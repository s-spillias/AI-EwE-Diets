import os
import sys
import json
import unittest

# Add scripts directory to path to import modules
scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts')
sys.path.append(scripts_dir)

from group_species_utils import get_ai_reference_groups
from ask_AI import ask_ai

class TestAIGrouping(unittest.TestCase):
    def setUp(self):
        self.test_output_dir = os.path.join('tests', 'test_output')
        os.makedirs(self.test_output_dir, exist_ok=True)
        
        # Copy NT.geojson to test directory
        self.test_geojson = os.path.join(self.test_output_dir, 'test_area.geojson')
        with open('geojson/NT.geojson', 'r') as src, open(self.test_geojson, 'w') as dst:
            dst.write(src.read())

    def test_multiple_iterations(self):
        """Test that multiple iterations are run and synthesized"""
        print("\nTesting multiple iterations and synthesis...")
        
        num_iterations = 3  # Using fewer iterations for testing
        
        # Test with NT.geojson
        group_names, group_dict = get_ai_reference_groups(
            self.test_geojson,
            ai_model='claude',  # Using Claude for more precise formatting
            researchFocus='Focus on coastal fisheries',
            num_iterations=num_iterations
        )
        
        # Load the saved ecosystem description and iterations
        ai_config_path = os.path.join(os.path.dirname(self.test_geojson), 'ai_config.json')
        self.assertTrue(os.path.exists(ai_config_path), "ai_config.json not created")
        
        with open(ai_config_path, 'r') as f:
            config = json.load(f)
        
        # Check if all iterations were saved
        self.assertEqual(config.get('iterations'), num_iterations, 
                        f"Expected {num_iterations} iterations")
        
        all_groupings = config.get('allGroupings', [])
        self.assertEqual(len(all_groupings), num_iterations, 
                        f"Expected {num_iterations} groupings")
        
        # Check if REGION is in the description
        description = config.get('ecosystemDescription', '')
        self.assertTrue(description, "No ecosystem description found")
        self.assertIn('REGION:', description, "No REGION field in AI response")
        
        # Check if final groups were generated
        self.assertTrue(group_names, "No groups were generated")
        self.assertTrue(group_dict, "Group dictionary is empty")
        
        # Print results for manual verification
        print(f"\nAI Response:")
        print(description)
        print(f"\nGenerated {len(group_names)} final consensus groups:")
        for name in group_names[:5]:
            print(f"- {name}")
        
        print(f"\nNumber of iterations saved: {len(all_groupings)}")

if __name__ == '__main__':
    unittest.main()
