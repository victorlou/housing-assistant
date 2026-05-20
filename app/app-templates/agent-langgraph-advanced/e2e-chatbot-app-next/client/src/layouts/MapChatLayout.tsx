import { Outlet } from 'react-router-dom';
import { useSession } from '@/contexts/SessionContext';
import { MapProvider } from '@/contexts/MapContext';
import { DatabricksLogo } from '@/components/DatabricksLogo';
import { DbIcon } from '@/components/ui/db-icon';
import { UserKeyIconIcon } from '@/components/icons';

export default function MapChatLayout() {
  const { session, loading } = useSession();

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-muted-foreground">Loading...</div>
      </div>
    );
  }

  if (!session?.user) {
    return (
      <div className="flex h-screen items-center justify-center bg-secondary">
        <div className="flex flex-col items-center gap-6">
          <DatabricksLogo height={20} />
          <div className="flex w-80 flex-col items-center gap-4 rounded-md border border-border bg-background p-10 shadow-[var(--shadow-db-lg)]">
            <DbIcon icon={UserKeyIconIcon} size={32} color="muted" />
            <div className="flex flex-col items-center gap-1.5 text-center">
              <h3>Authentication Required</h3>
              <p className="text-muted-foreground">
                Please authenticate using Databricks to access this application.
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <MapProvider>
      <Outlet />
    </MapProvider>
  );
}
