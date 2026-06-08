import os
import sys
import unittest
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.http_session import create_requests_session, should_trust_env_proxies  # noqa: E402


class NetworkUtilsTests(unittest.TestCase):
    def test_trusts_env_proxies_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(should_trust_env_proxies())

    def test_disables_broken_loopback_discard_proxy(self):
        with patch.dict(os.environ, {"HTTPS_PROXY": "http://127.0.0.1:9"}, clear=True):
            self.assertFalse(should_trust_env_proxies())

    def test_explicit_override_disables_env_proxy_trust(self):
        with patch.dict(os.environ, {"AUDITORIA_TRUST_ENV_PROXY": "false"}, clear=True):
            self.assertFalse(should_trust_env_proxies())

    def test_requests_session_uses_proxy_policy(self):
        with patch.dict(os.environ, {"HTTPS_PROXY": "http://localhost:9"}, clear=True):
            session = create_requests_session()
            self.assertFalse(session.trust_env)


if __name__ == "__main__":
    unittest.main()
