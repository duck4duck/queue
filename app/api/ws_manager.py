from fastapi import WebSocket


class WSManager:
    """Manages active WebSocket connections.

    Note: Connection state is currently kept in-process. When horizontally scaling
    to multiple worker processes or instances, a Redis Pub/Sub layer should be used.
    """

    def __init__(self):
        # Queue-level connections: subject -> list of websockets
        self.connections: dict[str, list[WebSocket]] = {}
        # Personal user connections: tg_id -> list of websockets
        self.user_connections: dict[int, list[WebSocket]] = {}

    @staticmethod
    async def _send_and_cleanup(sockets: list[WebSocket], data: dict) -> None:
        """Send JSON data to a list of sockets and prune disconnected ones."""
        dead = []
        for ws in sockets:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in sockets:
                sockets.remove(ws)

    # ──────────────────── Queue room WebSockets ────────────────────

    async def connect(self, websocket: WebSocket, subject: str) -> None:
        await websocket.accept()
        if subject not in self.connections:
            self.connections[subject] = []
        self.connections[subject].append(websocket)

    def disconnect(self, websocket: WebSocket, subject: str) -> None:
        if subject in self.connections:
            if websocket in self.connections[subject]:
                self.connections[subject].remove(websocket)
            if not self.connections[subject]:
                del self.connections[subject]

    async def broadcast(self, subject: str, data: dict) -> None:
        if subject not in self.connections:
            return
        sockets = self.connections[subject]
        await self._send_and_cleanup(sockets, data)
        if not sockets and subject in self.connections:
            del self.connections[subject]

    # ──────────────────── Personal User WebSockets ────────────────────

    async def connect_user(self, websocket: WebSocket, tg_id: int) -> None:
        await websocket.accept()
        if tg_id not in self.user_connections:
            self.user_connections[tg_id] = []
        self.user_connections[tg_id].append(websocket)

    def disconnect_user(self, websocket: WebSocket, tg_id: int) -> None:
        if tg_id in self.user_connections:
            if websocket in self.user_connections[tg_id]:
                self.user_connections[tg_id].remove(websocket)
            if not self.user_connections[tg_id]:
                del self.user_connections[tg_id]

    async def send_to_user(self, tg_id: int, data: dict) -> None:
        if tg_id not in self.user_connections:
            return
        sockets = self.user_connections[tg_id]
        await self._send_and_cleanup(sockets, data)
        if not sockets and tg_id in self.user_connections:
            del self.user_connections[tg_id]

    async def broadcast_all(self, data: dict) -> None:
        """Broadcast an event to all connected users across the application."""
        for tg_id, sockets in list(self.user_connections.items()):
            await self._send_and_cleanup(sockets, data)
            if not sockets and tg_id in self.user_connections:
                del self.user_connections[tg_id]

    async def broadcast_room_and_all(self, subject: str, data: dict) -> None:
        """Convenience method to broadcast to both room and all connected users."""
        await self.broadcast(subject, data)
        await self.broadcast_all(data)


manager = WSManager()
