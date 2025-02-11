import os
import time
import tiktoken
import logging
from dotenv import load_dotenv
import re

load_dotenv()

from llama_index.core import (
    SimpleDirectoryReader, 
    StorageContext,
    Settings,
    load_index_from_storage,
    VectorStoreIndex,
    Document,
)
from llama_index.core.node_parser import MarkdownElementNodeParser
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import IndexNode
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.llms.bedrock import Bedrock
from llama_index.llms.azure_openai import AzureOpenAI
from llama_index.llms.openai import OpenAI
from llama_index.llms.anthropic import Anthropic
from llama_index.embeddings.bedrock import BedrockEmbedding
from llama_index.embeddings.azure_openai import AzureOpenAIEmbedding
from llama_parse import LlamaParse
import chromadb
import json

GREEN = '\033[92m'
RED = '\033[91m'
RESET = '\033[0m'

def print_green(text):
    print(f"{GREEN}{text}{RESET}")

# Set up logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

embed_model = AzureOpenAIEmbedding(
    deployment_name=os.environ.get("AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT"),
    api_version=os.environ.get("AZURE_OPENAI_VERSION"),
    api_key=os.environ.get("AZURE_OPENAI_KEY"),
    azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
    embed_batch_size=1,
)

Settings.embed_model = embed_model

MAX_CHUNK_SIZE = 2000  # Reduced chunk size to avoid token limits

def get_llm(ai_model):
    if ai_model == 'aws_claude':
        return Bedrock(model='anthropic.claude-3-5-sonnet-20240620-v1:0')
    elif ai_model == 'azure_openai':
        return AzureOpenAI(
            engine=os.environ.get("AZURE_OPENAI_DEPLOYMENT"),
            api_key=os.environ.get("AZURE_OPENAI_KEY"),
            api_version=os.environ.get("AZURE_OPENAI_VERSION"),
            azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT")
        )
    elif ai_model == 'openai':
        return OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    elif ai_model == 'claude':
        return Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    else:
        raise ValueError(f"Unknown AI model: {ai_model}")

def num_tokens_from_string(string: str, encoding_name: str = "cl100k_base") -> int:
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens

def split_document(doc, max_tokens=MAX_CHUNK_SIZE):
    text = doc.text
    metadata = doc.metadata
    chunks = []
    current_chunk = ""
    current_tokens = 0

    sentences = text.split('. ')
    for sentence in sentences:
        sentence_tokens = num_tokens_from_string(sentence)
        if current_tokens + sentence_tokens > max_tokens:
            chunks.append(Document(text=current_chunk, metadata=metadata))
            current_chunk = sentence
            current_tokens = sentence_tokens
        else:
            current_chunk += ". " + sentence if current_chunk else sentence
            current_tokens += sentence_tokens

    if current_chunk:
        chunks.append(Document(text=current_chunk, metadata=metadata))

    return chunks

def load_documents(input_files):
    parser = LlamaParse(result_type="markdown")
    documents = []
    try:
        if isinstance(input_files, str) and os.path.isdir(input_files):
            for root, _, files in os.walk(input_files):
                for file in files:
                    file_path = os.path.join(root, file)
                    if file.endswith('.json'):
                        with open(file_path, 'r') as f:
                            json_data = json.load(f)
                        doc = Document(text=json.dumps(json_data, indent=2), metadata={"file_name": file_path})
                        documents.append(doc)
                    elif file.endswith('.pdf'):
                        pdf_docs = parser.load_data(file_path)
                        documents.extend(pdf_docs)
        else:
            for file in input_files:
                if file.endswith('.json'):
                    with open(file, 'r') as f:
                        json_data = json.load(f)
                    doc = Document(text=json.dumps(json_data, indent=2), metadata={"file_name": file})
                    documents.append(doc)
                elif file.endswith('.pdf'):
                    pdf_docs = parser.load_data(file)
                    documents.extend(pdf_docs)
        
        processed_documents = []
        for doc in documents:
            doc_tokens = num_tokens_from_string(doc.text)
            logging.debug(f"Document '{doc.metadata.get('file_name', 'Unknown')}' has {doc_tokens} tokens")
            if doc_tokens > MAX_CHUNK_SIZE:
                split_docs = split_document(doc)
                logging.debug(f"Split into {len(split_docs)} chunks")
                processed_documents.extend(split_docs)
            else:
                processed_documents.append(doc)
        logging.info(f"Loaded {len(processed_documents)} document chunks")
        return processed_documents
    except Exception as e:
        logging.error(f"Error loading documents: {e}")
        logging.error(f"Input files: {input_files}")
        return None

