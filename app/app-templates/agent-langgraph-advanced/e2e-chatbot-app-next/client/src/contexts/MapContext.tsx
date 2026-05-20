import {
  createContext,
  useContext,
  useReducer,
  type Dispatch,
  type ReactNode,
} from 'react';

export type SuburbStatus = 'active' | 'dimmed' | 'highlighted';

export interface SuburbEntry {
  name: string;
  status: SuburbStatus;
  lat?: number;
  lng?: number;
}

export interface IsochroneState {
  suburb: string;
  minutes: number;
  mode: 'transit' | 'walking' | 'driving';
}

export interface MapState {
  suburbs: SuburbEntry[];
  isochrone: IsochroneState | null;
  filterSummary: string;
  zoomToSuburb: string | null;
}

const initialState: MapState = {
  suburbs: [],
  isochrone: null,
  filterSummary: '',
  zoomToSuburb: null,
};

export type MapAction =
  | {
      type: 'RENDER_MAP';
      suburbs: SuburbEntry[];
      isochrone: IsochroneState | null;
      filterSummary: string;
    }
  | { type: 'ZOOM_TO_SUBURB'; name: string }
  | { type: 'CLEAR_ZOOM' }
  | { type: 'RESET' };

function mapReducer(state: MapState, action: MapAction): MapState {
  switch (action.type) {
    case 'RENDER_MAP': {
      const highlighted = action.suburbs.find((s) => s.status === 'highlighted');
      return {
        ...state,
        suburbs: action.suburbs,
        isochrone: action.isochrone,
        filterSummary: action.filterSummary,
        zoomToSuburb: highlighted ? highlighted.name : null,
      };
    }
    case 'ZOOM_TO_SUBURB':
      return { ...state, zoomToSuburb: action.name };
    case 'CLEAR_ZOOM':
      return { ...state, zoomToSuburb: null };
    case 'RESET':
      return initialState;
    default:
      return state;
  }
}

const MapStateContext = createContext<MapState | null>(null);
const MapDispatchContext = createContext<Dispatch<MapAction> | null>(null);

export function MapProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(mapReducer, initialState);
  return (
    <MapStateContext.Provider value={state}>
      <MapDispatchContext.Provider value={dispatch}>
        {children}
      </MapDispatchContext.Provider>
    </MapStateContext.Provider>
  );
}

export function useMapState(): MapState {
  const ctx = useContext(MapStateContext);
  if (!ctx) throw new Error('useMapState must be used inside MapProvider');
  return ctx;
}

export function useMapDispatch(): Dispatch<MapAction> {
  const ctx = useContext(MapDispatchContext);
  if (!ctx) throw new Error('useMapDispatch must be used inside MapProvider');
  return ctx;
}

/** Safe version — returns null when outside MapProvider (chat mode). */
export function useOptionalMapDispatch(): Dispatch<MapAction> | null {
  return useContext(MapDispatchContext);
}
