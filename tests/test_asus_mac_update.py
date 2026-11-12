import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import asus_mac


class AsusMacUpdateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "macip.txt"
        self.path.write_text(
            "MAC | IP | Oma nimi | Tila | Yhteys | Signaali | Tukiasema\n"
            "00:00:00:00:00:01 | 192.0.2.1 | yksi | Online | 5 GHz | -50 | r3\n"
            "00:00:00:00:00:02 | 192.0.2.2 | kaksi | Online | 2.4 GHz | -60 | r2\n"
            "00:00:00:00:00:03 | 192.0.2.3 | kolme | Offline | 5 GHz | -70 | r3\n",
            encoding="utf-8",
        )
        self.config = {"ip": "192.0.2.10", "macip": str(self.path), "router_nickname": "r3"}

    def update(self, clients):
        with redirect_stdout(io.StringIO()):
            asus_mac.update_macip(clients, self.config)
        return asus_mac.read_macip(self.path)[2]

    def test_clear_only_current_access_point_and_repopulate_valid_client(self):
        clients = {
            "maclist": ["00:00:00:00:00:01"],
            "00:00:00:00:00:01": {
                "isOnline": "1", "isWL": "2", "rssi": "-42",
                "amesh_papMac": "AA:BB:CC:DD:EE:FF", "ip": "192.0.2.1",
            },
        }
        rows = self.update(clients)
        self.assertEqual([rows["00:00:00:00:00:01"][field] for field in
                          ("Yhteys", "Signaali", "Tukiasema")], ["5 GHz", "-42", "r3"])
        self.assertEqual([rows["00:00:00:00:00:02"][field] for field in
                          ("Yhteys", "Signaali", "Tukiasema")], ["2.4 GHz", "-60", "r2"])
        self.assertEqual([rows["00:00:00:00:00:03"][field] for field in
                          ("Yhteys", "Signaali", "Tukiasema")], ["", "", ""])
        self.assertEqual(rows["00:00:00:00:00:03"]["Tila"], "Offline")

    def test_candidate_requires_online_wireless_parent_and_negative_signal(self):
        base = {"isOnline": "1", "isWL": "1", "rssi": "-40",
                "amesh_papMac": "AA:BB:CC:DD:EE:FF", "ip": "192.0.2.1"}
        cases = [
            {"isOnline": "0"}, {"isWL": "0"}, {"rssi": "0"},
            {"rssi": ""}, {"amesh_papMac": ""}, {"amesh_papMac": None},
        ]
        for change in cases:
            with self.subTest(change=change):
                client = {**base, **change}
                rows = self.update({"maclist": ["00:00:00:00:00:01"],
                                    "00:00:00:00:00:01": client})
                self.assertEqual(rows["00:00:00:00:00:01"]["Tukiasema"], "")

    def test_later_router_overwrites_previous_access_point(self):
        mac = "00:00:00:00:00:01"
        clients = {"maclist": [mac], mac: {
            "isOnline": "1", "isWL": "1", "rssi": "-36",
            "amesh_papMac": "AA:BB:CC:DD:EE:FF", "ip": "192.0.2.1",
        }}
        self.update(clients)
        self.config["router_nickname"] = "r2"
        rows = self.update(clients)
        self.assertEqual(rows[mac]["Tukiasema"], "r2")
        self.assertEqual(rows[mac]["Yhteys"], "2.4 GHz")

    def test_missing_nickname_uses_router_ip_for_clearing(self):
        self.config["router_nickname"] = ""
        self.path.write_text(
            "MAC | IP | Tukiasema | Yhteys | Signaali\n"
            "00:00:00:00:00:01 | 192.0.2.1 | 192.0.2.10 | 5 GHz | -50\n",
            encoding="utf-8",
        )
        rows = self.update({"maclist": []})
        self.assertEqual(rows["00:00:00:00:00:01"]["Tukiasema"], "")
        self.assertEqual(rows["00:00:00:00:00:01"]["Yhteys"], "")

    def test_invalid_maclist_does_not_change_file(self):
        original = self.path.read_bytes()
        for clients in ({}, {"maclist": None}, {"maclist": ["good", 1]}):
            with self.subTest(clients=clients), self.assertRaises(ValueError):
                self.update(clients)
            self.assertEqual(self.path.read_bytes(), original)

    def test_reset_and_multiple_routers_combine_online_observations(self):
        first = "00:00:00:00:00:01"
        second = "00:00:00:00:00:02"
        third = "00:00:00:00:00:03"
        self.config.update(set_offline="true", allow_online="true")
        rows = self.update({"maclist": [first], first: {
            "isOnline": "1", "isWL": "0", "rssi": "0", "ip": "192.0.2.1",
        }})
        self.assertEqual([rows[mac]["Tila"] for mac in (first, second, third)],
                         ["Online", "Offline", "Offline"])

        self.config["set_offline"] = "false"
        rows = self.update({"maclist": [first, second], first: {"isOnline": "0"},
                            second: {"isOnline": "1", "ip": "192.0.2.2"}})
        self.assertEqual([rows[mac]["Tila"] for mac in (first, second, third)],
                         ["Online", "Online", "Offline"])

    def test_allow_online_false_preserves_status_and_updates_other_fields(self):
        mac = "00:00:00:00:00:03"
        self.config["allow_online"] = "false"
        rows = self.update({"maclist": [mac], mac: {
            "isOnline": "1", "ip": "192.0.2.33",
        }})
        self.assertEqual(rows[mac]["Tila"], "Offline")
        self.assertEqual(rows[mac]["IP"], "192.0.2.33")

    def test_default_settings_preserve_existing_behavior(self):
        mac = "00:00:00:00:00:03"
        rows = self.update({"maclist": [mac], mac: {
            "isOnline": "1", "ip": "192.0.2.3",
        }})
        self.assertEqual(rows[mac]["Tila"], "Online")
        self.assertEqual(rows["00:00:00:00:00:02"]["Tila"], "Online")

    def test_set_offline_without_allow_online(self):
        self.config.update(set_offline="true", allow_online="false")
        mac = "00:00:00:00:00:01"
        rows = self.update({"maclist": [mac], mac: {
            "isOnline": "1", "ip": "192.0.2.1",
        }})
        self.assertTrue(all(row["Tila"] == "Offline" for row in rows.values()))

    def test_invalid_status_options_leave_file_unchanged(self):
        original = self.path.read_bytes()
        for option in ("set_offline", "allow_online"):
            with self.subTest(option=option):
                self.config[option] = "invalid"
                with self.assertRaisesRegex(ValueError, option):
                    self.update({"maclist": []})
                self.assertEqual(self.path.read_bytes(), original)
                del self.config[option]

    def test_invalid_signal_is_reported(self):
        mac = "00:00:00:00:00:01"
        clients = {"maclist": [mac], mac: {
            "isOnline": "1", "isWL": "1", "rssi": "invalid",
            "amesh_papMac": "AA:BB:CC:DD:EE:FF", "ip": "192.0.2.1",
        }}
        error = io.StringIO()
        with redirect_stderr(error):
            rows = self.update(clients)
        self.assertIn("Virheellinen signaali", error.getvalue())
        self.assertEqual(rows[mac]["Tukiasema"], "")


if __name__ == "__main__":
    unittest.main()
