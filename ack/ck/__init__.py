"""Drive a running Creation Kit: load plugins, open cells, select and edit references, move the camera, take
screenshots, generate navmesh, save (checked) and close (never saving). See session.py for what needs the CK in
the foreground, and lifecycle.py for how sessions are kept from overwriting plugins."""
from .session import CKError, CloseResult, CreationKit, RefData, SaveResult, Status

__all__ = ['CKError', 'CloseResult', 'CreationKit', 'RefData', 'SaveResult', 'Status']
