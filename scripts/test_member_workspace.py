import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "share/vasp-pbs/scripts"))
import setup_workspace as deploy


class MemberWorkspaceTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name).resolve()
        self.library = base / "published"
        self.old = base / "old"
        self.member = base / "member"
        self.member.mkdir()
        for name, value in (("LIBRARY_ROOT", self.library), ("OLD_ROOT", self.old)):
            change = patch.object(deploy, name, value)
            change.start()
            self.addCleanup(change.stop)
        self.source = self.library / deploy.AICC_NAME
        for name in ("AGENTS.md", "site-zjt.md", ".upstream-revision", "tools/hpc-submit/SKILL.md",
                     "tools/vasp/SKILL.md", "tools/vasp/scripts/check_inputs.py",
                     "tools/vasp/scripts/parse_vasp.py", "procedures/comp-chem-workflow/SKILL.md"):
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(name.encode())

    def test_private_install_independent_of_group_index(self):
        owned = deploy.install_aicc(self.member)
        self.assertEqual(owned, self.member / deploy.AICC_NAME)
        self.assertFalse(owned.is_symlink())
        self.assertEqual((owned / ".upstream-revision").read_bytes(), b".upstream-revision")
        self.assertIn(str(self.member), (owned / "site-zjt.md").read_text(encoding="utf-8"))
        (owned / "tools/vasp/SKILL.md").write_bytes(b"personal edits")
        deploy.install_aicc(self.member)
        self.assertEqual((owned / "tools/vasp/SKILL.md").read_bytes(), b"personal edits")
        self.assertEqual((self.source / "tools/vasp/SKILL.md").read_bytes(), b"tools/vasp/SKILL.md")

    @unittest.skipUnless(os.name == "posix", "Remote directory locks and symlinks require POSIX")
    def test_legacy_links_migrate_then_disable_without_losing_personal_files(self):
        import pwd
        from types import SimpleNamespace
        knowledge = self.member / "knowledge"
        personal = knowledge / "personal"
        personal.mkdir(parents=True)
        (personal / "README.md").write_bytes(b"member notes")
        for name, rel in (("default", "Master"), ("examples", "Materials/examples"), ("group", "Master")):
            (knowledge / name).symlink_to(self.old / rel)
        (self.library / "Master").mkdir()
        (self.library / "Master/README.md").touch()
        (self.library / "Master/case_index.md").touch()
        (self.library / "Materials/examples").mkdir(parents=True)
        with patch.object(pwd, "getpwuid", return_value=SimpleNamespace(pw_name="zjt")):
            state = deploy.configure_remote(str(self.member), True)
            self.assertEqual(Path(state["aicc"]), self.member / deploy.AICC_NAME)
            self.assertEqual((knowledge / "default").resolve(), self.library / "Master")
            self.assertEqual((knowledge / "examples").resolve(), self.library / "Materials/examples")
            self.assertFalse((knowledge / "group").is_symlink())
            deploy.configure_remote(str(self.member), False)
            self.assertFalse((knowledge / "default").is_symlink())
            self.assertFalse((knowledge / "examples").is_symlink())
            self.assertTrue((self.member / deploy.AICC_NAME / "AGENTS.md").is_file())
            self.assertEqual((personal / "README.md").read_bytes(), b"member notes")
            (knowledge / "default").symlink_to(personal)
            with self.assertRaisesRegex(ValueError, "Unrelated link"):
                deploy.configure_remote(str(self.member), True)
            self.assertEqual((knowledge / "default").resolve(), personal)


if __name__ == "__main__":
    unittest.main()
