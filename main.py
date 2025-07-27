# --------------------------------------------- #
# Plugin Name           : Telegram Support Bot  #
# Author Name           : fabston               #
# File Name             : main.py               #
# --------------------------------------------- #
import time
import config
from resources import mysql_handler as mysql
from resources import markups_handler as markup
from resources import msg_handler as msg
from resources.utils import normalize_language_input

import telebot
from datetime import datetime, timedelta
import arrow
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

bot = telebot.TeleBot(config.token)

mysql.run_migrations()
mysql.createTables()
# Safe “ensure”
try:
    mysql.ensure_claimed_by_column()
except Exception as e:
    print("⚠️ ensure_claimed_by_column:", e)

# Runtime memory
pending_issue_choice = {}      # {user_id: {"relate_ticket_id": int}}
user_registration_state = {}   # legacy variable—still harmless

# -------------------- Helpers -------------------- #
def is_agent(uid):
    return mysql.get_agent_languages(uid) is not None

def is_admin(uid):
    return uid in getattr(config, 'admin_ids', [])

def dm_only(message):
    return message.chat.type != 'private'

def send_agent_welcome(bot_obj, user_id, invite_link):
    text = (
        "🎉 *Welcome aboard, Agent!*\n\n"
        "📍 *Run these commands in DM with the bot*\n"
        "  `/mytickets` – your active tickets\n"
        "  `/whoami` – profile & stats\n"
        "  `/setlang en,es` – update your languages\n\n"
        "📍 *Run these in the support group*\n"
        "  `/resolve <user_id>` – mark a ticket resolved\n"
        "  `/close <user_id>` – close a *resolved* ticket (admin can force-close)\n"
        "  `/claim_ticket` – manual claim if button fails\n\n"
        f"✅ Join support group:\n{invite_link}"
    )
    bot_obj.send_message(user_id, text, parse_mode="Markdown", disable_web_page_preview=True)

# ---------- Language helpers (Milestone 5) ----------
def build_lang_kb():
    kb = InlineKeyboardMarkup()
    row = []
    for code, label in config.LANG_OPTIONS.items():
        row.append(InlineKeyboardButton(label, callback_data=f"user_set_lang_{code}"))
        if len(row) == 2:
            kb.row(*row)
            row = []
    if row:
        kb.row(*row)
    return kb

def ensure_user_language(message):
    """Ensure user has a language in DB; if not, try TG code or prompt."""
    uid = message.from_user.id
    saved = mysql.get_user_language(uid)
    if saved:
        return True

    tg_code = getattr(message.from_user, 'language_code', None)
    if tg_code and tg_code in config.LANG_OPTIONS:
        mysql.save_user_language(uid, tg_code)
        return True

    bot.send_message(
        uid,
        "🌐 Please choose your language:",
        reply_markup=build_lang_kb()
    )
    return False

# -------------------- Agent Onboarding -------------------- #
@bot.message_handler(commands=['become_agent'])
def handle_agent_request(message):
    if dm_only(message):
        return
    user_id = message.from_user.id
    bot.send_message(user_id, "📝 Please enter your *full name*:", parse_mode="Markdown")
    bot.register_next_step_handler(message, collect_name)

def collect_name(message):
    full_name = message.text.strip()
    bot.send_message(message.from_user.id, "🌍 What languages do you speak?")
    bot.register_next_step_handler(message, lambda m: collect_languages(m, full_name))

def collect_languages(message, full_name):
    languages = message.text.strip()
    bot.send_message(message.from_user.id, "⏰ When are you mostly available (e.g., 9AM–5PM)?")
    bot.register_next_step_handler(message, lambda m: finalize_request(m, full_name, languages))

def finalize_request(message, full_name, languages):
    availability = message.text.strip()
    user_id = message.from_user.id
    try:
        normalized_languages = normalize_language_input(languages)
    except ValueError as e:
        bot.send_message(user_id, f"❌ {e}\n\nPlease enter valid languages (e.g. English, German).")
        return

    mysql.save_pending_agent(user_id, full_name, normalized_languages, availability)
    bot.send_message(user_id, "✅ Your request has been submitted for review. Please wait for admin approval.")

    text = (
        f"📥 *New Agent Request*\n\n"
        f"👤 Name: `{full_name}`\n"
        f"🆔 User ID: `{user_id}`\n"
        f"🌍 Languages: `{languages}`\n"
        f"⏰ Availability: `{availability}`\n\n"
        f"Use `/approve {user_id}` or `/reject {user_id}`"
    )
    approval_markup = InlineKeyboardMarkup()
    approval_markup.add(
        InlineKeyboardButton("✅ Approve", callback_data=f"approve_agent_{user_id}"),
        InlineKeyboardButton("❌ Reject",  callback_data=f"reject_agent_{user_id}")
    )
    bot.send_message(config.support_chat, text, parse_mode='Markdown', reply_markup=approval_markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith(('approve_agent_', 'reject_agent_')))
