import unittest
from pathlib import Path

from app.config import Settings


class TestConfig(unittest.TestCase):
    def test_default_branch_fallback(self):
        original = {
            "DISCORD_TOKEN": "token",
            "GIT_REPO_URL": "https://example.com/repo.git",
            "ALLOWED_USER_IDS": "1,2,3",
            "GIT_BRANCH": "",
            "LOG_LEVEL": "",
        }
        for key, value in original.items():
            import os
            os.environ[key] = value

        settings = Settings.from_env()
        self.assertEqual(settings.git_branch, "main")
        self.assertEqual(settings.allowed_user_ids, ("1", "2", "3"))


if __name__ == "__main__":
    unittest.main()
