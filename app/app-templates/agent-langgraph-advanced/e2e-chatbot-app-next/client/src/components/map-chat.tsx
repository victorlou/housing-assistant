import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useChat } from '@ai-sdk/react';
import type { DataUIPart, LanguageModelUsage, UIMessageChunk } from 'ai';
import { useSWRConfig } from 'swr';
import { fetchWithErrorHandlers, generateUUID } from '@/lib/utils';
import { MultimodalInput } from './multimodal-input';
import { Messages } from './messages';
import type { Attachment, ChatMessage, CustomUIDataTypes } from '@chat-template/core';
import { unstable_serialize } from 'swr/infinite';
import { getChatHistoryPaginationKey } from './sidebar-history';
import { toast } from './toast';
import { ChatSDKError } from '@chat-template/core/errors';
import { useDataStream } from './data-stream-provider';
import { isCredentialErrorMessage } from '@/lib/oauth-error-utils';
import { ChatTransport } from '../lib/ChatTransport';
import type { ClientSession } from '@chat-template/auth';
import { useAppConfig } from '@/contexts/AppConfigContext';
import { MapPanel } from './map-panel';
import { SuburbInfoPanel } from './suburb-info-panel';
import { useMapState } from '@/contexts/MapContext';
import { Map as MapIcon, MessageSquare } from 'lucide-react';

