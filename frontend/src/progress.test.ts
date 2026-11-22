import { describe, expect, it } from "vitest";

import { formatBytes, phaseLabel, projectProgress } from "./progress";

describe("project progress", () => {
  it("shows a small non-zero intake state", () => {
    expect(projectProgress("INTAKE", "running")).toBe(3);
  });

  it("marks completed work as done", () => {
    expect(projectProgress("BUILDING", "completed")).toBe(100);
  });

  it("renders readable labels and file sizes", () => {
    expect(phaseLabel("INTEGRATION_QA")).toBe("Integration QA");
    expect(formatBytes(1536)).toBe("1.5 KB");
  });
});
