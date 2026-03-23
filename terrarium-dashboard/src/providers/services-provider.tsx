import { createContext, useContext, type ReactNode } from 'react';
import { ApiClient } from '@/services/api-client';
import { WsManager } from '@/services/ws-manager';

const apiClient = new ApiClient(import.meta.env.VITE_API_BASE_URL ?? '');
const wsManager = new WsManager(import.meta.env.VITE_WS_BASE_URL ?? '');

const ApiClientContext = createContext<ApiClient>(apiClient);
const WsManagerContext = createContext<WsManager>(wsManager);

export function ServicesProvider({ children }: { children: ReactNode }) {
  return (
    <ApiClientContext.Provider value={apiClient}>
      <WsManagerContext.Provider value={wsManager}>
        {children}
      </WsManagerContext.Provider>
    </ApiClientContext.Provider>
  );
}

export function useApiClient(): ApiClient {
  return useContext(ApiClientContext);
}

export function useWsManager(): WsManager {
  return useContext(WsManagerContext);
}
