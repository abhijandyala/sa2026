import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import type { Priority } from "../../content/strategies";
import { PriorityPicker } from "./PriorityPicker";

function Harness() {
  const [p, setP] = useState<Priority[]>([]);
  return <PriorityPicker priorities={p} onToggle={(x) => setP((cur) => (cur.includes(x) ? cur.filter((y) => y !== x) : [...cur, x]))} />;
}

describe("PriorityPicker", () => {
  it("allows up to two and says which are on", () => {
    render(<Harness />);
    const soil = screen.getByRole("button", { name: /protect soil/i });
    const moisture = screen.getByRole("button", { name: /spring moisture/i });
    const grain = screen.getByRole("button", { name: /grain harvest/i });
    fireEvent.click(soil);
    fireEvent.click(moisture);
    expect(soil).toHaveAttribute("aria-pressed", "true");
    expect(grain).toBeDisabled();
    fireEvent.click(soil);
    expect(soil).toHaveAttribute("aria-pressed", "false");
    expect(grain).not.toBeDisabled();
  });
});
