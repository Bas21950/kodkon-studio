interface KodkonDesktopUpdate {
  available: boolean;
  currentVersion: string;
  version?: string;
  notes?: string;
}

interface KodkonDesktopStatus {
  status: 'preparing' | 'downloading' | 'ready' | 'failed';
  progress?: number;
  message: string;
}

interface Window {
  kodkonDesktop?: {
    checkForUpdates: () => Promise<KodkonDesktopUpdate>;
    downloadUpdate: () => Promise<boolean>;
    installUpdate: () => Promise<void>;
    onUpdateStatus: (callback: (status: KodkonDesktopStatus) => void) => () => void;
  };
}
