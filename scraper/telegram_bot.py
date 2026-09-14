"""Telegram bot for family account subscriptions and IPO alerts."""

from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


def get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Supabase credentials are set, but the optional 'supabase' package is not installed. "
            "Install scraper/requirements-supabase.txt."
        ) from exc
    return create_client(url, key)


def _account_name_for_id(supabase, account_id: str | int) -> str:
    if supabase is None:
        return "family account"
    try:
        response = supabase.table("accounts").select("id,name").eq("id", int(account_id)).execute()
    except Exception:
        return "family account"
    rows = getattr(response, "data", []) or []
    if not rows:
        return "family account"
    return str(rows[0].get("name") or "family account")


def _signal_summary_for_account(supabase, account_id: int) -> str:
    if supabase is None:
        return "No holdings summary available."
    holdings = supabase.table("holdings").select("symbol,quantity").eq("account_id", account_id).execute()
    rows = getattr(holdings, "data", []) or []
    if not rows:
        return "No holdings in this account yet."

    symbols = [str(row.get("symbol") or "").upper() for row in rows if row.get("symbol")]
    if not symbols:
        return "No holdings in this account yet."

    signals = supabase.table("symbol_signal").select("symbol,label,note").in_("symbol", symbols).execute()
    signal_map = {
        str(item.get("symbol") or "").upper(): item for item in (getattr(signals, "data", []) or [])
    }

    lines = []
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        signal = signal_map.get(symbol, {})
        label = signal.get("label") or "Neutral"
        lines.append(f"- {symbol}: {label}")
    return "\n".join(lines)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_text = " ".join(context.args) if context.args else ""
    account_id = user_text.strip() or None
    supabase = get_supabase()
    if not supabase:
        await update.message.reply_text(
            "Supabase is not configured yet. Set SUPABASE_URL and SUPABASE_SERVICE_KEY before registering."
        )
        return

    if not account_id:
        await update.message.reply_text(
            "Use /start <account_id> to register this chat to a family account. Example: /start 1"
        )
        return

    try:
        account_id_int = int(account_id)
    except ValueError:
        await update.message.reply_text("Account ID must be a number.")
        return

    response = supabase.table("accounts").select("id").eq("id", account_id_int).execute()
    rows = getattr(response, "data", []) or []
    if not rows:
        await update.message.reply_text(f"Account #{account_id_int} was not found in Supabase.")
        return

    payload = {
        "chat_id": str(chat_id),
        "account_id": account_id_int,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    supabase.table("telegram_subscribers").upsert(payload, on_conflict="chat_id").execute()
    name = _account_name_for_id(supabase, account_id_int)
    await update.message.reply_text(f"Registered chat {chat_id} to {name} (account #{account_id_int}).")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Commands:\n/start <account_id> - register this chat to a family account\n/help - show this message"
    )


def build_application() -> Application:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to run the Telegram bot.")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    return app


async def send_new_ipo_alerts() -> None:
    supabase = get_supabase()
    if supabase is None:
        return
    response = supabase.table("ipo_alerts").select("*").order("close_date").execute()
    rows = getattr(response, "data", []) or []
    if not rows:
        return

    today = datetime.now(timezone.utc).date()
    subscribers = supabase.table("telegram_subscribers").select("chat_id,account_id").execute()
    subs = getattr(subscribers, "data", []) or []
    for sub in subs:
        chat_id = sub.get("chat_id")
        if not chat_id:
            continue
        account_id = sub.get("account_id")
        body = []
        for row in rows:
            close_date = row.get("close_date")
            if close_date and datetime.strptime(close_date, "%Y-%m-%d").date() >= today:
                body.append(
                    f"{row.get('company_name')} ({row.get('symbol')})\n"
                    f"Open: {row.get('open_date')} | Close: {row.get('close_date')}\n"
                    f"Shares: {row.get('shares_offered', 0):,} | Type: {row.get('share_type', 'ordinary')}"
                )
        if body:
            summary = _signal_summary_for_account(supabase, account_id) if account_id else "No holdings summary available."
            text = "New IPO opportunity:\n\n" + "\n\n".join(body) + "\n\nPortfolio signal summary:\n" + summary
            try:
                from telegram import Bot
                bot = Bot(token=os.environ["TELEGRAM_BOT_TOKEN"])
                await bot.send_message(chat_id=chat_id, text=text)
            except Exception:
                pass


