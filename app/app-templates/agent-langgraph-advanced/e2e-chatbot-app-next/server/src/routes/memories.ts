import {
  Router,
  type Request,
  type Response,
  type Router as RouterType,
} from 'express';
import { authMiddleware, requireAuth } from '../middleware/auth';

const AGENT_BASE_URL =
  process.env.AGENT_BASE_URL || 'http://localhost:8080';

export const memoriesRouter: RouterType = Router();
memoriesRouter.use(authMiddleware);

function userId(req: Request): string {
  const s = req.session!;
  return s.user.email ?? s.user.id;
}

memoriesRouter.get(
  '/',
  requireAuth,
  async (req: Request, res: Response) => {
    try {
      const url = `${AGENT_BASE_URL}/user-memories?user_id=${encodeURIComponent(userId(req))}`;
      const upstream = await fetch(url);
      const data = await upstream.json();
      return res.status(upstream.ok ? 200 : upstream.status).json(data);
    } catch (err) {
      console.error('[memories GET]', err);
      return res.status(500).json({ error: 'Failed to fetch memories' });
    }
  },
);

memoriesRouter.put(
  '/:key',
  requireAuth,
  async (req: Request, res: Response) => {
    try {
      const url = `${AGENT_BASE_URL}/user-memories/${encodeURIComponent(req.params.key)}?user_id=${encodeURIComponent(userId(req))}`;
      const upstream = await fetch(url, {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ value: req.body }),
      });
      const data = await upstream.json();
      return res.status(upstream.ok ? 200 : upstream.status).json(data);
    } catch (err) {
      console.error('[memories PUT]', err);
      return res.status(500).json({ error: 'Failed to update memory' });
    }
  },
);

memoriesRouter.delete(
  '/:key',
  requireAuth,
  async (req: Request, res: Response) => {
    try {
      const url = `${AGENT_BASE_URL}/user-memories/${encodeURIComponent(req.params.key)}?user_id=${encodeURIComponent(userId(req))}`;
      const upstream = await fetch(url, { method: 'DELETE' });
      const data = await upstream.json();
      return res.status(upstream.ok ? 200 : upstream.status).json(data);
    } catch (err) {
      console.error('[memories DELETE]', err);
      return res.status(500).json({ error: 'Failed to delete memory' });
    }
  },
);
