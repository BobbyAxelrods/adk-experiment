# ====================== CORPUS TOOLS =====================

import vertexai
from vertexai import rag
from google.adk.tools import FunctionTool
from typing import Dict, Optional, Any, List
import sys
import os
import logging

logger = logging.getLogger(__name__)

# Ensure parent directory is in path to allow imports if running as script or module
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

try:
    from config.config import (
        PROJECT_ID,
        LOCATION,
        RAG_DEFAULT_CORPUS_ID,
        RAG_DEFAULT_EMBEDDING_MODEL,
        RAG_DEFAULT_SEARCH_TOP_K,
        RAG_DEFAULT_TOP_K,
        RAG_DEFAULT_VECTOR_DISTANCE_THRESHOLD,
        RAG_DEFAULT_CHUNK_SIZE,
        RAG_DEFAULT_CHUNK_OVERLAP,
        RAG_DEFAULT_EMBEDDING_REQUESTS_PER_MIN,
    )
except ImportError:
    # Fallback/Defaults
    PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
    LOCATION = os.getenv("LOCATION", "us-central1")
    RAG_DEFAULT_CORPUS_ID = os.getenv("RAG_DEFAULT_CORPUS_ID")
    RAG_DEFAULT_EMBEDDING_MODEL = "publishers/google/models/text-embedding-004"
    RAG_DEFAULT_SEARCH_TOP_K = 5
    RAG_DEFAULT_TOP_K = 10
    RAG_DEFAULT_VECTOR_DISTANCE_THRESHOLD = 0.5
    RAG_DEFAULT_CHUNK_SIZE = 512
    RAG_DEFAULT_CHUNK_OVERLAP = 100
    RAG_DEFAULT_EMBEDDING_REQUESTS_PER_MIN = 1000

# Initialize Vertex AI
if PROJECT_ID:
    vertexai.init(project=PROJECT_ID, location=LOCATION)

def create_corpus(
    display_name: str,
    description: Optional[str] = None,
    embedding_model: Optional[str] = None
) -> Dict[str, Any]:
    """Creates a new RAG corpus in Vertex AI."""
    embedding_model = embedding_model or RAG_DEFAULT_EMBEDDING_MODEL
    try:
        # Configure embedding model
        embedding_model_config = rag.EmbeddingModelConfig(
            publisher_model=f"publishers/google/models/{embedding_model.split('/')[-1]}"
        )
        
        corpus = rag.create_corpus(
            display_name=display_name,
            description=description or f"RAG corpus : {display_name}",
            embedding_model_config=embedding_model_config
        )
        
        # Extract ID from full resource name
        # Name format: projects/.../locations/.../ragCorpora/{id}
        corpus_id = corpus.name.split('/')[-1]
        return {"status": "success", "corpus_id": corpus_id, "display_name": display_name}
    except Exception as e:
        logger.error(f"Error creating corpus: {e}")
        return {"status": "error", "message": str(e)}

def list_corpora() -> List[Dict[str, Any]]:
    """Lists all RAG corpora."""
    try:
        corpora = rag.list_corpora()
        return [{"display_name": c.display_name, "name": c.name} for c in corpora]
    except Exception as e:
        logger.error(f"Error listing corpora: {e}")
        return []

def get_corpus_id_by_display_name(display_name: str) -> Optional[str]:
    """Finds a corpus ID by its display name."""
    corpora = list_corpora()
    for c in corpora:
        if c["display_name"] == display_name:
            return c["name"].split('/')[-1]
    return None

