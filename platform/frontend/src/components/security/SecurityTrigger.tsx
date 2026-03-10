'use client';

import { useEffect, useRef } from 'react';
import { useSearchParams } from 'next/navigation';
import { usePathname } from 'next/navigation';
import { useSecurityStore } from '@/stores/useSecurityStore';

/**
 * SecurityTrigger: monitors URL for ?forceChallenge=true parameter.
 * When detected, triggers the security challenge modal globally.
 * Placed in app/layout.tsx to intercept any page.
 */
export default function SecurityTrigger() {
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const showChallenge = useSecurityStore((s) => s.showChallenge);
  const isVisible = useSecurityStore((s) => s.isVisible);
  const hasTriggered = useRef(false);

  useEffect(() => {
    const forceChallenge = searchParams.get('forceChallenge');

    if (forceChallenge === 'true' && !isVisible && !hasTriggered.current) {
      hasTriggered.current = true;
      showChallenge();
    }

    const isSeatsPage = pathname?.startsWith('/seats');
    const passedOnce = typeof window !== 'undefined' && localStorage.getItem('TM_VQA_PASSED_ONCE') === '1';
    if (isSeatsPage && !passedOnce && !isVisible && !hasTriggered.current) {
      hasTriggered.current = true;
      showChallenge();
    }
  }, [searchParams, pathname, showChallenge, isVisible]);

  return null; // No visual rendering
}
