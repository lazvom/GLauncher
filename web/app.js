import { Spring, project, rubberband, VelocityTracker } from "./spring.js";

/* ========================================================================
   DOM + API helpers
   ======================================================================== */

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k === "style" && typeof v === "object") Object.assign(node.style, v);
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) node.setAttribute(k, v);
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

/* ---- inline icon set (lucide-style, no emoji) ---- */
const ICONS = {
  home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.2V21h14V9.2"/>',
  box: '<path d="M21 8 12 3 3 8v8l9 5 9-5V8z"/><path d="m3 8 9 5 9-5"/><path d="M12 13v8"/>',
  trash: '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M6 6l1 14h10l1-14"/><path d="M10 11v6M14 11v6"/>',
  palette: '<circle cx="12" cy="12" r="9"/><circle cx="8.5" cy="9.5" r="1"/><circle cx="15.5" cy="9.5" r="1"/><circle cx="9" cy="15" r="1"/><path d="M12 21a3 3 0 0 0 0-6"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 6.5 19l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 3 13.6a2 2 0 1 1 0-4h.1A1.6 1.6 0 0 0 5 6.5l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.6 1.6 0 0 0 10.4 3H10a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8v.4a1.6 1.6 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z"/>',
  activity: '<path d="M12 3v12"/><path d="m7 11 5 5 5-5"/><path d="M4 20h16"/>',
  play: '<path d="M6 4.5v15l13-7.5z"/>',
  chevron: '<path d="m6 9 6 6 6-6"/>',
  chevronUp: '<path d="m6 15 6-6 6 6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  winMinimize: '<path d="M5 12h14"/>',
  winMaximize: '<rect x="5" y="5" width="14" height="14" rx="1.5"/>',
  winRestore: '<path d="M8 3h9a2 2 0 0 1 2 2v9"/><rect x="3" y="8" width="12" height="12" rx="1.5"/>',
  folder: '<path d="M4 5h5l2 2h9v11H4z"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
  cube: '<path d="M21 8 12 3 3 8v8l9 5 9-5V8z"/><path d="m3 8 9 5 9-5"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  sparkle: '<path d="M12 3l1.8 4.6L18 9l-4.2 1.4L12 15l-1.8-4.6L6 9l4.2-1.4z"/>',
};
function icon(name) {
  const wrap = document.createElement("span");
  wrap.style.display = "inline-flex";
  wrap.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ""}</svg>`;
  return wrap.firstElementChild;
}

let apiReady = new Promise((resolve) => {
  if (window.pywebview) resolve();
  else window.addEventListener("pywebviewready", resolve, { once: true });
});

async function api(method, ...args) {
  await apiReady;
  try {
    return await window.pywebview.api[method](...args);
  } catch (e) {
    console.error(`api.${method} failed:`, e);
    return { error: String(e) };
  }
}

function fmtDownloads(n) {
  if (!n) return "";
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k downloads` : `${n} downloads`;
}
function fmtDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return (iso || "").slice(0, 10);
  }
}

/* ========================================================================
   Toasts
   ======================================================================== */
const toastStack = document.getElementById("toast-stack");
function toast(message, kind = "error") {
  const node = el("div", { class: `toast ${kind === "success" ? "success" : ""}`, "data-testid": "toast" }, message);
  toastStack.append(node);
  const spring = new Spring({
    position: 120, target: 0, damping: 0.86, response: 0.4,
    onUpdate: (x) => {
      node.style.transform = `translateX(${x}%)`;
      node.style.opacity = String(Math.min(1, 1 - Math.abs(x) / 90));
    },
  });
  spring.setTarget(0);
  const dismiss = () => {
    spring.setTarget(140, { velocity: spring.velocity });
    setTimeout(() => node.remove(), 500);
  };
  const timer = setTimeout(dismiss, 4500);
  node.addEventListener("pointerdown", () => { clearTimeout(timer); dismiss(); });
}

/* ========================================================================
   Drag-dismissible sheet (the genuine gesture surface)
   ======================================================================== */
class Sheet {
  constructor(root) {
    this.grabber = el("div", { class: "sheet-grabber" });
    this.headerEl = el("div", { class: "sheet-header" });
    this.bodyEl = el("div", { class: "sheet-body" });
    this.footerEl = el("div", { class: "sheet-footer" });
    this.sheetEl = el("div", { class: "sheet", "data-testid": "sheet" }, [this.grabber, this.headerEl, this.bodyEl, this.footerEl]);
    this.scrim = el("div", { class: "scrim" });
    root.append(this.scrim, this.sheetEl);
    this.height = 400;
    this.spring = new Spring({ position: this.height, target: this.height, damping: 1, response: 0.38, onUpdate: (y) => this._render(y) });
    this.velocityTracker = new VelocityTracker();
    this._dragging = false;
    this._onMove = this._onPointerMove.bind(this);
    this._onUp = this._onPointerUp.bind(this);
    this.grabber.addEventListener("pointerdown", this._onPointerDown.bind(this));
    this.scrim.addEventListener("pointerdown", () => this.close());
  }
  _render(y) {
    const clamped = Math.max(0, y);
    this.sheetEl.style.transform = `translate(-50%, ${y < 0 ? -rubberband(-y, this.height) : clamped}px)`;
    const openness = this.height > 0 ? Math.max(0, 1 - clamped / this.height) : 0;
    this.scrim.style.background = `rgba(0,0,0,${0.55 * openness})`;
    this.scrim.classList.toggle("visible", openness > 0.02);
  }
  open(buildFn) {
    this.footerEl = this.footerEl || el("div", { class: "sheet-footer" });
    if (!this.footerEl.isConnected) this.sheetEl.append(this.footerEl);
    this.headerEl.replaceChildren();
    this.bodyEl.replaceChildren();
    this.footerEl.replaceChildren();
    buildFn({ header: this.headerEl, body: this.bodyEl, footer: this.footerEl, close: () => this.close() });
    requestAnimationFrame(() => { this.spring.jumpTo(this._dismissTarget()); this.spring.setTarget(0); });
  }
  _dismissTarget() {
    const measured = this.sheetEl.offsetHeight || this.height || 400;
    this.height = measured;
    return measured + 40;
  }
  close() { this.spring.setTarget(this._dismissTarget(), { velocity: this.spring.velocity }); }
  _onPointerDown(e) {
    this._dragging = true;
    this._startClientY = e.clientY;
    this._startPos = this.spring.position;
    this.spring.stop();
    this.velocityTracker.reset();
    this.velocityTracker.push(this.spring.position);
    try { this.grabber.setPointerCapture(e.pointerId); } catch {}
    window.addEventListener("pointermove", this._onMove);
    window.addEventListener("pointerup", this._onUp);
  }
  _onPointerMove(e) {
    if (!this._dragging) return;
    const pos = this._startPos + (e.clientY - this._startClientY);
    this.spring.jumpTo(pos);
    this.velocityTracker.push(pos);
  }
  _onPointerUp() {
    if (!this._dragging) return;
    this._dragging = false;
    window.removeEventListener("pointermove", this._onMove);
    window.removeEventListener("pointerup", this._onUp);
    const v = this.velocityTracker.velocity();
    const projected = this.spring.position + project(v);
    const shouldClose = projected > this.height * 0.35 || v > 700;
    this.spring.setTarget(shouldClose ? this._dismissTarget() : 0, { velocity: v });
  }
}
const sheet = new Sheet(document.getElementById("sheet-root"));

/* ========================================================================
   Anchored scale+fade popover (opens above a dock button)
   ======================================================================== */
class Popover {
  constructor(root) { this.root = root; this.el = null; this.anchorEl = null; this._onClose = null; this._outsideHandler = this._onOutsideClick.bind(this); }
  isOpen() { return !!this.el; }
  open(anchorEl, buildFn, onClose) {
    this.close();
    this._onClose = onClose || null;
    this.anchorEl = anchorEl;
    const node = el("div", { class: "popover", "data-testid": "popover" });
    buildFn(node);
    this.root.append(node);
    this.el = node;
    const rect = anchorEl.getBoundingClientRect();
    node.style.left = `${rect.left}px`;
    node.style.bottom = `${window.innerHeight - rect.top + 10}px`;
    node.style.transformOrigin = "bottom left";
    const spring = new Spring({
      position: 0, target: 1, damping: 0.82, response: 0.3,
      onUpdate: (v) => { node.style.transform = `scale(${0.9 + 0.1 * v})`; node.style.opacity = String(Math.max(0, Math.min(1, v))); },
    });
    spring.setTarget(1);
    setTimeout(() => document.addEventListener("pointerdown", this._outsideHandler), 0);
  }
  // Clicks on the button that opens this popover are ignored here — that button
  // already toggles open/close itself. Without this, a pointerdown on the dock
  // button would close the popover a beat before its own click handler runs,
  // so the handler would see it as "already closed" and reopen it immediately
  // (the popover looked like it wouldn't close, or kept reopening).
  _onOutsideClick(e) {
    if (!this.el) return;
    if (this.el.contains(e.target)) return;
    if (this.anchorEl && this.anchorEl.contains(e.target)) return;
    this.close();
  }
  close() {
    if (!this.el) return;
    document.removeEventListener("pointerdown", this._outsideHandler);
    const node = this.el;
    this.el = null;
    this.anchorEl = null;
    const onClose = this._onClose;
    this._onClose = null;
    if (onClose) onClose();
    const spring = new Spring({
      position: 1, target: 0, damping: 0.88, response: 0.2,
      onUpdate: (v) => { node.style.transform = `scale(${0.9 + 0.1 * v})`; node.style.opacity = String(Math.max(0, Math.min(1, v))); },
      onSettle: () => node.remove(),
    });
    spring.setTarget(0);
  }
}
const accountPopover = new Popover(document.getElementById("account-popover-root"));
const instancePopover = new Popover(document.getElementById("instance-popover-root"));

/* ========================================================================
   Inline progress row
   ======================================================================== */
