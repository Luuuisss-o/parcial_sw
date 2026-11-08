# app/ws_manager.py
import asyncio
from typing import Dict, List, Optional
from fastapi import WebSocket

class WSManager:
    """
    Manejador global de WebSockets.
    Registra conexiones por diagrama_id y permite hacer broadcast.
    """

    def __init__(self):
        # Diccionario { diagram_id: [lista de websockets conectados] }
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # Loop principal de FastAPI/uvicorn, capturado en el evento de startup.
        # Lo necesitan las notificaciones disparadas desde endpoints sincronos
        # (corren en un worker thread sin loop propio, ej. el asistente de IA).
        self.main_loop: Optional[asyncio.AbstractEventLoop] = None

    async def connect(self, diagram_id: str, websocket: WebSocket):
        """Registrar nueva conexión en un diagrama"""
        await websocket.accept()
        if diagram_id not in self.active_connections:
            self.active_connections[diagram_id] = []
        self.active_connections[diagram_id].append(websocket)

    def disconnect(self, diagram_id: str, websocket: WebSocket):
        """Eliminar conexión cuando se desconecta"""
        if diagram_id in self.active_connections:
            if websocket in self.active_connections[diagram_id]:
                self.active_connections[diagram_id].remove(websocket)
            if not self.active_connections[diagram_id]:
                del self.active_connections[diagram_id]

    async def broadcast(self, diagram_id: str, message: dict, exclude: Optional[WebSocket] = None):
        """Enviar un mensaje a todos los clientes conectados al diagrama.

        `exclude` sirve para eventos de alta frecuencia como la posicion del
        cursor: cada cliente ya sabe donde esta su propio mouse, asi que
        reenviarselo a si mismo es trafico de mas (y en el caso del cursor,
        haria parpadear el propio puntero con la latencia de ida y vuelta).
        """
        if diagram_id not in self.active_connections:
            return
        dead_connections = []
        for ws in self.active_connections[diagram_id]:
            if ws is exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                dead_connections.append(ws)
        # limpiar conexiones caídas
        for ws in dead_connections:
            self.disconnect(diagram_id, ws)


# Instancia global que se importa en routers
ws_manager = WSManager()
