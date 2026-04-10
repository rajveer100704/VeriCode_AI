from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class DocChunk(BaseModel):
    id: str = Field(..., description="Unique identifier for the chunk, usually an arbitrary hash or semantically constructed string")
    content: str = Field(..., description="The raw Markdown content of this documentation chunk")
    source: str = Field(..., description="The source file, url, or origin of this documentation")
    symbol: str = Field(..., description="The full symbol name (e.g., 'foo.bar.Baz')")
    symbol_type: str = Field(..., description="The type of symbol (e.g., 'class', 'function', 'module', 'method', 'constant')")
    signature: Optional[str] = Field(None, description="The code signature (e.g., 'def my_func(a: int) -> str')")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Any additional metadata (version, line numbers, etc.)")

    def to_context_string(self) -> str:
        """
        Formats the chunk for injection into an LLM context window.
        """
        header = f"[{self.symbol_type.upper()}] {self.symbol}"
        if self.signature:
            header += f"\nSignature: {self.signature}"
        
        return f"{header}\nSource: {self.source}\nDocs:\n{self.content}"
