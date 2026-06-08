import asyncio
import logging
import os
import sys
import unittest
from unittest.mock import patch


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main  # noqa: E402
from routers import system  # noqa: E402


class _FakeSentryScope:
    def __init__(self):
        self.tags = {}
        self.extras = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def set_tag(self, key, value):
        self.tags[key] = value

    def set_extra(self, key, value):
        self.extras[key] = value


class _FakeSentrySdk:
    def __init__(self):
        self.scope = _FakeSentryScope()
        self.messages = []

    def new_scope(self):
        return self.scope

    def capture_message(self, message, level=None):
        self.messages.append({"message": message, "level": level})


class TestSentryMonitoring(unittest.TestCase):
    def test_sample_rate_parser_clamps_invalid_values(self):
        with patch.dict(
            os.environ,
            {
                "SENTRY_TRACES_SAMPLE_RATE": "2.5",
                "SENTRY_PROFILES_SAMPLE_RATE": "invalid",
                "SENTRY_EMPTY_SAMPLE_RATE": "",
            },
            clear=False,
        ):
            self.assertEqual(main._parse_sentry_sample_rate("SENTRY_TRACES_SAMPLE_RATE", 0.0), 1.0)
            self.assertEqual(main._parse_sentry_sample_rate("SENTRY_PROFILES_SAMPLE_RATE", 0.25), 0.25)
            self.assertEqual(main._parse_sentry_sample_rate("SENTRY_EMPTY_SAMPLE_RATE", 0.5), 0.5)

    def test_sentry_can_be_disabled_even_with_dsn_configured(self):
        with patch.dict(os.environ, {"SENTRY_ENABLED": "false", "SENTRY_DSN": "https://example@sentry.io/1"}, clear=False):
            self.assertTrue(main._sentry_monitoring_disabled())

    def test_scrub_sentry_event_filters_sensitive_request_headers(self):
        event = {
            "request": {
                "cookies": {"session": "secret"},
                "headers": {
                    "Authorization": "Bearer secret",
                    "X-API-Key": "secret",
                    "Accept": "application/json",
                },
            }
        }

        scrubbed = main._scrub_sentry_event(event, None)

        self.assertNotIn("cookies", scrubbed["request"])
        self.assertEqual(scrubbed["request"]["headers"]["Authorization"], "[Filtered]")
        self.assertEqual(scrubbed["request"]["headers"]["X-API-Key"], "[Filtered]")
        self.assertEqual(scrubbed["request"]["headers"]["Accept"], "application/json")

    def test_client_log_capture_sanitizes_url_and_sets_frontend_tags(self):
        fake_sentry = _FakeSentrySdk()
        request = system.ClientLogRequest(
            level="error",
            message="Browser crashed",
            stack="stacktrace",
            url="https://auditoria.example/app?token=secret#fragment",
            user_agent="TestAgent",
        )

        with patch.object(system, "sentry_sdk", fake_sentry):
            system._capture_client_log_in_sentry(request, "error")

        self.assertEqual(fake_sentry.messages, [{"message": "Browser crashed", "level": "error"}])
        self.assertEqual(fake_sentry.scope.tags["source"], "frontend")
        self.assertEqual(fake_sentry.scope.tags["client_log_level"], "error")
        self.assertEqual(fake_sentry.scope.extras["frontend_url"], "https://auditoria.example/app")
        self.assertEqual(fake_sentry.scope.extras["user_agent"], "TestAgent")
        self.assertEqual(fake_sentry.scope.extras["frontend_stack"], "stacktrace")

    def test_client_log_endpoint_logs_errors_as_warning_and_captures_once(self):
        fake_sentry = _FakeSentrySdk()
        request = system.ClientLogRequest(
            level="error",
            message="API Request Failed",
            stack=None,
            url="https://auditoria.example/app?token=secret",
            user_agent="TestAgent",
        )

        with patch.object(system, "sentry_sdk", fake_sentry):
            with patch.object(system.logger, "log") as mock_log:
                response = asyncio.run(system.receive_client_logs(request))

        self.assertEqual(response, {"status": "ok"})
        mock_log.assert_called_once()
        self.assertEqual(mock_log.call_args.args[0], logging.WARNING)
        self.assertEqual(fake_sentry.messages, [{"message": "API Request Failed", "level": "error"}])


if __name__ == "__main__":
    unittest.main()
