# ====================== CORPUS TOOLS =====================

import vertexai
from vertexai.preview import rag
from copy import deepcopy
from google.adk.tools import FunctionTool
from typing import Dict, Optional, Any, List
import sys
import os
import pandas as pd
import re
from thefuzz import fuzz
from enum import Enum
import json

# Ensure parent directory is in path to allow imports if running as script or module
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

try:
    from config import (
        PROJECT_ID,
        LOCATION,
        RAG_DEFAULT_CORPUS_ID,
        RAG_DEFAULT_EMBEDDING_MODEL,
        RAG_DEFAULT_SEARCH_TOP_K,
        RAG_DEFAULT_TOP_K,
        RAG_DEFAULT_VECTOR_SIMILARITY_THRESHOLD,
        RAG_DEFAULT_CHUNK_SIZE,
        RAG_DEFAULT_CHUNK_OVERLAP,
        RAG_DEFAULT_EMBEDDING_REQUESTS_PER_MIN,
        POLICY_CORPUS_NAME,
        VAS_CORPUS_NAME,
    )
except ImportError:
    try:
        from config.config import (
            PROJECT_ID,
            LOCATION,
            RAG_DEFAULT_CORPUS_ID,
            RAG_DEFAULT_EMBEDDING_MODEL,
            RAG_DEFAULT_SEARCH_TOP_K,
            RAG_DEFAULT_TOP_K,
            RAG_DEFAULT_VECTOR_SIMILARITY_THRESHOLD,
            RAG_DEFAULT_CHUNK_SIZE,
            RAG_DEFAULT_CHUNK_OVERLAP,
            RAG_DEFAULT_EMBEDDING_REQUESTS_PER_MIN,
            POLICY_CORPUS_NAME,
            VAS_CORPUS_NAME,
        )
    except ImportError:
        # Fallback for relative import if master is not a package
        from ...config import (
            PROJECT_ID,
            LOCATION,
            RAG_DEFAULT_CORPUS_ID,
            RAG_DEFAULT_EMBEDDING_MODEL,
            RAG_DEFAULT_SEARCH_TOP_K,
            RAG_DEFAULT_TOP_K,
            RAG_DEFAULT_VECTOR_SIMILARITY_THRESHOLD,
            RAG_DEFAULT_CHUNK_SIZE,
            RAG_DEFAULT_CHUNK_OVERLAP,
            RAG_DEFAULT_EMBEDDING_REQUESTS_PER_MIN,
            POLICY_CORPUS_NAME,
            VAS_CORPUS_NAME,
        )

# initialize vertexai
vertexai.init(project=PROJECT_ID, location=LOCATION)

def create_corpus(
    display_name: str,
    description: Optional[str] = None,
    embedding_model: Optional[str] = None
) -> Dict[str, Any]:
    """
    Creates a new RAG corpus in Vertex AI.

    Args:
        display_name: A human-readable name for the corpus
        description: Optional description for the corpus
        embedding_model: The embedding model to use (default: configured RAG_DEFAULT_EMBEDDING_MODEL)

    Returns:
        A dictionary containing the created corpus details.
    """
    # Force usage of the configured embedding model, ignoring any Agent-provided value
    # This prevents issues where the Agent hallucinates "ada-002" or includes region prefixes
    embedding_model = RAG_DEFAULT_EMBEDDING_MODEL

    try:
        embedding_model_config = rag.EmbeddingModelConfig(
            publisher_model=embedding_model
        )

        corpus = rag.create_corpus(
            display_name=display_name,
            description=description or f"RAG corpus : {display_name}",
            embedding_model_config=embedding_model_config
        )

        # Corpus name format: projects/{project}/locations/{location}/ragCorpora/{corpus_id}
        corpus_id = corpus.name.split('/')[-1]

        return {
            "status": "success",
            "corpus_id": corpus_id,
            "display_name": display_name,
            "embedding_model": embedding_model, # Return actual used model
            "name": corpus.name,
            "message": f"Successfully created RAG corpus `{display_name}` using model `{embedding_model}`"
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": str(e),
            "message": f"Failed to create RAG corpus: {str(e)}"
        }

