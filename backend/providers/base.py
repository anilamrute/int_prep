from abc import ABC, abstractmethod
from typing import Generator


class AIProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def check_health(self) -> bool:
        ...

    @abstractmethod
    def generate(
        self, question: str, system_prompt: str
    ) -> Generator[dict, None, None]:
        ...
