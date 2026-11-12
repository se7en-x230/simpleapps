Native C/GTK frontend
---------------------
The window is compiled C/GTK4. Shared frontend source: ../simple-common/organizer.c, built separately by each app Makefile. Native executable: ~/.local/bin/simplecontacts-native. Python remains the provider/storage worker. Both frontends invoke ../simple-common/organizer-helper.py using JSON on stdin/stdout; adapters are bridge.py. Future Google sign-ins share google_oauth.py; existing tokens and caches retain their formats and locations. Calendar and Contacts keep separate permission grants.

Newinit setup-runtime.py builds and installs the native binary locally. Sources and configuration sync; compiled binaries, account tokens and personal caches do not. Legacy ui.py is retained only as reference and is not launched.

# SimpleContacts
Google Contacts through the People API, with a private local JSON address book for offline browsing. Shared Simple theme and Vim navigation. Search, copy phone/email, draft email in SimpleMail, create/edit/delete contacts online, and export vCards. The editor supports names, multiple emails/phones, and notes; other Google fields are preserved and displayed read-only.

Launch `simplecontacts` or Super+Alt+A. j/k select; h/l focus; / search; n new; e edit; x delete (confirmation); s sync; c accounts; b export. Configuration: ~/.config/simplecontacts/{config.ini,keys.ini,style.css}. Global navigation inherits simple/keys.ini. Reopen after configuration changes.

Enable People API in the Google Cloud project used for Calendar. Accounts → Connect Google reuses ~/.config/simplecalendar/google-client.json and opens the dedicated cloud-setup browser. Google must separately approve the contacts scope. Calendar credentials are never altered. --connect --client-json PATH accepts another Desktop OAuth client. Newinit Final Setup also has Contacts setup. Sign in once per device.

Private data and token: ~/.local/share/simplecontacts (directory 0700; JSON 0600), not copied by dotfile sync. Atomic snapshots retain the ten most recent nonempty versions in history/. Export does not include photos or all Google-specific metadata; the private JSON snapshots retain the full fetched fields. Read scope excludes Google's separate Other Contacts suggestions and domain directory.

Background refresh every 30 minutes plus on open/manual sync. Failed requests leave the local snapshot intact. Saves require a connection; no offline write queue. Updates use source etags and only changed fields. Deletes compare the latest source revision immediately before the request; Google's delete endpoint has no revision parameter. Create failures after a network interruption can be ambiguous: sync and check before retrying. Successful write responses are retained for ten minutes while the list endpoint catches up. The UI does not claim that local exports are a complete Google account backup.

Dependencies: python, python-gobject, gtk4, python-google-auth, python-requests. No extra runtime or web server; OAuth uses a short-lived localhost callback with state verification and PKCE. OAuth tokens stay on this computer. Google apps in Testing may require reauthorization.

Sources:
https://developers.google.com/people/v1/contacts
https://developers.google.com/people/api/rest/v1/people/updateContact
https://developers.google.com/people/api/rest/v1/people.connections/list
https://developers.google.com/identity/protocols/oauth2/native-app

## Shared base and portable installation

Uses the shared C/GTK4 base in `simple-common`. Python UI code calls the same native library through a thin adapter. Shared theme and keyboard adapters replace separate implementations; app-specific commands and content remain local.

Requires Linux and Python 3.11+ for the source installer. Building the shared base requires a C compiler, make, pkg-config and GTK4 >= 4.12 development files. Install dependencies using your distribution’s package manager; package names can differ.

- Libraries / pkg-config modules: `gtk4 >= 4.12`, `json-c`.
- Python imports: `google.auth`, `requests`.
- Required commands: `cc`, `make`, `pkg-config`, `python3`.
- Desktop requirements: GTK desktop.

From the suite checkout (no pacman or distro detection on this path):

```sh
./install --dependencies simplecontacts
./install --check simplecontacts
./install --no-packages --install simplecontacts
```

To build a relocatable staging tree without changing your installation:

```sh
./install --install simplecontacts --stage "$PWD/package-simplecontacts"
```

Keep `simple-common` alongside the app sources. Staged files are under `.local/`; move that prefix as a unit so executables, shared libraries and resources stay together. Individual C Makefiles also accept `PREFIX`/`DESTDIR` where documented. See [portable builds](../docs/portability.md) for Debian/Arch dependency examples and limitations.

## License

Original Simpleapps code is licensed under GPL-3.0-or-later (GNU GPL version 3 or any later version). See the repository’s LICENSE and COPYING files. Third-party components retain their own licenses and notices.
