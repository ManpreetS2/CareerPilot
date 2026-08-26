import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import "./index.css";

describe("layout geometry primitives", () => {
  it("contains wrap-anywhere and kanban overflow rules in computed styles", () => {
    const { container } = render(
      <div style={{ width: 320 }}>
        <p className="wrap-anywhere">
          supercalifragilisticexpialidocious@verylong.example.com
        </p>
        <div className="kanban-board" data-testid="board">
          {Array.from({ length: 6 }).map((_, index) => (
            <section key={index} className="kanban-column">
              Column
            </section>
          ))}
        </div>
      </div>,
    );
    const wrapped = container.querySelector(".wrap-anywhere") as HTMLElement;
    const board = container.querySelector(".kanban-board") as HTMLElement;
    const column = container.querySelector(".kanban-column") as HTMLElement;
    expect(getComputedStyle(wrapped).overflowWrap).toBe("anywhere");
    expect(getComputedStyle(board).maxWidth).toBe("100%");
    expect(getComputedStyle(board).overflowX).toBe("auto");
    expect(getComputedStyle(column).flexShrink).toBe("0");
  });

  it("keeps skip-link hidden until focus and command palette fixed from the top", () => {
    const { container } = render(
      <>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <div className="command-palette glass-floating">Palette</div>
      </>,
    );
    const skip = container.querySelector(".skip-link") as HTMLElement;
    const palette = container.querySelector(".command-palette") as HTMLElement;
    expect(getComputedStyle(skip).position).toBe("absolute");
    const paletteStyle = getComputedStyle(palette);
    expect(paletteStyle.position).toBe("fixed");
    expect(paletteStyle.bottom).toBe("auto");
    expect(paletteStyle.top).not.toBe("0px");
  });
});
