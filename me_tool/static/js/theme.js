// Themes: light, dark and ocean. Loaded in <head> (not deferred) so the right
// colours apply before the page draws. The choice is remembered in this
// browser; without a choice the device setting picks light or dark.
(function () {
  "use strict";
  const root = document.documentElement;
  let saved = null;
  try { saved = localStorage.getItem("theme"); } catch (e) { /* private browsing */ }
  const THEMES = ["light", "dark", "ocean"];
  root.dataset.theme = THEMES.includes(saved)
    ? saved
    : window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";

  function mark() {
    document.querySelectorAll(".theme-option").forEach((button) => {
      const on = button.dataset.themeValue === root.dataset.theme;
      button.classList.toggle("active", on);
      button.setAttribute("aria-checked", String(on));
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    // Eye button next to a password: show or hide what was typed
    document.querySelectorAll(".password-toggle").forEach((button) => {
      const input = button.parentElement.querySelector("input");
      button.addEventListener("click", () => {
        const show = input.type === "password";
        input.type = show ? "text" : "password";
        const text = show ? "Hide password" : "Show password";
        button.setAttribute("aria-label", text);
        button.title = text;
        button.setAttribute("aria-pressed", String(show));
        input.focus();
      });
    });

    mark();
    document.querySelectorAll(".theme-option").forEach((button) => {
      button.addEventListener("click", () => {
        const next = button.dataset.themeValue;
        root.dataset.theme = next;
        try { localStorage.setItem("theme", next); } catch (e) { /* not remembered */ }
        mark();
        // Charts read their colours from the CSS variables: redraw them
        document.dispatchEvent(new CustomEvent("themechange", { detail: next }));
      });
    });
  });
})();
