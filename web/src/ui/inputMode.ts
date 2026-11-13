/*
  Focus rings are for the keyboard. A click or a tap never draws one.
  The page remembers how the last interaction happened (`data-input` on <html>);
  `fieldback.css` hides the outline while it is "pointer". Tab and the arrow keys
  bring the ring back, so keyboard users always see where they are.
*/
const KEYS = new Set(["Tab", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End", "PageUp", "PageDown"]);

export function trackInputMode(root: HTMLElement = document.documentElement): () => void {
  const pointer = () => {
    root.dataset.input = "pointer";
  };
  const key = (e: KeyboardEvent) => {
    if (KEYS.has(e.key)) root.dataset.input = "keyboard";
  };
  window.addEventListener("pointerdown", pointer, true);
  window.addEventListener("keydown", key, true);
  return () => {
    window.removeEventListener("pointerdown", pointer, true);
    window.removeEventListener("keydown", key, true);
  };
}