function progressRow() {
  const status = el("div", { class: "status" });
  const fill = el("div", { class: "progress-fill" });
  const row = el("div", { class: "inline-progress" }, [status, el("div", { class: "progress-track" }, fill)]);
  return {
    node: row,
    show() { row.classList.add("visible"); },
    hide() { row.classList.remove("visible"); },
    update(text, progress, isError = false) {
      status.textContent = text || "";
      status.classList.toggle("error", !!isError);
      if (progress === null || progress === undefined) fill.classList.add("indeterminate");
      else { fill.classList.remove("indeterminate"); fill.style.width = `${Math.max(0, Math.min(1, progress)) * 100}%`; }
    },
  };
}

/* ========================================================================
   Segmented control (spring-driven indicator)
   ======================================================================== */
const segmentedRepositioners = [];
function segmented(container, onChange) {
  const items = [...container.querySelectorAll(".seg-item")];
  let indicator = container.querySelector(".seg-indicator");
  if (!indicator) { indicator = el("div", { class: "seg-indicator" }); container.prepend(indicator); }
  const spring = new Spring({ damping: 0.86, response: 0.28, onUpdate: (v) => { indicator.style.transform = `translateX(${v}px)`; } });
  function place(item, animate = true) {
    if (!item) return;
    const w = item.offsetWidth;
    if (!w) return;
    indicator.style.width = `${w}px`;
    const x = item.offsetLeft;
    animate ? spring.setTarget(x) : spring.jumpTo(x);
  }
  items.forEach((it) => it.addEventListener("click", () => {
    if (it.classList.contains("disabled")) return;
    items.forEach((i) => i.classList.remove("active"));
    it.classList.add("active");
    place(it);
    onChange(it.dataset.val);
  }));
  const reposition = () => place(items.find((i) => i.classList.contains("active")), false);
  requestAnimationFrame(reposition);
  window.addEventListener("resize", reposition);
  segmentedRepositioners.push(reposition);
  return reposition;
}

/* ========================================================================
   Task + console event routing
   ======================================================================== */
const taskSubscribers = new Map();
const allTasks = new Map();

window.onTaskEvent = (task) => {
  allTasks.set(task.id, task);
  const fn = taskSubscribers.get(task.id);
  if (fn) fn(task);
  if (task.status !== "running") taskSubscribers.delete(task.id);
  renderActivityBadge();
};
function renderActivityBadge() {
  const badge = document.getElementById("activity-badge");
  const running = [...allTasks.values()].filter((t) => t.status === "running").length;
  badge.style.display = running ? "grid" : "none";
  badge.textContent = String(running);
}

let consoleMinimizedPref = false;
api("get_console_minimized").then((v) => { consoleMinimizedPref = v === true; });

const consolePanels = new Map();
window.onGameOutput = (instanceId, text) => {
  let panel = consolePanels.get(instanceId);
  if (!panel) panel = openConsolePanel(instanceId);
  panel.logEl.textContent += text;
  panel.logEl.scrollTop = panel.logEl.scrollHeight;
};
window.onGameExit = (instanceId, exitCode) => {
  runningInstances.delete(instanceId);
  installingInstances.delete(instanceId);
  refreshDockPlay();
  if (currentPage === "manage") loadManage();
  const panel = consolePanels.get(instanceId);
  if (!panel) return;
  const codeText = exitCode === null || exitCode === undefined ? "" : ` (exit code ${exitCode})`;
  panel.logEl.textContent += `\n[Game closed${codeText} — closing automatically]\n`;
  panel.logEl.scrollTop = panel.logEl.scrollHeight;
  setTimeout(() => closeConsolePanel(instanceId), 2500);
};
function repositionConsolePanels() {
  const dock = document.getElementById("dock");
  if (!dock) return;
  const rect = dock.getBoundingClientRect();
  const gap = 14;
  let stackBottom = window.innerHeight - rect.top + gap;
  for (const panel of consolePanels.values()) {
    panel.node.style.left = `${rect.left + rect.width / 2}px`;
    panel.node.style.bottom = `${stackBottom}px`;
    stackBottom += panel.node.offsetHeight + gap;
  }
}
window.addEventListener("resize", repositionConsolePanels);
function openConsolePanel(instanceId) {
  const logEl = el("div", { class: "console-log" });
  const minimizeBtn = el("button", { class: "console-minimize-btn", title: "Minimize", "data-testid": "console-minimize-btn" });
  const setMinimizeIcon = (minimized) => { minimizeBtn.replaceChildren(icon(minimized ? "chevronUp" : "chevron")); };
  const node = el("div", { class: "console-panel" }, [
    el("div", { class: "console-header" }, [document.createTextNode("Game output"), minimizeBtn]),
    logEl,
  ]);
  node.style.transform = "translateX(-50%)";
  document.getElementById("console-root").append(node);
  const spring = new Spring({
    position: 60, target: 0, damping: 0.85, response: 0.4,
    onUpdate: (y) => { node.style.transform = `translateX(-50%) translateY(${y}px)`; node.style.opacity = String(1 - Math.min(1, Math.abs(y) / 60)); },
  });
  spring.jumpTo(60); spring.setTarget(0);
  const panel = { node, logEl, spring, minimized: consoleMinimizedPref };
  const applyMinimized = () => {
    node.classList.toggle("minimized", panel.minimized);
    setMinimizeIcon(panel.minimized);
    setTimeout(repositionConsolePanels, 260); // after the height transition settles
  };
  applyMinimized();
  minimizeBtn.addEventListener("click", () => {
    panel.minimized = !panel.minimized;
    applyMinimized();
    consoleMinimizedPref = panel.minimized;
    api("set_console_minimized", panel.minimized);
  });
  consolePanels.set(instanceId, panel);
  repositionConsolePanels();
  return panel;
}
function closeConsolePanel(instanceId) {
  const panel = consolePanels.get(instanceId);
  if (!panel) return;
  panel.spring.setTarget(60, { velocity: panel.spring.velocity });
  setTimeout(() => { panel.node.remove(); consolePanels.delete(instanceId); repositionConsolePanels(); }, 400);
}

/* ========================================================================
   Global launcher state
   ======================================================================== */
const state = { instances: [], activeId: null, loaderLabels: {}, accounts: [] };
const runningInstances = new Set();
const installingInstances = new Set();
const launching = new Set(); // guards the click→api gap so Play can't double-fire

/* Soft launch chime (WebAudio, no asset) + gentle button bloom, fired the
   moment the game actually starts. */
let _audioCtx = null;
function playChime() {
  try {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    _audioCtx = _audioCtx || new AC();
    const ctx = _audioCtx;
    if (ctx.state === "suspended") ctx.resume();
    const now = ctx.currentTime;
    const master = ctx.createGain();
    master.gain.value = 0.9;
    master.connect(ctx.destination);
    // two soft sine notes (E5 → B5) with a quick attack and long, gentle tail
    [[659.25, 0], [987.77, 0.11]].forEach(([freq, t]) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, now + t);
      gain.gain.exponentialRampToValueAtTime(0.13, now + t + 0.03);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + t + 0.9);
      osc.connect(gain).connect(master);
      osc.start(now + t);
      osc.stop(now + t + 1.0);
    });
  } catch {}
}
function bloomPlay() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  dockPlayBtn.classList.remove("bloom");
  void dockPlayBtn.offsetWidth; // restart the animation if it's mid-flight
  dockPlayBtn.classList.add("bloom");
  dockPlayBtn.addEventListener("animationend", () => dockPlayBtn.classList.remove("bloom"), { once: true });
}
function celebrateLaunch() { playChime(); bloomPlay(); }

function activeInstance() { return state.instances.find((i) => i.id === state.activeId) || null; }

async function refreshInstances() {
  const [instances, labels] = await Promise.all([api("list_instances"), api("loader_labels")]);
  state.instances = instances || [];
  state.loaderLabels = labels || {};
  if (!state.instances.find((i) => i.id === state.activeId)) state.activeId = state.instances[0]?.id || null;
  refreshDockInstance();
  refreshDockPlay();
  if (currentPage === "content") updateContentTypeAvailability();
  return state.instances;
}
function setActive(id) {
  state.activeId = id;
  refreshDockInstance();
  refreshDockPlay();
  if (currentPage === "content") { updateContentTypeAvailability(); searchContent(); }
  if (currentPage === "manage") loadManage();
}

/* ========================================================================
   Top navigation + page routing
   ======================================================================== */
const NAV = [
  { page: "home", label: "Home", icon: "home" },
  { page: "content", label: "Content", icon: "box" },
  { page: "manage", label: "Manage", icon: "trash" },
  { page: "skins", label: "Skins", icon: "palette" },
];
const navItems = [...document.querySelectorAll(".nav-item")];
navItems.forEach((item) => {
  const def = NAV.find((n) => n.page === item.dataset.page);
  item.append(icon(def.icon), document.createTextNode(def.label));
  item.addEventListener("click", () => showPage(item.dataset.page));
});
const navPill = document.getElementById("nav-pill");
const navPillSpring = new Spring({ damping: 0.85, response: 0.32, onUpdate: (x) => { navPill.style.transform = `translateX(${x}px)`; } });
function movePill(item, animate = true) {
  navPill.style.width = `${item.offsetWidth}px`;
  animate ? navPillSpring.setTarget(item.offsetLeft) : navPillSpring.jumpTo(item.offsetLeft);
}

let currentPage = "home";
const pageEls = Object.fromEntries([...document.querySelectorAll(".page")].map((p) => [p.id.replace("page-", ""), p]));
const pageLoaders = {};

function showPage(name) {
  currentPage = name;
  document.body.classList.toggle("on-home", name === "home");
  for (const [key, node] of Object.entries(pageEls)) node.classList.toggle("active", key === name);
  const activeItem = navItems.find((i) => i.dataset.page === name);
  navItems.forEach((i) => i.classList.toggle("active", i.dataset.page === name));
  if (activeItem) movePill(activeItem);
  if (pageLoaders[name]) pageLoaders[name]();
  requestAnimationFrame(() => segmentedRepositioners.forEach((fn) => fn()));
}
window.addEventListener("resize", () => {
  const active = navItems.find((i) => i.classList.contains("active"));
  if (active) movePill(active, false);
});

