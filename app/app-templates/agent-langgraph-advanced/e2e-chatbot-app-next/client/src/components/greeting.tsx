import { motion } from 'framer-motion';
import { useSession } from '@/contexts/SessionContext';

const SUGGESTED_PROMPTS = [
  'Best suburbs within 30 min transit of Newmarket under $650 a week',
  'Is Takanini at high flood or coastal risk?',
  'Compare rent and affordability in Avondale and New Lynn',
  'Which suburbs near Manukau have the lowest income deciles?',
];

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
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.22, ease: 'easeOut' }}
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
    </div>
  );
};
