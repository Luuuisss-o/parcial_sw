#models/__init__.py
from .uml import Diagram, Clase, Relacion, Atributo, Metodo, DiagramCollaborator, CollaboratorRole
from .user import User
from .chat import AiProposal, ChatMessage, ChatRole, ProposalStatus

__all__ = [
    "Diagram",
    "Clase",
    "Relacion",
    "Atributo",
    "Metodo",
    "User",
    "DiagramCollaborator",
    "CollaboratorRole",
    "ChatMessage",
    "ChatRole",
]
