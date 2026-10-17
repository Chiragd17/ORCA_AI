import sys
import asyncio
import pytest

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

@pytest.fixture(scope='session')
def event_loop():
    if sys.platform == 'win32':
        loop = asyncio.WindowsSelectorEventLoopPolicy().new_event_loop()
    else:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()
