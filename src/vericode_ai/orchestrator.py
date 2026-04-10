from typing import List, Optional
import structlog

from vericode_ai.schema.doc_chunk import DocChunk
from vericode_ai.retrieval.embedder import Embedder
from vericode_ai.retrieval.vector_db import FAISSDatabase
from vericode_ai.retrieval.ranker import Ranker
from vericode_ai.context.builder import ContextBuilder
from vericode_ai.router.llm_router import LLMRouter
from vericode_ai.validator.ast_validator import ASTValidator
from vericode_ai.analyzer.diff_engine import DiffEngine

logger = structlog.get_logger(__name__)

class QueryOrchestrator:
    """
    Central control plane for VeriCode AI.
    Handles retrieving ground-truth documentation, ranking, building context, and
    routing to the appropriate LLM exactly as dictated by the system design.
    """
    
    def __init__(
        self, 
        vector_db: FAISSDatabase, 
        ranker: Ranker, 
        router: LLMRouter
    ):
        self.vector_db = vector_db
        self.ranker = ranker
        self.router = router
        self.diff_engine = DiffEngine()
        
    def add_knowledge(self, chunks: List[DocChunk]):
        """Injects new documentation chunks into the verifiable datastore."""
        logger.info(f"Indexing {len(chunks)} chunks into vector DB...")
        self.vector_db.add_chunks(chunks)
        logger.info("Indexing complete.")

    def query(
        self, 
        user_query: str, 
        task_type: str = "code_generation",
        top_k_retrieve: int = 5,
        top_k_rank: int = 2,
        **llm_kwargs
    ) -> dict:
        """
        Executes the full Retrieval-Augmented Generation pipeline.
        Returns a dictionary containing the answer, a confidence score, and sources.
        """
        logger.info(f"Received query: {user_query}")
        
        # 1. Retrieval Layer (FAISS + SentenceTransformers)
        # returns [(chunk, distance), ...]
        retrieved_results = self.vector_db.search(user_query, top_k=top_k_retrieve)
        logger.info(f"Retrieved {len(retrieved_results)} chunks from local FAISS index.")
        
        # 2. Ranking Layer
        ranked_results = self.ranker.rank(user_query, retrieved_results, top_k=top_k_rank)
        logger.info(f"Ranked and selected top {top_k_rank} chunks.")
        
        # Extract just chunks for context building
        ranked_chunks = [res[0] for res in ranked_results]
        
        # 3. Context Construction
        prompt = ContextBuilder.construct_prompt(user_query, ranked_chunks)
        
        # 4. LLM Routing & Generation
        logger.info("Executing zero-hallucination prompt generation...")
        response = self.router.generate(prompt, task_type=task_type, **llm_kwargs)
        
        # 5. Extract Confidence and Sources
        confidence = 0.0
        if ranked_results:
            top_distance = ranked_results[0][1]
            confidence = max(0.0, 1.0 - float(top_distance) / 10.0)
            
        confidence_score = round(confidence * 100, 2)
        if confidence_score > 80:
            label = "HIGH"
        elif confidence_score > 50:
            label = "MEDIUM"
        else:
            label = "LOW"
            
        sources = [chunk.symbol for chunk in ranked_chunks if chunk.symbol]
        
        return {
            "answer": response,
            "confidence": confidence_score,
            "confidence_label": label,
            "sources": sources
        }

    def validate_code(self, user_code: str) -> dict:
        """
        Runs static AST validation against the entire known ground-truth dataset in the Vector DB.
        This provides IDE-like intellisense and error catching against hallucinated calls.
        """
        # Load all available constraints from Vector DB (Naive for phase 1: get everything)
        # Assuming `chunk_store` holds all ingested docs:
        validator = ASTValidator(self.vector_db.chunk_store)
        errors = validator.validate(user_code)
        
        if errors:
            return {
                "status": "error",
                "errors": [e.to_dict() for e in errors]
            }
            
        return {
            "status": "success",
            "message": "All API calls map correctly to ground-truth documentation."
        }

    def generate_migration(self, old_chunks: List[DocChunk], new_chunks: List[DocChunk]) -> dict:
        """
        Runs the diff engine and asks the LLM to generate a migration guide.
        """
        diff = self.diff_engine.compare(old_chunks, new_chunks)
        prompt = diff.generate_migration_prompt()

        logger.info("Generating migration guide via LLM...")
        response = self.router.generate(
            prompt=prompt,
            task_type="code_generation"
        )

        return {
            "diff": diff.to_dict(),
            "migration_guide": response
        }
