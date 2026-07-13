import asyncio
from mcq_crawler.browser import BrowserRuntime
from mcq_crawler.config import RunConfig, DEFAULT_SELECTOR_PROFILE
from mcq_crawler.models import RuntimeState

async def main():
    state = RuntimeState(max_records=5, next_index=1)
    cfg = RunConfig(start_url='about:blank', headless=True, max_records=5, max_turns=5)
    runtime = BrowserRuntime(cfg, DEFAULT_SELECTOR_PROFILE, state)
    await runtime.start()
    print('started')
    await runtime.stop()
    print('stopped')

asyncio.run(main())
