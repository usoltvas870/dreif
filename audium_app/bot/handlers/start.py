from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from audium_app.core.config import settings

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        f"Привет! Audium — звуковой wellness-сервис.\n\n"
        f"Перейди на сайт, чтобы начать 3-дневный триал:\n"
        f"{settings.app_base_url}"
    )
