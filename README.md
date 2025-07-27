<p align="center"><a href="https://github.com/fabston/Telegram-Support-Bot" target="_blank"><img src="https://raw.githubusercontent.com/fabston/Telegram-Support-Bot/master/assets/logo.png"></a></p>

<p align="center">
    <a href="https://www.python.org/downloads/release/python-380/"><img src="https://img.shields.io/badge/python-3.9-blue.svg?style=plastic" alt="Python version"></a>
    <a href="https://github.com/fabston/Telegram-Support-Bot/blob/master/LICENSE"><img src="https://img.shields.io/github/license/fabston/Telegram-Support-Bot?style=plastic" alt="GitHub license"></a>
    <a href="https://github.com/fabston/Telegram-Support-Bot/issues"><img src="https://img.shields.io/github/issues/fabston/Telegram-Support-Bot?style=plastic" alt="GitHub issues"></a>
    <a href="https://github.com/fabston/Telegram-Support-Bot/pulls"><img src="https://img.shields.io/github/issues-pr/fabston/Telegram-Support-Bot?style=plastic" alt="GitHub pull requests"></a>
    <br /><a href="https://github.com/fabston/Telegram-Support-Bot/stargazers"><img src="https://img.shields.io/github/stars/fabston/Telegram-Support-Bot?style=social" alt="GitHub stars"></a>
    <a href="https://github.com/fabston/Telegram-Support-Bot/network/members"><img src="https://img.shields.io/github/forks/fabston/Telegram-Support-Bot?style=social" alt="GitHub forks"></a>
    <a href="https://github.com/fabston/Telegram-Support-Bot/watchers"><img src="https://img.shields.io/github/watchers/fabston/Telegram-Support-Bot?style=social" alt="GitHub watchers"></a>
</p>

<p align="center">
  <a href="#about">About</a> •
  <a href="#features">Features</a> •
  <a href="#commands">Commands</a> •
  <a href="#installation">Installation</a> •
  <a href="#testing--handoff">Testing&nbsp;&amp;&nbsp;Handoff</a> •
  <a href="#images">Images</a> •
  <a href="#how-can-i-help">Help</a>
</p>

## About
The **Telegram Support Bot** 📬 is an end-to-end help-desk solution designed for Telegram.  
It forwards user messages to a private support group, lets agents claim & resolve tickets, tracks agent performance/commissions, and routes requests by language ― all from one lightweight Python app.

---

## Features
| Group | Highlights |
|-------|------------|
| **Messaging** | • Forwards *text / photos / documents / stickers*<br>• Rich reply flow (user ↔ agent DM) |
| **Ticketing** | • Automatic ticket creation with unique ID<br>• Claim / resolve / close with safety checks<br>• Re-opening prompt (“new issue or related?”)<br>• Spam throttle & bad-word filter |
| **Agent Management** | • Self-service onboarding (`/become_agent`)<br>• Languages & availability profile<br>• Claim-restriction based on user language |
| **Performance & Commissions** | • Tracks *claimed / resolved* counts per agent<br>• Configurable commission-per-ticket & earnings ledger<br>• Admin stats & summary reports |
| **Language Routing** | • Detects Telegram `language_code`<br>• Fallback inline picker (`/set_language`)<br>• Agents may only claim tickets they can serve |
| **Admin Tools** | • Ban/Un-ban users, open-ticket list, full performance report<br>• Dynamic commission rates |
| **Misc** | • Customisable FAQ, emoji language badge, spam counter, MySQL persistence |

> 💡 Have a new idea? Open an [issue](https://github.com/fabston/Telegram-Support-Bot/issues/new/choose).

---

## Commands
### User
| Command | Description |
|---------|-------------|
| `/start` | Intro & FAQ link |
| `/faq` | Display FAQs |
| `/set_language` | Inline keyboard to pick UI language |

### Agent (run in **DM** with the bot unless noted)
| Command | Description |
|---------|-------------|
| `/become_agent` | Interactive onboarding |
| `/whoami` | Show agent profile, stats & earnings |
| `/mytickets` | List tickets you currently claim |
| `/setlang <codes>` | Update languages you serve (ex: `en,es`) |
| `/resolve <user_id>` *(group only)* | Mark a ticket resolved |
| `/claim_ticket` *(reply in group)* | Manual claim if button fails |

### Staff (group-only helpers - require agent role)
| Command | Description |
|---------|-------------|
| `/tickets` or `/t` | List open tickets |
| `/close <user_id>` | Close a *resolved* ticket (admin can force) |

### Admin superset
| Command | Description |
|---------|-------------|
| `/set_commission <agent_id> <rate>` | Set % rate for an agent |
| `/agent_stat <agent_id>` | Detailed agent stats |
| `/report_summary` | Overall performance dashboard |
| `/ban` / `/unban` | Ban / un-ban user by reply or ID |
| `/banned` | List banned users |
| `/groupid` | Echo group chat-id (debug) |

---

## Installation
> ⚠️ Best hosted on a small VPS (e.g. Hetzner CX11 €2.89/mo). [Sign up & get €20 credit](https://hetzner.cloud/?ref=tQ1NdT8zbfNY).

1. **MySQL prep**
   ```sql
   CREATE DATABASE TelegramSupportBot;
   CREATE USER 'SupportBotUser'@'localhost' IDENTIFIED BY '<PASSWORD>';
   GRANT ALL PRIVILEGES ON TelegramSupportBot.* TO 'SupportBotUser'@'localhost';
````

Then run the migration script in `docs/migrations.sql` to create `tickets`, add new columns, etc.
2\. **Clone & env**

```bash
git clone https://github.com/fabston/Telegram-Support-Bot.git
cd Telegram-Support-Bot
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp config.sample.py config.py            # edit values
```

3. **Run**

   ```bash
   python main.py
   ```

   Optionally install as a systemd service (`docs/supportbot.service`).

---

## Testing & Handoff

| Step                         | Actor        | What to verify                                 |
| ---------------------------- | ------------ | ---------------------------------------------- |
| Ticket creation & forwarding | User → group | `tickets` row created, `current_ticket_id` set |
| Claim flow                   | Agent        | Claim button updates DB, DM routing works      |
| Resolve/close rules          | Agent/Admin  | Cannot close unless resolved (except admin)    |
| Commission credit            | Agent        | `agents.total_earnings` increases on close     |
| Language gate                | Agent        | Claim blocked if language mismatch             |
| Re-opening prompt            | User         | Bot asks *new vs related* when appropriate     |
| Reports                      | Admin        | `/agent_stat` & `/report_summary` accurate     |

See `docs/test_checklist.md` for full script.

---

## Images

![Telegram Support Bot](https://raw.githubusercontent.com/fabston/Telegram-Support-Bot/master/assets/about.jpg)

---

## How can I help?

All contributions welcome 🙌 — the easiest: **star** ⭐ the repo, or file [`🐞 issues`](https://github.com/fabston/Telegram-Support-Bot/issues/new/choose).

---

<p align="center">
  <a href="https://www.buymeacoffee.com/fabston"><img alt="Buy Me A Coffee" src="https://github.com/fabston/Telegram-Airdrop-Bot/blob/main/assets/bmac.png?raw=true" width=200></a>
</p>