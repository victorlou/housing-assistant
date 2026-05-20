import { useEffect, useState } from 'react';
import { CircleMarker, Tooltip } from 'react-leaflet';
import { useMapState, useMapDispatch, type SuburbStatus } from '@/contexts/MapContext';

interface Centroid {
  name: string;
  lat: number;
  lng: number;
}

const STATUS_COLORS: Record<SuburbStatus, string> = {
  active: '#16a34a',
  dimmed: '#a8a29e',
  highlighted: '#0d9488',
};

const STATUS_OPACITY: Record<SuburbStatus, number> = {
  active: 0.85,
  dimmed: 0.35,
  highlighted: 0.9,
};

const STATUS_RADIUS: Record<SuburbStatus, number> = {
  active: 8,
  dimmed: 6,
  highlighted: 11,
};

export function SuburbLayer() {
  const { suburbs } = useMapState();
  const dispatch = useMapDispatch();
  const [centroids, setCentroids] = useState<Centroid[]>([]);

  useEffect(() => {
    if (suburbs.length === 0) return;
    fetch('/api/map/centroids')
      .then((r) => r.json())
      .then((data: Centroid[]) => setCentroids(data))
      .catch((e) => console.error('[SuburbLayer] centroid fetch failed:', e));
  }, [suburbs.length]);

  if (suburbs.length === 0) return null;

  const centroidMap = new Map(centroids.map((c) => [c.name.toLowerCase(), c]));

  return (
    <>
      {suburbs.map((suburb) => {
        const centroid = centroidMap.get(suburb.name.toLowerCase());
        if (!centroid) return null;

        const color = STATUS_COLORS[suburb.status];
        const opacity = STATUS_OPACITY[suburb.status];
        const radius = STATUS_RADIUS[suburb.status];

        return (
          <CircleMarker
            key={suburb.name}
            center={[centroid.lat, centroid.lng]}
            radius={radius}
            pathOptions={{
              color: suburb.status === 'highlighted' ? '#0d9488' : color,
              fillColor: color,
              fillOpacity: opacity,
              weight: suburb.status === 'highlighted' ? 3 : 1,
            }}
            eventHandlers={{
              click: () => {
                dispatch({ type: 'ZOOM_TO_SUBURB', name: suburb.name });
              },
            }}
          >
            <Tooltip direction="top" offset={[0, -8]} opacity={0.9}>
              <span className="text-sm font-medium">{suburb.name}</span>
            </Tooltip>
          </CircleMarker>
        );
      })}
    </>
  );
}
