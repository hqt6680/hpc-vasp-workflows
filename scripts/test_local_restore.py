import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "share/vasp-pbs/scripts"))
import local_workspace as deploy


class RestoreTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "member"
        self.root.mkdir()
        env = patch.dict(os.environ, LOCALAPPDATA=str(Path(tmp.name) / "appdata"))
        env.start()
        self.addCleanup(env.stop)
        self.task = self.enter_patch(patch.object(deploy, "task", return_value=False))

    def enter_patch(self, p):
        self.addCleanup(p.stop)
        return p.start()

    def test_empty_workspace_and_watcher(self):
        deploy.install(self.root, cfg="site")
        deploy.install(self.root, watcher=True)
        state = deploy.runtime(self.root)
        state.mkdir(parents=True)
        (state / "watch.sqlite3").write_bytes(b"test state")
        (state / "watch.log.1").write_text("test")
        cache = self.root / "scripts/__pycache__"
        cache.mkdir()
        (cache / "desktop_owner.cpython-310.pyc").touch()
        deploy.install(self.root, watcher=True)
        deploy.restore(self.root)
        self.task.assert_called_with(self.root, remove=True)
        self.assertFalse(state.parent.exists())
        self.assertEqual(list(self.root.iterdir()), [])
        deploy.restore(self.root)

    def test_preserves_user_files_and_edits(self):
        original = b"\xef\xbb\xbfMy rules\r\n"
        rules = self.root / "AGENTS.md"
        rules.write_bytes(original)
        settings = self.root / ".vasp-local"
        settings.mkdir()
        (settings / "knowledge.md").touch()
        scripts = self.root / "scripts"
        scripts.mkdir()
        (scripts / "pbs_watch.config.json").write_bytes(b"original")
        self.task.return_value = True
        deploy.install(self.root, watcher=True, cfg="site")
        with rules.open("ab") as stream:
            stream.write(b"New note\r\n")
        (scripts / "personal.py").touch()
        (scripts / "pbs_watch.py").write_text("locally edited code")
        deploy.restore(self.root)
        self.assertEqual(rules.read_bytes(), original + b"New note\r\n")
        self.assertEqual((settings / "knowledge.md").read_bytes(), b"")
        self.assertEqual((scripts / "pbs_watch.config.json").read_bytes(), b"original")
        self.assertTrue((scripts / "personal.py").exists())
        self.assertEqual((scripts / "pbs_watch.py").read_text(), "locally edited code")
        self.task.assert_called_once_with(self.root)

    def test_conflict_precedes_local_writes(self):
        folder = self.root / "scripts"
        folder.mkdir()
        (folder / "pbs_watch.py").write_text("existing code")
        with self.assertRaisesRegex(ValueError, "Existing file differs"):
            deploy.install(self.root, watcher=True)
        self.assertEqual(list(self.root.iterdir()), [folder])

    def test_new_project_and_preexisting_empty_directories(self):
        created = self.root / "new project"
        deploy.install(created, cfg="site")
        deploy.restore(created)
        self.assertFalse(created.exists())
        (self.root / ".agents").mkdir()
        deploy.install(self.root)
        deploy.install(self.root, cfg="site")
        deploy.restore(self.root)
        self.assertEqual(list(self.root.iterdir()), [self.root / ".agents"])

    def test_interrupted_restore_can_resume(self):
        deploy.install(self.root, cfg="site")
        real_unlink = Path.unlink
        def interrupted(path, *args, **kwargs):
            if path.name == "setup_workspace.py":
                raise PermissionError("file in use")
            return real_unlink(path, *args, **kwargs)
        with patch.object(Path, "unlink", interrupted), self.assertRaises(PermissionError):
            deploy.restore(self.root)
        self.assertTrue((self.root / deploy.RECEIPT).is_file())
        deploy.restore(self.root)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_legacy_markers_and_template(self):
        m = self.root / ".vasp-local"
        m.mkdir()
        cfg = m / "knowledge.md"
        cfg.write_bytes(deploy.section(cfg, "site"))
        rules = self.root / "AGENTS.md"
        template = (deploy.SOURCE / "assets/project/AGENTS.md").read_bytes()
        rules.write_bytes(b"old rules\r\n\r\n" + template.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        rules.write_bytes(deploy.section(rules, deploy.LOCAL_RULE))
        deploy.restore(self.root)
        self.assertEqual(rules.read_bytes(), b"old rules")
        self.assertEqual(list(self.root.iterdir()), [rules])