/* ========================================================================
   Titlebar (native Win32 chrome - see core/winchrome.py)
   Minimize/maximize/close all go straight to the real Win32 API on the
   window's actual handle (core/winchrome.py), so Windows performs its own
   native animations for these - nothing is animated here in the page.
   ======================================================================== */
const winMinimizeBtn = document.getElementById("win-minimize");
const winMaximizeBtn = document.getElementById("win-maximize");
const winCloseBtn = document.getElementById("win-close");
const setMaximizeIcon = (maximized) => { winMaximizeBtn.replaceChildren(icon(maximized ? "winRestore" : "winMaximize")); };
setMaximizeIcon(false);
winMinimizeBtn.addEventListener("click", () => api("window_minimize"));
async function toggleMaximize() {
  await api("window_toggle_maximize");
  setMaximizeIcon(await api("window_is_maximized"));
}
winMaximizeBtn.addEventListener("click", toggleMaximize);
winCloseBtn.addEventListener("click", () => api("window_close"));
const titlebarDrag = document.getElementById("titlebar-drag");

// Only this explicit HTML strip starts a native move. Do not use
// .pywebview-drag-region: pywebview 5.x routes that class through
// Window.move()/SetWindowPos, which is both fragile on WinForms and makes
// browser/client-area interactions look like window dragging.
titlebarDrag.addEventListener("mousedown", (event) => {
  if (event.button !== 0) return;
  event.preventDefault();
  event.stopPropagation();
  api("window_start_drag");
});
titlebarDrag.addEventListener("dblclick", (event) => {
  if (event.button !== 0) return;
  toggleMaximize();
});