def handle_agent_approval(call):
    try:
        user_id = int(call.data.split('_')[-1])

        if call.data.startswith('approve_agent_'):
            mysql.approve_agent(user_id)
            bot.answer_callback_query(call.id, "✅ Agent Approved!")
            bot.edit_message_text("✅ This agent has been approved.",
                                  chat_id=call.message.chat.id, message_id=call.message.message_id)

            invite = bot.create_chat_invite_link(chat_id=config.support_chat, member_limit=1)
            send_agent_welcome(bot, user_id, invite.invite_link)
        else:
            mysql.reject_agent(user_id)
            bot.answer_callback_query(call.id, "❌ Agent Rejected")
            bot.edit_message_text("❌ This agent request was rejected.",
                                  chat_id=call.message.chat.id, message_id=call.message.message_id)
            bot.send_message(user_id, "❌ Your request to become an agent was rejected.")
    except Exception as e:
        print("⚠️ Error in agent approval callback:", e)
        bot.answer_callback_query(call.id, "❌ Error processing this action.")

# -------------------- User Commands -------------------- #
@bot.message_handler(commands=['start'])
def cmd_start(message):
    if message.chat.type == 'private':
        bot.send_message(
            message.chat.id,
            config.text_messages['start'].format(message.from_user.first_name) + msg.repo(),
            parse_mode='Markdown',
            disable_web_page_preview=True,
            reply_markup=markup.faqButton()
        )
        mysql.start_bot(message.chat.id)
    else:
        bot.reply_to(message, "Please send me a PM if you'd like to talk to the Support Team.")

@bot.message_handler(commands=['faq'])
def cmd_faq(message):
    if message.chat.type == 'private':
        bot.reply_to(message, config.text_messages['faqs'], parse_mode='Markdown', disable_web_page_preview=True)

@bot.message_handler(commands=['set_language', 'setlang_user'])
def cmd_set_language(message):
    if message.chat.type != 'private':
        bot.reply_to(message, "📬 Please DM me for this command.")
        return
    bot.send_message(
        message.chat.id,
        "🌐 Select your language:",
        reply_markup=build_lang_kb()
    )

# -------------------- Ticket Lists & Admin Actions -------------------- #
@bot.message_handler(commands=['tickets', 't'])
def cmd_tickets(message):
    if message.chat.id != config.support_chat:
        return

    if not mysql.open_tickets:
        bot.reply_to(message, "ℹ️ Great job, you answered all your tickets!")
        return

    ot_msg = '📨 *Open tickets:*\n\n'
    now = arrow.now()
    for user in mysql.open_tickets:
        bot.send_chat_action(message.chat.id, 'typing')
        data = mysql.user_tables(int(user))
        ot_link = data['open_ticket_link']
        ot_time = data['open_ticket_time']
        if ot_time:
            diff = datetime.now() - ot_time
            time_since_secs = diff.total_seconds()
            time_since = now.shift(seconds=-time_since_secs).humanize()
        else:
            time_since = "just now"

        alert = ' ↳ ⚠️ ' if ot_time and (datetime.now() - ot_time) > timedelta(hours=config.open_ticket_emoji) else ' ↳ '
        chat = bot.get_chat(int(user))
        ot_msg += "• [{0}{1}](tg://user?id={2}) (`{2}`)\n{5}_{3}_ [➜ Go to msg]({4})\n".format(
            chat.first_name,
            f' {chat.last_name}' if chat.last_name else '',
            int(user), time_since, ot_link, alert
        )
    bot.send_message(message.chat.id, ot_msg, parse_mode='Markdown')

