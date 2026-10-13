"""A reference that may be a number or text (scenario E)."""
from typing import Union

from pydantic import BaseModel


class Ref(BaseModel):
    value: Union[int, str]             # pydantic 1 tries int first, so "42" becomes 42; pydantic 2 keeps "42" as text