export function MapChat({
  id,
  initialMessages,
  session,
}: {
  id: string;
  initialMessages: ChatMessage[];
  session: ClientSession;
}) {
  const { mutate } = useSWRConfig();
  const { setDataStream } = useDataStream();
  const { chatHistoryEnabled } = useAppConfig();
  const mapState = useMapState();

  const [input, setInput] = useState('');
  const [attachments, setAttachments] = useState<Attachment[]>([]);

  const lastPartRef = useRef<UIMessageChunk | undefined>(undefined);
  const resumeAttemptCountRef = useRef(0);
  const maxResumeAttempts = 3;

  const abortController = useRef<AbortController | null>(new AbortController());
  useEffect(() => {
    return () => {
      abortController.current?.abort('ABORT_SIGNAL');
    };
  }, []);

  const fetchWithAbort = useMemo(
    () =>
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const signal = abortController.current?.signal;
        return fetchWithErrorHandlers(input, { ...init, signal });
      },
    [],
  );

  const stop = useCallback(() => {
    abortController.current?.abort('USER_ABORT_SIGNAL');
  }, []);

  const isNewChat = initialMessages.length === 0;
  const didFetchHistoryOnNewChat = useRef(false);
  const fetchChatHistory = useCallback(() => {
    mutate(unstable_serialize(getChatHistoryPaginationKey));
  }, [mutate]);

  const {
    messages,
    setMessages,
    sendMessage,
    status,
    resumeStream,
    clearError,
    addToolApprovalResponse,
    regenerate,
  } = useChat<ChatMessage>({
    id,
    messages: initialMessages,
    experimental_throttle: 100,
    generateId: generateUUID,
    resume: id !== undefined && initialMessages.length > 0,
    transport: new ChatTransport({
      onStreamPart: (part) => {
        if (isNewChat && !didFetchHistoryOnNewChat.current) {
          fetchChatHistory();
          didFetchHistoryOnNewChat.current = true;
        }
        resumeAttemptCountRef.current = 0;
        lastPartRef.current = part;
      },
      api: '/api/chat',
      fetch: fetchWithAbort,
      prepareSendMessagesRequest({ messages, id, body }) {
        const lastMessage = messages.at(-1);
        const isUserMessage = lastMessage?.role === 'user';
        const needsPreviousMessages = !chatHistoryEnabled || !isUserMessage;

        return {
          body: {
            id,
            ...(isUserMessage ? { message: lastMessage } : {}),
            selectedChatModel: 'chat-model',
            selectedVisibilityType: 'private',
            mode: 'map',
            ...(needsPreviousMessages
              ? {
                  previousMessages: isUserMessage
                    ? messages.slice(0, -1)
                    : messages,
                }
              : {}),
            ...body,
          },
        };
      },
      prepareReconnectToStreamRequest({ id }) {
        return {
          api: `/api/chat/${id}/stream`,
          credentials: 'include',
        };
      },
    }),
    onData: (dataPart) => {
      setDataStream((ds) =>
        ds ? [...ds, dataPart as DataUIPart<CustomUIDataTypes>] : [],
      );
    },
    onFinish: ({ isAbort, isDisconnect, isError, messages: finishedMessages }) => {
      didFetchHistoryOnNewChat.current = false;

      if (isAbort) {
        fetchChatHistory();
        return;
      }

      const lastMessage = finishedMessages?.at(-1);
      const hasOAuthError = lastMessage?.parts?.some(
        (part) =>
          part.type === 'data-error' &&
          typeof part.data === 'string' &&
          isCredentialErrorMessage(part.data),
      );

      if (hasOAuthError) {
        fetchChatHistory();
        clearError();
        return;
      }

      const streamIncomplete = lastPartRef.current?.type !== 'finish';
      const shouldResume =
        streamIncomplete &&
        (isDisconnect || isError || lastPartRef.current === undefined);

      if (shouldResume && resumeAttemptCountRef.current < maxResumeAttempts) {
        resumeAttemptCountRef.current++;
        queueMicrotask(() => {
          resumeStream();
        });
      } else {
        fetchChatHistory();
      }
    },
    onError: (error) => {
      if (error instanceof ChatSDKError) {
        toast({ type: 'error', description: error.message });
      } else {
        console.warn('[MapChat onError]', error.message);
      }
    },
  });

  const hasSuburbs = mapState.suburbs.length > 0;
  const highlightedSuburb = mapState.suburbs.find((s) => s.status === 'highlighted');

  return (
    <div className="flex h-dvh overflow-hidden bg-background">
      {/* Map panel — left side */}
      <div className="relative flex-1 min-w-0">
        <MapPanel />

        {/* Filter summary legend */}
        {mapState.filterSummary && (
          <div className="absolute bottom-4 left-1/2 z-[1000] -translate-x-1/2 rounded-full border border-border bg-background/90 px-4 py-1.5 text-sm text-foreground shadow-md backdrop-blur-sm">
            {mapState.filterSummary}
          </div>
        )}

        {/* Suburb info panel — overlays map when a suburb is highlighted */}
        {highlightedSuburb && (
          <div className="absolute right-4 top-4 z-[1000] w-72">
            <SuburbInfoPanel suburbName={highlightedSuburb.name} />
          </div>
        )}

        {/* Map mode badge */}
        <div className="absolute left-4 top-4 z-[1000] flex items-center gap-1.5 rounded-full border border-border bg-background/90 px-3 py-1 text-xs font-medium text-foreground shadow-sm backdrop-blur-sm">
          <MapIcon className="size-3 text-primary" />
          Map Mode
        </div>
      </div>

      {/* Chat panel — right side, fixed width */}
      <div className="flex w-[380px] shrink-0 flex-col border-l border-border bg-background">
        {/* Header */}
        <div className="flex items-center gap-2 border-b border-border px-4 py-3">
          <MessageSquare className="size-4 text-muted-foreground" />
          <span className="text-sm font-medium">
            {hasSuburbs
              ? `${mapState.suburbs.filter((s) => s.status === 'active').length} suburbs active`
              : 'Describe your needs'}
          </span>
        </div>

        {/* Messages */}
        <div className="min-h-0 flex-1 overflow-hidden">
          <Messages
            status={status}
            messages={messages}
            setMessages={setMessages}
            addToolApprovalResponse={addToolApprovalResponse}
            regenerate={regenerate}
            sendMessage={sendMessage}
            isReadonly={false}
            selectedModelId="chat-model"
            feedback={{}}
          />
        </div>

        {/* Input */}
        <div className="border-t border-border px-3 pb-3 pt-2">
          <MultimodalInput
            chatId={id}
            input={input}
            setInput={setInput}
            status={status}
            stop={stop}
            attachments={attachments}
            setAttachments={setAttachments}
            messages={messages}
            setMessages={setMessages}
            sendMessage={sendMessage}
            selectedVisibilityType="private"
          />
        </div>
      </div>
    </div>
  );
}
