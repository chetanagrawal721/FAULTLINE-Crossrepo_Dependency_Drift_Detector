"""fulfilment-svc (Faultline demo fixture). Uses every module of the shared library, in a world with newer dependencies."""
import acme_showcase.customer as customer
import acme_showcase.ids as ids
import acme_showcase.retry as retry
import acme_showcase.web as web

print("loaded", customer.__name__, ids.__name__, retry.__name__, web.__name__)