// The WebView2 child owns the whole client area, so the top-level Win32
// WM_NCHITTEST does not see the HTML edge pixels. These tiny transparent
// handles explicitly hand the operation to the real Win32 resize loop.
// Nothing else in the client area is draggable.
document.querySelectorAll(".resize-handle").forEach((handle) => {
  handle.addEventListener("mousedown", (event) => {
    if (event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    api("window_start_resize", handle.dataset.edge);
  });
});

api("window_is_maximized").then((v) => setMaximizeIcon(v === true));

/* ========================================================================
   Topbar icon buttons
   ======================================================================== */
document.getElementById("brand-dot").append(icon("cube"));
document.getElementById("btn-settings").append(icon("settings"));
document.getElementById("btn-activity").append(icon("activity"));
document.getElementById("dock-account-chev").append(icon("chevronUp"));
document.getElementById("dock-instance-chev").append(icon("chevronUp"));
document.getElementById("dock-instance-icon").append(icon("cube"));
document.getElementById("btn-settings").addEventListener("click", openSettingsSheet);
document.getElementById("btn-activity").addEventListener("click", openActivitySheet);
winMinimizeBtn.append(icon("winMinimize"));
winCloseBtn.append(icon("x"));

/* ========================================================================
   HOME — live Minecraft patch notes over the cherry-blossom background
   ======================================================================== */
const homePage = document.getElementById("page-home");
let patchNotesLoaded = false;

async function loadHome() {
  if (patchNotesLoaded) return;
  patchNotesLoaded = true;
  homePage.replaceChildren(el("div", { class: "empty-state" }, "Loading the latest from Minecraft…"));
  const data = await api("get_patch_notes");
  if (data?.error || !data?.entries?.length) {
    patchNotesLoaded = false;
    homePage.replaceChildren(
      el("div", { class: "page-head" }, el("div", {}, [el("h1", {}, "Minecraft Patch Notes")])),
      el("div", { class: "card empty-state" }, [
        el("div", {}, data?.error ? `Couldn't reach Mojang's patch-note feed: ${data.error}` : "No patch notes available."),
        el("button", { class: "btn btn-ghost", style: { marginTop: "14px" }, onclick: () => { patchNotesLoaded = false; loadHome(); } }, "Try again"),
      ])
    );
    return;
  }
  renderHome(data.entries);
}

function renderHome(entries) {
  const latest = entries[0];
  const rest = entries.slice(1);

  const hero = el("div", { class: "hero", "data-testid": "patch-hero", onclick: () => openPatchNote(latest) }, [
    el("div", { class: "hero-media", style: { backgroundImage: `url("${latest.image}")` } }),
    el("div", { class: "hero-body" }, [
      el("div", { class: "hero-kicker" }, "Minecraft Patch Notes"),
      el("h1", { class: "hero-title" }, latest.title || "Minecraft"),
      el("div", { class: "hero-meta" }, [
        el("span", { class: `badge-pill ${latest.type === "release" ? "green" : "blue"}` }, latest.type || "update"),
        el("span", { class: "patch-date" }, fmtDate(latest.date)),
      ]),
      el("p", { class: "hero-text" }, (latest.shortText || "").slice(0, 220)),
      el("button", { class: "btn btn-primary", "data-testid": "hero-read-btn", onclick: (e) => { e.stopPropagation(); openPatchNote(latest); } }, "Read patch notes"),
    ]),
  ]);

  const grid = el("div", { class: "patch-grid", "data-testid": "patch-grid" },
    rest.map((entry) =>
      el("div", { class: "patch-card", "data-testid": "patch-card", onclick: () => openPatchNote(entry) }, [
        el("div", { class: "patch-card-media", style: { backgroundImage: `url("${entry.image}")` } }),
        el("div", { class: "patch-card-body" }, [
          el("div", { class: "patch-title" }, entry.title || entry.version),
          el("div", { class: "patch-meta" }, [
            el("span", { class: `badge-pill ${entry.type === "release" ? "green" : "blue"}` }, entry.type || "update"),
            el("span", { class: "patch-date" }, fmtDate(entry.date)),
          ]),
        ]),
      ])
    )
  );

  homePage.replaceChildren(hero, el("div", { class: "section-title" }, [icon("sparkle"), "Recent updates"]), grid);
}

function openPatchNote(entry) {
  sheet.open(({ header, body }) => {
    header.append(
      el("h2", {}, entry.title || entry.version),
      el("div", { class: "patch-meta", style: { marginBottom: "6px" } }, [
        el("span", { class: `badge-pill ${entry.type === "release" ? "green" : "blue"}` }, entry.type || "update"),
        el("span", { class: "patch-date" }, fmtDate(entry.date)),
      ])
    );
    const bodyEl = el("div", { class: "patch-body" }, el("div", { class: "empty-state" }, "Loading…"));
    body.append(bodyEl);
    api("get_patch_note_body", entry.contentPath).then((res) => {
      if (res?.error || !res?.body) { bodyEl.replaceChildren(el("div", { class: "empty-state" }, "Couldn't load the full notes.")); return; }
      bodyEl.innerHTML = res.body;
    });
  });
}

/* ========================================================================
   CONTENT — install mods / modpacks / shaders / resource packs
   ======================================================================== */
const contentPage = document.getElementById("page-content");
let contentType = "mod";
let contentResults, contentSearchInput, betaToggleRow, betaCheckbox, contentScopeNote, contentSeg;

function initContentPage() {
  const seg = el("div", { class: "seg", "data-testid": "content-type-seg" }, [
    el("div", { class: "seg-item active", "data-val": "mod", "data-testid": "content-type-mod" }, "Mods"),
    el("div", { class: "seg-item", "data-val": "modpack", "data-testid": "content-type-modpack" }, "Modpacks"),
    el("div", { class: "seg-item", "data-val": "shader", "data-testid": "content-type-shader" }, "Shaders"),
    el("div", { class: "seg-item", "data-val": "resourcepack", "data-testid": "content-type-resourcepack" }, "Resource Packs"),
  ]);
  contentSeg = seg;
  contentSearchInput = el("input", { type: "search", placeholder: "Search Modrinth…", "data-testid": "content-search-input", style: { flex: "1", minWidth: "220px" } });
  const searchBtn = el("button", { class: "btn btn-blue", "data-testid": "content-search-btn", onclick: searchContent }, "Search");
  betaCheckbox = el("input", { type: "checkbox", "data-testid": "content-beta-toggle" });
  betaToggleRow = el("label", { style: { display: "flex", alignItems: "center", gap: "7px", cursor: "pointer" } }, [betaCheckbox, el("span", { class: "text-small" }, "Show beta/alpha")]);
  contentScopeNote = el("div", { class: "text-small" });
  contentResults = el("div", { class: "results-grid", "data-testid": "content-results" });

  contentSearchInput.addEventListener("keydown", (e) => { if (e.key === "Enter") searchContent(); });

  contentPage.replaceChildren(
    el("div", { class: "page-head" }, el("div", {}, [el("h1", {}, "Content"), el("p", {}, "Install mods, modpacks, shaders and resource packs from Modrinth")])),
    el("div", { class: "toolbar" }, [seg, contentScopeNote]),
    el("div", { class: "toolbar" }, [contentSearchInput, searchBtn, betaToggleRow]),
    contentResults
  );
  segmented(seg, (val) => {
    contentType = val;
    betaToggleRow.style.display = val === "mod" ? "" : "none";
    searchContent();
  });
}

function updateContentTypeAvailability() {
  if (!contentSeg) return;
  const inst = activeInstance();
  const modsDisabled = !!inst && inst.loader === "vanilla";
  const modItem = contentSeg.querySelector('.seg-item[data-val="mod"]');
  if (modItem) {
    modItem.classList.toggle("disabled", modsDisabled);
    modItem.title = modsDisabled ? "Vanilla instances can't use mods" : "";
  }
  if (!modsDisabled || contentType !== "mod") return;
  const target = contentSeg.querySelector('.seg-item[data-val="resourcepack"]');
  if (!target) return;
  contentType = "resourcepack";
  [...contentSeg.querySelectorAll(".seg-item")].forEach((i) => i.classList.toggle("active", i === target));
  if (betaToggleRow) betaToggleRow.style.display = "none";
  const indicator = contentSeg.querySelector(".seg-indicator");
  if (indicator) {
    indicator.style.width = `${target.offsetWidth}px`;
    indicator.style.transform = `translateX(${target.offsetLeft}px)`;
  }
}

function updateContentScopeNote() {
  const inst = activeInstance();
  contentScopeNote.replaceChildren(
    contentType === "modpack"
      ? document.createTextNode("Modpacks install as a brand-new instance.")
      : inst
        ? el("span", {}, [document.createTextNode("For "), el("b", {}, inst.name), document.createTextNode(` · ${inst.mc_version} ${state.loaderLabels[inst.loader] || inst.loader} — switch via the dock`)])
        : document.createTextNode("Pick an instance in the dock first.")
  );
}

const resultCardsByProjectId = new Map();
let knownInstalledProjectIds = new Set();

async function fetchInstalledIdsForCurrentType() {
  if (contentType === "modpack" || !state.activeId) return new Set();
  const result = await api("list_installed_content", state.activeId);
  return new Set((result?.items || []).map((i) => i.project_id));
}

/* Infinite scroll: results load a page (20) at a time as the sentinel row
   at the bottom of the grid scrolls into view, and each page is appended a
   few cards per animation frame instead of all at once so a big batch never
   blocks the main thread / causes jank while scrolling. */
const CONTENT_PAGE_SIZE = 20;
const CONTENT_APPEND_CHUNK = 4;
let contentSearchId = 0;
let contentQuery = "";
let contentOffset = 0;
let contentHasMore = true;
let contentLoadingMore = false;
let contentSentinel = null;
let contentLoadingRow = null;
let contentObserver = null;

function ensureContentObserver() {
  if (contentObserver) return;
  contentObserver = new IntersectionObserver(
    (entries) => { if (entries.some((e) => e.isIntersecting)) loadMoreContent(); },
    { root: contentPage, rootMargin: "600px 0px" }
  );
}

async function searchContent() {
  if (!contentResults) return;
  updateContentScopeNote();
  const searchId = ++contentSearchId;
  contentQuery = contentSearchInput.value.trim();
  contentOffset = 0;
  contentHasMore = true;
  contentLoadingMore = false;
  if (contentObserver) contentObserver.disconnect();
  contentResults.replaceChildren(el("div", { class: "empty-state" }, "Searching…"));
  resultCardsByProjectId.clear();
  stopContentPolling();
  const [result, installedIds] = await Promise.all([
    api("search_content", contentQuery, contentType, state.activeId, 0),
    fetchInstalledIdsForCurrentType(),
  ]);
  if (searchId !== contentSearchId) return; // a newer search superseded this one
  knownInstalledProjectIds = installedIds;
  contentResults.replaceChildren();
  if (result?.error) { contentHasMore = false; contentResults.append(el("div", { class: "empty-state" }, `Search failed: ${result.error}`)); return; }
  const hits = result?.hits || [];
  if (!hits.length) { contentHasMore = false; contentResults.append(el("div", { class: "empty-state" }, "No results.")); return; }
  contentOffset = hits.length;
  contentHasMore = hits.length >= CONTENT_PAGE_SIZE;

  contentSentinel = el("div", { class: "content-sentinel" });
  contentLoadingRow = el("div", { class: "empty-state content-loading-more", style: { display: "none" } }, "Loading more…");
  contentResults.append(contentSentinel, contentLoadingRow);

  await appendHitsChunked(hits, searchId);
  startContentPolling();

  ensureContentObserver();
  contentObserver.observe(contentSentinel);
}

async function loadMoreContent() {
  if (contentLoadingMore || !contentHasMore) return;
  const searchId = contentSearchId;
  contentLoadingMore = true;
  contentLoadingRow.style.display = "";
  try {
    const result = await api("search_content", contentQuery, contentType, state.activeId, contentOffset);
    if (searchId !== contentSearchId) return; // superseded by a newer search
    if (result?.error) { contentHasMore = false; return; }
    const hits = result?.hits || [];
    contentHasMore = hits.length >= CONTENT_PAGE_SIZE;
    contentOffset += hits.length;
    await appendHitsChunked(hits, searchId);
  } finally {
    if (searchId === contentSearchId) contentLoadingRow.style.display = "none";
    contentLoadingMore = false;
    if (!contentHasMore && contentObserver) contentObserver.disconnect();
  }
}

function appendHitsChunked(hits, searchId) {
  return new Promise((resolve) => {
    let i = 0;
    function step() {
      if (searchId !== contentSearchId || !contentResults) return resolve();
      const end = Math.min(i + CONTENT_APPEND_CHUNK, hits.length);
      for (; i < end; i++) contentResults.insertBefore(buildContentCard(hits[i]), contentSentinel);
      if (i < hits.length) requestAnimationFrame(step);
      else resolve();
    }
    requestAnimationFrame(step);
  });
}

function buildContentCard(hit) {
  const progress = progressRow();
  const installBtn = el("button", { class: "btn btn-pink", "data-testid": "content-install-btn" }, "Install");
  const thumb = el("div", { class: "content-thumb", style: hit.icon_url ? { backgroundImage: `url("${hit.icon_url}")` } : {} });
  const card = el("div", { class: "card content-card", "data-testid": "content-card" }, [
    el("div", { class: "top" }, [
      thumb,
      el("div", { style: { flex: "1", minWidth: "0" } }, [
        el("div", { class: "content-title" }, hit.title || "Untitled"),
        el("div", { class: "content-desc" }, (hit.description || "").slice(0, 130)),
        el("div", { class: "content-meta" }, `${fmtDownloads(hit.downloads)}  ·  by ${hit.author || "?"}`),
      ]),
    ]),
    el("div", { class: "content-actions" }, [el("span", { class: "grow" }), installBtn]),
    progress.node,
  ]);
  const clickHandler = () => installFlow(hit, installBtn, progress);
  function setInstalled(installed) {
    if (installed) {
      installBtn.removeEventListener("click", clickHandler);
      installBtn.textContent = "✓ Installed";
      installBtn.className = "btn btn-ghost";
      installBtn.disabled = true;
    } else {
      installBtn.textContent = "Install";
      installBtn.className = "btn btn-pink";
      installBtn.disabled = false;
      installBtn.addEventListener("click", clickHandler);
    }
  }
  setInstalled(knownInstalledProjectIds.has(hit.project_id));
  if (hit.project_id) resultCardsByProjectId.set(hit.project_id, { setInstalled });
  return card;
}

function applyInstalledIds(newIds) {
  const changed = [];
  for (const pid of newIds) if (!knownInstalledProjectIds.has(pid)) changed.push([pid, true]);
  for (const pid of knownInstalledProjectIds) if (!newIds.has(pid)) changed.push([pid, false]);
  knownInstalledProjectIds = newIds;
  for (const [pid, installed] of changed) resultCardsByProjectId.get(pid)?.setInstalled(installed);
}

let contentPollTimer = null;
function startContentPolling() {
  stopContentPolling();
  contentPollTimer = setInterval(async () => {
    if (currentPage !== "content" || contentType === "modpack" || !resultCardsByProjectId.size || !state.activeId) return;
    applyInstalledIds(await fetchInstalledIdsForCurrentType());
  }, 3000);
}
function stopContentPolling() { if (contentPollTimer) clearInterval(contentPollTimer); contentPollTimer = null; }

async function installFlow(hit, installBtn, progress) {
  if (contentType === "modpack") return installModpackFlow(hit, installBtn, progress);
  if (!state.activeId) { toast("Pick an instance in the dock first."); openInstancePicker(); return; }
  installBtn.disabled = true;
  const result = await api("get_versions", hit.project_id, state.activeId, contentType);
  installBtn.disabled = false;
  if (result?.error) { toast(result.error); return; }
  let versions = result.versions || [];
  if (contentType === "mod" && !betaCheckbox.checked) versions = versions.filter((v) => (v.version_type || "release") === "release");
  const instanceId = state.activeId;
  openVersionPicker(hit.title, versions, (version) => downloadAndInstall(instanceId, version, installBtn, progress, hit.title, hit.icon_url));
}
async function downloadAndInstall(instanceId, version, installBtn, progress, name, iconUrl) {
  installBtn.disabled = true;
  progress.show();
  const result = await api("install_content", instanceId, contentType, version, name, iconUrl);
  if (result?.error) { installBtn.disabled = false; toast(result.error); return; }
  taskSubscribers.set(result.task_id, (task) => {
    progress.update(task.detail || task.error, task.progress, task.status === "error");
    if (task.status !== "running") {
      setTimeout(() => progress.hide(), 4000);
      if (task.status === "done" && version.project_id) applyInstalledIds(new Set([...knownInstalledProjectIds, version.project_id]));
      else installBtn.disabled = false;
    }
  });
}
async function installModpackFlow(hit, installBtn, progress) {
  installBtn.disabled = true;
  const result = await api("get_modpack_versions", hit.project_id);
  installBtn.disabled = false;
  if (result?.error) { toast(result.error); return; }
  openVersionPicker(hit.title, result.versions || [], (version) => downloadAndInstallModpack(hit.title, version, installBtn, progress));
}
async function downloadAndInstallModpack(title, version, installBtn, progress) {
  installBtn.disabled = true;
  progress.show();
  const result = await api("install_modpack", title, version);
  if (result?.error) { installBtn.disabled = false; toast(result.error); return; }
  taskSubscribers.set(result.task_id, (task) => {
    progress.update(task.detail || task.error, task.progress, task.status === "error");
    if (task.status !== "running") {
      installBtn.disabled = false;
      setTimeout(() => progress.hide(), 4000);
      if (task.status === "done") refreshInstances();
    }
  });
}

/* version picker sheet (paginated + filterable) */
const PAGE_SIZE = 20;
function openVersionPicker(title, versions, onSelect) {
  sheet.open(({ header, body, footer }) => {
    header.append(el("h2", {}, `Choose a version`), el("div", { class: "text-small", id: "vp-count" }, `${versions.length} compatible version(s) — ${title}`));
    footer.remove();
    let filtered = versions;
    let rendered = 0;
    const list = el("div", { class: "list" });
    body.append(list);
    if (versions.length > PAGE_SIZE) {
      const filterInput = el("input", { type: "search", placeholder: "Filter by version / MC version…", style: { marginBottom: "12px" } });
      filterInput.addEventListener("input", () => {
        const q = filterInput.value.trim().toLowerCase();
        filtered = !q ? versions : versions.filter((v) =>
          (v.version_number || "").toLowerCase().includes(q) || (v.name || "").toLowerCase().includes(q) ||
          (v.version_type || "").toLowerCase().includes(q) || (v.game_versions || []).some((gv) => gv.toLowerCase().includes(q)));
        document.getElementById("vp-count").textContent = `${filtered.length} of ${versions.length} version(s)`;
        renderBatch(true);
      });
      body.insertBefore(filterInput, list);
    }
    let loadMoreBtn = null;
    function renderBatch(reset = false) {
      if (reset) { list.replaceChildren(); rendered = 0; }
      if (loadMoreBtn) { loadMoreBtn.remove(); loadMoreBtn = null; }
      if (!filtered.length) { list.append(el("div", { class: "empty-state" }, "No versions match this instance's loader + Minecraft version.")); return; }
      const batch = filtered.slice(rendered, rendered + PAGE_SIZE);
      for (const v of batch) list.append(buildVersionRow(v));
      rendered += batch.length;
      const remaining = filtered.length - rendered;
      if (remaining > 0) {
        loadMoreBtn = el("button", { class: "btn btn-ghost", style: { width: "100%" }, onclick: () => renderBatch(false) }, `Show ${Math.min(remaining, PAGE_SIZE)} more (${remaining} remaining)`);
        list.append(loadMoreBtn);
      }
    }
    function buildVersionRow(v) {
      const name = v.name || v.version_number || "unknown";
      const channel = v.version_type && v.version_type !== "release" ? `  ·  ${v.version_type}` : "";
      const date = (v.date_published || "").slice(0, 10);
      const gameVersions = (v.game_versions || []).slice(0, 6).join(", ");
      const loaders = (v.loaders || []).join(", ");
      const installBtn = el("button", { class: "btn btn-pink", "data-testid": "version-install-btn" }, "Install");
      installBtn.addEventListener("click", () => { sheet.close(); onSelect(v); });
      return el("div", { class: "card" }, [el("div", { class: "card-row" }, [
        el("div", { style: { flex: "1" } }, [
          el("h2", {}, name),
          el("div", { class: "text-small" }, `v${v.version_number || ""}${channel}${date ? `  ·  ${date}` : ""}`),
          gameVersions ? el("div", { class: "text-small" }, `MC: ${gameVersions}${loaders ? `  |  ${loaders}` : ""}`) : null,
        ]),
        installBtn,
      ])]);
    }
    renderBatch(true);
  });
}

/* ========================================================================
   MANAGE — delete instances / mods / shaders / resource packs
   ======================================================================== */
const managePage = document.getElementById("page-manage");
let manageType = "instances";
let manageList, manageScopeNote;

function initManagePage() {
  const seg = el("div", { class: "seg", "data-testid": "manage-type-seg" }, [
    el("div", { class: "seg-item active", "data-val": "instances", "data-testid": "manage-type-instances" }, "Instances"),
    el("div", { class: "seg-item", "data-val": "mod", "data-testid": "manage-type-mod" }, "Mods"),
    el("div", { class: "seg-item", "data-val": "shader", "data-testid": "manage-type-shader" }, "Shaders"),
    el("div", { class: "seg-item", "data-val": "resourcepack", "data-testid": "manage-type-resourcepack" }, "Resource Packs"),
  ]);
  manageScopeNote = el("div", { class: "text-small" });
  manageList = el("div", { class: "list", "data-testid": "manage-list" });
  managePage.replaceChildren(
    el("div", { class: "page-head" }, el("div", {}, [el("h1", {}, "Manage"), el("p", {}, "Remove instances and installed content")])),
    el("div", { class: "toolbar" }, [seg, manageScopeNote]),
    manageList
  );
  segmented(seg, (val) => { manageType = val; loadManage(); });
}

async function loadManage() {
  if (!manageList) return;
  if (manageType === "instances") return renderManageInstances();
  const inst = activeInstance();
  manageScopeNote.replaceChildren(inst ? el("span", {}, [document.createTextNode("For "), el("b", {}, inst.name), document.createTextNode(" — switch via the dock")]) : document.createTextNode("Pick an instance in the dock first."));
  if (!inst) { manageList.replaceChildren(el("div", { class: "card empty-state" }, "Pick an instance in the dock first.")); return; }
  manageList.replaceChildren(el("div", { class: "empty-state" }, "Loading…"));
  const result = await api("list_installed_content", state.activeId);
  manageList.replaceChildren();
  if (result?.error) { manageList.append(el("div", { class: "card empty-state" }, result.error)); return; }
  const items = (result.items || []).filter((i) => i.project_type === manageType);
  const label = { mod: "mods", shader: "shaders", resourcepack: "resource packs" }[manageType];
  if (!items.length) { manageList.append(el("div", { class: "card empty-state" }, `No installed ${label} for this instance yet.`)); return; }
  for (const item of items) manageList.append(buildManageContentRow(item, label));
}

function renderManageInstances() {
  manageScopeNote.replaceChildren(document.createTextNode(`${state.instances.length} instance(s)`));
  manageList.replaceChildren();
  if (!state.instances.length) { manageList.append(el("div", { class: "card empty-state" }, "No instances yet — create one from the dock.")); return; }
  for (const inst of state.instances) {
    const badgeColor = inst.loader === "vanilla" ? "blue" : "pink";
    const deleteBtn = el("button", { class: "btn btn-danger", "data-testid": "manage-delete-instance-btn" }, "Delete");
    if (runningInstances.has(inst.id) || installingInstances.has(inst.id)) deleteBtn.disabled = true;
    deleteBtn.addEventListener("click", () => {
      if (!confirm(`Delete '${inst.name}' and all its files? This cannot be undone.`)) return;
      deleteBtn.disabled = true;
      api("delete_instance", inst.id).then(() => refreshInstances().then(loadManage));
    });
    manageList.append(el("div", { class: "card" }, [el("div", { class: "manage-row" }, [
      el("div", { style: { minWidth: "0" } }, [
        el("div", { style: { display: "flex", alignItems: "center", gap: "10px", marginBottom: "3px" } }, [
          el("h2", {}, inst.name),
          el("span", { class: `badge-pill ${badgeColor}` }, state.loaderLabels[inst.loader] || inst.loader),
        ]),
        el("div", { class: "text-small" }, `Minecraft ${inst.mc_version}${inst.installed ? "" : "  ·  not installed"}`),
      ]),
      el("div", { style: { display: "flex", gap: "8px" } }, [
        el("button", { class: "btn btn-ghost", onclick: () => api("open_folder", inst.id) }, "Open Folder"),
        deleteBtn,
      ]),
    ])]));
  }
}

function buildManageContentRow(item, label) {
  const deleteBtn = el("button", { class: "btn btn-danger", "data-testid": "manage-delete-content-btn" }, "Delete");
  deleteBtn.addEventListener("click", async () => {
    if (!confirm(`Delete ${item.filename}? This removes the file from the instance.`)) return;
    deleteBtn.disabled = true;
    const result = await api("delete_installed_content", state.activeId, item.project_id);
    if (result?.error) { toast(result.error); deleteBtn.disabled = false; return; }
    toast(`${item.filename} removed.`, "success");
    const updated = new Set(knownInstalledProjectIds); updated.delete(item.project_id); applyInstalledIds(updated);
    loadManage();
  });
  // Content installed through GLauncher has a known Modrinth project (name +
  // icon); a file the user dropped into the folder by hand has no project_id
  // at all, so it falls back to showing just its raw filename with no icon.
  const known = !!item.name;
  const titleEl = el("div", { class: known ? "fname" : "fname mono" }, known ? item.name : item.filename);
  const rowChildren = [];
  if (known) rowChildren.push(el("div", { class: "content-thumb manage-thumb", style: item.icon_url ? { backgroundImage: `url("${item.icon_url}")` } : {} }));
  rowChildren.push(el("div", { style: { minWidth: "0" } }, [titleEl, el("div", { class: "text-small" }, label)]));
  return el("div", { class: "card" }, [el("div", { class: "manage-row" }, [
    el("div", { style: { display: "flex", alignItems: "center", gap: "12px", minWidth: "0" } }, rowChildren),
    deleteBtn,
  ])]);
}

/* ========================================================================
   THE DOCK — account · instance · play
   ======================================================================== */
const dockAccountBtn = document.getElementById("dock-account");
const dockAccountAvatar = document.getElementById("dock-account-avatar");
const dockAccountName = document.getElementById("dock-account-name");
const dockInstanceBtn = document.getElementById("dock-instance");
const dockInstanceName = document.getElementById("dock-instance-name");
const dockPlayBtn = document.getElementById("dock-play");
const dockPlayProgress = document.getElementById("dock-play-progress");
const dockPlayFill = dockPlayProgress.querySelector(".fill");
const dockProgress = {
  show() { dockPlayProgress.classList.add("visible"); },
  hide() { dockPlayProgress.classList.remove("visible"); },
  update(_t, p) {
    if (p === null || p === undefined) dockPlayFill.classList.add("indeterminate");
    else { dockPlayFill.classList.remove("indeterminate"); dockPlayFill.style.width = `${Math.max(0, Math.min(1, p)) * 100}%`; }
  },
};

function setDockPlay(label, disabled, withIcon) {
  dockPlayBtn.replaceChildren();
  if (withIcon) dockPlayBtn.append(icon("play"));
  dockPlayBtn.append(document.createTextNode(label));
  dockPlayBtn.disabled = disabled;
}
function refreshDockInstance() {
  const inst = activeInstance();
  dockInstanceName.textContent = inst ? inst.name : "No instance";
  if (currentPage === "content") updateContentScopeNote();
}
function refreshDockPlay() {
  const inst = activeInstance();
  if (!inst) { setDockPlay("Play", false, true); dockProgress.hide(); return; }
  if (runningInstances.has(inst.id)) { setDockPlay("Playing", true, false); return; }
  if (launching.has(inst.id)) { setDockPlay("Starting…", true, false); return; }
  if (installingInstances.has(inst.id)) { setDockPlay("Installing…", true, false); return; }
  setDockPlay("Play", false, true);
}

dockPlayBtn.addEventListener("click", playActive);
async function playActive() {
  const inst = activeInstance();
  if (!inst) { toast("Create or pick an instance first."); openInstancePicker(); return; }
  if (installingInstances.has(inst.id) || runningInstances.has(inst.id) || launching.has(inst.id)) return;
  // Guard + immediate feedback, synchronously — closes the click→api round-trip
  // race so Play can't be pressed again during the (slightly delayed) response.
  launching.add(inst.id);
  setDockPlay("Starting…", true, false);
  dockProgress.show();
  dockProgress.update(null, null);
  const result = await api("play", inst.id);
  launching.delete(inst.id);
  if (result?.error === "no_account") { refreshDockPlay(); dockProgress.hide(); toast("Add and select an account first."); openAccountPopover(); return; }
  if (result?.error) { refreshDockPlay(); dockProgress.hide(); toast(result.error); return; }
  installingInstances.add(inst.id);
  setDockPlay("Starting…", true, false); // keep friendly label until a task event clarifies
  taskSubscribers.set(result.task_id, (task) => {
    if (task.status === "running") {
      const busy = /^(installing|waiting|preparing)/i.test(task.detail || "");
      setDockPlay(busy ? "Installing…" : "Starting…", true, false);
      dockProgress.update(task.detail, task.progress);
    } else if (task.status === "done") {
      const wasRunning = runningInstances.has(inst.id);
      installingInstances.delete(inst.id);
      runningInstances.add(inst.id);
      refreshDockPlay();
      dockProgress.update("Running", 1);
      setTimeout(() => dockProgress.hide(), 1200);
      if (!wasRunning) celebrateLaunch(); // chime + bloom the moment it starts
      if (currentPage === "manage") loadManage();
    } else {
      installingInstances.delete(inst.id);
      refreshDockPlay();
      dockProgress.update(`Failed: ${task.error}`, 1, true);
      toast(`Launch failed: ${task.error}`);
      setTimeout(() => dockProgress.hide(), 4000);
    }
  });
}

/* ---- instance picker popover ---- */
dockInstanceBtn.addEventListener("click", () => { instancePopover.isOpen() ? instancePopover.close() : openInstancePicker(); });
function openInstancePicker() {
  dockInstanceBtn.classList.add("open");
  instancePopover.open(dockInstanceBtn, (node) => {
    if (!state.instances.length) node.append(el("div", { class: "text-small", style: { padding: "8px" } }, "No instances yet."));
    for (const inst of state.instances) {
      const item = el("div", { class: `popover-item${inst.id === state.activeId ? " active" : ""}`, "data-testid": "instance-picker-item" }, [
        el("span", { class: "dock-icon-badge", style: { width: "34px", height: "34px" } }, icon("cube")),
        el("div", { class: "info" }, [
          el("div", { class: "name" }, inst.name),
          el("div", { class: "text-small" }, `${inst.mc_version} · ${state.loaderLabels[inst.loader] || inst.loader}`),
        ]),
        inst.id === state.activeId ? el("span", { class: "pill pink" }, "Active") : null,
      ]);
      item.addEventListener("click", () => { setActive(inst.id); instancePopover.close(); });
      node.append(item);
    }
    node.append(el("div", { class: "popover-divider" }));
    node.append(el("div", { class: "popover-action", "data-testid": "new-instance-action", onclick: () => { instancePopover.close(); openNewInstanceSheet(); } }, [icon("plus"), "New Instance"]));
  }, () => dockInstanceBtn.classList.remove("open"));
}

function openNewInstanceSheet() {
  sheet.open(({ header, body, footer, close }) => {
    header.append(el("h2", {}, "Create Instance"));
    const nameInput = el("input", { type: "text", placeholder: "My New World", class: "field-row", "data-testid": "new-instance-name" });
    const loaderSelect = el("select", { class: "dropdown field-row", "data-testid": "new-instance-loader" }, Object.entries(state.loaderLabels).map(([id, label]) => el("option", { value: id }, label)));
    const snapshotsCheck = el("input", { type: "checkbox" });
    const oldCheck = el("input", { type: "checkbox" });
    const versionSelect = el("select", { class: "dropdown field-row", "data-testid": "new-instance-version" }, [el("option", {}, "Loading…")]);
    const loaderVersionLabel = el("div", { class: "field-label" }, "Loader version");
    const loaderVersionSelect = el("select", { class: "dropdown field-row" }, [el("option", {}, "(latest)")]);
    loaderVersionLabel.style.display = "none"; loaderVersionSelect.style.display = "none";
    body.append(
      el("div", { class: "field-label", style: { marginTop: "0" } }, "Instance name"), nameInput,
      el("div", { class: "field-label" }, "Mod loader"), loaderSelect,
      el("div", { class: "checkbox-row" }, [el("label", {}, [snapshotsCheck, "Show snapshots"]), el("label", {}, [oldCheck, "Show old versions"])]),
      el("div", { class: "field-label" }, "Minecraft version"), versionSelect, loaderVersionLabel, loaderVersionSelect
    );
    const createBtn = el("button", { class: "btn btn-primary", "data-testid": "new-instance-create" }, "Create & Install");
    footer.append(el("button", { class: "btn btn-ghost", onclick: close }, "Cancel"), createBtn);
    async function reloadVersions() {
      versionSelect.replaceChildren(el("option", {}, "Loading…"));
      const loaderId = loaderSelect.value;
      const result = loaderId === "vanilla" ? await api("version_list", snapshotsCheck.checked, oldCheck.checked) : await api("loader_mc_versions", loaderId, !snapshotsCheck.checked);
      const versions = result?.versions?.length ? result.versions : ["(none available)"];
      versionSelect.replaceChildren(...versions.map((v) => el("option", { value: v }, v)));
      onVersionChange();
    }
    async function onVersionChange() {
      const loaderId = loaderSelect.value;
      if (loaderId === "vanilla") { loaderVersionLabel.style.display = "none"; loaderVersionSelect.style.display = "none"; return; }
      loaderVersionLabel.style.display = ""; loaderVersionSelect.style.display = "";
      loaderVersionSelect.replaceChildren(el("option", {}, "Loading…"));
      const result = await api("loader_versions", loaderId, versionSelect.value, false);
      const versions = result?.versions?.length ? result.versions : ["(latest)"];
      loaderVersionSelect.replaceChildren(...versions.map((v) => el("option", { value: v }, v)));
    }
    loaderSelect.addEventListener("change", reloadVersions);
    snapshotsCheck.addEventListener("change", reloadVersions);
    oldCheck.addEventListener("change", reloadVersions);
    versionSelect.addEventListener("change", onVersionChange);
    reloadVersions();
    createBtn.addEventListener("click", async () => {
      const name = nameInput.value.trim();
      if (!name) { toast("Please enter an instance name."); return; }
      const mcVersion = versionSelect.value;
      if (!mcVersion || mcVersion.startsWith("(") || mcVersion === "Loading…") { toast("Please wait for versions to finish loading."); return; }
      const loaderId = loaderSelect.value;
      const loaderVersion = loaderId === "vanilla" || ["(latest)", "Loading…"].includes(loaderVersionSelect.value) ? null : loaderVersionSelect.value;
      const inst = await api("create_instance", name, mcVersion, loaderId, loaderVersion);
      close();
      await refreshInstances();
      setActive(inst.id);
      startInstallTask(inst);
    });
  });
}

function startInstallTask(inst) {
  installingInstances.add(inst.id);
  refreshDockPlay();
  api("start_install", inst.id).then((result) => {
    if (result?.error) { installingInstances.delete(inst.id); toast(result.error); refreshDockPlay(); return; }
    dockProgress.show();
    taskSubscribers.set(result.task_id, (task) => {
      if (task.status === "running") {
        if (state.activeId === inst.id) { setDockPlay("Installing…", true, false); dockProgress.update(task.detail, task.progress); }
      } else {
        installingInstances.delete(inst.id);
        refreshInstances();
        if (state.activeId === inst.id) { dockProgress.update("Ready", 1); setTimeout(() => dockProgress.hide(), 1200); }
        if (currentPage === "manage") loadManage();
      }
    });
  });
}

/* ========================================================================
   Account switcher (dock popover) + avatar rendering
   ======================================================================== */
async function cropHeadIcon(skinUrl, size = 64) {
  const img = new Image();
  img.crossOrigin = "anonymous";
  await new Promise((resolve, reject) => { img.onload = resolve; img.onerror = reject; img.src = skinUrl; });
  const canvas = document.createElement("canvas");
  canvas.width = size; canvas.height = size;
  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(img, 8, 8, 8, 8, 0, 0, size, size);
  ctx.drawImage(img, 40, 8, 8, 8, 0, 0, size, size);
  return canvas.toDataURL("image/png");
}
const GREY_STEVE_SVG = "data:image/svg+xml;utf8," + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8" shape-rendering="crispEdges">' +
  '<rect width="8" height="8" fill="#4a5165"/><rect x="2" y="2" width="1" height="1" fill="#2c3140"/>' +
  '<rect x="5" y="2" width="1" height="1" fill="#2c3140"/><rect x="2" y="5" width="4" height="1" fill="#2c3140"/></svg>');

