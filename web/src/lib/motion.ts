// Vestox-style motion: scroll reveals, mouse parallax, scroll progress. Pure DOM, no dependency.
// Reveal classes are added by script, so React re-renders only ever remove them (the content then simply shows).
// Motion is ON by default (it is the design). ?motion=off turns it off and is remembered; ?motion=on turns it back on.
try {
  const q0 = new URLSearchParams(location.search).get("motion");
  if (q0 === "on" || q0 === "off") localStorage.setItem("pam.motion", q0);
  if (localStorage.getItem("pam.motion") !== "off") document.documentElement.setAttribute("data-motion", "on");
} catch { document.documentElement.setAttribute("data-motion", "on"); }

const SEL = ".vx-wrap .info-card, .vx-wrap .alert-card, .vx-wrap .panel, .vx-wrap h1, .vx-wrap h2, .vx-wrap section, .vx-wrap table.register, .vx-wrap .border.border-rule, .vx-wrap .border.border-rule-strong";

export function initMotion(): () => void {
  if (typeof window === "undefined") return () => {};
  const root = document.documentElement;
  // Opt-out: ?motion=off (remembered).
  const q = new URLSearchParams(location.search).get("motion");
  try { if (q === "on" || q === "off") localStorage.setItem("pam.motion", q); } catch { /* storage blocked */ }
  let pref: string | null = null;
  try { pref = localStorage.getItem("pam.motion"); } catch { /* storage blocked */ }
  const force = pref !== "off";
  if (force) root.setAttribute("data-motion", "on");
  if (!force) return () => {};
  const io = new IntersectionObserver((entries) => {
    let i = 0;
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      const el = e.target as HTMLElement;
      el.style.transitionDelay = `${Math.min(i++, 6) * 70}ms`;
      requestAnimationFrame(() => el.classList.add("vx-in"));
      io.unobserve(el);
    }
  }, { threshold: 0.08, rootMargin: "0px 0px -6% 0px" });

  const seen = new WeakSet<Element>();
  const scan = () => {
    document.querySelectorAll(SEL).forEach((el) => {
      if (seen.has(el)) return;
      seen.add(el);
      // nested matches would double-animate; reveal only the outermost
      if (el.parentElement?.closest(SEL)) return;
      el.classList.add("vx-r");
      io.observe(el);
    });
  };
  scan();
  const mo = new MutationObserver(() => scan());
  mo.observe(document.body, { childList: true, subtree: true });

  let raf = 0, mx = 0, my = 0;
  const onMove = (ev: MouseEvent) => {
    mx = (ev.clientX / window.innerWidth) * 2 - 1;
    my = (ev.clientY / window.innerHeight) * 2 - 1;
    if (!raf) raf = requestAnimationFrame(() => { raf = 0; root.style.setProperty("--mx", mx.toFixed(3)); root.style.setProperty("--my", my.toFixed(3)); });
  };
  const onScroll = () => {
    const max = root.scrollHeight - window.innerHeight;
    root.style.setProperty("--sp", max > 0 ? String(Math.min(1, window.scrollY / max)) : "0");
    root.style.setProperty("--sy", String(window.scrollY));
  };
  window.addEventListener("mousemove", onMove, { passive: true });
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();
  return () => { io.disconnect(); mo.disconnect(); window.removeEventListener("mousemove", onMove); window.removeEventListener("scroll", onScroll); };
}
