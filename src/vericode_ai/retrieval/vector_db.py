from typing import List, Tuple, Dict
import faiss
import numpy as np

from vericode_ai.schema.doc_chunk import DocChunk
from vericode_ai.retrieval.embedder import Embedder

class FAISSDatabase:
    """
    Local, fast, in-memory vector database using FAISS for storing and retrieving 
    DocChunks. Phase 3 scale-out can substitute this for Qdrant.
    """
    
    def __init__(self, embedder: Embedder, dimension: int = 384):
        """
        Initializes an empty FAISS index (L2 distance by default).
        dimension must match the embedder's output (384 for MiniLM).
        """
        self.embedder = embedder
        # IndexFlatL2 provides exact search (L2 distance on normalized vectors is monotonic with cosine similarity)
        self.index = faiss.IndexFlatL2(dimension)
        # Store the actual DocChunks so we can retrieve exactly what matched
        self.chunk_store: List[DocChunk] = []

    def add_chunks(self, chunks: List[DocChunk]):
        """
        Embeds and indexes a list of DocChunks.
        """
        if not chunks:
            return
            
        # Extract text to embed. We embed the symbol + content for dense retrieval.
        texts_to_embed = [
            f"[{c.symbol_type}] {c.symbol}\n{c.content}" 
            for c in chunks
        ]
        
        embeddings = self.embedder.embed_batch(texts_to_embed)
        
        self.index.add(embeddings)
        self.chunk_store.extend(chunks)

    def search(self, query: str, top_k: int = 5) -> List[Tuple[DocChunk, float]]:
        """
        Searches the DB for the most relevant chunks.
        Returns a list of tuples containing (DocChunk, distance_score).
        """
        if self.index.ntotal == 0:
            return []
            
        # Ensure we don't ask for more than we have
        k = min(top_k, self.index.ntotal)
        
        query_vector = self.embedder.embed_text(query)
        # Reshape to match FAISS explicitly
        query_vector = np.expand_dims(query_vector, axis=0)
        
        distances, indices = self.index.search(query_vector, k)
        
        # indices and distances are 2D arrays
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx != -1:
                results.append((self.chunk_store[idx], float(dist)))
                
        return results
