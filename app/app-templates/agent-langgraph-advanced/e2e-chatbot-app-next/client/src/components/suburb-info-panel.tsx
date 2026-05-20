import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { useMapDispatch } from '@/contexts/MapContext';
import { cn } from '@/lib/utils';

interface SuburbProfile {
  suburb_name: string;
  median_rent_weekly: number | null;
  median_household_income: number | null;
  income_decile: number | null;
  territorial_authority: string | null;
  flood_risk: string | null;
  coastal_risk: string | null;
  overall_risk: string | null;
}

function RiskBadge({ level }: { level: string | null }) {
  if (!level) return <span className="text-muted-foreground">—</span>;
  const lower = level.toLowerCase();
  return (
    <span
      className={cn('rounded-full px-2 py-0.5 text-xs font-medium capitalize', {
        'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400': lower === 'low',
        'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400': lower === 'medium',
        'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400': lower === 'high',
      })}
    >
      {level}
    </span>
  );
}

export function SuburbInfoPanel({ suburbName }: { suburbName: string }) {
  const dispatch = useMapDispatch();
  const [profile, setProfile] = useState<SuburbProfile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setProfile(null);
    fetch(`/api/map/suburb/${encodeURIComponent(suburbName)}`)
      .then((r) => r.json())
      .then((data: SuburbProfile) => {
        setProfile(data);
        setLoading(false);
      })
      .catch((e) => {
        console.error('[SuburbInfoPanel] fetch failed:', e);
        setLoading(false);
      });
  }, [suburbName]);

  return (
    <div className="rounded-xl border border-border bg-background/95 shadow-lg backdrop-blur-sm">
      <div className="flex items-start justify-between border-b border-border px-4 py-3">
        <div>
          <h3 className="font-semibold text-foreground">{suburbName}</h3>
          {profile?.territorial_authority && (
            <p className="text-muted-foreground text-xs">{profile.territorial_authority}</p>
          )}
        </div>
        <button
          type="button"
          onClick={() => {
            dispatch({ type: 'CLEAR_ZOOM' });
            // Also un-highlight the suburb
            dispatch({ type: 'ZOOM_TO_SUBURB', name: '' });
          }}
          className="rounded p-0.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
        >
          <X className="size-4" />
        </button>
      </div>

      <div className="px-4 py-3">
        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-4 animate-pulse rounded bg-muted" />
            ))}
          </div>
        ) : profile ? (
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Median rent</dt>
              <dd className="font-medium">
                {profile.median_rent_weekly != null
                  ? `$${profile.median_rent_weekly}/wk`
                  : '—'}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Household income</dt>
              <dd className="font-medium">
                {profile.median_household_income != null
                  ? `$${profile.median_household_income.toLocaleString()}/yr`
                  : '—'}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Income decile</dt>
              <dd className="font-medium">
                {profile.income_decile != null ? `${profile.income_decile}/10` : '—'}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Flood risk</dt>
              <dd>
                <RiskBadge level={profile.flood_risk} />
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Coastal risk</dt>
              <dd>
                <RiskBadge level={profile.coastal_risk} />
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Overall risk</dt>
              <dd>
                <RiskBadge level={profile.overall_risk} />
              </dd>
            </div>
          </dl>
        ) : (
          <p className="text-muted-foreground text-sm">No data available</p>
        )}
      </div>
    </div>
  );
}
