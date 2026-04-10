from typing import List
from sentence_transformers import SentenceTransformer
import numpy as np

class Embedder:
    """
    Handles converting text into dense vector embeddings using SentenceTransformers.
    """
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initializes the embedding model. MiniLM is chosen as the default for its 
        excellent balance of local inference speed and text representation quality.
        """
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        
    def embed_text(self, text: str) -> np.ndarray:
        """
        Embeds a single string into a normalized numpy array.
        """
        embedding = self.model.encode(text, normalize_embeddings=True)
        return np.array(embedding, dtype=np.float32)

    def embed_batch(self, texts: List[str]) -> np.ndarray:
        """
        Embeds a batch of strings into a normalized numpy array matrix.
        Optimized for processing large lists of chunks during ingestion.
        """
        embeddings = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
        return np.array(embeddings, dtype=np.float32)
