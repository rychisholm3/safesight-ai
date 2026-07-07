import { useEffect, useRef } from "react";
import type { SafeEvent } from "../types";
import { WS_URL } from "../lib/api";

type WsMessage =
  | { type: "history"; events: SafeEvent[] }
  | { type: "event"; action: "opened" | "closed"; event: SafeEvent };

interface Handlers {
  onHistory: (events: SafeEvent[]) => void;
  onOpened: (event: SafeEvent) => void;
  onClosed: (event: SafeEvent) => void;
}

export function useWebSocket(handlers: Handlers) {
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  useEffect(() => {
    let ws: WebSocket;
    let reconnectTimer: ReturnType<typeof setTimeout>;

    function connect() {
      ws = new WebSocket(WS_URL);

      ws.onmessage = (e) => {
        const msg: WsMessage = JSON.parse(e.data);
        if (msg.type === "history") {
          handlersRef.current.onHistory(msg.events);
        } else if (msg.type === "event") {
          if (msg.action === "opened") handlersRef.current.onOpened(msg.event);
          else handlersRef.current.onClosed(msg.event);
        }
      };

      ws.onclose = () => {
        reconnectTimer = setTimeout(connect, 3000);
      };
    }

    connect();
    return () => {
      clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, []);
}
