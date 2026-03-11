import os 
import hashlib
import math
import json
import io
import time
import re
import numpy as np
from typing import Any, Optional, List, Dict
import pandas as pd 
import datetime
import logging
from google.cloud import storage
from google.adk.tools import FunctionTool, ToolContext
import sys
from dotenv import load_dotenv
from google import genai
from google.cloud import aiplatform
import vertexai
import math
from thefuzz import fuzz
from vertexai.preview.language_models import TextEmbeddingModel

_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env")
if os.path.exists(_env_path):
    load_dotenv(_env_path)
else:
    load_dotenv()

from tools.corpus.corpus_tools import (
    get_corpus_id_by_display_name,
    query_corpus,
    import_files,
    delete_file_from_corpus,
    create_corpus,
    delete_corpus,
    list_corpora,
    list_files
)
from tools.storage.storage_tools import create_gcs_bucket, list_blobs
from config.config import (
    PROJECT_ID, 
    RAG_DEFAULT_TOP_K,
    LOCATION, 
    EVAL_BUCKET_NAME,
)

# Import tone tools
try:
    from tools.tone_management.tone_tools import (
        apply_tone_guidelines, 
        validate_tone_compliance,
        classify_tone_group,
        get_tone_guidelines_by_group
    )
except ImportError:
    apply_tone_guidelines = None
    validate_tone_compliance = None
    classify_tone_group = None
    get_tone_guidelines_by_group = None

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

try:
    storage_client = storage.Client(project=PROJECT_ID)
except Exception as e:
    logger.error(f"Failed to initialize storage client: {e}")
    storage_client = None


def _get_genai_client() -> Optional[genai.Client]:
    use_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true"
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GENAI_LOCATION") or os.getenv("GOOGLE_CLOUD_LOCATION") or LOCATION
    if use_vertex and project_id and location:
        try:
            return genai.Client(vertexai=True, project=project_id, location=location)
        except Exception:
            return None
    api_key = os.getenv("GOOGLE_API_KEY")
    if api_key:
        try:
            return genai.Client(api_key=api_key)
        except Exception:
            return None
    return None

def _evaluate_with_llm(query: str, response: str, ground_truth: str) -> Dict[str, Any]:
    try:
        client = _get_genai_client()
        prompt = f"""
        You are an expert evaluator for RAG systems.
        
        Query: {query}
        Generated Response (Retrieved Context): {response}
        Ground Truth: {ground_truth}
        
        Task:
        1. Compare the Generated Response with the Ground Truth.
        2. Assign a score between 0.0 and 1.0 (1.0 being perfect match in meaning).
        3. Provide a brief reason.
        
        Output JSON format:
        {{
            "score": float,
            "reason": "string"
        }}
        """
        if client:
            model_name = os.getenv("LLM_MODEL", "gemini-2.5-flash")
            completion = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            content = completion.text or ""
        else:
            model_name = os.getenv("AZURE", "azure/gpt-4o")
            completion = litellm.completion(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant designed to output JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={ "type": "json_object" }
            )
            content = completion.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        return {"score": 0.0, "reason": f"Evaluation failed: {str(e)}"}

