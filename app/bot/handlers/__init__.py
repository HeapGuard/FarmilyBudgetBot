from aiogram import Router

def setup_routers() -> Router:
    from app.bot.handlers import start, balance, add, report, goals, advice, export, settings, budgets
    root_router = Router()
    root_router.include_router(start.router)
    root_router.include_router(balance.router)
    root_router.include_router(add.router)
    root_router.include_router(report.router)
    root_router.include_router(goals.router)
    root_router.include_router(advice.router)
    root_router.include_router(export.router)
    root_router.include_router(settings.router)
    root_router.include_router(budgets.router)
    return root_router

