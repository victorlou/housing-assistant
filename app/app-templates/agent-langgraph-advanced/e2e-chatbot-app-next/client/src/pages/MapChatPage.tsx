import { useParams } from 'react-router-dom';
import { useSession } from '@/contexts/SessionContext';
import { useChatData } from '@/hooks/useChatData';
import { MapChat } from '@/components/map-chat';

export default function MapChatPage() {
  const { id } = useParams<{ id: string }>();
  const { session } = useSession();
  const { chatData, error } = useChatData(id, !!session?.user);

  if (!session?.user) return null;

  if (error) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <h1 className="mb-4 font-bold text-2xl">Error</h1>
          <p className="text-muted-foreground">{error}</p>
        </div>
      </div>
    );
  }

  if (!id) return null;

  return (
    <MapChat
      key={id}
      id={id}
      initialMessages={chatData?.messages ?? []}
      session={session}
    />
  );
}
