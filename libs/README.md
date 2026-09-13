# libs

Build inputs. `build.ps1` / `build.sh` fill this folder:

* `libs/valheim/` — game assemblies copied from the dedicated server
  (`valheim_server_Data/Managed`). Publicized at build time by
  Krafs.Publicizer.
* `libs/BepInEx/` — BepInEx 5 downloaded on first build.
* `websocket-sharp.dll` — shipped with the plugin.

Nothing here except `websocket-sharp.dll` is committed.
