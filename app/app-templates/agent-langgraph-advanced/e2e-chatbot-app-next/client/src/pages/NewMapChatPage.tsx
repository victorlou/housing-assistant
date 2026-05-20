import { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { generateUUID } from '@/lib/utils';
import { useSession } from '@/contexts/SessionContext';
import { MapChat } from '@/components/map-chat';

export default function NewMapChatPage() {
  const { session } = useSession();
  const [id, setId] = useState(() => generateUUID());
  const location = useLocation();

  // biome-ignore lint/correctness/useExhaustiveDependencies: re-mount on nav
  useEffect(() => {
    setId(generateUUID());
  }, [location.key]);

  if (!session?.user) return null;

  return (
    <MapChat
      key={id}
      id={id}
      initialMessages={[]}
      session={session}
    />
  );
}
