import {
  Router,
  type Request,
  type Response,
  type Router as RouterType,
} from 'express';
import { authMiddleware, requireAuth } from '../middleware/auth';
import {
  getSuburbSaves,
  upsertSuburbSave,
  deleteSuburbSave,
  clearSuburbSaves,
  isDatabaseAvailable,
} from '@chat-template/db';
import { ChatSDKError } from '@chat-template/core/errors';
import { randomUUID } from 'node:crypto';

export const savedSearchesRouter: RouterType = Router();
savedSearchesRouter.use(authMiddleware);

savedSearchesRouter.get('/', requireAuth, async (req: Request, res: Response) => {
  if (!isDatabaseAvailable()) {
    return res.status(204).end();
  }
  const session = req.session;
  if (!session) {
    const error = new ChatSDKError('unauthorized:chat');
    return res.status(error.toResponse().status).json(error.toResponse().json);
  }
  try {
    const saves = await getSuburbSaves(session.user.id);
    return res.status(200).json(saves);
  } catch (err) {
    console.error('[saved-searches GET]', err);
    return res.status(500).json({ error: 'Failed to fetch saved searches' });
  }
});

savedSearchesRouter.post('/', requireAuth, async (req: Request, res: Response) => {
  if (!isDatabaseAvailable()) {
    return res.status(503).json({ error: 'Database not available' });
  }
  const session = req.session;
  if (!session) {
    const error = new ChatSDKError('unauthorized:chat');
    return res.status(error.toResponse().status).json(error.toResponse().json);
  }
  const {
    suburb_name,
    median_rent_weekly,
    commute_minutes,
    commute_mode,
    hazard_risk,
    affordability_band,
  } = req.body as {
    suburb_name: string;
    median_rent_weekly: number;
    commute_minutes: number;
    commute_mode: string;
    hazard_risk: string;
    affordability_band: string;
  };

  if (!suburb_name) {
    return res.status(400).json({ error: 'suburb_name is required' });
  }

  try {
    await upsertSuburbSave({
      id: randomUUID(),
      user_id: session.user.id,
      suburb_name,
      median_rent_weekly: Number(median_rent_weekly),
      commute_minutes: Number(commute_minutes),
      commute_mode,
      hazard_risk,
      affordability_band,
    });
    return res.status(201).json({ ok: true });
  } catch (err) {
    console.error('[saved-searches POST]', err);
    return res.status(500).json({ error: 'Failed to save suburb' });
  }
});

savedSearchesRouter.delete('/:suburbName', requireAuth, async (req: Request, res: Response) => {
  if (!isDatabaseAvailable()) {
    return res.status(503).json({ error: 'Database not available' });
  }
  const session = req.session;
  if (!session) {
    const error = new ChatSDKError('unauthorized:chat');
    return res.status(error.toResponse().status).json(error.toResponse().json);
  }
  try {
    await deleteSuburbSave(session.user.id, req.params.suburbName);
    return res.status(200).json({ ok: true });
  } catch (err) {
    console.error('[saved-searches DELETE]', err);
    return res.status(500).json({ error: 'Failed to delete saved search' });
  }
});

savedSearchesRouter.delete('/', requireAuth, async (req: Request, res: Response) => {
  if (!isDatabaseAvailable()) {
    return res.status(503).json({ error: 'Database not available' });
  }
  const session = req.session;
  if (!session) {
    const error = new ChatSDKError('unauthorized:chat');
    return res.status(error.toResponse().status).json(error.toResponse().json);
  }
  try {
    await clearSuburbSaves(session.user.id);
    return res.status(200).json({ ok: true });
  } catch (err) {
    console.error('[saved-searches DELETE all]', err);
    return res.status(500).json({ error: 'Failed to clear saved searches' });
  }
});
