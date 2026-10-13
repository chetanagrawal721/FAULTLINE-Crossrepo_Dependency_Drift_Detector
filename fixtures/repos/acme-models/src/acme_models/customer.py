from pydantic import BaseModel


class CustomerRequest(BaseModel):
    customer_id: int
    email: str
    loyalty_points: int = 0


def to_payload(request: CustomerRequest) -> dict:
    """Serialise for the wire. `.dict()` exists in pydantic 1 and (deprecated) in pydantic 2."""
    return request.dict()
