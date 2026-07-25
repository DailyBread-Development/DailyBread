import asyncio  # noqa: I001
import os

import aiohttp
import uvicorn
from discord.ext import tasks

from bot.bot import create_bot
from bot.utils.config import (
    configure_logging,
    get_discord_token,
    load_environment_variables,
)
from backend.main import app as web_app

# Globals initialized after loading environment variables
PUSH_URL: str | None = None
http_session: aiohttp.ClientSession | None = None


@tasks.loop(seconds=60)
async def send_heartbeat():
    if not PUSH_URL or http_session is None:
        return

    try:
        async with http_session.get(PUSH_URL) as response:
            if response.status == 200:
                print("Heartbeat sent to Uptime Kuma")
            else:
                print(f"Heartbeat failed with status {response.status}")
    except Exception as e:  # noqa: BLE001
        print(f"Failed to send heartbeat: {e}")


def _get_port() -> int:
    return int(os.getenv("PORT", "8000"))


async def start_services() -> None:
    global PUSH_URL, http_session

    # Load configuration first
    load_environment_variables()
    configure_logging()

    PUSH_URL = os.getenv("push_url")  # Use your actual env var name

    http_session = aiohttp.ClientSession()

    if PUSH_URL:
        send_heartbeat.start()
        print("Heartbeat task started.")
    else:
        print("PUSH_URL not configured. Heartbeat disabled.")

    token = get_discord_token()
    bot = create_bot()

    server_config = uvicorn.Config(
        web_app,
        host="0.0.0.0",
        port=_get_port(),
        log_level=os.getenv("LOG_LEVEL", "info"),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )

    web_server = uvicorn.Server(server_config)

    bot_task = asyncio.create_task(bot.start(token))
    web_task = asyncio.create_task(web_server.serve())

    running_tasks = {bot_task, web_task}

    try:
        done, pending = await asyncio.wait(  # noqa: RUF059
            running_tasks,
            return_when=asyncio.FIRST_EXCEPTION,
        )

        for task in done:
            exc = task.exception()
            if exc is not None:
                raise exc

    except asyncio.CancelledError:
        pass

    finally:
        if send_heartbeat.is_running():
            send_heartbeat.stop()

        for task in running_tasks:
            if not task.done():
                task.cancel()

        await asyncio.gather(*running_tasks, return_exceptions=True)

        if not bot.is_closed():
            await bot.close()

        if http_session is not None:
            await http_session.close()


def run_main() -> None:
    asyncio.run(start_services())


if __name__ == "__main__":
    run_main()