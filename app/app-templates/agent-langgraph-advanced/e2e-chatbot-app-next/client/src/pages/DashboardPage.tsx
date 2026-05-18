import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { DatabricksDashboard } from '@databricks/aibi-client';

interface EmbedConfig {
  workspace_url: string;
  workspace_id?: string;
  dashboard_id: string;
  embed_token: string;
}

export default function DashboardPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let dashboard: DatabricksDashboard | null = null;

    const init = async () => {
      try {
        const res = await fetch('/api/dashboard/embed-config', {
          credentials: 'include',
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.message ?? `Server error ${res.status}`);
        }
        const config: EmbedConfig = await res.json();

        if (!containerRef.current) return;

        dashboard = new DatabricksDashboard({
          instanceUrl: config.workspace_url,
          workspaceId: config.workspace_id ?? '',
          dashboardId: config.dashboard_id,
          token: config.embed_token,
          container: containerRef.current,
          getNewToken: async () => {
            const refresh = await fetch('/api/dashboard/embed-config', {
              credentials: 'include',
            });
            const fresh: EmbedConfig = await refresh.json();
            return fresh.embed_token;
          },
          colorScheme: 'light',
        });

        dashboard.initialize();
        setLoading(false);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load dashboard');
        setLoading(false);
      }
    };

    init();

    return () => {
      dashboard?.destroy();
    };
  }, []);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      className="flex h-full flex-col"
    >
      {loading && (
        <div className="flex h-full items-center justify-center">
          <p className="text-sm text-muted-foreground">Loading dashboard...</p>
        </div>
      )}
      {error && (
        <div className="flex h-full items-center justify-center px-4">
          <p className="text-sm text-destructive text-center">{error}</p>
        </div>
      )}
      <div ref={containerRef} className="flex-1 w-full" />
    </motion.div>
  );
}
