from typing import Dict, Any, Optional
import structlog

logger = structlog.get_logger(__name__)

class BaseLLM:
    """Base interface for all LLM providers."""
    def generate(self, prompt: str, **kwargs) -> str:
        raise NotImplementedError("Each provider must implement generate()")


class LLMRouter:
    """
    Model-agnostic LLM routing layer. Routes queries dynamically to the best model 
    based on task type, token constraints, or cost-awareness.
    """
    
    def __init__(self):
        self._providers: Dict[str, BaseLLM] = {}
        
    def register_provider(self, name: str, provider: BaseLLM):
        self._providers[name] = provider
        logger.info(f"Registered LLM provider: {name}")

    def route(self, task_type: str) -> str:
        """
        Determines the optimal provider ID based on the task description.
        """
        if task_type == "code_generation" and "openai" in self._providers:
            # Use OpenAI (GPT-4o) for high-accuracy code gen
            return "openai"
        elif task_type == "long_context" and "gemini" in self._providers:
            # Use Gemini (1.5 Pro) for 1M+ context tasks
            return "gemini"
        elif task_type == "offline" and "local" in self._providers:
            # Mistral/Llama for offline fallbacks
            return "local"
            
        # Fallback to whatever is available
        available = list(self._providers.keys())
        if not available:
            raise ValueError("No LLM providers registered in the router.")
            
        return available[0]

    def generate(self, prompt: str, task_type: str = "code_generation", **kwargs) -> str:
        """
        Routes the prompt to the appropriate model and generates text.
        """
        provider_name = self.route(task_type)
        provider = self._providers[provider_name]
        
        logger.info(f"Routing task '{task_type}' to '{provider_name}'")
        try:
            return provider.generate(prompt, **kwargs)
        except Exception as e:
            logger.error(f"Provider {provider_name} failed: {e}")
            # Naive failover
            for fallback_name, fallback_provider in self._providers.items():
                if fallback_name != provider_name:
                    logger.info(f"Failing over to '{fallback_name}'")
                    return fallback_provider.generate(prompt, **kwargs)
            raise