# ------------- Milestone 4: Resolve & Close control ------------- #
@bot.message_handler(commands=['resolve'])
def cmd_resolve(message):
    if message.chat.id != config.support_chat:
        return
    if not is_agent(message.from_user.id):
        return

    user_id = None
    if message.reply_to_message and '(#id' in msg.msgCheck(message):
        user_id = msg.getUserID(message)
    elif msg.getReferrer(message.text):
        try:
            user_id = int(msg.getReferrer(message.text))
        except ValueError:
            pass

    if not user_id:
        bot.reply_to(message, "Reply to the ticket or `/resolve <user_id>`.", parse_mode='Markdown')
        return

    ticket = mysql.get_current_ticket(user_id)
    if not ticket:
        bot.reply_to(message, "❌ No open ticket for that user.")
        return

    claimer = ticket['claimed_by']
    if claimer and claimer != message.from_user.id and not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Only the claiming agent (or an admin) can resolve this ticket.")
        return

    mysql.mark_ticket_resolved(ticket['id'])
    bot.reply_to(message, f"✅ Ticket `{ticket['id']}` for `{user_id}` marked *resolved*.", parse_mode='Markdown')

@bot.message_handler(commands=['close', 'c'])
def cmd_close(message):
    if message.chat.id != config.support_chat:
        return

    user_id = None
    if message.reply_to_message and '(#id' in msg.msgCheck(message):
        user_id = msg.getUserID(message)
    elif msg.getReferrer(message.text):
        try:
            user_id = int(msg.getReferrer(message.text))
        except ValueError:
            pass

    if not user_id:
        bot.reply_to(message, "ℹ️ Reply to the ticket message or use `/close <user_id>`.",
                     parse_mode='Markdown')
        return

    ticket = mysql.get_current_ticket(user_id)
    if not ticket:
        bot.reply_to(message, '❌ That user has no open ticket...')
        return

    if not is_admin(message.from_user.id) and ticket['resolved'] == 0:
        bot.reply_to(message, "❌ Mark it resolved first with `/resolve <user_id>`.", parse_mode='Markdown')
        return

    current_claimer = ticket['claimed_by']
    if current_claimer:
        mysql.increment_resolved_and_pay(current_claimer)

    mysql.close_ticket(ticket['id'])
    mysql.reset_user_ticket_state(user_id)
    bot.reply_to(message, f'✅ Ticket `{ticket["id"]}` closed for `{user_id}`.', parse_mode='Markdown')

@bot.message_handler(commands=['banned'])
def cmd_banned(message):
    if message.chat.id != config.support_chat:
        return
    if not mysql.banned:
        bot.reply_to(message, "ℹ️ Great news, nobody got banned... Yet.")
        return

    ot_msg = '⛔️ *Banned users:*\n\n'
    for user in mysql.banned:
        bot.send_chat_action(message.chat.id, 'typing')
        ot_link = mysql.user_tables(int(user))['open_ticket_link']
        chat = bot.get_chat(int(user))
        ot_msg += "• [{0}{1}](tg://user?id={2}) (`{2}`)\n[➜ Go to last msg]({3})\n".format(
            chat.first_name,
            f' {chat.last_name}' if chat.last_name else '',
            int(user), ot_link
        )
    bot.send_message(message.chat.id, ot_msg, parse_mode='Markdown')

@bot.message_handler(commands=['ban'])
def cmd_ban(message):
    try:
        if message.chat.id != config.support_chat:
            return
        target_id = None
        if message.reply_to_message and '(#id' in msg.msgCheck(message):
            target_id = msg.getUserID(message)
        elif msg.getReferrer(message.text):
            target_id = int(msg.getReferrer(message.text))
        if not target_id:
            bot.reply_to(message, 'ℹ️ Reply to a message or mention a `User ID`.', parse_mode='Markdown')
            return

        banned_status = mysql.user_tables(target_id)['banned']
        if banned_status == 1:
            bot.reply_to(message, '❌ That user is already banned...')
        else:
            mysql.ban_user(target_id)
            try:
                mysql.reset_user_ticket_state(target_id)
            except Exception:
                pass
            bot.reply_to(message, '✅ Ok, banned that user!')
    except TypeError:
        bot.reply_to(message, '❌ Are you sure I interacted with that user before...?')

