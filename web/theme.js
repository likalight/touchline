/* Set the judge presentation theme before paint; the full studio keeps its broadcast theme. */
"use strict";
(() => {
  if (location.pathname !== "/judge" && new URLSearchParams(location.search).get("judge") !== "1") return;
  document.documentElement.classList.add("judge-page");
  const media = matchMedia("(prefers-color-scheme: dark)");
  let choice = "system";
  try { const saved = JSON.parse(localStorage.getItem("tl.theme")); if (["system", "light", "dark"].includes(saved)) choice = saved; } catch { /* optional */ }
  const apply = () => { document.documentElement.dataset.theme = choice === "system" ? (media.matches ? "dark" : "light") : choice; };
  apply(); media.addEventListener("change", apply);
  const preload = document.createElement("link"); preload.rel = "preload"; preload.as = "image";
  preload.href = "/static/assets/matchday-hero.webp";
  preload.imageSrcset = "/static/assets/matchday-hero-480.webp 480w, /static/assets/matchday-hero-960.webp 960w, /static/assets/matchday-hero.webp 1536w";
  preload.imageSizes = "(max-width: 767px) calc(100vw - 40px), 50vw";
  document.head.appendChild(preload);
  document.addEventListener("DOMContentLoaded", () => {
    const select = document.querySelector("#storyTheme");
    select.value = choice; select.parentElement.hidden = false;
    select.addEventListener("change", () => {
      choice = select.value; apply();
      try { localStorage.setItem("tl.theme", JSON.stringify(choice)); } catch { /* optional */ }
    });
  });
})();
