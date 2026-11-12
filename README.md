# MAC/IP Device Inventory

Maintain a network device inventory using data collected from ASUS and Huawei
routers. The project includes a local browser-based editor and a Home Assistant
panel. The user interface and detailed setup guides are currently in Finnish.

![Local device inventory editor showing example data](screenshot1.jpg)

## Features

- Collect MAC and IP addresses, device names and status from configured routers.
- Edit names, add or delete devices, sort columns and filter the inventory.
- Run router updates from the editor and review new devices and IP changes.
- View estimated Wi-Fi connection information from ASUS routers when available.
- Optionally synchronize local device names to ASUS router nicknames.

Router data can be stale, so the reported access point is an estimate, not
proof of a device's current connection. Updates run in the configured order;
later routers can overwrite values recorded by earlier ones. ASUS nickname
synchronization is enabled by default and changes router settings. Set
`sync_nicknames=false` in an ASUS router's configuration to disable it.

## Requirements

- Python 3.10 or later and the `requests` package for router scripts.
- A web browser for the local editor or a Home Assistant installation for the
  Home Assistant panel.
- Node.js is needed only for the JavaScript test.

Install `requests` into the Python environment used to run the router scripts:

```shell
python -m pip install requests
```

## Local setup

1. Create a separate `key=value` configuration file for each router. Use
   [huawei_config_example.txt](huawei_config_example.txt) as a starting point;
   replace the example address and credentials with your own. The ASUS script
   uses the same basic format. The `macip` setting must point to the same
   `macip.txt` in the project directory for every router.
2. Edit [macip_server_config.json](macip_server_config.json) to list your
   router scripts and configuration files in the order they should run.
   Paths are relative to the project directory. For example:

   ```json
   {
     "update_commands": [
       ["asus_mac.py", "secret2.txt"],
       ["huawei_lan_inventory.py", "secret1.txt"]
     ]
   }
   ```

3. Generate an initial `macip.txt` by running one of the configured router
   scripts, or copy an existing inventory into the project directory:

   ```shell
   python asus_mac.py secret2.txt
   ```

   Alternatively, run `python huawei_lan_inventory.py secret1.txt` for a Huawei
   router. The local editor expects `macip.txt` to exist before it is opened.
4. On Windows, run `macip.bat`. Alternatively, run
   `python macip_local_server.py`. Keep the server running while using the
   editor; it listens on `127.0.0.1:8765` and opens the editor in a browser.

The router settings and inventory can contain credentials and personal network
information. Keep them private: `.gitignore` excludes files whose names contain
`secret` and files named `macip.txt`. Use secret filenames accordingly and
check what you are committing.

For detailed local editor, router configuration and ASUS diagnostic instructions,
see [macip_server_ohje.txt](macip_server_ohje.txt) (Finnish).

## Home Assistant

The Home Assistant integration provides an authenticated sidebar panel. For
installation, configuration and migration instructions, see
[the Home Assistant guide](home_assistant/custom_components/macip/README.md)
(Finnish). The Home Assistant integration creates an empty inventory with
headers when it is first opened if the file is missing.

## Tests

From the project directory:

```shell
python -m unittest discover -s tests
node tests/test_macip_filter.js
```

## License

[MIT](LICENSE)
