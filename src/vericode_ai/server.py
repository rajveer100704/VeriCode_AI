import sys
import json
import logging
from typing import Dict, Any

from vericode_ai.retrieval.embedder import Embedder
from vericode_ai.retrieval.vector_db import FAISSDatabase
from vericode_ai.retrieval.ranker import Ranker
from vericode_ai.router.llm_router import LLMRouter
from vericode_ai.orchestrator import QueryOrchestrator

# Standard logging (outputting to stderr so it doesn't corrupt stdout JSONRPC)
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("vericode_ai.server")


class StdioServer:
    """
    Minimal LSP-style JSON-RPC STDIO server for VeriCode AI.
    Reads requests on stdin, outputs responses on stdout.
    """
    def __init__(self, orchestrator: QueryOrchestrator):
        self.orchestrator = orchestrator

    def run(self):
        logger.info("VeriCode AI STDIO Server starting...")
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break  # EOF reached
                    
                line = line.strip()
                if not line:
                    continue
                    
                request = json.loads(line)
                response = self.handle_request(request)
                
                # Write back to stdout
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
                
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON request: {line}")
                self._send_error("Invalid JSON format")
            except Exception as e:
                logger.exception("Server error")
                self._send_error(str(e))

    def handle_request(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Routes the parsed RPC request."""
        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        logger.info(f"Received method: {method}")

        if method == "query":
            query = params.get("query", "")
            code_context = params.get("code", "")
            
            # Formulate robust query based on existing code context
            full_query = query
            if code_context:
                full_query += f"\n\nContext code:\n```python\n{code_context}\n```"
                
            result = self.orchestrator.query(full_query)
            return self._build_response(req_id, result)
            
        elif method == "validate":
            code = params.get("code", "")
            result = self.orchestrator.validate_code(code)
            return self._build_response(req_id, result)
            
        elif method == "ping":
            return self._build_response(req_id, {"status": "ok"})
            
        else:
            return self._build_error(req_id, -32601, f"Method not found: {method}")

    def _build_response(self, req_id, result) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def _build_error(self, req_id, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    def _send_error(self, message: str):
        # Fire off generic JSON-RPC error
        err = self._build_error(None, -32000, message)
        sys.stdout.write(json.dumps(err) + "\n")
        sys.stdout.flush()

if __name__ == "__main__":
    # Boot infrastructure quickly
    embedder = Embedder()
    vector_db = FAISSDatabase(embedder=embedder)
    ranker = Ranker()
    router = LLMRouter()
    
    import os
    if os.environ.get("OPENAI_API_KEY"):
        from vericode_ai.router.providers.openai_client import OpenAIProvider
        router.register_provider("openai", OpenAIProvider())
        
    orchestrator = QueryOrchestrator(vector_db, ranker, router)
    
    server = StdioServer(orchestrator)
    server.run()