def chunk_query_results(results, max_tokens=MAX_CHUNK_SIZE):
    chunked_results = []
    current_chunk = ""
    current_tokens = 0

    for result in results:
        result_tokens = num_tokens_from_string(result)
        if current_tokens + result_tokens > max_tokens:
            chunked_results.append(current_chunk)
            current_chunk = result
            current_tokens = result_tokens
        else:
            current_chunk += "\n" + result if current_chunk else result
            current_tokens += result_tokens

    if current_chunk:
        chunked_results.append(current_chunk)

    return chunked_results

def rag_search(query, directory, ai_model='claude'):
    # Ensure the directory path is absolute
    directory = os.path.abspath(directory)
    
    if not os.path.exists(directory):
        raise ValueError(f"Directory does not exist: {directory}")
    
    chroma_client = chromadb.PersistentClient()
    chroma_collection = chroma_client.get_or_create_collection(os.path.basename(directory))
    
    def get_or_create_index(store, persist_dir, chroma_collection):
        index_files_path = os.path.join(persist_dir, 'indexed_files.json')
        
        if os.path.exists(persist_dir):
            logging.info(f"Loading existing index from {persist_dir}...")
            storage_context = StorageContext.from_defaults(persist_dir=persist_dir)
            vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
            index = VectorStoreIndex.from_vector_store(vector_store, storage_context=storage_context)
            
            if os.path.exists(index_files_path):
                with open(index_files_path, 'r') as f:
                    indexed_files = set(json.load(f))
            else:
                indexed_files = set()
            
            current_files = set(get_all_files(store))
            new_files = current_files - indexed_files
            
            if new_files:
                logging.info(f"Found {len(new_files)} new files. Updating index...")
                new_documents = load_documents(list(new_files))
                if new_documents:
                    index.insert_nodes(new_documents)
                    
                    indexed_files.update(new_files)
                    with open(index_files_path, 'w') as f:
                        json.dump(list(indexed_files), f)
                    logging.info("Index Successfully Updated...")
                else:
                    logging.warning('Documents failed to load.')
            logging.info("Index Successfully Loaded")
        else:
            logging.info(f"Creating new index for {store}...")
            documents = load_documents(store)
            if not documents:
                raise ValueError(f"No documents found in {store}")
            
            vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
            storage_context = StorageContext.from_defaults(vector_store=vector_store)
            index = VectorStoreIndex(documents, storage_context=storage_context)
            index.storage_context.persist(persist_dir=persist_dir)
            
            indexed_files = get_all_files(store)
            with open(index_files_path, 'w') as f:
                json.dump(indexed_files, f)
            
            logging.info(f"Index Successfully Created for {store}")
        
        return index
    
    def get_all_files(directory):
        file_list = []
        for root, _, files in os.walk(directory):
            for file in files:
                file_list.append(os.path.join(root, file))
        return file_list

    def extract_model_numbers(results):
        """Extract model numbers from RAG search results"""
        model_numbers = set()
        for result in results:
            # Try to find a list enclosed in square brackets
            list_match = re.search(r'\[([\d,\s]+)\]', result)
            if list_match:
                # If found, split the string into a list and convert to integers
                number_list = [int(num.strip()) for num in list_match.group(1).split(',') if num.strip().isdigit()]
                model_numbers.update(number_list)
            else:
                # If no list is found, fall back to extracting all numbers from the text
                numbers = [int(num) for num in re.findall(r'\b\d+\b', result)]
                model_numbers.update(numbers)
        return list(model_numbers)

    store = directory
    persist_dir = os.path.join(os.path.dirname(directory), f'storage_chroma_{os.path.basename(directory)}')

    index = get_or_create_index(store, persist_dir, chroma_collection)
    
    llm = get_llm(ai_model)
    query_engine = index.as_query_engine(llm=llm)
    response = query_engine.query(query)
    out = response.response
    citations = list(set(entry['file_name'] for entry in response.metadata.values()))
    
    # Chunk the results if they exceed the token limit
    chunked_results = chunk_query_results([out])
    
    print_green(chunked_results[0])  # Print the first chunk
    return chunked_results, citations

if __name__ == "__main__":
    # Test the rag_search function with different AI models
    query = "What do seabirds eat?"
    directory = "SW_Atlantis_Diets_of_Functional_Groups"
    ai_models = ['claude', 'aws_claude', 'azure_openai', 'openai']
    
    for model in ai_models:
        try:
            print(f"\nTesting with {model} model:")
            result, citations = rag_search(query, directory, ai_model=model)
            print("\nResult:", result)
            print("\nCitations:", citations)
        except Exception as e:
            logging.error(f"Test query failed for {model}: {str(e)}")
