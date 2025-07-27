# --------------------------------------------- #
# Plugin Name           : Telegram Support Bot  #
# Author Name           : fabston               #
# File Name             : config.py             #
# --------------------------------------------- #

# Telegram
token = '8358243654:AAGVh802-P823WU3CKd-ZiCcubHzt4f40Nc'  # More: https://core.telegram.org/bots#3-how-do-i-create-a-bot

# MySQL Database
mysql_host = 'localhost'
mysql_db   = 'TelegramSupportBot'
mysql_user = 'SupportBotUser'
mysql_pw = 'supportpass123'

# Support Chat (Chat ID)
support_chat = -1002759088455

admin_ids = [744260641]          # your Telegram ID(s)
ticket_commission_base = 1.0     # base amount per resolved ticket


# Misc
time_zone           = 'GMT+2'   # Supports time zone
bad_words_toggle    = True      # Enable / disable bad words filter
spam_toggle         = True      # Enable / disable spam filter
spam_protection     = 5         # How many consecutive messages can be sent without a reply from the team
open_ticket_emoji   = 24        # After X amount of HOURS an emoji will pop up at /tickets

# Messages
text_messages = {
    'start': 'Hi {}, how can we help you today?',
    'faqs': 'Your FAQ text goes in here.',
    'support_response': 'From: {}'                  # Support response is being added automatically. {} = refers to the staffs first name.
}

# Regex (https://regex101.com/)
regex_filter = {
    'bad_words': r'(?i)^(.*?(\b\w*fuck|shut up|dick|bitch|bastart|cunt|bollocks|bugger|rubbish|wanker|twat|suck|ass|pussy|arsch\w*\b)[^$]*)$'
}

# Which languages you want to support for routing
LANG_OPTIONS = {
    "en": "🇬🇧 English",
    "es": "🇪🇸 Español",
    "fr": "🇫🇷 Français",
    "de": "🇩🇪 Deutsch",
    "pt": "🇵🇹 Português",
    "ru": "🇷🇺 Русский",
    "tr": "🇹🇷 Türkçe",
    "ar": "🇸🇦 العربية",
    "id": "🇮🇩 Indonesia",
    "hi": "🇮🇳 हिन्दी"
}
DEFAULT_LANG = "en"
