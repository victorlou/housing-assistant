import { useEffect, useState } from 'react';
import { GeoJSON } from 'react-leaflet';
import { cellToBoundary } from 'h3-js';
import { useMapState } from '@/contexts/MapContext';
import type { FeatureCollection } from 'geojson';

function hexIdsToGeoJSON(hexIds: string[]): FeatureCollection {
  const features = hexIds
    .map((id) => {
      try {
        const boundary = cellToBoundary(id, true); // true = [lng, lat] GeoJSON order
        return {
          type: 'Feature' as const,
          properties: {},
          geometry: {
            type: 'Polygon' as const,
            coordinates: [[...boundary, boundary[0]]],
          },
        };
      } catch {
        return null;
      }
    })
    .filter((f): f is NonNullable<typeof f> => f != null);

  return { type: 'FeatureCollection', features };
}

export function IsochroneLayer() {
  const { isochrone } = useMapState();
  const [geoJSON, setGeoJSON] = useState<FeatureCollection | null>(null);

  useEffect(() => {
    if (!isochrone) {
      setGeoJSON(null);
      return;
    }

    const { suburb, minutes, mode } = isochrone;
    const url = `/api/map/isochrone/${encodeURIComponent(suburb)}/${minutes}/${mode}`;

    fetch(url)
      .then((r) => r.json())
      .then((data: { hexIds: string[] }) => {
        setGeoJSON(hexIdsToGeoJSON(data.hexIds ?? []));
      })
      .catch((e) => console.error('[IsochroneLayer] fetch failed:', e));
  }, [isochrone]);

  if (!geoJSON || geoJSON.features.length === 0) return null;

  return (
    <GeoJSON
      key={JSON.stringify(isochrone)}
      data={geoJSON}
      style={{
        color: '#0d9488',
        fillColor: '#0d9488',
        fillOpacity: 0.12,
        weight: 1,
        opacity: 0.5,
      }}
    />
  );
}
