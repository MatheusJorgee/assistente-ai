'use client';

import { useQuintaFeiraUI } from '@/hooks/useQuintaFeiraUI';
import { VoiceOrb } from '@/components/ui/VoiceOrb';
import { ChatOverlay } from '@/components/ui/ChatOverlay';
import { ControlDeck } from '@/components/ui/ControlDeck';
import { MediaPlayer } from '@/components/MediaPlayer';

export default function Page() {
  const {
    messages,
    isConnected,
    connectionStatus,
    isLoading,
    intermediateStatus,
    error,
    activeMedia,
    clearMedia,
    orbState,
    isMuted,
    isChatOpen,
    input,
    setInput,
    handleSend,
    toggleMute,
    toggleChat,
    scrollEndRef,
  } = useQuintaFeiraUI();

  return (
    <div className="h-screen w-full bg-zinc-950 text-white flex overflow-hidden">
      <ChatOverlay
        isVisible={isChatOpen}
        messages={messages}
        isLoading={isLoading}
        intermediateStatus={intermediateStatus}
        error={error}
        isConnected={isConnected}
        input={input}
        onInputChange={setInput}
        onSend={handleSend}
        scrollEndRef={scrollEndRef}
      />

      <div className="flex-1 flex flex-col items-center justify-between">
        <div className="flex-1 flex items-center justify-center">
          <VoiceOrb state={orbState} />
        </div>

        <ControlDeck
          isMuted={isMuted}
          isChatOpen={isChatOpen}
          isConnected={isConnected}
          connectionStatus={connectionStatus}
          onToggleMute={toggleMute}
          onToggleChat={toggleChat}
        />
      </div>

      <MediaPlayer media={activeMedia} onClose={clearMedia} />
    </div>
  );
}
