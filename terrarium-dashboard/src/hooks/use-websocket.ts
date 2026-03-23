import { useEffect, useState } from 'react';
import { useWsManager } from '@/providers/services-provider';
import type { ConnectionStatus } from '@/types/ui';

/** Hook that manages WebSocket connection lifecycle for a run. */
export function useWebSocket(runId: string | null) {
  const ws = useWsManager();
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');

  useEffect(() => {
    if (!runId) return;

    const unsubStatus = ws.subscribeStatus(setStatus);
    ws.connect(runId);

    return () => {
      unsubStatus();
      ws.disconnect();
    };
  }, [runId, ws]);

  return { status, manager: ws };
}
