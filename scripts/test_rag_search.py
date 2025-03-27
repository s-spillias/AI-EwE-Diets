import os
import unittest
import tempfile
import json
from rag_search import load_documents, Document
import shutil

class TestRagSearch(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for test files
        self.test_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        # Clean up the temporary directory
        shutil.rmtree(self.test_dir)
    
    def test_load_json_document(self):
        # Test JSON file handling
        test_json = {"test": "data"}
        json_path = os.path.join(self.test_dir, "test.json")
        with open(json_path, 'w') as f:
            json.dump(test_json, f)
        
        # Test single file
        docs = load_documents([json_path])
        self.assertIsNotNone(docs)
        self.assertEqual(len(docs), 1)
        self.assertIn("test.json", docs[0].metadata["file_name"])
        self.assertIn("test", json.loads(docs[0].text))
        
        # Test directory
        docs = load_documents(self.test_dir)
        self.assertIsNotNone(docs)
        self.assertEqual(len(docs), 1)
        self.assertIn("test.json", docs[0].metadata["file_name"])
    
    def test_load_nonexistent_file(self):
        # Test handling of non-existent files
        docs = load_documents([os.path.join(self.test_dir, "nonexistent.json")])
        self.assertIsNone(docs)
    
    def test_load_empty_directory(self):
        # Test handling of empty directory
        docs = load_documents(self.test_dir)
        self.assertIsNotNone(docs)
        self.assertEqual(len(docs), 0)
    
    def test_document_chunking(self):
        # Create a document that will definitely exceed MAX_CHUNK_SIZE in tokens
        # Each word is roughly 1.3 tokens, so 4000 words should give us >5000 tokens
        words = ["testing"] * 4000
        large_content = {"data": " ".join(words)}
        json_path = os.path.join(self.test_dir, "large.json")
        with open(json_path, 'w') as f:
            json.dump(large_content, f)
        
        docs = load_documents([json_path])
        self.assertIsNotNone(docs)
        self.assertGreater(len(docs), 1)  # Should be split into multiple chunks
        
        # Verify each chunk is within MAX_CHUNK_SIZE
        from rag_search import num_tokens_from_string, MAX_CHUNK_SIZE
        for doc in docs:
            tokens = num_tokens_from_string(doc.text)
            self.assertLessEqual(tokens, MAX_CHUNK_SIZE)
        
    def test_load_multiple_files(self):
        # Test handling multiple files
        for i in range(3):
            json_path = os.path.join(self.test_dir, f"test{i}.json")
            with open(json_path, 'w') as f:
                json.dump({"test": f"data{i}"}, f)
        
        docs = load_documents(self.test_dir)
        self.assertIsNotNone(docs)
        self.assertEqual(len(docs), 3)

    def test_docx_handling(self):
        # Test that .docx files are not processed yet
        # This test verifies current behavior before we implement .docx support
        docx_path = os.path.join(self.test_dir, "test.docx")
        # Create an empty .docx file
        with open(docx_path, 'wb') as f:
            f.write(b'PK\x03\x04' + b'\x00' * 30)  # Minimal valid docx file header
        
        docs = load_documents([docx_path])
        self.assertIsNotNone(docs)
        self.assertEqual(len(docs), 0)  # Should not process .docx files yet

if __name__ == '__main__':
    unittest.main()
