import json
from typing import List, Dict, Any, Optional
from pathlib import Path

from vericode_ai.schema.doc_chunk import DocChunk


class RustIngestor:
    """
    Ingests Rust documentation from rustdoc JSON output and converts it
    into structured DocChunk objects.
    """
    
    def __init__(self, json_path: str):
        self.json_path = Path(json_path)

    def ingest(self) -> List[DocChunk]:
        """Loads rustdoc JSON and returns parsed DocChunks."""
        if not self.json_path.exists():
            print(f"Error: JSON file not found at {self.json_path}")
            return []
            
        with open(self.json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        chunks = []
        index = data.get("index", {})
        paths = data.get("paths", {})
        
        root_id = str(data.get("root", ""))
        root_item = index.get(root_id, {})
        crate_name = root_item.get("name", "unknown")
        
        # Build path lookup
        path_lookup = {}
        for pid, pinfo in paths.items():
            if isinstance(pinfo, dict):
                path_lookup[pid] = "::".join(pinfo.get("path", []))

        for item_id, item in index.items():
            inner = item.get("inner", {})
            name = item.get("name")
            if not name:
                continue
                
            docs = item.get("docs", "")
            if not docs:
                continue

            symbol_path = path_lookup.get(item_id, name)
            
            # Simple heuristic classification
            symbol_type = "unknown"
            if "struct" in inner: symbol_type = "struct"
            elif "enum" in inner: symbol_type = "enum"
            elif "trait" in inner: symbol_type = "trait"
            elif "function" in inner: symbol_type = "function"
            elif "module" in inner: symbol_type = "module"
            
            if symbol_type != "unknown":
                chunks.append(DocChunk(
                    id=f"{crate_name}_{item_id}",
                    content=docs,
                    source=crate_name,
                    symbol=symbol_path,
                    symbol_type=symbol_type,
                    # Fallback signature logic since full Rust signature parsing is complex
                    signature=name 
                ))
                
        return chunks
