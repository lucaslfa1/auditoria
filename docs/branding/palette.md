## 2024-05-24 - Drag-and-Drop Keyboard Accessibility
**Learning:** Drag-and-drop zones often lack keyboard support, leaving users unable to upload files without a mouse.
**Action:** Always add tabIndex, role='button', and onKeyDown handlers to trigger the file input via Enter/Space.
