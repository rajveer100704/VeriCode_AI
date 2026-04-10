import re
from typing import List
from vericode_ai.schema.doc_chunk import DocChunk

class MarkdownChunker:
    """
    Parses flat Markdown files (like curated guides or READMEs) into semantic `DocChunk`s.
    Splits content by headers, preserving the hierarchy as context.
    """
    
    def __init__(self, source_name: str):
        self.source_name = source_name

    def chunk(self, markdown_text: str) -> List[DocChunk]:
        """
        Splits Markdown text into chunks based on headers.
        """
        chunks = []
        
        # Regex to match headers like "# Heading" or "## Subheading"
        header_pattern = re.compile(r'^(#{1,6})\s+(.*)$', re.MULTILINE)
        
        matches = list(header_pattern.finditer(markdown_text))
        
        if not matches:
            # No headers, entire text is one chunk
            return [DocChunk(
                id=f"{self.source_name}_full",
                content=markdown_text.strip(),
                source=self.source_name,
                symbol="root",
                symbol_type="document",
                signature=None
            )]
            
        # Parse based on headers
        for i, match in enumerate(matches):
            level = len(match.group(1))
            title = match.group(2).strip()
            
            start_idx = match.end()
            end_idx = matches[i+1].start() if i + 1 < len(matches) else len(markdown_text)
            
            content = markdown_text[start_idx:end_idx].strip()
            
            if content:
                chunks.append(DocChunk(
                    id=f"{self.source_name}_{title.replace(' ', '_').lower()}",
                    content=content,
                    source=self.source_name,
                    symbol=title,
                    symbol_type="markdown_section",
                    signature=f"H{level}",
                    metadata={"level": level}
                ))
                
        return chunks
