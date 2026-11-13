import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { Tour, type TourStep } from "./Tour";

const steps: TourStep[] = [
  { target: "#a", title: "First", body: "One" },
  { target: "#b", title: "Second", body: "Two" },
];

function Harness({ onEnter, onClose }: { onEnter: () => void; onClose: () => void }) {
  const [i, setI] = useState(0);
  return (
    <>
      <div id="a" />
      <div id="b" />
      <Tour steps={[steps[0]!, { ...steps[1]!, onEnter }]} index={i} onIndex={setI} onClose={onClose} />
    </>
  );
}

describe("Walk me through it", () => {
  beforeAll(() => {
    Element.prototype.scrollIntoView = () => {};
    window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} })) as never;
  });

  it("steps forward and back, marks the target and runs the step's action", () => {
    const onEnter = vi.fn();
    const onClose = vi.fn();
    render(<Harness onEnter={onEnter} onClose={onClose} />);
    expect(screen.getByText("Step 1 of 2")).toBeInTheDocument();
    expect(document.getElementById("a")).toHaveClass("tour-target");
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByRole("heading", { name: "Second" })).toHaveFocus();
    expect(document.getElementById("a")).not.toHaveClass("tour-target");
    expect(onEnter).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("ends on Escape", () => {
    const onClose = vi.fn();
    render(<Harness onEnter={() => {}} onClose={onClose} />);
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