const avatarCache = new Map();
async function resolveAvatar(idx, acc) {
  if (avatarCache.has(idx)) return avatarCache.get(idx);
  if (!acc || acc.kind !== "microsoft") { avatarCache.set(idx, GREY_STEVE_SVG); return GREY_STEVE_SVG; }
  try {
    const result = await api("get_account_skin_url", idx);
    if (!result?.url) throw new Error("no skin url");
    const dataUri = await cropHeadIcon(result.url);
    avatarCache.set(idx, dataUri);
    return dataUri;
  } catch { avatarCache.set(idx, GREY_STEVE_SVG); return GREY_STEVE_SVG; }
}
async function loadAccounts() {
  state.accounts = (await api("list_accounts")) || [];
  avatarCache.clear();
  refreshDockAccount();
}
function refreshDockAccount() {
  const activeIdx = state.accounts.findIndex((a) => a.active);
  const active = activeIdx >= 0 ? state.accounts[activeIdx] : null;
  dockAccountAvatar.src = GREY_STEVE_SVG;
  if (active) resolveAvatar(activeIdx, active).then((src) => { dockAccountAvatar.src = src; });
  dockAccountName.textContent = active ? active.username : "No account";
}
dockAccountBtn.addEventListener("click", () => { accountPopover.isOpen() ? accountPopover.close() : openAccountPopover(); });
function openAccountPopover() {
  dockAccountBtn.classList.add("open");
  accountPopover.open(dockAccountBtn, (node) => {
    if (!state.accounts.length) node.append(el("div", { class: "text-small", style: { padding: "8px" } }, "No accounts yet."));
    state.accounts.forEach((acc, idx) => {
      const avatarImg = el("img", { src: GREY_STEVE_SVG, alt: "" });
      resolveAvatar(idx, acc).then((src) => { avatarImg.src = src; });
      const remove = el("div", { class: "popover-remove", onclick: async (e) => { e.stopPropagation(); await api("remove_account", idx); await loadAccounts(); openAccountPopover(); } }, icon("x"));
      const item = el("div", { class: `popover-item${acc.active ? " active" : ""}`, "data-testid": "account-item" }, [
        avatarImg,
        el("div", { class: "info" }, [el("div", { class: "name" }, acc.username), el("div", { class: "text-small" }, acc.kind === "microsoft" ? "Microsoft" : "Offline")]),
        remove,
      ]);
      item.addEventListener("click", async () => {
        if (!acc.active) { await api("set_active_account", idx); await loadAccounts(); }
        accountPopover.close();
        if (currentPage === "skins") loadSkins();
      });
      node.append(item);
    });
    node.append(el("div", { class: "popover-divider" }));
    node.append(
      el("div", { class: "popover-action", "data-testid": "add-offline-action", onclick: () => { accountPopover.close(); startAddOfflineFlow(); } }, [icon("user"), "Offline account"]),
      el("div", { class: "popover-action", "data-testid": "add-microsoft-action", onclick: () => { accountPopover.close(); startAddMicrosoftFlow(); } }, [icon("plus"), "Microsoft account"])
    );
  }, () => dockAccountBtn.classList.remove("open"));
}
function startAddOfflineFlow() {
  sheet.open(({ header, body, footer, close }) => {
    header.append(el("h2", {}, "Add offline account"));
    const input = el("input", { type: "text", placeholder: "Username", class: "field-row", "data-testid": "offline-username" });
    body.append(input);
    const addBtn = el("button", { class: "btn btn-primary", "data-testid": "offline-add-btn" }, "Add");
    footer.append(el("button", { class: "btn btn-ghost", onclick: close }, "Cancel"), addBtn);
    addBtn.addEventListener("click", async () => {
      const name = input.value.trim();
      if (!name) return;
      await api("add_offline_account", name);
      close();
      loadAccounts();
    });
  });
}
function startAddMicrosoftFlow() {
  sheet.open(async ({ header, body, footer, close }) => {
    header.append(el("h2", {}, "Sign in with Microsoft"));
    const clientId = await api("get_azure_client_id");
    if (!clientId) {
      body.append(el("div", { class: "text-small" }, "No Azure Client ID is configured. Set DEFAULT_AZURE_CLIENT_ID in core/settings.py to your own registered app's Client ID, then restart the launcher."));
      footer.append(el("button", { class: "btn btn-ghost", onclick: close }, "Close"));
      return;
    }
    const statusEl = el("div", { class: "text-small" });
    body.append(statusEl);
    const startBtn = el("button", { class: "btn btn-primary" }, "Get sign-in code");
    footer.append(el("button", { class: "btn btn-ghost", onclick: close }, "Cancel"), startBtn);
    startBtn.addEventListener("click", async () => {
      startBtn.disabled = true;
      statusEl.textContent = "Requesting a sign-in code…";
      const data = await api("ms_request_code", clientId);
      if (data?.error) { statusEl.textContent = ""; toast(data.error); startBtn.disabled = false; return; }
      body.replaceChildren(
        el("div", { class: "text-small" }, "Enter this code"),
        el("div", { style: { fontSize: "34px", fontWeight: "800", color: "var(--sakura-bright)", margin: "4px 0" } }, data.user_code),
        el("div", { class: "text-small", style: { color: "var(--blue-bright)", marginBottom: "16px" } }, `at ${data.verification_uri}`),
        el("div", { class: "text-small" }, "Waiting for you to enter the code…")
      );
      footer.replaceChildren();
      const result = await api("ms_wait_and_complete", data.expires_in || 900);
      if (result?.error) { toast(result.error); close(); return; }
      close();
      loadAccounts();
    });
  });
}

