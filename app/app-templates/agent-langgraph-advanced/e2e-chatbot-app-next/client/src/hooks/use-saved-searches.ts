import { toast } from 'sonner';
import useSWR from 'swr';

export interface SuburbSave {
  id: string;
  user_id: string;
  suburb_name: string;
  median_rent_weekly: number;
  commute_minutes: number;
  commute_mode: string;
  hazard_risk: string;
  affordability_band: string;
  saved_at: string;
}

const ENDPOINT = '/api/saved-searches';

const fetcher = (url: string) =>
  fetch(url).then((r) => {
    if (!r.ok) throw new Error('Failed to load saved searches');
    return r.json() as Promise<SuburbSave[]>;
  });

export function useSavedSearches() {
  const { data, error, isLoading, mutate } = useSWR<SuburbSave[]>(ENDPOINT, fetcher, {
    fallbackData: [],
  });

  const save = async (suburb: Omit<SuburbSave, 'id' | 'user_id' | 'saved_at'>) => {
    try {
      const res = await fetch(ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(suburb),
      });
      if (!res.ok) throw new Error('Save failed');
      await mutate();
      toast.success(`${suburb.suburb_name} saved to your searches`);
    } catch {
      toast.error('Failed to save suburb');
    }
  };

  const remove = async (suburbName: string) => {
    try {
      await fetch(`${ENDPOINT}/${encodeURIComponent(suburbName)}`, { method: 'DELETE' });
      await mutate();
    } catch {
      toast.error('Failed to remove suburb');
    }
  };

  const clear = async () => {
    try {
      await fetch(ENDPOINT, { method: 'DELETE' });
      await mutate();
    } catch {
      toast.error('Failed to clear saved searches');
    }
  };

  const isSaved = (suburbName: string) =>
    (data ?? []).some((s) => s.suburb_name === suburbName);

  return {
    searches: data ?? [],
    save,
    remove,
    clear,
    isSaved,
    isLoading,
    error,
  };
}
