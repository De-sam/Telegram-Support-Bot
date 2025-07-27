# --------------------------------------------- #
# Plugin Name           : Telegram Support Bot  #
# Author Name           : fabston               #
# File Name             : msg_handler.py        #
# --------------------------------------------- #

import config
from resources import mysql_handler as mysql
from resources import lang_emojis as emoji
import re
import arrow
import traceback
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


def getReferrer(text):
    parts = text.split()
    return parts[1] if len(parts) > 1 else None


def msg_type(message):
    if message.content_type == 'text':
        return message.text
    elif message.content_type in ['photo', 'document']:
        return message.caption or ''
    return ''


def getUserID(message):
    src = message.reply_to_message
    if src.content_type == 'text':
        return int(src.text.split('(#id')[1].split(')')[0])
    elif src.content_type in ['photo', 'document']:
        return int(src.caption.split('(#id')[1].split(')')[0])
    return None


def msgCheck(message):
    src = message.reply_to_message
    if src.content_type == 'text':
        return src.text
    elif src.content_type in ['photo', 'document']:
        return src.caption
    return ''


def msgCaption(message):
    return message.caption if message.caption else ''


# (Support -> User Handler)
def snd_handler(user_id, bot, message, txt):
    try:
        if message.content_type == 'text':
            bot.send_chat_action(user_id, 'typing')
            bot.send_message(
                user_id,
                config.text_messages['support_response'].format(bot.get_chat(user_id).first_name) + f'\n\n{message.text}',
                parse_mode='Markdown',
                disable_web_page_preview=True
            )

        elif message.content_type == 'photo':
            bot.send_chat_action(user_id, 'upload_photo')
            bot.send_photo(
                user_id,
                message.photo[-1].file_id,
                caption=config.text_messages['support_response'].format(bot.get_chat(user_id).first_name) + f'\n\n{msgCaption(message)}',
                parse_mode='Markdown'
            )

        elif message.content_type == 'document':
            bot.send_chat_action(user_id, 'upload_document')
            bot.send_document(
                user_id,
                message.document.file_id,
                caption=config.text_messages['support_response'].format(bot.get_chat(user_id).first_name) + f'\n\n{msgCaption(message)}',
                parse_mode='Markdown'
            )
        else:
            bot.reply_to(message, '❌ That format is not supported.')
    except Exception as e:
        print("❌ Failed to send message to user:", e)
        traceback.print_exc()
        try:
            bot.reply_to(message, '❌ That format is not supported.')
        except Exception:
            pass

def snd_to_agent(agent_id, bot, message):
    """
    Send the user's private message to the claiming agent (in the agent's DM).
    """
    try:
        if message.content_type == 'text':
            bot.send_chat_action(agent_id, 'typing')
            bot.send_message(
                agent_id,
                f"{message.text}",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )

        elif message.content_type == 'photo':
            bot.send_chat_action(agent_id, 'upload_photo')
            bot.send_photo(
                agent_id,
                message.photo[-1].file_id,
                caption=f"{msgCaption(message)}",
                parse_mode='Markdown'
            )

        elif message.content_type == 'document':
            bot.send_chat_action(agent_id, 'upload_document')
            bot.send_document(
                agent_id,
                message.document.file_id,
                caption=f"{msgCaption(message)}",
                parse_mode='Markdown'
            )

        else:
            # Ignore unsupported types or add more handlers (voice, video, etc.)
            pass

    except Exception as e:
        print("❌ Failed to DM agent:", e)


