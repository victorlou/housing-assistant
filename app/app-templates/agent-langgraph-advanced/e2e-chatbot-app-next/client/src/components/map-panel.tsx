import 'leaflet/dist/leaflet.css';
import { MapContainer, TileLayer } from 'react-leaflet';
import { SuburbLayer } from './suburb-layer';
import { FlyToController } from './fly-to-controller';
import { IsochroneLayer } from './isochrone-layer';

// Default center: Auckland, NZ
const DEFAULT_CENTER: [number, number] = [-36.86, 174.76];
const DEFAULT_ZOOM = 11;

export function MapPanel() {
  return (
    <MapContainer
      center={DEFAULT_CENTER}
      zoom={DEFAULT_ZOOM}
      className="h-full w-full"
      style={{ zIndex: 0 }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <IsochroneLayer />
      <SuburbLayer />
      <FlyToController />
    </MapContainer>
  );
}
