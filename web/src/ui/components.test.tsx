import { act, fireEvent, render, screen } from "@testing-library/react";
import { useRef, useState } from "react";
import { Drawer, Segmented } from "./components";

function DrawerHarness() {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const opener = useRef<HTMLButtonElement>(null);
  return (
    <>
      <button ref={opener} onClick={() => setOpen(true)}>
        Open
      </button>
      {/* A new onClose function every render, like a real parent. */}
      <Drawer open={open} title="Edit farm dates" onClose={() => setOpen(false)} returnFocusRef={opener}>
        <input aria-label="Field" value={text} onChange={(e) => setText(e.target.value)} />
      </Drawer>
    </>
  );
}

describe("Drawer", () => {
  it("keeps focus in a field while the parent re-renders", () => {
    render(<DrawerHarness />);
    fireEvent.click(screen.getByText("Open"));
    const field = screen.getByLabelText("Field");
    field.focus();
    fireEvent.change(field, { target: { value: "a" } });
    fireEvent.change(field, { target: { value: "ab" } });
    expect(document.activeElement).toBe(field);
  });

  it("closes on Escape and returns focus to the opener", () => {
    render(<DrawerHarness />);
    const opener = screen.getByText("Open");
    fireEvent.click(opener);
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(opener);
  });
});

describe("Segmented", () => {
  it("moves the choice with arrow keys", () => {
    function H() {
      const [v, setV] = useState<"a" | "b">("a");
      return <Segmented label="Pick" value={v} onChange={setV} options={[{ value: "a", label: "A" }, { value: "b", label: "B" }]} />;
    }
    render(<H />);
    fireEvent.keyDown(screen.getByRole("radio", { name: "A" }), { key: "ArrowRight" });
    expect(screen.getByRole("radio", { name: "B" })).toHaveAttribute("aria-checked", "true");
  });
});