def query_corpus(query: str, corpus_id: Optional[str] = None) -> str:
    """
    Retrieve factual information from the Prudential knowledge base about policies, products, and health.
    
    Queries the RAG corpus for information.
    """
    target_corpus_id = corpus_id or RAG_DEFAULT_CORPUS_ID
    if not target_corpus_id:
        return "No corpus ID configured."

    try:
        # Construct full corpus name if only ID provided
        if "/" not in target_corpus_id:
            corpus_name = f"projects/{PROJECT_ID}/locations/{LOCATION}/ragCorpora/{target_corpus_id}"
        else:
            corpus_name = target_corpus_id
        
        response = rag.retrieval_query(
            rag_resources=[rag.RagResource(
                rag_corpus=corpus_name,
            )],
            text=query,
            rag_retrieval_config=rag.RagRetrievalConfig(
                top_k=RAG_DEFAULT_SEARCH_TOP_K,
                filter=None,
            )
        )
        
        context = ""
        if response and response.contexts:
            for context_item in response.contexts.contexts:
                context += context_item.text + "\n\n"
        
        if not context:
            return "No relevant information found in the knowledge base."
            
        return context

    except Exception as e:
        logger.error(f"Error querying corpus: {e}")
        return f"Error retrieving information: {str(e)}"

def import_files(corpus_id: str, gcs_uris: List[str]) -> Dict[str, Any]:
    """Imports files from GCS to the corpus."""
    try:
        if "/" not in corpus_id:
            corpus_name = f"projects/{PROJECT_ID}/locations/{LOCATION}/ragCorpora/{corpus_id}"
        else:
            corpus_name = corpus_id

        response = rag.import_files(
            rag_corpus=corpus_name,
            paths=gcs_uris,
            chunk_size=RAG_DEFAULT_CHUNK_SIZE,
            chunk_overlap=RAG_DEFAULT_CHUNK_OVERLAP
        )
        return {"status": "success", "imported_count": response.imported_rag_files_count}
    except Exception as e:
        logger.error(f"Error importing files: {e}")
        return {"status": "error", "message": str(e)}

def delete_file_from_corpus(file_name: str, corpus_id: str) -> Dict[str, Any]:
    """Deletes a file from the corpus."""
    try:
        if "/" not in corpus_id:
            corpus_name = f"projects/{PROJECT_ID}/locations/{LOCATION}/ragCorpora/{corpus_id}"
        else:
            corpus_name = corpus_id
            
        # Need to find the file ID first
        files = rag.list_files(rag_corpus=corpus_name)
        target_file = None
        for f in files:
            if f.display_name == file_name:
                target_file = f
                break
        
        if target_file:
            rag.delete_file(name=target_file.name)
            return {"status": "success", "message": f"Deleted {file_name}"}
        else:
            return {"status": "error", "message": "File not found"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}

def delete_corpus(corpus_id: str) -> Dict[str, Any]:
    """Deletes a corpus."""
    try:
        if "/" not in corpus_id:
            corpus_name = f"projects/{PROJECT_ID}/locations/{LOCATION}/ragCorpora/{corpus_id}"
        else:
            corpus_name = corpus_id
            
        rag.delete_corpus(name=corpus_name)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def list_files(corpus_id: str) -> List[Dict[str, Any]]:
    """Lists files in a corpus."""
    try:
        if "/" not in corpus_id:
            corpus_name = f"projects/{PROJECT_ID}/locations/{LOCATION}/ragCorpora/{corpus_id}"
        else:
            corpus_name = corpus_id
            
        files = rag.list_files(rag_corpus=corpus_name)
        return [{"display_name": f.display_name, "name": f.name} for f in files]
    except Exception as e:
        logger.error(f"Error listing files: {e}")
        return []

def identify_policy_vas_context(query: str, product_name: Optional[str] = None, vas_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Helper to identify policy and VAS context for a given query.
    Returns relevant filenames to enrich corpus queries with specific policy/VAS context.

    Args:
        query: The user's question.
        product_name: Optional product name to filter (e.g. 'PremierFlex').
        vas_name: Optional VAS name to filter (e.g. 'Medical Green Channel').

    Returns:
        Dict with context details including suggested filenames.
    """
    return {
        "query": query,
        "product_name": product_name,
        "vas_name": vas_name,
        "status": "ok",
        "message": "Use query_corpus with the provided product_name and vas_name filters."
    }


# ADK Tool Definition
query_corpus = FunctionTool(func=query_corpus)
identify_policy_vas_context = FunctionTool(func=identify_policy_vas_context)