def update_corpus(
    corpus_id: str,
    display_name: Optional[str] = None,
    description: Optional[str] = None
) -> Dict[str, Any]:
    """
    Updates an existing RAG corpus with new display name and/or description.
    """
    try:
        corpus_name = f"projects/{PROJECT_ID}/locations/{LOCATION}/ragCorpora/{corpus_id}"

        # We need to fetch the corpus object first to update it via the SDK object-oriented way
        # OR use the update_corpus method if it accepts ID. 
        # The vertexai SDK usually requires passing the corpus name string or object to update_corpus.

        # Ideally:
        # rag.update_corpus(corpus_name=..., display_name=..., description=...)

        updated_corpus = rag.update_corpus(
            corpus_name=corpus_name,
            display_name=display_name,
            description=description
        )

        return {
            "status": "success",
            "corpus_name": updated_corpus.name,
            "corpus_id": corpus_id,
            "display_name": updated_corpus.display_name,
            "description": updated_corpus.description,
            "message": f"Successfully updated RAG corpus '{corpus_id}'"
        }
    except Exception as e:
        return {
            "status": "error",
            "corpus_id": corpus_id,
            "error_message": str(e),
            "message": f"Failed to update RAG corpus: {str(e)}"
        }

def list_corpora() -> Dict[str, Any]:
    """
    Lists all RAG corpora in the current project and location.
    """
    try:
        corpora = rag.list_corpora()

        corpus_list = []
        for corpus in corpora:
            corpus_id = corpus.name.split('/')[-1]

            # Safely get status
            status = "UNKNOWN"
            # Try different attribute paths for compatibility
            if hasattr(corpus, "corpus_status") and hasattr(corpus.corpus_status, "state"):
                status = str(corpus.corpus_status.state)

            corpus_list.append({
                "id": corpus_id,
                "name": corpus.name,
                "display_name": corpus.display_name,
                "description": getattr(corpus, "description", None),
                "create_time": str(getattr(corpus, "create_time", "")),
                "status": status
            })

        return {
            "status": "success",
            "corpora": corpus_list,
            "count": len(corpus_list),
            "message": f"Found {len(corpus_list)} RAG corpora"
        }
    except Exception as e:
        return {
            "status": "error",
            "error_message": str(e),
            "message": f"Failed to list RAG corpora: {str(e)}"
        }

def get_corpus(corpus_id: str) -> Dict[str, Any]:
    """
    Retrieves details of a specific RAG corpus.
    """
    try:
        corpus_name = f"projects/{PROJECT_ID}/locations/{LOCATION}/ragCorpora/{corpus_id}"
        corpus = rag.get_corpus(name=corpus_name)

        files_count = 0
        try:
            # Simple list to count
            files_iter = rag.list_files(corpus_name=corpus_name)
            # rag.list_files returns an iterable, need to convert to list to count
            files_count = len(list(files_iter))
        except:
            pass

        return {
            "status": "success",
            "corpus": {
                "id": corpus_id,
                "name": corpus.name,
                "display_name": corpus.display_name,
                "description": getattr(corpus, "description", None),
                "create_time": str(getattr(corpus, "create_time", "")),
                "files_count": files_count
            },
            "message": f"Successfully retrieved RAG corpus '{corpus_id}'"
        }
    except Exception as e:
        return {
            "status": "error",
            "corpus_id": corpus_id,
            "error_message": str(e),
            "message": f"Failed to retrieve RAG corpus: {str(e)}"
        }

def delete_corpus(corpus_id: str) -> Dict[str, Any]:
    """
    Deletes a RAG corpus.
    """
    try:
        corpus_name = f"projects/{PROJECT_ID}/locations/{LOCATION}/ragCorpora/{corpus_id}"
        rag.delete_corpus(name=corpus_name)
        return {
            "status": "success",
            "corpus_id": corpus_id,
            "message": f"Successfully deleted RAG corpus '{corpus_id}'"
        }
    except Exception as e:
        return {
            "status": "error",
            "corpus_id": corpus_id,
            "error_message": str(e),
            "message": f"Failed to delete RAG corpus: {str(e)}"
        }