/* ========================================================================
   SKINS
   ======================================================================== */
const skinsPage = document.getElementById("page-skins");
let _skinview3dModulePromise = null;
function loadSkinview3d() {
  if (!_skinview3dModulePromise) _skinview3dModulePromise = import("https://cdn.jsdelivr.net/npm/skinview3d@3.4.2/+esm");
  return _skinview3dModulePromise;
}
let _activeSkinViewer = null;
async function create3DSkinPreview(container, skinUrl, capeUrl) {
  if (_activeSkinViewer) { try { _activeSkinViewer.dispose?.(); } catch {} _activeSkinViewer = null; }
  container.replaceChildren();
  if (!skinUrl) { container.append("No skin"); return; }
  const canvas = el("canvas");
  container.append(canvas);
  try {
    const skinview3d = await loadSkinview3d();
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const viewer = new skinview3d.SkinViewer({ canvas, width: 190, height: 250, skin: skinUrl });
    if (capeUrl) viewer.loadCape(capeUrl);
    viewer.fov = 50; viewer.zoom = 0.9; viewer.autoRotate = !reducedMotion; viewer.autoRotateSpeed = 0.8;
    _activeSkinViewer = viewer;
  } catch (e) {
    container.replaceChildren(el("img", { src: skinUrl, alt: "" }));
  }
}
async function loadSkins() {
  skinsPage.replaceChildren(
    el("div", { class: "page-head" }, el("div", {}, [el("h1", {}, "Skins"), el("p", {}, "Preview, upload and equip skins & capes")])),
    el("div", { class: "empty-state" }, "Loading…")
  );
  const profile = await api("get_skin_profile");
  const head = el("div", { class: "page-head" }, el("div", {}, [el("h1", {}, "Skins"), el("p", {}, "Preview, upload and equip skins & capes")]));
  if (profile?.error) {
    skinsPage.replaceChildren(head, el("div", { class: "card empty-state" }, [
      el("div", {}, profile.error),
      profile.error.includes("Microsoft") ? el("button", { class: "btn btn-primary", style: { marginTop: "14px" }, onclick: () => openAccountPopover() }, "Manage accounts") : null,
    ]));
    return;
  }
  renderSkins(head, profile);
}
function renderSkins(head, profile) {
  const skins = profile.skins || [];
  const capes = profile.capes || [];
  const activeSkin = skins.find((s) => s.state === "ACTIVE") || skins[0];
  const activeCape = capes.find((c) => c.state === "ACTIVE");
  const progress = progressRow();
  let selectedVariant = (activeSkin?.variant || "classic").toLowerCase();
  const preview = el("div", { class: "skin-preview-box" });
  create3DSkinPreview(preview, activeSkin?.url, activeCape?.url);
  const variantSeg = el("div", { class: "seg" }, [
    el("div", { class: `seg-item${selectedVariant === "classic" ? " active" : ""}`, "data-val": "classic" }, "Classic"),
    el("div", { class: `seg-item${selectedVariant === "slim" ? " active" : ""}`, "data-val": "slim" }, "Slim"),
  ]);
  const chooseBtn = el("button", { class: "btn btn-primary", "data-testid": "skin-choose-btn" }, "Choose Skin File…");
  const resetBtn = el("button", { class: "btn btn-ghost" }, "Reset to Default");
  const skinCard = el("div", { class: "card" }, [
    el("h2", { style: { marginBottom: "12px" } }, "Current Skin"),
    el("div", { style: { display: "flex", gap: "20px", alignItems: "flex-start", flexWrap: "wrap" } }, [
      preview,
      el("div", { style: { flex: "1", minWidth: "220px" } }, [
        el("div", { class: "field-label", style: { marginTop: "0" } }, "Model"),
        variantSeg,
        el("div", { style: { display: "flex", gap: "8px", marginTop: "18px" } }, [chooseBtn, resetBtn]),
      ]),
    ]),
    progress.node,
  ]);
  const rerender = () => loadSkins();
  const variantReposition = segmented(variantSeg, (v) => { selectedVariant = v; });
  requestAnimationFrame(variantReposition);
  chooseBtn.addEventListener("click", async () => {
    const picked = await api("pick_skin_file");
    if (picked?.error) { toast(picked.error); return; }
    if (!picked.path) return;
    chooseBtn.disabled = true; resetBtn.disabled = true; progress.show(); progress.update("Uploading skin…", null);
    const result = await api("upload_skin", picked.path, selectedVariant);
    chooseBtn.disabled = false; resetBtn.disabled = false; progress.hide();
    if (result?.error) { toast(result.error); return; }
    toast("Skin updated.", "success"); avatarCache.clear(); refreshDockAccount(); rerender();
  });
  resetBtn.addEventListener("click", async () => {
    chooseBtn.disabled = true; resetBtn.disabled = true; progress.show(); progress.update("Resetting skin…", null);
    const result = await api("reset_skin");
    chooseBtn.disabled = false; resetBtn.disabled = false; progress.hide();
    if (result?.error) { toast(result.error); return; }
    toast("Skin reset to default.", "success"); avatarCache.clear(); refreshDockAccount(); rerender();
  });
  const capeGrid = el("div", { class: "cape-grid" }, [
    el("div", { class: `cape-item${capes.every((c) => c.state !== "ACTIVE") ? " active" : ""}`, onclick: async () => { const r = await api("clear_cape"); if (r?.error) { toast(r.error); return; } rerender(); } },
      [el("div", { class: "cape-thumb" }, icon("x")), el("div", { class: "cape-name" }, "No cape")]),
    ...capes.map((cape) => el("div", { class: `cape-item${cape.state === "ACTIVE" ? " active" : ""}`, onclick: async () => { const r = await api("set_cape", cape.id); if (r?.error) { toast(r.error); return; } rerender(); } },
      [el("div", { class: "cape-thumb" }, el("img", { src: cape.url, alt: "" })), el("div", { class: "cape-name" }, cape.alias || "Cape")])),
  ]);
  const capesCard = el("div", { class: "card", style: { marginTop: "14px" } }, [
    el("h2", {}, "Capes"),
    capes.length ? capeGrid : el("div", { class: "text-small", style: { marginTop: "8px" } }, "This account doesn't own any capes."),
  ]);
  skinsPage.replaceChildren(head, el("div", { class: "skins-wrap" }, [skinCard, capesCard]));
}