@bot.message_handler(commands=['unban'])
def cmd_unban(message):
    try:
        if message.chat.id != config.support_chat:
            return
        target_id = None
        if message.reply_to_message and '(#id' in msg.msgCheck(message):
            target_id = msg.getUserID(message)
        elif msg.getReferrer(message.text):
            target_id = int(msg.getReferrer(message.text))
        if not target_id:
            bot.reply_to(message, 'ℹ️ Reply to a message or mention a `User ID`.', parse_mode='Markdown')
            return

        banned_status = mysql.user_tables(target_id)['banned']
        if banned_status == 0:
            bot.reply_to(message, '❌ That user is already un-banned...')
        else:
            mysql.unban_user(target_id)
            bot.reply_to(message, '✅ Ok, un-banned that user!')
    except TypeError:
        bot.reply_to(message, '❌ Are you sure I interacted with that user before...?')

# -------------------- Private Messages (Users & Agents) -------------------- #
@bot.message_handler(
    func=lambda m: m.chat.type == 'private' and not (getattr(m, 'text', '') or '').startswith('/'),
    content_types=['text', 'photo', 'document']
)
def echo_all(message):
    mysql.start_bot(message.chat.id)
    sender_id = message.chat.id

    # ---- AGENT DM FLOW ----
    if is_agent(sender_id):
        target_user = mysql.get_claimed_ticket_by_agent(sender_id)
        if target_user:
            msg.snd_handler(target_user, bot, message, message.text)
        else:
            bot.reply_to(message, "You haven't claimed any ticket. Claim one in the group first.")
        return

    # ---- USER FLOW ----
    # ensure language ONLY for users
    if not ensure_user_language(message):
        return

    # If user’s ticket is claimed -> send to that agent
    claimed_by_agent = mysql.get_ticket_claim(sender_id)
    if claimed_by_agent:
        msg.snd_to_agent(claimed_by_agent, bot, message)
        return

    # Normal (unclaimed) user flow
    data = mysql.user_tables(sender_id) or {}
    if data.get('banned', 0) == 1:
        return

    current_ticket = mysql.get_current_ticket(sender_id)
    if not current_ticket:
        last_unresolved = mysql.get_last_unresolved_ticket(sender_id)
        if last_unresolved and sender_id not in pending_issue_choice:
            kb = InlineKeyboardMarkup()
            kb.row(
                InlineKeyboardButton("🆕 New issue", callback_data=f"new_issue_{sender_id}"),
                InlineKeyboardButton("🔁 Related to past ticket", callback_data=f"relate_issue_{sender_id}_{last_unresolved['id']}")
            )
            bot.send_message(
                sender_id,
                "Is this a *new issue* or related to a *past ticket*?",
                parse_mode="Markdown",
                reply_markup=kb
            )
            return

    # Forward user message to support group
    msg.fwd_handler(sender_id, bot, message)

    # Save / update ticket links
    row = mysql.user_tables(sender_id)
    msg_link = row.get('open_ticket_link')
    if not current_ticket:
        ticket_id = mysql.create_ticket(sender_id, msg_link)
    else:
        ticket_id = current_ticket['id']
    mysql.mark_ticket_last_link(ticket_id, msg_link)

    # If user said it's related to old ticket, post context
    choice = pending_issue_choice.pop(sender_id, None)
    if choice:
        old_tid = choice.get("relate_ticket_id")
        if old_tid:
            old = mysql.get_ticket_by_id(old_tid)
            ctx_link = old.get('last_message_link') or old.get('first_message_link')
            bot.send_message(
                config.support_chat,
                f"🧷 *Context:* User `{sender_id}` says this is related to ticket `#{old_tid}`\nLast link: {ctx_link}",
                parse_mode="Markdown",
                disable_web_page_preview=True
            )

# -------------------- Group Replies -------------------- #
@bot.message_handler(func=lambda m: m.chat.id == config.support_chat,
                     content_types=['text', 'photo', 'document'])
def group_reply_handler(message):
    try:
        if not message.reply_to_message or '(#id' not in msg.msgCheck(message):
            return

        user_id = msg.getUserID(message)
        claimed_by = mysql.get_ticket_claim(user_id)
        banned_status = mysql.user_tables(user_id)['banned']

        if claimed_by:
            if claimed_by != message.from_user.id:
                bot.reply_to(message, "❌ This ticket is already claimed by another agent.")
            else:
                bot.reply_to(message, "❌ You claimed this ticket. Continue in private chat with the bot.")
            return

        if banned_status == 1:
            mysql.unban_user(user_id)
            bot.reply_to(message,
                         'ℹ️ *FYI: That user was banned.*\n_Un-banned and sent message!_',
                         parse_mode='Markdown')

        msg.snd_handler(user_id, bot, message, message.text)

    except telebot.apihelper.ApiException:
        bot.reply_to(message, '❌ Could not send the message to the user (maybe blocked the bot).')
    except Exception as e:
        bot.reply_to(message, '❌ Invalid command or reply format.')
        print("⚠️ Error in group_reply_handler:", e)

