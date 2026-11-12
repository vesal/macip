import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, call, patch
from urllib.parse import quote

import requests
import asus_mac


class AsusNicknameTests(unittest.TestCase):
    def setUp(self):
        self.mac = "AA:BB:CC:DD:EE:FF"
        self.other = "11:22:33:44:55:66"
        self.clients = {self.mac: {"type": "2", "isOnline": "0"},
                        self.other: {"type": "0", "isOnline": "1"}, "maclist": [self.other]}
        self.rows = {self.mac.lower(): {"Oma nimi": "Päivin laite"},
                     self.other.lower(): {"Oma nimi": "Uusi"}}
        self.original = f"<Vanha>{self.mac}>7>2>callback>keep>extra<Untouched>00:00:00:00:00:01>0>0>>"

    def test_merge_preserves_other_fields_and_adds_offline_or_online_clients(self):
        result, count = asus_mac.build_custom_clientlist(self.original, self.clients, self.rows)
        self.assertEqual(count, 2)
        self.assertEqual(result, f"<Päivin laite>{self.mac}>7>2>callback>keep>extra"
                                 f"<Untouched>00:00:00:00:00:01>0>0>>"
                                 f"<Uusi>{self.other}>0>0>>")
        self.assertEqual(asus_mac.build_custom_clientlist(result, self.clients, self.rows), (result, 0))

    def test_invalid_or_duplicate_entries_and_names_rejected(self):
        for raw in ("broken", "<bad", self.original + f"<duplicate>{self.mac}>0>0>>"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                asus_mac.build_custom_clientlist(raw, self.clients, self.rows)
        self.rows[self.mac.lower()]["Oma nimi"] = "Bad<name"
        with self.assertRaises(ValueError):
            asus_mac.build_custom_clientlist(self.original, self.clients, self.rows)

    def test_missing_empty_and_placeholder_names_do_not_replace_router_names(self):
        for name in ("", "  ", "--", "0"):
            with self.subTest(name=name):
                self.rows[self.mac.lower()]["Oma nimi"] = name
                result, count = asus_mac.build_custom_clientlist(self.original, self.clients, self.rows)
                self.assertIn(f"<Vanha>{self.mac}>7>2>callback>keep>extra", result)
                self.assertEqual(count, 1)

    def test_read_custom_list_decodes_utf8_and_rejects_bad_response(self):
        session = MagicMock()
        response = session.get.return_value
        response.text = "{}"
        response.json.return_value = {"custom_clientlist": quote(self.original, safe="")}
        config = {"protocol": "http", "ip": "192.0.2.1", "verify": "true"}
        self.assertEqual(asus_mac.get_custom_clientlist(session, config), self.original)
        self.assertEqual(session.get.call_args.kwargs["params"]["hook"],
                         "nvram_char_to_ascii(custom_clientlist,custom_clientlist)")
        response.json.return_value = {"custom_clientlist": "%ZZ"}
        with self.assertRaises(ValueError):
            asus_mac.get_custom_clientlist(session, config)
        response.json.return_value = {}
        with self.assertRaises(ValueError):
            asus_mac.get_custom_clientlist(session, config)

    def test_sync_posts_only_changes_and_verifies(self):
        updated, _ = asus_mac.build_custom_clientlist(self.original, self.clients, self.rows)
        session = MagicMock()
        session.post.return_value.text = ""
        config = {"protocol": "http", "ip": "192.0.2.1", "verify": "true", "macip": "file"}
        with patch.object(asus_mac, "read_macip", return_value=(Path("file"), [], self.rows)), \
             patch.object(asus_mac, "get_custom_clientlist", side_effect=[self.original, updated]), \
             redirect_stdout(io.StringIO()):
            asus_mac.sync_nicknames(session, config, self.clients)
        self.assertEqual(session.post.call_args.args[0], "http://192.0.2.1/start_apply2.htm")
        self.assertEqual(session.post.call_args.kwargs["data"]["custom_clientlist"], updated)
        self.assertEqual(session.post.call_args.kwargs["data"]["action_script"], "saveNvram")

    def test_sync_no_changes_does_not_post(self):
        session = MagicMock()
        config = {"macip": "file"}
        with patch.object(asus_mac, "read_macip", return_value=(Path("file"), [], {})), \
             patch.object(asus_mac, "get_custom_clientlist", return_value=self.original), \
             redirect_stdout(io.StringIO()):
            asus_mac.sync_nicknames(session, config, self.clients)
        session.post.assert_not_called()

    def test_sync_reports_unverified_write(self):
        session = MagicMock()
        config = {"protocol": "http", "ip": "192.0.2.1", "verify": "true", "macip": "file"}
        with patch.object(asus_mac, "read_macip", return_value=(Path("file"), [], self.rows)), \
             patch.object(asus_mac, "get_custom_clientlist", return_value=self.original):
            with self.assertRaises(RuntimeError):
                asus_mac.sync_nicknames(session, config, self.clients)
        session.post.assert_called_once()

    def test_import_only_fills_empty_existing_rows(self):
        raw = (f"<Reitittimen nimi>{self.mac}>0>0>>"
               f"<Toinen>{self.other}>0>0>>"
               "<Tuntematon>22:22:22:22:22:22>0>0>>")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "macip.txt"
            path.write_text(
                f"MAC | IP | Oma nimi\n{self.mac.lower()} | 192.0.2.1 | \n"
                f"{self.other.lower()} | 192.0.2.2 | Oma nimi\n", encoding="utf-8"
            )
            config = {"macip": str(path), "sync_nicknames": "false"}
            with patch.object(asus_mac, "get_custom_clientlist", return_value=raw), \
                 redirect_stdout(io.StringIO()):
                asus_mac.import_nicknames(MagicMock(), config)
            rows = asus_mac.read_macip(path)[2]
        self.assertEqual(rows[self.mac.lower()]["Oma nimi"], "Reitittimen nimi")
        self.assertEqual(rows[self.other.lower()]["Oma nimi"], "Oma nimi")
        self.assertEqual(len(rows), 2)

    def test_import_rejects_invalid_name_without_saving(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "macip.txt"
            content = f"MAC | IP | Oma nimi\n{self.mac} | 192.0.2.1 | \n"
            path.write_bytes(content.encode("utf-8"))
            raw = f"<Bad|name>{self.mac}>0>0>>"
            with patch.object(asus_mac, "get_custom_clientlist", return_value=raw):
                with self.assertRaises(ValueError):
                    asus_mac.import_nicknames(MagicMock(), {"macip": str(path)})
            self.assertEqual(path.read_bytes(), content.encode("utf-8"))

    def test_import_skips_empty_and_placeholder_router_names(self):
        for name in ("", " ", "--", "0"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "macip.txt"
                content = f"MAC | IP | Oma nimi\n{self.mac} | 192.0.2.1 | \n"
                path.write_bytes(content.encode("utf-8"))
                with patch.object(asus_mac, "get_custom_clientlist",
                                  return_value=f"<{name}>{self.mac}>0>0>>"), \
                     redirect_stdout(io.StringIO()):
                    asus_mac.import_nicknames(MagicMock(), {"macip": str(path)})
                self.assertEqual(path.read_bytes(), content.encode("utf-8"))

    def test_main_imports_after_update_when_router_sync_is_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "macip.txt"
            path.write_text(f"MAC | IP | Oma nimi\n{self.mac} | 192.0.2.1 | \n",
                            encoding="utf-8")
            config = {"ip": "192.0.2.1", "macip": str(path), "sync_nicknames": "false"}
            with patch.object(asus_mac.sys, "argv", ["asus_mac.py", "config"]), \
                 patch.object(asus_mac, "read_config", return_value=config), \
                 patch.object(asus_mac, "login", return_value=MagicMock()), \
                 patch.object(asus_mac, "get_client_list", return_value={"maclist": []}), \
                 patch.object(asus_mac, "get_custom_clientlist", return_value=self.original), \
                 patch.object(asus_mac, "sync_nicknames") as sync, \
                 patch.object(asus_mac, "logout"), redirect_stdout(io.StringIO()):
                asus_mac.main()
            self.assertEqual(asus_mac.read_macip(path)[2][self.mac.lower()]["Oma nimi"], "Vanha")
            sync.assert_not_called()

    def test_main_saves_before_sync_and_failure_is_reported(self):
        config = {"ip": "192.0.2.1"}
        session = MagicMock()
        order = MagicMock()
        order.sync.side_effect = requests.ConnectionError("sync failed")
        output = io.StringIO()
        with patch.object(asus_mac.sys, "argv", ["asus_mac.py", "config"]), \
             patch.object(asus_mac, "read_config", return_value=config), \
             patch.object(asus_mac, "login", return_value=session), \
             patch.object(asus_mac, "get_client_list", return_value={"maclist": []}), \
             patch.object(asus_mac, "update_macip", order.update), \
             patch.object(asus_mac, "import_nicknames", order.import_names), \
             patch.object(asus_mac, "sync_nicknames", order.sync), \
             patch.object(asus_mac, "logout") as logout, redirect_stdout(output):
            with self.assertRaises(SystemExit):
                asus_mac.main()
        self.assertEqual(order.mock_calls, [call.update({"maclist": []}, config),
                                            call.import_names(session, config),
                                            call.sync(session, config, {"maclist": []})])
        self.assertIn("sync failed", output.getvalue())
        logout.assert_called_once()

    def test_opt_out_and_debug_do_not_synchronize(self):
        for argv, config in [
            (["asus_mac.py", "config"], {"ip": "192.0.2.1", "sync_nicknames": "false"}),
            (["asus_mac.py", "config", ".*"], {"ip": "192.0.2.1"}),
        ]:
            with self.subTest(argv=argv), \
                 patch.object(asus_mac.sys, "argv", argv), \
                 patch.object(asus_mac, "read_config", return_value=config), \
                 patch.object(asus_mac, "login", return_value=MagicMock()), \
                 patch.object(asus_mac, "get_client_list", return_value={"maclist": []}), \
                 patch.object(asus_mac, "get_router_list", return_value={}), \
                 patch.object(asus_mac, "update_macip"), \
                 patch.object(asus_mac, "import_nicknames") as import_names, \
                 patch.object(asus_mac, "sync_nicknames") as sync, \
                 patch.object(asus_mac, "logout"), redirect_stdout(io.StringIO()):
                asus_mac.main()
                sync.assert_not_called()
                if len(argv) == 2:
                    import_names.assert_called_once()
                else:
                    import_names.assert_not_called()


if __name__ == "__main__":
    unittest.main()