def fwd_handler(user_id, bot, message):
    # Update the Spamfilter
    mysql.spam(message.chat.id)

    # Capture and save user language
    lang_code = message.from_user.language_code
    lang_emoji = emoji.lang_emoji(lang_code)
    mysql.save_user_language(message.from_user.id, lang_code)

    # Claim button
    claim_markup = InlineKeyboardMarkup()
    claim_markup.add(
        InlineKeyboardButton(
            f"🎯 Claim Ticket ({lang_code.upper()})",
            callback_data=f"claim_ticket_{message.from_user.id}"
        )
    )

    # Forward to support group
    if message.content_type == 'text':
        msg = bot.send_message(
            config.support_chat,
            "[{0}{1}](tg://user?id={2}) (#id{2}) | {3}\n\n{4}".format(
                message.from_user.first_name,
                f" {message.from_user.last_name}" if message.from_user.last_name else '',
                message.from_user.id,
                lang_emoji,
                message.text
            ),
            parse_mode='Markdown',
            disable_web_page_preview=True,
            reply_markup=claim_markup
        )

    elif message.content_type == 'photo':
        msg = bot.send_photo(
            config.support_chat,
            message.photo[-1].file_id,
            caption="[{0}{1}](tg://user?id={2}) (#id{2}) | {3}\n\n{4}".format(
                message.from_user.first_name,
                f" {message.from_user.last_name}" if message.from_user.last_name else '',
                message.from_user.id,
                lang_emoji,
                msgCaption(message)
            ),
            parse_mode='Markdown',
            reply_markup=claim_markup
        )

    elif message.content_type == 'document':
        msg = bot.send_document(
            config.support_chat,
            message.document.file_id,
            caption="[{0}{1}](tg://user?id={2}) (#id{2}) | {3}\n\n{4}".format(
                message.from_user.first_name,
                f" {message.from_user.last_name}" if message.from_user.last_name else '',
                message.from_user.id,
                lang_emoji,
                msgCaption(message)
            ),
            parse_mode='Markdown',
            reply_markup=claim_markup
        )

    elif message.content_type == 'sticker':
        # Send sticker to group (was incorrectly sending to user before)
        msg = bot.send_sticker(config.support_chat, message.sticker.file_id)

    else:
        bot.reply_to(message, "❌ That format is not supported and won't be forwarded.")
        return False

    # Save the ticket link in DB
    import re
    channel_id = re.sub(r"-100(\S+)", r"\1", str(config.support_chat))
    message_link = f'https://t.me/c/{channel_id}/{msg.message_id}'
    mysql.post_open_ticket(message_link, user_id)

    # Notify user
    try:
        bot.send_message(
            user_id,
            "✅ Your message has been submitted.\nOur support team will respond shortly.",
            parse_mode='Markdown'
        )
    except Exception as e:
        print("⚠️ Failed to send confirmation:", e)

    return True


def bad_words_handler(bot, message):
    if config.bad_words_toggle:
        try:
            if re.findall(config.regex_filter['bad_words'], msg_type(message)):
                bot.reply_to(message, '❗️ Watch your tongue...')
                return bad_words_handler
        except Exception:
            pass


def time_zone():
    return arrow.now(config.time_zone).strftime('%I:%M %p')


def repo():
    return '\n\n[» Source Code](github.com/vsnz/Telegram-Support-Bot)'


def spam_handler_warning(bot, user_id, message):
    if config.spam_toggle:
        ticket_spam = mysql.user_tables(user_id)['open_ticket_spam']
        if ticket_spam > config.spam_protection:
            bot.reply_to(
                message,
                '{}, your messages are not being forwarded anymore. Please wait until the team responded. Thank you.\n\n'
                f'_The support\'s local time is_ `{time_zone()}`.'.format(message.from_user.first_name),
                parse_mode='Markdown'
            )
            return spam_handler_warning


def spam_handler_blocked(bot, user_id, message):
    if config.spam_toggle:
        ticket_spam = mysql.user_tables(user_id)['open_ticket_spam']
        if ticket_spam == config.spam_protection - 1:
            fwd_handler(user_id, bot, message)
            bot.reply_to(
                message,
                'We will be with you shortly.\n\n{}, to prevent spam you can only send us *1* more message.\n\n'
                f'_The support\'s local time is_ `{time_zone()}`.'.format(message.from_user.first_name),
                parse_mode='Markdown'
            )
            return spam_handler_blocked
