import { ExternalLink, Home, Tag, Building2 } from 'lucide-react';

interface ListingLinksCardProps {
  suburb: string;
  realestate: string;
  trademe: string;
  barfoot: string;
}

const SITES = [
  {
    key: 'realestate',
    name: 'realestate.co.nz',
    description: "NZ's largest property site",
    Icon: Home,
  },
  {
    key: 'trademe',
    name: 'Trade Me Property',
    description: "NZ's biggest marketplace",
    Icon: Tag,
  },
  {
    key: 'barfoot',
    name: 'Barfoot & Thompson',
    description: "Auckland's largest agency",
    Icon: Building2,
  },
] as const;

export function ListingLinksCard({
  suburb,
  realestate,
  trademe,
  barfoot,
}: ListingLinksCardProps) {
  const hrefs: Record<string, string> = { realestate, trademe, barfoot };

  return (
    <div className="my-2 rounded-xl border border-primary/30 bg-muted/30">
      <div className="flex items-center gap-2 px-4 py-2.5 bg-background/60 border-b rounded-t-xl">
        <ExternalLink className="size-4 shrink-0 text-primary" />
        <span className="flex-1 text-sm font-medium">{suburb}</span>
      </div>
      <div className="flex flex-col divide-y divide-border/50">
        {SITES.map(({ key, name, description, Icon }) => (
          <a
            key={key}
            href={hrefs[key]}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-3 px-4 py-3 hover:bg-accent/50 transition-colors last:rounded-b-xl"
          >
            <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10">
              <Icon className="size-4 text-primary" />
            </div>
            <div className="flex min-w-0 flex-col">
              <span className="text-sm font-medium">{name}</span>
              <span className="text-xs text-muted-foreground">{description}</span>
            </div>
            <ExternalLink className="ml-auto size-3.5 shrink-0 text-muted-foreground" />
          </a>
        ))}
      </div>
    </div>
  );
}
