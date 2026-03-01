from fastapi import WebSocket
import json

class WSManager:
    def __init__(self):
        self.connections: dict[str,list[WebSocket]] = {}

    async def connect(self,websocket: WebSocket,subject: str,):
        await websocket.accept()
        if subject not in self.connections:
            self.connections[subject] = []
        self.connections[subject].append(websocket)

    def disconnect(self,websoket: WebSocket,subject: str):
        if subject in self.connections:
            self.connections[subject].remove(websoket)
        if not self.connections[subject]:
            del self.connections[subject]

    async def broadcast(self,subject: str,data: dict):
        if subject not in self.connections:
            return
        dead = []
        for ws in self.connections[subject]:
            try:
                await ws.send_json(data)

            except Exception:
                dead.append(ws)

        for ws in dead:
            self.connections[subject].remove(ws)


manager = WSManager()