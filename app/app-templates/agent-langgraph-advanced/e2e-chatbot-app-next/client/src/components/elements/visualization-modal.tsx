import React, { useEffect, useId, useRef, useState } from 'react';
import mermaid from 'mermaid';
import { Download, BarChart2, ChevronUp, ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

/**
 * Pre-process mermaid code to fix common LLM-generated syntax issues before
 * passing to the renderer. Specifically: node labels like [text] that contain
 * special chars ( ) + ~ / % must be wrapped in double quotes per Mermaid spec.
 */
function sanitizeMermaidCode(code: string): string {
  return (
    code
      .trim()
      // Wrap unquoted [...] node labels in double quotes when they contain
      // special chars that Mermaid's lexer treats as shape tokens.
      .replace(/\[([^"\]\[]+)\]/g, (_, inner: string) => {
        if (/[()~+/%&`]/.test(inner)) {
          const escaped = inner.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
          return `["${escaped}"]`;
        }
        return `[${inner}]`;
      })
      // Same treatment for (...) rounded-rect labels
      .replace(/\(([^"()]+)\)/g, (_, inner: string) => {
        if (/[()~+/%&`]/.test(inner)) {
          const escaped = inner.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
          return `("${escaped}")`;
        }
        return `(${inner})`;
      })
  );
}

type VisualizationCardProps = {
  title: string;
  mermaidCode: string;
  description: string;
};

export function VisualizationCard({
  title,
  mermaidCode,
  description,
}: VisualizationCardProps) {
  const diagramRef = useRef<HTMLDivElement>(null);
  const rawId = useId();
  const diagramId = `mermaid-${rawId.replace(/[^a-zA-Z0-9]/g, '')}`;
  const [renderError, setRenderError] = useState<string | null>(null);
  const [isRendering, setIsRendering] = useState(true);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    if (!diagramRef.current || !mermaidCode) return;

    const isDark = document.documentElement.classList.contains('dark');

    mermaid.initialize({
      startOnLoad: false,
      theme: isDark ? 'dark' : 'default',
      securityLevel: 'loose',
    });

    setIsRendering(true);
    setRenderError(null);

    const sanitized = sanitizeMermaidCode(mermaidCode);

    mermaid
      .render(diagramId, sanitized)
      .then(({ svg }) => {
        if (diagramRef.current) {
          diagramRef.current.innerHTML = svg;
          const svgEl = diagramRef.current.querySelector('svg');
          if (svgEl) {
            svgEl.removeAttribute('height');
            svgEl.style.width = '100%';
            svgEl.style.maxWidth = '100%';
          }
        }
      })
      .catch((err) => {
        setRenderError(String(err?.message ?? err));
      })
      .finally(() => {
        setIsRendering(false);
      });
  }, [mermaidCode, diagramId]);

  // Silently suppress failed renders — don't show error cards in chat
  if (!isRendering && renderError) return null;

  function handleDownload() {
    const svgEl = diagramRef.current?.querySelector('svg');
    if (!svgEl) return;

    // Use actual rendered dimensions — img.width is 0 for SVGs without explicit attrs
    const bbox = svgEl.getBoundingClientRect();
    const naturalW = Math.round(bbox.width) || 1200;
    const naturalH = Math.round(bbox.height) || 600;
    const scale = 2; // 2× for crisp retina output

    // Clone and stamp explicit dimensions so the browser decodes at the right size
    const clone = svgEl.cloneNode(true) as SVGSVGElement;
    clone.setAttribute('width', String(naturalW));
    clone.setAttribute('height', String(naturalH));
    const svgData = new XMLSerializer().serializeToString(clone);
    const svgUrl = `data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(svgData)))}`;

    const canvas = document.createElement('canvas');
    canvas.width = naturalW * scale;
    canvas.height = naturalH * scale;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const img = new Image();
    img.onload = () => {
      ctx.scale(scale, scale);
      ctx.drawImage(img, 0, 0, naturalW, naturalH);
      const a = document.createElement('a');
      a.download = `${title.replace(/\s+/g, '-').toLowerCase()}.png`;
      a.href = canvas.toDataURL('image/png');
      a.click();
    };
    img.src = svgUrl;
  }

  return (
    <div className="my-2 rounded-xl border bg-muted/30">
      {/* Header */}
      <div className={cn(
        'flex items-center gap-2 px-4 py-2.5 bg-background/60',
        collapsed ? 'rounded-xl' : 'border-b rounded-t-xl',
      )}>
        <BarChart2 className="size-4 shrink-0 text-primary" />
        <span className="flex-1 text-sm font-medium truncate">{title}</span>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleDownload}
          disabled={isRendering || collapsed}
          className="gap-1 text-xs h-7 px-2 text-muted-foreground hover:text-foreground"
        >
          <Download className="size-3" />
          PNG
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="size-7 text-muted-foreground hover:text-foreground"
          onClick={() => setCollapsed((c) => !c)}
          title={collapsed ? 'Expand diagram' : 'Collapse diagram'}
        >
          {collapsed
            ? <ChevronDown className="size-3.5" />
            : <ChevronUp className="size-3.5" />}
        </Button>
      </div>

      {/* Diagram body — stays mounted so the SVG is preserved across collapse/expand */}
      <div className={cn('px-4 py-4', collapsed && 'hidden')}>
        {isRendering && (
          <div className="flex items-center gap-2 py-8 justify-center text-muted-foreground text-sm">
            <div className="size-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
            Rendering diagram…
          </div>
        )}
        <div
          ref={diagramRef}
          className={cn('w-full', isRendering && 'hidden')}
        />
        {description && !isRendering && (
          <p className="mt-3 text-xs text-muted-foreground">{description}</p>
        )}
      </div>
    </div>
  );
}

// Alias so message.tsx import doesn't need updating
export const VisualizationModalTrigger = VisualizationCard;
