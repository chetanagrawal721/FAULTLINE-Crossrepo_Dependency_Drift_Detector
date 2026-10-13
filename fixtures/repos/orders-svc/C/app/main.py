"""orders-svc (Faultline fixture, scenario C). Uses the shared HTTP retry policies."""
import acme_http.retry as shared

print("loaded", shared.__name__)
