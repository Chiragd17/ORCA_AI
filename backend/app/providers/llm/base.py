from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

class BaseLLMProvider(ABC):
    name: str

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        """Generate response text for the given prompt."""
        pass
