import { Bookmark, BookmarkCheck, Car, Footprints, Bike, Train, Droplets, MessageSquare } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { SuburbSave } from '@/hooks/use-saved-searches';

const COMMUTE_ICONS: Record<string, React.ElementType> = {
  transit: Train,
  drive: Car,
  bike: Bike,
  walk: Footprints,
};

const HAZARD_COLORS: Record<string, string> = {
  low: 'text-[var(--color-hazard-low,#277c43)]',
  medium: 'text-[var(--color-hazard-medium,#be501e)]',
  high: 'text-[var(--color-hazard-high,#c82d4c)]',
};

const BAND_STYLES: Record<string, string> = {
  affordable: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  moderate: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
  stressed: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
};

export interface SuburbCardProps extends Omit<SuburbSave, 'id' | 'user_id'> {
  isSaved?: boolean;
  onSave?: () => void;
  onRemove?: () => void;
  onStartChat?: (suburbName: string) => void;
  className?: string;
}

export function SuburbCard({
  suburb_name,
  median_rent_weekly,
  commute_minutes,
  commute_mode,
  hazard_risk,
  affordability_band,
  saved_at,
  isSaved,
  onSave,
  onRemove,
  onStartChat,
  className,
}: SuburbCardProps) {
  const CommuteIcon = COMMUTE_ICONS[commute_mode] ?? Car;
  const savedDate = saved_at ? new Date(saved_at).toLocaleDateString('en-NZ', { day: 'numeric', month: 'short', year: 'numeric' }) : null;

  return (
    <div className={cn('rounded-xl border bg-card p-4 flex flex-col gap-3 hover:shadow-sm transition-shadow', className)}>
      {/* Top row: suburb name + bookmark */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold text-base leading-tight">{suburb_name}</h3>
          {savedDate && (
            <p className="text-xs text-muted-foreground mt-0.5">Saved {savedDate}</p>
          )}
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="size-8 shrink-0 text-muted-foreground hover:text-primary"
          onClick={isSaved ? onRemove : onSave}
          title={isSaved ? 'Remove from saved' : 'Save suburb'}
        >
          {isSaved
            ? <BookmarkCheck className="size-4 text-primary" />
            : <Bookmark className="size-4" />
          }
        </Button>
      </div>

      {/* Stats row */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Affordability band */}
        <span className={cn('rounded-full px-2 py-0.5 text-xs font-medium capitalize', BAND_STYLES[affordability_band] ?? BAND_STYLES.moderate)}>
          {affordability_band}
        </span>

        {/* Rent */}
        <span className="text-sm font-bold">${median_rent_weekly}/wk</span>

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
      </div>

      {/* Start Chat button */}
      {onStartChat && (
        <Button
          variant="outline"
          size="sm"
          className="w-full gap-1.5 text-xs h-8"
          onClick={() => onStartChat(suburb_name)}
        >
          <MessageSquare className="size-3.5" />
          Tell me more about {suburb_name}
        </Button>
      )}
    </div>
  );
}
