import { useEffect } from 'react';

export function useBodyScrollLock(locked: boolean) {
  useEffect(() => {
    if (!locked) {
      return;
    }

    const { body, documentElement } = document;
    const previousOverflow = body.style.overflow;
    const previousOverscrollBehavior = body.style.overscrollBehavior;
    const previousPaddingRight = body.style.paddingRight;
    const scrollbarCompensation = window.innerWidth - documentElement.clientWidth;

    body.classList.add('overlay-open');
    body.style.overflow = 'hidden';
    body.style.overscrollBehavior = 'none';

    if (scrollbarCompensation > 0) {
      body.style.paddingRight = `${scrollbarCompensation}px`;
    }

    return () => {
      body.classList.remove('overlay-open');
      body.style.overflow = previousOverflow;
      body.style.overscrollBehavior = previousOverscrollBehavior;
      body.style.paddingRight = previousPaddingRight;
    };
  }, [locked]);
}
