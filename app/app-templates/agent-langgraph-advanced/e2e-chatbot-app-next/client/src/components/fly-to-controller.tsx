import { useEffect, useRef } from 'react';
import { useMap } from 'react-leaflet';
import { useMapState, useMapDispatch } from '@/contexts/MapContext';
import L from 'leaflet';

interface Centroid {
  name: string;
  lat: number;
  lng: number;
}

let cachedCentroids: Centroid[] | null = null;

async function getCentroids(): Promise<Centroid[]> {
  if (cachedCentroids) return cachedCentroids;
  const res = await fetch('/api/map/centroids');
  cachedCentroids = await res.json();
  return cachedCentroids ?? [];
}

export function FlyToController() {
  const map = useMap();
  const { suburbs, zoomToSuburb } = useMapState();
  const dispatch = useMapDispatch();
  const prevSuburbsRef = useRef<string>('');
  const prevZoomRef = useRef<string | null>(null);

  // Survivor zoom: fly to fit all active suburbs whenever the list changes
  useEffect(() => {
    const activeSuburbs = suburbs.filter((s) => s.status !== 'dimmed');
    const key = activeSuburbs.map((s) => s.name).join('|');
    if (key === prevSuburbsRef.current || activeSuburbs.length === 0) return;
    prevSuburbsRef.current = key;

    // Single highlighted suburb triggers street-level zoom, not survivor zoom
    const highlightedOnly =
      activeSuburbs.length === 1 && activeSuburbs[0].status === 'highlighted';
    if (highlightedOnly) return;

    getCentroids().then((centroids) => {
      const centroidMap = new Map(centroids.map((c) => [c.name.toLowerCase(), c]));
      const points: [number, number][] = activeSuburbs
        .map((s) => centroidMap.get(s.name.toLowerCase()))
        .filter((c): c is Centroid => c != null)
        .map((c) => [c.lat, c.lng]);

      if (points.length === 0) return;

      const bounds = L.latLngBounds(points);
      map.flyToBounds(bounds, {
        padding: [60, 60],
        maxZoom: 13,
        duration: 1.2,
      });
    });
  }, [suburbs, map]);

  // Single-suburb zoom: fly to street level when zoomToSuburb changes
  useEffect(() => {
    if (!zoomToSuburb || zoomToSuburb === prevZoomRef.current) return;
    prevZoomRef.current = zoomToSuburb;

    getCentroids().then((centroids) => {
      const centroid = centroids.find(
        (c) => c.name.toLowerCase() === zoomToSuburb.toLowerCase(),
      );
      if (!centroid) return;

      map.flyTo([centroid.lat, centroid.lng], 14, { duration: 1.0 });

      // Clear zoom intent after flying so subsequent re-renders don't re-fire
      setTimeout(() => {
        dispatch({ type: 'CLEAR_ZOOM' });
      }, 1200);
    });
  }, [zoomToSuburb, map, dispatch]);

  return null;
}