def import_files(
    corpus_id: str,
    gcs_uris: List[str],
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    max_embedding_requests_per_min: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Imports files from Google Cloud Storage into a RAG corpus.
    """
    try:
        corpus_name = f"projects/{PROJECT_ID}/locations/{LOCATION}/ragCorpora/{corpus_id}"

        if chunk_size is None:
            chunk_size = RAG_DEFAULT_CHUNK_SIZE
        if chunk_overlap is None:
            chunk_overlap = RAG_DEFAULT_CHUNK_OVERLAP
        if max_embedding_requests_per_min is None:
            max_embedding_requests_per_min = RAG_DEFAULT_EMBEDDING_REQUESTS_PER_MIN

        transformation_config = rag.TransformationConfig(
            chunking_config=rag.ChunkingConfig(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            ),
        )

        response = rag.import_files(
            corpus_name,
            gcs_uris,
            transformation_config=transformation_config,
            max_embedding_requests_per_min=max_embedding_requests_per_min,
        )

        imported_count = 0
        failed_count = 0
        skipped_count = 0

        if hasattr(response, "imported_rag_files_count"):
             imported_count = response.imported_rag_files_count
        if hasattr(response, "failed_rag_files_count"):
             failed_count = response.failed_rag_files_count
        if hasattr(response, "skipped_rag_files_count"):
             skipped_count = response.skipped_rag_files_count

        return {
            "status": "success",
            "imported_count": imported_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "message": f"Successfully initiated import of {len(gcs_uris)} URIs into corpus '{corpus_id}'. Imported: {imported_count}, Failed: {failed_count}, Skipped: {skipped_count}"
        }
    except Exception as e:
        return {
            "status": "error",
            "corpus_id": corpus_id,
            "error_message": str(e),
            "message": f"Failed to import files: {str(e)}"
        }

def list_files(corpus_id: str) -> Dict[str, Any]:
    """
    Lists files in a RAG corpus.
    """
    try:
        corpus_name = f"projects/{PROJECT_ID}/locations/{LOCATION}/ragCorpora/{corpus_id}"
        files = rag.list_files(corpus_name=corpus_name)

        file_list = []
        for f in files:
            file_id = f.name.split('/')[-1]
            file_list.append({
                "id": file_id,
                "name": f.name,
                "display_name": f.display_name,
                "create_time": str(getattr(f, "create_time", ""))
            })

        return {
            "status": "success",
            "files": file_list,
            "count": len(file_list),
            "message": f"Found {len(file_list)} files in corpus '{corpus_id}'"
        }
    except Exception as e:
        return {
            "status": "error",
            "corpus_id": corpus_id,
            "error_message": str(e),
            "message": f"Failed to list files: {str(e)}"
        }

def get_file(corpus_id: str, file_id: str) -> Dict[str, Any]:
    """
    Retrieves details of a specific file in a RAG corpus.
    """
    try:
        # File name format: projects/{project}/locations/{location}/ragCorpora/{corpus}/ragFiles/{file}
        # But SDK usually takes `name` as the full resource name
        file_name = f"projects/{PROJECT_ID}/locations/{LOCATION}/ragCorpora/{corpus_id}/ragFiles/{file_id}"

        f = rag.get_file(name=file_name)

        return {
            "status": "success",
            "file": {
                "id": file_id,
                "name": f.name,
                "display_name": f.display_name,
                "create_time": str(getattr(f, "create_time", ""))
            },
            "message": f"Successfully retrieved file '{file_id}'"
        }
    except Exception as e:
        return {
            "status": "error",
            "error_message": str(e),
            "message": f"Failed to get file: {str(e)}"
        }

def delete_file_from_corpus(corpus_id: str, file_id: str) -> Dict[str, Any]:
    """
    Deletes a file from a RAG corpus.
    """
    try:
        file_name = f"projects/{PROJECT_ID}/locations/{LOCATION}/ragCorpora/{corpus_id}/ragFiles/{file_id}"
        rag.delete_file(name=file_name)
        return {
            "status": "success",
            "file_id": file_id,
            "message": f"Successfully deleted file '{file_id}' from corpus '{corpus_id}'"
        }
    except Exception as e:
        return {
            "status": "error",
            "error_message": str(e),
            "message": f"Failed to delete file: {str(e)}"
        }



class ProductName(str, Enum):
    PRUDENTIAL_ENCASH_HOSPITAL_CASH_SAVINGS_INSURANCE = "Prudential Encash Hospital Cash Savings Insurance"
    PREMIERFLEX_MEDICAL_PLAN = "PremierFlex Medical Plan"
    PRUHEALTH_CORECHOICE_MEDICAL_PLAN = "PRUHealth CoreChoice Medical Plan"
    PRUHEALTH_MEDICAL_PLUS = "PRUhealth medical plus"
    PRUHEALTH_VHIS_EASYCHOICE_PLAN = "PRUHealth VHIS EasyChoice Plan"
    PRUHEALTH_VHIS_VIP_PLAN = "PRUHealth VHIS VIP Plan"
    PRUMYHEALTH_PRESTIGE_MEDICAL_PLAN = "PRUmyhealth prestige medical plan"

class VASName(str, Enum):
    MEDICAL_GREEN_CHANNEL = "Medical Green Channel"
    MEDICAL_EXPENSES_DIRECT_BILLING_SERVICE = "Medical Expenses Direct Billing Service"
    PRUHEALTH_TEAM = "PRUHealth Team"
    SMARTAPPOINT_SERVICE = "SmartAppoint Service"
    TREATMENT_SURE = "Treatment Sure"
    HEALTHCARE_PLUS = "HealthCare+"
    WORLDWIDE_EMERGENCY_ASSISTANCE_SERVICES = "Worldwide emergency assistance services"

def _load_product_context() -> Dict[str, List[Dict[str, Any]]]:
    try:
        json_path = os.path.join(os.path.dirname(__file__), "prudential_products.json")
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # New structure: {"Product": [...], "VAS": [...]}
            products = data.get("Product", [])
            vas_services = data.get("VAS", [])
            
            return {
                "products": [item for item in products if item.get("Product") and item.get("Product") != "NA"],
                "vas_services": [item for item in vas_services if item.get("VAS") and item.get("VAS") != "NA"]
            }
    except Exception as e:
        print(f"Error loading product context: {e}")
        return {"products": [], "vas_services": []}

def query_corpus(
    query: str,
    product_name: Optional[ProductName] = None,
    vas_name: Optional[VASName] = None,
    similarity_top_k: int = RAG_DEFAULT_SEARCH_TOP_K,
    vector_similarity_threshold: float = RAG_DEFAULT_VECTOR_SIMILARITY_THRESHOLD,
    user_auth: bool = False,
) -> Dict[str, Any]:
    """
    Queries the RAG corpus for a specific product or VAS.
    If both product_name and vas_name are provided, it queries both corpora.
    """
    try:
        print(f"DEBUG: query_corpus called with query='{query}', product_name='{product_name}', vas_name='{vas_name}'")
        context_data = _load_product_context()
        #print(f"DEBUG: Loaded context data: {list(context_data)}")
        rag_resources = []

        # Policy Corpus ID
        policy_corpus_id = get_corpus_id_by_display_name(POLICY_CORPUS_NAME)
        print(f"policy_c: {policy_corpus_id}")
        # VAS Corpus ID
        vas_corpus_id = get_corpus_id_by_display_name(VAS_CORPUS_NAME)
        print(f"vas_c: {vas_corpus_id}")



        corpus = []

        # 1. Handle Product Name (Policy Corpus)
        if product_name:
            # Handle both Enum and string inputs
            target_product = product_name.value if hasattr(product_name, "value") else product_name
            print(F'DEBUG: target {target_product.lower()}')
            #print(F'DEBUG: prod {[item.get("Product").lower() for item in context_data.get("products", [])]}')
            matches = [item for item in context_data.get("products", []) if item.get("Product").lower() == target_product.lower()]
            

            # Extract and flatten all documents, splitting by semicolon if necessary
            target_files = []
            for m in matches:
                docs = m.get("Documents")
                if docs:
                    target_files.extend([d.strip() for d in docs.split(";") if d.strip()])
            
            print(f"DEBUG: Found {len(matches)} product matches for {target_product}")
            print(f"DEBUG: Target files for product: {target_files}")

            if target_files:
                rag_file_ids = get_file_ids_by_filter(policy_corpus_id, list(set(target_files)))
                print(f"DEBUG: Retrieved file IDs for product: {rag_file_ids}")
                if rag_file_ids:
                     corpus.append(POLICY_CORPUS_NAME)
                     rag_resources.append(rag.RagResource(
                        rag_corpus=f"projects/{PROJECT_ID}/locations/{LOCATION}/ragCorpora/{policy_corpus_id}",
                        rag_file_ids=rag_file_ids
                    ))
                else:
                    print(f"Warning: Documents {target_files} not found in policy corpus")

        # 2. Handle VAS Name (VAS Corpus)
        if vas_name:
            # Handle both Enum and string inputs
            target_vas = vas_name.value if hasattr(vas_name, "value") else vas_name
            print(F'DEBUG: target {target_vas.lower()}')
            print(F'DEBUG: vas {[item.get("VAS").lower() for item in context_data.get("vas_services", [])]}')
            matches = [item for item in context_data.get("vas_services", []) if item.get("VAS").lower() == target_vas.lower()]
            
            # Extract and flatten all documents, splitting by semicolon if necessary
            target_files = []
            for m in matches:
                docs = m.get("Documents")
                if docs:
                    target_files.extend([d.strip() for d in docs.split(";") if d.strip()])
                    
            print(f"DEBUG: Found {len(matches)} VAS matches for {target_vas}")
            print(f"DEBUG: Target files for VAS: {target_files}")

            if target_files:
                rag_file_ids = get_file_ids_by_filter(vas_corpus_id, list(set(target_files)))
                print(f"DEBUG: Retrieved file IDs for VAS: {rag_file_ids}")
                if rag_file_ids:
                    corpus.append(VAS_CORPUS_NAME)
                    rag_resources.append(rag.RagResource(
                        rag_corpus=f"projects/{PROJECT_ID}/locations/{LOCATION}/ragCorpora/{vas_corpus_id}",
                        rag_file_ids=rag_file_ids
                    ))
                else:
                     print(f"Warning: Documents {target_files} not found in VAS corpus")

        # 3. If no specific filters, use default behavior (Policy Corpus)
        if not rag_resources:
            print("DEBUG: No specific filters applied or no files found. defaulting to general Policy Corpus search.")
            rag_resources.append(rag.RagResource(
                rag_corpus=f"projects/{PROJECT_ID}/locations/{LOCATION}/ragCorpora/{policy_corpus_id}"
            ))

        # Build document-to-URL mapping for enrichment
        doc_to_url = {}
        for item in context_data.get("products", []):
            docs = item.get("Documents")
            url = item.get("URL")
            if docs and url:
                for d in docs.split(";"):
                    doc_to_url[d.strip()] = url
        for item in context_data.get("vas_services", []):
            docs = item.get("Documents")
            url = item.get("URL")
            if docs and url:
                for d in docs.split(";"):
                    doc_to_url[d.strip()] = url

        print(f"DEBUG: Final rag_resources count: {len(rag_resources)}")

        # Use RagRetrievalConfig to encapsulate retrieval parameters
        rag_retrieval_config = rag.RagRetrievalConfig(
            top_k=similarity_top_k,
            filter=rag.Filter(
                vector_similarity_threshold=vector_similarity_threshold
            ),
            

            # Enable reranking for better relevance.
            ranking=rag.Ranking(
                llm_ranker=rag.LlmRanker(model_name="gemini-2.5-flash")
            )
        )

        
        response = rag.retrieval_query(
            rag_resources=rag_resources,
            text=query,
            rag_retrieval_config=rag_retrieval_config
        )
        
        results = []
        if hasattr(response, "contexts"):
            contexts = response.contexts
            if hasattr(contexts, "contexts"):
                contexts = contexts.contexts

            for ctx in contexts:
                # Extract filename from source_uri (e.g., "gs://bucket/file.pdf" -> "file.pdf")
                filename = os.path.basename(ctx.source_uri)
                url = doc_to_url.get(filename)
                
                results.append({
                    "text": ctx.text,
                    "source_uri": ctx.source_uri,
                    "url": url,
                    "corpus": corpus,
                    "distance": ctx.distance
                })

        print(f"DEBUG: Retrieval returned {len(results)} results")
        return {
            "status": "success",
            "results": results,
            "count": len(results),
            "message": f"Found {len(results)} results for query"
        }
    except Exception as e:
        return {
            "status": "error",
            "error_message": str(e),
            "message": f"Failed to query corpus: {str(e)}"
        }


def parallel_check_relevant_corpus(
    query: str,
    per_corpus_top_k: int = RAG_DEFAULT_SEARCH_TOP_K
) -> Dict[str, Any]:
    try:
        corpora = rag.list_corpora()
        scores = []
        for corpus in corpora:
            corpus_id = corpus.name.split('/')[-1]
            q = query_corpus(
                corpus_id=corpus_id,
                query=query,
                similarity_top_k=per_corpus_top_k,
                vector_similarity_threshold=RAG_DEFAULT_VECTOR_SIMILARITY_THRESHOLD
            )
            avg_distance = None
            if q.get("status") == "success" and q.get("results"):
                ds = [r.get("distance", 1.0) for r in q["results"]]
                if ds:
                    avg_distance = sum(ds) / len(ds)
            scores.append({
                "corpus_id": corpus_id,
                "display_name": corpus.display_name,
                "avg_distance": avg_distance if avg_distance is not None else 1.0,
                "top_chunks": [
                    {
                        "text": r.get("text", ""),
                        "source_uri": r.get("source_uri", ""),
                        "filename": r.get("source_uri", "").split("/")[-1]
                    }
                    for r in (q.get("results") or [])[:per_corpus_top_k]
                ]
            })
        scores.sort(key=lambda x: x["avg_distance"])
        best = scores[0] if scores else None
        return {
            "status": "success",
            "best_corpus": best,
            "ranked": scores,
            "message": "Computed relevance across corpora"
        }
    except Exception as e:
        return {
            "status": "error",
            "error_message": str(e),
            "message": f"Failed to check relevant corpus: {str(e)}"
        }

def automated_evaluation_testcase(
    excel_path: str
) -> Dict[str, Any]:
    try:
        return {
            "status": "error",
            "message": "automated_evaluation_testcase requires Excel parsing dependency; provide CSV or install openpyxl"
        }
    except Exception as e:
        return {
            "status": "error",
            "error_message": str(e),
            "message": f"Failed to run automated evaluation: {str(e)}"
        }

def get_corpus_id_by_display_name(display_name: str) -> Optional[str]:
    """
    Helper: Finds a corpus ID by its display name.
    """
    try:
        corpora = rag.list_corpora()
        for corpus in corpora:
            if corpus.display_name == display_name:
                return corpus.name.split('/')[-1]
        return None
    except:
        return None

def get_file_ids_by_filter(corpus_id: str, filter_vals: List[str]) -> List[str]:
    """
    Helper: Finds all unique file IDs that match any of the display names or URI fragments/prefixes in a specific corpus.
    """
    try:
        corpus_name = f"projects/{PROJECT_ID}/locations/{LOCATION}/ragCorpora/{corpus_id}"
        files = rag.list_files(corpus_name=corpus_name)
        matched_ids = set()

        # rag.list_files returns an iterable, so we can iterate over it multiple times if needed,
        # but it's cleaner to loop through filters first.
        for filter_val in filter_vals:
            for f in files:
                # Check if it's a direct match or substring in the display name
                if f.display_name and (f.display_name.startswith(filter_val) or filter_val in f.display_name):
                    matched_ids.add(f.name.split('/')[-1])
                # If search is a URI, extract the filename part for matching
                elif filter_val.startswith("gs://") and "/" in filter_val:
                    filename_part = filter_val.split("/")[-1]
                    if f.display_name and (f.display_name.startswith(filename_part) or filename_part in f.display_name):
                        matched_ids.add(f.name.split('/')[-1])
        print(f"matched_ids: {list(matched_ids)}")
        return list(matched_ids)
    except:
        return []



def identify_policy_vas_context(query: str) -> List[Dict[str, Any]]:
    """
    Searches for matching product metadata in policy_metadata.csv and vas_metadata.csv based on the given query.

    Args:
        query (str): The query string to search for in the 'product' column.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, each containing a matching row from the metadata files.
                              Returns an empty list if no matches are found.
        Context (str): 'policy' or 'vas
    """

    # Construct the absolute path to the CSV files
    mcp_mock_data_dir = "./rag/tools/mcp_mock_data"
    policy_metadata_path = os.path.join(mcp_mock_data_dir, "policy_metadata.csv")
    vas_metadata_path = os.path.join(mcp_mock_data_dir, "vas_metadata.csv")

    try:
        # Read the policy metadata CSV into a DataFrame
        policy_metadata = pd.read_csv(policy_metadata_path)
    except FileNotFoundError:
        print(f"Error: policy_metadata.csv not found at {policy_metadata_path}")
        return {}

    try:
        # Read the vas metadata CSV into a DataFrame
        vas_metadata = pd.read_csv(vas_metadata_path)
    except FileNotFoundError:
        print(f"Error: vas_metadata.csv not found at {vas_metadata_path}")
        return {}

    matching_rows = []
    context = None

    # Search for matching product in policy metadata
    for index, row in policy_metadata.iterrows():
        product = str(row['Product'])
        if fuzz.partial_ratio(product.lower(), query.lower()) > 80:
            matching_rows.append(row.to_dict())
            context = 'policy'

    if matching_rows == []:
        # If no match is found in policy metadata, search in vas metadata
        for index, row in vas_metadata.iterrows():
            vas = str(row['VAS'])
            if fuzz.partial_ratio(vas.lower(), query.lower()) > 80:
                matching_rows.append(row.to_dict())
                context = 'vas'

    return matching_rows, context
 
