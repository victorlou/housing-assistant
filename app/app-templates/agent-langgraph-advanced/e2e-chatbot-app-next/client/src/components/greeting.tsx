import { motion } from 'framer-motion';
import { Lightbulb } from 'lucide-react';
import { useSession } from '@/contexts/SessionContext';
import kaingaLogoUrl from '@/assets/kainga-logo.svg';

const SUGGESTED_PROMPTS = [
  'Best suburbs within 30 min transit of Newmarket under $650 a week',
  'Is Takanini at high flood or coastal risk?',
  'Compare rent and affordability in Avondale and New Lynn',
  'Which suburbs near Manukau have the lowest income deciles?',
];

const VIZ_TIP_PROMPT = 'Compare Onehunga, Avondale, and Glen Innes by rent and flood risk — show me a diagram';

function getGreeting(name: string | null | undefined): string {
  const hour = new Date().getHours();
  const timeOfDay = hour < 12 ? 'morning' : hour < 17 ? 'afternoon' : 'evening';
  const firstName = name?.split(' ')[0];
  return firstName ? `Good ${timeOfDay}, ${firstName}` : 'What would you like to know?';
}

export const Greeting = ({ onSend }: { onSend?: (text: string) => void }) => {
  const { session } = useSession();
  const displayName = session?.user?.preferredUsername ?? session?.user?.name;
  const greeting = getGreeting(displayName);

  return (
    <div
      key="overview"
      className="mx-auto flex size-full max-w-3xl flex-col justify-center gap-6 px-4 mb-6"
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.92 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.28, ease: 'easeOut' }}
        className="flex justify-center"
      >
        <img
          src={kaingaLogoUrl}
          alt="Kāinga"
          className="w-28 h-28 rounded-2xl"
          draggable={false}
        />
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.22, ease: 'easeOut', delay: 0.08 }}
        className="font-semibold text-lg md:text-xl text-center"
      >
        {greeting}
      </motion.div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {SUGGESTED_PROMPTS.map((prompt, i) => (
          <motion.button
            key={prompt}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.18, ease: 'easeOut', delay: 0.1 + i * 0.07 }}
            type="button"
            onClick={() => onSend?.(prompt)}
            className="text-left rounded-xl border border-border bg-secondary/60 px-4 py-3 text-sm text-muted-foreground hover:bg-secondary hover:text-foreground hover:border-primary/30 transition-colors duration-150 cursor-pointer"
          >
            {prompt}
          </motion.button>
        ))}
      </div>

      <motion.button
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.18, ease: 'easeOut', delay: 0.42 }}
        type="button"
        onClick={() => onSend?.(VIZ_TIP_PROMPT)}
        className="w-full text-left rounded-xl border border-primary/20 bg-primary/5 px-4 py-3 hover:bg-primary/10 hover:border-primary/40 transition-colors duration-150 cursor-pointer"
      >
        <div className="flex items-start gap-3">
          <Lightbulb className="size-4 mt-0.5 shrink-0 text-primary/70" />
          <div className="space-y-0.5">
            <p className="text-xs font-semibold text-primary/80 uppercase tracking-wide">Tip — try a visualization</p>
            <p className="text-sm text-muted-foreground">
              Ask Kāinga to compare suburbs with a diagram — e.g.{' '}
              <span className="text-foreground font-medium">
                "Compare Onehunga, Avondale, and Glen Innes by rent and flood risk — show me a diagram"
              </span>
            </p>
          </div>
        </div>
      </motion.button>
    </div>
  );
};
