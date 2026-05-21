import { useEffect, useState } from 'react';
import { Brain, Pencil, Trash2, X, Check } from 'lucide-react';
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';

interface MemoryItem {
  key: string;
  value: Record<string, unknown>;
  updated_at: string | null;
}

interface MemoriesPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function ValueSummary({ value }: { value: Record<string, unknown> }) {
  const entries = Object.entries(value).slice(0, 4);
  if (entries.length === 0) return <span className="text-muted-foreground text-xs italic">empty</span>;
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-0.5">
      {entries.map(([k, v]) => (
        <span key={k} className="text-xs text-muted-foreground">
          <span className="font-medium text-foreground/70">{k}:</span>{' '}
          {Array.isArray(v)
            ? (v as unknown[]).join(', ')
            : typeof v === 'object' && v !== null
              ? JSON.stringify(v)
              : String(v)}
        </span>
      ))}
      {Object.keys(value).length > 4 && (
        <span className="text-xs text-muted-foreground italic">+{Object.keys(value).length - 4} more</span>
      )}
    </div>
  );
}

export function MemoriesPanel({ open, onOpenChange }: MemoriesPanelProps) {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState('');
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    fetch('/api/memories', { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then((data: MemoryItem[]) => setMemories(data))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [open]);

  function startEdit(item: MemoryItem) {
    setEditingKey(item.key);
    setEditDraft(JSON.stringify(item.value, null, 2));
  }

  function cancelEdit() {
    setEditingKey(null);
    setEditDraft('');
  }

  async function saveEdit(key: string) {
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(editDraft);
      if (typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error();
    } catch {
      alert('Value must be a valid JSON object');
      return;
    }
    setSaving(true);
    try {
      const r = await fetch(`/api/memories/${encodeURIComponent(key)}`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(parsed),
      });
      if (!r.ok) throw new Error(await r.text());
      setMemories((prev) =>
        prev.map((m) => (m.key === key ? { ...m, value: parsed } : m)),
      );
      cancelEdit();
    } catch (e) {
      alert(`Save failed: ${e}`);
    } finally {
      setSaving(false);
    }
  }

  async function deleteMemory(key: string) {
    setDeleting(key);
    try {
      const r = await fetch(`/api/memories/${encodeURIComponent(key)}`, {
        method: 'DELETE',
        credentials: 'include',
      });
      if (!r.ok) throw new Error(await r.text());
      setMemories((prev) => prev.filter((m) => m.key !== key));
      if (editingKey === key) cancelEdit();
    } catch (e) {
      alert(`Delete failed: ${e}`);
    } finally {
      setDeleting(null);
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[420px] sm:w-[480px] overflow-y-auto">
        <div className="mb-4">
          <SheetTitle className="flex items-center gap-2">
            <Brain className="size-4" />
            Your Memories
          </SheetTitle>
          <p className="mt-1.5 text-xs text-muted-foreground">
            You can edit or delete existing memories, but new ones are created automatically as Kāinga learns your preferences through conversation.
          </p>
        </div>

        {loading && (
          <div className="flex flex-col gap-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-16 rounded-lg" />
            ))}
          </div>
        )}

        {error && (
          <p className="text-sm text-destructive">Failed to load memories: {error}</p>
        )}

        {!loading && !error && memories.length === 0 && (
          <p className="text-sm text-muted-foreground italic">No saved memories yet. Start a conversation to build up your profile.</p>
        )}

        {!loading && !error && memories.length > 0 && (
          <div className="flex flex-col gap-3">
            {memories.map((item) => (
              <div
                key={item.key}
                className="rounded-xl border border-border/60 bg-muted/20 px-4 py-3"
              >
                <div className="flex items-start justify-between gap-2 mb-1.5">
                  <span className="text-sm font-semibold leading-tight">{item.key}</span>
                  <div className="flex items-center gap-1 shrink-0">
                    {editingKey === item.key ? (
                      <>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="size-6"
                          disabled={saving}
                          onClick={() => saveEdit(item.key)}
                        >
                          <Check className="size-3.5" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="size-6"
                          onClick={cancelEdit}
                        >
                          <X className="size-3.5" />
                        </Button>
                      </>
                    ) : (
                      <>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="size-6"
                          onClick={() => startEdit(item)}
                        >
                          <Pencil className="size-3.5" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="size-6 text-destructive hover:text-destructive"
                          disabled={deleting === item.key}
                          onClick={() => deleteMemory(item.key)}
                        >
                          <Trash2 className="size-3.5" />
                        </Button>
                      </>
                    )}
                  </div>
                </div>

                {editingKey === item.key ? (
                  <Textarea
                    className="font-mono text-xs min-h-[120px] mt-1"
                    value={editDraft}
                    onChange={(e) => setEditDraft(e.target.value)}
                    spellCheck={false}
                  />
                ) : (
                  <ValueSummary value={item.value} />
                )}
              </div>
            ))}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
