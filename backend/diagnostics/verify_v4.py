"""Verificacao consolidada v4: lembretes, embeddings, musica."""
import sys, time, json
sys.path.insert(0, ".")
from core.proactive import reminders_store

print("=== LEMBRETES PENDENTES ===")
for x in reminders_store.listar_pendentes():
    due = x.get("due_ts")
    falta = round((due - time.time()) / 60, 1) if due else None
    print(f"  id={x['id']} texto={x['texto']!r} anual={x.get('anual_mmdd')} due_em_min={falta}")

print("\n=== VENCIDOS AGORA ===")
for x in reminders_store.vencidos():
    print(f"  id={x['id']} {x['texto']!r}")
