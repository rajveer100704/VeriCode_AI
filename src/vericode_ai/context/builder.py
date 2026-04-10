from typing import List
from vericode_ai.schema.doc_chunk import DocChunk

class ContextBuilder:
    """
    Builds hallucination-proof context prompts for the LLM.
    """
    
    @staticmethod
    def build_context(chunks: List[DocChunk]) -> str:
        """
        Takes a list of DocChunks and formats them into a tight, focused text
        block to act as the grounded knowledge base for the LLM.
        """
        if not chunks:
            return "No documentation context available."
            
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            chunk_text = f"--- Document {i} ---\n{chunk.to_context_string()}"
            context_parts.append(chunk_text)
            
        return "\n\n".join(context_parts)

    @staticmethod
    def construct_prompt(query: str, chunks: List[DocChunk]) -> str:
        """
        Wraps the user query and the retrieved context into a strict zero-hallucination prompt.
        """
        context_str = ContextBuilder.build_context(chunks)
        
        prompt = f"""You are a precise, senior software engineer. 
Answer the user's question using ONLY the provided documentation context. 
If the answer is not contained in the context, explicitly state "I cannot answer this based on the provided documentation" and do not guess.

<documentation_context>
{context_str}
</documentation_context>

User Question: {query}

Answer:"""
        
        return prompt
