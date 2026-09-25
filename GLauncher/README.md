# GLauncher

A custom Minecraft launcher. The UI is a real HTML/CSS/JS frontend running in
a native window (via [pywebview](https://pywebview.flowrl.com/)), built
around Apple's *Designing Fluid Interfaces* principles - genuine glass
materials, a real critically-damped spring physics engine (not CSS
transitions), 1:1 gesture tracking, and interruptible motion. The backend
(`core/`) - installing versions, downloading content, managing accounts and
background tasks - is plain Python and untouched by any of that; the UI is
just a window onto it.

## UI (Moonlit Sakura redesign)

The interface is organised around a **floating glass dock** pinned to the
bottom of the window, visible everywhere, holding three things:

- **Account picker** (left) - your avatar + name; opens the account switcher.
- **Instance picker** (centre) - the one active instance everything else is
  scoped to; opens a list to switch, plus **+ New Instance**.
- **Play** (right) - launches the active instance; its label tracks the real
  state (Play → Installing… → Starting… → Playing).

Four top tabs:

- **Home** - live **Minecraft patch notes** pulled straight from Mojang's
  official feed, laid over the night cherry-blossom background. Click any
  card to read the full notes in a drag-dismissible sheet.
- **Content** - install **mods / modpacks / shaders / resource packs** from
  Modrinth for the active instance.
- **Manage** - delete **instances / mods / shaders / resource packs**.
- **Skins** - 3D skin + cape preview, upload, and cape switching.

Settings live behind the gear icon (top-right); the download icon next to it
opens the Activity sheet (all running/finished installs). The dark glass,
moonlit-blue + sakura-pink palette, and every animation follow the design
skill in `SKILL.md`.

### Previewing the UI in a browser

The launcher is a desktop app, but `web/preview.html` loads the exact same
UI with a mock data bridge (`web/mock-api.js`) so it can be opened in any
browser for design review. `?tab=home|content|manage|skins` selects a tab.
Neither file is used by the real app (`main.py` → `index.html`).

## Why a web UI for a desktop app

Native toolkits like Tkinter can't do real backdrop blur, spring physics, or
smooth pointer-tracked dragging - there's no way to "translate" those
principles into Tk widgets without losing what makes them work. So the UI
here is HTML/CSS/JS, same as a website, just rendered in a plain native
window instead of a browser tab. No Node/React/build step - `web/` is loaded
directly, no bundler involved.

## Architecture

```
main.py          - opens the native window (pywebview), points it at web/
api.py           - the only bridge between JS and Python: exposes core/ as
                    `pywebview.api.*` methods callable from JS, and pushes
                    live task/console updates into the page
core/            - the actual engine (unchanged): version installs, Modrinth
                    content, accounts, background tasks
web/
  index.html     - page shell
  style.css      - design tokens, glass materials, typography
  spring.js      - the spring physics engine (position/velocity/damping,
                    retargetable at any instant, no external library)
  app.js         - all UI logic: the floating dock (account / instance /
                    play), four tabs (Home patch notes, Content, Manage,
                    Skins), the drag-dismissible sheet component, popovers,
                    task/console event routing
  preview.html   - browser preview entry (dev only)
  mock-api.js    - sample-data stand-in for the pywebview bridge (dev only)
```

**What's genuinely gesture-driven** (not just re-themed): the bottom sheets
used for "New Instance", the mod/modpack version picker, and the account
dialogs can be dragged by their grabber handle - 1:1 with the pointer,
rubber-banding if you drag past fully-open, and released with real momentum
(a fast flick dismisses it even if you didn't drag far; a slow drag snaps
back unless you passed roughly a third of the way). Grab a sheet while it's
still animating and it reverses instantly from wherever it is - no jump,
because a spring's position and velocity are exactly what they are the
moment you interrupt it, not a fixed keyframe.

**What stayed simple on purpose**: page switching, page cross-fades, and
list re-renders use plain state changes rather than gesture physics - they
aren't things you drag, so a spring there would just be decoration, not
function. The nav pill and the content-type segmented control *do* use the
spring engine, since they're a natural fit for it (see `spring.js` /
`makeSegmented`).

## 1. Install dependencies

```bash
pip install -r requirements.txt
```

Requires **Python 3.10+** and a working **Java** installation (the vanilla
launcher lib will tell you if a version is missing when you first launch
that version).

`pywebview` renders through your OS's native web engine - Edge WebView2 on
Windows and WebKit on macOS are normally already present. On **Linux** you
may need to install WebKitGTK first (e.g. `sudo apt install
python3-gi gir1.2-webkit2-4.1` on Debian/Ubuntu, or the equivalent for your
distro) - see [pywebview's install docs](https://pywebview.flowrl.com/guide/installation.html)
if `python main.py` can't find a renderer.

## 2. Run it

```bash
python main.py
```

All data (instances, downloaded versions, accounts) is stored in a `data`
folder next to the launcher itself, not in your home directory - the whole
thing is portable, so the folder containing `main.py` (or the packaged `.exe`)
can be moved, copied, or zipped up as one self-contained unit.

## 3. Accounts

Accounts live in the **bottom-left of the sidebar** now (not a separate
tab) - click your avatar/name to open a switcher listing every signed-in
account, with **+ Offline account** / **+ Microsoft account** at the bottom.
Offline accounts show a grey silhouette; Microsoft accounts show a real 2D
render of your actual skin.

Microsoft account tokens are refreshed automatically before every launch -
so signed-in sessions stay valid indefinitely without ever needing a manual
re-login. (If you were seeing skins fail to load or servers refuse to let
you join after being signed in for a while, that was a stale-token issue -
the token was never being refreshed at all before, so it would eventually
expire and quietly break both of those; it's what a re-login was actually
fixing.)

- **Offline account**: just pick a username. Fine for singleplayer/LAN and
  offline-mode servers. Not valid for realms or servers that require
  Microsoft auth. Always shows the default Steve/Alex model - that's normal,
  since offline mode has no real Mojang profile to pull a skin from.
- **Microsoft account**: Mojang/Microsoft require every third-party launcher
  to use its **own Azure app registration** - there's no legitimate way
  around this (using another app's client ID, e.g. a game console's or one
  someone else registered, means impersonating an app you don't own, which
  breaks Microsoft's and Mojang's terms and puts that app's quota/standing
  at risk for people who never agreed to share it). Sign-in here uses
  **device code flow** - no redirect URI, no local server, nothing to
  paste. One-time setup:
  1. Go to https://portal.azure.com → **App registrations** → **New
     registration**.
  2. Any name is fine. Under **Supported account types**, pick "Personal
     Microsoft accounts only".
  3. Open the new app → **Authentication** → **Advanced settings** → turn on
     **"Allow public client flows"**. (No redirect URI needed at all.)
  4. Copy the **Application (client) ID** from the app's Overview page.
  5. Paste it into `core/settings.py` as `DEFAULT_AZURE_CLIENT_ID = "..."`
     (there's a comment right above it) - this is the only place you enter
     it; there's no field for it in the UI at all.
  6. In the launcher: account switcher → **+ Microsoft account** →
     **Get sign-in code**. You'll see a short code - open the shown link
     (microsoft.com/link) on any device, enter the code, sign in. The
     launcher finishes automatically.

  `DEFAULT_AZURE_CLIENT_ID` should only ever be an app **you** registered -
  see the note in that file. If you'd rather not edit the source, leave it
  blank; the sign-in sheet will tell you it's unconfigured instead of
  silently failing.

## 4. Creating an instance

Instances tab → **+ New Instance** opens a drag-dismissible sheet from the
bottom - pick a name, mod loader, and Minecraft version (toggle "Show
snapshots" / "Show old versions" to reveal more) → **Create & Install**. The
sheet closes immediately and the install runs in the background with
progress right on the new instance's card - you're free to start another
instance, browse content, or launch something else while it installs.

## 5. Installing content

Content Browser tab → **Browse** mode opens straight to Modrinth's top
results for the selected instance and content type - no need to search
first. Pick a content type (Mods / Modpacks / Shaders / Resource Packs) or
switch instances and results refresh automatically; type something and hit
search (or Enter) to narrow it down. **Install** → pick the exact version
from the sheet that slides up (large lists render in small batches with a
filter box, so a modpack with hundreds of versions doesn't lag). Progress
shows inline under the result you clicked - install as many things as you
like back to back, they all run concurrently. Modpacks install as a
brand-new instance with the correct loader detected automatically - and
every mod/resourcepack/shader it actually installed gets identified by file
hash against Modrinth's database and registered as installed content for
that new instance too. Hash-based means this works whether the pack listed
a mod in its tracked download manifest or just bundled it directly as a raw
file (a common way modpacks ship things like Sodium) - either way, browsing
Mods for that instance afterward correctly shows it as "✓ Installed"
instead of offering to download it again.

- **Already installed?** The result shows a disabled "✓ Installed" state
  instead of an Install button - no accidental re-downloads. This updates
  live: delete something from the Manage tab (or even delete the file by
  hand outside the app) and the matching Browse result flips back to
  "Install" on its own within a few seconds - no need to search again.
- **Mod dependencies** install automatically if they're not already present
  (e.g. a mod that needs Fabric API pulls it in too); anything already
  installed is skipped rather than re-downloaded.
- **Mods default to release versions only** - beta/alpha builds are hidden
  unless you check "Show beta/alpha" next to the search box.

**Manage mode** (the toggle next to the page title) lists everything
currently installed for the selected instance and content type, with a
**Delete** button per item - removes the actual file and un-tracks it, so
that content shows back up as installable (not stuck on "already
installed") the next time you search for it.

## 6. Playing

Instances tab → **Play**. The button itself tracks what's actually
happening: **Installing...** while it's not installed yet and needs to be,
**Starting...** for the brief moment the game is booting, then **Playing**
(and disabled) for as long as the game is actually running - not just until
the launch kicks off, the whole session - and back to **▶ Play** the moment
it exits. This state survives switching tabs and coming back, so you can't
lose track of which instance is currently running. A console panel slides
in showing live game output, and closes itself automatically a couple
seconds after the game exits (showing the exit code first). You can hit Play
on multiple instances at once - installs into the same shared version store
are automatically queued rather than running at the literal same instant,
which avoids a rare "wrong checksum" download error two simultaneous
installs could otherwise cause by writing the same shared file at once.

**Video settings and your multiplayer server list are shared across every
instance.** Minecraft doesn't have a native way to keep some files
per-instance (mods, saves, config) and others shared (options.txt,
servers.dat) at the same time, so this launcher copies those two files in
from `shared/` right before launch, and copies them back after the game
exits - meaning changing your settings or adding a server in any instance
carries over to all the others the next time each one launches. Everything
else (mods, worlds, resource packs, per-mod config) stays fully
per-instance as usual.

## 7. Activity tab

Shows every install/download/launch currently running or recently finished,
with live progress, in one place. "Clear finished" tidies up the list.

## 8. Skins tab

Requires an active **Microsoft account** (offline accounts always show the
default Steve/Alex model - that's normal, not a bug, since offline mode has
no real Mojang profile to fetch a skin from). Shows a real **3D preview**
of your current skin and equipped cape together (rendered live via
[skinview3d](https://github.com/bs-community/skinview3d), loaded from a
CDN - falls back to a flat 2D texture automatically if that can't load,
e.g. no internet), lets you pick a local PNG to upload (with a Classic/Slim
model toggle) or reset back to default, and shows every cape you own as a
clickable grid - click one to equip it, or "No cape" to go capeless. Uses
Mojang's own Minecraft Services API directly with the same access token
used to launch the game, so changes apply immediately and show up in-game
right away.

**If skins weren't showing in-game before:** this was a real bug, now
fixed - Mojang's profile API returns your account UUID without dashes, and
passing that straight through as the game's `--uuid` launch argument could
cause the game's skin/cape lookup to silently fail even though sign-in
worked fine. The launcher now formats it correctly, and automatically
repairs any already-signed-in account with the broken format the next time
it starts (no need to sign in again).

## Notes / limitations

- Modpack support covers Modrinth's `.mrpack` format. CurseForge modpacks
  aren't supported (CurseForge requires a paid API key for automated
  downloads).
- Shaders require a shader-supporting mod (e.g. Iris) to actually apply
  in-game - this launcher installs the shader file into `shaderpacks/`, but
  doesn't install Iris/OptiFine for you unless you search for and install it
  as a "mod" too.
- The account switcher's avatar for Microsoft accounts is rendered
  entirely locally - it crops the actual face straight out of your real,
  current Mojang skin texture onto a small canvas. No third party involved
  at all: NameMC's own image renderer (found directly in their page source,
  `s.namemc.com/3d/skin/body.png`) turns out to need NameMC's own internal
  skin-hash ID, which isn't derivable from the Mojang UUID this launcher has
  without scraping their HTML - too fragile to build a permanent feature on.
  Cropping the real texture directly gets the same practical result (a small
  icon that always matches your actual skin) without that dependency.
- Everything in `web/` runs on the browser engine your OS provides via
  pywebview, not Chrome specifically - backdrop-filter blur, spring-driven
  motion, and pointer events all need a reasonably current engine (WebView2,
  recent WebKit). Very old OS builds may render the glass materials as flat
  colors instead of blurred.
