import { motion } from 'framer-motion';
import { Bookmark, Trash2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { SuburbCard } from '@/components/suburb-card';
import { useSavedSearches } from '@/hooks/use-saved-searches';
import { Button } from '@/components/ui/button';

function EmptyState() {
  const navigate = useNavigate();
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="flex flex-col items-center justify-center gap-4 py-24 text-center"
    >
      <Bookmark className="size-12 text-muted-foreground/40" strokeWidth={1.5} />
      <div>
        <p className="text-base font-medium">No saved suburbs yet</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Save suburb recommendations from your chats to review them here.
        </p>
      </div>
      <Button variant="outline" onClick={() => navigate('/')}>
        Start a chat
      </Button>
    </motion.div>
  );
}

export default function SavedSearchesPage() {
  const { searches, remove, clear, isSaved, isLoading } = useSavedSearches();
  const navigate = useNavigate();

  const handleStartChat = (suburbName: string) => {
    navigate(`/?query=${encodeURIComponent(`Tell me more about ${suburbName}`)}`);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-24 text-sm text-muted-foreground">
        Loading…
      </div>
    );
  }

  if (searches.length === 0) {
    return <EmptyState />;
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="mx-auto max-w-4xl p-6"
    >
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Saved Searches</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {searches.length} suburb{searches.length !== 1 ? 's' : ''} saved
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5 text-xs text-destructive hover:text-destructive"
          onClick={clear}
        >
          <Trash2 className="size-3.5" />
          Clear all
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {searches.map((s) => (
          <SuburbCard
            key={s.id}
            suburb_name={s.suburb_name}
            median_rent_weekly={s.median_rent_weekly}
            commute_minutes={s.commute_minutes}
            commute_mode={s.commute_mode}
            hazard_risk={s.hazard_risk}
            affordability_band={s.affordability_band}
            saved_at={s.saved_at}
            isSaved={isSaved(s.suburb_name)}
            onRemove={() => remove(s.suburb_name)}
            onStartChat={handleStartChat}
          />
        ))}
      </div>
    </motion.div>
  );
}
