import asyncio


async def run_sync(fn):
    return await asyncio.get_running_loop().run_in_executor(None, fn)