/* ========================================================================
   SETTINGS sheet + ACTIVITY sheet
   ======================================================================== */
async function openSettingsSheet() {
  const s = await api("get_settings");
  sheet.open(({ header, body, footer, close }) => {
    header.append(el("h2", {}, "Settings"));
    const ramMin = el("input", { type: "range", min: "512", max: "8192", step: "128", value: s.ram_min_mb, "data-testid": "ram-min" });
    const ramMax = el("input", { type: "range", min: "1024", max: "16384", step: "256", value: s.ram_max_mb, "data-testid": "ram-max" });
    const ramMinLabel = el("span", {}, String(s.ram_min_mb));
    const ramMaxLabel = el("span", {}, String(s.ram_max_mb));
    const javaInput = el("input", { type: "text", value: s.java_path || "", placeholder: "Leave blank to auto-detect" });
    ramMin.addEventListener("input", () => (ramMinLabel.textContent = ramMin.value));
    ramMax.addEventListener("input", () => (ramMaxLabel.textContent = ramMax.value));
    body.append(
      el("div", { class: "text-small", style: { marginBottom: "12px" } }, `Data directory: ${s.base_dir}`),
      el("div", { class: "field-label", style: { marginTop: "0" } }, [document.createTextNode("Min RAM: "), ramMinLabel, document.createTextNode(" MB")]), ramMin,
      el("div", { class: "field-label" }, [document.createTextNode("Max RAM: "), ramMaxLabel, document.createTextNode(" MB")]), ramMax,
      el("div", { class: "field-label" }, "Custom Java executable (optional)"), javaInput,
      updateSection(s)
    );
    const saveBtn = el("button", { class: "btn btn-primary", "data-testid": "settings-save-btn" }, "Save settings");
    footer.append(el("button", { class: "btn btn-ghost", onclick: close }, "Cancel"), saveBtn);
    saveBtn.addEventListener("click", async () => { await api("save_settings", ramMin.value, ramMax.value, javaInput.value.trim()); toast("Settings saved.", "success"); close(); });
  });
}