# -------------------- Claim Ticket & Close Button -------------------- #
@bot.message_handler(commands=['claim_ticket'])
def claim_ticket_handler(message):
    if message.chat.id != config.support_chat:
        return

    if message.reply_to_message and '(#id' in msg.msgCheck(message):
        user_id = msg.getUserID(message)
        claimer_id = message.from_user.id
        existing_claim = mysql.get_ticket_claim(user_id)

        if existing_claim and existing_claim != claimer_id:
            bot.reply_to(message, "❌ Ticket already claimed by another agent.")
        elif existing_claim == claimer_id:
            bot.reply_to(message, "ℹ️ You already claimed this ticket.")
        else:
            mysql.claim_ticket(user_id, claimer_id)
            mysql.increment_claim(claimer_id)

            ticket = mysql.get_current_ticket(user_id)
            if ticket:
                mysql.set_ticket_claim(ticket['id'], claimer_id)

            bot.reply_to(message, f"✅ You have claimed the ticket for user {user_id}.")
    else:
        bot.reply_to(message, "ℹ️ Please reply to the ticket message to claim it.")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if not call.message:
        return

    data = call.data
    print(f"🔁 Callback received: {data}")

    # FAQ
    if data == "faqCallbackdata":
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=config.text_messages['faqs'],
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        return

    # User language selection
    if data.startswith("user_set_lang_"):
        code = data.split("_")[-1]
        if code not in config.LANG_OPTIONS:
            bot.answer_callback_query(call.id, "❌ Unsupported language.")
            return
        uid = call.from_user.id
        mysql.save_user_language(uid, code)
        bot.answer_callback_query(call.id, "✅ Language saved!")
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"✅ Language set to *{config.LANG_OPTIONS[code]}*.",
            parse_mode="Markdown"
        )
        return

    # Issue type choice
    if data.startswith("new_issue_") or data.startswith("relate_issue_"):
        parts = data.split('_')
        uid = int(parts[2])
        if data.startswith("new_issue_"):
            pending_issue_choice.pop(uid, None)
            bot.answer_callback_query(call.id, "New issue noted.")
        else:
            tid = int(parts[3])
            pending_issue_choice[uid] = {"relate_ticket_id": tid}
            bot.answer_callback_query(call.id, "Linked to past ticket.")
        return

    # Claim
    if data.startswith("claim_ticket_"):
        try:
            user_id = int(data.split("_")[-1])
            claimer_id = call.from_user.id
            claimer_name = f"[{call.from_user.first_name}](tg://user?id={claimer_id})"

            existing_claim = mysql.get_ticket_claim(user_id)
            user_lang = mysql.get_user_language(user_id)
            agent_langs = mysql.get_agent_languages(claimer_id)

            if agent_langs is None:
                bot.answer_callback_query(call.id, "❌ You are not a registered agent.", show_alert=True)
                return
            if not agent_langs:
                bot.answer_callback_query(call.id, "❌ You have no languages listed. Contact admin.", show_alert=True)
                return
            if user_lang not in agent_langs:
                bot.answer_callback_query(call.id,
                                          f"❌ You cannot claim. Requires '{user_lang}'.",
                                          show_alert=True)
                return
            if existing_claim and existing_claim != claimer_id:
                bot.answer_callback_query(call.id, "❌ Already claimed by another agent.", show_alert=True)
                return
            if existing_claim == claimer_id:
                bot.answer_callback_query(call.id, "ℹ️ You already claimed this ticket.")
                return

            mysql.claim_ticket(user_id, claimer_id)
            mysql.increment_claim(claimer_id)
            ticket = mysql.get_current_ticket(user_id)
            if ticket:
                mysql.set_ticket_claim(ticket['id'], claimer_id)

            bot.answer_callback_query(call.id, "✅ Ticket claimed!")

            bot_username = bot.get_me().username
            kb = InlineKeyboardMarkup()
            kb.row(
                InlineKeyboardButton("➡️ Continue Ticket in Private", url=f"https://t.me/{bot_username}"),
                InlineKeyboardButton("✅ Close Ticket", callback_data=f"close_ticket_{user_id}")
            )

            bot.send_message(
                chat_id=call.message.chat.id,
                text=(
                    f"🎯 *Ticket Claimed!*\n\n"
                    f"👤 User ID: `{user_id}`\n"
                    f"🧑‍💼 Claimed by: {claimer_name}\n\n"
                    f"_Choose an action below._"
                ),
                parse_mode="Markdown",
                reply_markup=kb
            )

            try:
                bot.send_message(
                    chat_id=claimer_id,
                    text=(
                        f"✅ You’ve *claimed* ticket for user `{user_id}`.\n"
                        f"Send your replies *here* to reach the user privately.\n\n"
                        f"_You’ll also receive their replies here._"
                    ),
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"⚠️ Could not DM agent: {e}")

        except Exception as e:
            print(f"❌ claim_ticket callback error: {e} | data={data}")
            bot.answer_callback_query(call.id, "❌ Invalid/expired claim button.")
        return

    # Close
    if data.startswith("close_ticket_"):
        try:
            user_id = int(data.split("_")[-1])
            caller_id = call.from_user.id

            ticket = mysql.get_current_ticket(user_id)
            if not ticket:
                bot.answer_callback_query(call.id, "❌ No open ticket.", show_alert=True)
                return

            if not is_admin(caller_id) and ticket['resolved'] == 0:
                bot.answer_callback_query(call.id, "❌ Resolve first with /resolve.", show_alert=True)
                return

            current_claimer = ticket['claimed_by']
            if current_claimer and current_claimer != caller_id and not is_admin(caller_id):
                bot.answer_callback_query(call.id, "❌ Only claiming agent or admin can close.", show_alert=True)
                return

            if current_claimer:
                mysql.increment_resolved_and_pay(current_claimer)

            mysql.close_ticket(ticket['id'])
            mysql.reset_user_ticket_state(user_id)

            bot.answer_callback_query(call.id, "✅ Ticket closed.")
            bot.send_message(call.message.chat.id,
                             f"✅ Ticket `{ticket['id']}` for `{user_id}` has been closed.",
                             parse_mode="Markdown")

            try:
                bot.send_message(user_id, "✅ Your ticket has been closed. If you need more help, just message me again.")
            except Exception as e:
                print("⚠️ Could not notify user:", e)

        except Exception as e:
            print("❌ close_ticket callback error:", e)
            bot.answer_callback_query(call.id, "❌ Failed to close ticket.", show_alert=True)

