import { motion } from 'framer-motion';
import { Bookmark } from 'lucide-react';

export default function SavedSearchesPage() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      className="flex h-full flex-col items-center justify-center gap-3 text-center px-4"
    >
      <Bookmark className="size-8 text-muted-foreground/40" />
      <div>
        <p className="font-medium text-foreground">Saved Searches</p>
        <p className="text-sm text-muted-foreground mt-1">
          Save suburb recommendations from your chats to review them here.
        </p>
      </div>
    </motion.div>
  );
}
