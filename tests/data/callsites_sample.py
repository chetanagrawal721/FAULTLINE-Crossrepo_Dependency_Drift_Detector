import urllib3
import urllib3.util.retry as retry_mod
from urllib3.util.retry import Retry as R
from urllib3 import PoolManager
import importlib
import os


def make():
    a = urllib3.PoolManager(10)
    b = R(total=3, method_whitelist=["GET"])
    c = retry_mod.Retry(*[1, 2], **{"x": 1})
    d = PoolManager(num_pools=5, headers=get_headers())
    e = getattr(urllib3, "PoolManager")(1)
    f = getattr(urllib3, os.environ["NAME"])(2)
    g = importlib.import_module(os.environ["MOD"])
    h = os.path.join("a", "b")
    eval("1+1")
    return a, b, c, d, e, f, g, h


try:
    import requests
except ImportError:
    requests = None

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import yaml


def other():
    requests.get("http://x", timeout=3)
    yaml.safe_load("a: 1")
