"""
CareBridge Backend API Smoke Tests
Validates route registration, OpenAPI schemas, and app configuration synchronously.
"""

import unittest
from app.main import app
from app.core.config import settings


class TestCareBridgeAPI(unittest.TestCase):
    def test_app_configuration(self):
        self.assertEqual(settings.APP_NAME, "CareBridge AI Care Coordinator")
        self.assertEqual(settings.API_V1_STR, "/api/v1")
        self.assertIn("http://localhost:3000", settings.CORS_ORIGINS)

    def test_openapi_schema(self):
        schema = app.openapi()
        self.assertEqual(schema["info"]["title"], "CareBridge AI Care Coordinator")
        self.assertEqual(schema["info"]["version"], "0.1.0")
        
        # Verify required endpoints exist in the schema
        paths = schema["paths"]
        self.assertIn("/", paths)
        self.assertIn("/health", paths)
        self.assertIn(f"{settings.API_V1_STR}/health", paths)
        self.assertIn(f"{settings.API_V1_STR}/cases", paths)
        self.assertIn(f"{settings.API_V1_STR}/patients", paths)
        self.assertIn(f"{settings.API_V1_STR}/appointments", paths)
        self.assertIn(f"{settings.API_V1_STR}/referrals", paths)
        self.assertIn(f"{settings.API_V1_STR}/recovery", paths)
        self.assertIn(f"{settings.API_V1_STR}/auth/login", paths)
        self.assertIn(f"{settings.API_V1_STR}/appointments/book", paths)
        self.assertIn(f"{settings.API_V1_STR}/appointments/{{appointment_id}}/cancel", paths)
        self.assertIn(f"{settings.API_V1_STR}/appointments/{{appointment_id}}/reschedule-propose", paths)
        self.assertIn(f"{settings.API_V1_STR}/appointments/{{appointment_id}}/reschedule-accept", paths)


if __name__ == "__main__":
    unittest.main()
