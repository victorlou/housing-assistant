import { Router, type Request, type Response, type Router as RouterType } from 'express';
import { authMiddleware, requireAuth } from '../middleware/auth';
import { getDatabricksToken, getAuthMethod } from '@chat-template/auth';
import { getWorkspaceHostname } from '@chat-template/ai-sdk-providers';

export const mapDataRouter: RouterType = Router();
mapDataRouter.use(authMiddleware);

const WAREHOUSE_ID = process.env.DATABRICKS_WAREHOUSE_ID;
const CATALOG = process.env.HOUSING_CATALOG ?? 'housing';
const SCHEMA = process.env.HOUSING_SCHEMA ?? 'gold';

// In-memory cache
let centroidsCache: { name: string; lat: number; lng: number }[] | null = null;
let centroidsCacheTime = 0;
const CACHE_TTL = 60 * 60 * 1000; // 1 hour

async function runSql(statement: string): Promise<unknown[][]> {
  if (!WAREHOUSE_ID) throw new Error('DATABRICKS_WAREHOUSE_ID not set');

  const token = await getDatabricksToken();
  const hostname = await getWorkspaceHostname();

  const res = await fetch(`${hostname}/api/2.0/sql/statements`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      warehouse_id: WAREHOUSE_ID,
      statement,
      wait_timeout: '30s',
      disposition: 'INLINE',
      format: 'JSON_ARRAY',
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Databricks SQL error ${res.status}: ${text}`);
  }

  const data = (await res.json()) as {
    status: { state: string; error?: { message: string } };
    result?: { data_array?: unknown[][] };
  };

  if (data.status.state !== 'SUCCEEDED') {
    throw new Error(
      `SQL failed: ${data.status.state} — ${data.status.error?.message ?? 'unknown'}`,
    );
  }

  return data.result?.data_array ?? [];
}

/**
 * GET /api/map/centroids
 * Returns all suburb centroids as [{name, lat, lng}]
 */
mapDataRouter.get('/centroids', requireAuth, async (_req: Request, res: Response) => {
  try {
    if (centroidsCache && Date.now() - centroidsCacheTime < CACHE_TTL) {
      return res.json(centroidsCache);
    }

    const rows = await runSql(`
      SELECT
        suburb_name,
        ST_Y(ST_GeomFromGeoJSON(h3_centerasgeojson(h3_cell))) AS lat,
        ST_X(ST_GeomFromGeoJSON(h3_centerasgeojson(h3_cell))) AS lng
      FROM ${CATALOG}.${SCHEMA}.suburb_metrics_latest
      WHERE h3_cell IS NOT NULL
    `);

    const centroids = rows
      .map((row) => ({
        name: String(row[0]),
        lat: Number(row[1]),
        lng: Number(row[2]),
      }))
      .filter((c) => !Number.isNaN(c.lat) && !Number.isNaN(c.lng));

    centroidsCache = centroids;
    centroidsCacheTime = Date.now();
    return res.json(centroids);
  } catch (err) {
    console.error('[map-data] centroids error:', err);
    return res.status(500).json({ error: String(err) });
  }
});

/**
 * GET /api/map/isochrone/:suburb/:minutes/:mode
 * Returns GeoJSON FeatureCollection of H3 hexagon polygons
 */
mapDataRouter.get(
  '/isochrone/:suburb/:minutes/:mode',
  requireAuth,
  async (req: Request, res: Response) => {
    const { suburb, minutes, mode } = req.params;
    const minutesNum = Number.parseInt(minutes, 10);
    if (Number.isNaN(minutesNum)) {
      return res.status(400).json({ error: 'minutes must be a number' });
    }

    try {
      const rows = await runSql(`
        SELECT DISTINCT
          conv(cast(h3_cell as string), 10, 16) as h3_hex
        FROM ${CATALOG}.${SCHEMA}.isochrone
        WHERE suburb_name ILIKE '%${suburb.replace(/'/g, "''")}%'
          AND travel_minutes <= ${minutesNum}
          AND mode = '${mode.replace(/'/g, "''")}'
          AND h3_cell IS NOT NULL
      `);

      const hexIds = rows.map((r) => String(r[0]).padStart(15, '0'));

      // Convert H3 cells to GeoJSON polygons on the server using raw cell boundary approximation
      // We return the hex IDs and let the client convert using h3-js
      return res.json({ hexIds });
    } catch (err) {
      console.error('[map-data] isochrone error:', err);
      return res.status(500).json({ error: String(err) });
    }
  },
);

/**
 * GET /api/map/suburb/:name
 * Returns suburb profile: rent, income, hazards
 */
mapDataRouter.get(
  '/suburb/:name',
  requireAuth,
  async (req: Request, res: Response) => {
    const { name } = req.params;
    try {
      const rows = await runSql(`
        SELECT
          suburb_name,
          median_rent_weekly,
          median_household_income,
          income_decile,
          territorial_authority
        FROM ${CATALOG}.${SCHEMA}.suburb_metrics_latest
        WHERE suburb_name ILIKE '%${name.replace(/'/g, "''")}%'
        LIMIT 1
      `);

      const hazardRows = await runSql(`
        SELECT
          flood_risk,
          coastal_risk,
          overall_risk
        FROM ${CATALOG}.${SCHEMA}.suburb_hazard
        WHERE suburb_name ILIKE '%${name.replace(/'/g, "''")}%'
        LIMIT 1
      `);

      if (!rows.length) {
        return res.status(404).json({ error: 'Suburb not found' });
      }

      const [suburbName, rent, income, decile, ta] = rows[0];
      const hazard = hazardRows[0] ?? [null, null, null];

      return res.json({
        suburb_name: suburbName,
        median_rent_weekly: rent ? Number(rent) : null,
        median_household_income: income ? Number(income) : null,
        income_decile: decile ? Number(decile) : null,
        territorial_authority: ta,
        flood_risk: hazard[0],
        coastal_risk: hazard[1],
        overall_risk: hazard[2],
      });
    } catch (err) {
      console.error('[map-data] suburb profile error:', err);
      return res.status(500).json({ error: String(err) });
    }
  },
);