/* ---- Version / update card inside the Settings sheet ---- */
function updateSection(s) {
  const versionLabel = el("span", {}, s.version || "unknown");
  const actionBtn = el("button", { class: "btn btn-ghost", "data-testid": "check-updates-btn" }, "Check for Updates");
  const progress = progressRow();
  const card = el("div", { class: "card", style: { marginTop: "16px" } }, [
    el("div", { class: "card-row" }, [
      el("div", {}, [el("div", { class: "field-label", style: { marginTop: "0" } }, "Version"), versionLabel]),
      actionBtn,
    ]),
    progress.node,
  ]);

  let latestInfo = null;

  const setAction = (label, kind, handler) => {
    actionBtn.textContent = label;
    actionBtn.className = `btn ${kind}`;
    actionBtn.onclick = handler;
  };

  const runCheck = async () => {
    actionBtn.disabled = true;
    actionBtn.textContent = "Checking...";
    const result = await api("check_for_updates");
    actionBtn.disabled = false;
    if (result?.error) { toast(`Couldn't check for updates: ${result.error}`); setAction("Check for Updates", "btn-ghost", runCheck); return; }
    if (result.frozen || result.no_releases) { setAction("Check for Updates", "btn-ghost", runCheck); return; }
    if (result.update_available) {
      latestInfo = result;
      setAction(`Update to ${result.latest}`, "btn-primary", runUpdate);
    } else {
      toast("You're up to date.", "success");
      setAction("Check for Updates", "btn-ghost", runCheck);
    }
  };

  const runUpdate = async () => {
    actionBtn.disabled = true;
    progress.show();
    progress.update("Starting update...", null);
    const result = await api("start_update");
    if (result?.error) { actionBtn.disabled = false; toast(result.error); return; }
    taskSubscribers.set(result.task_id, (task) => {
      progress.update(task.detail || task.error, task.progress, task.status === "error");
      if (task.status === "done") {
        versionLabel.textContent = latestInfo?.latest || versionLabel.textContent;
        setAction("Restart to Apply", "btn-primary", () => api("restart_app"));
        actionBtn.disabled = false;
      } else if (task.status === "error") {
        actionBtn.disabled = false;
        setAction(`Update to ${latestInfo?.latest || ""}`, "btn-primary", runUpdate);
      }
    });
  };

  setAction("Check for Updates", "btn-ghost", runCheck);
  return card;
}

/* ---- Tiny, safe subset-of-Markdown renderer for release changelogs ---- */
function renderChangelog(md) {
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const lines = (md || "").replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let inList = false;
  const closeList = () => { if (inList) { html.push("</ul>"); inList = false; } };
  for (let line of lines) {
    line = line.trimEnd();
    const heading = line.match(/^(#{1,6})\s+(.*)/);
    const item = line.match(/^[-*]\s+(.*)/);
    let inline = (s) => esc(s)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/(?<!\*)\*(?!\*)(.+?)\*(?!\*)/g, "<em>$1</em>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    if (heading) { closeList(); const lvl = Math.min(6, heading[1].length); html.push(`<h${lvl}>${inline(heading[2])}</h${lvl}>`); }
    else if (item) { if (!inList) { html.push("<ul>"); inList = true; } html.push(`<li>${inline(item[1])}</li>`); }
    else if (!line) { closeList(); }
    else { closeList(); html.push(`<p>${inline(line)}</p>`); }
  }
  closeList();
  return html.join("");
}

/* ---- Prompt shown when the background loop finds a new release ---- */
window.onUpdateAvailable = (info) => {
  sheet.open(({ header, body, footer, close }) => {
    header.append(el("h2", {}, "Update available"));
    const progress = progressRow();
    const changelog = el("div", { class: "changelog", html: renderChangelog(info.body) });
    body.append(
      el("div", { class: "text-small" }, `${info.current} → ${info.latest}${info.date ? " · " + fmtDate(info.date) : ""}`),
      changelog,
      progress.node
    );
    const laterBtn = el("button", { class: "btn btn-ghost" }, "Later");
    const updateBtn = el("button", { class: "btn btn-primary" }, "Update Now");
    footer.append(laterBtn, updateBtn);
    laterBtn.addEventListener("click", close);
    updateBtn.addEventListener("click", async () => {
      updateBtn.disabled = true;
      laterBtn.disabled = true;
      progress.show();
      progress.update("Starting update...", null);
      const result = await api("start_update");
      if (result?.error) { toast(result.error); close(); return; }
      taskSubscribers.set(result.task_id, (task) => {
        progress.update(task.detail || task.error, task.progress, task.status === "error");
        if (task.status === "done") {
          updateBtn.textContent = "Restart Now";
          updateBtn.disabled = false;
          updateBtn.onclick = () => api("restart_app");
        } else if (task.status === "error") {
          updateBtn.disabled = false;
          laterBtn.disabled = false;
        }
      });
    });
  });
};

async function openActivitySheet() {
  const tasks = await api("list_tasks");
  for (const t of tasks || []) allTasks.set(t.id, t);
  sheet.open(({ header, body, footer }) => {
    header.append(el("h2", {}, "Activity"));
    const list = el("div", { class: "list" });
    body.append(list);
    const render = () => {
      const arr = [...allTasks.values()].sort((a, b) => (a.id < b.id ? 1 : -1));
      list.replaceChildren();
      if (!arr.length) { list.append(el("div", { class: "card empty-state" }, "Nothing going on right now. Installs and downloads will show up here.")); return; }
      for (const t of arr) {
        const p = progressRow(); p.show(); p.update(t.detail || t.error, t.progress, t.status === "error");
        const color = t.status === "done" ? "var(--success)" : t.status === "error" ? "var(--danger)" : "var(--muted)";
        list.append(el("div", { class: "card" }, [
          el("div", { class: "card-row" }, [el("h2", { style: { fontSize: "14px" } }, t.title), el("span", { class: "text-small", style: { color } }, t.status)]),
          p.node,
        ]));
      }
    };
    render();
    const clearBtn = el("button", { class: "btn btn-ghost", "data-testid": "activity-clear-btn" }, "Clear finished");
    clearBtn.addEventListener("click", async () => { const r = await api("clear_finished_tasks"); allTasks.clear(); for (const t of r || []) allTasks.set(t.id, t); render(); renderActivityBadge(); });
    footer.append(clearBtn);
  });
}

/* ========================================================================
   Boot
   ======================================================================== */
initContentPage();
initManagePage();
pageLoaders.home = loadHome;
pageLoaders.content = () => { updateContentTypeAvailability(); updateContentScopeNote(); if (!resultCardsByProjectId.size) searchContent(); };
pageLoaders.manage = loadManage;
pageLoaders.skins = loadSkins;

(async function boot() {
  await Promise.all([refreshInstances(), loadAccounts()]);
  const initial = new URLSearchParams(location.search).get("tab");
  showPage(["home", "content", "manage", "skins"].includes(initial) ? initial : "home");
  const open = new URLSearchParams(location.search).get("open");
  if (open === "account") setTimeout(openAccountPopover, 500);
  else if (open === "instance") setTimeout(openInstancePicker, 500);
  else if (open === "newinstance") setTimeout(openNewInstanceSheet, 500);
  else if (open === "settings") setTimeout(openSettingsSheet, 500);
  requestAnimationFrame(() => { const active = navItems.find((i) => i.classList.contains("active")); if (active) movePill(active, false); });
  setTimeout(() => { const active = navItems.find((i) => i.classList.contains("active")); if (active) movePill(active, false); }, 400);
})();
