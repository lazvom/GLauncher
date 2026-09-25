/* ============================================================================
   DEV-ONLY mock of the pywebview bridge.
   Loaded exclusively by preview.html so the UI can be viewed / screenshotted
   in a plain browser with sample data. The real app (index.html via main.py)
   never loads this file — it uses the genuine `pywebview.api` bridge.
   ========================================================================== */

const IMG = "https://launchercontent.mojang.com/v2/images/";
const PATCH_ENTRIES = [
  { title: "Minecraft: Java Edition 26.3", version: "26.3", type: "release", date: "2026-09-15T11:23:02.000Z", image: IMG + "dappledcamp540x540.jpg", contentPath: "javaPatchNotes/26-3.json", shortText: "Wilderness Bound is out now in Minecraft Java Edition! Pack your supplies and set off on an expedition into the dappled forest where the trails end and adventure begins." },
  { title: "Minecraft 26.3 Release Candidate 3", version: "26.3-rc-3", type: "snapshot", date: "2026-09-14T12:58:38.000Z", image: IMG + "26.3rc3540x540.jpg", contentPath: "javaPatchNotes/26-3-release-candidate-3.json", shortText: "They say that third time's the charm! Release Candidate 3 for 26.3 is here with yet another fix." },
  { title: "Minecraft 26.3 Release Candidate 2", version: "26.3-rc-2", type: "snapshot", date: "2026-09-11T10:34:40.000Z", image: IMG + "26.3rc2540x540.jpg", contentPath: "javaPatchNotes/26-3-release-candidate-2.json", shortText: "Today we are shipping a second release candidate for 26.3, the Wilderness Bound game drop." },
  { title: "Minecraft 26.3 Release Candidate 1", version: "26.3-rc-1", type: "snapshot", date: "2026-09-10T11:28:25.000Z", image: IMG + "26.3rc1540x540.jpg", contentPath: "javaPatchNotes/rc1.json", shortText: "Today we are shipping the first release candidate for 26.3, the Wilderness Bound game drop." },
  { title: "Minecraft 26.3 Pre-Release 3", version: "26.3-pre-3", type: "snapshot", date: "2026-09-08T13:04:44.000Z", image: IMG + "26.3pre3540x540.jpg", contentPath: "javaPatchNotes/pre3.json", shortText: "The road to release continues with pre-release 3! Today we're tackling another batch of bugs." },
  { title: "Minecraft 26.3 Pre-Release 2", version: "26.3-pre-2", type: "snapshot", date: "2026-09-04T11:54:52.000Z", image: IMG + "26.3pre2540x540.jpg", contentPath: "javaPatchNotes/pre2.json", shortText: "Two pre-releases in one week!? That's right! Now that we're in the pre-release phase." },
];

const INSTANCES = [
  { id: "i1", name: "Sakura SMP", mc_version: "1.21.1", loader: "fabric", loader_version: "0.16.5", installed: true, installed_version_id: "fabric-1.21.1" },
  { id: "i2", name: "Vanilla Creative", mc_version: "1.21.1", loader: "vanilla", loader_version: null, installed: true, installed_version_id: "1.21.1" },
  { id: "i3", name: "Moonlit Modpack", mc_version: "1.20.1", loader: "forge", loader_version: "47.3.0", installed: false, installed_version_id: null },
];

const HITS = [
  { project_id: "AANobbMI", title: "Sodium", description: "The fastest and most compatible rendering optimization mod for Minecraft.", downloads: 32100000, author: "jellysquid3", icon_url: "https://cdn.modrinth.com/data/AANobbMI/icon.png" },
  { project_id: "gvQqBUqZ", title: "Lithium", description: "No-compromises game logic & server optimization mod.", downloads: 21000000, author: "jellysquid3", icon_url: "https://cdn.modrinth.com/data/gvQqBUqZ/icon.png" },
  { project_id: "YL57xq9U", title: "Iris Shaders", description: "A modern shaders mod compatible with Sodium and OptiFine shaderpacks.", downloads: 18500000, author: "coderbot", icon_url: "https://cdn.modrinth.com/data/YL57xq9U/icon.png" },
  { project_id: "1IjD5062", title: "Continuity", description: "A Fabric mod that adds support for connected textures.", downloads: 6200000, author: "PepperCode1", icon_url: "https://cdn.modrinth.com/data/1IjD5062/icon.png" },
  { project_id: "mOgUt4GM", title: "Modmenu", description: "Adds a mod menu to view the list of mods you have installed.", downloads: 24000000, author: "Prospector", icon_url: "https://cdn.modrinth.com/data/mOgUt4GM/icon.png" },
  { project_id: "P7dR8mSH", title: "Fabric API", description: "Lightweight and modular API providing common hooks and intercompatibility.", downloads: 45000000, author: "modmuss50", icon_url: "https://cdn.modrinth.com/data/P7dR8mSH/icon.png" },
];

const ACCOUNTS = [
  { kind: "microsoft", username: "Sakura_Dev", uuid: "aaaa", active: true },
  { kind: "offline", username: "Steve", uuid: "bbbb", active: false },
];

