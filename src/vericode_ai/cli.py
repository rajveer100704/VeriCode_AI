import sys
import argparse
import structlog

from vericode_ai.retrieval.embedder import Embedder
from vericode_ai.retrieval.vector_db import FAISSDatabase
from vericode_ai.retrieval.ranker import Ranker
from vericode_ai.router.llm_router import LLMRouter
from vericode_ai.orchestrator import QueryOrchestrator
from vericode_ai.ingestion.python_parser import PythonIngestor

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(colors=True)
    ]
)

logger = structlog.get_logger(__name__)

def main():
    parser = argparse.ArgumentParser(description="VeriCode AI: Ground-Truth Coding Engine CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    query_parser = subparsers.add_parser("query", help="Query with validation")
    query_parser.add_argument("text", type=str, help="Your code query")
    query_parser.add_argument("--ingest-py", "-p", type=str, help="Python package to ingest before querying (e.g. 'os')")
    
    validate_parser = subparsers.add_parser("validate", help="Validate a python file")
    validate_parser.add_argument("file", type=str, help="Python file to validate")
    validate_parser.add_argument("--ingest-py", "-p", type=str, help="Python package context")

    migrate_parser = subparsers.add_parser("migrate", help="Generate migration guide")
    migrate_parser.add_argument("v1", type=str, help="Old python package name")
    migrate_parser.add_argument("v2", type=str, help="New python package name")
    
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # 1. Setup Infrastructure
    logger.info("Initializing VeriCode AI Infrastructure...", extra={"action": "BOOT"})
    embedder = Embedder()
    vector_db = FAISSDatabase(embedder=embedder)
    ranker = Ranker()
    router = LLMRouter()

    # Conditionally register models if keys exist
    import os
    if os.environ.get("OPENAI_API_KEY"):
        from vericode_ai.router.providers.openai_client import OpenAIProvider
        router.register_provider("openai", OpenAIProvider())
        logger.info("Registered OpenAI Provider (Primary).")
        
    if os.environ.get("GEMINI_API_KEY"):
        from vericode_ai.router.providers.gemini_client import GeminiProvider
        router.register_provider("gemini", GeminiProvider())
        logger.info("Registered Gemini Provider.")

    orchestrator = QueryOrchestrator(vector_db, ranker, router)

    # Context injection for query/validate
    if getattr(args, "ingest_py", None):
        logger.info(f"Ingesting module: {args.ingest_py}")
        ingestor = PythonIngestor(args.ingest_py)
        chunks = ingestor.ingest()
        orchestrator.add_knowledge(chunks)

    if args.command == "query":
        if len(vector_db.chunk_store) == 0:
            logger.warning("No knowledge ingested. Generating without verifiable context.")
            
        logger.info(f"Solving Query: {args.text}")
        answer_data = orchestrator.query(args.text, task_type="code_generation")
        
        print("\n" + "="*60)
        print("🔥 VERICODE AI RESPONSE 🔥")
        print("="*60)
        print(answer_data["answer"])
        print("\n" + "-"*60)
        
        # Color specific output based on confidence
        conf_str = f"{answer_data['confidence']}% [{answer_data['confidence_label']}]"
        print(f"Confidence: {conf_str}")
        print(f"Sources: {', '.join(answer_data['sources']) if answer_data['sources'] else 'None'}")
        print("="*60 + "\n")

    elif args.command == "validate":
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                code_text = f.read()
            logger.info(f"Validating {args.file}...")
            result = orchestrator.validate_code(code_text)
            
            print("\n" + "="*60)
            if result["status"] == "success":
                print("[PASS] VALIDATION SUCCESS: All API calls map to Ground-Truth.")
            else:
                print("[FAIL] VALIDATION FAILED: Hallucinations/Mismatches Detected!")
                print("-" * 60)
                for err in result["errors"]:
                    line = err.get("line")
                    msg = err.get("message")
                    sug = err.get("suggestion")
                    sug_str = f"\n  -> Suggestion: {sug}" if sug else ""
                    print(f"Line {line}: {msg}{sug_str}")
            print("="*60 + "\n")
        except Exception as e:
            logger.error(f"Failed to read/validate file: {e}")

    elif args.command == "migrate":
        logger.info(f"Extracting V1 ({args.v1})...")
        v1_chunks = PythonIngestor(args.v1).ingest()
        
        logger.info(f"Extracting V2 ({args.v2})...")
        v2_chunks = PythonIngestor(args.v2).ingest()
        
        result = orchestrator.generate_migration(v1_chunks, v2_chunks)
        
        print("\n" + "="*60)
        print(f"🔥 MIGRATION GUIDE: {args.v1} -> {args.v2} 🔥")
        print("="*60)
        diff = result["diff"]
        print(f"[Diff Engine] Added: {len(diff['added'])}, Removed: {len(diff['removed'])}, Modified: {len(diff['modified'])}")
        print("-" * 60 + "\n")
        print(result["migration_guide"])
        print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    main()
