/* Observatory workspace: one tool on screen at a time, every tool one click away in the side panel.
   app.js still moves between chapters with scrollIntoView and #ch- links; both are routed here. */
(() => {
  const work = document.getElementById("work");
  const chapters = [...document.querySelectorAll(".chapter")];
  const ids = chapters.map((c) => c.id);
  const strip = document.createElement("nav");
  strip.className = "tabstrip";
  strip.setAttribute("aria-label", "Tools");
  document.querySelectorAll(".rail a[data-tool]").forEach((a) => { const c = a.cloneNode(true); c.querySelector(".count")?.remove(); strip.append(c); });
  work.prepend(strip);
  const links = [...document.querySelectorAll("a[data-tool]")];
  const label = (id) => (links.find((a) => a.dataset.tool === id)?.querySelector("span")?.textContent) || id;
  const prev = document.getElementById("prevT"), next = document.getElementById("nextT");
  let current = null;

  function show(id, keepScroll) {
    if (!ids.includes(id)) id = ids[0];
    closeMenu();
    if (id === current) return;
    current = id;
    chapters.forEach((c) => c.classList.toggle("active", c.id === id));
    links.forEach((a) => {
      const on = a.dataset.tool === id;
      a.classList.toggle("on", on);
      if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    const i = ids.indexOf(id);
    pagerLink(prev, ids[i - 1], "Previous");
    pagerLink(next, ids[i + 1], "Next");
    const u = new URL(location.href);
    u.searchParams.set("tool", id.replace(/^ch-/, ""));
    history.replaceState(null, "", u);
    document.title = `${label(id)} · Observatory · Nakshatra CHRONOS`;
    const tab = strip.querySelector("a.on");
    if (tab && strip.offsetParent) strip.scrollTo({ left: tab.offsetLeft - (strip.clientWidth - tab.offsetWidth) / 2 });
    if (!keepScroll) { work.scrollTop = 0; if (getComputedStyle(work).overflowY === "visible") window.scrollTo(0, 0); }
  }

  function pagerLink(a, id, word) {
    a.hidden = !id;
    if (!id) return;
    a.href = "#" + id;
    a.innerHTML = `<small>${word}</small>${label(id)}`;
  }

  const nativeScroll = Element.prototype.scrollIntoView;
  Element.prototype.scrollIntoView = function (arg) {
    const ch = this.closest && this.closest(".chapter");
    if (ch && ids.includes(ch.id)) {
      show(ch.id, true);
      if (ch === this) { work.scrollTo({ top: 0 }); if (getComputedStyle(work).overflowY === "visible") window.scrollTo(0, 0); return; }
    }
    return nativeScroll.call(this, arg);
  };

  document.addEventListener("click", (e) => {
    const a = e.target.closest('a[href^="#ch-"]');
    if (!a) return;
    e.preventDefault();
    show(a.getAttribute("href").slice(1));
    if (a.closest(".pager")) work.focus({ preventScroll: true });
  });

  document.addEventListener("keydown", (e) => {
    const t = e.target, typing = t.matches && t.matches("input, select, textarea, [contenteditable]");
    if (e.key === "/" && !typing) { e.preventDefault(); document.getElementById("ask").focus(); return; }
    if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
    const i = ids.indexOf(current);
    if (e.key === "]" && ids[i + 1]) show(ids[i + 1]);
    if (e.key === "[" && ids[i - 1]) show(ids[i - 1]);
    if (e.key === "Escape") closeMenu();
  });

  const menu = document.getElementById("menuBtn");
  function closeMenu() { document.body.classList.remove("menu-open"); menu.setAttribute("aria-expanded", "false"); }
  menu.addEventListener("click", () => {
    const open = !document.body.classList.contains("menu-open");
    document.body.classList.toggle("menu-open", open);
    menu.setAttribute("aria-expanded", String(open));
  });

  function setBadge(id, v) { const b = document.getElementById(id); if (b) { b.textContent = v ?? ""; b.hidden = v == null || v === ""; } }
  function badges() {
    let D = null, V = null, sel = null;
    try { D = ST.D; V = ST.V; sel = ST.sel; } catch (e) { return; }
    if (D) {
      setBadge("b-sky", D.field?.exposures?.length);
      setBadge("b-fair", D.field?.microscope?.length);
      setBadge("b-cands", D.candidates?.length);
    }
    setBadge("b-dos", sel);
    const acc = V?.unknown?.accuracy_when_decided;
    setBadge("b-valid", acc != null ? (100 * acc).toFixed(1) + "%" : null);
  }
  const watch = new MutationObserver(badges);
  ["status", "dosId", "railnote"].forEach((id) => { const n = document.getElementById(id); if (n) watch.observe(n, { childList: true, characterData: true, subtree: true }); });
  document.querySelectorAll(".count").forEach((b) => { b.hidden = true; });

  const q = new URLSearchParams(location.search).get("tool");
  const fromHash = location.hash.startsWith("#ch-") ? location.hash.slice(1) : null;
  if (fromHash) history.replaceState(null, "", location.pathname + location.search);
  show(fromHash || (q ? "ch-" + q : ids[0]));
})();
