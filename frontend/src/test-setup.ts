import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

// ExamMultiSelect scrolls its menu into view when opened. jsdom has no layout,
// so provide the browser API while keeping the test focused on behavior.
Element.prototype.scrollIntoView = vi.fn();
