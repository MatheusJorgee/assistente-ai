import sys
sys.path.insert(0, '.')
from services.database import Database, Message, Event, Image, get_database
import asyncio
import os

async def test():
    db = Database('backend/data/hook_test.db')
    msg = await db.add_message('session1', 'user', 'test content', {'meta': 'data'})
    stats = await db.get_stats()
    print(f'SUCCESS: Messages={stats["messages_count"]}')

try:
    asyncio.run(test())
except Exception as e:
    print(f'ERROR: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

os.remove('backend/data/hook_test.db')
print('✓ Test complete and database cleaned up')
