"""reporting-svc (Faultline demo fixture). Uses the shared library in exactly the library's own world: nothing differs, so nothing is run."""
import acme_showcase.customer as customer
import acme_showcase.ids as ids
import acme_showcase.retry as retry
import acme_showcase.web as web

print("loaded", customer.__name__, ids.__name__, retry.__name__, web.__name__)
