import { useEffect, useRef, useState } from "react";

import { apiBase } from "../../api/client";
import type { EnrichedTelemetry } from "../../types";

type Transport = "idle" | "websocket" | "sse";

export function useTelemetryStream(token: string | null, onEvent: (event: EnrichedTelemetry) => void) {
  const onEventRef = useRef(onEvent);
  const [transport, setTransport] = useState<Transport>("idle");
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    if (!token) {
      setConnected(false);
      setTransport("idle");
      return undefined;
    }

    let cancelled = false;
    let ws: WebSocket | null = null;
    let sse: EventSource | null = null;
    let retryHandle: number | null = null;
    let attempt = 0;

    const connectSse = () => {
      if (cancelled) {
        return;
      }
      setTransport("sse");
      sse = new EventSource(`${apiBase()}/stream?token=${encodeURIComponent(token)}`);
      sse.onopen = () => {
        setConnected(true);
        attempt = 0;
      };
      sse.onmessage = (message) => {
        try {
          onEventRef.current(JSON.parse(message.data) as EnrichedTelemetry);
        } catch (error) {
          console.error("Failed to parse SSE message", error);
        }
      };
      sse.onerror = () => {
        setConnected(false);
        sse?.close();
        const delay = Math.min(4000, 600 * 2 ** attempt);
        attempt += 1;
        retryHandle = window.setTimeout(connectWebSocket, delay);
      };
    };

    const connectWebSocket = () => {
      if (cancelled) {
        return;
      }
      setTransport("websocket");
      const url = new URL(apiBase().replace(/^http/, "ws"));
      url.pathname = "/ws";
      url.searchParams.set("token", token);
      ws = new WebSocket(url.toString());
      ws.onopen = () => {
        setConnected(true);
        attempt = 0;
      };
      ws.onmessage = (message) => {
        onEventRef.current(JSON.parse(message.data) as EnrichedTelemetry);
      };
      ws.onclose = () => {
        setConnected(false);
        connectSse();
      };
      ws.onerror = () => {
        setConnected(false);
        ws?.close();
      };
    };

    connectWebSocket();

    return () => {
      cancelled = true;
      setConnected(false);
      ws?.close();
      sse?.close();
      if (retryHandle) {
        window.clearTimeout(retryHandle);
      }
    };
  }, [token]);

  return { connected, transport };
}