def _generate_answer(query: str, context: str) -> str:
    try:
        client = _get_genai_client()
        prompt = f"""

        # Prudential Knowledge & Policy Agent
 
        You are the **Knowledge Agent RAG agent** and **Universal Query Handler** for Prudential. Your role is to answer factual health, policy, and service questions using the Prudential knowledge base, as well as handle user-specific policy inquiries. always use `query_corpus` to retrieve factual information before answering
        
        
        #### A. Sample Questions
        *(e.g., "What is the claim process?", "Tell me about Treatment Sure", "Hotline number")*
        1. **Retrieve Content**:
        Use context: {context} to generate answers as the best of your understanding.

        
        #### B: Final Output
        Return the answer following the format below:
        1. **Apply Tone**: Follow the **Peace-of-Mind Formula**: **Empathise** -> **Guide** -> **Reassure**. Your persona guidelines are automatically applied to your prompt.
        2. **Style**: Keep the tone human, warm, and supportive. Use active voice.
        3. **Length**: Maximum 20 words per sentence.
        4. **Output**: Use the specific formats defined below.
 
        
        Query: 
        {query}
        
        """
        if client:
            model_name = os.getenv("LLM_MODEL", "gemini-2.5-flash")
            completion = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            text = completion.text or ""
            return text.strip()
        model_name = os.getenv("AZURE", "azure/gpt-4o")
        completion = litellm.completion(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        return f"Generation failed: {str(e)}"



def _calculate_cosine_similarity(text1: str, text2: str) -> float:
    """Calculates cosine similarity using Vertex AI text-embedding-004."""
    try:
        model = TextEmbeddingModel.from_pretrained("text-embedding-004")
        embeddings = model.get_embeddings([text1, text2])
        vec1 = np.array(embeddings[0].values)
        vec2 = np.array(embeddings[1].values)
        
        dot_product = np.dot(vec1, vec2)
        norm_a = np.linalg.norm(vec1)
        norm_b = np.linalg.norm(vec2)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0

        similarity = dot_product / (norm_a * norm_b)
        return float(similarity)
    except Exception as e:
        logger.error(f"Cosine similarity calculation failed: {e}")
        return 0.0

def _normalize_filename(uri: str) -> str:
    """
    Extracts the base filename (lowercase, no extension) from a URI or file path.
    Example: "gs://bucket/folder/File-Name.pdf" -> "file-name"
    Handles removing parenthesis content and normalizing separators.
    """
    if not uri or pd.isna(uri):
        return ""
    
    # 1. Get basename
    base = os.path.basename(str(uri))
    
    # 2. Remove extension
    name = os.path.splitext(base)[0]
    
    # 3. Remove content in parentheses (e.g. "Treatment Sure (webpage)" -> "Treatment Sure")
    name = re.sub(r'\([^)]*\)', '', name)
    
    # 4. Replace special chars ([-_]) with space
    name = re.sub(r'[-_]', ' ', name)
    
    # 5. Normalize whitespace (strip and collapse multiple spaces)
    name = " ".join(name.split())
    
    return name.lower()

def _calculate_retrieval_metrics(retrieved_chunk: List[str], ground_truth_chunk: List[str], retrieved_uris: List[str], ground_truth_docs: List[str], retrieved_corpus: str, ground_truth_corpus: str, k_doc: int = 20, k_chunk: int = 20, k_corpus: int = 20) -> Dict[str, float]:
    """
    Calculates score retrieval of chunk, docs and corpus.
    """
    # Normalize inputs
    retrieved_norm_raw_doc = [_normalize_filename(u) for u in retrieved_uris]
    retrieved_norm_raw_chunk = [_normalize_filename(u) for u in retrieved_chunk]
    retrieved_norm_raw_corpus = [_normalize_filename(u) for u in retrieved_corpus]

    gt_norm_doc = set([_normalize_filename(g) for g in ground_truth_docs if _normalize_filename(g)])
    gt_norm_chunk = set([_normalize_filename(g) for g in ground_truth_chunk if _normalize_filename(g)])
    gt_norm_corpus = set([_normalize_filename(g) for g in ground_truth_corpus if _normalize_filename(g)])
    
    if not gt_norm_doc and not gt_norm_chunk and not gt_norm_corpus:
        return {"retrieved_doc_cosine": 0.0,  
                "retrieved_chunk_cosine": 0.0,  
                "retrieved_corpus_cosine": 0.0,
                }

    # Deduplicate retrieved items based on Ground Truth matching (Strict Document Level)
    # 1. Map each retrieved item to its matched GT document (if any)
    # 2. Deduplicate the resulting list preserving order
    retrieved_unique = []
    seen_docs = set() # Stores the normalized doc string (either GT name or original doc name)

    for doc in retrieved_norm_raw_doc:
        # Check if this doc matches any Ground Truth
        matched_gt_doc = None
        for gt in gt_norm_doc:
            # Match if strings are equal, or one is substring of another
            if fuzz.partial_ratio(doc, gt) > 90:
                matched_gt_doc = gt # Use the GT doc for canonical representation
                break
        
        # Use the matched GT name if found, otherwise use the original doc name
        item_to_add = matched_gt_doc if matched_gt_doc else doc
        
        if item_to_add not in seen_docs:
            retrieved_unique.append(item_to_add)
            seen_docs.add(item_to_add)

    # Slice to top K (Document Level)
    retrieved_k_doc = retrieved_unique[:k_doc]
    print(f"retrieved_k_doc: {retrieved_k_doc}")
    # Calculate Matches (Strict Document Level)
    matches_count = 0
    dcg = 0.0
    
    for i, doc in enumerate(retrieved_k_doc):
        # Check strict existence in GT set (since we already mapped them)
        if doc in gt_norm_doc:
            matches_count += 1
            # DCG: Binary relevance = 1
            dcg += 1.0 / math.log2(i + 2)

    # 1. Recall (Document-Level)
    # Unique Matches / Total Unique GT
    recall_doc = matches_count / len(gt_norm_doc)
    
    # 2. Precision (Document-Level)
    # Unique Matches / Total Unique Retrieved (Dynamic K)
    # This ensures 1/1 = 1.0 (100%)
    precision_doc = matches_count / len(retrieved_k_doc) if retrieved_k_doc else 0.0
    

    # Deduplicate retrieved items based on Ground Truth matching (Strict Chunk Level)
    # 1. Map each retrieved item to its matched GT Chunk (if any)
    # 2. Deduplicate the resulting list preserving order
    retrieved_unique = []
    seen_chunks = set() # Stores the normalized chunk string

    for chunk in retrieved_norm_raw_chunk:
        # Check if this chunk matches any Ground Truth
        matched_gt_chunk = None
        for gt in gt_norm_chunk:
            # Match if strings are equal, or one is substring of another
            if fuzz.partial_ratio(chunk, gt) > 90:
                matched_gt_chunk = gt # Use the GT chunk for canonical representation
                break
        
        # Use the matched GT name if found, otherwise use the original chunk
        item_to_add = matched_gt_chunk if matched_gt_chunk else chunk
        
        if item_to_add not in seen_chunks:
            retrieved_unique.append(item_to_add)
            seen_chunks.add(item_to_add)

    # Slice to top K (Chunk Level)
    retrieved_k_chunk = retrieved_unique[:k_chunk]
    #print(f"retrieved_k_chunk: {retrieved_k_chunk}")
    
    # Calculate Matches (Strict Chunk Level)
    # matches_count = 0
    # dcg = 0.0
    
    # for i, doc in enumerate(retrieved_k_chunk):
    #     # Check strict existence in GT set (since we already mapped them)
    #     if doc in gt_norm_chunk:
    #         matches_count += 1
    #         # DCG: Binary relevance = 1
    #         dcg += 1.0 / math.log2(i + 2)

    # 1. Recall (Chunk-Level)
    # Unique Matches / Total Unique GT
    # recall_chunk = matches_count / len(gt_norm_chunk)
    
    # 2. Precision (Chunk-Level)
    # Unique Matches / Total Unique Retrieved (Dynamic K)
    # This ensures 1/1 = 1.0 (100%)
    # precision_chunk = matches_count / len(retrieved_k_chunk) if retrieved_k_chunk else 0.0
    

    # Deduplicate retrieved items based on Ground Truth matching (Strict Corpus Level)
    # 1. Map each retrieved item to its matched GT corpus (if any)
    # 2. Deduplicate the resulting list preserving order
    retrieved_unique = []
    seen_corpus = set() # Stores the normalized corpus string

    for corpus in retrieved_norm_raw_corpus:
        # Check if this corpus matches any Ground Truth
        matched_gt_corpus = None
        for gt in gt_norm_corpus:
            # Match if strings are equal, or one is substring of another
            if fuzz.partial_ratio(corpus, gt) > 90:
                matched_gt_corpus = gt # Use the GT chunk for canonical representation
                break
        
        # Use the matched GT name if found, otherwise use the original corpus
        item_to_add = matched_gt_corpus if matched_gt_corpus else corpus
        
        if item_to_add not in seen_corpus:
            retrieved_unique.append(item_to_add)
            seen_corpus.add(item_to_add)

    # Slice to top K (Chunk Level)
    retrieved_k_corpus = retrieved_unique[:k_corpus]
    print(f"retrieved_k_corpus: {retrieved_k_corpus}")
    
    # Calculate Matches (Strict Chunk Level)
    # matches_count = 0
    # dcg = 0.0
    
    # for i, doc in enumerate(retrieved_k_corpus):
    #     # Check strict existence in GT set (since we already mapped them)
    #     if doc in gt_norm_corpus:
    #         matches_count += 1
    #         # DCG: Binary relevance = 1
    #         dcg += 1.0 / math.log2(i + 2)

    # 1. Recall (Chunk-Level)
    # Unique Matches / Total Unique GT
    # recall_corpus = matches_count / len(gt_norm_corpus)
    
    # 2. Precision (corpus-Level)
    # Unique Matches / Total Unique Retrieved (Dynamic K)
    # This ensures 1/1 = 1.0 (100%)
    # precision_corpus = matches_count / len(retrieved_k_corpus) if retrieved_k_corpus else 0.0
    
    
    return {
        "retrieved_doc": round(recall_doc, 4),
        "precision_doc": round(precision_doc, 4),
        "recall_chunk": round(recall_chunk, 4),
        "precision_chunk": round(precision_chunk, 4),
        "recall_corpus": round(recall_corpus, 4),
        "precision_corpus": round(precision_corpus, 4),
    }

def _clean_chunk_text(text: str) -> str:
    """
    Cleans retrieval chunks by removing common navigational noise.
    """
    if not text:
        return ""
    
    # Remove specific noise patterns
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        # Skip empty lines
        if not line:
            continue
        # Skip navigation items
        if line.startswith('* Home') or line.startswith('* Health services') or \
           line.startswith('* Value-added service') or line.startswith('Skip links') or \
           line == 'PreviousNext' or line == 'Expand all' or \
           line.startswith('Please click here') or \
           line.startswith('Treatment Sure service hotline') or \
           line.startswith('Call us by one of these numbers'):
            continue
        cleaned_lines.append(line)
        
    return " ".join(cleaned_lines)

def _calculate_simple_retrieval_metrics(
    retrieved_chunk: List[str],
    query_list: List[str],
    ground_truth_chunk: List[str],
    retrieved_uris: List[str],
    ground_truth_docs: List[str],
    retrieved_corpus: str,
    ground_truth_corpus: str
) -> Dict[str, float]:
    """
    Calculates retrieval metrics based on cosine similarity for chunks and exact matches for docs and corpus.
    """
    # 1. Cosine similarity for chunks
    # Clean the retrieved text to remove noise
    
    retrieved_chunk_text = " ".join(retrieved_chunk)
    query_text = " ".join(query_list)
    ground_truth_chunk_text = " ".join(ground_truth_chunk)
    
    chunk_cosine_similarity = _calculate_cosine_similarity(query_text, retrieved_chunk_text)
    chunk_gt_cosine_similarity = _calculate_cosine_similarity(ground_truth_chunk_text, retrieved_chunk_text)

    # 2. Exact match for documents/URIs
    # Score is 1 if any retrieved URI is in the ground truth list, 0 otherwise.
    doc_match_score = 0
    # Normalize retrieved URIs and Ground Truth Docs
    retrieved_norms = set(_normalize_filename(u) for u in retrieved_uris if u)
    gt_norms = set(_normalize_filename(u) for u in ground_truth_docs if u)
    
    # Check for intersection
    if retrieved_norms & gt_norms:
        doc_match_score = 1

    # 3. Exact match for corpus (Normalized)
    retrieved_norm = retrieved_corpus.lower().strip() if retrieved_corpus else ""
    gt_norm = ground_truth_corpus.lower().strip() if ground_truth_corpus else ""
    
    # Simple containment check or exact match
    corpus_match_score = 1 if (retrieved_norm == gt_norm or gt_norm in retrieved_norm) else 0

    return {
        "chunk_cosine_similarity": chunk_cosine_similarity,
        "chunk_gt_cosine_similarity": chunk_gt_cosine_similarity,
        "doc_exact_match": doc_match_score,
        "corpus_exact_match": corpus_match_score,
    }

def test_vertex_experiment_connection(project_id: str, location: str, experiment_name: str) -> bool:
    """
    Tests the connection to a Vertex AI Experiment.

    Initializes the connection and attempts to get/create the specified experiment.
    Logs the outcome.

    Args:
        project_id: The Google Cloud project ID.
        location: The region for Vertex AI (e.g., "us-central1").
        experiment_name: The name of the experiment to connect to.

    Returns:
        True if the connection is successful, False otherwise.
    """
    try:
        aiplatform.init(project=project_id, location=location, experiment=experiment_name)
        experiment = aiplatform.Experiment(experiment_name=experiment_name)
        experiment_url = f"https://console.cloud.google.com/vertex-ai/locations/{location}/experiments/{experiment.name}?project={project_id}"
        logger.info(f"Successfully connected to Vertex AI Experiment '{experiment.name}'. View at: {experiment_url}")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize or connect to Vertex AI Experiment '{experiment_name}': {e}")
        return False


def _identify_context_from_instruction(query: str) -> tuple[Optional[dict], Optional[str]]:
    """
    Identifies Policy or VAS context by reading rules dynamically from rag_agent_instruction.md.
    This ensures evaluation logic aligns exactly with the agent's instructions.
    """
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Path to rag_agent_instruction.md relative to this file
        # tools/lifecycle/lifecycle_main.py -> ../../agents/rag_agent_instruction.md
        instruction_path = os.path.join(current_dir, "../../agents/rag_agent_instruction.md")
        
        if not os.path.exists(instruction_path):
            logger.warning(f"Instruction file not found at {instruction_path}")
            return None, None
            
        with open(instruction_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Split into Policy and VAS sections using a unique text marker from the file
        # Policy is before "go to vas_rag retrieval", VAS is after.
        split_marker = "go to vas_rag retrieval"
        parts = content.split(split_marker)
        if len(parts) < 2:
            logger.warning("Could not split instruction file into Policy and VAS sections using marker 'go to vas_rag retrieval'.")
            return None, None
            
        policy_section = parts[0]
        vas_section = parts[1]
        
        def extract_and_parse_json(text):
            # Find the first '[' and last ']'
            start = text.find('[')
            end = text.rfind(']')
            if start != -1 and end != -1 and end > start:
                json_str = text[start:end+1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    return None
            return None

        policy_list = extract_and_parse_json(policy_section)
        vas_list = extract_and_parse_json(vas_section)
        
        if not policy_list or not vas_list:
             logger.warning("Failed to parse Policy or VAS JSON lists from instructions.")
             return None, None

        # 1. Check Policy
        for item in policy_list:
            product = item.get("Product", "")
            # Simple substring match (Case-insensitive)
            if product and product.lower() in query.lower():
                return item, "policy"
                
        # 2. Check VAS
        for item in vas_list:
            print(item)
            vas_service = item.get("VAS", "")
            if vas_service and vas_service.lower() in query.lower():
                return item, "vas"
                
        return None, None
    except Exception as e:
        logger.error(f"Error identifying context from instruction: {e}")
        return None, None


# =================MAIN PROCESS =====================
# =================MAIN PROCESS =====================
def automated_evaluation_testcase(
) -> Dict[str,Any]:

    """
    Executes an automated evaluation of a RAG corpus using a test case Excel file.
    
    
    Plan:

    1. Read the Excel file using pandas .
    2. Iterate through the rows.
    3. For each row, execute a RAG query using query_corpus .
    4. Compare the result with the ground truth using an LLM as a judge (). # Change this adding quantitative scoring recall, precision & NDCG 
    5. Update the pandas DataFrame with the results (RAG response, Score, Pass/Fail status).
    6. Return the final DataFrame (as a dict/list of records) and summary statistics.
    7. 

    """

    # Read Excel 
    testset_path = "./evaluation_files/rag_test_set_generated_v2.csv"
    df = pd.read_csv(testset_path)
    
    # Identify columns (flexible) by checking lowercase stripped versions but keeping original headers
    # Create a mapping for easy lookup
    col_map = {str(c).lower().strip(): c for c in df.columns}
    
    # Find actual column names in the dataframe
    query_col_name = next((c for c in col_map.keys() if c in ['query', 'question', 'input', 'user query']), list(col_map.keys())[0])
    truth_col_name = next((c for c in col_map.keys() if c in ['ground_truth', 'ground truth', 'groundtruth', 'expected', 'truth', 'answer', 'correct answer']), None)
    doc_truth_col_name = next((c for c in col_map.keys() if c in ['ground truth documents uri', 'document uri', 'source documents', 'ground truth documents']), None)
    chunk_truth_col_name = next((c for c in col_map.keys() if c in ['ground truth chunk', 'chunk match']), None)
    corpus_truth_col_name = next((c for c in col_map.keys() if c in ['ground truth corpus', 'corpus match', 'corpus name', 'corpus uri', 'corpura']), None)

    query_col = col_map[query_col_name]
    truth_col = col_map[truth_col_name] if truth_col_name else None
    doc_truth_col = col_map[doc_truth_col_name] if doc_truth_col_name else None
    chunk_truth_col = col_map[chunk_truth_col_name] if chunk_truth_col_name else None
    corpus_truth_col = col_map[corpus_truth_col_name] if corpus_truth_col_name else None


    # Loop and Validate
    total_chunk_question_cosine_similarity = 0.0
    total_chunk_gt_cosine_similarity = 0.0
    #qa_pass_count = 0
    chunk_pass_count = 0
    total_doc_exact_match = 0
    total_corpus_exact_match = 0

    total_cosine_score = 0
    pass_count = 0
    evaluated_rows = []

    # Setup for continuous save. Use hyphens in timestamp for Vertex AI compatibility.
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    date_folder = datetime.datetime.now().strftime("%Y-%m-%d")
    base_name = os.path.splitext(os.path.basename(testset_path))[0]
    
    # Define temporary and final paths
    temp_blob_path = f"temp_processing/{base_name}_{timestamp}_working.xlsx"
    final_blob_path = f"eval_results/{date_folder}/{base_name}_results_{timestamp}.xlsx"

    # # Helper to save current progress to GCS
    # def save_progress_to_gcs(current_rows, blob_path, is_temp=True):
    #     if not storage_client: return
    #     try:
    #         temp_df = pd.DataFrame(current_rows)
    #         output = io.BytesIO()
    #         with pd.ExcelWriter(output, engine='openpyxl') as writer:
    #             temp_df.to_excel(writer, index=False)
    #         output_bytes = output.getvalue()
            
    #         bucket = storage_client.bucket(EVAL_BUCKET_NAME)
    #         blob = bucket.blob(blob_path)
    #         blob.upload_from_string(
    #             data=output_bytes,
    #             content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    #         )
    #         if not is_temp:
    #             logger.info(f"Saved results to gs://{EVAL_BUCKET_NAME}/{blob_path}")
    #     except Exception as e:
    #         logger.warning(f"Failed to save progress to {blob_path}: {e}")

    # 1. Initialize Vertex AI Experiment
    experiment_name = os.getenv("VERTEX_EXPERIMENT_NAME", "guidedcareeval")
    if not test_vertex_experiment_connection(
        project_id=PROJECT_ID, location=LOCATION, experiment_name=experiment_name
    ):
        return {"status": "error", "message": f"Failed to initialize Vertex AI connection for experiment '{experiment_name}'."}


    # # Upload initial file to temp location
    # try:
    #     if storage_client:
    #         bucket = storage_client.bucket(EVAL_BUCKET_NAME)
    #         if not bucket.exists():
    #             create_gcs_bucket(tool_context=tool_context, bucket_name=EVAL_BUCKET_NAME, location=LOCATION)
            
    #         # Read bytes from local file
    #         with open(testset_path, "rb") as f:
    #             bucket.blob(temp_blob_path).upload_from_file(f)
    #         logger.info(f"Uploaded working copy to gs://{EVAL_BUCKET_NAME}/{temp_blob_path}")
    # except Exception as e:
    #     logger.warning(f"Failed to upload initial working copy: {e}")
    
    try:
        # Start a summary run for this evaluation
        run_name = f"eval-run-{timestamp}"
        aiplatform.start_run(run=run_name)
        aiplatform.log_params({"evaluation_file": testset_path, "model": os.getenv("LLM_MODEL", "gemini-2.5-flash")})
        logger.info(f"Started Vertex AI Experiment run: {run_name}")

        df_eval = pd.DataFrame()
        for index, row in df.iterrows():
            # Add delay to avoid hitting rate limits (LLM/Vertex AI quotas)
            time.sleep(2)
            
            query_text = str(row[query_col])
            print(f"query:{query_text}")
            
            # # Identify Policy/VAS Context from Instruction
            # matched_metadata, context = _identify_context_from_instruction(query_text)
            #if context == "vas":
            #    target_corpus_display_name = 'gc-phkl-vas'
            #else:
                # Default to policy if context is 'policy' or None
            #    target_corpus_display_name = 'gc-phkl-policy'
            
            # Use the identified truth column, but keep strict N/A handling for evaluation
            ground_truth = str(row[truth_col]) if truth_col and truth_col in df.columns else "N/A"
            if ground_truth.lower() == 'nan': ground_truth = "N/A"
            
            # --- Start of New Agent-like Logic ---
            # Query Corpus and Generate Initial Answer
            response_text = "No response"
            citations, chunks, document_names, retrieved_uris = [], [], [], []

            rag_result = query_corpus(query=query_text)
            print(f"rag_result: {rag_result}")
            if rag_result.get("status") == "success" and "results" in rag_result and rag_result["results"]:
                 # Re-rank by query–chunk cosine and take top 1
                 candidates = rag_result["results"][:RAG_DEFAULT_TOP_K]
                 if candidates:
                     scored = []
                     for r in candidates:
                         t = r.get("text", "") or ""
                         sim = _calculate_cosine_similarity(query_text, t) if t else 0.0
                         r2 = dict(r)
                         r2["_query_chunk_cosine"] = sim
                         scored.append(r2)
                     scored.sort(key=lambda x: x.get("_query_chunk_cosine", 0.0), reverse=True)
                     top_results = [scored[0]]
                 else:
                     top_results = []
                
                 # Prepare context from chunks
                 context_text = "\n\n".join([r.get("text", "") for r in top_results])

                 # Generate Initial Answer using LLM
                 initial_answer = _generate_answer(query_text, context_text)

            # Collect URIs for retrieval evaluation (Use ALL retrieved results, not just top 5)
            retrieved_uris = [r.get("source_uri", "") for r in rag_result["results"]]

            response_text = initial_answer
            
            # Extract chunk details and citations
            chunks = [r.get("text", "") for r in top_results]
            document_names = [os.path.basename(r.get("source_uri", "Unknown")) for r in top_results]
            citations = list(set([r.get("source_uri", "Unknown") for r in top_results if r.get("source_uri")]))
            
            #else:
            #    response_text = "Could not retrieve any information from the corpus to answer the query."
                

            # --- Retrieval Evaluation (New) ---
            retrieval_metrics = {
                                "chunk_cosine_similarity": 0.0,
                                "chunk_gt_cosine_similarity": 0.0,
                                "corpus_exact_match": 0,
                                "doc_exact_match":0,
                                }

            if doc_truth_col and doc_truth_col in df.columns and chunk_truth_col and chunk_truth_col in df.columns and corpus_truth_col and corpus_truth_col in df.columns:
                raw_gt_docs = str(row[doc_truth_col])
                raw_gt_chunks = str(row[chunk_truth_col])
                raw_gt_corpus = str(row[corpus_truth_col])
                if raw_gt_docs.lower() != 'nan' and raw_gt_chunks.lower() != 'nan' and raw_gt_corpus.lower() != 'nan':
                    # Split by comma if multiple docs
                    gt_docs_list = [d.strip() for d in raw_gt_docs.split(',')]
                    #print(f"gt_doc: {gt_docs_list}")
                    query_list = [str(row['Question'])]
                    gt_chunks_list = [d.strip() for d in raw_gt_chunks.split(',')]
                    #print(f"gt_chunk: {gt_chunks_list}")
                    gt_corpus_list = [raw_gt_corpus]
                    #print(f"gt_corpus: {gt_corpus_list}")
                    retrieval_metrics = _calculate_simple_retrieval_metrics(chunks, query_list, gt_chunks_list, retrieved_uris, gt_docs_list, target_corpus_display_name, raw_gt_corpus)
                    
            # --- End of New Agent-like Logic ---
            
            # Evaluate
            # eval_result = _evaluate_with_llm(query_text, response_text, ground_truth)
            cosine_score = _calculate_cosine_similarity(ground_truth, response_text)
            print(f"Ground_truth: {ground_truth}")
            print(f"response_text: {response_text}")
            print(f"cosine_score: {cosine_score}")
            print(f"retrieval_metrics: {retrieval_metrics}")

            # Log metrics to the current row's run
            aiplatform.log_time_series_metrics({
                "cosine_score": cosine_score,
                "retrieval_chunk_question_cosine_similarity": retrieval_metrics.get("chunk_cosine_similarity", 0.0),
                "retrieval_chunk_gt_cosine_similarity": retrieval_metrics.get("chunk_gt_cosine_similarity", 0.0),
                "retrieval_doc_exact_match": float(retrieval_metrics.get("doc_exact_match", 0)),
                "retrieval_corpus_exact_match": float(retrieval_metrics.get("corpus_exact_match", 0)),
            }, step=index + 1)
            
            total_cosine_scores += cosine_score
            total_chunk_question_cosine_similarity += retrieval_metrics.get("chunk_cosine_similarity", 0.0)
            total_chunk_gt_cosine_similarity += retrieval_metrics.get("chunk_gt_cosine_similarity", 0.0)
            total_doc_exact_match += retrieval_metrics.get("doc_exact_match", 0)
            total_corpus_exact_match += retrieval_metrics.get("corpus_exact_match", 0)
            
            # Construct Output Row:
            # 1. Start with original row data to preserve structure and values
            out_row = row.to_dict()
            
            # 2. Append new results columns
            out_row['rag_response'] = response_text[:1000] + "..." if len(response_text) > 1000 else response_text
            
            # Add Retrieval Metrics
            out_row['retrieval_cosine_similarity'] = cosine_score
            out_row['retrieval_chunk_question_cosine_similarity'] = retrieval_metrics['chunk_cosine_similarity']
            out_row['retrieval_chunk_gt_cosine_similarity'] = retrieval_metrics['chunk_gt_cosine_similarity']
            out_row['retrieval_doc_exact_match'] = retrieval_metrics['doc_exact_match']
            out_row['retrieval_corpus_exact_match'] = retrieval_metrics['corpus_exact_match']
            
            retrieve_k_chunk = 1

            # Add top 1 chunks and their details
            for i in range(retrieve_k_chunk):
                out_row[f'retrieved_chunk_{i+1}'] = chunks[i] if i < len(chunks) else ""
                out_row[f'retrieved_document_name_{i+1}'] = document_names[i] if i < len(document_names) else ""

            out_row['retrieved_citations'] = ", ".join(citations)
            out_row['row_id'] = index + 1
            out_row['retrieved_corpus'] = target_corpus_display_name
            
            # Sanitize for JSON/LiteLLM compatibility (handle NaN, Timestamp, etc.)
            for k, v in out_row.items():
                if pd.isna(v):  # Handles NaN, None, NaT
                    out_row[k] = None
                elif isinstance(v, (pd.Timestamp, datetime.datetime, datetime.date)):
                    out_row[k] = str(v)
            
            evaluated_rows.append(out_row)
            df_eval = pd.DataFrame(evaluated_rows)
            df_eval = df_eval[['Question', 'Ground Truth', 'rag_reponse', 'corpus match', 'retrieved_corpus',
                                'document uri', 'retrieved_citations', 'chunk match'] + [f'retrieved_chunk_{i+1}' for i in range(0, retrieve_k_chunk)] 
                                + ['retrieval_cosine_similarity', 'retrieval_chunk_question_cosine_similarity', 'retrieval_chunk_gt_cosine_similarity', 'retrieval_doc_exact_match', 'retrieval_corpus_exact_match']]
            print(df_eval[['retrieval_cosine_similarity', 'retrieval_chunk_question_cosine_similarity', 'retrieval_chunk_gt_cosine_similarity', 'retrieval_doc_exact_match', 'retrieval_corpus_exact_match']].tail())
        
            

    except Exception as e:
        logger.error(f"Regression test interrupted: {e}")
    
    total_rows = len(df) if len(df) > 0 else 1

    # Calculate Averages
    
    avg_cosine_score = total_cosine_score / total_rows
    avg_chunk_question_cosine_similarity = total_chunk_question_cosine_similarity / total_rows
    avg_chunk_gt_cosine_similarity = total_chunk_gt_cosine_similarity / total_rows

    # Calculate Precision/Pass Rate for different metrics
    # In this context, precision is the same as the pass rate (number of passes / total items)
    # because we assume all items in the test set are "positive" candidates.
    doc_match = total_doc_exact_match / total_rows
    corpus_match = total_corpus_exact_match / total_rows
    
    # Log summary metrics to Vertex AI
    try:
        aiplatform.log_metrics({
            "average_cosine_similarity": round(avg_cosine_score, 4),
           "average_chunk_question_cosine_similarity": round(avg_chunk_question_cosine_similarity, 4),
           "average_chunk_gt_cosine_similarity": round(avg_chunk_gt_cosine_similarity, 4),
            "doc_match_rate": round(doc_match, 4),
            "corpus_match_rate": round(corpus_match, 4),
        })
        logger.info("Logged summary metrics to Vertex AI Experiment.")
        aiplatform.end_run()
    except Exception as e:
        logger.warning(f"Failed to log summary metrics or end run: {e}")

    doc_failures = [r["row_id"] for r in evaluated_rows if r["retrieval_doc_exact_match"] == 0]
    corpus_failures = [r["row_id"] for r in evaluated_rows if r["retrieval_corpus_exact_match"] == 0]
    

    # Save to local file (timestamped)
    try:
        results_filename = f"{base_name}_results_{timestamp}.xlsx"
        results_path = os.path.join("./evaluation_files", results_filename)
        df_eval.to_excel(results_path, index=False)
        logger.info(f"Saved evaluation results to {results_path}")
    except Exception as e:
        logger.warning(f"Failed to save local Excel file: {e}")

    return {
        "status": "success",
        "project_id": PROJECT_ID,
        "summary": {
            "total_queries": len(df),
            "cosine_score" : round(avg_cosine_score, 4),
            "corpus_failed": len(corpus_failures),
            "average_chunk_question_cosine_score": round(avg_chunk_question_cosine_similarity, 4), 
            "average_chunk_gt_cosine_score": round(avg_chunk_gt_cosine_similarity, 4), 
            "doc_match_rate": round(doc_match, 4),
            "corpus_match_rate": round(corpus_match, 4)
        },
    }

    
