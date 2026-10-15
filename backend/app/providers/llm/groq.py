from typing import Optional
from app.providers.llm.base import BaseLLMProvider
from app.core.config import settings
from app.core.exceptions import ProviderError

class GroqLLMProvider(BaseLLMProvider):
    name: str = "groq"

    def __init__(self):
        self.api_key = settings.GROQ_API_KEY
        self.model = settings.GROQ_MODEL
        self._client = None

    def _get_client(self):
        if not self._client:
            if not self.api_key:
                raise ProviderError("Groq API key is not configured in environment.")
            from groq import AsyncGroq
            self._client = AsyncGroq(api_key=self.api_key)
        return self._client

    async def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        client = self._get_client()
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        try:
            chat_completion = await client.chat.completions.create(
                messages=messages,
                model=self.model,
                temperature=temperature,
            )
            return chat_completion.choices[0].message.content or ""
        except Exception as e:
            raise ProviderError(f"Groq API completion error: {str(e)}")