# -------------------- Agent Utility Commands -------------------- #
@bot.message_handler(commands=['mytickets'])
def cmd_mytickets(message):
    if dm_only(message):
        bot.reply_to(message, "📬 Please DM me for this command.")
        return
    if not is_agent(message.from_user.id):
        return
    with mysql.getConnection().cursor() as c:
        c.execute("SELECT userid, open_ticket_link FROM users WHERE claimed_by=%s AND open_ticket=1",
                  (message.from_user.id,))
        rows = c.fetchall()
    if not rows:
        bot.reply_to(message, "ℹ️ You have no active tickets.")
        return
    text = "🎟️ *Your active tickets:*\n\n"
    for r in rows:
        text += f"• `{r['userid']}` — [link]({r['open_ticket_link']})\n"
    bot.reply_to(message, text, parse_mode="Markdown", disable_web_page_preview=True)

@bot.message_handler(commands=['whoami'])
def cmd_whoami(message):
    if dm_only(message):
        bot.reply_to(message, "📬 Please DM me for this command.")
        return
    if not is_agent(message.from_user.id):
        return

    profile = mysql.get_agent_profile(message.from_user.id) or {}
    full_name    = profile.get('full_name') or f"{message.from_user.first_name} {message.from_user.last_name or ''}".strip()
    languages    = (profile.get('languages') or '').split(',') if profile.get('languages') else []
    availability = profile.get('availability') or '—'
    rate         = profile.get('commission_rate') or 0
    earnings     = profile.get('total_earnings') or 0
    claimed      = profile.get('tickets_claimed') or 0
    resolved     = profile.get('tickets_resolved') or 0

    with mysql.getConnection().cursor() as c:
        c.execute("SELECT COUNT(*) AS cnt FROM users WHERE claimed_by=%s AND open_ticket=1",
                  (message.from_user.id,))
        active = c.fetchone()['cnt']

    text = (
        f"🧑‍💼 *Agent Profile*\n"
        f"Name: `{full_name}`\n"
        f"ID: `{message.from_user.id}`\n"
        f"Languages: `{', '.join([l.strip() for l in languages]) or 'none'}`\n"
        f"Availability: `{availability}`\n"
        f"Commission rate: `{rate}`\n"
        f"Total earnings: `{earnings}`\n"
        f"Tickets claimed: `{claimed}` | resolved: `{resolved}` | active: `{active}`"
    )
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['setlang'])
def cmd_setlang(message):
    if dm_only(message):
        bot.reply_to(message, "📬 Please DM me for this command.")
        return
    if not is_agent(message.from_user.id):
        return
    parts = message.text.split(' ', 1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: `/setlang en,es`", parse_mode="Markdown")
        return
    raw = parts[1]
    try:
        normalized = normalize_language_input(raw)
    except ValueError as e:
        bot.reply_to(message, f"❌ {e}", parse_mode="Markdown")
        return
    with mysql.getConnection().cursor() as c:
        c.execute("UPDATE agents SET languages=%s WHERE user_id=%s", (normalized, message.from_user.id))
    bot.reply_to(message, f"✅ Languages updated to `{normalized}`", parse_mode="Markdown")

# -------------------- ADMIN COMMANDS -------------------- #
@bot.message_handler(commands=['set_commission'])
def cmd_set_commission(message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message, "Usage: `/set_commission <agent_id> <rate>`", parse_mode='Markdown')
        return
    try:
        agent_id = int(parts[1])
        rate = float(parts[2])
    except ValueError:
        bot.reply_to(message, "❌ Invalid args. Example: `/set_commission 123456789 0.15`", parse_mode='Markdown')
        return
    mysql.set_commission(agent_id, rate)
    bot.reply_to(message, f"✅ Commission rate for `{agent_id}` set to `{rate}`")

@bot.message_handler(commands=['agent_stat'])
def cmd_agent_stat(message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "Usage: `/agent_stat <agent_id>`", parse_mode='Markdown')
        return
    try:
        agent_id = int(parts[1])
    except ValueError:
        bot.reply_to(message, "❌ Invalid agent_id.", parse_mode='Markdown')
        return
    stat = mysql.get_agent_stats(agent_id)
    if not stat:
        bot.reply_to(message, "❌ Agent not found.")
        return
    text = (
        f"📊 *Agent Stats*\n"
        f"ID: `{agent_id}`\n"
        f"Name: `{stat['full_name'] or '—'}`\n"
        f"Commission: `{stat['commission_rate']}`\n"
        f"Tickets claimed: `{stat['tickets_claimed']}`\n"
        f"Tickets resolved: `{stat['tickets_resolved']}`\n"
        f"Total earnings: `{stat['total_earnings']}`"
    )
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['report_summary'])
def cmd_report_summary(message):
    if not is_admin(message.from_user.id):
        return
    r = mysql.get_report_summary()
    top_lines = "".join(
        f"• `{t['user_id']}` {t['full_name'] or ''} — {t['tickets_resolved']} resolved\n" for t in r['top']
    ) or '—'
    text = (
        "📈 *Support Performance Summary*\n\n"
        f"Total users/tickets: `{r['total_tickets']}`\n"
        f"Open tickets now: `{r['open_now']}`\n"
        f"Banned users: `{r['banned_cnt']}`\n"
        f"Resolved tickets (all agents): `{r['resolved']}`\n"
        f"Total earnings paid: `{r['earned']}`\n\n"
        "*Top agents by resolved:*\n"
        f"{top_lines}"
    )
    bot.reply_to(message, text, parse_mode='Markdown', disable_web_page_preview=True)

# -------------------- Utility Debug -------------------- #
@bot.message_handler(commands=['groupid'])
def get_group_id(message):
    print(f"Received /groupid from chat: {message.chat.id} | Type: {message.chat.type}")
    bot.reply_to(message, f"👥 Group ID: `{message.chat.id}`", parse_mode='Markdown')

@bot.message_handler(func=lambda m: True)
def log_chat_id(message):
    print(f"Message from chat_id={message.chat.id} | type={message.chat.type} | text={getattr(message, 'text', None)}")

# -------------------- Run Bot -------------------- #
print("Telegram Support Bot started...")
while True:
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"⚠️ Bot crashed with error: {e}")
        time.sleep(15)
