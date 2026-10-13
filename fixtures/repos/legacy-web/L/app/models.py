from pydantic import BaseModel


class CustomerRequest(BaseModel):
    """A look-alike: same name and similar fields, but NOT the shared artifact."""
    customer_id: int
    email: str
    loyalty_points: int = 0
