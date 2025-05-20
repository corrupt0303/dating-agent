import { useTrackTranscription, useVoiceAssistant } from "@livekit/components-react";
import { useMemo, useEffect, useRef } from "react";
import useLocalMicTrack from "./useLocalMicTrack";

export default function useCombinedTranscriptions() {
  const { agentTranscriptions } = useVoiceAssistant();
  const micTrackRef = useLocalMicTrack();
  const { segments: userTranscriptions } = useTrackTranscription(micTrackRef);
  const openedUrls = useRef<Set<string>>(new Set());

  // Intercept agent transcriptions for open_url actions
  useEffect(() => {
    agentTranscriptions.forEach((segment) => {
      let parsed: any;
      try {
        parsed = typeof segment.text === "string" ? JSON.parse(segment.text) : segment.text;
      } catch {
        parsed = null;
      }
      if (
        parsed &&
        parsed.action === "open_url" &&
        parsed.url &&
        typeof window !== "undefined" &&
        !openedUrls.current.has(parsed.url)
      ) {
        window.open(parsed.url, "_blank");
        openedUrls.current.add(parsed.url);
      }
    });
  }, [agentTranscriptions]);

  const combinedTranscriptions = useMemo(() => {
    // Only display the message for open_url actions
    const processedAgentTranscriptions = agentTranscriptions.map((segment) => {
      let parsed: any;
      try {
        parsed = typeof segment.text === "string" ? JSON.parse(segment.text) : segment.text;
      } catch {
        parsed = null;
      }
      if (parsed && parsed.action === "open_url" && parsed.message) {
        return { ...segment, text: parsed.message };
      }
      return { ...segment, role: "assistant" };
    });
    const processedUserTranscriptions = userTranscriptions.map((val) => {
      return { ...val, role: "user" };
    });
    return [
      ...processedAgentTranscriptions,
      ...processedUserTranscriptions,
    ].sort((a, b) => a.firstReceivedTime - b.firstReceivedTime);
  }, [agentTranscriptions, userTranscriptions]);

  return combinedTranscriptions;
}
