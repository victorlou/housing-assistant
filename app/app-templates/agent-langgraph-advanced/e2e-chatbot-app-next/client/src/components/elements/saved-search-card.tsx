import { useState } from 'react';
import { Bookmark, Car, Footprints, Bike, Train, Droplets, X, Check, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useSavedSearches } from '@/hooks/use-saved-searches';

const COMMUTE_ICONS: Record<string, React.ElementType> = {
  transit: Train,
  drive: Car,
  bike: Bike,
  walk: Footprints,
};

const HAZARD_COLORS: Record<string, string> = {
  low: 'text-green-600 dark:text-green-400',
  medium: 'text-amber-600 dark:text-amber-400',
  high: 'text-red-600 dark:text-red-400',
};

const BAND_STYLES: Record<string, string> = {
  affordable: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  moderate: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
  stressed: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
};

export interface SavedSearchCardProps {
  suburb_name: string;
  median_rent_weekly: number;
  commute_minutes: number;
  commute_mode: string;
  hazard_risk: string;
  affordability_band: string;
}

export function SavedSearchCard({
  suburb_name,
  median_rent_weekly,
  commute_minutes,
  commute_mode,
  hazard_risk,
  affordability_band,
}: SavedSearchCardProps) {
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved' | 'dismissed'>('idle');
  const { save, isSaved } = useSavedSearches();

  const alreadySaved = isSaved(suburb_name);
  const CommuteIcon = COMMUTE_ICONS[commute_mode] ?? Car;

  if (status === 'dismissed' || alreadySaved) return null;

  const handleSave = async () => {
    setStatus('saving');
    await save({ suburb_name, median_rent_weekly, commute_minutes, commute_mode, hazard_risk, affordability_band });
    setStatus('saved');
    setTimeout(() => setStatus('dismissed'), 1500);
  };

  return (
    <div className="my-2 rounded-xl border bg-muted/30">
      {/* Header */}
      <div className={cn(
        'flex items-center gap-2 px-4 py-2.5 bg-background/60 border-b rounded-t-xl',
      )}>
        <Bookmark className="size-4 shrink-0 text-primary" />
        <span className="flex-1 text-sm font-medium truncate">
          Save {suburb_name}?
        </span>
        <Button
          variant="ghost"
          size="icon"
          className="size-7 text-muted-foreground hover:text-foreground"
          onClick={() => setStatus('dismissed')}
          title="Dismiss"
        >
          <X className="size-3.5" />
        </Button>
      </div>

      {/* Body */}
      <div className="px-4 py-3 flex flex-wrap items-center gap-3">
        {/* Affordability band */}
        <span className={cn('rounded-full px-2 py-0.5 text-xs font-medium capitalize', BAND_STYLES[affordability_band] ?? BAND_STYLES.moderate)}>
          {affordability_band}
        </span>

        {/* Rent */}
        <span className="text-sm font-semibold">${median_rent_weekly}/wk</span>

        {/* Commute */}
        <span className="flex items-center gap-1 text-sm text-muted-foreground">
          <CommuteIcon className="size-3.5" />
          {commute_minutes} min
        </span>

        {/* Hazard */}
        <span className={cn('flex items-center gap-1 text-xs capitalize', HAZARD_COLORS[hazard_risk] ?? '')}>
          <Droplets className="size-3.5" />
          {hazard_risk} risk
        </span>

        {/* Actions */}
        <div className="ml-auto flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs text-muted-foreground"
            onClick={() => setStatus('dismissed')}
            disabled={status !== 'idle'}
          >
            Not now
          </Button>
          <Button
            size="sm"
            className="h-7 px-3 text-xs gap-1"
            onClick={handleSave}
            disabled={status !== 'idle' || alreadySaved}
          >
            {status === 'saving' && <Loader2 className="size-3 animate-spin" />}
            {status === 'saved' && <Check className="size-3" />}
            {status === 'idle' && !alreadySaved && <Bookmark className="size-3" />}
            {status === 'saved' ? 'Saved!' : alreadySaved ? 'Already saved' : 'Save to My Searches'}
          </Button>
        </div>
      </div>
    </div>
  );
}