const INSTALLED = {
  i1: [
    { project_id: "AANobbMI", version_id: "v1", filename: "sodium-fabric-0.5.11.jar", project_type: "mod", name: "Sodium", icon_url: "https://cdn.modrinth.com/data/AANobbMI/icon.png" },
    { project_id: "P7dR8mSH", version_id: "v2", filename: "fabric-api-0.102.jar", project_type: "mod", name: "Fabric API", icon_url: "https://cdn.modrinth.com/data/P7dR8mSH/icon.png" },
    { project_id: "shdr1", version_id: "v3", filename: "ComplementaryShaders_r5.2.2.zip", project_type: "shader" },
    { project_id: null, version_id: null, filename: "my-custom-tweak-v3-FINAL.jar", project_type: "mod" },
  ],
  i2: [], i3: [],
};

const delay = (ms) => new Promise((r) => setTimeout(r, ms));

window.pywebview = {
  api: {
    async list_instances() { await delay(120); return INSTANCES; },
    async loader_labels() { return { vanilla: "Vanilla", fabric: "Fabric", quilt: "Quilt", forge: "Forge", neoforge: "NeoForge" }; },
    async list_accounts() { await delay(80); return ACCOUNTS; },
    async get_account_skin_url() { return { url: null }; },
    async get_patch_notes() { await delay(200); return { entries: PATCH_ENTRIES }; },
    async get_patch_note_body() {
      await delay(150);
      return { body: "<p>Wilderness Bound is out now in Minecraft Java Edition! Pack your supplies and set off on an expedition into the dappled forest where the trails end and adventure begins.</p><h3>New Features</h3><ul><li>Added the Dappled Forest biome</li><li>New straw beds and campfire storytelling</li><li>Abandoned camps generate along old trails</li></ul><h3>Bug Fixes</h3><ul><li>Fixed a crash when placing poplar saplings</li><li>Improved fog rendering under shaders</li></ul>" };
    },
    async search_content(q, type, instanceId, offset = 0) {
      await delay(offset ? 350 : 200); // extra delay on "load more" pages so the loading row is visible in preview
      const base = type === "modpack" ? HITS.slice(0, 3) : HITS;
      const total = base.length * 6; // simulate a larger result set so infinite scroll has something to do
      const pool = Array.from({ length: total }, (_, i) => {
        const src = base[i % base.length];
        const page = Math.floor(i / base.length);
        return page === 0 ? src : { ...src, project_id: `${src.project_id}-p${page}`, title: `${src.title} (${page + 1})` };
      });
      return { hits: pool.slice(offset, offset + 20), total_hits: total };
    },
    async list_installed_content(id) { await delay(120); return { items: INSTALLED[id] || [] }; },
    async get_settings() { return { ram_min_mb: 2048, ram_max_mb: 6144, java_path: "", base_dir: "~/GlassLauncher" }; },
    async list_tasks() { return []; },
    async clear_finished_tasks() { return []; },
    async get_skin_profile() { return { error: "Skins and capes require a signed-in Microsoft account (offline accounts always show the default Steve/Alex model — that's normal, not a bug)." }; },
    async version_list() { return { versions: ["1.21.1", "1.21", "1.20.6", "1.20.4", "1.20.1"] }; },
    async loader_mc_versions() { return { versions: ["1.21.1", "1.21", "1.20.1"] }; },
    async loader_versions() { return { versions: ["(latest)", "0.16.5", "0.16.4"] }; },
    async create_instance(name, mc, loader) { const inst = { id: "new", name, mc_version: mc, loader, loader_version: null, installed: false }; INSTANCES.push(inst); return inst; },
    async start_install() { return { task_id: "t1" }; },
    async play(id) {
      const tid = "t_play_" + Date.now();
      const emit = (patch) => window.onTaskEvent && window.onTaskEvent(Object.assign({ id: tid, title: "Launch", kind: "launch", ref_id: id }, patch));
      setTimeout(() => emit({ status: "running", progress: null, detail: "Starting Minecraft…" }), 400);
      setTimeout(() => emit({ status: "done", progress: 1, detail: "Running" }), 1600);
      return { task_id: tid };
    },
    async delete_instance() { return { ok: true }; },
    async open_folder() { return { ok: true }; },
    async get_versions() { return { versions: [{ id: "vx", name: "Sodium 0.5.11", version_number: "0.5.11", version_type: "release", game_versions: ["1.21.1"], loaders: ["fabric"], date_published: "2026-08-01", project_id: "AANobbMI" }] }; },
    async get_modpack_versions() { return { versions: [{ id: "mp", name: "Moonlit 1.0", version_number: "1.0", version_type: "release", date_published: "2026-08-01" }] }; },
    async install_content() { return { task_id: "t3" }; },
    async install_modpack() { return { task_id: "t4" }; },
    async delete_installed_content() { return { ok: true }; },
    async add_offline_account(n) { ACCOUNTS.push({ kind: "offline", username: n, uuid: "z", active: false }); return ACCOUNTS; },
    async set_active_account(i) { ACCOUNTS.forEach((a, idx) => (a.active = idx === i)); return ACCOUNTS; },
    async remove_account(i) { ACCOUNTS.splice(i, 1); return ACCOUNTS; },
    async get_azure_client_id() { return ""; },
    async pick_skin_file() { return { path: null }; },
    async save_settings() { return {}; },
    async get_console_minimized() { return false; },
    async set_console_minimized() { return { ok: true }; },
    async window_minimize() { return {}; },
    async window_toggle_maximize() { return {}; },
    async window_close() { return {}; },
    async window_is_maximized() { return false; },
  },
};
