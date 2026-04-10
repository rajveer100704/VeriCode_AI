from typing import List, Dict
from vericode_ai.schema.doc_chunk import DocChunk


class DiffResult:
    def __init__(self):
        self.added = []
        self.removed = []
        self.modified = []

    def to_dict(self):
        return {
            "added": self.added,
            "removed": self.removed,
            "modified": self.modified,
        }

    def generate_migration_prompt(self) -> str:
        """
        Generates an LLM prompt to construct a migration guide based on the diff.
        """
        return f"""
        You are an expert Python migration assistant.

        Here are the API changes between the two documentation versions:

        Added:
        {self.added}

        Removed:
        {self.removed}

        Modified:
        {self.modified}

        Generate a concise migration guide with code fixes. Explain what broke,
        and show before/after code snippets to resolve it based on the Added/Modified signatures.
        """


class DiffEngine:
    """
    Compares two versions of DocChunks and detects:
    - Added APIs
    - Removed APIs
    - Modified APIs (signature change)
    """

    def _index_chunks(self, chunks: List[DocChunk]) -> Dict[str, DocChunk]:
        """
        Create a lookup map:
        key = symbol (unique identifier)
        """
        index = {}
        for chunk in chunks:
            if chunk.symbol:
                index[chunk.symbol] = chunk
        return index

    def compare(self, old_chunks: List[DocChunk], new_chunks: List[DocChunk]) -> DiffResult:
        old_index = self._index_chunks(old_chunks)
        new_index = self._index_chunks(new_chunks)

        result = DiffResult()

        old_symbols = set(old_index.keys())
        new_symbols = set(new_index.keys())

        # Detect added
        for symbol in new_symbols - old_symbols:
            result.added.append({
                "symbol": symbol,
                "signature": new_index[symbol].signature,
                "source": new_index[symbol].source,
            })

        # Detect removed
        for symbol in old_symbols - new_symbols:
            result.removed.append({
                "symbol": symbol,
                "signature": old_index[symbol].signature,
                "source": old_index[symbol].source,
            })

        # Detect modified (same symbol, different signature)
        for symbol in old_symbols & new_symbols:
            old_sig = old_index[symbol].signature
            new_sig = new_index[symbol].signature

            if old_sig != new_sig:
                result.modified.append({
                    "symbol": symbol,
                    "old_signature": old_sig,
                    "new_signature": new_sig,
                    "source": new_index[symbol].source,
                })

        return result
