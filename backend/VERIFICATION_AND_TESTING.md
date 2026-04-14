"""
VERIFICATION & TESTING CHECKLIST
=================================

Complete step-by-step guide to verify patches and test the integration.

═══════════════════════════════════════════════════════════════════

## PRE-PATCH VERIFICATION (Before applying any changes)

### ✅ Check 1: Current state of codebase
─────────────────────────────────────────

```powershell
# Verify files exist
Get-Item backend/brain/quinta_feira_brain.py
Get-Item backend/core/gemini_provider.py
Get-Item backend/core/llm_provider.py

# Check MessageHistory is used
Select-String "self.message_history" backend/brain/quinta_feira_brain.py | Measure-Object
```

Expected:
- quinta_feira_brain.py exists ✓
- MessageHistory used ~5-7 times ✓

### ✅ Check 2: New files created
──────────────────────────────────

```powershell
Get-Item backend/core/obsidian_manager.py
Get-Item backend/core/sliding_window_context.py
```

Both should exist before patching brain.py.

### ✅ Check 3: Python environment ready
──────────────────────────────────────

```powershell
# Verify imports work
python -c "from pathlib import Path; print('✓ pathlib')"
python -c "import asyncio; print('✓ asyncio')"
python -c "import json; print('✓ json')"
python -c "from datetime import datetime; print('✓ datetime')"

# Expected: All should succeed with ✓ outputs
```

═══════════════════════════════════════════════════════════════════

## PATCH APPLICATION VERIFICATION

### ⚙️ Step 1: Apply Patch 1 (Imports)
────────────────────────────────────

Edit: backend/brain/quinta_feira_brain.py, Line ~50

VERIFY result:
```python
# After patch, should have:
from core.obsidian_manager import get_obsidian_vault, ObsidianMemory
from core.sliding_window_context import SlidingWindowContextManager, ChatMessage
```

Check:
```powershell
Select-String "from core.obsidian_manager" backend/brain/quinta_feira_brain.py
Select-String "from core.sliding_window_context" backend/brain/quinta_feira_brain.py
```

Expected: Both lines found ✓

### ⚙️ Step 2: Apply Patch 2 (__init__ method)
──────────────────────────────────────────────

Edit: quinsa_feira_brain.py, __init__ method

VERIFY:
```powershell
# Check sliding window initialization
Select-String "SlidingWindowContextManager" backend/brain/quinta_feira_brain.py
```

Expected: Found (shows instantiation with max_active_messages=20) ✓

### ⚙️ Step 3: Apply Patch 3 (initialize method)
─────────────────────────────────────────────────

Edit: quinta_feira_brain.py async def initialize

VERIFY:
```powershell
# Check vault initialization
Select-String "get_obsidian_vault" backend/brain/quinta_feira_brain.py
Select-String "self.vault = await" backend/brain/quinta_feira_brain.py
```

### ⚙️ Step 4: Apply Patch 4 (ask method - MAIN)
────────────────────────────────────────────────

This is the largest patch. After applying:

```powershell
# Check RAG keyword extraction
Select-String "_extract_query_keywords" backend/brain/quinta_feira_brain.py

# Check RAG search
Select-String "search_by_tags" backend/brain/quinta_feira_brain.py

# Check sliding window context
Select-String "context_manager.add_message" backend/brain/quinta_feira_brain.py

# Check removed message handling
Select-String "_handle_removed_messages" backend/brain/quinta_feira_brain.py
```

All 4 should be found ✓

### ⚙️ Step 5: Apply Patch 5 (Helper methods)
──────────────────────────────────────────────

Add 3 new methods before clear_history()

```powershell
# Verify methods exist
Select-String "def _extract_query_keywords" backend/brain/quinta_feira_brain.py
Select-String "def _format_rag_context" backend/brain/quinta_feira_brain.py
Select-String "def _handle_removed_messages" backend/brain/quinta_feira_brain.py
```

All 3 should be found ✓

### ⚙️ Step 6: Apply Patch 6 (clear_history)
─────────────────────────────────────────────

Update method to use context_manager

```powershell
# Verify update
Select-String "context_manager.messages.clear" backend/brain/quinta_feira_brain.py
```

Found ✓

### ⚙️ Step 7: Apply Patch 7 (get_stats)
─────────────────────────────────────────

Update method to include new metrics

```powershell
# Verify new fields
Select-String '"active_window"' backend/brain/quinta_feira_brain.py
Select-String '"estimated_tokens"' backend/brain/quinta_feira_brain.py
Select-String '"vault_available"' backend/brain/quinta_feira_brain.py
```

All 3 should be found ✓

═══════════════════════════════════════════════════════════════════

## SYNTAX VALIDATION

### 🔍 Check 1: Python compilation
──────────────────────────────────

```powershell
# Compile the files
python -m py_compile backend/brain/quinta_feira_brain.py
python -m py_compile backend/core/obsidian_manager.py
python -m py_compile backend/core/sliding_window_context.py

# If no errors, output should be empty
# If syntax errors, you'll see: "SyntaxError: ..."
```

### 🔍 Check 2: Import verification
──────────────────────────────────

```powershell
# Test imports work
cd backend
python -c "from brain.quinta_feira_brain import QuintaFeiraBrain; print('✓ Import successful')"
```

Expected output:
```
✓ Import successful
```

If error:
```
ModuleNotFoundError: No module named 'core.obsidian_manager'
```

Solution: Verify files are in backend/core/ folder

### 🔍 Check 3: Type hints validation
────────────────────────────────────

```powershell
# Optional: Check with mypy (if installed)
pip install mypy
cd backend
mypy brain/quinta_feira_brain.py --ignore-missing-imports

# Expected: No errors (or very few harmless ones)
```

═══════════════════════════════════════════════════════════════════

## RUNTIME VALIDATION

### 🚀 Check 1: Start backend with new code
─────────────────────────────────────────────

```powershell
cd backend
uvicorn main:app --reload --log-level debug

# Watch for startup errors
# Expected logs:
# INFO:     Started server process [1234]
# [BRAIN] ✓ Inicializado com sucesso (Obsidian + SlidingWindow)
# [BRAIN] Obsidian Vault ready: {...}
```

### 🚀 Check 2: Test Obsidian vault creation
──────────────────────────────────────────────

```powershell
# Should see vault created
Get-Item -Force backend\.vault\ -ErrorAction SilentlyContinue

# Check structure
Get-ChildItem -Path backend\.vault\ -Recurse

# Expected:
# 00-Meta/
# Memorias/
# Conversas/
# Resumos/
# README.md
```

### 🚀 Check 3: Send test query via API
──────────────────────────────────────

```powershell
# In another terminal, make HTTP request
$body = @{
    message = "Olá, como vai?"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/ask" `
    -Method POST `
    -Body $body `
    -ContentType "application/json"

# Expected response:
# {
#   "text": "Resposta...",
#   "audio": "",
#   "mode": "responding",
#   "timestamp": "2024-..."
# }
```

### 🚀 Check 4: Verify sliding window in action
──────────────────────────────────────────────

Send 30 consecutive messages:

```python
# backend/scripts/test_ask_30_msgs.py
import httpx
import asyncio

async def send_30_messages():
    async with httpx.AsyncClient() as client:
        for i in range(30):
            response = await client.post(
                "http://localhost:8000/ask",
                json={"message": f"Test message {i+1}"},
                timeout=30.0,
            )
            print(f"Msg {i+1}: {response.status_code}")
            await asyncio.sleep(0.5)

asyncio.run(send_30_messages())
```

Expected:
- All 30 requests succeed
- Backend logs show "added to context"
- Some messages show "removed from active window"
- Final context_manager has ~20 messages

### 🚀 Check 5: Verify RAG search
────────────────────────────────

```python
# backend/scripts/test_rag.py
import asyncio
from core.obsidian_manager import get_obsidian_vault
from core.sliding_window_context import SlidingWindowContextManager

async def test_rag():
    vault = await get_obsidian_vault()
    
    # Add some test memories
    from core.obsidian_manager import ObsidianMemory
    mem = ObsidianMemory(
        title="Test Memory",
        content="This is about Python programming",
        categoria="Memorias",
        tags=["python", "programacao", "test"],
    )
    await vault.save_memory(mem)
    
    # Search for it
    results = await vault.search_by_tags(
        keywords=["python"],
        categoria="Memorias",
        limit=5,
    )
    
    print(f"✓ Found {len(results)} results for 'python'")
    if results:
        print(f"  First result: {results[0].title}")

asyncio.run(test_rag())
```

Expected output:
```
✓ Found 1 results for 'python'
  First result: Test Memory
```

═══════════════════════════════════════════════════════════════════

## INTEGRATION TESTS

### 📋 Test 1: Full conversation flow
───────────────────────────────────

Scenario:
1. User asks question 1
2. Assistant responds
3. User asks related question 2
4. Assistant uses RAG to reference earlier context

```python
# backend/scripts/test_conversation_flow.py
import asyncio
import httpx

async def test_flow():
    base_url = "http://localhost:8000"
    
    # Q1: About Python
    q1 = httpx.post(
        f"{base_url}/ask",
        json={"message": "I like Python programming"},
    )
    print(f"Q1 Response: {q1.json()['text'][:100]}...")
    
    await asyncio.sleep(1)
    
    # Q2: Related question
    q2 = httpx.post(
        f"{base_url}/ask",
        json={"message": "What's your favorite feature of it?"},
    )
    print(f"Q2 Response: {q2.json()['text'][:100]}...")
    
    # Check backend logs for RAG hit
    print("\\n✓ Check logs for: '[BRAIN] RAG: Found X relevant memories'")

asyncio.run(test_flow())
```

### 📋 Test 2: Verify token reduction
──────────────────────────────────────

Compare token usage before/after:

BEFORE (old code):
```
[LLM] 50 messages × 400 chars = 20k chars ≈ 8k tokens
Per call cost ≈ R$ 0.10
```

AFTER (new code):
```
[LLM] 20 messages × 200 chars = 4k chars
    + 5 RAG memories × 200 chars = 1k chars
    Total ≈ 5k chars ≈ 2k tokens
Per call cost ≈ R$ 0.02
```

To measure (requires Gemini API logging):
```python
# backend/scripts/measure_tokens.py
import httpx
import re

def measure_tokens_per_call(n_calls=10):
    for i in range(n_calls):
        response = httpx.post(
            "http://localhost:8000/ask",
            json={"message": f"Test query {i}"},
        )
        # Parse response headers or logs for token count
        # Expected: 2000-3000 tokens vs previous 8000-10000

asyncio.run(measure_tokens_per_call())
```

### 📋 Test 3: Sliding window overflow
──────────────────────────────────────

```python
# Verify messages are summarized when removed
import httpx

for i in range(35):  # More than 20 (max active)
    response = httpx.post(
        "http://localhost:8000/ask",
        json={"message": f"Message {i+1}"},
    )
    if i % 5 == 0:
        print(f"✓ Message {i+1} processed")

# Check backend logs:
# Should see:
# - "Summarized chunk X/Y saved to Obsidian"
# - New files in backend/.vault/Resumos/

print("✓ Check backend/.vault/Resumos/ for auto-generated summaries")
```

═══════════════════════════════════════════════════════════════════

## ERROR SCENARIOS & FIXES

### ❌ Error 1: ImportError - no module 'core.obsidian_manager'
──────────────────────────────────────────────────────────────

Cause: Files not in right location
Fix:
```powershell
# Verify files exist
Get-Item backend/core/obsidian_manager.py
Get-Item backend/core/sliding_window_context.py

# Check __init__.py exports (if needed)
# Or verify imports are in brain.py are correctly spelled
```

### ❌ Error 2: RuntimeError - Vault not initialized
────────────────────────────────────────────────────

Cause: initialize() not called or failed
Fix:
```python
# In brain initialization, ensure:
await brain.initialize()  # Call this before asking questions

# Or debug vault creation:
import asyncio
from core.obsidian_manager import get_obsidian_vault
vault = asyncio.run(get_obsidian_vault())
```

### ❌ Error 3: KeyError - 'active_messages' in get_stats()
──────────────────────────────────────────────────────────

Cause: SlidingWindowContextManager method not returning expected dict
Fix:
```python
# Verify method signature matches:
from core.sliding_window_context import SlidingWindowContextManager

manager = SlidingWindowContextManager()
info = manager.get_context_info()

# Should return dict with keys:
# 'active_messages', 'estimated_tokens', 'total_messages'
print(info.keys())
```

### ❌ Error 4: TypeError - can't use x as context manager
──────────────────────────────────────────────────────────

Cause: Trying to use async function without await
Fix:
```python
# Check all calls to vault/manager are awaited:

# WRONG:
vault = get_obsidian_vault()  # ✗ No await

# RIGHT:
vault = await get_obsidian_vault()  # ✓ Has await
```

═══════════════════════════════════════════════════════════════════

## FINAL VERIFICATION CHECKLIST

Before considering migration complete:

- [ ] ✅ Python syntax valid (py_compile passes)
- [ ] ✅ Imports work (can import QuintaFeiraBrain)
- [ ] ✅ Backend starts without errors
- [ ] ✅ Obsidian vault folder created automatically
- [ ] ✅ Can send ask() request successfully
- [ ] ✅ Sliding window keeps ~20 messages (tested with 30 msgs)
- [ ] ✅ RAG search finds relevant memories
- [ ] ✅ get_stats() returns all expected fields
- [ ] ✅ Token usage reduced (estimated 60%+ savings)
- [ ] ✅ Conversation flows work end-to-end
- [ ] ✅ Browser frontend still works and receives responses
- [ ] ✅ .vault/ folder has proper structure

## SAFE HANDOFF CRITERIA

✅ System is production-ready when:
1. All 12 items above pass
2. 1+ hour of stability testing (50+ requests)
3. No new errors in logs
4. Obsidian vault has 10+ memory files

At this point: COMMIT AND DEPLOY WITH CONFIDENCE! 🚀

═══════════════════════════════════════════════════════════════════

## COMMANDS QUICK REFERENCE

```powershell
# Test syntax
python -m py_compile backend/brain/quinta_feira_brain.py

# Test imports
cd backend; python -c "from brain.quinta_feira_brain import QuintaFeiraBrain; print('OK')"

# Start backend
cd backend; uvicorn main:app --reload

# Run verification scripts
python scripts/test_rag_search.py
python scripts/test_sliding_window.py
python scripts/test_ask_30_msgs.py

# Check vault structure
Get-ChildItem -Path backend\.vault\ -Recurse

# Monitor logs
Get-Content backend/logs/*.log -Tail 50 -Wait

# Measure vault size
(Get-ChildItem -Path backend\.vault\ -Recurse | Measure-Object -Sum Length).Sum / 1MB
```
"""
