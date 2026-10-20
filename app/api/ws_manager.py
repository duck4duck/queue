from fastapi import WebSocket


class WSManager:
    def __init__(self):
        # Queue-level connections: subject -> list of websockets
        self.connections: dict[str, list[WebSocket]] = {}
        # Personal user connections: tg_id -> list of websockets
        self.user_connections: dict[int, list[WebSocket]] = {}

    # ──────────────────── Queue room WebSockets ────────────────────

    async def connect(self, websocket: WebSocket, subject: str):
        await websocket.accept()
        if subject not in self.connections:
            self.connections[subject] = []
        self.connections[subject].append(websocket)

    def disconnect(self, websocket: WebSocket, subject: str):
        if subject in self.connections:
            if websocket in self.connections[subject]:
                self.connections[subject].remove(websocket)
            if not self.connections[subject]:
                del self.connections[subject]

    async def broadcast(self, subject: str, data: dict):
        if subject not in self.connections:
            return
        dead = []
        for ws in self.connections[subject]:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)

        for ws in dead:
            if ws in self.connections.get(subject, []):
                self.connections[subject].remove(ws)
        if subject in self.connections and not self.connections[subject]:
            del self.connections[subject]

    # ──────────────────── Personal User WebSockets ────────────────────

    async def connect_user(self, websocket: WebSocket, tg_id: int):
        await websocket.accept()
        if tg_id not in self.user_connections:
            self.user_connections[tg_id] = []
        self.user_connections[tg_id].append(websocket)

    def disconnect_user(self, websocket: WebSocket, tg_id: int):
        if tg_id in self.user_connections:
            if websocket in self.user_connections[tg_id]:
                self.user_connections[tg_id].remove(websocket)
            if not self.user_connections[tg_id]:
                del self.user_connections[tg_id]

    async def send_to_user(self, tg_id: int, data: dict):
        if tg_id not in self.user_connections:
            return
        dead = []
        for ws in self.user_connections[tg_id]:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)

        for ws in dead:
            if ws in self.user_connections.get(tg_id, []):
                self.user_connections[tg_id].remove(ws)
        if tg_id in self.user_connections and not self.user_connections[tg_id]:
            del self.user_connections[tg_id]


manager = WSManager()
