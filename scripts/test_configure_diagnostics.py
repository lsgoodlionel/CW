"""Guard the interactive token setup against disclosure and failed writes."""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("configure_diagnostics", Path(__file__).with_name("configure-diagnostics.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def response(stdout="", returncode=0):
    return SimpleNamespace(stdout=stdout, returncode=returncode)


class SetupTests(unittest.TestCase):
    def run_setup(self, token, *, upload_ok=True):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env_file = root / ".env"
            env_file.write_text("PAPER_REPO_TOKEN=\nHTTP_PORT=127.0.0.1:18080\n")
            (root / "backups").mkdir()
            commands = []
            def fake_run(args, *, env=None):
                commands.append(args)
                if args[0] == "curl": return response("200")
                if args[:3] == ["docker", "compose", "config"]:
                    return response(json.dumps({"services": {"backend": {"environment": {"PAPER_REPO": "lsgoodlionel/paper"}}}}))
                if args[:4] == ["docker", "compose", "ps", "-q"]: return response("backend-id\n")
                if args[:2] == ["docker", "inspect"]:
                    return response(json.dumps([{"Config": {"Image": "ghcr.io/lsgoodlionel/cw-backend:v1.0.14"}}]))
                if args[:3] == ["docker", "compose", "up"]: return response()
                if args[:2] == ["docker", "exec"]:
                    return response("True\n" if "diag.enabled" in args[-1] or upload_ok else "False\n",
                                    0 if "diag.enabled" in args[-1] or upload_ok else 1)
                raise AssertionError(args)
            class FakeUrlopen(io.BytesIO):
                pass
            output = io.StringIO()
            with patch.object(module, "APP_DIR", root), patch.object(module, "ENV_FILE", env_file), \
                 patch.object(module.os, "geteuid", return_value=0), \
                 patch.object(module.sys, "stdin", SimpleNamespace(isatty=lambda: True)), \
                 patch.object(module.getpass, "getpass", return_value=token), \
                 patch.object(module.urllib.request, "urlopen", return_value=FakeUrlopen(b'{"full_name":"lsgoodlionel/paper"}')), \
                 patch.object(module, "run", side_effect=fake_run), \
                 contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                result = module.main()
            return result, output.getvalue(), env_file.read_text(), env_file.stat().st_mode & 0o777, commands

    def test_valid_token_is_not_printed_or_passed_as_command_argument(self):
        secret = "github_pat_test_secret"
        result, output, env, mode, commands = self.run_setup(secret)
        self.assertEqual(result, 0)
        self.assertNotIn(secret, output)
        self.assertTrue(all(secret not in " ".join(command) for command in commands))
        self.assertIn("PAPER_REPO_TOKEN=" + secret, env)
        self.assertEqual(mode, 0o600)

    def test_invalid_token_does_not_change_env(self):
        result, output, env, _, _ = self.run_setup(" # 中文占位")
        self.assertEqual(result, 1)
        self.assertEqual(env.splitlines()[0], "PAPER_REPO_TOKEN=")
        self.assertNotIn("中文占位", output)

    def test_failed_test_upload_restores_prior_env(self):
        result, output, env, _, _ = self.run_setup("github_pat_test_secret", upload_ok=False)
        self.assertEqual(result, 1)
        self.assertEqual(env.splitlines()[0], "PAPER_REPO_TOKEN=")
        self.assertIn("已恢复旧配置", output)


if __name__ == "__main__":
    unittest.main()
