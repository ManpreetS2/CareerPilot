import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { GuidedCombobox } from "./GuidedCombobox";

function Harness({ multiple = true }: { multiple?: boolean }) {
  const [values, setValues] = useState<string[]>([]);
  return (
    <GuidedCombobox
      id="guided-test"
      label="Target roles"
      values={values}
      onChange={setValues}
      options={[
        { value: "Software Engineer", label: "Software Engineer" },
        { value: "Data Analyst", label: "Data Analyst" },
      ]}
      multiple={multiple}
      placeholder="Search roles"
    />
  );
}

describe("GuidedCombobox", () => {
  it("selects a suggestion with keyboard", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const input = screen.getByRole("combobox", { name: "Target roles" });
    await user.click(input);
    await user.keyboard("{Enter}");
    expect(screen.getByRole("button", { name: "Remove Software Engineer" })).toBeInTheDocument();
  });

  it("persists a custom value losslessly", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("combobox", { name: "Target roles" }));
    await user.type(screen.getByRole("combobox", { name: "Target roles" }), "Quant Researcher");
    await user.keyboard("{Enter}");
    expect(screen.getByText("Quant Researcher")).toBeInTheDocument();
  });

  it("keeps mobile-sized controls", () => {
    render(<Harness />);
    expect(screen.getByRole("combobox", { name: "Target roles" }).parentElement).toHaveClass("min-h-11");
  });
});
