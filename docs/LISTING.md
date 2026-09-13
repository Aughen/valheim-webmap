# Store listings

Same package for both stores: `dist/ValheimWebMap-<version>.zip` from
`build.ps1`. Zip root holds `manifest.json`, `README.md`, `CHANGELOG.md`,
`icon.png` (256×256), `LICENSE`, `WebMap/`. Never any `map_data/`.

Screenshots in `docs/screenshots/` (1568 px wide, from the live server):

* `08-hero-3d` pine forest with birches, `03-base-3d` Vhauss base by the
  water, `09-pier-3d` pier house in the pines, `10-shore-3d` shore base,
  `04-players` Smokey longhouse with the Players tab, `05-stats`,
  `06-markers` portal hub with the Markers tab.
* `01-overview-2d` whole island with fog, `02-base-2d` base footprints with
  the tree and rock overlay, `07-events`.
* Clips: `valheim-webmap-3d-tour.gif` (2D to 3D, orbit, trees toggle) and
  `valheim-webmap-layers-markers.gif` (overlay toggle, marker jump, 3D).
Upload the 3D ones first; stores show the first image as the cover.

## Thunderstore

* Namespace: your team name. Package name: `ValheimWebMap`.
* Categories: Mods, Server-side, Utility, Deep North Update.
* Description (from `manifest.json`, 250 char max):

  > Live web map for your dedicated server. 1 m/px tiles, 3D view with the game's own models, fog of war, players, bases, portals, stats. Clients need no mods.

* Website: GitHub repo URL.
* Dependencies: `denikson-BepInExPack_Valheim-5.4.2350` (in manifest).
* Page body: README.md renders as-is.

## Nexus Mods

Name: **Valheim WebMap**

Summary (255 char max):

> Live web map for dedicated servers. 1 m/px tiles with terraforming and every building, 3D view built from the game's own models, fog of war, live players, bases, portals, stats. Server-side only. Players install nothing.

Category: Utilities. Tags: Server-side, Map, Utility, Multiplayer.

Description (BBCode):

```
[size=5][b]Valheim WebMap[/b][/size]

Server-side mod. Publishes a live web map of your world at http://your_ip:3000. Players install nothing. Dedicated server only.

[b]Map at 1 m per pixel.[/b] Seven zoom levels. Terraforming, roads, farms, forests. Every placed piece drawn as a footprint in its material colour.

[b]3D view.[/b] Same world with the game's own models: walls, roofs, portals, ruins, trees, rocks, boats. Placed exactly as built.

[b]Fog of war.[/b] Black until someone walks there. Shared across all players. No override for viewers.

[b]Live.[/b] Players with facing and health, pings, chat pins, event feed, per-player stats: playtime, deaths, distance, portal trips.

[b]Markers.[/b] Portals with tags and links, tombstones, player bases, boats, carts, your own markers.json. Boss altars, dungeons, traders and the world seed are never published. No spoilers.

[b]Install[/b]
[list=1]
[*]BepInEx on the server. Copy the WebMap folder to BepInEx/plugins/WebMap.
[*]Start once. Edit BepInEx/config/com.valheimwebmap.server.cfg. Restart.
[*]Open port 3000. Share http://your_ip:3000.
[/list]
Docker (lloesche/valheim-server): plugins live under /opt/valheim/bepinex/BepInEx/plugins. Publish -p 3000:3000/tcp.

[b]Textures[/b]
The server cannot read textures, so 3D models start flat-coloured. The mod pulls the textures out of your own server's game files in the background, once per game version, on Windows, Linux and Docker. Game assets are never redistributed. Steps in the README.

[b]Requirements[/b]
BepInExPack Valheim 5.4.2350 or newer. Valheim 1.0.

[b]Source[/b]
GitHub: <repo url>. MIT licence.
```

## Version bump checklist

1. `WebMap/WebMap.cs` `VERSION`, `WebMap/WebMap.csproj` `<Version>`, `manifest.json` `version_number`.
2. `CHANGELOG.md` entry.
3. `.\build.ps1` → zip in `dist/`.
4. Upload zip to Thunderstore. Upload zip to Nexus, paste CHANGELOG entry as version notes.
5. `git tag v<version>` and push.
