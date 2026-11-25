"""Safety checks for existing database volumes during upgrades."""
import contextlib
import importlib.util
import io
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("check_db_auth", Path(__file__).with_name("check-db-auth.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

CONFIG = json.dumps({"services": {
    "db": {"environment": {"POSTGRES_USER": "finance", "POSTGRES_PASSWORD": "configured", "POSTGRES_DB": "finance"}},
    "backend": {"environment": {"DATABASE_URL": "postgresql+psycopg://finance:configured@db:5432/finance"}},
}})
INSPECT = json.dumps([{
    "NetworkSettings": {"Networks": {"cw_default": {"IPAddress": "172.20.0.2"}}},
    "Config": {"Env": ["POSTGRES_PASSWORD=previous"]},
}])


def result(stdout="", returncode=0):
    return SimpleNamespace(stdout=stdout, returncode=returncode)


class CheckDbAuthTests(unittest.TestCase):
    def invoke(self, accepted_password=None, *, trust=False, missing_db=False):
        calls = []
        def fake_run(args, *, input_text=None):
            calls.append(args)
            if args[:3] == ["docker", "compose", "config"]:
                return result(CONFIG)
            if args[:4] == ["docker", "compose", "ps", "-q"]:
                return result("" if missing_db else "db-container\n")
            if args[:2] == ["docker", "inspect"]:
                return result(INSPECT)
            if args[:3] == ["docker", "exec", "-i"]:
                return result(returncode=0 if trust or input_text == accepted_password + "\n" else 2)
            raise AssertionError(args)
        output = io.StringIO()
        with patch.object(module, "run", fake_run), patch.object(module.secrets, "token_hex", return_value="wrong"), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = module.main()
        self.assertTrue(all("up" not in call and "tag" not in call for call in calls))
        return code, output.getvalue()

    def test_rejects_configured_password_that_database_does_not_accept(self):
        code, message = self.invoke("previous")
        self.assertEqual(code, 1)
        self.assertIn("认证失败", message)
        self.assertNotIn("configured", message)

    def test_rejects_trust_authentication_that_ignores_password(self):
        code, message = self.invoke("configured", trust=True)
        self.assertEqual(code, 1)
        self.assertIn("未验证密码", message)

    def test_accepts_actual_password_authentication(self):
        code, message = self.invoke("configured")
        self.assertEqual(code, 0)
        self.assertIn("通过数据库网桥认证", message)

    def test_allows_first_install_without_existing_container(self):
        code, message = self.invoke(missing_db=True)
        self.assertEqual(code, 0)
        self.assertIn("首次安装", message)


if __name__ == "__main__":
    unittest.main()
