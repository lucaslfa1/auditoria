import { useEffect, type RefObject } from 'react';

interface UseDialogFocusTrapOptions {
  onDismiss?: () => void;
  initialFocusSelector?: string;
  restoreFocus?: boolean;
}

const FOCUSABLE_SELECTOR = [
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[href]',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

export function useDialogFocusTrap(
  containerRef: RefObject<HTMLElement | null>,
  active: boolean,
  options: UseDialogFocusTrapOptions = {},
) {
  const { onDismiss, initialFocusSelector, restoreFocus = true } = options;

  useEffect(() => {
    if (!active) {
      return;
    }

    const container = containerRef.current;
    if (!container) {
      return;
    }

    const previousActiveElement = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;

    const getFocusableElements = () =>
      Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
        (element) => !element.hasAttribute('disabled') && element.getAttribute('aria-hidden') !== 'true',
      );

    const initialFocus = initialFocusSelector
      ? container.querySelector<HTMLElement>(initialFocusSelector)
      : null;

    window.requestAnimationFrame(() => {
      const focusTarget = initialFocus ?? getFocusableElements()[0] ?? container;
      focusTarget.focus();
    });

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        if (onDismiss) {
          event.preventDefault();
          onDismiss();
        }
        return;
      }

      if (event.key !== 'Tab') {
        return;
      }

      const focusableElements = getFocusableElements();
      if (focusableElements.length === 0) {
        event.preventDefault();
        container.focus();
        return;
      }

      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];
      const activeElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;

      if (event.shiftKey) {
        if (!activeElement || activeElement === firstElement || activeElement === container) {
          event.preventDefault();
          lastElement.focus();
        }
        return;
      }

      if (!activeElement || activeElement === lastElement) {
        event.preventDefault();
        firstElement.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      if (restoreFocus && previousActiveElement?.isConnected) {
        previousActiveElement.focus();
      }
    };
  }, [active, containerRef, initialFocusSelector, onDismiss, restoreFocus]);
}
