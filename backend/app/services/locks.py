# app/services/locks.py
"""
Exclusion mutua a nivel de clase (requisito de la catedra: "hay que resolver
problemas como exclusion mutua, evitar conflictos cuando varios editan a la
vez").

Diseño: bloqueo optimista-pesimista simple. Cuando un usuario selecciona una
clase para editarla, pide el lock por WebSocket; si nadie mas la tiene,
se la queda y todos los demas ven "Cliente esta siendo editada por X" y no
pueden tocarla (ni arrastrarla ni editar sus atributos) hasta que se libere.

Vive en memoria, no en la base: un lock es efimero por diseño (dura lo que
dura la sesion de edicion de un usuario) y este backend corre en un solo
proceso (un worker de uvicorn), asi que no hace falta coordinarlo entre
procesos. Se libera solo, sin timers, en dos casos: el usuario deselecciona
la clase, o su WebSocket se desconecta (cierre de pestaña, F5, caida de red).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from fastapi import WebSocket


@dataclass
class LockInfo:
    email: str
    ws: WebSocket


class LockManager:
    def __init__(self):
        # {diagram_id: {class_id: LockInfo}}
        self._locks: Dict[str, Dict[str, LockInfo]] = {}

    def snapshot(self, diagram_id: str) -> dict[str, dict[str, str]]:
        """{class_id: {email, conn_id}} de todo lo bloqueado en el diagrama,
        para mandarselo a un cliente que recien se conecta."""
        return {
            cid: {"email": info.email, "conn_id": str(id(info.ws))}
            for cid, info in self._locks.get(diagram_id, {}).items()
        }

    def info(self, diagram_id: str, class_id: str) -> Optional[LockInfo]:
        return self._locks.get(diagram_id, {}).get(class_id)

    def acquire(self, diagram_id: str, class_id: str, email: str, ws: WebSocket) -> bool:
        """True si el lock quedo en manos de `ws` (nuevo o ya era suyo).
        False si otra conexion ya lo tiene."""
        room = self._locks.setdefault(diagram_id, {})
        current = room.get(class_id)
        if current is not None and current.ws is not ws:
            return False
        room[class_id] = LockInfo(email=email, ws=ws)
        return True

    def release(self, diagram_id: str, class_id: str, ws: WebSocket) -> bool:
        """True si se libero de verdad (existia y era de esta conexion)."""
        room = self._locks.get(diagram_id)
        if not room or class_id not in room:
            return False
        if room[class_id].ws is not ws:
            return False  # no le pertenece, ignorar en silencio
        del room[class_id]
        if not room:
            del self._locks[diagram_id]
        return True

    def release_all_for(self, diagram_id: str, ws: WebSocket) -> list[str]:
        """Libera todos los locks de esta conexion en el diagrama (al
        desconectarse). Devuelve los class_id liberados, para poder avisar
        por WebSocket a los demas."""
        room = self._locks.get(diagram_id)
        if not room:
            return []
        released = [cid for cid, info in room.items() if info.ws is ws]
        for cid in released:
            del room[cid]
        if not room:
            del self._locks[diagram_id]
        return released


lock_manager = LockManager()