async def send_ipo_closing_reminders() -> None:
    supabase = get_supabase()
    if supabase is None:
        return
    response = supabase.table("ipo_alerts").select("*").execute()
    rows = getattr(response, "data", []) or []
    tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
    relevant = [
        row for row in rows
        if row.get("close_date") and datetime.strptime(row["close_date"], "%Y-%m-%d").date() == tomorrow
    ]
    if not relevant:
        return

    subscribers = supabase.table("telegram_subscribers").select("chat_id,account_id").execute()
    subs = getattr(subscribers, "data", []) or []
    for sub in subs:
        chat_id = sub.get("chat_id")
        if not chat_id:
            continue
        account_id = sub.get("account_id")
        entries = []
        for row in relevant:
            entries.append(
                f"{row.get('company_name')} ({row.get('symbol')}) closes tomorrow. "
                f"Open: {row.get('open_date')} | Close: {row.get('close_date')} | Shares: {row.get('shares_offered', 0):,}"
            )
        if entries:
            summary = _signal_summary_for_account(supabase, account_id) if account_id else "No holdings summary available."
            text = "IPO closing reminder:\n\n" + "\n".join(entries) + "\n\nPortfolio signal summary:\n" + summary
            try:
                from telegram import Bot
                bot = Bot(token=os.environ["TELEGRAM_BOT_TOKEN"])
                await bot.send_message(chat_id=chat_id, text=text)
            except Exception:
                pass


async def send_daily_digest() -> None:
    supabase = get_supabase()
    if supabase is None:
        return
    response = supabase.table("ipo_alerts").select("*").gte("close_date", datetime.now(timezone.utc).date().isoformat()).execute()
    upcoming = getattr(response, "data", []) or []
    subscribers = supabase.table("telegram_subscribers").select("chat_id,account_id").execute()
    subs = getattr(subscribers, "data", []) or []
    for sub in subs:
        chat_id = sub.get("chat_id")
        account_id = sub.get("account_id")
        if not chat_id or not account_id:
            continue
        summary = _signal_summary_for_account(supabase, account_id)
        lines = [f"Daily digest for account #{account_id}", summary]
        if upcoming:
            lines.append("Upcoming IPOs:")
            for row in upcoming[:3]:
                lines.append(f"- {row.get('company_name')} ({row.get('symbol')}): {row.get('close_date')}")
        try:
            from telegram import Bot
            bot = Bot(token=os.environ["TELEGRAM_BOT_TOKEN"])
            await bot.send_message(chat_id=chat_id, text="\n".join(lines))
        except Exception:
            pass


def run_bot() -> None:
    app = build_application()
    app.run_polling()


def main() -> None:
    parser = argparse.ArgumentParser(description="Telegram bot for IPO and family portfolio alerts.")
    parser.add_argument("--send-alerts", action="store_true", help="Send IPO alert messages to subscribers")
    parser.add_argument("--send-reminders", action="store_true", help="Send IPO close reminders")
    parser.add_argument("--send-digest", action="store_true", help="Send the daily family digest")
    parser.add_argument("--run-bot", action="store_true", help="Start the Telegram polling bot")
    args = parser.parse_args()

    if args.send_alerts:
        asyncio.run(send_new_ipo_alerts())
        return
    if args.send_reminders:
        asyncio.run(send_ipo_closing_reminders())
        return
    if args.send_digest:
        asyncio.run(send_daily_digest())
        return
    if args.run_bot:
        run_bot()
        return
    run_bot()


if __name__ == "__main__":
    main()
