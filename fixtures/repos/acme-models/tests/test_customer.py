from acme_models.customer import CustomerRequest, to_payload


def test_round_trip():
    req = CustomerRequest(customer_id=7, email="a@example.com")
    assert to_payload(req) == {"customer_id": 7, "email": "a@example.com", "loyalty_points": 0}


def test_default_points():
    assert CustomerRequest(customer_id=1, email="b@example.com").loyalty_points == 0
